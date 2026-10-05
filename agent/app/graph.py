"""Build the banking customer-service conversation graph and policy flow."""

import asyncio
import time
from copy import deepcopy
from typing import TypedDict

try:
    from langgraph.checkpoint.memory import MemorySaver as Checkpointer
except ImportError:  # pragma: no cover
    from langgraph.checkpoint.memory import InMemorySaver as Checkpointer

from langgraph.graph import END, START, StateGraph

import app.grounding as grounding
from app import guardrail, intents, ranking, replies
from app.tools import ToolError

REASON_CODE = "unrecognized_charge"


class AgentState(TypedDict, total=False):
    """Store graph inputs and per-turn decision, candidate, and reply state."""

    session_token: str
    message: str
    conversation_id: str
    run_id: str
    language: str
    intent: str
    intent_confidence: float | None
    intent_source: str | None
    intent_abstain: bool
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
    selected_transaction_id: str | None
    error: str | None


def dispute_summary(candidate: dict) -> str:
    status = candidate.get("transaction_status", "")
    return (
        f"Cliente reporta cobro de {replies.describe(candidate)} que no reconoce; "
        f"la transacción {candidate['transaction_id']} figura como {status}."
    )


def _elapsed(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def build_graph(tools, tracer, llm=None):
    """Build and compile the customer-service conversation graph.

    The deterministic guardrail controls understand, decide, act, and verify;
    the LLM only drafts the final response from verified facts.
    """

    async def understand(state: AgentState) -> dict:
        start = time.monotonic()
        message = state["message"]
        # Classification and a second look for fraud run together, so the second look costs no extra waiting. It can
        # only make the agent more cautious: a "yes" hands over to a person, a "no" or a failure leaves the keyword
        # rule as it was. It also applies to "out of scope": a leaked password or a phishing link is not a loan
        # request, it is a security matter a person must see, and a decline would leave the customer with nothing.
        second_look = getattr(llm, "flags_fraud", None)  # a model without it (a test double) just skips the look
        if llm is not None and llm.enabled and second_look is not None and not guardrail.mentions_fraud(message):
            classification, fraud = await asyncio.gather(intents.classify_detailed(message, llm), second_look(message))
        else:
            classification, fraud = await intents.classify_detailed(message, llm), None
        intent = classification["intent"]
        # The replies exist in Spanish and Portuguese: a "mixed" reading from the model is settled by the text itself.
        language = classification["language"] if classification["language"] in ("es", "pt") else replies.detect_language(message)
        if fraud and intent in ("dispute", "out_of_scope"):
            intent = "fraud_report"
        # A short "yes" answers the candidate proposed in the previous turn: it is part of the
        # dispute, whatever the classifier makes of two words.
        if state.get("proposed_id") and guardrail.is_affirmation(message):
            intent = "dispute"
            classification["abstain"] = False
        await tracer.log(
            state["run_id"], state["conversation_id"], "understand",
            intent=intent,
            params={
                "language": language,
                "intent_source": classification["source"],
                "intent_confidence": classification["confidence"],
                "intent_abstain": classification["abstain"],
                "intent_prompt_version": classification["prompt_version"],
                "classifier_latency_ms": classification["classifier_latency_ms"],
            },
            latency_ms=_elapsed(start),
        )
        continuing_dispute = intent == "dispute"
        return {
            "language": language,
            "intent": intent,
            "intent_confidence": classification["confidence"],
            "intent_source": classification["source"],
            "intent_abstain": classification["abstain"],
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

    async def selected_transaction(state: AgentState) -> dict | None:
        """The transaction the customer picked in the app (a button on a movement), or None.

        The backend checks that it is theirs: a 404 means "not found for this customer", and then it is as if
        nothing had been picked, never an error and never somebody else's data.
        """
        transaction_id = state.get("selected_transaction_id")
        if not transaction_id:
            return None
        try:
            return await tools.get_transaction(state["session_token"], transaction_id)
        except ToolError as error:
            if error.status_code == 404:
                return None
            raise

    async def fetch_candidates(state: AgentState, entities: dict) -> list:
        """List all statuses so disputed posted charges remain visible.

        An approved charge may be the exact transaction the customer disputes.
        """
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
            decision = {"intent": intent, "route": "escalate", "reason": "fraud_suspected", "outcome": "escalated"}
            selected = await selected_transaction(state)
            if selected is not None:
                decision["candidate"] = selected
            return decision

        # El clasificador se abstuvo (confianza bajo INTENT_MIN_CONFIDENCE):
        # regla de código, nunca del modelo. Siempre después del override de fraude.
        if state.get("intent_abstain"):
            await tracer.log(state["run_id"], state["conversation_id"], "decide", intent=intent, result_status="escalate", params={"reason": "intent_low_confidence", "confidence": state.get("intent_confidence")}, latency_ms=_elapsed(start))
            return {"intent": intent, "route": "escalate", "reason": "intent_low_confidence", "outcome": "escalated"}

        if intent == "out_of_scope":
            # Declined, not escalated: there is no case and no handoff behind it, so claiming that "a person continues
            # from here" would be false and nobody would pick it up. (A customer asked about the weather and was told
            # a specialist team had the case.)
            await tracer.log(state["run_id"], state["conversation_id"], "decide", intent=intent, result_status="declined", params={"reason": "out_of_scope"}, latency_ms=_elapsed(start))
            return {"intent": intent, "route": "respond", "reason": "out_of_scope", "outcome": "declined"}

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
        selected = await selected_transaction(state)
        if selected is not None:
            # The customer picked it in the app: that identifies the transaction better than any words do, so
            # there is nothing to search or to confirm. Every other check below still applies to it.
            candidates, pool, affirmed = [selected], [selected], False
        else:
            candidates = await fetch_candidates(state, entities)

            # A short "yes" confirms the one candidate proposed in the previous turn.
            proposed = state.get("proposed_id")
            affirmed = bool(proposed) and guardrail.is_affirmation(message)
            if affirmed:
                pool = [tx for tx in candidates if tx.get("transaction_id") == proposed]
            else:
                pool = guardrail.narrow_candidates(candidates, message, entities)
                # The ranker only orders an ambiguous pool (which options are offered first); 0, 1 or 2+ and all the
                # policy remain narrow_candidates.
                if len(pool) > 1:
                    pool = ranking.rank_candidates(message, pool)

        if len(pool) != 1:
            await tracer.log(state["run_id"], state["conversation_id"], "decide", intent=intent, result_status="clarify", params={"candidates": len(pool), "ranked_by": "weighted_v1" if len(pool) > 1 else None}, latency_ms=_elapsed(start))
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
        if not (affirmed or selected is not None or guardrail.is_corroborated(candidate, message, entities)):
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
        case = await tools.create_dispute(
            state["session_token"], candidate["transaction_id"], REASON_CODE, dispute_summary(candidate)
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
        if replies.decline_reason(candidate, "es"):
            facts.append(replies.decline_reason(candidate, "es").strip())
        return {"case": fresh, "facts": facts, "outcome": "resolved", "route": "respond"}

    def handoff_facts(state: AgentState) -> list[str]:
        facts = list(state.get("facts") or [])
        candidate = state.get("candidate")
        if candidate:
            known = guardrail.amount_known(candidate)
            facts.append(
                f"transacción {candidate.get('transaction_id')} ({candidate.get('merchant_name') or 'sin comercio'}), "
                f"estado {candidate.get('transaction_status')}, del cliente (titularidad verificada por el backend)"
            )
            facts.append(f"monto efectivo {guardrail.effective_usd(candidate):.2f} USD" if known else "monto efectivo en USD desconocido")
            if candidate.get("transaction_date"):
                facts.append(f"fecha {str(candidate['transaction_date'])[:10]}")
            if candidate.get("response_code"):
                facts.append(f"código de respuesta {candidate['response_code']}")
        else:
            total = len(state.get("candidates") or [])
            facts.append("no se identificó una única transacción" + (f" ({total} candidatas en la ventana de búsqueda)" if total else ""))
        facts.append(f"regla aplicada: {guardrail.GUARDRAIL_LIMITATIONS.get(state.get('reason') or '', 'revisión humana requerida')}")
        return facts

    def build_handoff(state: AgentState) -> dict:
        candidate = state.get("candidate")
        case = state.get("case")
        case_id = case.get("case_id") if case else None
        handoff = {
            "reason": state.get("reason") or "unspecified",
            "limitation": guardrail.GUARDRAIL_LIMITATIONS.get(state.get("reason") or "", "human review required"),
            "request": replies.handoff_request(state.get("reason")),
            "customer_language": state.get("language", "es"),
            "conversation_id": state.get("conversation_id"),
            # What the person taking the case can rely on without asking again: what the backend confirmed about the
            # transaction and which rule sent it to them. (Before the held-out evaluation this was empty on every
            # escalation, because facts were only collected on the path that resolves.)
            "verified_facts": handoff_facts(state),
            "customer_message": " ".join((state.get("message") or "").split())[:300],
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
            "intent_low_confidence",
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
        elif outcome == "declined":
            reply = replies.declined_reply(language)
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

        draft_status = None
        facts = state.get("facts") or []
        # The model phrases ONE thing: a case the policy resolved and the backend recorded, which is the only
        # turn that has verified facts to give it. Escalations, questions, greetings and statuses keep their fixed
        # text: the escalation carries the case number and what happens next, the question carries the candidates,
        # and without facts a model improvises (it told customers to contact the fraud team, when the case had
        # already been escalated to a person).
        drafts_here = (
            llm is not None
            and llm.enabled
            and facts
            and outcome == "resolved"
            and not state.get("handoff")
            and state.get("case")
            and state.get("candidate")
            and state.get("intent") == "dispute"
        )
        if drafts_here:
            case_id = str(state["case"].get("case_id") or "")
            draft = await llm.chat(
                "Hechos verificados:\n- " + "\n- ".join(facts)
                + f"\n\nMensaje del cliente: {state['message']}\n"
                + f"Redacta la respuesta final al cliente en {language} usando solo estos hechos."
            )
            if not draft:
                draft_status = "llm_no_answer"
            else:
                broken = grounding.check(draft, facts, state["message"], case_id)
                if broken:
                    draft_status = f"llm_rejected_{broken}"  # the fixed text stays
                else:
                    reply = grounding.with_case_id(draft, case_id, language)
                    draft_status = "llm_drafted"
        await tracer.log(state["run_id"], state["conversation_id"], "respond", intent=state.get("intent"), result_status=draft_status or outcome, latency_ms=_elapsed(start))
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
