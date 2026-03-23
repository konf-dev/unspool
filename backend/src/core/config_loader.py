"""YAML config loading with file-mtime caching and hash tracking."""

import hashlib
from pathlib import Path
from typing import Any

import yaml

from src.core.settings import get_settings
from src.telemetry.logger import get_logger

_log = get_logger("config_loader")

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
_config_cache: dict[str, tuple[dict[str, Any], float]] = {}
_config_hashes: dict[str, str] = {}


def _file_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def load_config(name: str) -> dict[str, Any]:
    path = _CONFIG_DIR / f"{name}.yaml"
    settings = get_settings()
    is_dev = settings.ENVIRONMENT == "development"

    if name in _config_cache:
        cached, cached_mtime = _config_cache[name]
        if not is_dev or _file_mtime(path) <= cached_mtime:
            return cached

    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    raw_bytes = path.read_bytes()
    file_hash = hashlib.sha256(raw_bytes).hexdigest()[:12]
    _config_hashes[f"config:{name}"] = file_hash

    _config_cache[name] = (raw, _file_mtime(path))
    return raw


def get_config_hash(key: str) -> str | None:
    return _config_hashes.get(key)


def get_all_config_hashes() -> dict[str, str]:
    return dict(_config_hashes)
