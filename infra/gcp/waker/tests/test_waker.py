from fastapi.testclient import TestClient

from app.config import Settings
from app.logic import ASLEEP, AWAKE, WAKING, Waker, state_of
from app.main import build_app


class FakeBackend:
    def __init__(self, policy="ALWAYS", state="RUNNABLE", labels=None, requests=0, vm=""):
        self.policy, self.state, self.labels = policy, state, dict(labels or {})
        self.requests, self.vm = requests, vm
        self.patches: list[tuple[str, dict]] = []
        self.reads = 0
        self.fail_requests = False

    def get_instance(self):
        self.reads += 1
        return {"state": self.state, "settings": {"settingsVersion": "7", "activationPolicy": self.policy, "userLabels": dict(self.labels)}}

    def set_activation(self, instance, policy, labels):
        self.patches.append((policy, dict(labels)))
        self.policy, self.labels = policy, dict(labels)
        self.state = "RUNNABLE" if policy == "ALWAYS" else "STOPPED"

    def request_count(self, minutes):
        if self.fail_requests:
            raise RuntimeError("monitoring is down")
        return self.requests

    def vm_status(self):
        return self.vm


NOW = 1_000_000.0


def make(backend, cache=0.0, idle=30):
    return Waker(backend, idle_minutes=idle, cache_seconds=cache, clock=lambda: NOW)


def test_state_of_covers_the_three_states():
    assert state_of({"state": "STOPPED", "settings": {"activationPolicy": "NEVER"}}) == ASLEEP
    # Asked to stop but still shutting down: the decision is made, so it reads as asleep.
    assert state_of({"state": "RUNNABLE", "settings": {"activationPolicy": "NEVER"}}) == ASLEEP
    assert state_of({"state": "STOPPED", "settings": {"activationPolicy": "ALWAYS"}}) == WAKING
    assert state_of({"state": "RUNNABLE", "settings": {"activationPolicy": "ALWAYS"}}) == AWAKE


def test_wake_starts_a_stopped_database_and_stamps_the_time():
    backend = FakeBackend(policy="NEVER", state="STOPPED", labels={"environment": "prod"})
    assert make(backend).wake() == WAKING
    assert backend.patches == [("ALWAYS", {"environment": "prod", "woken_at": str(int(NOW))})]


def test_wake_is_idempotent():
    backend = FakeBackend(policy="NEVER", state="STOPPED")
    waker = make(backend)
    waker.wake()
    backend.state = "STOPPED"  # still starting
    assert waker.wake() == WAKING
    assert len(backend.patches) == 1  # the second call did not write again


def test_wake_on_a_running_database_writes_nothing():
    backend = FakeBackend()
    assert make(backend).wake() == AWAKE
    assert backend.patches == []


def test_status_is_cached_for_a_few_seconds():
    backend = FakeBackend()
    waker = Waker(backend, idle_minutes=30, cache_seconds=5, clock=lambda: NOW)
    waker.status()
    waker.status()
    assert backend.reads == 1


def test_sleeps_when_nobody_used_the_demo():
    backend = FakeBackend(labels={"woken_at": str(int(NOW) - 31 * 60)}, requests=0)
    assert make(backend).sleep_if_idle() == "slept"
    assert backend.patches[-1][0] == "NEVER"
    # The labels of the instance survive the write.
    assert backend.patches[-1][1] == {"woken_at": str(int(NOW) - 31 * 60)}


def test_stays_awake_when_the_demo_is_in_use():
    backend = FakeBackend(requests=3)
    assert make(backend).sleep_if_idle() == "in_use"
    assert backend.patches == []


def test_stays_awake_right_after_a_wake_even_without_traffic():
    backend = FakeBackend(labels={"woken_at": str(int(NOW) - 60)}, requests=0)
    assert make(backend).sleep_if_idle() == "recently_woken"
    assert backend.patches == []


def test_never_sleeps_while_airflow_runs():
    backend = FakeBackend(requests=0, vm="RUNNING")
    assert make(backend).sleep_if_idle() == "airflow_running"
    assert backend.patches == []


def test_a_stopped_airflow_vm_does_not_block_sleep():
    assert make(FakeBackend(requests=0, vm="TERMINATED")).sleep_if_idle() == "slept"


def test_already_asleep_does_nothing():
    backend = FakeBackend(policy="NEVER", state="STOPPED")
    assert make(backend).sleep_if_idle() == "already_asleep"
    assert backend.patches == []


def test_any_doubt_keeps_it_awake():
    backend = FakeBackend(requests=0)
    backend.fail_requests = True
    try:
        make(backend).sleep_if_idle()
    except RuntimeError:
        pass
    assert backend.patches == []


SETTINGS = Settings(
    project_id="p", sql_instance="i", watch_services=["frontend", "agent"], idle_minutes=30, airflow_vm="", airflow_zone="",
    cors_origins=["https://landing.example"], scheduler_sa="scheduler@p.iam", scheduler_audience="waker", status_cache_seconds=0,
)


def client(backend, caller="scheduler@p.iam"):
    def verify(token):
        if token != "good":
            raise ValueError("bad token")
        return caller

    return TestClient(build_app(SETTINGS, make(backend), verify_token=verify))


def test_status_and_wake_are_public_and_not_cached():
    backend = FakeBackend(policy="NEVER", state="STOPPED")
    api = client(backend)
    assert api.get("/status").json() == {"state": "asleep"}
    response = api.post("/wake")
    assert response.json() == {"state": "waking"}
    assert response.headers["cache-control"] == "no-store"


def test_cors_allows_only_the_landing():
    api = client(FakeBackend())
    ok = api.get("/status", headers={"Origin": "https://landing.example"})
    other = api.get("/status", headers={"Origin": "https://evil.example"})
    assert ok.headers.get("access-control-allow-origin") == "https://landing.example"
    assert "access-control-allow-origin" not in other.headers


def test_sleep_endpoint_rejects_everyone_but_the_scheduler():
    backend = FakeBackend(requests=0, labels={})
    api = client(backend)
    assert api.post("/sleep-if-idle").status_code == 403
    assert api.post("/sleep-if-idle", headers={"Authorization": "Bearer nope"}).status_code == 403
    assert client(backend, caller="someone@else.iam").post("/sleep-if-idle", headers={"Authorization": "Bearer good"}).status_code == 403
    assert backend.patches == []
    ok = api.post("/sleep-if-idle", headers={"Authorization": "Bearer good"})
    assert ok.json() == {"result": "slept"}
