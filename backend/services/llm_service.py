"""Unified, observable interface to OpenAI-compatible model providers."""

from __future__ import annotations

import time
from contextvars import ContextVar, Token
from typing import Any, Callable

from loguru import logger
from openai import OpenAI

from core.config import settings
from utils.json_parser import safe_json_parse


_llm_context: ContextVar[dict[str, str]] = ContextVar(
    "llm_context", default={"user_id": "system", "feature": "unknown"}
)


def set_llm_context(*, user_id: str, feature: str) -> Token:
    return _llm_context.set({"user_id": user_id or "anonymous", "feature": feature or "unknown"})


def reset_llm_context(token: Token) -> None:
    _llm_context.reset(token)


class LLMService:
    """One reusable client with timeout, retry, validation, and cost metadata logs."""

    def __init__(self) -> None:
        self._client = OpenAI(
            api_key=settings.llm_api_key or "not-configured",
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout,
            max_retries=settings.llm_max_retries,
        )
        self._model = settings.llm_model

    @property
    def model(self) -> str:
        return self._model

    @staticmethod
    def _sanitize(text: str) -> str:
        if not text:
            return text
        text = text.replace("\ufffd", "").replace("\x00", "")
        question_count = text.count("?") + text.count("？")
        total = max(len(text.replace(" ", "")), 1)
        if question_count / total > 0.6:
            return ""
        try:
            text.encode("utf-8").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            text = text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
        return text.strip()

    def _log_call(
        self,
        *,
        started: float,
        success: bool,
        response: Any = None,
        error: Exception | None = None,
    ) -> None:
        context = _llm_context.get()
        usage = getattr(response, "usage", None)
        fields = {
            "event": "ai_call",
            "user_id": context.get("user_id", "system"),
            "feature": context.get("feature", "unknown"),
            "model": self._model,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "success": success,
            "error_reason": type(error).__name__ if error else None,
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
        bound = logger.bind(**fields)
        if success:
            bound.info("ai_call")
        else:
            # Deliberately log only the exception class, never prompts or credentials.
            bound.warning("ai_call_failed")

    def _complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        request_timeout: float | None = None,
        max_retries: int | None = None,
    ) -> str:
        if not settings.llm_api_key:
            error = RuntimeError("AI 服务暂未配置，请稍后再试")
            self._log_call(started=time.perf_counter(), success=False, error=error)
            raise error

        client = self._client
        options: dict[str, Any] = {}
        if request_timeout is not None:
            options["timeout"] = max(1.0, float(request_timeout))
        if max_retries is not None:
            options["max_retries"] = max(0, int(max_retries))
        if options:
            client = self._client.with_options(**options)

        started = time.perf_counter()
        response = None
        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            content = self._sanitize(content or "")
            if not content:
                raise RuntimeError("AI returned an empty or invalid response")
            self._log_call(started=started, success=True, response=response)
            return content
        except Exception as exc:
            self._log_call(started=started, success=False, response=response, error=exc)
            if isinstance(exc, RuntimeError) and str(exc).startswith("AI 服务"):
                raise
            raise RuntimeError("AI 服务响应超时或不可用，请稍后重试") from exc

    def chat(
        self,
        user_message: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        request_timeout: float | None = None,
        max_retries: int | None = None,
    ) -> str:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        return self._complete(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout=request_timeout,
            max_retries=max_retries,
        )

    def chat_multi_turn(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        if not messages:
            raise ValueError("messages must not be empty")
        return self._complete(messages, temperature=temperature, max_tokens=max_tokens)

    def chat_json(
        self,
        user_message: str,
        system_prompt: str,
        *,
        validator: Callable[[dict[str, Any]], bool] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Request JSON and retry once with a repair prompt when validation fails."""
        raw = self.chat(user_message, system_prompt, temperature, max_tokens)
        parsed = safe_json_parse(raw)
        if isinstance(parsed, dict) and (validator is None or validator(parsed)):
            return parsed

        repair_prompt = (
            "Return only one valid JSON object matching the requested schema. "
            "Do not use Markdown fences. Repair this output:\n" + raw[:6000]
        )
        repaired = self.chat(
            repair_prompt,
            system_prompt,
            temperature=0.0,
            max_tokens=max_tokens,
            max_retries=0,
        )
        parsed = safe_json_parse(repaired)
        if not isinstance(parsed, dict) or (validator is not None and not validator(parsed)):
            raise RuntimeError("AI 返回格式异常，请稍后重试")
        return parsed

    def chat_stream(
        self,
        user_message: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ):
        if not settings.llm_api_key:
            error = RuntimeError("AI 服务暂未配置，请稍后再试")
            self._log_call(started=time.perf_counter(), success=False, error=error)
            raise error
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        started = time.perf_counter()
        try:
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
            self._log_call(started=started, success=True)
        except Exception as exc:
            self._log_call(started=started, success=False, error=exc)
            raise RuntimeError("AI 服务响应超时或不可用，请稍后重试") from exc


_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
