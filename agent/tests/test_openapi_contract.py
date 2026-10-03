"""The agent's API contract, committed. See backend/tests/test_openapi_contract.py for how and why.

    UPDATE_CONTRACT=1 python -m pytest tests/test_openapi_contract.py
"""

import json
import os
from pathlib import Path

from app.main import create_app
from app.tracing import NullTracer
from tests.fakes import FakeBankTools

CONTRACT = Path(__file__).parent / "contract" / "openapi.json"


def generated() -> dict:
    return create_app(tools=FakeBankTools(), tracer=NullTracer(), llm=None).openapi()


def test_the_committed_contract_is_what_the_code_generates():
    current = json.dumps(generated(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if os.environ.get("UPDATE_CONTRACT"):
        CONTRACT.write_text(current)
    assert CONTRACT.exists(), "run: UPDATE_CONTRACT=1 python -m pytest tests/test_openapi_contract.py"
    assert CONTRACT.read_text() == current, (
        "the generated OpenAPI differs from tests/contract/openapi.json: review the change and, if it is intended, "
        "regenerate with UPDATE_CONTRACT=1"
    )


def test_the_chat_request_cannot_name_a_customer():
    schema = generated()["components"]["schemas"]["ChatRequest"]
    assert set(schema["properties"]) == {"session_token", "message", "conversation_id", "transaction_id"}
    assert "customer_id" not in schema["properties"]


def test_the_chat_response_carries_what_the_app_needs_to_follow_up():
    schema = generated()["components"]["schemas"]["ChatResponse"]
    assert {"reply", "conversation_id", "outcome", "handoff", "case_id", "case_status"} <= set(schema["properties"])
