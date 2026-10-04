"""The customer's conversations, kept so they can come back to them.

Until now a conversation lived only in the browser: starting a new one threw the previous one away, and "My cases"
listed only the disputes that had been opened. This stores each turn (what the customer wrote and what the agent
answered, with the cards that went with it) in agent.conversation_messages, owned by the agent like agent.trace_log.

It is not the audit trail. trace_log holds no user text on purpose and stays that way; this table does hold it, so
it is only ever read for the customer who wrote it (the customer id comes from the verified token, never from the
request), and it is the table to apply the retention policy to. Saving is best effort: a failure here must not
break the conversation.
"""

import json

DDL = [
    "create schema if not exists agent",
    """
    create table if not exists agent.conversation_messages (
        id bigint generated always as identity primary key,
        conversation_id text not null,
        customer_id text not null,
        role text not null check (role in ('user', 'bot')),
        text text not null,
        response jsonb,
        created_at timestamptz not null default now()
    )
    """,
    "create index if not exists conversation_messages_customer_idx on agent.conversation_messages (customer_id, conversation_id, id)",
]

TITLE_LENGTH = 60


def title_of(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= TITLE_LENGTH else text[: TITLE_LENGTH - 1].rstrip() + "…"


class Conversations:
    """Postgres-backed. Without a pool it is disabled: nothing is saved and the lists are empty."""

    def __init__(self, pool=None):
        self.pool = pool
        self.enabled = pool is not None

    async def init_schema(self) -> None:
        if not self.enabled:
            return
        async with self.pool.acquire() as conn:
            for statement in DDL:
                await conn.execute(statement)

    async def save_turn(self, customer_id: str, conversation_id: str, user_text: str, reply: str, response: dict) -> None:
        if not self.enabled:
            return
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "insert into agent.conversation_messages (conversation_id, customer_id, role, text) values ($1, $2, 'user', $3)",
                        conversation_id,
                        customer_id,
                        user_text,
                    )
                    await conn.execute(
                        "insert into agent.conversation_messages (conversation_id, customer_id, role, text, response)"
                        " values ($1, $2, 'bot', $3, $4::jsonb)",
                        conversation_id,
                        customer_id,
                        reply,
                        json.dumps(response, default=str),
                    )
        except Exception:
            pass

    async def recent(self, customer_id: str, limit: int = 30) -> list[dict]:
        if not self.enabled:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                select conversation_id,
                       max(created_at) as last_at,
                       (array_agg(text order by id) filter (where role = 'user'))[1] as first_message
                from agent.conversation_messages
                where customer_id = $1
                group by conversation_id
                order by max(created_at) desc
                limit $2
                """,
                customer_id,
                limit,
            )
        return [
            {"conversation_id": row["conversation_id"], "title": title_of(row["first_message"] or ""), "last_at": row["last_at"]}
            for row in rows
        ]

    async def messages(self, customer_id: str, conversation_id: str) -> list[dict]:
        if not self.enabled:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                select role, text, response::text as response, created_at
                from agent.conversation_messages
                where customer_id = $1 and conversation_id = $2
                order by id
                """,
                customer_id,
                conversation_id,
            )
        return [
            {
                "role": row["role"],
                "text": row["text"],
                "response": json.loads(row["response"]) if row["response"] else None,
                "created_at": row["created_at"],
            }
            for row in rows
        ]


class MemoryConversations(Conversations):
    """The same behavior in a list, for tests."""

    def __init__(self):
        super().__init__(None)
        self.enabled = True
        self.rows: list[dict] = []

    async def init_schema(self) -> None:
        return None

    async def save_turn(self, customer_id, conversation_id, user_text, reply, response) -> None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        self.rows.append({"customer_id": customer_id, "conversation_id": conversation_id, "role": "user", "text": user_text, "response": None, "created_at": now})
        self.rows.append({"customer_id": customer_id, "conversation_id": conversation_id, "role": "bot", "text": reply, "response": response, "created_at": now})

    async def recent(self, customer_id, limit=30):
        latest: dict[str, dict] = {}
        for row in self.rows:
            if row["customer_id"] != customer_id:
                continue
            entry = latest.setdefault(row["conversation_id"], {"conversation_id": row["conversation_id"], "title": None, "last_at": row["created_at"]})
            if entry["title"] is None and row["role"] == "user":
                entry["title"] = title_of(row["text"])
            entry["last_at"] = max(entry["last_at"], row["created_at"])
        return sorted(latest.values(), key=lambda item: item["last_at"], reverse=True)[:limit]

    async def messages(self, customer_id, conversation_id):
        return [
            {k: row[k] for k in ("role", "text", "response", "created_at")}
            for row in self.rows
            if row["customer_id"] == customer_id and row["conversation_id"] == conversation_id
        ]
