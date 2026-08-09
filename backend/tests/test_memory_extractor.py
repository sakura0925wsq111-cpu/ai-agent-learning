# -*- coding: utf-8 -*-
"""Unit tests for memory extractor, key normalization, and conflict history."""

from __future__ import annotations

import datetime
import json
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, r"D:\ai-agent-learning\backend")


class TestParseExtractionResult(unittest.TestCase):
    def setUp(self):
        from memory.async_extractor import _parse_extraction_result
        self.parse = _parse_extraction_result

    def test_valid_json_with_memory_type(self):
        raw = json.dumps({"memories": [{"key": "major", "value": "CS", "confidence": 1.0, "source": "s", "memory_type": "profile", "importance": 5}]})
        result = self.parse(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["memory_type"], "profile")
        self.assertEqual(result[0]["key"], "专业")

    def test_aliases_are_deduplicated_by_confidence(self):
        raw = json.dumps({"memories": [
            {"key": "major", "value": "计算机", "confidence": 0.7},
            {"key": "专业", "value": "软件工程", "confidence": 0.9},
        ]}, ensure_ascii=False)
        result = self.parse(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "专业")
        self.assertEqual(result[0]["value"], "软件工程")

    def test_missing_memory_type_defaults_to_fact(self):
        raw = json.dumps({"memories": [{"key": "note", "value": "x"}]})
        result = self.parse(raw)
        self.assertEqual(result[0]["memory_type"], "fact")

    def test_empty_response(self):
        self.assertEqual(self.parse('{"memories": []}'), [])

    def test_invalid_json_returns_empty(self):
        self.assertEqual(self.parse("not json"), [])


class TestInferMemoryType(unittest.TestCase):
    def setUp(self):
        from memory.async_extractor import _infer_memory_type
        self.infer = _infer_memory_type
    def test_infer_profile(self):
        self.assertEqual(self.infer("major"), "profile")
    def test_infer_goal(self):
        self.assertEqual(self.infer("goal"), "goal")
    def test_infer_action(self):
        self.assertEqual(self.infer("task"), "action")
    def test_infer_unknown_as_fact(self):
        self.assertEqual(self.infer("xyz"), "fact")

