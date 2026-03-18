import hmac

from fastapi import HTTPException, Request

from src.config import get_settings


async def verify_admin_key(request: Request) -> None:
    settings = get_settings()
    admin_key = settings.ADMIN_API_KEY
    if not admin_key:
        raise HTTPException(status_code=403, detail="Admin API not configured")

    provided = request.headers.get("X-Admin-Key")
    if not provided or not hmac.compare_digest(provided, admin_key):
        raise HTTPException(status_code=403, detail="Invalid admin key")
