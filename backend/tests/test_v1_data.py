from datetime import datetime

from tests.fakes import CUS_A, CUS_B, _tx


def test_every_v1_data_route_requires_a_session(client):
    for path in ("/v1/me", "/v1/me/summary", "/v1/me/products", "/v1/me/transactions", "/v1/disputes"):
        assert client.get(path).status_code == 401, path


# ------------------------------------------------------------------ products


def test_products_are_the_customers_own_with_the_number_masked(client, auth_headers):
    products = client.get("/v1/me/products", headers=auth_headers).json()
    assert {p["product_id"] for p in products} == {"PRD-A-SAV", "PRD-A-CC", "PRD-A-OLD"}
    assert "PRD-B-SAV" not in {p["product_id"] for p in products}
    saving = next(p for p in products if p["product_id"] == "PRD-A-SAV")
    assert saving["product_number_masked"] == "****4444"
    assert "1111222233334444" not in str(products)
    assert saving["kind"] == "deposit"
    assert next(p for p in products if p["product_id"] == "PRD-A-CC")["kind"] == "credit"


def test_active_products_come_first(client, auth_headers):
    products = client.get("/v1/me/products", headers=auth_headers).json()
    assert products[-1]["product_id"] == "PRD-A-OLD"  # Closed


def test_money_is_a_number_not_a_string(client, auth_headers):
    saving = client.get("/v1/me/products/PRD-A-SAV", headers=auth_headers).json()
    assert saving["current_balance"] == 1500000.5


def test_another_customers_product_is_404(client, auth_headers):
    assert client.get("/v1/me/products/PRD-B-SAV", headers=auth_headers).status_code == 404
    assert client.get("/v1/me/products/NOPE", headers=auth_headers).status_code == 404


# ------------------------------------------------------------------ transactions: paging and filters


def _many(store, count):
    for n in range(count):
        store.transactions[f"TXN-N{n:02d}"] = _tx(
            f"TXN-N{n:02d}", CUS_A, transaction_date=datetime(2026, 7, 1, 10, n, 0), product_id="PRD-A-CC"
        )


