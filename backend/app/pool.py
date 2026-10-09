"""A connection pool that never hands out a dead connection.

When the database is stopped and started again (the demo sleeps and wakes), the connections a pool holds are dead, but the pool
does not know it: asyncpg closes idle connections with a timer, and that timer does not run while the instance is frozen between
requests (the CPU is billed per request). The next queries that pick one of them fail, one connection at a time, for as long as
there are dead ones. Nothing the services do then is safe, and a readiness check at wake-up only covers the instance it reaches.

So every connection is checked with a trivial query before it is handed out. A dead one is thrown away, the whole pool is marked
to be replaced, and the next one is tried, with a short wait, until the database answers or it is clearly not there. The check
costs one round trip inside the VPC. The code that uses the pool does not change: it only calls `acquire()`.
"""

import asyncio

import asyncpg

# What a dead connection, a database that is starting up or one that is not there raise on the check.
CHECK_ERRORS = (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError)


class DatabaseUnavailable(Exception):
    """The database did not answer on a fresh connection either, after several tries."""


class ResilientPool:
    CHECK_TIMEOUT_SECONDS = 5.0
    ATTEMPTS = 4
    BACKOFF_SECONDS = (0.2, 0.5, 1.0)

    def __init__(self, pool):
        self._pool = pool

    def acquire(self):
        return _Acquire(self)

    def __getattr__(self, name):
        # close(), expire_connections() and the rest are the real pool's.
        return getattr(self._pool, name)


async def _discard(pool, conn) -> None:
    """Throw a connection away. When a query fails because the connection was closed, asyncpg's own pool has already taken it
    back, and then terminate() and release() refuse with an InterfaceError: that is fine, it is already gone."""
    try:
        conn.terminate()
    except CHECK_ERRORS:
        pass
    try:
        await pool.release(conn)
    except CHECK_ERRORS:
        pass


class _Acquire:
    def __init__(self, owner: ResilientPool):
        self.owner = owner
        self.conn = None

    async def __aenter__(self):
        owner, pool = self.owner, self.owner._pool
        last: BaseException | None = None
        for attempt in range(owner.ATTEMPTS):
            conn = None
            try:
                conn = await pool.acquire(timeout=owner.CHECK_TIMEOUT_SECONDS)
                async with asyncio.timeout(owner.CHECK_TIMEOUT_SECONDS):
                    await conn.fetchval("select 1")
                self.conn = conn
                return conn
            except CHECK_ERRORS as error:
                last = error
                if conn is not None:
                    await _discard(pool, conn)
                # The others in the pool are very likely dead too: replace them all on their next use.
                await pool.expire_connections()
                if attempt < owner.ATTEMPTS - 1:
                    await asyncio.sleep(owner.BACKOFF_SECONDS[min(attempt, len(owner.BACKOFF_SECONDS) - 1)])
        raise DatabaseUnavailable(f"the database did not answer after {owner.ATTEMPTS} tries: {type(last).__name__}") from last

    async def __aexit__(self, *exc):
        conn, self.conn = self.conn, None
        if conn is not None:
            await self.owner._pool.release(conn)
        return False
