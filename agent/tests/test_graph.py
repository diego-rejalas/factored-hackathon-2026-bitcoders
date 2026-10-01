import pytest

from app.graph import build_graph
from app.llm import LLM
from app.tracing import NullTracer
from tests.fakes import CUS_A, FakeBankTools, _tx


@pytest.fixture()
def tools():
    return FakeBankTools()


@pytest.fixture()
def graph(tools):
    return build_graph(tools, NullTracer(), LLM(api_key=None))


def _run(graph, message, conversation="conv-test", token=f"token-{CUS_A}"):
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


def test_normal_dispute_auto_resolves_with_verification(graph, tools):
    result = _run(graph, "Me hicieron un cobro que no reconozco de 45.50 en Tienda Don Pepe")

    assert result["outcome"] == "resolved"
    assert result["case"]["status"] == "open"
    assert result.get("handoff") is None
    # verify must re-consult the case after create_dispute (does not trust the LLM)
    methods = [c[0] for c in tools.calls]
    assert methods.index("create_dispute") < methods.index("get_dispute")
    assert str(result["case"]["case_id"]) in result["reply"]
    assert "rechazada" in result["reply"]
    assert result["facts"]


def test_ambiguous_dispute_asks_before_assuming(graph, tools):
    result = _run(graph, "Me hicieron un cobro que no reconozco en Tienda Don Pepe")
    assert result["outcome"] == "clarify"
    assert tools.calls_of("create_dispute") == []
    assert "Cuál es" in result["reply"] or "cuál" in result["reply"].lower()


def test_ambiguous_then_answer_resolves(graph, tools):
    conversation = "conv-amb"
    first = _run(graph, "Me hicieron un cobro que no reconozco", conversation=conversation)
    assert first["outcome"] == "clarify"

    second = _run(
        graph,
        "fue el cobro de 120 en Farmacia Central",
        conversation=conversation,
    )
    assert second["outcome"] == "resolved"
    assert second["case"]["transaction_id"] == "TXN-2"


def test_two_clarify_rounds_then_escalate(graph, tools):
    conversation = "conv-rounds"
    first = _run(graph, "Me hicieron un cobro que no reconozco", conversation=conversation)
    assert first["outcome"] == "clarify"

    second = _run(graph, "fue un cobro que no reconozco", conversation=conversation)
    assert second["outcome"] == "clarify"

    third = _run(graph, "ya te dije, un cobro", conversation=conversation)
    assert third["outcome"] == "escalated"
    assert third["handoff"]["reason"] == "ambiguity_unresolved"
    assert tools.calls_of("create_dispute") == []


def test_fraud_mention_always_escalates_with_structured_handoff(graph, tools):
    result = _run(graph, "me robaron la tarjeta, no fui yo, hay un cobro raro")

    assert result["outcome"] == "escalated"
    handoff = result["handoff"]
    assert handoff["reason"] == "fraud_suspected"
    for key in ("request", "verified_facts", "actions_taken", "evidence", "open_questions"):
        assert key in handoff
    assert tools.calls_of("create_dispute") == []


def test_amount_above_threshold_escalates_without_creating_case(graph, tools):
    tools.transactions.append(
        _tx("TXN-BIG", CUS_A, "Electro Mega", "Declined", 600.00)
    )
    result = _run(graph, "hay un cobro de 600 en Electro Mega que no reconozco")

    assert result["outcome"] == "escalated"
    assert result["handoff"]["reason"] == "amount_threshold"
    assert tools.calls_of("create_dispute") == []


def test_out_of_scope_escalates(graph, tools):
    result = _run(graph, "quiero un préstamo personal nuevo")
    assert result["outcome"] == "escalated"
    assert result["handoff"]["reason"] == "out_of_scope"


def test_greeting_gets_answer_not_escalation(graph, tools):
    result = _run(graph, "Hola, buenas tardes")
    assert result["outcome"] == "resolved"
    assert result["intent"] == "greeting"
    assert tools.calls == []


def test_case_status_reports_existing_case(graph, tools):
    conversation = "conv-status"
    resolved = _run(
        graph,
        "cobro que no reconozco de 45.50 en Tienda Don Pepe",
        conversation=conversation,
    )
    case_id = resolved["case"]["case_id"]

    status = _run(graph, "¿Qué pasó con mi caso?", conversation=conversation)
    assert status["outcome"] == "resolved"
    assert str(case_id) in status["reply"]
    assert "open" in status["reply"]


def test_portuguese_message_gets_portuguese_reply(graph, tools):
    result = _run(
        graph,
        "Olá, não reconheço uma cobrança de 45.50 na Tienda Don Pepe",
    )
    assert result["language"] == "pt"
    assert result["outcome"] == "resolved"
    assert "Verifiquei" in result["reply"]


def test_agent_never_touches_other_customers_data(graph, tools):
    result = _run(
        graph,
        "cobro que no reconozco de 99 en Mega Mercado",
    )
    # TXN-B1 belongs to CUS-B; CUS-A's token must never see it
    assert result["outcome"] == "clarify"
    assert tools.calls_of("create_dispute") == []
