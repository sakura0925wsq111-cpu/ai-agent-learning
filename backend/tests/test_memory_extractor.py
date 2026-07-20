# -*- coding: utf-8 -*-
"""Unit tests for async memory extractor and related components."""

from __future__ import annotations

import datetime
import json
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure backend is importable
sys.path.insert(0, r"D:i-agent-learningackend")


class TestParseExtractionResult(unittest.TestCase):
    """Tests for _parse_extraction_result in async_extractor."""

    def setUp(self):
        from memory.async_extractor import _parse_extraction_result
        self.parse = _parse_extraction_result

    def test_valid_json_response(self):
        """Should parse a valid JSON response correctly."""
        raw = json.dumps({
            "memories": [
                {"key": "专业", "value": "交通工程", "confidence": 1.0, "source": "用户说"},
                {"key": "年级", "value": "大二", "confidence": 0.9, "source": "推断"},
            ]
        }, ensure_ascii=False)
        result = self.parse(raw)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["key"], "专业")
        self.assertEqual(result[0]["value"], "交通工程")
        self.assertEqual(result[0]["confidence"], 1.0)

    def test_json_in_code_fence(self):
        """Should extract JSON from markdown code fence."""
        raw = '```json{"memories": [{"key": "goal", "value": "考研", "confidence": 1.0, "source": "用户说"}]}```'
        result = self.parse(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "goal")

    def test_empty_response(self):
        """Should return empty list for empty JSON."""
        raw = '{"memories": []}'
        result = self.parse(raw)
        self.assertEqual(len(result), 0)

    def test_invalid_json(self):
        """Should return empty list for invalid JSON."""
        result = self.parse("not json at all")
        self.assertEqual(result, [])

    def test_missing_memories_key(self):
        """Should return empty list when 'memories' key is missing."""
        result = self.parse('{"other": "data"}')
        self.assertEqual(result, [])

    def test_memories_not_list(self):
        """Should return empty list when 'memories' is not a list."""
        result = self.parse('{"memories": "not a list"}')
        self.assertEqual(result, [])

    def test_missing_fields_get_defaults(self):
        """Missing confidence/source should get defaults."""
        raw = json.dumps({"memories": [{"key": "test", "value": "val"}]})
        result = self.parse(raw)
        self.assertEqual(result[0]["confidence"], 0.5)
        self.assertEqual(result[0]["source"], "")

    def test_skip_non_dict_items(self):
        """Non-dict items in the memories list should be skipped."""
        raw = json.dumps({"memories": [{"key": "a", "value": "b"}, "not a dict", {"key": "c", "value": "d"}]})
        result = self.parse(raw)
        self.assertEqual(len(result), 2)

    def test_partial_json_with_noise(self):
        """Should handle JSON with surrounding text noise."""
        raw = 'Some text before {"memories": [{"key": "k", "value": "v", "confidence": 0.8, "source": "s"}]} and after'
        result = self.parse(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "k")


class TestExtractProfileFromHistory(unittest.TestCase):
    """Tests for extract_profile_from_history with mocked LLM."""

    def test_empty_messages_returns_empty(self):
        from memory.async_extractor import extract_profile_from_history
        result = extract_profile_from_history([])
        self.assertEqual(result, [])

    @patch("memory.async_extractor.get_llm_service")
    def test_extracts_and_parses(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.chat_multi_turn.return_value = json.dumps({
            "memories": [{"key": "major", "value": "CS", "confidence": 1.0, "source": "stated"}]
        })
        mock_get_llm.return_value = mock_llm

        from memory.async_extractor import extract_profile_from_history
        result = extract_profile_from_history([
            {"role": "user", "content": "我学计算机"},
        ])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "major")

    @patch("memory.async_extractor.get_llm_service")
    def test_retry_on_failure(self, mock_get_llm):
        mock_llm = MagicMock()
        # First call fails, second succeeds
        mock_llm.chat_multi_turn.side_effect = [
            RuntimeError("API error"),
            json.dumps({"memories": [{"key": "goal", "value": "就业", "confidence": 0.9, "source": "推断"}]}),
        ]
        mock_get_llm.return_value = mock_llm

        from memory.async_extractor import extract_profile_from_history
        result = extract_profile_from_history([
            {"role": "user", "content": "我想找工作"},
        ], max_retries=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(mock_llm.chat_multi_turn.call_count, 2)

    @patch("memory.async_extractor.get_llm_service")
    def test_returns_empty_on_all_failures(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.chat_multi_turn.side_effect = RuntimeError("Always fails")
        mock_get_llm.return_value = mock_llm

        from memory.async_extractor import extract_profile_from_history
        result = extract_profile_from_history([
            {"role": "user", "content": "hello"},
        ], max_retries=1)
        self.assertEqual(result, [])
        self.assertEqual(mock_llm.chat_multi_turn.call_count, 2)


class TestStructuredValue(unittest.TestCase):
    """Tests for parsed_value property and auto serialization."""

    def test_parsed_value_list(self):
        from schemas.memory import MemoryResponse
        resp = MemoryResponse(
            id="1", user_id="u1", key="skills", value='["Python","SQL"]',
            importance=5, confidence=1.0, source="", created_at=datetime.datetime(2026, 1, 1),
        )
        self.assertEqual(resp.parsed_value, ["Python", "SQL"])

    def test_parsed_value_dict(self):
        from schemas.memory import MemoryResponse
        resp = MemoryResponse(
            id="1", user_id="u1", key="prefs", value='{"city":"北京"}',
            importance=5, confidence=1.0, source="", created_at=datetime.datetime(2026, 1, 1),
        )
        self.assertEqual(resp.parsed_value, {"city": "北京"})

    def test_parsed_value_plain_string(self):
        from schemas.memory import MemoryResponse
        resp = MemoryResponse(
            id="1", user_id="u1", key="major", value="交通工程",
            importance=5, confidence=1.0, source="", created_at=datetime.datetime(2026, 1, 1),
        )
        self.assertEqual(resp.parsed_value, "交通工程")

    def test_serialize_value_list(self):
        from crud.memory import _serialize_value
        result = _serialize_value(["Python", "SQL"])
        self.assertEqual(result, '["Python", "SQL"]')

    def test_serialize_value_dict(self):
        from crud.memory import _serialize_value
        result = _serialize_value({"city": "北京"})
        self.assertEqual(result, '{"city": "北京"}')

    def test_serialize_value_string_passthrough(self):
        from crud.memory import _serialize_value
        result = _serialize_value("plain text")
        self.assertEqual(result, "plain text")


if __name__ == "__main__":
    unittest.main()
