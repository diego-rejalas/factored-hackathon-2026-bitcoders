"""ID tokens for calling another Cloud Run service that requires IAM authentication.

The service account the agent runs as is granted `roles/run.invoker` on the backend. Cloud Run reads the
token from `X-Serverless-Authorization`, which leaves the `Authorization` header free for the session JWT
the backend validates itself.
"""

import time

import httpx

METADATA_URL = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"
# An identity token lives one hour; ask for a new one a few minutes before it expires.
REFRESH_MARGIN_SECONDS = 300
TOKEN_LIFETIME_SECONDS = 3600


class IdentityTokenProvider:
    def __init__(self, audience: str, transport: httpx.AsyncBaseTransport | None = None):
        self.audience = audience
        self._transport = transport
        self._token: str | None = None
        self._expires_at = 0.0

    async def token(self) -> str:
        if self._token is None or time.monotonic() >= self._expires_at:
            async with httpx.AsyncClient(transport=self._transport, timeout=5.0) as client:
                response = await client.get(
                    METADATA_URL, params={"audience": self.audience}, headers={"Metadata-Flavor": "Google"}
                )
            response.raise_for_status()
            self._token = response.text.strip()
            self._expires_at = time.monotonic() + TOKEN_LIFETIME_SECONDS - REFRESH_MARGIN_SECONDS
        return self._token
