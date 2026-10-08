"""ResilientPool never hands out a dead connection (unit tests with fakes; the real thing is checked against PostgreSQL in CI's
database tests and by stopping and starting a real server)."""

import asyncio

import asyncpg
import pytest

from app.pool import DatabaseUnavailable, ResilientPool


class Conn:
    def __init__(self, outcome=1, already_back=False):
        self.outcome = outcome
        self.terminated = False
        self.already_back = already_back

    async def fetchval(self, sql):
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        if self.outcome == "hang":
            await asyncio.sleep(60)
        return self.outcome

    def terminate(self):
        if self.already_back:
            raise asyncpg.InterfaceError("cannot call Connection.terminate(): connection has been released back to the pool")
        self.terminated = True


class Pool:
    """Hands out the connections it was given, in order; remembers what happened to them."""

    def __init__(self, *conns, acquire_errors=()):
        self.conns = list(conns)
        self.acquire_errors = list(acquire_errors)
        self.released = []
        self.expired = 0
        self.acquires = 0

    async def acquire(self, timeout=None):
        self.acquires += 1
        if self.acquire_errors:
            error = self.acquire_errors.pop(0)
            if error:
                raise error
        return self.conns.pop(0)

    async def release(self, conn):
        self.released.append(conn)

    async def expire_connections(self):
        self.expired += 1

    async def close(self):
        self.closed = True


def resilient(pool):
    wrapper = ResilientPool(pool)
    wrapper.BACKOFF_SECONDS = (0, 0, 0)
    wrapper.CHECK_TIMEOUT_SECONDS = 0.05
    return wrapper


@pytest.mark.anyio
async def test_a_healthy_connection_is_handed_out_and_given_back():
    good = Conn()
    pool = Pool(good)
    async with resilient(pool).acquire() as conn:
        assert conn is good
    assert pool.released == [good]
    assert pool.expired == 0 and not good.terminated


@pytest.mark.anyio
async def test_a_dead_connection_is_thrown_away_and_the_next_one_is_used():
    dead, good = Conn(ConnectionResetError("reset by peer")), Conn()
    pool = Pool(dead, good)
    async with resilient(pool).acquire() as conn:
        assert conn is good
    assert dead.terminated and not good.terminated
    assert pool.expired == 1, "the whole pool is marked to be replaced, not only the connection that failed"
    assert pool.released == [dead, good]


@pytest.mark.anyio
async def test_a_connection_the_driver_already_took_back_is_not_a_second_failure():
    # Seen against a real PostgreSQL: when a query dies because the connection was closed, asyncpg's pool has already
    # taken the connection back, so terminate() refuses. That must not escape.
    dead = Conn(asyncpg.ConnectionDoesNotExistError("connection was closed in the middle of operation"), already_back=True)
    pool = Pool(dead, Conn())
    async with resilient(pool).acquire():
        pass
    assert pool.expired == 1


@pytest.mark.anyio
async def test_the_drivers_lost_connection_errors_count_as_dead_too():
    dead = Conn(asyncpg.ConnectionDoesNotExistError("connection was closed in the middle of operation"))
    pool = Pool(dead, Conn())
    async with resilient(pool).acquire():
        pass
    assert dead.terminated


@pytest.mark.anyio
async def test_a_database_that_is_starting_up_is_waited_for():
    starting = Conn(asyncpg.CannotConnectNowError("the database system is starting up"))
    pool = Pool(starting, Conn(), acquire_errors=[None, None])
    async with resilient(pool).acquire():
        pass
    assert pool.expired == 1


@pytest.mark.anyio
async def test_a_connection_that_hangs_is_cut_off():
    hung = Conn("hang")
    pool = Pool(hung, Conn())
    async with resilient(pool).acquire():
        pass
    assert hung.terminated


@pytest.mark.anyio
async def test_a_pool_that_cannot_connect_is_retried_and_then_gives_up():
    pool = Pool(acquire_errors=[ConnectionRefusedError()] * 4)
    with pytest.raises(DatabaseUnavailable):
        async with resilient(pool).acquire():
            pass
    assert pool.acquires == 4 and pool.expired == 4


@pytest.mark.anyio
async def test_it_gives_up_when_every_connection_is_dead():
    pool = Pool(*[Conn(ConnectionResetError()) for _ in range(4)])
    with pytest.raises(DatabaseUnavailable):
        async with resilient(pool).acquire():
            pass


@pytest.mark.anyio
async def test_an_error_in_the_body_still_gives_the_connection_back_and_is_not_swallowed():
    good = Conn()
    pool = Pool(good)
    with pytest.raises(ValueError):
        async with resilient(pool).acquire():
            raise ValueError("a bug of the caller")
    assert pool.released == [good]


@pytest.mark.anyio
async def test_the_rest_of_the_pool_is_the_real_pools():
    pool = Pool()
    wrapper = resilient(pool)
    await wrapper.close()
    await wrapper.expire_connections()
    assert pool.closed and pool.expired == 1


def test_a_database_that_is_unavailable_answers_503_and_not_500(client, store):
    async def down():
        raise DatabaseUnavailable("no answer")

    store.demo_scenarios = down
    assert client.get("/meta/demo-scenarios").status_code == 503
