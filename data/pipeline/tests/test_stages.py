import datetime as dt

import duckdb
import pytest

from latam_pipeline import stages
from latam_pipeline.config import short_id


def test_short_id_differs_between_airflow_run_ids():
    # The old run_id[:8] gave "manual__" for both, so the second run's index names collided.
    a, b = "manual__2026-10-02T01:00:00+00:00", "manual__2026-10-02T02:00:00+00:00"
    assert a[:8] == b[:8]
    assert short_id(a) != short_id(b)
    assert len(short_id(a)) == 8 and short_id(a) == short_id(a)


def test_parse_dbt_summary():
    out = "noise\n02:01:51  Done. PASS=170 WARN=6 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=176\n"
    assert stages.parse_dbt_summary(out) == {"pass": 170, "warn": 6, "error": 0, "skip": 0}
    assert stages.parse_dbt_summary("nothing") == {"pass": 0, "warn": 0, "error": 0, "skip": 0}


def test_scrub_hides_secrets(monkeypatch):
    monkeypatch.setenv("PG_PASSWORD", "s3cr3t-value")
    assert stages.scrub("connect password=s3cr3t-value ok") == "connect password=*** ok"


def test_extract_loads_flat_and_partitioned_tables_as_text_with_lineage(settings):
    counts = stages.extract_bronze(settings, tables=["branches", "transactions"])
    assert counts == {"branches": 3, "transactions": 3}

    con = duckdb.connect(settings.db_path, read_only=True)
    types = {r[0]: r[1] for r in con.execute("describe bronze.transactions").fetchall()}
    assert types["amount"] == "VARCHAR"  # bronze keeps everything as text
    assert {"_source_key", "_ingested_at"} <= set(types)
    keys = {r[0] for r in con.execute("select distinct _source_key from bronze.transactions").fetchall()}
    assert len(keys) == 2 and all(k.endswith(".csv") for k in keys)
    # hive partition columns are kept as the source writes them (DuckDB types year as an integer);
    # changing that would change the lakehouse folder layout (month=1 vs month=01)
    assert [tuple(str(v) for v in r) for r in con.execute("select distinct year, month, day from bronze.transactions order by day").fetchall()] == [("2026", "01", "01"), ("2026", "01", "02")]
    con.close()


def test_extract_is_a_full_reload_not_an_accumulation(settings):
    stages.extract_bronze(settings, tables=["branches"])
    stages.extract_bronze(settings, tables=["branches"])
    con = duckdb.connect(settings.db_path, read_only=True)
    assert con.execute("select count(*) from bronze.branches").fetchone()[0] == 3
    con.close()


def test_extract_fails_loudly_when_nothing_matches(tmp_path, settings):
    empty = tmp_path / "empty"
    (empty / "data").mkdir(parents=True)
    (empty / "data" / "branches.csv").write_text("branch_id,city\n")
    bad = type(settings)(**{**settings.__dict__, "source_root": str(empty)})
    with pytest.raises(RuntimeError, match="empty"):
        stages.extract_bronze(bad, tables=["branches"])


def test_extract_from_s3_requires_credentials(monkeypatch, settings):
    monkeypatch.delenv("LATAM_BANK_AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("LATAM_BANK_AWS_SECRET_ACCESS_KEY", raising=False)
    s3 = type(settings)(**{**settings.__dict__, "source_root": ""})  # falls back to s3://<bucket>
    with pytest.raises(RuntimeError, match="Missing S3 credentials"):
        stages.extract_bronze(s3, tables=["branches"])


def test_export_writes_parquet_per_layer_and_skips_without_a_lake(tmp_path, settings, monkeypatch):
    monkeypatch.setattr(stages, "ALL_TABLES", ["branches", "transactions"])
    stages.extract_bronze(settings, tables=["branches", "transactions"])
    assert stages.export_bronze(settings) == {}  # no lake configured: nothing happens

    lake = tmp_path / "lake"
    with_lake = type(settings)(**{**settings.__dict__, "lake_uri": str(lake)})
    assert stages.export_bronze(with_lake) == {"branches": 3, "transactions": 3}
    assert (lake / "bronze" / "branches" / "branches.parquet").exists()
    assert list((lake / "bronze" / "transactions").rglob("*.parquet"))

    con = duckdb.connect(settings.db_path)  # silver export reads silver.stg_*; build a minimal one
    con.execute("create schema silver")
    con.execute("create table silver.stg_branches as select * from bronze.branches")
    con.execute("create table silver.stg_transactions as select *, date '2026-01-01' as process_date from bronze.transactions")
    con.close()
    assert stages.export_silver(with_lake) == {"branches": 3, "transactions": 3}
    assert list((lake / "silver" / "transactions").rglob("*.parquet"))


def test_grant_rejects_a_role_name_that_could_inject_sql():
    with pytest.raises(ValueError):
        stages._grant_read(None, "gold", "x; drop schema gold")


def test_record_run_is_best_effort_without_a_database(monkeypatch):
    monkeypatch.delenv("PG_HOST", raising=False)
    stages.record_run("r1", dt.datetime.now(dt.timezone.utc), "success", {})  # must not raise
