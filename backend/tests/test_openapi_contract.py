"""The API contract: the OpenAPI document this service generates is committed, and a change to it is a decision.

If this fails you changed a route, a parameter or a response model. If that was intended, regenerate the file and
review the diff in the pull request like any other change to the contract:

    UPDATE_CONTRACT=1 python -m pytest tests/test_openapi_contract.py

The web app (through its BFF) and the agent are written against this, so it must not drift unnoticed.
"""

import json
import os
from pathlib import Path

from app.main import create_app
from tests.fakes import FakeStore

CONTRACT = Path(__file__).parent / "contract" / "openapi.json"

# The only operations that do not ask for a session. Anything else that appears without security is a mistake.
PUBLIC = {
    ("get", "/health"),
    ("get", "/ready"),
    ("post", "/session"),  # the agent's login (customer id + document)
    ("post", "/v1/auth/login"),
    ("get", "/v1/auth/demo-accounts"),
    ("post", "/admin/session"),  # the specialist's login: it asks for the credentials
    ("get", "/meta/demo-scenarios"),  # public by design: the sandbox's demo picks, never a fraud field
}


def generated() -> dict:
    return create_app(FakeStore()).openapi()


def test_the_committed_contract_is_what_the_code_generates():
    current = json.dumps(generated(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if os.environ.get("UPDATE_CONTRACT"):
        CONTRACT.write_text(current)
    assert CONTRACT.exists(), "run: UPDATE_CONTRACT=1 python -m pytest tests/test_openapi_contract.py"
    assert CONTRACT.read_text() == current, (
        "the generated OpenAPI differs from tests/contract/openapi.json: review the change and, if it is intended, "
        "regenerate with UPDATE_CONTRACT=1"
    )


def test_every_operation_asks_for_a_session_except_the_public_ones():
    document = generated()
    unprotected = {
        (method, path)
        for path, item in document["paths"].items()
        for method, operation in item.items()
        if not operation.get("security")
    }
    assert unprotected == PUBLIC, f"public by accident: {sorted(unprotected - PUBLIC)}; protected by accident: {sorted(PUBLIC - unprotected)}"


def test_no_route_takes_a_customer_id_from_the_caller():
    """Identity comes from the validated session token, never from a parameter, a path or a body."""
    document = generated()
    offenders = []
    for path, item in document["paths"].items():
        if path == "/session":  # the login: the customer proves who they are with their document
            continue
        if path.startswith("/admin/"):  # a specialist looks at any customer's cases: the role is what authorizes it
            continue
        for method, operation in item.items():
            names = [p["name"] for p in operation.get("parameters", [])]
            if any("customer" in name for name in names) or "{customer" in path:
                offenders.append((method, path))
    assert offenders == []
    schemas = document["components"]["schemas"]
    for name, schema in schemas.items():
        if name.endswith("Create") or name.endswith("Request"):
            if name == "SessionRequest":
                continue
            assert "customer_id" not in schema.get("properties", {}), name


def test_no_schema_has_a_field_for_fraud_ground_truth_or_a_password_hash():
    """The prose of the API description mentions is_fraud (to say it is never exposed), so look at the fields."""
    fields = {
        (name, field)
        for name, schema in generated()["components"]["schemas"].items()
        for field in schema.get("properties", {})
    }
    forbidden = {"is_fraud", "fraud_score", "password_hash", "credit_score", "estimated_monthly_income"}
    assert {item for item in fields if item[1] in forbidden} == set()
    # The document number is something the customer sends to sign in with the agent's login, never something we return.
    assert {name for name, field in fields if field == "document_number"} <= {"SessionRequest"}
