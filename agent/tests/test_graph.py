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
    assert result["case"]["status"] == "auto_resolved"
    assert result.get("handoff") is None
    # verify must re-consult the case after create_dispute (does not trust the LLM)…
    methods = [c[0] for c in tools.calls]
    assert methods.index("create_dispute") < methods.index("get_dispute")
    # …and close the safe path itself through the guarded resolve endpoint
    assert methods.index("get_dispute") < methods.index("resolve_dispute")
    assert str(result["case"]["case_id"]) in result["reply"]
    assert "rechazada" in result["reply"]
    assert result["facts"]


def test_resolution_failure_escalates_instead_of_reporting_success(graph, tools):
    from app.tools import ToolError

    async def fail_resolve(token, case_id, resolution):
        raise ToolError(409, "case changed state")

    tools.resolve_dispute = fail_resolve
    result = _run(
        graph,
        "Me hicieron un cobro de 45.50 en Tienda Don Pepe",
        conversation="conv-verify-failure",
    )

    assert result["outcome"] == "escalated"
    assert result["reason"] == "verify_failed"
    assert result["handoff"]["reason"] == "verify_failed"


def test_new_case_does_not_reuse_previous_case_or_handoff(graph, tools):
    conversation = "conv-new-case-after-resolution"
    resolved = _run(
        graph,
        "No reconozco el cobro de 45.50",
        conversation=conversation,
    )
    assert resolved["case"]["status"] == "auto_resolved"
    tools.transactions.append(
        _tx("TXN-APPROVED", CUS_A, "Librería Norte", "Approved", 980.00)
    )

    escalated = _run(
        graph,
        "No reconozco el cobro aprobado de 980 en Librería Norte",
        conversation=conversation,
    )
    assert escalated["outcome"] == "escalated"
    assert escalated["case"]["case_id"] != resolved["case"]["case_id"]
    assert escalated["case"]["transaction_id"] == "TXN-APPROVED"
    assert escalated["handoff"]["case_id"] == escalated["case"]["case_id"]

    greeting = _run(graph, "Hola", conversation=conversation)
    assert greeting["outcome"] == "resolved"
    assert greeting.get("handoff") is None
    assert greeting.get("case") is None


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
    assert third["case"]["transaction_id"] is None
    assert third["case"]["status"] == "escalated"
    assert third["handoff"]["case_id"] == third["case"]["case_id"]
    assert tools.calls_of("create_dispute")[-1][1]["transaction_id"] is None


def test_fraud_mention_always_escalates_with_structured_handoff(graph, tools):
    result = _run(graph, "me robaron la tarjeta, no fui yo, hay un cobro raro")

    assert result["outcome"] == "escalated"
    handoff = result["handoff"]
    assert handoff["reason"] == "fraud_suspected"
    for key in ("request", "verified_facts", "actions_taken", "evidence", "open_questions"):
        assert key in handoff
    assert result["case"]["transaction_id"] is None
    assert handoff["case_id"] == result["case"]["case_id"]


def _cases_opened(tools):
    """The transactions a case was opened on, in order."""
    return [params["transaction_id"] for _, params in tools.calls_of("create_dispute")]


def test_amount_above_threshold_creates_linked_human_review_case(graph, tools):
    tools.transactions.append(
        _tx("TXN-BIG", CUS_A, "Electro Mega", "Declined", 600.00)
    )
    result = _run(graph, "hay un cobro de 600 en Electro Mega que no reconozco")

    assert result["outcome"] == "escalated"
    assert result["handoff"]["reason"] == "amount_threshold"
    # The workflow spec: escalating opens the case as `escalated` and the customer gets its number.
    assert _cases_opened(tools) == ["TXN-BIG"]
    case = result["case"]
    assert case["status"] == "escalated"
    assert result["handoff"]["case_id"] == case["case_id"]
    assert result["handoff"]["escalated_in_backend"] is True
    assert case["case_id"] in result["reply"]
    assert [c[0] for c in tools.calls if c[0] in ("create_dispute", "escalate_dispute")] == ["create_dispute", "escalate_dispute"]
    assert result["case"]["transaction_id"] == "TXN-BIG"
    assert result["case"]["status"] == "escalated"


