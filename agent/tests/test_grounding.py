import asyncio
import uuid

import pytest

from app import grounding
from app.graph import build_graph
from app.tracing import NullTracer
from tests.fakes import CUS_A, FakeBankTools, _tx

CASE = "53cd8bb2-545c-4ba9-a1c2-0412516e99a1"
FACTS = [
    "transacción TXN-1 (Tienda Don Pepe) estado Declined",
    "monto efectivo 256.10 USD",
    f"caso {CASE} verificado en estado auto_resolved",
    "Motivo informado por el estándar de tarjetas (código 51): fondos insuficientes.",
]
MESSAGE = "No reconozco el cobro de 256.10"


def verdict(draft):
    return grounding.check(draft, FACTS, MESSAGE, CASE)


# ------------------------------------------------------------------ the rules


def test_a_draft_that_only_says_what_was_verified_passes():
    draft = f"Tu cobro de 256.10 USD en Tienda Don Pepe fue rechazado (código 51): fondos insuficientes. Caso {CASE}."
    assert verdict(draft) is None


def test_a_decimal_comma_is_the_same_number():
    assert verdict("El cobro de 256,10 USD fue rechazado.") is None  # Portuguese writes it so


@pytest.mark.parametrize(
    "draft",
    [
        "Desaparecerá en las próximas 24-48 horas.",
        "Se reflejará en unos días.",
        "Lo revisaremos en una semana.",
        "Will be gone in 2 days.",
        "Te reembolsaremos el importe.",
        "Vamos a estornar o valor.",
        "Te devolveremos el dinero.",
    ],
)
def test_a_promise_of_time_or_money_is_rejected(draft):
    assert verdict(draft) == "promise"


def test_a_number_nobody_verified_is_rejected():
    assert verdict("El cobro fue de 300 USD y está rechazado.") == "ungrounded_number"
    assert verdict("Son 256.10 USD, y el límite es 5000.") == "ungrounded_number"


def test_numbers_that_are_in_the_message_or_the_facts_are_fine():
    assert verdict("El 51 es el código y 256.10 el monto.") is None


def test_the_case_number_does_not_count_as_a_number_to_verify():
    assert numbers_of(f"caso {CASE}") == set()


def numbers_of(text):
    return grounding.numbers(text)


def test_numbers_normalize_decimals_and_thousands():
    assert numbers_of("256,10 y 256.10") == {"256.1"}
    assert numbers_of("1,200.50") == {"1200.5"}
    assert numbers_of("1.000") == {"1.000".rstrip("0").rstrip(".")}  # a point decimal reads as a decimal


def test_a_customer_id_or_a_document_number_is_never_repeated():
    assert verdict("Hola CLI-0064RNKCVQCN, tu cobro fue rechazado.") == "identity"
    assert verdict("Tu documento 0863503738 coincide.") == "identity"


def test_a_long_draft_is_rejected():
    assert verdict("x" * 901) == "too_long"


def test_the_case_number_is_added_when_the_model_left_it_out():
    assert CASE in grounding.with_case_id("Tu cobro fue rechazado.", CASE, "es")
    assert grounding.with_case_id(f"Caso {CASE}.", CASE, "es") == f"Caso {CASE}."  # not twice
    assert grounding.with_case_id("Texto.", None, "es") == "Texto."


# ------------------------------------------------------------------ where the model is used


class FakeLLM:
    enabled = True

    def __init__(self, draft):
        self.draft = draft
        self.prompts = []

    async def chat(self, prompt, system=None):
        self.prompts.append(prompt)
        return self.draft

    async def classify_intent(self, message):
        return None  # the keyword baseline decides

    async def flags_fraud(self, message):
        return False


def run(graph, message, token=f"token-{CUS_A}"):
    return asyncio.run(
        graph.ainvoke(
            {"session_token": token, "message": message, "conversation_id": "conv-" + uuid.uuid4().hex, "run_id": uuid.uuid4().hex},
            config={"configurable": {"thread_id": "t-" + uuid.uuid4().hex}},
        )
    )


@pytest.fixture()
def tools():
    return FakeBankTools()


def make(tools, draft):
    llm = FakeLLM(draft)
    return build_graph(tools, NullTracer(), llm), llm


