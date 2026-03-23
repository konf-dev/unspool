"""PII scrubbing — regex masking for common PII patterns."""

import re

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # SSN: 123-45-6789
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    # Credit card: 16 digits with optional separators
    (re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "[CARD]"),
    # Email
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL]"),
    # Phone: various formats
    (re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[PHONE]"),
]


def scrub_pii(text: str) -> str:
    """Mask common PII patterns in text."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
