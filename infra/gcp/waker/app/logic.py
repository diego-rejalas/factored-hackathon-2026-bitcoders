"""When the demo is asleep, how it wakes, and when it goes back to sleep.

The demo has one piece that does not wake by itself: Cloud SQL. Cloud Run scales from zero on the first request, so
"asleep" means the database is stopped (activation policy NEVER) and "awake" means it is running.
"""

import threading
import time
from typing import Protocol

ASLEEP, WAKING, AWAKE = "asleep", "waking", "awake"
WOKEN_LABEL = "woken_at"


class Backend(Protocol):
    def get_instance(self) -> dict: ...
    def set_activation(self, instance: dict, policy: str, labels: dict[str, str]) -> None: ...
    def request_count(self, minutes: int) -> int: ...
    def vm_status(self) -> str: ...


def state_of(instance: dict) -> str:
    policy = instance.get("settings", {}).get("activationPolicy", "ALWAYS")
    if policy == "NEVER":
        return ASLEEP  # also while it is still shutting down: the decision is made
    return AWAKE if instance.get("state") == "RUNNABLE" else WAKING


class Waker:
    def __init__(self, backend: Backend, idle_minutes: int, cache_seconds: float = 5.0, clock=time.time):
        self.backend = backend
        self.idle_minutes = idle_minutes
        self.cache_seconds = cache_seconds
        self.clock = clock
        self._lock = threading.Lock()
        self._cached: tuple[float, str] | None = None

    def _labels(self, instance: dict) -> dict[str, str]:
        return dict(instance.get("settings", {}).get("userLabels") or {})

    def status(self) -> str:
        now = self.clock()
        with self._lock:
            if self._cached and now - self._cached[0] < self.cache_seconds:
                return self._cached[1]
        state = state_of(self.backend.get_instance())
        with self._lock:
            self._cached = (now, state)
        return state

    def wake(self) -> str:
        """Idempotent: starts the database only if it is stopped."""
        with self._lock:
            instance = self.backend.get_instance()
            state = state_of(instance)
            if state == ASLEEP:
                labels = self._labels(instance)
                labels[WOKEN_LABEL] = str(int(self.clock()))
                self.backend.set_activation(instance, "ALWAYS", labels)
                state = WAKING
            self._cached = (self.clock(), state)
            return state

    def sleep_if_idle(self) -> str:
        """Stops the database if nobody used the demo for `idle_minutes`. Any doubt keeps it awake."""
        instance = self.backend.get_instance()
        if state_of(instance) == ASLEEP:
            return "already_asleep"
        labels = self._labels(instance)
        woken_at = labels.get(WOKEN_LABEL, "")
        if woken_at.isdigit() and self.clock() - int(woken_at) < self.idle_minutes * 60:
            return "recently_woken"
        if self.backend.vm_status() == "RUNNING":
            return "airflow_running"
        if self.backend.request_count(self.idle_minutes) > 0:
            return "in_use"
        self.backend.set_activation(instance, "NEVER", labels)
        with self._lock:
            self._cached = None
        return "slept"
