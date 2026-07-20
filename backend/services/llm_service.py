"""LLM service — unified interface to language model APIs.

Supports any OpenAI-compatible provider (DeepSeek, Qwen, OpenAI, etc.)
by switching LLM_BASE_URL / LLM_API_KEY / LLM_MODEL in .env.
"""

from openai import OpenAI

from core.config import settings


class LLMService:
    """Encapsulates LLM API calls.

    Singleton — create once at startup, reuse across all requests.
    """

    def __init__(self) -> None:
        self._client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=30.0,
            max_retries=1,
        )
        self._model = settings.llm_model

    def chat(
        self,
        user_message: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Send a single-turn message to the LLM and return the reply.

        Args:
            user_message: The user's input text.
            system_prompt: Optional system-level instruction.
            temperature: Sampling temperature (0.0-2.0).
            max_tokens: Max tokens in the response.

        Returns:
            The model's text response.

        Raises:
            RuntimeError: If the API call fails or returns empty content.
        """
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned empty response.")
        return content

    def chat_multi_turn(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        """Send a multi-turn conversation to the LLM.

        Args:
            messages: List of {"role": "...", "content": "..."} dicts.
                      Must include at least one message.
            temperature: Sampling temperature (lower for structured output).
            max_tokens: Max tokens in the response.

        Returns:
            The model's text response.

        Raises:
            RuntimeError: If the API call fails or returns empty content.
        """
        if not messages:
            raise ValueError("messages must not be empty")

        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned empty response.")
        return content


# ── Singleton ────────────────────────────────────────────────────

_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """Return the singleton LLMService instance (lazy init)."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
