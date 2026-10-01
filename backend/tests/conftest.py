import os

os.environ.setdefault("SESSION_JWT_SECRET", "test-secret")
os.environ.setdefault("SESSION_TTL_MINUTES", "120")
