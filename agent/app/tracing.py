import json
import os

DDL = [
    "create schema if not exists agent",
    """
    create table if not exists agent.trace_log (
        id bigint generated always as identity primary key,
        run_id uuid not null,
        conversation_id text not null,
        ts timestamptz not null default now(),
        node text not null,
        intent text,
        tool text,
        params jsonb,
        result_status text,
        latency_ms integer
    )
    """,
    "create index if not exists trace_log_conversation_idx on agent.trace_log (conversation_id, ts)",
]


class Tracer:
    """Append-only audit trail of every graph step into agent.trace_log.
    Never logs chain-of-thought, only structured step metadata. Best-effort:
    tracing failures never break the conversation."""

    def __init__(self, pool=None):
        self.pool = pool
        self.enabled = pool is not None

    @classmethod
    async def connect(cls) -> "Tracer":
        import asyncpg

        required = ("PG_HOST", "PG_USER", "PG_PASSWORD")
        if not all(os.environ.get(var) for var in required):
            return cls(None)
        pool = await asyncpg.create_pool(
            host=os.environ["PG_HOST"],
            port=int(os.environ.get("PG_PORT", "5432")),
            user=os.environ["PG_USER"],
            password=os.environ["PG_PASSWORD"],
            database=os.environ.get("PG_DATABASE", "data"),
        )
        tracer = cls(pool)
        await tracer.init_schema()
        return tracer

    async def init_schema(self) -> None:
        if not self.enabled:
            return
        async with self.pool.acquire() as conn:
            for statement in DDL:
                await conn.execute(statement)

    async def close(self) -> None:
        if self.enabled:
            await self.pool.close()

    async def log(
        self,
        run_id: str,
        conversation_id: str,
        node: str,
        intent: str | None = None,
        tool: str | None = None,
        params: dict | None = None,
        result_status: str | None = None,
        latency_ms: int | None = None,
    ) -> None:
        if not self.enabled:
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    insert into agent.trace_log
                        (run_id, conversation_id, node, intent, tool, params, result_status, latency_ms)
                    values ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    run_id,
                    conversation_id,
                    node,
                    intent,
                    tool,
                    json.dumps(params or {}),
                    result_status,
                    latency_ms,
                )
        except Exception:
            pass


class NullTracer(Tracer):
    def __init__(self):
        super().__init__(None)
