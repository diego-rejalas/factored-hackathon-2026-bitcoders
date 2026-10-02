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