class TestExtractProfileFromHistory(unittest.TestCase):
    def test_empty_messages_returns_empty(self):
        from memory.async_extractor import extract_profile_from_history
        self.assertEqual(extract_profile_from_history([]), [])

    @patch("memory.async_extractor.get_llm_service")
    def test_extracts_and_parses(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.chat_multi_turn.return_value = json.dumps({"memories": [{"key": "major", "value": "CS", "confidence": 1.0, "source": "s", "memory_type": "profile"}]})
        mock_get_llm.return_value = mock_llm
        from memory.async_extractor import extract_profile_from_history
        result = extract_profile_from_history([{"role": "user", "content": "I study CS"}])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "专业")

    @patch("memory.async_extractor.get_llm_service")
    def test_retry_on_failure(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.chat_multi_turn.side_effect = [
            RuntimeError("API error"),
            json.dumps({"memories": [{"key": "goal", "value": "job", "confidence": 0.9, "source": "i", "memory_type": "goal"}]}),
        ]
        mock_get_llm.return_value = mock_llm
        from memory.async_extractor import extract_profile_from_history
        result = extract_profile_from_history([{"role": "user", "content": "I want a job"}], max_retries=1)
        self.assertEqual(len(result), 1)

    @patch("memory.async_extractor.get_llm_service")
    def test_returns_empty_on_all_failures(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.chat_multi_turn.side_effect = RuntimeError("Always fails")
        mock_get_llm.return_value = mock_llm
        from memory.async_extractor import extract_profile_from_history
        result = extract_profile_from_history([{"role": "user", "content": "hello"}], max_retries=1)
        self.assertEqual(result, [])

class TestKeyNormalization(unittest.TestCase):
    def setUp(self):
        from crud.memory import normalize_key
        self.norm = normalize_key

    def test_chinese_keys_are_canonical(self):
        self.assertEqual(self.norm("专业"), "专业")
        self.assertEqual(self.norm("年级"), "年级")
        self.assertEqual(self.norm("目标"), "目标")
        self.assertEqual(self.norm("兴趣"), "兴趣")

    def test_english_aliases_map_to_canonical_keys(self):
        self.assertEqual(self.norm("major"), "专业")
        self.assertEqual(self.norm("goal"), "目标")
        self.assertEqual(self.norm("career_direction"), "职业")

    def test_unknown_key_passthrough(self):
        self.assertEqual(self.norm("custom_tag"), "custom_tag")

    def test_compound_key_normalization(self):
        self.assertEqual(self.norm("技能-Python"), "技能-Python")

    def test_empty_key(self):
        self.assertEqual(self.norm(""), "")

    def test_case_insensitive(self):
        self.assertEqual(self.norm("职业方向"), "职业")
        self.assertEqual(self.norm("性格特质"), "性格")

    def test_synonym_dedup(self):
        self.assertEqual(self.norm("目标"), self.norm("目标"))
        self.assertEqual(self.norm("职业方向"), self.norm("职业"))

    def test_extractor_level_normalization(self):
        from memory.async_extractor import _normalize_extracted_key
        self.assertEqual(_normalize_extracted_key("性格特质"), "性格")


class TestConflictSafeMemory(unittest.TestCase):
    def setUp(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from database.base import Base
        import models  # noqa: F401 - registers all mapped tables
        from models.user import User

        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user_id = "user-memory-test"
        self.db.add(User(id=self.user_id, name="测试用户", nickname="测试用户"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_alias_duplicate_keeps_one_strongest_row(self):
        from crud.memory import memory

        first = memory.upsert(
            self.db, user_id=self.user_id, key="major", value="计算机",
            memory_type="profile", confidence=0.9, source="conversation",
        )
        duplicate = memory.upsert(
            self.db, user_id=self.user_id, key="专业", value="计算机",
            memory_type="profile", confidence=0.5, source="conversation",
        )
        rows = list(memory.get_by_user(self.db, user_id=self.user_id))
        self.assertEqual(first.id, duplicate.id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].key, "专业")
        self.assertEqual(rows[0].confidence, 0.9)
        self.assertEqual(json.loads(rows[0].conflict_history), [])

    def test_lower_conflict_is_rejected_and_authoritative_edit_replaces(self):
        from crud.memory import memory

        memory.upsert(
            self.db, user_id=self.user_id, key="grade", value="大三",
            memory_type="profile", confidence=0.9, source="growth_turn:s1",
        )
        rejected = memory.upsert(
            self.db, user_id=self.user_id, key="年级", value="大二",
            memory_type="profile", confidence=0.4, source="conversation",
        )
        self.assertEqual(rejected.value, "大三")
        history = json.loads(rejected.conflict_history)
        self.assertEqual(history[-1]["status"], "rejected_lower_confidence")

        replaced = memory.upsert(
            self.db, user_id=self.user_id, key="年级", value="大四",
            memory_type="profile", confidence=0.2, source="user_edit",
        )
        self.assertEqual(replaced.value, "大四")
        history = json.loads(replaced.conflict_history)
        self.assertEqual(history[-1]["status"], "replaced")

        # Routine login sync and sandbox inference must not undo an explicit edit.
        for source in ("user_profile_sync", "sandbox_profile:s1", "user_profile_sync"):
            protected = memory.upsert(
                self.db, user_id=self.user_id, key="grade", value="大三",
                memory_type="profile", confidence=0.9, source=source,
            )
        self.assertEqual(protected.value, "大四")
        repeated = [
            item for item in json.loads(protected.conflict_history)
            if item["value"] == "大三" and item["source"] == "user_profile_sync"
        ]
        self.assertEqual(len(repeated), 1)

    def test_context_is_separate_and_round_trips(self):
        from services.memory_service import MemoryService

        service = MemoryService()
        payload = {
            "session_id": "sandbox-1", "user_id": self.user_id,
            "discovery_history": [{"q": "更看重什么？", "a": "稳定"}],
        }
        service.save_context(
            self.db, user_id=self.user_id, context_kind="sandbox",
            context_id="sandbox-1", payload=payload,
        )
        self.assertEqual(
            service.load_context(
                self.db, user_id=self.user_id, context_kind="sandbox",
                context_id="sandbox-1",
            ),
            payload,
        )
        self.assertEqual(service.load_memory_count(self.db, user_id=self.user_id), 0)
        self.assertEqual(len(service.load_context_metadata(self.db, user_id=self.user_id)), 1)

    def test_expired_context_is_not_loaded(self):
        from datetime import timedelta, timezone
        from crud.memory import memory
        from services.memory_service import MemoryService

        memory.upsert(
            self.db, user_id=self.user_id, key="context:sandbox:expired",
            value='{"session_id":"expired"}', memory_type="context",
            confidence=1.0, source="sandbox_context:expired",
            expires_at=datetime.datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        service = MemoryService()
        self.assertIsNone(service.load_context(
            self.db, user_id=self.user_id, context_kind="sandbox", context_id="expired",
        ))
        self.assertEqual(service.load_context_metadata(self.db, user_id=self.user_id), [])

    def test_growth_agents_keep_separate_goals_and_plans(self):
        from services.memory_service import MemoryService

        service = MemoryService()
        service.save_batch(self.db, user_id=self.user_id, items=[
            {"key": "growth:career:goal", "value": "拿到后端开发 offer", "memory_type": "goal"},
            {"key": "growth:career:action_plan", "value": "完成两个项目", "memory_type": "action"},
            {"key": "growth:graduate:goal", "value": "考取研究生", "memory_type": "goal"},
        ])
        career = service.load_growth_context(
            self.db, user_id=self.user_id, agent_type="career",
        )
        graduate = service.load_growth_context(
            self.db, user_id=self.user_id, agent_type="graduate",
        )
        self.assertEqual(career["goal"], "拿到后端开发 offer")
        self.assertEqual(career["action_plan"], "完成两个项目")
        self.assertEqual(graduate["goal"], "考取研究生")
        self.assertNotEqual(career["goal"], graduate["goal"])

class TestStructuredValue(unittest.TestCase):
    def test_parsed_value_list(self):
        from schemas.memory import MemoryResponse
        resp = MemoryResponse(
            id="1", user_id="u1", key="skills", value='["Python","SQL"]',
            importance=5, confidence=1.0, source="", memory_type="profile",
            created_at=datetime.datetime(2026, 1, 1),
        )
        self.assertEqual(resp.parsed_value, ["Python", "SQL"])

    def test_parsed_value_plain_string(self):
        from schemas.memory import MemoryResponse
        resp = MemoryResponse(
            id="1", user_id="u1", key="major", value="CS",
            importance=5, confidence=1.0, source="", memory_type="profile",
            created_at=datetime.datetime(2026, 1, 1),
        )
        self.assertEqual(resp.parsed_value, "CS")

    def test_serialize_value_list(self):
        from crud.memory import _serialize_value
        self.assertEqual(_serialize_value(["Python", "SQL"]), '["Python", "SQL"]')

    def test_serialize_value_string(self):
        from crud.memory import _serialize_value
        self.assertEqual(_serialize_value("plain"), "plain")


if __name__ == "__main__":
    unittest.main()
