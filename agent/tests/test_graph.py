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
    # the policy resolved it, and the case says so (it used to stay "open" in the customer's list)
    assert result["case"]["status"] == "auto_resolved"
    assert result.get("handoff") is None
    # verify must re-consult the case after create_dispute (does not trust the LLM), and again after
    # recording the resolution (it does not trust its own write either)
    methods = [c[0] for c in tools.calls]
    assert methods.index("create_dispute") < methods.index("get_dispute") < methods.index("resolve_dispute")
    assert methods[methods.index("resolve_dispute") + 1] == "get_dispute"
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
    assert "auto_resolved" in status["reply"]


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


# --- regressions found in the PR #1 review --------------------------------------------------


def _only(tools, *txs):
    tools.transactions = list(txs)


def test_vague_report_is_not_closed_against_an_unrelated_declined_charge(graph, tools):
    """A vague report must not be closed against an old declined charge while the real
    unrecognized charge is an approved one."""
    _only(
        tools,
        _tx("TXN-2", CUS_A, "Farmacia Central", "Declined", 120.00, date="2026-06-09T10:00:00"),
        _tx("TXN-9", CUS_A, "Casino Royal", "Approved", 980.00, date="2026-06-12T23:10:00"),
    )
    result = _run(graph, "Me hicieron un cobro que no reconozco")

    assert result["outcome"] == "clarify"
    assert tools.calls_of("create_dispute") == []


def test_single_unidentified_candidate_is_proposed_not_assumed(graph, tools):
    _only(tools, _tx("TXN-2", CUS_A, "Farmacia Central", "Declined", 120.00))
    conversation = "conv-propose"

    first = _run(graph, "Me hicieron un cobro que no reconozco", conversation=conversation)
    assert first["outcome"] == "clarify"
    assert first["reason"] == "unconfirmed_candidate"
    assert "Farmacia Central" in first["reply"]
    assert tools.calls_of("create_dispute") == []

    second = _run(graph, "sí, esa", conversation=conversation)
    assert second["outcome"] == "resolved"
    assert second["case"]["transaction_id"] == "TXN-2"


def test_a_yes_without_a_proposal_does_not_resolve_anything(graph, tools):
    _only(tools, _tx("TXN-2", CUS_A, "Farmacia Central", "Declined", 120.00))
    result = _run(graph, "sí")
    assert tools.calls_of("create_dispute") == []
    assert result["outcome"] != "resolved"


def test_unknown_usd_amount_escalates_instead_of_counting_as_zero(graph, tools):
    big = _tx("TXN-5", CUS_A, "Electro Mundo", "Declined", 9_500_000.00)
    big["currency"] = "COP"
    big["amount_usd_effective"] = None
    _only(tools, big)

    result = _run(graph, "Me cobraron lo de Electro Mundo y no lo reconozco")

    assert result["outcome"] == "escalated"
    assert result["handoff"]["reason"] == "amount_unknown"
    assert tools.calls_of("create_dispute") == []


def test_unrecognized_approved_charge_escalates_as_possible_fraud(graph, tools):
    _only(tools, _tx("TXN-7", CUS_A, "Casino Royal", "Approved", 980.00, date="2026-06-12T23:10:00"))

    result = _run(graph, "No reconozco el cobro de 980 en Casino Royal")

    assert result["outcome"] == "escalated"
    assert result["handoff"]["reason"] == "posted_charge_disputed"
    assert tools.calls_of("create_dispute") == []


def test_pending_charge_also_escalates(graph, tools):
    _only(tools, _tx("TXN-8", CUS_A, "Tienda Norte", "Pending", 50.00))
    result = _run(graph, "No reconozco el cobro de 50 en Tienda Norte")
    assert result["outcome"] == "escalated"
    assert result["handoff"]["reason"] == "posted_charge_disputed"


def test_a_four_digit_amount_is_not_read_as_a_smaller_one(graph, tools):
    """'1200' was read as 120 and could close an unrelated 120.00 transaction."""
    _only(
        tools,
        _tx("TXN-SMALL", CUS_A, None, "Declined", 120.00, date="2026-06-02T10:00:00"),
        _tx("TXN-BIG", CUS_A, None, "Declined", 400.00, effective=1200.00, date="2026-06-01T10:00:00"),
    )
    tools.transactions[1]["amount_usd_effective"] = 1200.00
    result = _run(graph, "No reconozco el cobro de 1200")
    # 1200 USD is above the 500 threshold: it must escalate on the RIGHT transaction, not close the 120 one.
    assert result["outcome"] == "escalated"
    assert result["handoff"]["reason"] == "amount_threshold"
    assert tools.calls_of("create_dispute") == []


def test_replies_never_print_none_for_a_missing_merchant(graph, tools):
    _only(
        tools,
        _tx("TXN-A", CUS_A, None, "Declined", 40.00, date="2026-06-02T10:00:00"),
        _tx("TXN-B", CUS_A, None, "Declined", 55.00, date="2026-06-01T10:00:00"),
    )
    result = _run(graph, "Me hicieron un cobro que no reconozco")
    assert "None" not in result["reply"]
    resolved = _run(graph, "No reconozco el cobro de 55")
    assert resolved["outcome"] == "resolved"
    assert "None" not in resolved["reply"]


def test_a_backend_without_resolve_still_answers_the_customer(graph, tools, monkeypatch):
    """An older backend answers 404 to /resolve: the case stays open and the customer gets the same answer."""
    from app.tools import ToolError

    async def no_resolve(token, case_id, resolution):
        raise ToolError(404, "Not Found")

    monkeypatch.setattr(tools, "resolve_dispute", no_resolve)
    result = _run(graph, "Me hicieron un cobro que no reconozco de 45.50 en Tienda Don Pepe")
    assert result["outcome"] == "resolved"
    assert result["case"]["status"] == "open"
    assert str(result["case"]["case_id"]) in result["reply"]
