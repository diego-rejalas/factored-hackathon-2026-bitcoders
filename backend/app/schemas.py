"""Response models. The agent's tools are typed against these, so they are the contract."""
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: str


class TableCount(BaseModel):
    table: str
    rows: int


class LastRun(BaseModel):
    run_id: str
    status: str
    started_at: datetime
    finished_at: datetime


class DataMeta(BaseModel):
    """What the gold layer holds and when the pipeline last succeeded."""

    gold: list[TableCount]
    last_successful_run: LastRun | None


# --------------------------------------------------------------------------------------------- v1 contract
# Money is a float in the JSON (the database has numeric, which pydantic would otherwise write as a string).


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class Customer(BaseModel):
    customer_id: str
    first_name: str
    last_name: str
    country: str | None = None


class LoginResponse(BaseModel):
    session_token: str
    token_type: str
    expires_in: int
    customer: Customer


class DemoAccount(BaseModel):
    username: str
    label: str
    hint: str | None = None
    first_name: str
    country: str | None = None


class DemoAccounts(BaseModel):
    """The accounts listed on the sign-in page. Their shared password is public by design: it is a demo."""

    accounts: list[DemoAccount]
    password: str | None = None


class Product(BaseModel):
    product_id: str
    product_type: str
    kind: str = Field(description="deposit, credit or other. For credit the balance is what is owed (inferred).")
    product_number_masked: str
    currency: str
    current_balance: float | None = None
    credit_limit: float | None = None
    interest_rate: float | None = None
    opening_date: date | None = None
    product_status: str
    days_past_due: int | None = None
    last_transaction_date: datetime | None = None


class Transaction(BaseModel):
    transaction_id: str
    transaction_date: datetime
    process_date: date | None = None
    product_id: str | None = None
    transaction_type: str | None = None
    transaction_category: str | None = None
    amount: float
    currency: str
    amount_usd_effective: float | None = None
    channel: str | None = None
    merchant_name: str | None = None
    merchant_category: str | None = None
    transaction_country: str | None = None
    transaction_city: str | None = None
    transaction_status: str
    response_code: str | None = None
    response_meaning: dict[str, str] | None = Field(
        default=None,
        description="Standard (ISO 8583) meaning of response_code, as {es, pt}. An assumption: the organizer does not define the codes. Null when the code is empty or unknown.",
    )
    case_id: UUID | None = Field(default=None, description="Set when the transaction already has a dispute case.")
    dispute_status: str | None = None


class TransactionPage(BaseModel):
    items: list[Transaction]
    next_cursor: str | None = Field(default=None, description="Pass it as ?cursor= to get the next page.")


class Balance(BaseModel):
    currency: str
    kind: str
    total: float | None = None
    products: int


class Summary(BaseModel):
    balances: list[Balance]
    recent_transactions: list[Transaction]
    disputes: dict[str, int] = Field(description="Active cases by status.")


class DisputeEvent(BaseModel):
    event: str
    payload: dict
    ts: datetime


class Dispute(BaseModel):
    """A case. status: open (in progress), auto_resolved (the policy resolved it), escalated (a person has it) or closed."""

    case_id: UUID
    customer_id: str
    transaction_id: str
    reason_code: str
    summary: str
    status: str
    evidence: dict = Field(description="The transaction as it was, plus resolution (auto_resolved) or handoff (escalated).")
    created_at: datetime
    resolved_at: datetime | None = None


class DisputeDetail(Dispute):
    events: list[DisputeEvent] = Field(description="Append-only timeline: created, then resolved or escalated.")
