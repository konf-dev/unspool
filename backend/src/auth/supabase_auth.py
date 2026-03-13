from functools import lru_cache

import httpx
from fastapi import HTTPException, Request
from jose import JWTError, jwt

from src.config import get_settings
from src.telemetry.logger import get_logger


@lru_cache
def _fetch_jwks(supabase_url: str) -> dict:
    """Fetch JWKS from Supabase auth endpoint (cached for process lifetime)."""
    resp = httpx.get(f"{supabase_url}/auth/v1/.well-known/jwks.json", timeout=10)
    resp.raise_for_status()
    jwks = resp.json()
    # Build a kid -> key mapping
    return {key["kid"]: key for key in jwks["keys"]}


def _get_signing_key(token: str, supabase_url: str) -> tuple[dict, str]:
    """Extract the signing key and algorithm from JWKS based on token header."""
    header = jwt.get_unverified_header(token)
    alg = header.get("alg", "HS256")
    kid = header.get("kid")

    if alg == "HS256":
        # Legacy Supabase projects use symmetric HS256
        settings = get_settings()
        return {"kty": "oct", "k": settings.SUPABASE_JWT_SIGNING_SECRET}, alg

    # New Supabase projects use ES256 with JWKS
    keys = _fetch_jwks(supabase_url)
    if kid not in keys:
        raise JWTError(f"Key ID {kid} not found in JWKS")
    return keys[kid], alg


def verify_jwt(token: str) -> str:
    log = get_logger("auth")
    settings = get_settings()
    try:
        key, alg = _get_signing_key(token, settings.SUPABASE_URL)

        if alg == "HS256":
            payload = jwt.decode(
                token,
                settings.SUPABASE_JWT_SIGNING_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
                options={"require_exp": True},
            )
        else:
            payload = jwt.decode(
                token,
                key,
                algorithms=[alg],
                audience="authenticated",
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
