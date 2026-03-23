"""Backwards compatibility shim — use settings.py instead."""

from src.core.settings import get_settings

# Legacy: some existing code references `settings` directly
settings = get_settings()
