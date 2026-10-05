"""Unit tests for intent-evaluation cost reporting."""

from eval_intent import call_cost_usd


def test_provider_reported_cost_takes_precedence(monkeypatch):
    monkeypatch.setenv("INTENT_EVAL_INPUT_PRICE_PER_1M_USD", "99")
    monkeypatch.setenv("INTENT_EVAL_OUTPUT_PRICE_PER_1M_USD", "99")

    cost, source = call_cost_usd(
        {"cost": "0.00125", "prompt_tokens": 100, "completion_tokens": 20},
        requested_model=None,
        actual_model="vendor/model",
    )

    assert cost == 0.00125
    assert source == "openrouter_usage.cost"


def test_pinned_model_rates_estimate_per_call_cost(monkeypatch):
    monkeypatch.setenv("INTENT_EVAL_INPUT_PRICE_PER_1M_USD", "2")
    monkeypatch.setenv("INTENT_EVAL_OUTPUT_PRICE_PER_1M_USD", "4")

    cost, source = call_cost_usd(
        {"prompt_tokens": 1000, "completion_tokens": 500},
        requested_model="vendor/model",
        actual_model="vendor/model",
    )

    assert cost == 0.004
    assert source == "configured_per_million_rates"


def test_unpinned_model_or_incomplete_rates_are_not_priced(monkeypatch):
    monkeypatch.setenv("INTENT_EVAL_INPUT_PRICE_PER_1M_USD", "2")
    monkeypatch.delenv("INTENT_EVAL_OUTPUT_PRICE_PER_1M_USD", raising=False)

    cost, _ = call_cost_usd(
        {"prompt_tokens": 1000, "completion_tokens": 500},
        requested_model=None,
        actual_model="vendor/model",
    )
    assert cost is None

    cost, _ = call_cost_usd(
        {"prompt_tokens": 1000, "completion_tokens": 500},
        requested_model="vendor/model",
        actual_model="vendor/model",
    )
    assert cost is None
