from typing import Any

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from src.core.config import settings

# We assume Supavisor URL is provided in the connection string
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ECHO_SQL,
    pool_pre_ping=True, connect_args={"statement_cache_size": 0},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

Base = declarative_base()

async def get_db_session():
    async with AsyncSessionLocal() as session:
        yield session
