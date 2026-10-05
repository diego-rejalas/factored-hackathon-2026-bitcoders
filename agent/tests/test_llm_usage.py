import asyncio

import httpx

from app.llm import LLM


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


def run_with(monkeypatch, bodies):
    answers = iter(bodies)

    async def post(self, *args, **kwargs):
        return FakeResponse(next(answers))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    llm = LLM(api_key="k", models=["m"])
    results = [asyncio.run(llm.chat("hola")) for _ in bodies]
    return llm, results


def body(text, usage):
    return {"choices": [{"message": {"content": text}}], "usage": usage}


def test_tokens_and_cost_are_added_up_across_calls(monkeypatch):
    llm, results = run_with(
        monkeypatch,
        [
            body("a", {"prompt_tokens": 100, "completion_tokens": 20, "cost": 0.0003}),
            body("b", {"prompt_tokens": 50, "completion_tokens": 10, "cost": 0.0001}),
        ],
    )
    assert results == ["a", "b"]
    assert llm.usage["calls"] == 2
    assert llm.usage["prompt_tokens"] == 150 and llm.usage["completion_tokens"] == 30
    assert round(llm.usage["cost"], 6) == 0.0004 and llm.usage["cost_reported_calls"] == 2


def test_a_reply_without_usage_still_counts_the_call_and_never_invents_a_cost(monkeypatch):
    llm, _ = run_with(monkeypatch, [{"choices": [{"message": {"content": "a"}}]}])
    assert llm.usage["calls"] == 1 and llm.usage["cost_reported_calls"] == 0 and llm.usage["cost"] == 0.0


# --- the structured classification, with the real prompt template (docs/EVALUATION.md) -------------------------


def test_the_structured_classification_builds_its_prompt_and_reads_the_answer(monkeypatch):
    """The prompt holds literal JSON braces: str.format raised KeyError on every call with an API key, which broke the
    understand step of the whole chat. The tests with a fake model never reached that line."""
    seen = {}

    async def post(self, url, headers=None, json=None, **kwargs):
        seen["prompt"] = json["messages"][1]["content"]
        return FakeResponse(
            {"model": "m", "choices": [{"message": {"content": '{"intent": "dispute", "language": "pt", "confidence": 0.9}'}}], "usage": {"prompt_tokens": 5, "completion_tokens": 3}}
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    llm = LLM(api_key="k", models=["m"])
    detail = asyncio.run(llm.classify_detailed('Não reconheço a cobrança {de} "256,10"'))
    assert detail["intent"] == "dispute" and detail["language"] == "pt" and detail["confidence"] == 0.9
    assert 'Não reconheço a cobrança {de} "256,10"' in seen["prompt"]  # the customer's own braces survive too
    assert llm.usage["prompt_tokens"] == 5
