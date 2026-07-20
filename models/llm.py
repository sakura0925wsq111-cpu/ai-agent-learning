"""DeepSeek API wrapper using the OpenAI-compatible SDK."""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from config.settings import Settings, get_settings

Message = dict[str, str]


class LLMClient:
    """Thin wrapper around DeepSeek chat completions."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = OpenAI(
            api_key=self.settings.deepseek_api_key,
            base_url=self.settings.deepseek_base_url,
        )

    def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Send a chat request and return plain text content."""
        response = self._client.chat.completions.create(
            model=self.settings.deepseek_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned empty content.")
        return content

    def chat_json(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        max_retries: int = 1,
    ) -> dict[str, Any]:
        """
        Request JSON output and parse it into a dict.

        Retries once if the model returns invalid JSON.
        """
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            response = self._client.chat.completions.create(
                model=self.settings.deepseek_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            if not content:
                last_error = RuntimeError("LLM returned empty content.")
                continue

            try:
                parsed = json.loads(content)
                if not isinstance(parsed, dict):
                    raise ValueError("Expected a JSON object at the top level.")
                return parsed
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                if attempt < max_retries:
                    messages = messages + [
                        {
                            "role": "user",
                            "content": (
                                "Your previous response was not valid JSON. "
                                "Reply with a single valid JSON object only."
                            ),
                        }
                    ]

        raise RuntimeError(
            f"Failed to parse JSON from LLM after {max_retries + 1} attempts."
        ) from last_error


def _run_connectivity_test() -> None:
    """Quick manual test: python -m models.llm"""
    print("Testing DeepSeek API connection...")
    client = LLMClient()
    reply = client.chat(
        [
            {
                "role": "system",
                "content": "You are a helpful assistant. Reply briefly in Chinese.",
            },
            {"role": "user", "content": "用一句话介绍你自己。"},
        ],
        max_tokens=100,
    )
    print("Text reply:", reply)

    json_reply = client.chat_json(
        [
            {
                "role": "system",
                "content": 'Reply with JSON only: {"status": "ok", "message": "..."}',
            },
            {"role": "user", "content": "Confirm connection."},
        ],
        max_tokens=100,
    )
    print("JSON reply:", json_reply)
    print("DeepSeek API connection OK.")


if __name__ == "__main__":
    _run_connectivity_test()
