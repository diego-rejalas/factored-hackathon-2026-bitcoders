"""The conversation store against a real PostgreSQL: the SQL (grouping, ordering, jsonb) is not what a list in
memory exercises.

Needs a server: PG_TEST_HOST (and PG_TEST_PORT, PG_TEST_USER, PG_TEST_PASSWORD). It uses a throwaway database.
    PG_TEST_HOST=localhost PG_TEST_PORT=5433 PG_TEST_USER=postgres PG_TEST_PASSWORD=dev python -m pytest tests/test_conversations_postgres.py
"""

import asyncio
import os
import uuid

import pytest

from app.conversations import Conversations

pytestmark = pytest.mark.skipif(not os.environ.get("PG_TEST_HOST"), reason="set PG_TEST_HOST to run the Postgres tests")


def run(coro):
    return asyncio.run(coro)


async def _store():
    import asyncpg

    name = "conv_test_" + uuid.uuid4().hex[:8]
    params = dict(
        host=os.environ["PG_TEST_HOST"],
        port=int(os.environ.get("PG_TEST_PORT", "5432")),
        user=os.environ.get("PG_TEST_USER", "postgres"),
        password=os.environ.get("PG_TEST_PASSWORD", ""),
    )
    admin = await asyncpg.connect(database="postgres", **params)
    await admin.execute(f'create database "{name}"')
    pool = await asyncpg.create_pool(database=name, **params)
    store = Conversations(pool)
    await store.init_schema()
    return store, pool, admin, name


async def _drop(pool, admin, name):
    await pool.close()
    await admin.execute(f'drop database "{name}" with (force)')
    await admin.close()


def test_turns_are_saved_listed_newest_first_and_scoped_to_their_customer():
    async def scenario():
        store, pool, admin, name = await _store()
        try:
            await store.save_turn("CUS-A", "c1", "hola", "Hola, ¿en qué te ayudo?", {"outcome": "resolved"})
            await store.save_turn("CUS-A", "c2", "No reconozco un cobro de 45.50", "Caso abierto", {"outcome": "resolved", "case": {"case_id": "k1"}})
            await store.save_turn("CUS-A", "c2", "gracias", "De nada", {"outcome": "resolved"})
            await store.save_turn("CUS-B", "c3", "hola de B", "Hola", {"outcome": "resolved"})

            listed = await store.recent("CUS-A")
            assert [c["conversation_id"] for c in listed] == ["c2", "c1"]
            assert listed[0]["title"] == "No reconozco un cobro de 45.50"
            assert await store.recent("CUS-B") != listed

            messages = await store.messages("CUS-A", "c2")
            assert [m["role"] for m in messages] == ["user", "bot", "user", "bot"]
            assert messages[1]["response"]["case"]["case_id"] == "k1"  # jsonb comes back as a dict
            assert await store.messages("CUS-B", "c2") == []  # another customer's id reads nothing
        finally:
            await _drop(pool, admin, name)

    run(scenario())


def test_the_schema_can_be_created_twice():
    async def scenario():
        store, pool, admin, name = await _store()
        try:
            await store.init_schema()
        finally:
            await _drop(pool, admin, name)

    run(scenario())
