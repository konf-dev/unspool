import asyncio
import uuid
from datetime import datetime
from src.core.database import AsyncSessionLocal
from src.agents.cold_path.extractor import process_brain_dump

async def main():
    user_id = uuid.uuid4()
    raw_message = "I need to call sarah, buy milk, cancel the netflix sub, and why is my back hurting, also the project is due on the 12th."
    current_time = datetime.utcnow().isoformat()
    timezone = "UTC"
    
    async with AsyncSessionLocal() as session:
        # We need to create tables first since this is a clean DB
        from src.core.database import engine
        from src.core.models import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
            
        print("Running extraction...")
        await process_brain_dump(session, user_id, raw_message, current_time, timezone)
        print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
