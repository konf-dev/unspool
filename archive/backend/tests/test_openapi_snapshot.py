import json
import os
from pathlib import Path

from src.main import app

_SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "openapi.json"


def test_openapi_snapshot() -> None:
    schema = app.openapi()
    current = json.dumps(schema, indent=2, sort_keys=True)

    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        _SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SNAPSHOT_PATH.write_text(current + "\n", encoding="utf-8")
        return

    assert _SNAPSHOT_PATH.exists(), (
        f"OpenAPI snapshot not found at {_SNAPSHOT_PATH}. "
        "Run with UPDATE_SNAPSHOTS=1 to create it."
    )

    saved = _SNAPSHOT_PATH.read_text(encoding="utf-8").strip()
    assert current == saved, (
        "OpenAPI schema has changed. Run with UPDATE_SNAPSHOTS=1 to update.\n"
        f"Snapshot: {_SNAPSHOT_PATH}"
    )
