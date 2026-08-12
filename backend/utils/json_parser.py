"""Utility functions — safe JSON parsing and other helpers."""

import json
from typing import Any, Optional

from loguru import logger


def safe_json_parse(text: str) -> Optional[dict[str, Any]]:
    """Safely parse a JSON string, returning None on failure.

    Tries multiple strategies:
    1. Direct parse
    2. Extract from ```json ... ``` fences
    3. Find first { ... } block

    Args:
        text: Raw text that may contain JSON.

    Returns:
        Parsed dict or None.
    """
    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract from code fences
    import re
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: find first balanced { ... }
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start = -1

    # Do not log model output: it may contain private user context.
    logger.debug("Could not parse structured AI output (length={})", len(text))
    return None
