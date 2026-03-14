from collections.abc import Callable
from typing import Any

_registry: dict[str, Callable[..., Any]] = {}


def register_tool(name: str) -> Callable[..., Any]:
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        _registry[name] = fn
        return fn

    return decorator


def get_tool_registry() -> dict[str, Callable[..., Any]]:
    return _registry.copy()