def test_pages_walk_the_history_newest_first_without_gaps_or_repeats(client, auth_headers, store):
    _many(store, 25)
    seen, cursor = [], None
    for _ in range(10):
        url = "/v1/me/transactions?limit=10" + (f"&cursor={cursor}" if cursor else "")
        page = client.get(url, headers=auth_headers).json()
        seen += [t["transaction_id"] for t in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    own = [t for t in store.transactions.values() if t["customer_id"] == CUS_A]
    assert len(seen) == len(own) == len(set(seen))
    assert seen == [t["transaction_id"] for t in sorted(own, key=lambda t: (t["transaction_date"], t["transaction_id"]), reverse=True)]


def test_last_page_has_no_cursor(client, auth_headers):
    page = client.get("/v1/me/transactions?limit=100", headers=auth_headers).json()
    assert page["next_cursor"] is None


def test_a_cursor_that_was_not_issued_here_is_422(client, auth_headers):
    assert client.get("/v1/me/transactions?cursor=garbage", headers=auth_headers).status_code == 422


def test_filters_by_product_status_merchant_and_dates(client, auth_headers, store):
    _many(store, 5)
    by_product = client.get("/v1/me/transactions?product_id=PRD-A-CC", headers=auth_headers).json()["items"]
    assert len(by_product) == 5 and all(t["product_id"] == "PRD-A-CC" for t in by_product)
    reversed_ = client.get("/v1/me/transactions?status=Reversed", headers=auth_headers).json()["items"]
    assert [t["transaction_id"] for t in reversed_] == ["TXN-A2"]
    by_merchant = client.get("/v1/me/transactions?merchant=libre", headers=auth_headers).json()["items"]
    assert [t["transaction_id"] for t in by_merchant] == ["TXN-A3"]
    january = client.get("/v1/me/transactions?from=2026-01-01&to=2026-01-31", headers=auth_headers).json()["items"]
    assert [t["transaction_id"] for t in january] == ["TXN-A3"]


def test_from_after_to_is_422(client, auth_headers):
    assert client.get("/v1/me/transactions?from=2026-02-01&to=2026-01-01", headers=auth_headers).status_code == 422


def test_limit_is_bounded(client, auth_headers):
    assert client.get("/v1/me/transactions?limit=0", headers=auth_headers).status_code == 422
    assert client.get("/v1/me/transactions?limit=101", headers=auth_headers).status_code == 422


def test_transactions_are_never_another_customers(client, auth_headers):
    ids = [t["transaction_id"] for t in client.get("/v1/me/transactions", headers=auth_headers).json()["items"]]
    assert "TXN-B1" not in ids


def test_each_transaction_says_whether_it_has_a_case(client, auth_headers):
    plain = {t["transaction_id"]: t for t in client.get("/v1/me/transactions", headers=auth_headers).json()["items"]}
    assert plain["TXN-A1"]["case_id"] is None
    case_id = client.post(
        "/v1/disputes", json={"transaction_id": "TXN-A1", "reason_code": "x", "summary": "s"}, headers=auth_headers
    ).json()["case_id"]
    after = {t["transaction_id"]: t for t in client.get("/v1/me/transactions", headers=auth_headers).json()["items"]}
    assert after["TXN-A1"]["case_id"] == case_id
    assert after["TXN-A1"]["dispute_status"] == "open"
    assert after["TXN-A2"]["case_id"] is None


def test_no_fraud_ground_truth_in_any_row(client, auth_headers):
    text = client.get("/v1/me/transactions", headers=auth_headers).text
    assert "is_fraud" not in text and "fraud_score" not in text


# ------------------------------------------------------------------ summary and readiness


def test_summary_separates_what_is_owned_from_what_is_owed(client, auth_headers):
    summary = client.get("/v1/me/summary", headers=auth_headers).json()
    balances = {(b["currency"], b["kind"]): b for b in summary["balances"]}
    assert balances[("COP", "deposit")]["total"] == 1500000.5  # the closed account is not counted
    assert balances[("COP", "credit")]["total"] == 320000.0
    assert len(summary["recent_transactions"]) <= 5


def test_summary_counts_active_cases_by_status(client, auth_headers):
    case_id = client.post(
        "/v1/disputes", json={"transaction_id": "TXN-A1", "reason_code": "x", "summary": "s"}, headers=auth_headers
    ).json()["case_id"]
    assert client.get("/v1/me/summary", headers=auth_headers).json()["disputes"] == {"open": 1}
    client.post(f"/v1/disputes/{case_id}/resolve", json={"resolution": {}}, headers=auth_headers)
    assert client.get("/v1/me/summary", headers=auth_headers).json()["disputes"] == {"auto_resolved": 1}


def test_summary_of_a_customer_with_nothing_is_empty_not_an_error(client, store):
    from tests.fakes import CUS_B

    token = client.post("/session", json={"customer_id": CUS_B, "document_number": "CPF-456"}).json()["session_token"]
    summary = client.get("/v1/me/summary", headers={"Authorization": f"Bearer {token}"}).json()
    assert summary["disputes"] == {}


def test_health_and_ready(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/ready").json()["status"] == "ready"


def test_ready_is_503_when_the_database_is_down(client, store):
    async def down():
        raise ConnectionError("no database")

    store.ping = down
    assert client.get("/ready").status_code == 503


# ------------------------------------------------------------------ data freshness


def test_meta_data_says_when_the_data_was_last_refreshed(client, auth_headers):
    body = client.get("/v1/meta/data", headers=auth_headers).json()
    assert body["last_successful_run"]["status"] == "success"
    assert body["last_successful_run"]["finished_at"].startswith("2026-10-02T14:34")
    assert {"table": "transactions", "rows": 4425008} in body["gold"]


def test_meta_data_without_a_run_is_unknown_not_invented(client, auth_headers, store):
    store.meta = {"gold": [], "last_successful_run": None}
    body = client.get("/v1/meta/data", headers=auth_headers).json()
    assert body == {"gold": [], "last_successful_run": None}


def test_meta_data_needs_a_session(client):
    assert client.get("/v1/meta/data").status_code == 401
