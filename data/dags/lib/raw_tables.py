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
    # Natural PK columns. Defaults to (columns[0],) when omitted — set
    # explicitly for tables with a composite key (e.g. daily_exchange_rates
    # has no single-column identity).
    pk: tuple[str, ...] | None = None

    @property
    def pk_columns(self) -> tuple[str, ...]:
        return self.pk if self.pk is not None else (self.columns[0],)


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

BRANCHES = TableSpec(
    name="branches",
    partitioned=False,
    columns=[
        "branch_id", "branch_code", "branch_name", "branch_type", "address", "city",
        "state", "country", "postal_code", "geographic_zone", "phone", "email",
        "opening_time", "closing_time", "has_atms", "atm_count", "has_teller_windows",
        "teller_window_count", "latitude", "longitude", "branch_opening_date",
        "branch_status",
    ],
)

SERVICE_AGENTS = TableSpec(
    name="service_agents",
    partitioned=False,
    columns=[
        "agent_id", "employee_code", "first_name", "last_name", "email", "phone",
        "native_accent", "country_of_origin", "assigned_branch_id", "agent_type",
        "experience_level", "languages", "specialty", "hire_date", "avg_csat",
        "total_monthly_interactions", "agent_status", "work_shift",
    ],
)

MARKETING_CAMPAIGNS = TableSpec(
    name="marketing_campaigns",
    partitioned=False,
    columns=[
        "campaign_id", "campaign_name", "description", "campaign_type",
        "campaign_objective", "promoted_product", "target_segment", "target_country",
        "start_date", "end_date", "budget", "campaign_status", "expected_conversion_rate",
    ],
)

DAILY_EXCHANGE_RATES = TableSpec(
    name="daily_exchange_rates",
    partitioned=False,
    columns=[
        "date", "source_currency", "target_currency", "exchange_rate", "buy_rate",
        "sell_rate", "source",
    ],
    pk=("date", "source_currency", "target_currency"),
)

CALL_TRANSCRIPTS = TableSpec(
    name="call_transcripts",
    partitioned=True,
    columns=[
        "transcript_id", "interaction_id", "process_date", "customer_id", "agent_id",
        "full_text", "customer_text", "agent_text", "detected_language", "detected_accent",
        "accent_confidence", "detected_keywords", "mentioned_entities", "detected_intents",
        "main_topics", "transcription_model", "audio_quality", "duration_seconds",
    ],
)

SATISFACTION_SURVEYS = TableSpec(
    name="satisfaction_surveys",
    partitioned=True,
    columns=[
        "survey_id", "survey_date", "process_date", "interaction_id", "customer_id",
        "agent_id", "survey_type", "send_channel", "main_score", "nps_category",
        "question_1_text", "question_1_response", "question_2_text", "question_2_response",
        "question_3_text", "question_3_response", "open_comments", "comment_sentiment",
        "response_time_hours", "campaign_response_rate",
    ],
)

CAMPAIGN_SENDS = TableSpec(
    name="campaign_sends",
    partitioned=True,
    columns=[
        "send_id", "send_date", "process_date", "campaign_id", "customer_id",
        "send_channel", "template_used", "subject", "send_status", "was_delivered",
        "was_opened", "open_date", "was_clicked", "click_date", "click_count",
        "had_conversion", "conversion_date", "conversion_value", "open_device",
        "open_country", "failure_reason", "send_cost",
    ],
)

DIGITAL_EVENTS = TableSpec(
    name="digital_events",
    partitioned=True,
    columns=[
        "event_id", "event_date", "process_date", "customer_id", "session_id",
        "event_type", "event_category", "channel", "platform", "browser",
        "app_version", "page_url", "page_title", "action", "element_id", "product_id",
        "event_value", "duration_seconds", "ip_address", "ip_country", "ip_city",
        "is_mobile", "referrer", "utm_source", "utm_medium", "utm_campaign",
    ],
)

ALL_TABLES = [
    CUSTOMERS, PRODUCTS, TRANSACTIONS, COMPLAINTS, CALL_CENTER_INTERACTIONS,
    BRANCHES, SERVICE_AGENTS, MARKETING_CAMPAIGNS, DAILY_EXCHANGE_RATES,
    CALL_TRANSCRIPTS, SATISFACTION_SURVEYS, CAMPAIGN_SENDS, DIGITAL_EVENTS,
]
