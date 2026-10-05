"""The real SQL, against a real PostgreSQL. The fake store used by the other tests runs none of it.

Needs a server: PG_TEST_HOST (and PG_TEST_PORT, PG_TEST_USER, PG_TEST_PASSWORD). It creates a throwaway database
with gold tables of the same column types the dbt models produce, and drops it afterwards.
"""

import asyncio
import os
import shutil
import uuid
from datetime import date, datetime
from pathlib import Path

import asyncpg
import pytest

from app.db import BankStore
from app.migrate import MIGRATIONS_DIR, apply_migrations

pytestmark = pytest.mark.skipif(not os.environ.get("PG_TEST_HOST"), reason="set PG_TEST_HOST to run the Postgres tests")

GOLD = """
create schema gold;
create table gold.customers (customer_id text primary key, document_number text, first_name text, last_name text, country text);
create table gold.products (
    product_id text primary key, customer_id text, product_type text, product_number text, currency text,
    current_balance numeric(15,2), credit_limit numeric(15,2), interest_rate numeric(5,2), opening_date date,
    product_status text, days_past_due int, last_transaction_date timestamp);
create table gold.transactions (
    transaction_id text primary key, transaction_date timestamp, process_date date, product_id text, customer_id text,
    transaction_type text, transaction_category text, amount numeric(15,2), currency text, amount_usd numeric(15,2),
    channel text, branch_id text, merchant_name text, merchant_category text, transaction_country text,
    transaction_city text, transaction_status text, response_code text);
"""


def connection_args(database: str) -> dict:
    return dict(
        host=os.environ["PG_TEST_HOST"],
        port=int(os.environ.get("PG_TEST_PORT", "5432")),
        user=os.environ.get("PG_TEST_USER", "postgres"),
        password=os.environ.get("PG_TEST_PASSWORD", ""),
        database=database,
    )


@pytest.fixture()
def anyio_backend():
    return "asyncio"


@pytest.fixture()
async def database():
    name = f"backend_test_{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(**connection_args("postgres"))
    await admin.execute(f'create database "{name}"')
    conn = await asyncpg.connect(**connection_args(name))
    await conn.execute(GOLD)
    await conn.close()
    yield name
    await admin.execute(f'drop database "{name}" with (force)')
    await admin.close()


@pytest.fixture()
async def store(database):
    pool = await asyncpg.create_pool(**connection_args(database), init=BankStore._init_conn)
    bank = BankStore(pool)
    await bank.init_schema()
    yield bank
    await pool.close()


async def put(store, sql, *args):
    async with store.pool.acquire() as conn:
        await conn.execute(sql, *args)


async def add_customer(store, customer_id="C1", first="Ana"):
    await put(store, "insert into gold.customers values ($1, 'DOC1', $2, 'García', 'Colombia')", customer_id, first)


async def add_tx(store, tx_id, customer_id="C1", when=datetime(2026, 7, 1, 10, 0), status="Declined", merchant="Tienda", product="P1", amount=100):
    await put(
        store,
        """insert into gold.transactions values ($1, $2, $3, $4, $5, 'Purchase', 'Retail', $6, 'COP', null, 'POS', null,
                                                 $7, 'Retail', 'Colombia', 'Bogotá', $8, '51')""",
        tx_id, when, when.date(), product, customer_id, amount, merchant, status,
    )


@pytest.mark.anyio
async def test_migrations_build_the_schema_and_a_second_run_does_nothing(database):
    conn = await asyncpg.connect(**connection_args(database))
    first = await apply_migrations(conn)
    assert first == [
        "0001_baseline", "0002_login_accounts", "0003_dispute_per_transaction", "0004_repair_double_encoded_json",
        "0005_admin_console",
    ]
    assert await apply_migrations(conn) == []
    tables = {r["table_name"] for r in await conn.fetch("select table_name from information_schema.tables where table_schema = 'app'")}
    assert {"disputes", "dispute_events", "credentials", "schema_migrations"} <= tables
    await conn.close()


