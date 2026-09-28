"""Table specs for the S3 -> data.bronze.* ingestion task.

Column lists match data/dbt/models/staging/stg_*.sql exactly (bronze.* columns
are all text — casts happen once, in silver, not here). See
spec/DATA_FINDINGS.md for the data-quality context behind these tables.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: list[str]
    # Non-partitioned tables live at data/<name>.csv in the bucket.
    # Partitioned tables live at data/<name>/year=YYYY/month=MM/day=DD/<name>_YYYYMMDD.csv
    partitioned: bool


CUSTOMERS = TableSpec(
    name="customers",
    partitioned=False,
    columns=[
        "customer_id", "document_number", "document_type", "first_name", "last_name",
        "date_of_birth", "gender", "email", "mobile_phone", "landline_phone", "address",
        "city", "state", "country", "postal_code", "detected_accent", "segment",
        "credit_score", "estimated_monthly_income", "occupation", "marital_status",
        "education_level", "registration_date", "registration_branch_id",
        "customer_status", "last_updated", "accepts_marketing",
    ],
)

PRODUCTS = TableSpec(
    name="products",
    partitioned=False,
    columns=[
        "product_id", "customer_id", "product_type", "product_number", "currency",
        "current_balance", "credit_limit", "interest_rate", "opening_date",
        "expiration_date", "opening_branch_id", "product_status", "opening_channel",
        "has_linked_app", "days_past_due", "last_transaction_date", "last_updated",
    ],
)

TRANSACTIONS = TableSpec(
    name="transactions",
    partitioned=True,
    columns=[
        "transaction_id", "transaction_date", "process_date", "product_id", "customer_id",
        "transaction_type", "transaction_category", "amount", "currency", "amount_usd",
        "channel", "branch_id", "merchant_name", "merchant_category", "transaction_country",
        "transaction_city", "transaction_status", "response_code", "is_fraud",
        "fraud_score", "latitude", "longitude",
    ],
)

COMPLAINTS = TableSpec(
    name="complaints",
    partitioned=True,
    columns=[
        "complaint_id", "creation_date", "process_date", "customer_id", "case_type",
        "category", "subcategory", "reception_channel", "affected_product_id",
        "related_branch_id", "origin_interaction_id", "description", "claimed_amount",
        "currency", "priority", "status", "assigned_agent_id", "assignment_date",
        "first_response_date", "resolution_date", "closing_date", "sla_breached",
        "resolution_days", "resolution", "compensation_granted",
        "resolution_satisfaction", "is_repeat_complainer",
    ],
)

CALL_CENTER_INTERACTIONS = TableSpec(
    name="call_center_interactions",
    partitioned=True,
    columns=[
        "interaction_id", "interaction_date", "process_date", "customer_id", "agent_id",
        "interaction_type", "channel", "contact_reason", "reason_category",
        "duration_seconds", "wait_time_seconds", "was_resolved", "requires_followup",
        "detected_sentiment", "sentiment_score", "customer_detected_accent",
        "agent_used_accent", "was_escalated", "mentioned_products", "has_transcript",
        "has_recording",
    ],
)

ALL_TABLES = [CUSTOMERS, PRODUCTS, TRANSACTIONS, COMPLAINTS, CALL_CENTER_INTERACTIONS]
