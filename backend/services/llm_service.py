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
            timeout=90.0,
            max_retries=2,
        )
        self._model = settings.llm_model

    @staticmethod
    def _sanitize(text: str) -> str:
        """Clean LLM output: fix encoding artifacts, strip garbled markers."""
        if not text:
            return text
        # Replace common encoding corruption patterns
        text = text.replace("\ufffd", "")  # Unicode replacement char
        text = text.replace("\x00", "")     # Null bytes
        # If the text is mostly ???, return empty to trigger fallback
        question_count = text.count("?") + text.count("\uff1f")
        total = max(len(text.replace(" ", "")), 1)
        if question_count / total > 0.6:
            return ""
        # Ensure valid UTF-8 round-trip
        try:
            text.encode("utf-8").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
        return text.strip()

    def chat(
        self,
        user_message: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Send a single-turn message to the LLM and return the reply."""
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
        content = LLMService._sanitize(content)
        if not content:
            raise RuntimeError("LLM returned empty or garbled response.")
        return content

    def chat_multi_turn(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        """Send a multi-turn conversation to the LLM."""
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
        content = LLMService._sanitize(content)
        if not content:
            raise RuntimeError("LLM returned empty or garbled response.")
        return content


# ── Singleton ────────────────────────────────────────────────────


    def chat_stream(
        self,
        user_message: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ):
        """Stream LLM response token by token."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        stream = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """Return the singleton LLMService instance (lazy init)."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