def test_out_of_scope_escalates(graph, tools):
    result = _run(graph, "quiero un préstamo personal nuevo")
    assert result["outcome"] == "escalated"
    assert result["handoff"]["reason"] == "out_of_scope"
    assert _cases_opened(tools) == []  # no transaction: nothing to open a case on


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
    assert _cases_opened(tools) == ["TXN-5"]
    assert result["case"]["status"] == "escalated"
    assert result["case"]["transaction_id"] == "TXN-5"


def test_unrecognized_approved_charge_escalates_as_possible_fraud(graph, tools):
    _only(tools, _tx("TXN-7", CUS_A, "Casino Royal", "Approved", 980.00, date="2026-06-12T23:10:00"))

    result = _run(graph, "No reconozco el cobro de 980 en Casino Royal")

    assert result["outcome"] == "escalated"
    assert result["handoff"]["reason"] == "posted_charge_disputed"
    assert _cases_opened(tools) == ["TXN-7"]
    assert result["case"]["status"] == "escalated"
    assert result["case"]["transaction_id"] == "TXN-7"


def test_pending_charge_also_escalates(graph, tools):
    _only(tools, _tx("TXN-8", CUS_A, "Tienda Norte", "Pending", 50.00))
    result = _run(graph, "No reconozco el cobro de 50 en Tienda Norte")
    assert result["outcome"] == "escalated"
    assert result["handoff"]["reason"] == "posted_charge_disputed"
    assert result["case"]["transaction_id"] == "TXN-8"


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
    # The case is opened on the RIGHT transaction, and never on the 120 one.
    assert _cases_opened(tools) == ["TXN-BIG"]
    assert result["case"]["transaction_id"] == "TXN-BIG"


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


def test_when_the_case_cannot_be_marked_resolved_the_agent_escalates_instead_of_promising(graph, tools, monkeypatch):
    """The safe path closes the case through the backend. If that fails (the route is missing, or it answers an
    error), "resolved" would be a promise nobody recorded, so the turn becomes an escalation."""
    from app.tools import ToolError

    async def no_resolve(token, case_id, resolution):
        raise ToolError(404, "Not Found")

    monkeypatch.setattr(tools, "resolve_dispute", no_resolve)
    result = _run(graph, "Me hicieron un cobro que no reconozco de 45.50 en Tienda Don Pepe")
    assert result["outcome"] == "escalated"
    assert result["handoff"]["reason"] == "verify_failed"
    assert result["case"]["status"] in ("open", "escalated")  # never reported as auto_resolved


def _run_selected(graph, message, transaction_id, conversation="conv-sel", token=f"token-{CUS_A}"):
    import asyncio
    import uuid

    return asyncio.run(
        graph.ainvoke(
            {
                "session_token": token,
                "message": message,
                "conversation_id": conversation,
                "run_id": str(uuid.uuid4()),
                "selected_transaction_id": transaction_id,
            },
            config={"configurable": {"thread_id": conversation}},
        )
    )


def test_a_picked_transaction_needs_no_description_to_resolve(graph, tools):
    """Words alone are not enough to close a case (a vague report is only proposed), but a transaction the customer
    picked in the app identifies itself."""
    result = _run_selected(graph, "No reconozco este cobro", "TXN-1")
    assert result["outcome"] == "resolved"
    assert _cases_opened(tools) == ["TXN-1"]
    assert result["case"]["status"] == "auto_resolved"
    assert "clarify" not in str(result.get("reason"))


def test_the_same_vague_words_without_a_pick_are_not_closed(graph, tools):
    result = _run(graph, "No reconozco este cobro")
    assert result["outcome"] != "resolved" or _cases_opened(tools) == []


def test_a_picked_transaction_does_not_skip_the_guardrail(graph, tools):
    tools.transactions.append(_tx("TXN-BIG", CUS_A, "Electro Mega", "Declined", 600.00))
    big = _run_selected(graph, "No reconozco este cobro", "TXN-BIG", conversation="c1")
    assert big["outcome"] == "escalated" and big["handoff"]["reason"] == "amount_threshold"
    tools.transactions.append(_tx("TXN-POSTED", CUS_A, "Casino", "Approved", 50.00))
    posted = _run_selected(graph, "No reconozco este cobro", "TXN-POSTED", conversation="c2")
    assert posted["outcome"] == "escalated" and posted["handoff"]["reason"] == "posted_charge_disputed"


