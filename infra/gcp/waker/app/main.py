import logging
import os

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from .config import Settings
from .gcp import Gcp
from .logic import Waker

log = logging.getLogger("waker")
logging.basicConfig(level=logging.INFO)


def build_app(settings: Settings | None = None, waker: Waker | None = None, verify_token=None) -> FastAPI:
    settings = settings or Settings.from_env()
    waker = waker or Waker(Gcp(settings), settings.idle_minutes, settings.status_cache_seconds)

    def default_verify(token: str) -> str:
        claims = id_token.verify_oauth2_token(token, google_requests.Request(), settings.scheduler_audience)
        return claims.get("email", "") if claims.get("email_verified") else ""

    verify = verify_token or default_verify
    app = FastAPI(title="waker", docs_url=None, redoc_url=None, openapi_url=None)
    # The landing lives on another origin. Only the origins in CORS_ALLOWED_ORIGINS may read the answers.
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"], allow_headers=[])

    def scheduler_only(authorization: str = Header(default="")) -> None:
        token = authorization.removeprefix("Bearer ").strip()
        if not (token and settings.scheduler_sa and settings.scheduler_audience):
            raise HTTPException(status_code=403, detail="forbidden")
        try:
            email = verify(token)
        except ValueError:
            raise HTTPException(status_code=403, detail="forbidden")
        if email != settings.scheduler_sa:
            raise HTTPException(status_code=403, detail="forbidden")

    def answer(response: Response, state: str) -> dict:
        response.headers["Cache-Control"] = "no-store"
        return {"state": state}

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/status")
    def status(response: Response) -> dict:
        return answer(response, waker.status())

    @app.post("/wake")
    def wake(response: Response) -> dict:
        state = waker.wake()
        log.info("wake requested, state=%s", state)
        return answer(response, state)

    @app.post("/sleep-if-idle", dependencies=[Depends(scheduler_only)])
    def sleep_if_idle(response: Response) -> dict:
        result = waker.sleep_if_idle()
        log.info("sleep check: %s", result)
        response.headers["Cache-Control"] = "no-store"
        return {"result": result}

    return app


app = build_app() if os.environ.get("PROJECT_ID") else None  # the module can be imported by tests without the environment
