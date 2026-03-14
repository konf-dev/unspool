from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.account import router as account_router
from src.api.auth_token import router as auth_token_router
from src.api.chat import router as chat_router
from src.api.messages import router as messages_router
from src.api.subscribe import router as subscribe_router
from src.jobs.router import router as jobs_router
from src.config import get_settings
from src.telemetry.logger import configure_logging, get_logger
from src.telemetry.middleware import TraceMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log = get_logger("lifespan")
    settings = get_settings()
    log.info("app.starting", environment=settings.ENVIRONMENT)

    if settings.DATABASE_URL:
        from src.db.supabase import init_pool
        await init_pool()
        log.info("db.pool_initialized")

    # Auto-discover and import tool modules to trigger @register_tool decorators
    import importlib
    import pkgutil

    import src.tools as _tools_package

    for _, module_name, _ in pkgutil.iter_modules(_tools_package.__path__):
        importlib.import_module(f"src.tools.{module_name}")
    log.info("tools.registered")

    if settings.ENVIRONMENT != "development":
        from src.integrations.qstash import schedule_cron
        from src.orchestrator.config_loader import load_config as _load_config

        try:
            jobs_config = _load_config("jobs")
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

    if settings.DATABASE_URL:
        from src.db.supabase import close_pool
        await close_pool()

    log.info("app.shutdown")


settings = get_settings()
_is_prod = settings.ENVIRONMENT != "development"

app = FastAPI(
    title="Unspool",
    description="AI personal assistant for ADHD",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

cors_origins = [settings.FRONTEND_URL]
if settings.CORS_EXTRA_ORIGINS:
    cors_origins.extend(settings.CORS_EXTRA_ORIGINS.split(","))

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.add_middleware(TraceMiddleware)

app.include_router(account_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(messages_router, prefix="/api")
app.include_router(auth_token_router, prefix="/api")
app.include_router(subscribe_router, prefix="/api")
app.include_router(jobs_router, prefix="/jobs")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
