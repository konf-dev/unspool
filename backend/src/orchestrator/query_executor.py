from typing import Any


async def execute_query(
    query_name: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    raise NotImplementedError("Query executor not yet implemented")


async def execute_operation(
    operation_name: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    raise NotImplementedError("Operation executor not yet implemented")
