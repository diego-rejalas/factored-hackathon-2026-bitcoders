"""PydanticAI proof of concept with custom tools backed by fixed SQL.

The LLM never writes SQL. It only chooses a tool and passes a parameter (the customer id).
Each tool runs a fixed, parameterized query written here, with a role (`agent_poc_ro`) that can
only SELECT from `gold.*`, in a read-only session with a 10 s timeout. The tools return only the
columns the agent needs (no document number, email or phone).

POC shortcut: the production design has the agent call the backend over HTTP, where the session
and customer ownership are enforced, instead of connecting to the database.

Run:
    uv run customer_tools_poc.py "Busca al cliente CLI-00MT1OY089RA y dime sus ultimas transacciones"
"""
import os
import re
import sys
from datetime import date, datetime
from decimal import Decimal

import psycopg
from dotenv import load_dotenv
from pydantic_ai import Agent

load_dotenv()

MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-haiku-4.5")
CUSTOMER_ID = re.compile(r"^CLI-[A-Z0-9]{12}$")

FIND_CUSTOMER_SQL = """
    select customer_id, first_name, last_name, country, segment, customer_status
    from gold.customers
    where customer_id = %s
"""

CUSTOMER_TRANSACTIONS_SQL = """
    select transaction_id, transaction_date, product_id, transaction_type, transaction_category,
           amount, currency, transaction_status, response_code, merchant_name, channel
    from gold.transactions
    where customer_id = %s
    order by transaction_date desc
    limit %s
"""


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ["PG_RO_HOST"],
        port=os.environ["PG_RO_PORT"],
        dbname=os.environ["PG_RO_DATABASE"],
        user=os.environ["PG_RO_USER"],
        password=os.environ["PG_RO_PASSWORD"],
        connect_timeout=10,
    )


def jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def query(sql: str, params: tuple) -> list[dict]:
    with connect() as conn:
        cur = conn.execute(sql, params)
        names = [d.name for d in cur.description]
        return [{n: jsonable(v) for n, v in zip(names, row)} for row in cur.fetchall()]


agent = Agent(
    f"openrouter:{MODEL}",
    instructions=(
        "You are a bank customer-service assistant. Use the tools to look up the customer the user "
        "asks about, then answer from the tool results only; never invent data. "
        "Answer in the user's language (Spanish or Portuguese), briefly. "
        "Response code 54 = expired card, 51 = insufficient funds, 14 = invalid card number, 05 = not authorized."
    ),
)


@agent.tool_plain
def find_customer(customer_id: str) -> dict | str:
    """Look up a customer by id (format CLI- followed by 12 letters or digits)."""
    if not CUSTOMER_ID.match(customer_id):
        return "Invalid customer id format."
    rows = query(FIND_CUSTOMER_SQL, (customer_id,))
    return rows[0] if rows else "Customer not found."


@agent.tool_plain
def get_customer_transactions(customer_id: str, limit: int = 10) -> list[dict] | str:
    """Return the most recent transactions of a customer, newest first (limit 1 to 50)."""
    if not CUSTOMER_ID.match(customer_id):
        return "Invalid customer id format."
    return query(CUSTOMER_TRANSACTIONS_SQL, (customer_id, max(1, min(limit, 50))))


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Busca al cliente CLI-00MT1OY089RA y dime sus ultimas transacciones"
    result = agent.run_sync(question)
    for message in result.all_messages():
        for part in message.parts:
            if type(part).__name__ == "ToolCallPart":
                print(f"[tool call] {part.tool_name} {part.args}")
    print(result.output)
