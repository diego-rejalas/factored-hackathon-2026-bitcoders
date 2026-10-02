"""Command line: run the whole pipeline in order (what the Cloud Run job does) or one stage.

    python -m latam_pipeline all
    python -m latam_pipeline extract | export-bronze | dbt | export-silver | publish | docs
"""
import sys
import uuid

from . import stages
from .config import Settings, utcnow


def run_all(settings: Settings) -> int:
    run_id = uuid.uuid4().hex
    started = utcnow()
    stages.log(f"starting pipeline (run_id: {run_id[:8]})")
    detail: dict = {"publish_schema": settings.publish_schema, "lake_storage_uri": settings.lake_uri or "disabled"}
    status = "failed"
    try:
        detail["bronze_rows"] = stages.extract_bronze(settings)
        if settings.lake_uri:
            detail["lakehouse_bronze"] = stages.export_bronze(settings)
        detail["dbt"] = stages.dbt_build(settings)
        if settings.lake_uri:
            detail["lakehouse_silver"] = stages.export_silver(settings)
        detail["published_rows"] = stages.publish_gold(settings, run_id)
        status = "success"
        # Documentation is a by-product: the data is already published, so a failure here is reported
        # in the run's detail and does not turn the run into a failed one.
        try:
            detail["docs"] = stages.dbt_docs(settings, run_id)
        except Exception as exc:  # noqa: BLE001
            detail["docs"] = {"error": stages.scrub(f"{type(exc).__name__}: {exc}")[:400]}
            stages.log(f"documentation failed (the run is not affected): {detail['docs']['error']}")
    except Exception as exc:  # noqa: BLE001
        detail["error"] = stages.scrub(f"{type(exc).__name__}: {exc}")[:800]
        stages.log(f"FAILED: {detail['error']}")
    finally:
        stages.record_run(run_id, started, status, detail)
    stages.log(f"pipeline finished with status: {status}")
    return 0 if status == "success" else 1


def main(argv: list | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    command = args[0] if args else "all"
    settings = Settings.from_env()
    if command == "all":
        return run_all(settings)
    single = {
        "extract": lambda: stages.extract_bronze(settings),
        "export-bronze": lambda: stages.export_bronze(settings),
        "dbt": lambda: stages.dbt_build(settings),
        "export-silver": lambda: stages.export_silver(settings),
        "publish": lambda: stages.publish_gold(settings, uuid.uuid4().hex),
        "docs": lambda: stages.dbt_docs(settings, uuid.uuid4().hex),
    }
    if command not in single:
        print(f"unknown command {command!r}; use all or one of: {', '.join(single)}", file=sys.stderr)
        return 2
    single[command]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
