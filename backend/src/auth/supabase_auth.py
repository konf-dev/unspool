from fastapi import HTTPException, Request
from jose import JWTError, jwt

from src.config import get_settings
from src.telemetry.logger import get_logger


def verify_jwt(token: str) -> str:
    log = get_logger("auth")
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SIGNING_SECRET,
            algorithms=["HS256"],
            options={"require_exp": True},
        )
    except JWTError as exc:
        log.warning("jwt.verify_failed", error=str(exc), token_prefix=token[:20] if token else "empty")
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing sub claim")
    return user_id


async def get_current_user(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = auth_header.removeprefix("Bearer ")
    return verify_jwt(token)
