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
        self.assertEqual(result[0]["key"], "major")

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

    def test_chinese_to_english(self):
        self.assertEqual(self.norm("专业"), "专业")
        self.assertEqual(self.norm("年级"), "年级")
        self.assertEqual(self.norm("目标"), "目标")
        self.assertEqual(self.norm("兴趣"), "兴趣")

    def test_english_passthrough(self):
        self.assertEqual(self.norm("专业"), "专业")
        self.assertEqual(self.norm("目标"), "目标")

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