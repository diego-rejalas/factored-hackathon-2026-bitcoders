"""Componente B integrado: el ranker ordena el pool ambiguo, no autoriza.

Sin LLM y sin red: FakeBankTools + el ranker determinista (difflib).
"""

import pytest
from app.graph import build_graph
from app.llm import LLM
from app.ranking import rank_candidates, score_candidate
from app.tracing import NullTracer
from tests.fakes import CUS_A, FakeBankTools, _tx


@pytest.fixture()
def tools():
    return FakeBankTools()


@pytest.fixture()
def graph(tools):
    return build_graph(tools, NullTracer(), LLM(api_key=None))


def _run(graph, message, conversation="conv-ranking", token=f"token-{CUS_A}"):
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


# --- unidad -----------------------------------------------------------------------


def test_rank_candidates_orders_by_claim_evidence():
    old = _tx("TXN-OLD", CUS_A, "Farmacia Central", "Declined", 121.00, date="2026-06-10T10:00:00")
    new = _tx("TXN-NEW", CUS_A, "Farmacia Central", "Declined", 45.50, date="2026-06-09T10:00:00")
    ranked = rank_candidates("no reconozco el cobro de 45.50 en Farmacia Central", [old, new])
    assert ranked[0]["transaction_id"] == "TXN-NEW"


def test_rank_candidates_is_stable_without_evidence_and_preserves_membership():
    a = _tx("TXN-A", CUS_A, None, "Declined", 40.00, date="2026-06-01T10:00:00")
    b = _tx("TXN-B", CUS_A, None, "Declined", 55.00, date="2026-06-02T10:00:00")
    ranked = rank_candidates("me hicieron un cobro que no reconozco", [a, b])
    assert [tx["transaction_id"] for tx in ranked] == ["TXN-A", "TXN-B"]  # orden de entrada
    ranked_rev = rank_candidates("me hicieron un cobro que no reconozco", [b, a])
    assert [tx["transaction_id"] for tx in ranked_rev] == ["TXN-B", "TXN-A"]
    # nunca agrega ni quita
    assert {tx["transaction_id"] for tx in ranked} == {"TXN-A", "TXN-B"}


def test_score_is_higher_for_the_matching_transaction():
    match = _tx("TXN-M", CUS_A, "Librería Norte", "Declined", 30.00)
    other = _tx("TXN-O", CUS_A, None, "Declined", 310.00)
    claim = "cobro de 30 en Librería Norte que no reconozco"
    assert score_candidate(claim, match) > score_candidate(claim, other)


# --- integración en decide -----------------------------------------------------------


def test_ambiguous_pool_lists_the_likeliest_option_first(graph, tools):
    tools.transactions = [
        # "46" coincide aprox con ambos (ninguno exacto): pool de 2. La fecha
        # descendente pondría el de 45.80 primero; el claim apunta al de 46.10.
        _tx("TXN-OLD", CUS_A, "Farmacia Central", "Declined", 45.80, date="2026-06-10T10:00:00"),
        _tx("TXN-NEW", CUS_A, "Farmacia Central", "Declined", 46.10, date="2026-06-09T10:00:00"),
    ]
    result = _run(graph, "no reconozco un cobro de 46 en Farmacia Central")

    assert result["outcome"] == "clarify"
    options = result["candidate_options"]
    assert [tx["transaction_id"] for tx in options] == ["TXN-NEW", "TXN-OLD"]
    assert options[0]["merchant_name"] in result["reply"]


def test_ranker_never_resolves_an_ambiguous_pool(graph, tools):
    tools.transactions = [
        _tx("TXN-OLD", CUS_A, "Farmacia Central", "Declined", 45.80, date="2026-06-10T10:00:00"),
        _tx("TXN-NEW", CUS_A, "Farmacia Central", "Declined", 46.10, date="2026-06-09T10:00:00"),
    ]
    result = _run(graph, "no reconozco un cobro de 46 en Farmacia Central")
    assert tools.calls_of("create_dispute") == []
    assert result["outcome"] == "clarify"


def test_single_candidate_path_is_untouched_by_the_ranker(graph, tools):
    tools.transactions = [_tx("TXN-2", CUS_A, "Farmacia Central", "Declined", 120.00)]
    result = _run(graph, "cobro que no reconozco de 120 en Farmacia Central")
    assert result["outcome"] == "resolved"
    assert result["case"]["transaction_id"] == "TXN-2"


def test_empty_pool_stays_empty_and_asks(graph, tools):
    tools.transactions = [_tx("TXN-2", CUS_A, "Farmacia Central", "Declined", 120.00)]
    result = _run(graph, "no reconozco un cobro de 999 en Casino Royal")
    assert result["outcome"] == "clarify"
    assert result["candidates"] == []
    assert tools.calls_of("create_dispute") == []