@pytest.mark.anyio
async def test_migration_0003_closes_older_duplicates_and_keeps_the_newest(database, tmp_path):
    """The agent used to open a new case on every attempt: a database like that has to migrate."""
    old = tmp_path / "old"
    old.mkdir()
    for name in ("0001_baseline.sql", "0002_login_accounts.sql"):
        shutil.copy(MIGRATIONS_DIR / name, old / name)
    conn = await asyncpg.connect(**connection_args(database))
    await apply_migrations(conn, old)
    for n, status in enumerate(["open", "open", "escalated"]):
        await conn.execute(
            "insert into app.disputes (customer_id, transaction_id, reason_code, summary, status, created_at) "
            "values ('C1', 'T1', 'x', 's', $1, now() + make_interval(mins => $2))",
            status, n,
        )
    await conn.execute("insert into app.disputes (customer_id, transaction_id, reason_code, summary) values ('C1', 'T2', 'x', 's')")

    assert await apply_migrations(conn) == [
        "0003_dispute_per_transaction", "0004_repair_double_encoded_json", "0005_admin_console",
    ]

    rows = await conn.fetch("select status from app.disputes where transaction_id = 'T1' order by created_at")
    assert [r["status"] for r in rows] == ["closed", "closed", "escalated"]  # the newest stays as it was
    events = await conn.fetch("select event from app.dispute_events where event = 'closed'")
    assert len(events) == 2
    assert await conn.fetchval("select status from app.disputes where transaction_id = 'T2'") == "open"
    with pytest.raises(asyncpg.UniqueViolationError):
        await conn.execute("insert into app.disputes (customer_id, transaction_id, reason_code, summary) values ('C1', 'T1', 'x', 's')")
    await conn.close()


@pytest.mark.anyio
async def test_a_case_per_transaction_even_when_two_requests_race(store):
    await add_customer(store)
    await add_tx(store, "T1")
    cases = await asyncio.gather(*[store.create_dispute("C1", "T1", "x", "s", {"transaction": {}}) for _ in range(6)])
    assert len({case["case_id"] for case in cases}) == 1  # the six requests got the same case
    assert await store.pool.fetchval("select count(*) from app.disputes") == 1
    assert await store.pool.fetchval("select count(*) from app.dispute_events where event = 'created'") == 1


@pytest.mark.anyio
async def test_dispute_lifecycle_in_sql(store):
    case = await store.create_dispute("C1", "T1", "x", "s", {"transaction": {"a": 1}})
    assert case["status"] == "open"
    again = await store.create_dispute("C1", "T1", "x", "s", {})
    assert again["case_id"] == case["case_id"]  # one case per (customer, transaction)

    resolved = await store.resolve_dispute("C1", str(case["case_id"]), "no_charge_confirmed")
    assert resolved["status"] == "auto_resolved" and resolved["resolved_at"] is not None
    assert await store.resolve_dispute("C1", str(case["case_id"]), "no_charge_confirmed") is None  # only open can be resolved

    escalated = await store.escalate_dispute("C1", str(case["case_id"]), {"request": "human"})
    # The handoff is a JSON object, not JSON text inside the jsonb value (the bug the real database showed).
    assert escalated["status"] == "escalated" and escalated["evidence"]["handoff"] == {"request": "human"}
    events = await store.get_dispute_events(str(case["case_id"]))
    assert [e["event"] for e in events] == ["created", "auto_resolved", "escalated"]
    assert events[-1]["payload"] == {"request": "human"}
    assert await store.escalate_dispute("OTHER", str(case["case_id"]), {}) is None  # not theirs


@pytest.mark.anyio
async def test_escalating_never_resets_a_case_a_specialist_has_or_has_closed(store):
    """The SQL guard: before, any status was overwritten and a re-report could undo a specialist's closure."""
    case = await store.create_dispute("C1", "T2", "x", "s", {})
    case_id = str(case["case_id"])
    await store.escalate_dispute("C1", case_id, {"request": "first"})
    await store.admin_transition(case_id, "in_progress", ("open", "escalated"), "claimed", {"by": "ops", "note": "mine"})
    kept = await store.escalate_dispute("C1", case_id, {"request": "second"})
    assert kept["status"] == "in_progress" and kept["evidence"]["handoff"] == {"request": "first"}  # untouched
    await store.admin_transition(case_id, "closed", ("in_progress",), "closed", {"note": "done", "resolution": "resolved_customer"})
    kept = await store.escalate_dispute("C1", case_id, {"request": "third"})
    assert kept["status"] == "closed"
    events = [e["event"] for e in await store.get_dispute_events(case_id)]
    assert events.count("escalated") == 1  # the refused calls left no event


