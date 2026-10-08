"""The four Google API calls the waker needs, behind one small class so the logic can be tested with a fake."""

from datetime import datetime, timedelta, timezone

import google.auth
from google.auth.transport.requests import AuthorizedSession

from .config import Settings

SQLADMIN = "https://sqladmin.googleapis.com/v1"
MONITORING = "https://monitoring.googleapis.com/v3"
COMPUTE = "https://compute.googleapis.com/compute/v1"
TIMEOUT = 20


class Gcp:
    def __init__(self, settings: Settings):
        self.settings = settings
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        self.session = AuthorizedSession(credentials)

    def get_instance(self) -> dict:
        s = self.settings
        response = self.session.get(f"{SQLADMIN}/projects/{s.project_id}/instances/{s.sql_instance}", timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()

    def set_activation(self, instance: dict, policy: str, labels: dict[str, str]) -> None:
        """Patch the activation policy (ALWAYS starts the instance, NEVER stops it) and the labels.

        settingsVersion makes Cloud SQL refuse the write if someone else changed the settings since `instance` was read.
        """
        s = self.settings
        body = {
            "settings": {
                "settingsVersion": instance["settings"]["settingsVersion"],
                "activationPolicy": policy,
                "userLabels": labels,
            }
        }
        response = self.session.patch(
            f"{SQLADMIN}/projects/{s.project_id}/instances/{s.sql_instance}", json=body, timeout=TIMEOUT
        )
        response.raise_for_status()

    def request_count(self, minutes: int) -> int:
        """Requests the watched Cloud Run services received in the last `minutes` minutes."""
        s = self.settings
        if not s.watch_services:
            return 0
        names = " OR ".join(f'resource.labels.service_name="{name}"' for name in s.watch_services)
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=minutes)
        params = {
            "filter": f'metric.type="run.googleapis.com/request_count" AND resource.type="cloud_run_revision" AND ({names})',
            "interval.startTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "interval.endTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "view": "FULL",
        }
        total = 0
        while True:
            response = self.session.get(f"{MONITORING}/projects/{s.project_id}/timeSeries", params=params, timeout=TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            for series in payload.get("timeSeries", []):
                total += sum(int(point["value"].get("int64Value", 0)) for point in series.get("points", []))
            token = payload.get("nextPageToken")
            if not token:
                return total
            params["pageToken"] = token

    def vm_status(self) -> str:
        """RUNNING, TERMINATED, ... or "" when no VM is configured."""
        s = self.settings
        if not s.airflow_vm:
            return ""
        response = self.session.get(
            f"{COMPUTE}/projects/{s.project_id}/zones/{s.airflow_zone}/instances/{s.airflow_vm}", timeout=TIMEOUT
        )
        response.raise_for_status()
        return response.json().get("status", "")
