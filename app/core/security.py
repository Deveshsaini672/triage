from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:  # e.g. password longer than bcrypt's 72-byte limit
        return False


# Used to burn the same CPU time when the email doesn't exist,
# so login timing doesn't reveal which emails are registered.
DUMMY_HASH = hash_password("dummy-password")


def create_access_token(agent_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(agent_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError on any invalid/expired token."""
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "exp"]},
    )
