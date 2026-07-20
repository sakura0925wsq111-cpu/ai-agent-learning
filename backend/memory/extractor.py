"""Memory extractor — parses LLM responses for memory_update JSON.

The AI is instructed to append a JSON block at the end of its response
when it detects new user information. This module extracts and parses
that JSON, separating the clean reply from the memory update metadata.
"""

import json
import re
from typing import Tuple

from loguru import logger


# Pattern to find JSON blocks in AI responses
JSON_BLOCK_PATTERN = re.compile(
    r'```(?:json)?\s*\n?(.*?)\n?```',
    re.DOTALL,
)


def parse_memory_updates(raw_response: str) -> Tuple[str, list[dict]]:
    """Parse the AI response to extract memory updates.

    Searches for ```json ... ``` blocks containing "memory_update".
    Extracts the list of {key, value} pairs.
    Returns the clean reply text (without the JSON block) and the updates list.

    Args:
        raw_response: The full raw text from the LLM.

    Returns:
        Tuple of (clean_reply_text, list_of_memory_updates).
    """
    memory_updates: list[dict] = []
    clean_text = raw_response

    for match in JSON_BLOCK_PATTERN.finditer(raw_response):
        json_str = match.group(1).strip()
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON block: {json_str[:200]}")
            continue

        if isinstance(data, dict) and "memory_update" in data:
            updates = data["memory_update"]
            if isinstance(updates, list):
                for item in updates:
                    if isinstance(item, dict) and "key" in item and "value" in item:
                        memory_updates.append({
                            "key": str(item["key"]),
                            "value": str(item["value"]),
                            "importance": item.get("importance", 1),
                            "confidence": item.get("confidence", 1.0),
                            "source": item.get("source", ""),
                        })
            # Remove the JSON block from the clean reply
            clean_text = clean_text.replace(match.group(0), "").strip()

    # Also try inline JSON without code fences
    if not memory_updates:
        # Look for {"memory_update": [...]} anywhere in the text
        inline_pattern = re.compile(
            r'\{\s*"memory_update"\s*:\s*\[(.*?)\]\s*\}',
            re.DOTALL,
        )
        match = inline_pattern.search(raw_response)
        if match:
            try:
                full_json = "{" + match.group(0)[1:]  # reconstruct
                # Actually use the original match
                data = json.loads(match.group(0))
                if isinstance(data, dict) and "memory_update" in data:
                    for item in data["memory_update"]:
                        if isinstance(item, dict) and "key" in item and "value" in item:
                            memory_updates.append({
                                "key": str(item["key"]),
                                "value": str(item["value"]),
                                "importance": item.get("importance", 1),
                                "confidence": item.get("confidence", 1.0),
                                "source": item.get("source", ""),
                            })
                    clean_text = clean_text.replace(match.group(0), "").strip()
            except json.JSONDecodeError:
                pass

    return clean_text, memory_updates
