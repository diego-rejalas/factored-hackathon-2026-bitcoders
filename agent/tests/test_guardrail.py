import pytest

from app import guardrail
from tests.fakes import _tx


def test_fraud_keywords_es_with_accents():
    assert guardrail.mentions_fraud("Me clonaron la tarjeta, ¡fue un FRAUDE!")
    assert guardrail.mentions_fraud("no fui yo, me robaron")


def test_fraud_keywords_pt():
    assert guardrail.mentions_fraud("Não fui eu, foi roubo na minha conta")
    assert guardrail.mentions_fraud("isso é golpe")


def test_normal_dispute_is_not_fraud():
    assert not guardrail.mentions_fraud("Me hicieron un cobro que no reconozco")


@pytest.mark.parametrize(
    "effective,expected",
    [(500.00, True), (499.99, False), (500.01, True), (0, False)],
)
def test_threshold_boundary_is_inclusive(effective, expected):
    tx = _tx("TXN-X", "CUS-1", "M", "Declined", effective)
    assert guardrail.exceeds_threshold(tx) is expected


def test_threshold_reads_env(monkeypatch):
    monkeypatch.setenv("GUARDRAIL_MAX_USD", "40")
    tx = _tx("TXN-X", "CUS-1", "M", "Declined", 45.50)
    assert guardrail.exceeds_threshold(tx) is True


def test_extract_entities_amount_and_days():
    entities = guardrail.extract_entities("fue hace 3 días, por 49.90")
    assert entities["amount"] == 49.90
    assert entities["days"] == 3


def test_parse_number_handles_locale_formats():
    assert guardrail.parse_number("1.234,56") == 1234.56
    assert guardrail.parse_number("1,234.56") == 1234.56
    assert guardrail.parse_number("45.50") == 45.50
    assert guardrail.parse_number("1200") == 1200.0


def test_narrow_candidates_by_merchant_keeps_order():
    a = _tx("TXN-1", "C", "Tienda Don Pepe", "Declined", 45.50, date="2026-06-10")
    b = _tx("TXN-2", "C", "Farmacia Central", "Declined", 120.00, date="2026-06-09")
    narrowed = guardrail.narrow_candidates([a, b], "el cobro de Farmacia Central", {})
    assert narrowed == [b]


def test_narrow_candidates_by_amount():
    a = _tx("TXN-1", "C", "Tienda Don Pepe", "Declined", 45.50)
    b = _tx("TXN-2", "C", "Tienda Don Pepe", "Declined", 120.00)
    narrowed = guardrail.narrow_candidates([a, b], "cobro de 120 en Tienda Don Pepe", {"amount": 120.0})
    assert narrowed == [b]


def test_narrow_candidates_keeps_all_when_no_signal():
    a = _tx("TXN-1", "C", "Tienda Don Pepe", "Declined", 45.50)
    b = _tx("TXN-2", "C", "Farmacia", "Declined", 120.00)
    assert guardrail.narrow_candidates([a, b], "me cobraron", {}) == [a, b]


def test_guardrail_intent_override_on_fraud():
    assert guardrail.guardrail_intent("no fui yo", "dispute") == "fraud_report"
    assert guardrail.guardrail_intent("hola", "greeting") == "greeting"


def test_unknown_amount_is_not_known_and_never_zero():
    tx = _tx("TXN-X", "CUS-1", "M", "Declined", 100.0)
    tx["amount_usd_effective"] = None
    assert guardrail.amount_known(tx) is False
    assert guardrail.amount_known(_tx("TXN-Y", "CUS-1", "M", "Declined", 0)) is True


def test_corroboration_needs_merchant_or_amount_not_just_a_window():
    tx = _tx("TXN-1", "C", "Tienda Don Pepe", "Declined", 45.50)
    assert guardrail.is_corroborated(tx, "cobro en Tienda Don Pepe", {})
    assert guardrail.is_corroborated(tx, "me cobraron 45.50", {"amount": 45.50})
    assert not guardrail.is_corroborated(tx, "hace 3 días me cobraron algo", {"days": 3})
    assert not guardrail.is_corroborated(tx, "me cobraron algo", {})


