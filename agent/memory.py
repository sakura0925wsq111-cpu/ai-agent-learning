"""Session persistence: JSON files and conversation index."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.settings import PROJECT_ROOT, Settings
from agent.schemas import (
    ConversationIndexEntry,
    Message,
    Phase,
    Session,
    new_session_id,
    now_iso,
)


class MemoryStore:
    """Read and write sessions to local JSON files."""

    def __init__(
        self,
        settings: Settings | None = None,
        data_dir: Path | None = None,
    ) -> None:
        if data_dir is not None:
            self.data_dir = data_dir
        elif settings is not None:
            self.data_dir = settings.data_dir
        else:
            self.data_dir = PROJECT_ROOT / "data"
        self.sessions_dir = self.data_dir / "sessions"
        self.index_path = self.data_dir / "conversations.json"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def create_session(self, decision_question: str) -> Session:
        """Create a new in-memory session (not yet saved)."""
        timestamp = now_iso()
        return Session(
            session_id=new_session_id(),
            decision_question=decision_question.strip(),
            phase=Phase.COLLECT,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def save_session(self, session: Session) -> Path:
        """Persist session detail and update the index."""
        session.updated_at = now_iso()
        session_path = self._session_path(session.session_id)

        with session_path.open("w", encoding="utf-8") as file:
            json.dump(session.to_dict(), file, ensure_ascii=False, indent=2)

        self._upsert_index(session)
        return session_path

    def load_session(self, session_id: str) -> Session:
        """Load a session by id."""
        session_path = self._session_path(session_id)
        if not session_path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")

        with session_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return Session.from_dict(data)

    def list_sessions(self) -> list[ConversationIndexEntry]:
        """Return all sessions from the index, newest first."""
        if not self.index_path.exists():
            return []

        with self.index_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        entries = [
            ConversationIndexEntry.from_dict(item)
            for item in data.get("conversations", [])
        ]
        return sorted(entries, key=lambda item: item.updated_at, reverse=True)

    def append_message(
        self,
        session: Session,
        *,
        role: str,
        content: str,
        phase: Phase | None = None,
        structured: dict[str, Any] | None = None,
    ) -> None:
        """Append a message to the session."""
        session.messages.append(
            Message(
                role=role,
                content=content,
                phase=(phase or session.phase).value,
                structured=structured,
            )
        )

    def _upsert_index(self, session: Session) -> None:
        entries = self.list_sessions()
        entry = ConversationIndexEntry(
            session_id=session.session_id,
            decision_question=session.decision_question,
            phase=session.phase.value,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

        updated: list[ConversationIndexEntry] = []
        found = False
        for existing in entries:
            if existing.session_id == session.session_id:
                updated.append(entry)
                found = True
            else:
                updated.append(existing)

        if not found:
            updated.append(entry)

        payload = {"conversations": [item.to_dict() for item in updated]}
        with self.index_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)


def _run_memory_test() -> None:
    """Quick manual test: python -m agent.memory"""
    store = MemoryStore()

    session = store.create_session("考研还是就业？")
    store.append_message(
        session,
        role="assistant",
        content="你好，我们先从你的现状聊起。",
        phase=Phase.COLLECT,
    )
    store.append_message(
        session,
        role="user",
        content="我是大三计算机专业，GPA 3.2。",
        phase=Phase.COLLECT,
    )
    session.collect_state.covered_dimensions = ["background"]
    session.collect_state.turn_count = 1

    saved_path = store.save_session(session)
    loaded = store.load_session(session.session_id)
    sessions = store.list_sessions()

    print("Saved to:", saved_path)
    print("Loaded question:", loaded.decision_question)
    print("Loaded messages:", len(loaded.messages))
    print("Index count:", len(sessions))
    print("Memory test OK.")


if __name__ == "__main__":
    _run_memory_test()
