import asyncio
from src.core.database import engine
from src.core.models import Base

async def main():
    async with engine.begin() as conn:
        print("Creating V2 Tables in Supabase...")
        await conn.run_sync(Base.metadata.create_all)
        print("Tables created successfully.")

if __name__ == "__main__":
    asyncio.run(main())
