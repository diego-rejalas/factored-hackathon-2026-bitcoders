"""Componente A integrado: clasificador con confianza y abstención.

Sin LLM real: FakeLLM responde classify_detailed determinista y chat None,
así la redacción queda en las plantillas deterministas (mismo patrón que
los fakes de test_graph.py).
"""

import pytest
from app.graph import build_graph
from app.intents import baseline_language, classify_detailed
from app.llm import LLM
from app.tracing import NullTracer
from tests.fakes import CUS_A, FakeBankTools, _tx


class FakeLLM:
    """LLM estructurado de mentira: clasifica igual siempre, no redacta."""

    def __init__(self, intent="dispute", language="es", confidence=0.95):
        self.enabled = True
        self.intent = intent
        self.language = language
        self.confidence = confidence
        self.calls = 0

    async def classify_detailed(self, message):
        self.calls += 1
        return {
            "intent": self.intent, "language": self.language,
            "confidence": self.confidence, "model": "fake-model",
            "prompt_version": "v1-test", "usage": {}, "latency_ms": 1,
        }

    async def chat(self, user_prompt, system=None):
        return None


class CaptureTracer(NullTracer):
    def __init__(self):
        super().__init__()
        self.rows = []

    async def log(
        self, run_id, conversation_id, node, intent=None, tool=None,
        params=None, result_status=None, latency_ms=None,
    ):
        self.rows.append({
            "node": node,
            "params": params or {},
            "latency_ms": latency_ms,
        })


@pytest.fixture()
def tools():
    return FakeBankTools()


def _graph(tools, llm):
    return build_graph(tools, NullTracer(), llm)


def _run(graph, message, conversation="conv-intents", token=f"token-{CUS_A}"):
    import asyncio
    import uuid

    return asyncio.run(
        graph.ainvoke(
            {
                "session_token": token,
                "message": message,
                "conversation_id": conversation,
                "run_id": str(uuid.uuid4()),
            },
            config={"configurable": {"thread_id": conversation}},
        )
    )


# --- abstención ------------------------------------------------------------------


def test_low_confidence_abstains_and_escalates(tools):
    llm = FakeLLM(intent="dispute", language="es", confidence=0.30)
    result = _run(_graph(tools, llm), "Me hicieron un cobro que no reconozco")

    assert result["outcome"] == "escalated"
    assert result["reason"] == "intent_low_confidence"
    assert result["intent_abstain"] is True
    assert result["intent_source"] == "llm:fake-model"
    assert result["intent_confidence"] == 0.30
    # la abstención abre caso y lo escala a la bandeja humana
    assert result["case"]["status"] == "escalated"
    assert tools.calls_of("create_dispute")
    assert tools.calls_of("list_transactions") == []
    limitation = result["handoff"]["limitation"]
    assert "INTENT_MIN_CONFIDENCE" in limitation


def test_high_confidence_keeps_the_normal_path(tools):
    llm = FakeLLM(intent="dispute", language="es", confidence=0.95)
    result = _run(
        _graph(tools, llm),
        "Me hicieron un cobro que no reconozco de 45.50 en Tienda Don Pepe",
    )
    assert result["outcome"] == "resolved"
    assert result["case"]["status"] == "auto_resolved"
    assert result["intent_abstain"] is False


def test_affirmation_overrides_abstention(tools):
    tools.transactions = [_tx("TXN-2", CUS_A, "Farmacia Central", "Declined", 120.00)]
    llm = FakeLLM(intent="dispute", language="es", confidence=0.95)
    graph = _graph(tools, llm)
    conversation = "conv-abstain-affirm"

    first = _run(graph, "Me hicieron un cobro que no reconozco", conversation=conversation)
    assert first["outcome"] == "clarify"
    assert first["reason"] == "unconfirmed_candidate"

    llm.confidence = 0.20  # el "sí" de dos palabras no inspira confianza a nadie
    second = _run(graph, "sí", conversation=conversation)
    assert second["outcome"] == "resolved"
    assert second["case"]["transaction_id"] == "TXN-2"


