"""Password hashing (argon2id, the library's defaults) for the sign-in by user name."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()

# A user name that does not exist is checked against this hash, so "no such user" and "wrong password" take the
# same time and the answer does not tell them apart.
DUMMY_HASH = _hasher.hash("a password nobody has")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False
