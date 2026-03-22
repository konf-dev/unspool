from fastapi import APIRouter, Depends

from pydantic import BaseModel

from src.auth.supabase_auth import get_current_user
from src.db import supabase as db
from src.telemetry.logger import get_logger

_log = get_logger("api.auth_token")

router = APIRouter()


class StoreTokenRequest(BaseModel):
    provider_refresh_token: str
    scopes: list[str] = []


@router.post("/auth/store-token")
async def store_token(
    request: StoreTokenRequest,
    user_id: str = Depends(get_current_user),
) -> dict[str, str]:
    await db.save_oauth_token(
        user_id=user_id,
        provider="google",
        refresh_token=request.provider_refresh_token,
        scopes=request.scopes,
    )

    await db.update_profile(user_id, google_calendar_connected=True)

    _log.info("auth_token.stored", user_id=user_id, provider="google")
    return {"status": "ok"}
