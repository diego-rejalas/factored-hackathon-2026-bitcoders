"""Versioned SQL migrations: app/migrations/NNNN_name.sql, applied in order, each in its own transaction."""

from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
# Two instances starting together must not run the same migration twice.
LOCK_KEY = 727_274


async def apply_migrations(conn: asyncpg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every migration not yet recorded in app.schema_migrations. Returns the versions it ran."""
    await conn.execute("create schema if not exists app")
    await conn.execute(
        """
        create table if not exists app.schema_migrations (
            version text primary key,
            applied_at timestamptz not null default now()
        )
        """
    )
    await conn.execute("select pg_advisory_lock($1)", LOCK_KEY)
    try:
        applied = {row["version"] for row in await conn.fetch("select version from app.schema_migrations")}
        ran: list[str] = []
        for path in sorted(directory.glob("*.sql")):
            if path.stem in applied:
                continue
            async with conn.transaction():
                await conn.execute(path.read_text())
                await conn.execute("insert into app.schema_migrations (version) values ($1)", path.stem)
            ran.append(path.stem)
        return ran
    finally:
        await conn.execute("select pg_advisory_unlock($1)", LOCK_KEY)