def test_somebody_elses_transaction_is_ignored_and_never_leaks(graph, tools):
    result = _run_selected(graph, "No reconozco este cobro", "TXN-B1")  # belongs to CUS_B
    assert "TXN-B1" not in str(result.get("case")) and "Mega Mercado" not in result["reply"]
    assert "TXN-B1" not in _cases_opened(tools)


def test_a_transaction_that_does_not_exist_is_ignored(graph, tools):
    result = _run_selected(graph, "No reconozco este cobro", "TXN-NOPE")
    assert _cases_opened(tools) == []
    assert result["outcome"] != "resolved"


def test_fraud_wording_on_a_picked_transaction_escalates_with_its_case(graph, tools):
    result = _run_selected(graph, "me robaron la tarjeta, no fui yo", "TXN-1")
    assert result["outcome"] == "escalated" and result["handoff"]["reason"] == "fraud_suspected"
    assert _cases_opened(tools) == ["TXN-1"]
    assert result["case"]["status"] == "escalated"


def test_the_pick_does_not_carry_over_to_the_next_turn(graph, tools):
    _run_selected(graph, "No reconozco este cobro", "TXN-1", conversation="conv-carry")
    assert _cases_opened(tools) == ["TXN-1"]
    again = _run_selected(graph, "No reconozco el cobro de 120 en Farmacia Central", None, conversation="conv-carry")
    # The second turn is about TXN-2 (Farmacia Central), not about the transaction picked in the first.
    assert _cases_opened(tools)[-1] == "TXN-2"
    assert again["case"]["transaction_id"] == "TXN-2"


def test_a_declined_charge_explains_why_when_the_code_is_known(graph, tools):
    tools.transactions[0]["response_code"] = "51"
    tools.transactions[0]["response_meaning"] = {"es": "fondos insuficientes", "pt": "saldo insuficiente"}
    result = _run_selected(graph, "No reconozco este cobro", "TXN-1")
    assert "fondos insuficientes" in result["reply"] and "código 51" in result["reply"]
    assert "estándar" in result["reply"]  # said as the standard's meaning, not the bank's finding
    assert any("fondos insuficientes" in fact for fact in result["facts"])


def test_the_reason_is_in_portuguese_for_a_portuguese_message(graph, tools):
    tools.transactions[0]["response_code"] = "51"
    tools.transactions[0]["response_meaning"] = {"es": "fondos insuficientes", "pt": "saldo insuficiente"}
    result = _run_selected(graph, "Não reconheço esta cobrança", "TXN-1")
    assert "saldo insuficiente" in result["reply"] and "fondos" not in result["reply"]


def test_no_reason_is_invented_for_an_unknown_or_empty_code(graph, tools):
    tools.transactions[0]["response_code"] = "99"
    tools.transactions[0]["response_meaning"] = None
    result = _run_selected(graph, "No reconozco este cobro", "TXN-1")
    assert "Motivo informado" not in result["reply"] and "código 99" not in result["reply"]


# --- found by the held-out evaluation (docs/EVALUATION.md): the handoff arrived with no verified facts ----------


def test_an_escalation_hands_over_what_was_verified_and_what_the_customer_wrote(graph, tools):
    from tests.fakes import _tx, CUS_A

    tools.transactions.append(_tx("TXN-BIG", CUS_A, "Electro Mega", "Declined", 600.00))
    result = _run(graph, "No reconozco el cobro de 600 en Electro Mega")
    handoff = result["handoff"]
    facts = " | ".join(handoff["verified_facts"])
    assert "TXN-BIG" in facts and "Declined" in facts and "600.00 USD" in facts
    assert "GUARDRAIL_MAX_USD" in facts  # the rule that sent it to a person
    assert handoff["customer_message"] == "No reconozco el cobro de 600 en Electro Mega"


def test_an_escalation_with_no_transaction_says_so_instead_of_leaving_the_facts_empty(graph, tools):
    result = _run(graph, "Me robaron la tarjeta, no fui yo")
    facts = " | ".join(result["handoff"]["verified_facts"])
    assert "no se identificó una única transacción" in facts and "fraud" in facts
    assert len(result["handoff"]["customer_message"]) <= 300
