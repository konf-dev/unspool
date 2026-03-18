from pathlib import Path

import yaml

from tests.eval.types import GoldenCase

_GOLDEN_DIR = Path(__file__).parent / "golden"


def load_golden_cases(
    filename: str,
    tag_filter: str | None = None,
) -> list[GoldenCase]:
    path = _GOLDEN_DIR / filename
    raw = yaml.safe_load(path.read_text())
    cases = [GoldenCase(**c) for c in raw.get("cases", [])]
    if tag_filter:
        cases = [c for c in cases if tag_filter in c.tags]
    return cases
