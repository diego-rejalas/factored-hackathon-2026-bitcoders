import json
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import asyncpg
from fastapi import Request


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")

# gold.transactions is a static snapshot (see spec/DATA_FINDINGS.md): relative
# day filters are anchored to the latest transaction in the dataset, not now(),
# so the demo does not return an empty list once the snapshot ages.
SNAPSHOT_EDGE_SQL = "select max(transaction_date) as edge from gold.transactions"

DDL = [
    "create schema if not exists app",
    """
    create table if not exists app.disputes (
        case_id uuid primary key default gen_random_uuid(),
        customer_id text not null,
        transaction_id text not null,
        reason_code text not null,
        summary text not null,
        status text not null default 'open'
            check (status in ('open', 'auto_resolved', 'escalated', 'closed')),
        evidence jsonb not null default '{}'::jsonb,
        created_at timestamptz not null default now(),
        resolved_at timestamptz
    )
    """,
    "create index if not exists disputes_customer_idx on app.disputes (customer_id, created_at desc)",
    """
    create table if not exists app.dispute_events (
        id bigint generated always as identity primary key,
        case_id uuid not null references app.disputes (case_id),
        event text not null,
        payload jsonb not null default '{}'::jsonb,
        ts timestamptz not null default now()
    )
    """,
    "create index if not exists dispute_events_case_idx on app.dispute_events (case_id, ts)",
]

TRANSACTION_COLUMNS = """
    transaction_id,
    transaction_date,
    process_date,
    product_id,
    transaction_type,
    transaction_category,
    amount,
    currency,
    coalesce(amount_usd, case when currency = 'USD' then amount end) as amount_usd_effective,
    channel,
    merchant_name,
    merchant_category,
    transaction_country,
    transaction_city,
    transaction_status,
    response_code
"""


def get_store(request: Request) -> "BankStore":
    return request.app.state.store


class BankStore:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self._snapshot_edge_value: Any = None

    @classmethod
    async def create(cls) -> "BankStore":
        pool = await asyncpg.create_pool(
            host=os.environ["PG_HOST"],
            port=int(os.environ.get("PG_PORT", "5432")),
            user=os.environ["PG_USER"],
            password=os.environ["PG_PASSWORD"],
            database=os.environ.get("PG_DATABASE", "data"),
            init=cls._init_conn,
        )
        return cls(pool)

    @staticmethod
    async def _init_conn(conn: asyncpg.Connection) -> None:
        await conn.set_type_codec(
            "jsonb",
            encoder=lambda value: json.dumps(value, default=_json_default),
            decoder=json.loads,
            schema="pg_catalog",
        )

    async def close(self) -> None:
        await self.pool.close()

    async def init_schema(self) -> None:
        async with self.pool.acquire() as conn:
            for statement in DDL:
                await conn.execute(statement)

    async def snapshot_edge(self) -> Any:
        if self._snapshot_edge_value is None:
            async with self.pool.acquire() as conn:
                self._snapshot_edge_value = await conn.fetchval(SNAPSHOT_EDGE_SQL)
        return self._snapshot_edge_value

    async def authenticate(self, customer_id: str, document_number: str) -> str | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                select customer_id
                from gold.customers
                where customer_id = $1
                  and document_number is not null
                  and document_number = $2
                """,
                customer_id,
                document_number,
            )
        return row["customer_id"] if row else None

    async def get_profile(self, customer_id: str) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                select customer_id, first_name, last_name, country
                from gold.customers
                where customer_id = $1
                """,
                customer_id,
            )
        return dict(row) if row else None

    async def list_transactions(
        self,
        customer_id: str,
        status: str | None = None,
        merchant: str | None = None,
        days: int | None = None,
        limit: int = 20,
    ) -> list[dict]:
        sql = f"""
            select {TRANSACTION_COLUMNS}
            from gold.transactions
            where customer_id = $1
        """
        params: list[Any] = [customer_id]
        if status:
            params.append(status)
            sql += f" and transaction_status = ${len(params)}"
        if merchant:
            params.append(f"%{merchant}%")
            sql += f" and merchant_name ilike ${len(params)}"
        if days is not None:
            edge = await self.snapshot_edge()
            params.extend([edge, days])
            sql += (
                f" and transaction_date >= ${len(params) - 1}"
                f" - make_interval(days => ${len(params)})"
            )
        params.append(limit)
        sql += f" order by transaction_date desc limit ${len(params)}"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(row) for row in rows]

    async def get_transaction(self, customer_id: str, transaction_id: str) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                select {TRANSACTION_COLUMNS}
                from gold.transactions
                where transaction_id = $1 and customer_id = $2
                """,
                transaction_id,
                customer_id,
            )
        return dict(row) if row else None

    async def create_dispute(
        self,
        customer_id: str,
        transaction_id: str,
        reason_code: str,
        summary: str,
        evidence: dict,
    ) -> dict:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    insert into app.disputes (customer_id, transaction_id, reason_code, summary, evidence)
                    values ($1, $2, $3, $4, $5)
                    returning case_id, customer_id, transaction_id, reason_code,
                              summary, status, evidence, created_at, resolved_at
                    """,
                    customer_id,
                    transaction_id,
                    reason_code,
                    summary,
                    evidence,
                )
                await conn.execute(
                    """
                    insert into app.dispute_events (case_id, event, payload)
                    values ($1, 'created', $2)
                    """,
                    row["case_id"],
                    {"reason_code": reason_code},
                )
        return dict(row)

    async def get_dispute(self, customer_id: str, case_id: str) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                select case_id, customer_id, transaction_id, reason_code,
                       summary, status, evidence, created_at, resolved_at
                from app.disputes
                where case_id = $1 and customer_id = $2
                """,
                case_id,
                customer_id,
            )
        return dict(row) if row else None

    async def get_dispute_events(self, case_id: str) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                select event, payload, ts
                from app.dispute_events
                where case_id = $1
                order by ts, id
                """,
                case_id,
            )
        return [dict(row) for row in rows]

    async def escalate_dispute(
        self, customer_id: str, case_id: str, handoff: dict
    ) -> dict | None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    update app.disputes
                    set status = 'escalated',
                        evidence = evidence || jsonb_build_object('handoff', $3::jsonb),
                        resolved_at = now()
                    where case_id = $1 and customer_id = $2
                    returning case_id, customer_id, transaction_id, reason_code,
                              summary, status, evidence, created_at, resolved_at
                    """,
                    case_id,
                    customer_id,
                    json.dumps(handoff),
                )
                if row is not None:
                    await conn.execute(
                        """
                        insert into app.dispute_events (case_id, event, payload)
                        values ($1, 'escalated', $2)
                        """,
                        case_id,
                        json.dumps(handoff),
                    )
        return dict(row) if row else None
