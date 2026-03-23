from fastapi import APIRouter, Depends

from src.auth.supabase_auth import get_current_user
from src.db.queries import delete_user_data
from src.telemetry.logger import get_logger

_log = get_logger("api.account")

router = APIRouter()


@router.delete("/account")
async def delete_account(user_id: str = Depends(get_current_user)) -> dict:
    """Delete all user data. Irreversible."""
    _log.info("account.delete_requested", user_id=user_id)
    counts = await delete_user_data(user_id)
    total = sum(counts.values())
    _log.info("account.deleted", user_id=user_id, total_rows=total)
    return {"deleted": True, "rows_deleted": total, "details": counts}
