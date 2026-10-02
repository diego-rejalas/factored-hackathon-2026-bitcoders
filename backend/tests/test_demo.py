from pathlib import Path

import pytest

from app import demo
from app.demo import DEMO_CUSTOMERS, seed_demo_accounts, username_for
from app.passwords import verify_password
from tests.fakes import CUS_A, CUS_B, FakeStore


def test_user_names_have_no_accents_spaces_or_capitals():
    assert username_for("María José", "Núñez de la Peña") == "mariajose.nunezdelapena"
    assert username_for("Ana", "García") == "ana.garcia"


@pytest.mark.anyio
async def test_seeding_creates_the_accounts_of_customers_that_exist_and_skips_the_rest(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(demo, "DEMO_CUSTOMERS", [(CUS_A, "Escala", "h1"), (CUS_B, "Resuelve", "h2"), ("CLI-NOT-IN-GOLD", "x", "y")])
    store.credentials.clear()
    names = await seed_demo_accounts(store, "Demo-2026")
    assert names == ["ana.garcia", "bruno.souza"]
    row = store.credentials["ana.garcia"]
    assert row["demo_label"] == "Escala" and verify_password(row["password_hash"], "Demo-2026")
    assert "Demo-2026" not in str(store.credentials)  # only the hash is stored


@pytest.mark.anyio
async def test_seeding_twice_refreshes_instead_of_failing(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(demo, "DEMO_CUSTOMERS", [(CUS_A, "Escala", "h1")])
    await seed_demo_accounts(store, "primera")
    await seed_demo_accounts(store, "segunda")
    assert verify_password(store.credentials["ana.garcia"]["password_hash"], "segunda")


def test_the_demo_customers_are_the_ones_e2e_checks():
    e2e = Path(__file__).parents[2] / "infra/gcp/scripts/e2e.py"
    if not e2e.exists():  # inside the CI image only backend/app and backend/tests are copied
        pytest.skip("e2e.py is not in this checkout")
    assert all(customer_id in e2e.read_text() for customer_id, _, _ in DEMO_CUSTOMERS)
