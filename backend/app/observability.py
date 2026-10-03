"""A request id on every response and one structured log line per request.

The id comes in as X-Request-ID (from the BFF or the agent) when it is well formed, otherwise a new one is made, and it
goes back in the same header, so one customer action can be followed across the app, the agent and this service. The
log line is JSON on stdout with a `severity` field, which Cloud Run reads as a structured entry.

What is never logged: the Authorization header, the query string (it can carry a search the customer typed), request
and response bodies. The path is the route template (/v1/disputes/{case_id}), not the concrete one.
"""

import contextvars
import json
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,100}$")

# Readable anywhere in the same request, so a client call made deep in the code can pass the id on.
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def route_template(request) -> str:
    """/v1/disputes/{case_id}: the real path with each path parameter's value replaced by its name.

    Built from the path and the matched parameters instead of the route object, whose path leaves out the prefix of
    a router that was included under one.
    """
    path = request.url.path
    for name, value in request.scope.get("path_params", {}).items():
        path = path.replace(str(value), "{" + name + "}", 1)
    return path


def log(severity: str, message: str, **fields) -> None:
    print(json.dumps({"severity": severity, "message": message, **fields}, default=str, ensure_ascii=False), flush=True)


class RequestLogMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, service: str):
        super().__init__(app)
        self.service = service

    async def dispatch(self, request, call_next):
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception as error:  # noqa: BLE001
            log("ERROR", "request failed", service=self.service, request_id=request_id, method=request.method,
                path=request.url.path, error=type(error).__name__,
                duration_ms=int((time.monotonic() - start) * 1000))
            raise
        finally:
            request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        status = response.status_code
        log(
            "ERROR" if status >= 500 else "WARNING" if status >= 400 else "INFO",
            "request",
            service=self.service,
            request_id=request_id,
            method=request.method,
            path=route_template(request),
            status=status,
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        return response
