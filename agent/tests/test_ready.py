"""GET /ready: the agent is ready only when its own database connection and the backend work."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.tracing import NullTracer, Tracer
from tests.fakes import FakeBankTools


class Tools(FakeBankTools):
    def __init__(self, ready):
        super().__init__()
        self._ready = ready

    async def ready(self):
        return self._ready


class Tracing(NullTracer):
    def __init__(self, ok):
        super().__init__()
        self.ok = ok

    async def ping(self):
        return self.ok


def client(tools_ready=True, tracer_ok=True):
    return TestClient(create_app(tools=Tools(tools_ready), tracer=Tracing(tracer_ok), llm=None))


def test_ready_when_everything_behind_it_works():
    assert client().get("/ready").json() == {"status": "ready", "service": "agent"}


def test_not_ready_when_the_backend_cannot_reach_the_database():
    assert client(tools_ready=False).get("/ready").status_code == 503


def test_not_ready_when_the_agents_own_connection_is_dead():
    assert client(tracer_ok=False).get("/ready").status_code == 503


def test_liveness_does_not_depend_on_any_of_it():
    assert client(tools_ready=False, tracer_ok=False).get("/health").status_code == 200


class Conn:
    def __init__(self, outcome):
        self.outcome = outcome

    async def fetchval(self, sql):
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class Pool:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.expired = 0

    def acquire(self):
        return Acquire(Conn(self.outcomes.pop(0)))

    async def expire_connections(self):
        self.expired += 1


def test_the_tracers_ping_replaces_connections_that_died_with_the_database():
    pool = Pool(ConnectionResetError("reset"), 1)
    assert asyncio.run(Tracer(pool).ping()) is True
    assert pool.expired == 1


def test_the_tracers_ping_has_nothing_to_check_when_tracing_is_off():
    assert asyncio.run(Tracer(None).ping()) is True
