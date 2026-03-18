from datetime import datetime, timedelta, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


def eval_profile() -> dict:
    return {
        "id": "eval-user-001",
        "display_name": "Eval User",
        "timezone": "America/New_York",
        "tone_preference": "casual",
        "length_preference": "medium",
        "pushiness_preference": "gentle",
        "uses_emoji": False,
        "primary_language": "en",
        "google_calendar_connected": False,
        "notification_sent_today": False,
        "last_interaction_at": (_now() - timedelta(hours=2)).isoformat(),
        "patterns": {},
    }


def eval_items() -> list[dict]:
    now = _now()
    return [
        {
            "id": "item-001",
            "user_id": "eval-user-001",
            "raw_text": "finish the quarterly report",
            "interpreted_action": "Complete Q1 quarterly report",
            "deadline_type": "hard",
            "deadline_at": (now + timedelta(days=2)).isoformat(),
            "urgency_score": 0.8,
            "energy_estimate": "high",
            "status": "open",
            "created_at": (now - timedelta(days=3)).isoformat(),
            "last_surfaced_at": (now - timedelta(hours=6)).isoformat(),
            "nudge_after": None,
            "embedding": None,
        },
        {
            "id": "item-002",
            "user_id": "eval-user-001",
            "raw_text": "buy groceries",
            "interpreted_action": "Buy groceries (milk, eggs, bread)",
            "deadline_type": "soft",
            "deadline_at": (now + timedelta(days=1)).isoformat(),
            "urgency_score": 0.5,
            "energy_estimate": "low",
            "status": "open",
            "created_at": (now - timedelta(days=1)).isoformat(),
            "last_surfaced_at": None,
            "nudge_after": None,
            "embedding": None,
        },
        {
            "id": "item-003",
            "user_id": "eval-user-001",
            "raw_text": "schedule dentist appointment",
            "interpreted_action": "Call dentist office to schedule cleaning",
            "deadline_type": "none",
            "deadline_at": None,
            "urgency_score": 0.3,
            "energy_estimate": "low",
            "status": "open",
            "created_at": (now - timedelta(days=7)).isoformat(),
            "last_surfaced_at": (now - timedelta(days=2)).isoformat(),
            "nudge_after": None,
            "embedding": None,
        },
        {
            "id": "item-004",
            "user_id": "eval-user-001",
            "raw_text": "prep slides for Monday standup",
            "interpreted_action": "Prepare presentation slides for Monday standup meeting",
            "deadline_type": "hard",
            "deadline_at": (now + timedelta(days=4)).isoformat(),
            "urgency_score": 0.6,
            "energy_estimate": "medium",
            "status": "open",
            "created_at": (now - timedelta(days=2)).isoformat(),
            "last_surfaced_at": None,
            "nudge_after": None,
            "embedding": None,
        },
        {
            "id": "item-005",
            "user_id": "eval-user-001",
            "raw_text": "text mom back",
            "interpreted_action": "Reply to mom's text message",
            "deadline_type": "none",
            "deadline_at": None,
            "urgency_score": 0.4,
            "energy_estimate": "low",
            "status": "open",
            "created_at": (now - timedelta(hours=12)).isoformat(),
            "last_surfaced_at": None,
            "nudge_after": None,
            "embedding": None,
        },
    ]


def eval_messages() -> list[dict]:
    now = _now()
    return [
        {
            "id": "msg-001",
            "user_id": "eval-user-001",
            "role": "user",
            "content": "I need to finish the quarterly report by Wednesday",
            "created_at": (now - timedelta(hours=6)).isoformat(),
            "metadata": {},
        },
        {
            "id": "msg-002",
            "user_id": "eval-user-001",
            "role": "assistant",
            "content": "got it — quarterly report, due Wednesday. I'll keep track of that.",
            "created_at": (now - timedelta(hours=6, seconds=-1)).isoformat(),
            "metadata": {},
        },
        {
            "id": "msg-003",
            "user_id": "eval-user-001",
            "role": "user",
            "content": "also need to buy groceries and text my mom back",
            "created_at": (now - timedelta(hours=4)).isoformat(),
            "metadata": {},
        },
        {
            "id": "msg-004",
            "user_id": "eval-user-001",
            "role": "assistant",
            "content": "noted — groceries and texting mom. both low-effort ones you can knock out quick.",
            "created_at": (now - timedelta(hours=4, seconds=-1)).isoformat(),
            "metadata": {},
        },
        {
            "id": "msg-005",
            "user_id": "eval-user-001",
            "role": "user",
            "content": "what should I do right now?",
            "created_at": (now - timedelta(hours=2)).isoformat(),
            "metadata": {},
        },
        {
            "id": "msg-006",
            "user_id": "eval-user-001",
            "role": "assistant",
            "content": "the quarterly report — it's due soonest and you've got the energy window for it right now.",
            "created_at": (now - timedelta(hours=2, seconds=-1)).isoformat(),
            "metadata": {},
        },
    ]


class InMemoryStore:
    """Accumulates items/messages across turns within a multi-turn test."""

    def __init__(
        self,
        initial_items: list[dict] | None = None,
        initial_messages: list[dict] | None = None,
    ) -> None:
        self.items: list[dict] = list(initial_items or [])
        self.messages: list[dict] = list(initial_messages or [])

    async def save_item(
        self,
        user_id: str = "",
        raw_text: str = "",
        interpreted_action: str = "",
        deadline_type: str | None = None,
        deadline_at: str | None = None,
        urgency_score: float = 0.0,
        energy_estimate: str | None = None,
        source_message_id: str | None = None,
        entity_ids: list[str] | None = None,
        **kwargs: object,
    ) -> dict:
        import uuid

        item = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "raw_text": raw_text,
            "interpreted_action": interpreted_action,
            "deadline_type": deadline_type or "none",
            "deadline_at": deadline_at,
            "urgency_score": urgency_score,
            "energy_estimate": energy_estimate or "medium",
            "status": kwargs.get("status", "open"),
            "created_at": _now().isoformat(),
            "last_surfaced_at": None,
            "nudge_after": None,
            "embedding": None,
        }
        self.items.append(item)
        return item

    async def fetch_items(self, user_id: str, **kwargs: object) -> list[dict]:
        return [i for i in self.items if i.get("status", "open") == "open"]

    async def save_message(
        self,
        user_id: str = "",
        role: str = "user",
        content: str = "",
        metadata: dict | None = None,
        **kwargs: object,
    ) -> dict:
        import uuid

        msg = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "role": role,
            "content": content,
            "created_at": _now().isoformat(),
            "metadata": metadata or {},
        }
        self.messages.append(msg)
        return msg

    async def fetch_messages(self, user_id: str, **kwargs: object) -> list[dict]:
        limit = int(kwargs.get("limit", 20))  # type: ignore[arg-type]
        return self.messages[-limit:]

    async def fetch_profile(self, user_id: str, **kwargs: object) -> dict:
        return eval_profile()

    async def fetch_urgent_items(self, user_id: str, **kwargs: object) -> list[dict]:
        return [i for i in self.items if i.get("urgency_score", 0) >= 0.7]

    async def fetch_entities(self, user_id: str, **kwargs: object) -> list[dict]:
        return []

    async def fetch_memories(self, user_id: str, **kwargs: object) -> list[dict]:
        return []

    async def fetch_calendar_events(self, user_id: str, **kwargs: object) -> list[dict]:
        return []

    async def fetch_graph_context(self, user_id: str, **kwargs: object) -> str | None:
        return None
