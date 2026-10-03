import httpx
import pytest

from app import tools as tools_module
from app.tools import MAX_ATTEMPTS, BankTools, ToolError


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(tools_module, "BACKOFF_SECONDS", (0, 0))


def backend(monkeypatch, responses):
    """Answer each attempt with the next item: an httpx.Response, or an exception to raise. Returns the attempt log."""
    attempts: list = []
    queue = list(responses)
    real = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append((request.method, request.url.path))
        item = queue.pop(0) if queue else httpx.Response(200, json={"ok": True})
        if isinstance(item, Exception):
            raise item
        return item

    def client(**kwargs):
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return attempts


@pytest.mark.anyio
async def test_a_transient_failure_is_retried_and_the_call_succeeds(monkeypatch):
    attempts = backend(monkeypatch, [httpx.ConnectError("refused"), httpx.Response(503), httpx.Response(200, json={"ok": 1})])
    assert await BankTools("http://backend").get_dispute("t", "c1") == {"ok": 1}
    assert len(attempts) == 3


@pytest.mark.anyio
async def test_it_gives_up_after_the_bounded_number_of_attempts(monkeypatch):
    attempts = backend(monkeypatch, [httpx.ReadTimeout("slow")] * 10)
    with pytest.raises(ToolError) as error:
        await BankTools("http://backend").get_dispute("t", "c1")
    assert error.value.status_code == 503
    assert len(attempts) == MAX_ATTEMPTS == 3  # never a retry storm
    assert "unreachable" in error.value.detail


@pytest.mark.anyio
async def test_a_persistent_502_is_retried_then_reported_with_its_status(monkeypatch):
    attempts = backend(monkeypatch, [httpx.Response(502, text="bad gateway")] * 10)
    with pytest.raises(ToolError) as error:
        await BankTools("http://backend").list_transactions("t")
    assert error.value.status_code == 502
    assert len(attempts) == 3


@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 500])
async def test_the_backends_own_answer_is_never_retried(monkeypatch, status):
    attempts = backend(monkeypatch, [httpx.Response(status, json={"detail": "no"})] * 5)
    with pytest.raises(ToolError) as error:
        await BankTools("http://backend").get_dispute("t", "c1")
    assert error.value.status_code == status and error.value.detail == "no"
    assert len(attempts) == 1


@pytest.mark.anyio
async def test_the_writes_are_retried_too_because_they_are_idempotent(monkeypatch):
    attempts = backend(monkeypatch, [httpx.Response(504), httpx.Response(201, json={"case_id": "c1"})])
    case = await BankTools("http://backend").create_dispute("t", "TXN-1", "unrecognized_charge", "s")
    assert case == {"case_id": "c1"}
    assert attempts == [("POST", "/disputes"), ("POST", "/disputes")]


@pytest.mark.anyio
async def test_resolve_calls_the_backends_resolve_route(monkeypatch):
    attempts = backend(monkeypatch, [])
    await BankTools("http://backend").resolve_dispute("t", "c1", {"rule": "r"})
    assert attempts == [("POST", "/disputes/c1/resolve")]


def test_connecting_has_a_short_limit_of_its_own():
    timeout = BankTools("http://backend").http_timeout
    assert timeout.connect == 2.0 and timeout.read == 10.0
    assert BankTools("http://backend", timeout=1.0).http_timeout.connect == 1.0  # never above the overall limit
