import os

import bcrypt

os.environ.setdefault("SESSION_JWT_SECRET", "test-session-secret-key-over-thirty-two-bytes")
os.environ.setdefault("SESSION_TTL_MINUTES", "120")

# Admin credentials for the suite: same format as production ADMIN_USERS
# (user:bcrypt_hash). Low cost factor: it exists to pass, not to resist.
_HASH = bcrypt.hashpw(b"demo-password", bcrypt.gensalt(rounds=4)).decode()
os.environ.setdefault("ADMIN_USERS", f"ops-demo:{_HASH},lead-demo:{_HASH}")