def test_a_resolved_case_is_phrased_by_the_model_and_keeps_its_case_number(tools):
    graph, llm = make(tools, "Revisé tu cobro de 45.50 USD en Tienda Don Pepe: fue rechazado y no salió dinero.")
    result = run(graph, "Me hicieron un cobro que no reconozco de 45.50 en Tienda Don Pepe")
    assert result["outcome"] == "resolved" and len(llm.prompts) == 1
    assert result["reply"].startswith("Revisé tu cobro de 45.50 USD")
    assert result["case"]["case_id"] in result["reply"]  # added: the draft left it out


def test_a_draft_with_a_promise_is_replaced_by_the_fixed_text(tools):
    graph, llm = make(tools, "Rechazado. Desaparecerá en 24-48 horas de tu estado de cuenta.")
    result = run(graph, "Me hicieron un cobro que no reconozco de 45.50 en Tienda Don Pepe")
    assert len(llm.prompts) == 1  # it was asked
    assert "24-48" not in result["reply"] and "horas" not in result["reply"]
    assert "Registré el caso" in result["reply"]  # the template


def test_a_model_that_does_not_answer_leaves_the_fixed_text(tools):
    graph, llm = make(tools, None)
    result = run(graph, "Me hicieron un cobro que no reconozco de 45.50 en Tienda Don Pepe")
    assert "Registré el caso" in result["reply"]


def test_an_escalation_is_never_phrased_by_the_model(tools):
    """Without facts the model improvised: it told the customer to contact the fraud team when the case had already
    been escalated to a person. The escalation text carries the case number and what happens next."""
    tools.transactions.append(_tx("TXN-BIG", CUS_A, "Electro Mega", "Declined", 600.00))
    graph, llm = make(tools, "Contacta directamente con nuestro equipo de fraude.")
    result = run(graph, "hay un cobro de 600 en Electro Mega que no reconozco")
    assert result["outcome"] == "escalated"
    assert llm.prompts == []  # the model was not even asked
    assert result["case"]["case_id"] in result["reply"]
    assert "equipo de fraude" not in result["reply"]


@pytest.mark.parametrize("message", ["hola", "Me hicieron un cobro que no reconozco", "quiero un préstamo personal nuevo"])
def test_greetings_questions_and_out_of_scope_keep_their_fixed_text(tools, message):
    graph, llm = make(tools, "texto del modelo")
    result = run(graph, message)
    assert llm.prompts == [] and result["reply"] != "texto del modelo"


# --- the semantic fraud signal (docs/EVALUATION.md): fraud the keyword list does not hold ---------------------


class FraudLLM(FakeLLM):
    def __init__(self, verdict):
        super().__init__("never used")
        self.verdict = verdict

    async def flags_fraud(self, message):
        return self.verdict

    async def classify_intent(self, message):
        return "dispute"


NO_KEYWORD_FRAUD = "Fui roubada no ônibus e já tem compras que não reconheço"  # no word from the fraud list


def test_fraud_the_word_list_misses_is_handed_to_a_person_when_the_model_sees_it(tools):
    graph, _ = make(tools, "x")
    graph = build_graph(tools, NullTracer(), FraudLLM(True))
    result = run(graph, NO_KEYWORD_FRAUD)
    assert result["outcome"] == "escalated" and result["reason"] == "fraud_suspected"


def test_the_signal_only_adds_caution_a_no_or_a_failure_leaves_the_rule_as_it_was(tools):
    for verdict in (False, None):
        graph = build_graph(tools, NullTracer(), FraudLLM(verdict))
        result = run(graph, "Me hicieron un cobro que no reconozco de 45.50 en Tienda Don Pepe")
        assert result["outcome"] == "resolved", verdict  # an ordinary dispute still resolves


def test_without_a_model_nothing_changes(tools):
    graph = build_graph(tools, NullTracer(), None)
    assert run(graph, "Me hicieron un cobro que no reconozco de 45.50 en Tienda Don Pepe")["outcome"] == "resolved"


def test_a_security_matter_the_classifier_calls_out_of_scope_still_reaches_a_person_when_the_model_sees_fraud(tools):
    class OutOfScopeFraud(FraudLLM):
        async def classify_intent(self, message):
            return "out_of_scope"

    graph = build_graph(tools, NullTracer(), OutOfScopeFraud(True))
    result = run(graph, "Oi, minha senha foi vazada! Preciso trocar agora.")
    assert result["outcome"] == "escalated" and result["reason"] == "fraud_suspected"
    graph = build_graph(tools, NullTracer(), OutOfScopeFraud(False))
    assert run(graph, "Quero aumentar o limite do cartão")["outcome"] == "declined"