# --- invariantes -------------------------------------------------------------------


def test_fraud_override_beats_a_confident_classifier(tools):
    llm = FakeLLM(intent="dispute", language="es", confidence=0.99)
    result = _run(_graph(tools, llm), "me robaron la tarjeta, hay un cobro raro")

    assert result["outcome"] == "escalated"
    assert result["reason"] == "fraud_suspected"
    assert result["intent"] == "fraud_report"


def test_deterministic_policy_untouched_when_classifier_is_uncertain_about_amount(tools):
    llm = FakeLLM(intent="dispute", language="es", confidence=0.95)
    tools.transactions = [_tx("TXN-BIG", CUS_A, "Electro Mega", "Declined", 600.00)]
    result = _run(_graph(tools, llm), "hay un cobro de 600 en Electro Mega que no reconozco")
    assert result["handoff"]["reason"] == "amount_threshold"


def test_out_of_scope_is_declined_with_classifier_confident(tools):
    # Declined, not escalated: no case or handoff exists, so saying a person has it would be false
    # (docs/EVALUATION.md, defect 5). A low-confidence classifier still escalates (tests above).
    llm = FakeLLM(intent="out_of_scope", language="es", confidence=0.95)
    result = _run(_graph(tools, llm), "quiero un préstamo personal nuevo")
    assert result["outcome"] == "declined"
    assert result["reason"] == "out_of_scope"
    assert not result.get("handoff")


# --- fallback sin clave ---------------------------------------------------------------


def test_fallback_without_api_key_matches_production_baseline(tools):
    llm = LLM(api_key=None)
    assert not llm.enabled

    result = _run(
        _graph(tools, llm),
        "Me hicieron un cobro que no reconozco de 45.50 en Tienda Don Pepe",
    )
    assert result["outcome"] == "resolved"
    assert result["intent_source"] == "baseline"
    assert result["intent_confidence"] is None
    assert result["intent_abstain"] is False


def test_baseline_source_never_abstains():
    import asyncio

    result = asyncio.run(classify_detailed("hola", llm=None))
    assert result["source"] == "baseline"
    assert result["abstain"] is False


# --- idioma ------------------------------------------------------------------------


def test_language_comes_from_the_classifier_with_substring_fallback():
    import asyncio

    llm = FakeLLM(intent="dispute", language="pt", confidence=0.9)
    result = asyncio.run(classify_detailed("não reconheço uma cobrança", llm=llm))
    assert result["language"] == "pt"

    fallback = asyncio.run(classify_detailed("não reconheço uma cobrança", llm=None))
    assert fallback["language"] == "pt"  # substring de producción
    assert baseline_language("buenas tardes") == "es"


def test_portuguese_reply_with_classifier_language(tools):
    llm = FakeLLM(intent="dispute", language="pt", confidence=0.95)
    result = _run(
        _graph(tools, llm),
        "Não reconheço uma cobrança de 45.50 na Tienda Don Pepe",
    )
    assert result["language"] == "pt"
    assert result["outcome"] == "resolved"
    assert "Verifiquei" in result["reply"]


def test_understand_trace_records_prompt_version_and_classifier_latency(tools):
    tracer = CaptureTracer()
    llm = FakeLLM(intent="greeting", confidence=0.95)
    graph = build_graph(tools, tracer, llm)

    _run(graph, "Hola", conversation="conv-classifier-trace")

    row = next(row for row in tracer.rows if row["node"] == "understand")
    assert row["params"]["intent_prompt_version"] == "v1-test"
    classifier_latency = row["params"]["classifier_latency_ms"]
    assert isinstance(classifier_latency, int)
    assert classifier_latency >= 0
    assert row["latency_ms"] is not None  # conserva latencia total del nodo
