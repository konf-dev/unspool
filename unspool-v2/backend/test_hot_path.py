import asyncio
import uuid
from datetime import datetime
from langchain_core.messages import HumanMessage
from src.agents.hot_path.graph import app

async def main():
    user_id = str(uuid.uuid4())
    
    # We simulate a conversation
    initial_state = {
        "user_id": user_id,
        "session_id": "test_session",
        "messages": [
            HumanMessage(content="Can you search for any tasks related to 'milk' and mark them done?")
        ],
        "iteration": 0,
        "current_time_iso": datetime.now().isoformat(),
        "timezone": "UTC",
        "context_string": "No recent context."
    }
    
    print("Running Hot Path Agent...")
    final_state = await app.ainvoke(initial_state)
    
    print("\n--- FINAL MESSAGES ---")
    for msg in final_state["messages"]:
        msg_type = type(msg).__name__
        content = msg.content
        print(f"[{msg_type}]: {content}")
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            print(f"  Tool Calls: {msg.tool_calls}")

if __name__ == "__main__":
    asyncio.run(main())