@pytest.mark.anyio
async def test_a_case_without_a_transaction_is_never_a_duplicate(store):
    first = await store.create_dispute("C1", None, "x", "no transaction identified", {})
    second = await store.create_dispute("C1", None, "x", "no transaction identified", {})
    assert first["case_id"] != second["case_id"] and first["transaction_id"] is None


@pytest.mark.anyio
async def test_pages_follow_the_keyset_without_gaps_or_repeats(store):
    await add_customer(store)
    for n in range(25):
        await add_tx(store, f"T{n:02d}", when=datetime(2026, 7, 1 + n // 5, 10, n % 5))
    await add_tx(store, "TIE-A", when=datetime(2026, 8, 1, 9, 0))
    await add_tx(store, "TIE-B", when=datetime(2026, 8, 1, 9, 0))  # same instant: the id breaks the tie
    seen, cursor = [], None
    while True:
        items, cursor = await store.list_transactions_page("C1", cursor=cursor, limit=7)
        seen += [i["transaction_id"] for i in items]
        if cursor is None:
            break
    assert len(seen) == 27 == len(set(seen))
    assert seen[:2] == ["TIE-B", "TIE-A"]


@pytest.mark.anyio
async def test_filters_and_case_flag_in_sql(store):
    await add_customer(store)
    await add_tx(store, "T1", merchant="Farmacia Central", status="Approved", product="P1", when=datetime(2026, 1, 5, 10))
    await add_tx(store, "T2", merchant="Librería", status="Declined", product="P2", when=datetime(2026, 2, 5, 10))
    await add_tx(store, "TX", customer_id="OTHER", merchant="Farmacia")
    case = await store.create_dispute("C1", "T1", "x", "s", {})
    items, _ = await store.list_transactions_page("C1", merchant="farmacia")
    assert [(i["transaction_id"], i["dispute_status"]) for i in items] == [("T1", "open")]
    assert items[0]["case_id"] == case["case_id"]
    assert [i["transaction_id"] for i in (await store.list_transactions_page("C1", product_id="P2"))[0]] == ["T2"]
    assert [i["transaction_id"] for i in (await store.list_transactions_page("C1", status="Declined"))[0]] == ["T2"]
    assert [i["transaction_id"] for i in (await store.list_transactions_page("C1", date_from=date(2026, 2, 1), date_to=date(2026, 2, 5)))[0]] == ["T2"]  # 'to' is inclusive
    assert await store.list_transactions_page("C1", date_from=date(2027, 1, 1)) == ([], None)


@pytest.mark.anyio
async def test_a_closed_case_is_not_shown_as_the_transactions_case(store):
    await add_customer(store)
    await add_tx(store, "T1")
    case = await store.create_dispute("C1", "T1", "x", "s", {})
    await put(store, "update app.disputes set status = 'closed'")
    items, _ = await store.list_transactions_page("C1")
    assert items[0]["case_id"] is None
    again = await store.create_dispute("C1", "T1", "x", "s", {})
    assert again["case_id"] != case["case_id"]  # a closed case does not block reporting again


@pytest.mark.anyio
async def test_products_masked_classified_and_summed_in_sql(store):
    await add_customer(store)
    rows = [
        ("P1", "Cuenta Ahorro", "1111222233334444", "COP", 100, None, "Active"),
        ("P2", "Cuenta Corriente", "2222333344445555", "COP", 50, None, "Active"),
        ("P3", "Tarjeta Crédito", "3333444455556666", "COP", 30, 1000, "Active"),
        ("P4", "Cuenta Ahorro", "4444555566667777", "COP", 999, None, "Closed"),
        ("P5", "Seguro", "5555666677778888", "COP", 7, None, "Active"),
        ("P6", "Cuenta Ahorro", "6666777788889999", "USD", 5, None, "Active"),
    ]
    for pid, ptype, number, cur, bal, limit, status in rows:
        await put(store, "insert into gold.products values ($1, 'C1', $2, $3, $4, $5, $6, null, '2020-01-01', $7, null, '2026-06-01 13:45:00')",
                  pid, ptype, number, cur, bal, limit, status)
    products = await store.list_products("C1")
    assert [p["product_id"] for p in products][-1] == "P4"  # closed last
    one = await store.get_product("C1", "P1")
    assert one["product_number_masked"] == "****4444" and "1111222233334444" not in str(one)
    assert one["kind"] == "deposit" and (await store.get_product("C1", "P3"))["kind"] == "credit"
    assert one["last_transaction_date"] == datetime(2026, 6, 1, 13, 45)
    assert await store.get_product("OTHER", "P1") is None

    summary = await store.summary("C1")
    totals = {(b["currency"], b["kind"]): (float(b["total"]), b["products"]) for b in summary["balances"]}
    assert totals == {("COP", "deposit"): (150.0, 2), ("COP", "credit"): (30.0, 1), ("USD", "deposit"): (5.0, 1)}


@pytest.mark.anyio
async def test_login_lockout_in_sql(store):
    await add_customer(store)
    await store.upsert_credentials("C1", "Ana.Garcia", "hash", demo_label="Demo", demo_hint="h")
    assert (await store.get_credentials("ANA.garcia"))["customer_id"] == "C1"  # case-insensitive
    for _ in range(4):
        await store.record_login_failure("C1", 5, 15)
    assert (await store.get_credentials("ana.garcia"))["locked_until"] is None
    await store.record_login_failure("C1", 5, 15)
    assert (await store.get_credentials("ana.garcia"))["locked_until"] is not None
    await store.record_login_success("C1")
    row = await store.get_credentials("ana.garcia")
    assert row["failed_attempts"] == 0 and row["locked_until"] is None
    assert [a["username"] for a in await store.list_demo_accounts()] == ["Ana.Garcia"]
    with pytest.raises(asyncpg.UniqueViolationError):  # another customer cannot take the same user name
        await store.upsert_credentials("C2", "ana.garcia", "hash2")


@pytest.mark.anyio
async def test_migration_0004_unwraps_handoffs_that_were_stored_as_text(database, tmp_path):
    """The shape the old escalate_dispute wrote to production: JSON text inside the jsonb value."""
    old = tmp_path / "old"
    old.mkdir()
    for path in sorted(MIGRATIONS_DIR.glob("*.sql"))[:3]:
        shutil.copy(path, old / path.name)
    conn = await asyncpg.connect(**connection_args(database))
    await apply_migrations(conn, old)
    case_id = await conn.fetchval(
        """insert into app.disputes (customer_id, transaction_id, reason_code, summary, status, evidence)
           values ('C1', 'T1', 'x', 's', 'escalated', jsonb_build_object('handoff', to_jsonb('{"request": "human"}'::text), 'k', 1))
           returning case_id"""
    )
    await conn.execute(
        "insert into app.dispute_events (case_id, event, payload) values ($1, 'escalated', to_jsonb('{\"request\": \"human\"}'::text))",
        case_id,
    )
    await conn.execute("insert into app.dispute_events (case_id, event, payload) values ($1, 'created', '{\"reason_code\": \"x\"}')", case_id)

    assert await apply_migrations(conn) == ["0004_repair_double_encoded_json", "0005_admin_console"]

    evidence = await conn.fetchval("select evidence::text from app.disputes")
    assert '"handoff": {"request": "human"}' in evidence and '"k": 1' in evidence
    payloads = [r["p"] for r in await conn.fetch("select payload::text as p from app.dispute_events order by id")]
    assert payloads == ['{"request": "human"}', '{"reason_code": "x"}']
    await conn.close()


@pytest.mark.anyio
async def test_the_app_boots_migrates_seeds_the_demo_accounts_and_serves_the_login(database, monkeypatch):
    """The startup path production runs: lifespan -> migrations -> demo accounts -> a real sign-in."""
    from fastapi.testclient import TestClient

    from app import demo
    from app.main import create_app

    async def seed_gold():
        conn = await asyncpg.connect(**connection_args(database))
        await conn.execute("insert into gold.customers values ('CLI-X1', 'D1', 'María José', 'Núñez', 'Colombia')")
        await conn.execute("insert into gold.products values ('P1','CLI-X1','Cuenta Ahorro','1111222233334444','COP',2500.50,null,null,'2020-01-01','Active',null,'2026-06-01 13:45:00')")
        await conn.execute("insert into gold.transactions values ('T1','2026-06-01 13:45:00','2026-06-01','P1','CLI-X1','Purchase','Retail',49.90,'COP',null,'POS',null,'Tienda','Retail','Colombia','Bogotá','Declined','51')")
        await conn.close()

    await seed_gold()
    args = connection_args(database)
    for name, value in (("PG_HOST", args["host"]), ("PG_PORT", str(args["port"])), ("PG_USER", args["user"]),
                        ("PG_PASSWORD", args["password"]), ("PG_DATABASE", database),
                        ("DEMO_ACCOUNTS_ENABLED", "true"), ("DEMO_PASSWORD", "Demo-2026")):
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(demo, "DEMO_CUSTOMERS", [("CLI-X1", "Se resuelve solo", "hint")])

    with TestClient(create_app()) as client:  # the `with` runs the lifespan: migrations and seeding
        assert client.get("/ready").json()["status"] == "ready"
        accounts = client.get("/v1/auth/demo-accounts").json()
        assert accounts["password"] == "Demo-2026"
        assert [a["username"] for a in accounts["accounts"]] == ["mariajose.nunez"]

        login = client.post("/v1/auth/login", json={"username": "mariajose.nunez", "password": "Demo-2026"})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['session_token']}"}
        assert client.post("/v1/auth/login", json={"username": "mariajose.nunez", "password": "wrong"}).status_code == 401

        products = client.get("/v1/me/products", headers=headers).json()
        assert products[0]["product_number_masked"] == "****4444"
        assert products[0]["last_transaction_date"].startswith("2026-06-01T13:45")
        assert client.get("/v1/me/summary", headers=headers).json()["balances"][0]["total"] == 2500.5
        page = client.get("/v1/me/transactions", headers=headers).json()
        assert [t["transaction_id"] for t in page["items"]] == ["T1"]

        created = client.post("/v1/disputes", json={"transaction_id": "T1", "reason_code": "x", "summary": "s"}, headers=headers)
        assert created.status_code == 201
        again = client.post("/v1/disputes", json={"transaction_id": "T1", "reason_code": "x", "summary": "s"}, headers=headers)
        assert again.status_code == 201 and again.json()["case_id"] == created.json()["case_id"]
        case_id = created.json()["case_id"]
        resolved = client.post(f"/v1/disputes/{case_id}/resolve", json={"resolution": "no_charge_confirmed"}, headers=headers).json()
        assert resolved["status"] == "auto_resolved"
        assert [c["status"] for c in client.get("/v1/disputes", headers=headers).json()] == ["auto_resolved"]
        assert client.get(f"/v1/disputes/{case_id}", headers=headers).json()["events"][-1]["event"] == "auto_resolved"


@pytest.mark.anyio
async def test_transactions_carry_the_meaning_of_their_response_code_in_sql(store):
    await add_customer(store)
    await add_tx(store, "T1")  # the helper writes response code 51
    expected = {"es": "fondos insuficientes", "pt": "saldo insuficiente"}
    assert (await store.get_transaction("C1", "T1"))["response_meaning"] == expected
    assert (await store.list_transactions("C1"))[0]["response_meaning"] == expected
    assert (await store.list_transactions_page("C1"))[0][0]["response_meaning"] == expected


# ------------------------------------------------------------------ the specialist console's SQL, on a real database
# Its routes and logic are tested in memory (test_admin.py); these run its queries, which a fake cannot check.


@pytest.mark.anyio
async def test_admin_inbox_detail_transitions_and_metrics_in_sql(store):
    await add_customer(store)
    await add_tx(store, "T1")
    await add_tx(store, "T2", when=datetime(2026, 7, 2, 10, 0))
    escalated = await store.create_dispute("C1", "T1", "x", "over the threshold", {"transaction": {}})
    await store.escalate_dispute("C1", str(escalated["case_id"]), {"reason": "amount_threshold", "customer_language": "es", "conversation_id": "conv-1"})
    resolved = await store.create_dispute("C1", "T2", "x", "declined", {})
    await store.resolve_dispute("C1", str(resolved["case_id"]), "no_charge_confirmed")
    unlinked = await store.create_dispute("C1", None, "x", "no transaction identified", {})
    await store.escalate_dispute("C1", str(unlinked["case_id"]), {"reason": "fraud_suspected", "customer_language": "pt"})

    inbox = await store.admin_list_disputes("active")
    assert {row["status"] for row in inbox} == {"escalated"} and len(inbox) == 2
    assert {row["handoff_reason"] for row in inbox} == {"amount_threshold", "fraud_suspected"}
    assert all(row["first_name"] == "Ana" for row in inbox)  # the customer's name comes from gold
    assert await store.admin_count_disputes("active") == 2
    assert await store.admin_count_disputes("auto_resolved") == 1
    assert await store.admin_count_disputes(None, customer_id="OTHER") == 0
    page = await store.admin_list_disputes(None, limit=1, offset=1)
    assert len(page) == 1

    detail = await store.admin_get_dispute(str(escalated["case_id"]))
    assert detail["status"] == "escalated" and detail["evidence"]["handoff"]["reason"] == "amount_threshold"
    assert await store.admin_get_dispute("00000000-0000-0000-0000-000000000000") is None

    claimed = await store.admin_transition(str(escalated["case_id"]), "in_progress", ("open", "escalated"), "claimed", {"by": "ops", "note": "mine"})
    assert claimed["status"] == "in_progress"
    assert await store.admin_transition(str(escalated["case_id"]), "in_progress", ("open", "escalated"), "claimed", {}) is None  # no longer in a state it can be claimed from
    assert await store.admin_count_disputes("active") == 2  # in_progress still counts as active
    closed = await store.admin_transition(str(escalated["case_id"]), "closed", ("in_progress",), "closed", {"note": "done", "resolution": "resolved_customer"})
    assert closed["status"] == "closed" and closed["resolved_at"] is not None
    assert await store.admin_count_disputes("active") == 1

    metrics = await store.admin_metrics()
    assert metrics["total_cases"] == 3
    assert metrics["by_status"]["auto_resolved"] == 1 and metrics["by_status"]["closed"] == 1 and metrics["by_status"]["escalated"] == 1
    assert metrics["safe_automated_resolution"]["resolved"] == 1
    assert (await store.admin_metrics(window_hours=1))["total_cases"] == 3  # created just now


@pytest.mark.anyio
async def test_admin_metrics_without_cases_have_no_rate_instead_of_a_division_by_zero(store):
    metrics = await store.admin_metrics()
    assert metrics["total_cases"] == 0
    assert metrics["safe_automated_resolution"]["rate_percent"] is None


@pytest.mark.anyio
async def test_data_freshness_and_demo_scenarios_in_sql(store):
    await add_customer(store)
    await add_tx(store, "T1", status="Declined", amount=256)
    await put(store, "create schema ops")
    await put(store, "create table ops.etl_runs (run_id text primary key, started_at timestamptz, finished_at timestamptz, status text, detail text)")
    await put(store, "insert into ops.etl_runs values ('r1', '2026-10-01 10:00+00', '2026-10-01 10:20+00', 'success', '{}')")
    fresh = await store.data_freshness()
    assert fresh["gold"]["customers"] == 1 and fresh["gold"]["transactions"] == 1
    assert fresh["last_etl_run"]["run_id"] == "r1"
    assert isinstance(await store.demo_scenarios(), list)


@pytest.mark.anyio
async def test_the_days_filter_runs_in_sql_and_counts_back_from_the_snapshots_edge(store):
    """It never ran against a real database before: every call with a number of days was a 500."""
    await add_customer(store)
    await add_tx(store, "T-NEW", when=datetime(2026, 7, 1, 10, 0))
    await add_tx(store, "T-MID", when=datetime(2026, 6, 28, 10, 0))
    await add_tx(store, "T-OLD", when=datetime(2026, 5, 1, 10, 0))
    ids = lambda rows: [r["transaction_id"] for r in rows]
    assert ids(await store.list_transactions("C1", days=2)) == ["T-NEW"]
    assert ids(await store.list_transactions("C1", days=5)) == ["T-NEW", "T-MID"]
    assert ids(await store.list_transactions("C1", days=90)) == ["T-NEW", "T-MID", "T-OLD"]
    assert ids(await store.list_transactions("C1", days=5, status="Declined", merchant="Tienda")) == ["T-NEW", "T-MID"]
