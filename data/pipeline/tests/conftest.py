import os
from pathlib import Path

import pytest

from latam_pipeline.config import Settings


def write_csv(path: Path, header: str, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n" + "\n".join(rows) + "\n")


@pytest.fixture()
def source(tmp_path):
    """A tiny copy of the organizer's layout: one flat table and one hive-partitioned table."""
    root = tmp_path / "source"
    write_csv(root / "data" / "branches.csv", "branch_id,city", ["B1,Lima", "B2,Quito", "B3,"])
    for day, rows in (("01", ["T1,10.5", "T2,20"]), ("02", ["T3,30"])):
        write_csv(
            root / "data" / "transactions" / "year=2026" / "month=01" / f"day={day}" / f"transactions_202601{day}.csv",
            "transaction_id,amount",
            rows,
        )
    return root


@pytest.fixture()
def settings(tmp_path, source):
    return Settings(
        source_root=str(source),
        db_path=str(tmp_path / "work" / "latam.duckdb"),
        work_dir=str(tmp_path / "work"),
        threads=2,
        memory_limit="1GB",
    )


@pytest.fixture()
def pg_env(monkeypatch):
    """Connection to a throwaway Postgres for the integration tests; skipped when none is configured."""
    host = os.environ.get("PG_TEST_HOST")
    if not host:
        pytest.skip("set PG_TEST_HOST (and PG_TEST_PORT/USER/PASSWORD/DATABASE) to run the Postgres tests")
    monkeypatch.setenv("PG_HOST", host)
    monkeypatch.setenv("PG_PORT", os.environ.get("PG_TEST_PORT", "5432"))
    monkeypatch.setenv("PG_USER", os.environ.get("PG_TEST_USER", "postgres"))
    monkeypatch.setenv("PG_PASSWORD", os.environ.get("PG_TEST_PASSWORD", "pw"))
    monkeypatch.setenv("PG_DATABASE", os.environ.get("PG_TEST_DATABASE", "data"))
