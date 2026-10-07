import os
from dataclasses import dataclass


def _csv(name: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    project_id: str
    sql_instance: str
    # Cloud Run services whose traffic counts as "someone is using the demo".
    watch_services: list[str]
    idle_minutes: int
    # Airflow VM name and zone. While the VM runs, a pipeline may be using the database, so it never sleeps.
    airflow_vm: str
    airflow_zone: str
    cors_origins: list[str]
    # Cloud Scheduler calls /sleep-if-idle with an ID token for this audience, signed for this service account.
    scheduler_sa: str
    scheduler_audience: str
    status_cache_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            project_id=os.environ["PROJECT_ID"],
            sql_instance=os.environ["SQL_INSTANCE"],
            watch_services=_csv("WATCH_SERVICES"),
            idle_minutes=int(os.environ.get("IDLE_MINUTES", "30")),
            airflow_vm=os.environ.get("AIRFLOW_VM", ""),
            airflow_zone=os.environ.get("AIRFLOW_ZONE", ""),
            cors_origins=_csv("CORS_ALLOWED_ORIGINS"),
            scheduler_sa=os.environ.get("SCHEDULER_SA", ""),
            scheduler_audience=os.environ.get("SCHEDULER_AUDIENCE", ""),
            status_cache_seconds=float(os.environ.get("STATUS_CACHE_SECONDS", "5")),
        )
