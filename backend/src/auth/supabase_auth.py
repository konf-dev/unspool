import jwt
from jwt import PyJWKClient
from fastapi import HTTPException, Request

from src.config import get_settings
from src.telemetry.logger import get_logger

_jwk_client: PyJWKClient | None = None


def _get_jwk_client() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        settings = get_settings()
        jwks_url = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        _jwk_client = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=600)
    return _jwk_client


def verify_jwt(token: str) -> str:
    log = get_logger("auth")
    settings = get_settings()

    try:
        signing_key = _get_jwk_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
            issuer=f"{settings.SUPABASE_URL}/auth/v1",
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        log.warning("jwt.expired")
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        log.warning("jwt.verify_failed", error=str(exc))
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing sub claim")
    return user_id


EVAL_USER_ID = "b8a2e17e-ff55-485f-ad6c-29055a607b33"


async def get_current_user(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = auth_header.removeprefix("Bearer ")

    if token.startswith("eval:"):
        settings = get_settings()
        if not settings.EVAL_API_KEY:
            raise HTTPException(status_code=401, detail="Eval auth not configured")
        if token != f"eval:{settings.EVAL_API_KEY}":
            raise HTTPException(status_code=401, detail="Invalid eval key")
        return EVAL_USER_ID

    return verify_jwt(token)
