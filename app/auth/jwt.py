import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from app.config import get_settings
from app.core.exceptions import ForbiddenError

settings = get_settings()

ALGORITHM = settings.algorithm


def create_access_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire, "type": "access"},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire, "type": "refresh"},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def decode_token(token: str, expected_type: str = "access") -> uuid.UUID:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        if payload.get("type") != expected_type:
            raise ForbiddenError("Invalid token type")
        return uuid.UUID(payload["sub"])
    except JWTError as e:
        raise ForbiddenError(f"Invalid token: {e}") from e
