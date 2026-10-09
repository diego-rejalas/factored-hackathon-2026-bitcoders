"""BankStore.ping must notice connections that died with the database and replace them."""

import asyncio

import asyncpg
import pytest

from app.db import BankStore


class Conn:
    def __init__(self, outcome):
        self.outcome = outcome

    async def fetchval(self, sql):
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        if self.outcome == "hang":
            await asyncio.sleep(60)
        return self.outcome


class Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class Pool:
    """Hands out the outcomes one by one: the first acquire gets the first, and so on."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.expired = 0

    def acquire(self):
        return Acquire(Conn(self.outcomes.pop(0)))

    async def expire_connections(self):
        self.expired += 1


def store(pool):
    s = object.__new__(BankStore)
    s.pool = pool
    s.PING_TIMEOUT_SECONDS = 0.05
    return s


@pytest.mark.anyio
async def test_a_healthy_pool_answers_without_touching_the_connections():
    pool = Pool(1)
    assert await store(pool).ping() is True
    assert pool.expired == 0


@pytest.mark.anyio
async def test_a_dead_connection_is_replaced_and_the_ping_succeeds():
    # The database was stopped and started: the pool still holds a connection that is gone.
    pool = Pool(ConnectionResetError("connection reset by peer"), 1)
    assert await store(pool).ping() is True
    assert pool.expired == 1, "all the connections must be marked to be replaced, not only the one that failed"


@pytest.mark.anyio
async def test_a_connection_lost_error_of_the_driver_counts_too():
    pool = Pool(asyncpg.ConnectionDoesNotExistError("connection was closed in the middle of operation"), 1)
    assert await store(pool).ping() is True
    assert pool.expired == 1


@pytest.mark.anyio
async def test_a_database_that_is_still_down_is_not_ready():
    pool = Pool(ConnectionRefusedError(), ConnectionRefusedError())
    assert await store(pool).ping() is False
    assert pool.expired == 2


@pytest.mark.anyio
async def test_a_connection_that_hangs_is_cut_off():
    pool = Pool("hang", 1)
    assert await store(pool).ping() is True  # the hung one is replaced and the second try answers
    assert pool.expired == 1
