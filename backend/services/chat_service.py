"""Chat Service — orchestrates the full chat pipeline.

Flow:
  User Input
    ↓
  Load Memory from DB
    ↓
  Build System Prompt (with user context)
    ↓
  Call DeepSeek / OpenAI
    ↓
  Parse AI response for memory updates (JSON extraction)
    ↓
  Save memory updates to DB
    ↓
  Save conversation messages to DB
    ↓
  Return reply
"""

import json
from typing import Optional, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from core.config import settings
from crud.conversation import conversation as conversation_crud
from crud.user import user as user_crud
from models.user import User
from schemas.chat import ChatRequest
from services.llm_service import LLMService
from services.memory_service import memory_service
from memory.prompts import SYSTEM_PROMPT, build_system_prompt_with_memory
from memory.extractor import parse_memory_updates


class ChatService:
    """Orchestrates the full chat interaction with memory extraction."""

    def __init__(self, llm_service: LLMService) -> None:
        self.llm = llm_service

    def chat(
        self,
        db: Session,
        *,
        user_id: str,
        message: str,
    ) -> str:
        """Process a single chat turn.

        Args:
            db: Database session.
            user_id: The user's ID.
            message: User's input text.

        Returns:
            The AI's reply text.

        Raises:
            NotFoundException: If the user doesn't exist.
            RuntimeError: If the LLM call fails.
        """
        # 1. Verify user exists
        user = user_crud.get(db, id=user_id)
        if user is None:
            from core.exceptions import NotFoundException
            raise NotFoundException(f"User {user_id} not found")

        # 2. Load user memory
        memory_context = memory_service.format_for_prompt(db, user_id=user_id)
        logger.debug(f"Memory context for user {user_id}:\n{memory_context}")

        # 3. Build system prompt
        system_prompt = build_system_prompt_with_memory(
            memory_context=memory_context,
            user_info=self._build_user_info(user),
        )

        # 4. Save user message
        conversation_crud.create(
            db,
            obj_in={
                "user_id": user_id,
                "role": "user",
                "content": message,
            },
        )

        # 5. Call LLM
        logger.info(f"Calling LLM for user={user_id}, msg_len={len(message)}")
        try:
            raw_response = self.llm.chat(
                user_message=message,
                system_prompt=system_prompt,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
        except Exception as e:
            logger.error(f"LLM call failed for user={user_id}: {e}")
            raise RuntimeError(f"LLM call failed: {e}") from e

        # 6. Parse memory updates from AI response
        reply_text, memory_updates = parse_memory_updates(raw_response)
        logger.debug(f"Extracted {len(memory_updates)} memory updates: {memory_updates}")

        # 7. Save memory updates
        if memory_updates and settings.memory_auto_extract:
            for item in memory_updates:
                try:
                    memory_service.save_memory(
                        db,
                        data=__import__("schemas.memory").memory.MemoryCreate(
                            user_id=user_id,
                            key=item["key"],
                            value=item["value"],
                            importance=item.get("importance", 1),
                        ),
                    )
                    logger.info(f"Auto-saved memory: user={user_id}, key={item['key']}, value={item['value']}")
                except Exception as e:
                    logger.warning(f"Failed to save memory update: {e}")

        # 8. Save assistant reply
        conversation_crud.create(
            db,
            obj_in={
                "user_id": user_id,
                "role": "assistant",
                "content": reply_text,
            },
        )

        return reply_text

    @staticmethod
    def _build_user_info(user: User) -> str:
        """Build a concise user info string from the User model."""
        parts: list[str] = []
        if user.nickname:
            parts.append(f"昵称: {user.nickname}")
        if user.major:
            parts.append(f"专业: {user.major}")
        if user.grade:
            parts.append(f"年级: {user.grade}")
        if user.target:
            parts.append(f"目标: {user.target}")
        return "\n".join(parts) if parts else "新用户"


# Singleton management
_chat_service: Optional[ChatService] = None


def get_chat_service(llm_service: Optional[LLMService] = None) -> ChatService:
    """Return the singleton ChatService instance."""
    global _chat_service
    if _chat_service is None:
        if llm_service is None:
            from services.llm_service import get_llm_service
            llm_service = get_llm_service()
        _chat_service = ChatService(llm_service)
    return _chat_service
