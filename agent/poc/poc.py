"""Smallest possible PydanticAI proof of concept: one LLM, one tool, no guardrail.

The tool returns a few sample transactions from a local list (no database, no
backend). It only proves the wiring: LLM through OpenRouter -> tool call -> answer.

Run (uv installs everything from pyproject.toml / uv.lock):
    cp .env.example .env        # then set OPENROUTER_API_KEY
    uv run poc.py "Intente una transferencia de unos 4000 dolares, me la cobraron?"
"""
import os
import sys

from dotenv import load_dotenv
from pydantic_ai import Agent

load_dotenv()

# Sample customer data, taken from the shape of gold.transactions (synthetic dataset).
TRANSACTIONS = [
    {"id": "TRX-001", "date": "2026-05-09", "type": "Transfer", "amount": 6783.64, "currency": "USD", "status": "Approved", "response_code": "00"},
    {"id": "TRX-002", "date": "2026-05-11", "type": "Transfer", "amount": 4189.18, "currency": "USD", "status": "Declined", "response_code": "54"},
    {"id": "TRX-003", "date": "2026-05-17", "type": "Withdrawal", "amount": 391.25, "currency": "USD", "status": "Approved", "response_code": "00"},
    {"id": "TRX-004", "date": "2026-05-25", "type": "Payment", "amount": 1075.66, "currency": "USD", "status": "Approved", "response_code": "00"},
]

MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-haiku-4.5")

agent = Agent(
    f"openrouter:{MODEL}",
    instructions=(
        "You are a bank customer-service assistant for transaction questions. "
        "Use the tool to look at the customer's recent transactions before answering. "
        "Answer in the customer's language (Spanish or Portuguese). Be brief. "
        "Response code 54 means expired card, 51 insufficient funds, 14 invalid card number, 05 not authorized."
    ),
)


@agent.tool_plain
def get_recent_transactions() -> list[dict]:
    """Return the customer's recent transactions."""
    return TRANSACTIONS


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Intente una transferencia de unos 4000 dolares, me la cobraron?"
    result = agent.run_sync(question)
    print(result.output)
