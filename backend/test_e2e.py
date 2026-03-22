import asyncio
import uuid
from datetime import datetime
from langchain_core.messages import HumanMessage
from src.core.database import AsyncSessionLocal, engine
from src.core.models import Base
from src.agents.cold_path.extractor import process_brain_dump
from src.agents.hot_path.graph import app

async def main():
    user_id = str(uuid.uuid4())
    current_time = datetime.now().isoformat()
    timezone = "UTC"
    
    # 1. Database Setup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    print(f"--- TEST START for user: {user_id} ---")
    
    # 2. User dumps a thought (Cold Path)
    raw_message = "I need to buy milk tomorrow morning."
    print(f"\nUser Says: {raw_message}")
    
    print("\n[Background] Archiver Processing...")
    async with AsyncSessionLocal() as session:
        await process_brain_dump(session, uuid.UUID(user_id), raw_message, current_time, timezone)
        
    # 3. User asks Agent A to do something (Hot Path)
    chat_message = "Can you mark the milk task as done?"
    print(f"\nUser Says: {chat_message}")
    
    initial_state = {
        "user_id": user_id,
        "session_id": "test_session",
        "messages": [
            HumanMessage(content=chat_message)
        ],
        "iteration": 0,
        "current_time_iso": current_time,
        "timezone": timezone,
        "context_string": "No recent context."
    }
    
    print("\n[Foreground] Agent A Reasoning...")
    final_state = await app.ainvoke(initial_state)
    
    print("\n--- AGENT RESPONSES ---")
    for msg in final_state["messages"]:
        msg_type = type(msg).__name__
        content = msg.content
        print(f"[{msg_type}]: {content}")
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            print(f"  Tool Calls: {msg.tool_calls}")

if __name__ == "__main__":
    asyncio.run(main())
