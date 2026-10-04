import os

os.environ.setdefault("SESSION_JWT_SECRET", "test-session-secret-key-over-thirty-two-bytes")
os.environ.setdefault("GUARDRAIL_MAX_USD", "500")
