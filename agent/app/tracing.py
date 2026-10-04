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


def percentile(values: list[int], q: float) -> float | None:
    """Linear interpolation, same semantics as Postgres percentile_cont."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = q * (len(ordered) - 1)
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    frac = pos - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * frac, 2)


def aggregate_metrics(rows: list[dict]) -> dict:
    """Aggregate raw trace_log rows into the agent side of the admin metrics.
    Only structured step metadata is ever aggregated: no user text exists in
    trace_log by design. Definitions follow spec/CRITERIA.md; rates are None
    ("not defined") when there is no data."""
    runs_by_outcome: dict[str, int] = {}
    conversations: dict[str, dict] = {}
    node_latencies: dict[str, list[int]] = {}
    intents: dict[str, int] = {}
    languages: dict[str, int] = {}
    verify = {"ok": 0, "failed": 0}
    for row in rows:
        node = row.get("node")
        params = row.get("params") or {}
        if isinstance(params, str):  # no jsonb codec on the tracer pool: decode here
            try:
                params = json.loads(params)
            except ValueError:
                params = {}
        conversation = conversations.setdefault(
            row.get("conversation_id") or "", {"escalated": False, "runs": set()}
        )
        if row.get("run_id"):
            conversation["runs"].add(row["run_id"])
        if node == "respond" and row.get("result_status"):
            outcome = row["result_status"]
            runs_by_outcome[outcome] = runs_by_outcome.get(outcome, 0) + 1
            if outcome == "escalated":
                conversation["escalated"] = True
        if row.get("latency_ms") is not None:
            node_latencies.setdefault(node or "unknown", []).append(row["latency_ms"])
        if node == "understand":
            intents[row.get("intent") or "unknown"] = intents.get(row.get("intent") or "unknown", 0) + 1
            language = params.get("language") or "unknown"
            languages[language] = languages.get(language, 0) + 1
        if node == "verify":
            if row.get("result_status") == "failed":
                verify["failed"] += 1
            else:
                verify["ok"] += 1
    total_runs = sum(runs_by_outcome.values())
    total_conversations = len(conversations)
    escalated_conversations = sum(1 for c in conversations.values() if c["escalated"])
    latency = {
        node: {
            "p50_ms": percentile(values, 0.5),
            "p95_ms": percentile(values, 0.95),
            "n": len(values),
        }
        for node, values in sorted(node_latencies.items())
    }
    return {
        "runs_by_outcome": runs_by_outcome,
        "total_runs": total_runs,
        "containment": {
            "conversations": total_conversations,
            "without_transfer": total_conversations - escalated_conversations,
            "rate_percent": (
                round(100.0 * (total_conversations - escalated_conversations) / total_conversations, 1)
                if total_conversations
                else None
            ),
        },
        "latency_by_node": latency,
        "intents": intents,
        "languages": languages,
        "verify": verify,
    }


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

    TRACE_COLUMNS = "run_id, conversation_id, node, intent, params, result_status, latency_ms"

    async def metrics(self, window_hours: int | None = None) -> dict:
        """Agent-side metrics for the admin console, aggregated from agent.trace_log.
        The agent owns this schema: the backend never reads it (role isolation)."""
        if not self.enabled:
            return {"tracing_enabled": False}
        scope = "where ts >= now() - make_interval(hours => $1)" if window_hours is not None else ""
        args = (window_hours,) if window_hours is not None else ()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"select {self.TRACE_COLUMNS} from agent.trace_log {scope}", *args
            )
        result = aggregate_metrics([dict(row) for row in rows])
        result["tracing_enabled"] = True
        result["window_hours"] = window_hours
        return result

    async def conversation_trace(self, conversation_id: str) -> list[dict]:
        """Structured audit timeline of one conversation (never user text)."""
        if not self.enabled:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                select ts, node, intent, tool, result_status, latency_ms
                from agent.trace_log
                where conversation_id = $1
                order by ts, id
                """,
                conversation_id,
            )
        return [dict(row) for row in rows]


class NullTracer(Tracer):
    def __init__(self):
        super().__init__(None)
