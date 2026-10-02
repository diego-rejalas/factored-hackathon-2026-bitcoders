"""Integration tests against a real Postgres: set PG_TEST_HOST (see conftest)."""
import datetime as dt

import duckdb
import psycopg2
import pytest

from latam_pipeline import stages
from latam_pipeline.config import GOLD, Settings


@pytest.fixture()
def gold_db(tmp_path):
    """A DuckDB file with the five gold tables, as dbt would leave it."""
    # not named gold.duckdb: DuckDB names the catalog after the file, which would clash with schema gold
    path = tmp_path / "warehouse.duckdb"
    con = duckdb.connect(str(path))
    con.execute("create schema gold")
    columns = {
        "customers": "customer_id varchar, document_number varchar",
        "products": "product_id varchar, customer_id varchar",
        "transactions": "transaction_id varchar, customer_id varchar, transaction_date date, product_id varchar",
        "complaints": "complaint_id varchar, customer_id varchar",
        "call_center_interactions": "interaction_id varchar, customer_id varchar",
    }
    for table, cols in columns.items():
        con.execute(f"create table gold.{table} ({cols})")
        n = len(cols.split(","))
        con.execute(f"insert into gold.{table} select " + ", ".join(
            ["'k' || i::varchar" if c.strip().endswith("varchar") else "date '2026-01-01'" for c in cols.split(",")]
        ) + " from range(50) t(i)")
    con.close()
    return str(path)


def pg_query(sql, args=None):
    import os

    con = psycopg2.connect(host=os.environ["PG_HOST"], port=os.environ["PG_PORT"], user=os.environ["PG_USER"],
                           password=os.environ["PG_PASSWORD"], dbname=os.environ["PG_DATABASE"])
    con.autocommit = True
    cur = con.cursor()
    cur.execute(sql, args)
    rows = cur.fetchall() if cur.description else []
    con.close()
    return rows


def test_publish_swaps_all_gold_tables_and_survives_a_second_airflow_run(pg_env, gold_db, tmp_path):
    settings = Settings(db_path=gold_db, work_dir=str(tmp_path))
    pg_query("drop schema if exists gold cascade; drop schema if exists bronze cascade; create schema bronze")

    first = stages.publish_gold(settings, "manual__2026-10-02T01:00:00+00:00")
    assert first == {t: 50 for t in GOLD}
    # both runs share the first eight characters of the id; with the old suffix this second call failed
    second = stages.publish_gold(settings, "manual__2026-10-02T02:00:00+00:00")
    assert second == first

    assert pg_query("select count(*) from gold.transactions")[0][0] == 50
    leftovers = pg_query("select table_name from information_schema.tables where table_schema='gold' and (table_name like '%\\_\\_new' or table_name like '%\\_\\_old')")
    assert leftovers == []
    assert pg_query("select count(*) from pg_namespace where nspname='bronze'")[0][0] == 0  # purged
    assert pg_query("select count(*) from pg_indexes where schemaname='gold' and tablename='transactions'")[0][0] == 3


def test_publish_grants_read_only_to_configured_roles(pg_env, gold_db, tmp_path):
    pg_query("do $$ begin if not exists (select 1 from pg_roles where rolname='latam_reader') then create role latam_reader; end if; end $$")
    settings = Settings(db_path=gold_db, work_dir=str(tmp_path), gold_reader_roles=("latam_reader", "role_that_does_not_exist"))
    stages.publish_gold(settings, "grant-run")
    assert pg_query("select has_table_privilege('latam_reader','gold.customers','SELECT')")[0][0] is True
    assert pg_query("select has_table_privilege('latam_reader','gold.customers','INSERT')")[0][0] is False


def test_record_run_upserts_by_run_id(pg_env):
    pg_query("drop table if exists ops.etl_runs")
    started = dt.datetime.now(dt.timezone.utc)
    stages.record_run("run-1", started, "failed", {"error": "x"})
    stages.record_run("run-1", started, "success", {"rows": 1})
    rows = pg_query("select run_id, status from ops.etl_runs where run_id='run-1'")
    assert rows == [("run-1", "success")]
