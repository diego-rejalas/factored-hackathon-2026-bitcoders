from app.response_codes import RESPONSE_CODES, explain, meanings


def test_the_codes_the_dataset_carries_are_explained():
    assert explain("51") == "fondos insuficientes"
    assert explain("54") == "la tarjeta está vencida"
    assert explain("51", "pt") == "saldo insuficiente"
    assert set(RESPONSE_CODES) >= {"00", "05", "14", "51", "54"}


def test_an_empty_or_unknown_code_gets_no_explanation_rather_than_a_guess():
    assert explain(None) is None
    assert explain("") is None
    assert explain("99") is None
    assert explain("  51 ") == "fondos insuficientes"  # stray spaces do not hide a real code


def test_a_transaction_carries_the_meaning_of_its_code(client, auth_headers):
    declined = client.get("/v1/me/transactions/TXN-A2", headers=auth_headers).json()  # response_code "51"
    assert declined["response_code"] == "51"
    assert declined["response_meaning"] == {"es": "fondos insuficientes", "pt": "saldo insuficiente"}
    listing = client.get("/v1/me/transactions", headers=auth_headers).json()["items"]
    assert all("response_meaning" in t for t in listing)


def test_the_legacy_routes_the_agent_uses_carry_it_too(client, auth_headers):
    assert client.get("/me/transactions/TXN-A2", headers=auth_headers).json()["response_meaning"]["es"] == "fondos insuficientes"
    assert all("response_meaning" in t for t in client.get("/me/transactions", headers=auth_headers).json())


def test_meanings_come_in_both_languages_or_not_at_all():
    assert meanings("54") == {"es": "la tarjeta está vencida", "pt": "o cartão está vencido"}
    assert meanings("") is None and meanings(None) is None and meanings("77") is None
