"""Daily graph evolution — embeddings, connections, decay, pruning."""

from src.db import supabase as db
from src.telemetry.langfuse_integration import observe
from src.telemetry.logger import get_logger

_log = get_logger("jobs.evolve_graph")


@observe("job.evolve_graph")
async def run_evolve_graph() -> dict:
    try:
        from src.graph.evolve import evolve_graph
    except ImportError:
        _log.warning("evolve_graph.module_not_available")
        return {"evolved": 0, "status": "module_not_available"}

    users = await db.get_active_users(days=30)
    evolved = 0
    errors = 0

    for user in users:
        user_id = str(user["id"])
        try:
            await evolve_graph(user_id)
            evolved += 1
        except Exception:
            errors += 1
            _log.warning("evolve_graph.user_failed", user_id=user_id, exc_info=True)

    _log.info("evolve_graph.done", evolved=evolved, errors=errors)
    return {"evolved": evolved, "errors": errors}
