"""Demonstration accounts: customers of the synthetic dataset that each exercise one path of the dispute policy.

Seeded at startup when DEMO_ACCOUNTS_ENABLED=true and DEMO_PASSWORD is set (see main.py). The password is shared and
public by design: the data is synthetic and the sign-in page lists these accounts for whoever evaluates the demo.
The customers are the ones infra/gcp/scripts/e2e.py checks the agent with, so what each one shows is verified.
"""

import re
import unicodedata

from app.passwords import hash_password

DEMO_CUSTOMERS = [
    # (customer_id, label, what it shows)
    ("CLI-00MT1OY089RA", "Escala por monto",
     "Un rechazo de USD 4.189 (sobre el umbral de USD 500), un reverso y un cobro aprobado: el asistente escala a una persona."),
    ("CLI-0064RNKCVQCN", "Se resuelve solo",
     "Un rechazo de USD 256, bajo el umbral: el asistente explica el rechazo y cierra el caso."),
    ("CLI-00232W4ZDQPP", "Se resuelve solo (reverso)",
     "Un reverso de USD 389, bajo el umbral: el asistente confirma que no hubo cobro y cierra el caso."),
]


def username_for(first_name: str, last_name: str) -> str:
    """ana.garcia: lowercase, without accents or spaces."""
    def clean(text: str) -> str:
        folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "", folded.lower())

    return f"{clean(first_name)}.{clean(last_name)}"


async def seed_demo_accounts(store, password: str) -> list[str]:
    """Create or refresh the demo accounts. Returns the user names. A customer that is not in gold is skipped."""
    customers = await store.get_customer_names([c[0] for c in DEMO_CUSTOMERS])
    password_hash = hash_password(password)
    created: list[str] = []
    for customer_id, label, hint in DEMO_CUSTOMERS:
        customer = customers.get(customer_id)
        if customer is None:
            continue
        username = username_for(customer["first_name"], customer["last_name"])
        await store.upsert_credentials(customer_id, username, password_hash, demo_label=label, demo_hint=hint)
        created.append(username)
    return created
