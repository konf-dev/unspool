from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.account import router as account_router
from src.api.admin import router as admin_router
from src.api.chat import router as chat_router
from src.api.feed import router as feed_router
from src.api.messages import router as messages_router
from src.api.subscribe import router as subscribe_router
from src.api.webhooks import router as webhooks_router
from src.jobs.router import router as jobs_router
from src.core.settings import get_settings
from src.telemetry.logger import configure_logging, get_logger
from src.telemetry.middleware import GIT_SHA, TraceMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log = get_logger("lifespan")
    settings = get_settings()
    log.info("app.starting", environment=settings.ENVIRONMENT)

    # Initialize DB pool
    try:
        from src.core.database import init_db
        await init_db()
        log.info("db.pool_initialized")
    except Exception:
        log.error("db.init_failed", exc_info=True)

    # Register cron schedules in production
    if settings.ENVIRONMENT != "development":
        from src.integrations.qstash import (
            delete_schedule,
            list_schedules,
            schedule_cron,
        )
        from src.core.config_loader import load_config

        log.info("cron.registering", api_url=settings.API_URL)
        try:
            jobs_config = load_config("jobs")

            # Clean stale schedules before registering new ones
            valid_ids = {
                job_def["schedule_id"]
                for job_def in jobs_config.get("cron_jobs", {}).values()
                if "schedule_id" in job_def
            }
            existing = await list_schedules()
            for sched in existing:
                sid = getattr(sched, "schedule_id", None)
                if sid and sid.startswith("unspool-") and sid not in valid_ids:
                    await delete_schedule(sid)
                    log.info("cron.stale_schedule_deleted", schedule_id=sid)

            for job_name, job_def in jobs_config.get("cron_jobs", {}).items():
                await schedule_cron(
                    endpoint=job_name,
                    cron_expression=job_def["schedule"],
                    schedule_id=job_def.get("schedule_id"),
                )
            log.info("cron.schedules_registered", count=len(jobs_config.get("cron_jobs", {})))
        except Exception:
            log.error("cron.registration_failed", exc_info=True)

    yield

    # Shutdown
    try:
        from src.core.database import close_db
        await close_db()
    except Exception:
        pass

    log.info("app.shutdown")


settings = get_settings()
_is_prod = settings.ENVIRONMENT != "development"

app = FastAPI(
    title="Unspool",
    description="AI personal assistant for ADHD",
    version="2.0.0",
    lifespan=lifespan,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

# CORS — restricted to FRONTEND_URL + extras
cors_origins = [settings.FRONTEND_URL]
if settings.CORS_EXTRA_ORIGINS:
    cors_origins.extend(o.strip() for o in settings.CORS_EXTRA_ORIGINS.split(",") if o.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Trace middleware (adds x-trace-id header, structlog contextvars)
app.add_middleware(TraceMiddleware)

# API routes
app.include_router(account_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(messages_router, prefix="/api")
app.include_router(subscribe_router, prefix="/api")
app.include_router(feed_router, prefix="/api")
app.include_router(webhooks_router)
app.include_router(jobs_router, prefix="/jobs")
app.include_router(admin_router, prefix="/admin")


@app.get("/health")
async def health() -> dict[str, str]:
    try:
        from sqlalchemy import text as sa_text
        from src.core.database import engine
        async with engine.begin() as conn:
            await conn.execute(sa_text("SELECT 1"))
    except Exception:
        return {"status": "degraded", "db": "unreachable", "git_sha": GIT_SHA}
    return {"status": "ok", "version": "2.0.0", "git_sha": GIT_SHA}
