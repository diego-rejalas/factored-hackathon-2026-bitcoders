"""Settings and the table catalog shared by every stage."""
import datetime as dt
import hashlib
import os
from dataclasses import dataclass, field

# data/<name>.csv
FLAT = ["customers", "products", "branches", "service_agents", "marketing_campaigns", "daily_exchange_rates"]
# data/<name>/year=YYYY/month=MM/day=DD/<name>_YYYYMMDD.csv
PARTITIONED = [
    "transactions",
    "complaints",
    "call_center_interactions",
    "call_transcripts",
    "satisfaction_surveys",
    "campaign_sends",
    "digital_events",
]
ALL_TABLES = FLAT + PARTITIONED

# Published tables: the key is unique; the indexes support the backend's queries.
GOLD = {
    "customers": {"key": ["customer_id"], "indexes": [["document_number"]]},
    "products": {"key": ["product_id"], "indexes": [["customer_id"]]},
    "transactions": {
        "key": ["transaction_id"],
        "indexes": [["customer_id", "transaction_date"], ["product_id"]],
    },
    "complaints": {"key": ["complaint_id"], "indexes": [["customer_id"]]},
    "call_center_interactions": {"key": ["interaction_id"], "indexes": [["customer_id"]]},
}

SECRET_ENV_NAMES = ("PG_PASSWORD", "LATAM_BANK_AWS_SECRET_ACCESS_KEY", "LATAM_BANK_AWS_ACCESS_KEY_ID")


def short_id(run_id: str) -> str:
    """Eight hex characters that differ between runs.

    The old code used run_id[:8]. Airflow run ids start with 'manual__' or 'scheduled__', so every
    run produced the same suffix and the second run's index names collided with the first's.
    """
    return hashlib.sha1(run_id.encode()).hexdigest()[:8]


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


@dataclass(frozen=True)
class Settings:
    bucket: str = "factored-datathon-2026-s3-157725502942-us-east-2-an"
    # Where the CSVs are read from. s3://<bucket> in production; a local directory in tests.
    source_root: str = ""
    db_path: str = "/tmp/latam.duckdb"
    dbt_dir: str = "/app/dbt"
    dbt_bin: str = "dbt"  # the Airflow image points this at an isolated virtualenv
    dbt_target: str = ""  # empty means the profile's default target
    publish_schema: str = "gold"
    threads: int = 4
    memory_limit: str = "8GB"
    lake_uri: str = ""
    aws_region: str = "us-east-2"
    # Postgres roles that may read the published gold schema, comma separated. Empty grants nothing.
    gold_reader_roles: tuple = field(default_factory=tuple)
    work_dir: str = "/tmp"

    @property
    def source(self) -> str:
        return (self.source_root or f"s3://{self.bucket}").rstrip("/")

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        env = os.environ
        roles = tuple(r.strip() for r in env.get("GOLD_READER_ROLES", "").split(",") if r.strip())
        values = dict(
            bucket=env.get("LATAM_BANK_S3_BUCKET", cls.bucket),
            source_root=env.get("SOURCE_ROOT", ""),
            db_path=env.get("DUCKDB_PATH", cls.db_path),
            dbt_dir=env.get("DBT_DIR", cls.dbt_dir),
            dbt_bin=env.get("DBT_BIN", cls.dbt_bin),
            dbt_target=env.get("DBT_TARGET_NAME", ""),
            publish_schema=env.get("PUBLISH_SCHEMA", cls.publish_schema),
            threads=int(env.get("DUCKDB_THREADS", cls.threads)),
            memory_limit=env.get("DUCKDB_MEMORY_LIMIT", cls.memory_limit),
            lake_uri=env.get("LAKE_STORAGE_URI", "").rstrip("/"),
            aws_region=env.get("AWS_REGION", cls.aws_region),
            gold_reader_roles=roles,
            work_dir=env.get("PIPELINE_WORK_DIR", cls.work_dir),
        )
        values.update(overrides)
        return cls(**values)
