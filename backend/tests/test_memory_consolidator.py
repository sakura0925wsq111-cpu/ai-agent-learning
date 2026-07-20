# -*- coding: utf-8 -*-
"""Unit tests for the memory consolidator."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, r"D:\ai-agent-learning\backend")


class TestKeyPrefixExtraction(unittest.TestCase):
    def setUp(self):
        from memory.consolidator import _extract_key_prefix
        self.extract = _extract_key_prefix

    def test_dash_separator(self):
        self.assertEqual(self.extract("skill-Python"), "skill")

    def test_no_separator(self):
        self.assertEqual(self.extract("major"), "major")

    def test_dash_takes_priority(self):
        self.assertEqual(self.extract("a_b-c"), "a_b")


class TestConsolidateMemories(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()

    def _make_mock_memory(self, id_str, key, value, importance=1):
        mem = MagicMock()
        mem.id = id_str
        mem.key = key
        mem.value = value
        mem.importance = importance
        return mem

    def test_below_threshold_skips(self):
        mock_memories = [self._make_mock_memory("1", "major", "CS") for _ in range(10)]
        with patch("memory.consolidator.memory_crud") as mock_crud:
            mock_crud.get_by_user.return_value = mock_memories
            from memory.consolidator import consolidate_memories
            result = consolidate_memories(self.mock_db, "user1")
            self.assertEqual(result, 0)

    @patch("memory.consolidator.get_llm_service")
    def test_consolidates_group(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.chat_multi_turn.return_value = '{"key": "skill_summary", "value": "Python, SQL, Java", "confidence": 0.7}'
        mock_get_llm.return_value = mock_llm
        memories = [
            self._make_mock_memory("1", "skill-Python", "good", 5),
            self._make_mock_memory("2", "skill-SQL", "basic", 3),
            self._make_mock_memory("3", "skill-Java", "beginner", 2),
        ]
        for i in range(38):
            memories.append(self._make_mock_memory(str(i + 10), "attr" + str(i), "val" + str(i), 1))
        with patch("memory.consolidator.memory_crud") as mock_crud:
            mock_crud.get_by_user.return_value = memories
            mock_crud.delete_many_by_keys.return_value = 3
            from memory.consolidator import consolidate_memories
            result = consolidate_memories(self.mock_db, "user1")
            self.assertGreater(result, 0)
            mock_crud.delete_many_by_keys.assert_called()

    @patch("memory.consolidator.get_llm_service")
    def test_no_consolidatable_groups(self, mock_get_llm):
        memories = [
            self._make_mock_memory(str(i), "unique_key_" + str(i), "value_" + str(i), 1)
            for i in range(45)
        ]
        with patch("memory.consolidator.memory_crud") as mock_crud:
            mock_crud.get_by_user.return_value = memories
            from memory.consolidator import consolidate_memories
            result = consolidate_memories(self.mock_db, "user1")
            self.assertEqual(result, 0)

    @patch("memory.consolidator.get_llm_service")
    def test_fallback_on_parse_failure(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.chat_multi_turn.return_value = "not valid json at all"
        mock_get_llm.return_value = mock_llm
        memories = [
            self._make_mock_memory("1", "skill-Python", "good", 5),
            self._make_mock_memory("2", "skill-SQL", "basic", 3),
        ]
        for i in range(39):
            memories.append(self._make_mock_memory(str(i + 10), "attr" + str(i), "val" + str(i), 1))
        with patch("memory.consolidator.memory_crud") as mock_crud:
            mock_crud.get_by_user.return_value = memories
            mock_crud.delete_many_by_keys.return_value = 2
            from memory.consolidator import consolidate_memories
            result = consolidate_memories(self.mock_db, "user1")
            self.assertGreater(result, 0)
            call_args = mock_crud.upsert.call_args
            self.assertIn("consolidated from 2 memories", call_args[1]["source"])


if __name__ == "__main__":
    unittest.main()

