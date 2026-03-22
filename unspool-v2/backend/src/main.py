import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.chat import router as chat_router

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DB pools or background workers here if needed
    logger.info("Unspool V2 API starting up...")
    yield
    # Shutdown: Close connections
    logger.info("Unspool V2 API shutting down...")


app = FastAPI(
    title="Unspool V2 API",
    description="Event-sourced Graph API for Unspool",
    version="2.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api")

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "2.0.0"}
