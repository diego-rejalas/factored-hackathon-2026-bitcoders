# waker

Puts the demo to sleep when nobody uses it and wakes it on request. The one piece that does not wake by itself is Cloud SQL
(Cloud Run scales from zero on the first request), so that is what it stops and starts, by patching the instance's
activation policy (`NEVER` stops it, `ALWAYS` starts it). Design, permissions and costs: `infra/gcp/README.md`, "The demo sleeps by itself".

| Endpoint | Who | What |
|---|---|---|
| `GET /status` | anyone | `{"state": "asleep" \| "waking" \| "awake"}` (cached 5 s) |
| `POST /wake` | anyone | starts the database if it is stopped; idempotent |
| `POST /sleep-if-idle` | Cloud Scheduler (ID token of its service account) | stops the database if there was no request to the watched services for `IDLE_MINUTES`, it was not woken in that time, and the Airflow VM is not running |

The browser reaches it through the load balancer as `/waker/*`. The prefix is removed before the request arrives.

## Settings (environment)

`PROJECT_ID`, `SQL_INSTANCE`, `WATCH_SERVICES` (comma separated Cloud Run services), `IDLE_MINUTES` (30), `AIRFLOW_VM` and
`AIRFLOW_ZONE` (optional), `CORS_ALLOWED_ORIGINS`, `SCHEDULER_SA`, `SCHEDULER_AUDIENCE`, `STATUS_CACHE_SECONDS` (5). Terraform sets them.

## Tests

The Google calls are behind `app/gcp.py`; the tests use a fake in their place.

```bash
cd infra/gcp/waker
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest
```
