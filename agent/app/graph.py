from copy import deepcopy
import time
from typing import TypedDict

try:
    from langgraph.checkpoint.memory import MemorySaver as Checkpointer
except ImportError:  # pragma: no cover
    from langgraph.checkpoint.memory import InMemorySaver as Checkpointer

from langgraph.graph import END, START, StateGraph

import app.guardrail as guardrail
import app.intents as intents
import app.replies as replies
from app.tools import ToolError

REASON_CODE = "unrecognized_charge"


class AgentState(TypedDict, total=False):
    session_token: str
    message: str
    conversation_id: str
    run_id: str
    language: str
    intent: str
    entities: dict
    route: str
    reason: str | None
    candidates: list
    candidate_options: list
    candidate: dict | None
    case: dict | None
    facts: list
    outcome: str
    reply: str
    handoff: dict | None
    clarify_rounds: int
    proposed_id: str | None
    error: str | None


def _elapsed(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def build_graph(tools, tracer, llm=None):
    """understand -> decide (deterministic guardrail) -> act -> verify ->
    escalate/respond. Control flow lives in code; the LLM only drafts the
    final reply from verified facts."""

    async def understand(state: AgentState) -> dict:
        start = time.monotonic()
        message = state["message"]
        language = "pt" if any(w in message.lower() for w in ("não", "você", "obrigado", "obrigada", "bom dia", "boa tarde", "boa noite", "não reconheço", "cobrança", "estorno")) else "es"
        intent = await intents.classify(message, llm)
        # A short "yes" answers the candidate proposed in the previous turn: it is part of the
        # dispute, whatever the classifier makes of two words.
        if state.get("proposed_id") and guardrail.is_affirmation(message):
            intent = "dispute"
        await tracer.log(
            state["run_id"], state["conversation_id"], "understand",
            intent=intent, params={"language": language}, latency_ms=_elapsed(start),
        )
        continuing_dispute = intent == "dispute"
        return {
            "language": language,
            "intent": intent,
            "entities": guardrail.extract_entities(message),
            # Clear per-turn results from the previous checkpoint. Only case-status
            # requests intentionally reuse the last case; dispute clarification keeps
            # its proposal and round count across turns.
            "route": None,
            "reason": None,
            "candidates": [],
            "candidate_options": state.get("candidate_options", []) if continuing_dispute else [],
            "candidate": None,
            "case": state.get("case") if intent == "case_status" else None,
            "facts": [],
            "outcome": None,
            "handoff": None,
            "reply": None,
            "proposed_id": state.get("proposed_id") if continuing_dispute else None,
            "clarify_rounds": state.get("clarify_rounds", 0) if continuing_dispute else 0,
        }

    async def fetch_candidates(state: AgentState, entities: dict) -> list:
        """Every status, not only Declined/Reversed: a charge that was approved is exactly the
        one a customer disputes as unrecognized, and it must never be invisible to the agent."""
        token = state["session_token"]
        days = entities.get("days")
        merged: list = []
        for status in ("Declined", "Reversed", "Approved", "Pending"):
            merged += await tools.list_transactions(token, status=status, days=days, limit=50)
        merged.sort(key=lambda tx: str(tx.get("transaction_date") or ""), reverse=True)
        return merged

    async def decide(state: AgentState) -> dict:
        start = time.monotonic()
        message = state["message"]
        intent = guardrail.guardrail_intent(message, state["intent"])

        if intent == "fraud_report":
            await tracer.log(state["run_id"], state["conversation_id"], "decide", intent=intent, result_status="escalate", params={"reason": "fraud_suspected"}, latency_ms=_elapsed(start))
            return {"intent": intent, "route": "escalate", "reason": "fraud_suspected", "outcome": "escalated"}

        if intent == "out_of_scope":
            await tracer.log(state["run_id"], state["conversation_id"], "decide", intent=intent, result_status="escalate", params={"reason": "out_of_scope"}, latency_ms=_elapsed(start))
            return {"intent": intent, "route": "escalate", "reason": "out_of_scope", "outcome": "escalated"}

        if intent == "greeting":
            await tracer.log(state["run_id"], state["conversation_id"], "decide", intent=intent, result_status="answer", latency_ms=_elapsed(start))
            return {"intent": intent, "route": "respond", "outcome": "resolved"}

        if intent == "case_status":
            case = state.get("case")
            if case:
                fresh = await tools.get_dispute(state["session_token"], case["case_id"])
                await tracer.log(state["run_id"], state["conversation_id"], "decide", intent=intent, tool="get_dispute", result_status="answer", latency_ms=_elapsed(start))
                return {"intent": intent, "route": "respond", "case": fresh, "outcome": "resolved", "facts": [f"case {fresh['case_id']} status {fresh['status']}"]}
            await tracer.log(state["run_id"], state["conversation_id"], "decide", intent=intent, result_status="clarify", latency_ms=_elapsed(start))
            return {"intent": intent, "route": "respond", "outcome": "clarify", "reason": "no_case_yet"}

        # intent == "dispute": candidate selection is deterministic.
        if state.get("clarify_rounds", 0) >= 2:
            await tracer.log(state["run_id"], state["conversation_id"], "decide", intent=intent, result_status="escalate", params={"reason": "ambiguity_unresolved"}, latency_ms=_elapsed(start))
            return {"intent": intent, "route": "escalate", "reason": "ambiguity_unresolved", "outcome": "escalated"}

        entities = state.get("entities") or {}
        candidates = await fetch_candidates(state, entities)

        # A short "yes" confirms the one candidate proposed in the previous turn.
        proposed = state.get("proposed_id")
        affirmed = bool(proposed) and guardrail.is_affirmation(message)
        if affirmed:
            pool = [tx for tx in candidates if tx.get("transaction_id") == proposed]
        else:
            pool = guardrail.narrow_candidates(candidates, message, entities)

        if len(pool) != 1:
            await tracer.log(state["run_id"], state["conversation_id"], "decide", intent=intent, result_status="clarify", params={"candidates": len(pool)}, latency_ms=_elapsed(start))
            return {
                "intent": intent,
                "route": "respond",
                "outcome": "clarify",
                "reason": "no_case_yet" if len(pool) == 0 else "multiple_candidates",
                "candidates": pool,
                "candidate_options": pool,
                "proposed_id": None,
                "clarify_rounds": state.get("clarify_rounds", 0) + 1,
            }

        candidate = pool[0]

        # A charge that went through (Approved) or is still open (Pending): money may have moved,
        # and the customer says they do not recognize it. Never resolved by the agent.
        if candidate.get("transaction_status") not in ("Declined", "Reversed"):
            await tracer.log(state["run_id"], state["conversation_id"], "decide", intent=intent, tool="check_status", result_status="escalate", params={"reason": "posted_charge_disputed", "status": candidate.get("transaction_status")}, latency_ms=_elapsed(start))
            return {"intent": intent, "route": "escalate", "reason": "posted_charge_disputed", "outcome": "escalated", "candidate": candidate, "proposed_id": None}

        # The customer's own words must identify the transaction. A vague report is never closed
        # against whatever single candidate exists: the agent proposes it and asks.
        if not (affirmed or guardrail.is_corroborated(candidate, message, entities)):
            await tracer.log(state["run_id"], state["conversation_id"], "decide", intent=intent, result_status="clarify", params={"reason": "unconfirmed_candidate"}, latency_ms=_elapsed(start))
            return {
                "intent": intent,
                "route": "respond",
                "outcome": "clarify",
                "reason": "unconfirmed_candidate",
                "candidates": pool,
                "candidate_options": pool,
                "proposed_id": candidate["transaction_id"],
                "clarify_rounds": state.get("clarify_rounds", 0) + 1,
            }

        # Unknown USD amount is never treated as zero.
        if not guardrail.amount_known(candidate):
            await tracer.log(state["run_id"], state["conversation_id"], "decide", intent=intent, tool="check_amount", result_status="escalate", params={"reason": "amount_unknown"}, latency_ms=_elapsed(start))
            return {"intent": intent, "route": "escalate", "reason": "amount_unknown", "outcome": "escalated", "candidate": candidate, "proposed_id": None}

        if guardrail.exceeds_threshold(candidate):
            await tracer.log(state["run_id"], state["conversation_id"], "decide", intent=intent, tool="check_amount", result_status="escalate", params={"reason": "amount_threshold", "amount_usd": guardrail.effective_usd(candidate)}, latency_ms=_elapsed(start))
            return {"intent": intent, "route": "escalate", "reason": "amount_threshold", "outcome": "escalated", "candidate": candidate, "proposed_id": None}

        await tracer.log(state["run_id"], state["conversation_id"], "decide", intent=intent, result_status="act", params={"transaction_id": candidate["transaction_id"]}, latency_ms=_elapsed(start))
        return {"intent": intent, "route": "act", "candidate": candidate, "candidates": pool, "proposed_id": None}

    async def act(state: AgentState) -> dict:
        start = time.monotonic()
        candidate = state["candidate"]
        status = candidate.get("transaction_status", "")
        summary = (
            f"Cliente reporta cobro de {replies.describe(candidate)} que no reconoce; "
            f"la transacción {candidate['transaction_id']} figura como {status}."
        )
        case = await tools.create_dispute(
            state["session_token"], candidate["transaction_id"], REASON_CODE, summary
        )
        await tracer.log(state["run_id"], state["conversation_id"], "act", intent=state["intent"], tool="create_dispute", params={"transaction_id": candidate["transaction_id"]}, result_status=case.get("status"), latency_ms=_elapsed(start))
        return {"case": case}

    async def verify(state: AgentState) -> dict:
        start = time.monotonic()
        case = state["case"]
        fresh = await tools.get_dispute(state["session_token"], case["case_id"])
        if fresh.get("status") not in ("open", "auto_resolved", "escalated"):
            await tracer.log(state["run_id"], state["conversation_id"], "verify", intent=state["intent"], tool="get_dispute", result_status="failed", latency_ms=_elapsed(start))
            return {"route": "escalate", "reason": "verify_failed", "outcome": "escalated", "case": fresh}
        # The safe path closes the case itself: a Declined/Reversed charge under the
        # threshold is documented and marked auto_resolved by the backend (never by the
        # LLM), so "resolved" means a verified terminal state, not a promise.
        if fresh.get("status") == "open":
            candidate = state.get("candidate") or {}
            resolution = (
                "reversal_confirmed"
                if candidate.get("transaction_status") == "Reversed"
                else "no_charge_confirmed"
            )
            try:
                fresh = await tools.resolve_dispute(
                    state["session_token"], case["case_id"], resolution
                )
            except ToolError as error:
                await tracer.log(state["run_id"], state["conversation_id"], "verify", intent=state["intent"], tool="resolve_dispute", result_status="failed", params={"error": error.status_code}, latency_ms=_elapsed(start))
                return {"route": "escalate", "reason": "verify_failed", "outcome": "escalated", "case": case}
            await tracer.log(state["run_id"], state["conversation_id"], "verify", intent=state["intent"], tool="resolve_dispute", params={"resolution": resolution}, result_status=fresh.get("status"), latency_ms=_elapsed(start))
            if fresh.get("status") != "auto_resolved":
                return {"route": "escalate", "reason": "verify_failed", "outcome": "escalated", "case": fresh}
        candidate = state.get("candidate") or {}
        facts = [
            f"transacción {candidate.get('transaction_id')} ({replies.describe(candidate)}) estado {candidate.get('transaction_status')}",
            f"monto efectivo {guardrail.effective_usd(candidate):.2f} USD",
            f"caso {fresh['case_id']} verificado en estado {fresh['status']}",
        ]
        return {"case": fresh, "facts": facts, "outcome": "resolved", "route": "respond"}

    def build_handoff(state: AgentState) -> dict:
        candidate = state.get("candidate")
        case = state.get("case")
        case_id = case.get("case_id") if case else None
        handoff = {
            "reason": state.get("reason") or "unspecified",
            "limitation": guardrail.GUARDRAIL_LIMITATIONS.get(state.get("reason") or "", "human review required"),
            "request": {
                "es": "Revisión humana requerida: el guardrail no permite auto-resolver este caso.",
                "pt": "Revisão humana necessária: o guardrail não permite auto-resolver este caso.",
            },
            "customer_language": state.get("language", "es"),
            "conversation_id": state.get("conversation_id"),
            "verified_facts": state.get("facts") or [],
            "actions_taken": ([{"action": "create_dispute", "case_id": case_id}] if case_id else []),
            "evidence": (
                [{"candidate_transaction": candidate}] if candidate else []
            ),
            "open_questions": ["Confirmar con el cliente el comercio/monto/fecha exactos."],
        }
        if case_id:
            handoff["case_id"] = case_id
        return handoff

    async def escalate(state: AgentState) -> dict:
        start = time.monotonic()
        case = state.get("case")
        creation_error: ToolError | None = None
        if case is None and state.get("reason") in {
            "fraud_suspected",
            "amount_threshold",
            "amount_unknown",
            "posted_charge_disputed",
            "ambiguity_unresolved",
        }:
            candidate = state.get("candidate") or {}
            transaction_id = candidate.get("transaction_id")
            summary = (
                f"Cliente solicita revisión humana ({state.get('reason')}); "
                + (
                    f"transacción {transaction_id} figura como {candidate.get('transaction_status')}."
                    if transaction_id
                    else "no se identificó una transacción única."
                )
            )
            try:
                case = await tools.create_dispute(
                    state["session_token"], transaction_id, REASON_CODE, summary
                )
                await tracer.log(
                    state["run_id"], state["conversation_id"], "escalate",
                    intent=state["intent"], tool="create_dispute",
                    params={"transaction_id": transaction_id},
                    result_status=case.get("status"), latency_ms=_elapsed(start),
                )
            except ToolError as error:
                creation_error = error
                await tracer.log(
                    state["run_id"], state["conversation_id"], "escalate",
                    intent=state["intent"], tool="create_dispute",
                    result_status="failed", params={"error": error.status_code},
                    latency_ms=_elapsed(start),
                )
        handoff_state = {**state, "case": case}
        handoff = build_handoff(handoff_state)
        if state.get("candidate_options") and not state.get("candidate"):
            handoff["evidence"].append({"candidate_options": deepcopy(state["candidate_options"])})
        if creation_error:
            handoff["case_creation_failed"] = True
        if case:
            try:
                escalated_case = await tools.escalate_dispute(
                    state["session_token"], case["case_id"], handoff
                )
                case = escalated_case or case
                handoff["escalated_in_backend"] = escalated_case is not None
            except ToolError as error:
                handoff["escalated_in_backend"] = False
                handoff["backend_error"] = error.detail
        await tracer.log(state["run_id"], state["conversation_id"], "escalate", intent=state["intent"], tool="escalate_dispute" if case else None, result_status="escalated", latency_ms=_elapsed(start))
        return {"case": case, "handoff": handoff, "outcome": "escalated"}

    async def respond(state: AgentState) -> dict:
        start = time.monotonic()
        language = state.get("language", "es")
        route = state.get("route")
        outcome = state.get("outcome", "resolved")

        if state.get("handoff"):
            reply = replies.escalated_reply(language, state["handoff"])
        elif route == "respond" and outcome == "clarify":
            if state.get("reason") == "unconfirmed_candidate":
                reply = replies.confirm_reply(language, (state.get("candidates") or [{}])[0])
            elif state.get("reason") == "multiple_candidates":
                reply = replies.clarify_reply(language, state.get("candidates") or [])
            else:
                reply = replies.clarify_empty_reply(language)
        elif state.get("reason") == "no_case_yet" and outcome == "clarify":
            reply = replies.clarify_empty_reply(language)
        elif state.get("intent") == "greeting":
            reply = replies.greeting_reply(language)
        elif state.get("case") and state.get("intent") == "case_status":
            reply = replies.status_reply(language, state["case"])
        elif state.get("case") and state.get("candidate"):
            reply = replies.resolved_reply(language, state["case"], state["candidate"])
        else:
            reply = replies.clarify_empty_reply(language)

        if llm is not None and llm.enabled:
            facts = state.get("facts") or []
            draft = await llm.chat(
                "Hechos verificados:\n- " + "\n- ".join(facts)
                + f"\n\nMensaje del cliente: {state['message']}\n"
                + f"Redacta la respuesta final al cliente en {language} usando solo estos hechos."
            )
            if draft:
                reply = draft
        await tracer.log(state["run_id"], state["conversation_id"], "respond", intent=state.get("intent"), result_status=outcome, latency_ms=_elapsed(start))
        return {"reply": reply}

    def route_after_decide(state: AgentState) -> str:
        route = state.get("route")
        if route == "act":
            return "act"
        if route == "escalate":
            return "escalate"
        return "respond"

    def route_after_verify(state: AgentState) -> str:
        return "escalate" if state.get("route") == "escalate" else "respond"

    builder = StateGraph(AgentState)
    builder.add_node("understand", understand)
    builder.add_node("decide", decide)
    builder.add_node("act", act)
    builder.add_node("verify", verify)
    builder.add_node("escalate", escalate)
    builder.add_node("respond", respond)

    builder.add_edge(START, "understand")
    builder.add_edge("understand", "decide")
    builder.add_conditional_edges("decide", route_after_decide, ["act", "escalate", "respond"])
    builder.add_edge("act", "verify")
    builder.add_conditional_edges("verify", route_after_verify, ["escalate", "respond"])
    builder.add_edge("escalate", "respond")
    builder.add_edge("respond", END)

    return builder.compile(checkpointer=Checkpointer())