@pytest.mark.parametrize("text", ["sí", "Si, esa", "esa es", "sim", "isso mesmo", "Correcto!"])
def test_affirmations_are_recognized(text):
    assert guardrail.is_affirmation(text)


@pytest.mark.parametrize("text", ["no", "no fue esa", "cobro de 45 en otro lugar", "", "me cobraron algo que no reconozco ayer"])
def test_non_affirmations_are_rejected(text):
    assert not guardrail.is_affirmation(text)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("la transferencia de 4189.18 dólares", 4189.18),
        ("un cobro de 1200", 1200.0),
        ("pagué 6783.64", 6783.64),
        ("fueron 4,189.18", 4189.18),
        ("fueron 4.189,18", 4189.18),
        ("de 999999 pesos", 999999.0),
        ("cobro de 45.50", 45.50),
        ("cobro de 120", 120.0),
    ],
)
def test_amounts_are_not_truncated(text, expected):
    assert guardrail.extract_entities(text)["amount"] == expected


def test_dates_and_days_are_not_amounts():
    assert "amount" not in guardrail.extract_entities("fue el 2026-05-11")
    assert "amount" not in guardrail.extract_entities("fue el 11/05/2026")
    assert "amount" not in guardrail.extract_entities("fue hace 3 días")
    assert guardrail.extract_entities("fue el 2026-05-11 por 4189.18")["amount"] == 4189.18


def test_an_exact_amount_beats_an_approximate_one():
    near = _tx("TXN-1", "C", None, "Approved", 6736.04, date="2023-10-30T10:00:00")
    exact = _tx("TXN-2", "C", None, "Approved", 6783.64, date="2026-05-09T10:00:00")
    assert guardrail.narrow_candidates([near, exact], "cobro de 6783.64", {"amount": 6783.64}) == [exact]


def test_an_approximate_amount_still_matches_when_nothing_is_exact():
    a = _tx("TXN-1", "C", None, "Declined", 120.00)
    assert guardrail.narrow_candidates([a], "cobro de unos 119", {"amount": 119.0}) == [a]


# --- found by the held-out evaluation (docs/EVALUATION.md) ----------------------------------------------------

from app.guardrail import extract_entities, mentions_fraud  # noqa: E402


def test_a_written_date_is_not_read_as_the_amount():
    # The year used to win: "2026" was taken for the amount and the real one ignored.
    assert extract_entities("No dia 10 de junho de 2026, apareceu um valor de 27.65 USD que não entendo.")["amount"] == 27.65
    assert extract_entities("El 1 de mayo de 2026, hay un cargo de 107.27 USD de 'Café del Parque'")["amount"] == 107.27
    assert extract_entities("No dia 1º de maio de 2026 houve uma cobrança de 107,27")["amount"] == 107.27
    assert extract_entities("En junio de 2026 vi un cargo de 84.20")["amount"] == 84.20
    assert extract_entities("El 15 de junio vi un cargo de 84.20")["amount"] == 84.20


def test_a_real_amount_that_looks_like_a_year_is_still_an_amount():
    assert extract_entities("No reconozco el cobro de 2026")["amount"] == 2026.0
    assert extract_entities("Me cobraron 2514.48 USD")["amount"] == 2514.48


def test_fraud_described_without_the_obvious_words_is_still_fraud():
    for message in [
        "Alguien usó mi tarjeta sin mi permiso",
        "Alguém usou meu cartão sem minha autorização",
        "Me hackearon la cuenta, hay movimientos que no son míos",
        "Invadiram minha conta, tem movimentos que não são meus",
        "Perdí mi cartera y ya hay cargos raros",
        "Perdi minha carteira no ônibus",
        "Alguien entró a mi cuenta y cambió mi contraseña",
    ]:
        assert mentions_fraud(message), message


def test_an_ordinary_dispute_is_not_taken_for_fraud():
    for message in [
        "No reconozco el cobro de 256.10",
        "Não reconheço a cobrança de 389.87",
        "Me cobraron dos veces la misma compra",
        "Mi compra fue rechazada pero el dinero salió de mi cuenta",
    ]:
        assert not mentions_fraud(message), message
