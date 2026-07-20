# -*- coding: utf-8 -*-
'''QuestionFlowEngine — manages the card-based question progression.

Replaces the old LLM-driven free conversation with a deterministic
program-controlled question flow:

    5 core questions → (optional 2 supplementary) → LLM analysis → report

Key responsibilities:
- Track current question index
- Determine the next question
- Detect ambiguous answers ('not sure', 'anything is fine')
- Decide when to inject supplementary questions
- Signal completion when enough info is gathered
'''

from __future__ import annotations

from typing import Any

from loguru import logger

from questions import AGENT_QUESTIONS, AMBIGUOUS_ANSWERS
from schemas.growth import (
    AgentType,
    Question,
    Answer,
    SessionStatus,
)

# ── Constants ──────────────────────────────────────────────────

CORE_QUESTION_COUNT: int = 5
MAX_SUPPLEMENTARY: int = 2
MAX_TOTAL_QUESTIONS: int = CORE_QUESTION_COUNT + MAX_SUPPLEMENTARY  # 7


class QuestionFlowEngine:
    '''Deterministic question-flow engine for growth agents.

    Usage:
        engine = QuestionFlowEngine(agent_type='career')
        question = engine.get_current_question()

        # User answers
        state = engine.submit_answer(answer)

        # Check if done
        if state['status'] == SessionStatus.REPORT_READY:
            answers = engine.collect_answers()
            # ... send answers to LLM for final analysis
    '''

    def __init__(self, agent_type: str = 'career') -> None:
        if agent_type not in AGENT_QUESTIONS:
            raise ValueError(
                f'Unknown agent_type: {agent_type}. '
                f'Available: {list(AGENT_QUESTIONS.keys())}'
            )
        self.agent_type: str = agent_type
        config = AGENT_QUESTIONS[agent_type]
        self._core_questions: list[dict[str, Any]] = config['questions']
        self._supplementary_questions: list[dict[str, Any]] = config['supplementary']

        # Runtime state
        self._current_index: int = 0
        self._answers: list[Answer] = []
        self._ambiguous_count: int = 0
        self._supplementary_used: int = 0
        self._in_supplementary: bool = False
        self._finished: bool = False
        self._status: SessionStatus = SessionStatus.WAITING_SELECTION

    # ── Public API ─────────────────────────────────────────────

    def get_current_question(self) -> Question:
        '''Return the current question card for the frontend.

        Raises:
            RuntimeError: If the flow is already finished.
        '''
        if self._finished:
            raise RuntimeError('Question flow is already finished. Generate report instead.')

        q = self._get_question_at(self._current_index)
        total = self._estimate_total()
        return Question(
            id=q['id'],
            title=q['title'],
            options=q['options'],
            allow_custom=q.get('allow_custom', False),
            required=q.get('required', True),
            index=self._current_index + 1,
            total=total,
        )

    def submit_answer(self, answer: Answer) -> dict[str, Any]:
        '''Process a user's answer and advance the flow.

        Args:
            answer: The user's selected option (and optional custom text).

        Returns:
            Dict with keys: status, finished, progress, next_question (or None).
        '''
        if self._finished:
            raise RuntimeError('Question flow is already finished.')

        # ── 1. Save the answer ──
        self._answers.append(answer)

        # ── 2. Detect ambiguous answer ──
        answer_text = answer.custom_text or answer.selected_option or ''
        if self._is_ambiguous(answer_text):
            self._ambiguous_count += 1
            logger.debug(
                f'[QuestionEngine] Ambiguous answer detected: {answer_text!r} '
                f'(count={self._ambiguous_count})'
            )

        # ── 3. Advance the flow ──
        self._current_index += 1

        # ── 4. Decide what to do next ──

        # Check if we've finished all core questions
        core_done = self._current_index >= len(self._core_questions)

        if not core_done:
            # Still in core questions
            self._status = SessionStatus.WAITING_SELECTION
            next_q = self.get_current_question()
            return self._build_response(False, self._status, next_q)

        # Core questions done — should we add supplementary?
        if (
            self._ambiguous_count >= 2
            and self._supplementary_used < MAX_SUPPLEMENTARY
        ):
            # Need supplementary
            self._in_supplementary = True
            self._supplementary_used += 1
            sup_idx = self._supplementary_used - 1
            sup_q = self._supplementary_questions[sup_idx]
            self._status = SessionStatus.WAITING_SELECTION
            question = Question(
                id=sup_q['id'],
                title=sup_q['title'],
                options=sup_q['options'],
                allow_custom=sup_q.get('allow_custom', True),
                required=sup_q.get('required', True),
                index=self._current_index + 1,
                total=self._estimate_total(),
            )
            return self._build_response(False, self._status, question)

        # All done — trigger analysis
        self._finished = True
        self._status = SessionStatus.REPORT_READY
        return self._build_response(True, self._status, None)

    def collect_answers(self) -> list[dict[str, Any]]:
        '''Return all collected answers as a list of dicts for LLM analysis.'''
        return [
            {
                'question_id': a.question_id,
                'answer': a.custom_text or a.selected_option or '',
            }
            for a in self._answers
        ]

    def get_progress(self) -> float:
        '''Return progress as a float between 0.0 and 1.0.'''
        total = self._estimate_total()
        answered = len(self._answers)
        return min(1.0, answered / total) if total > 0 else 0.0

    @property
    def finished(self) -> bool:
        return self._finished

    @property
    def status(self) -> SessionStatus:
        return self._status

    @property
    def answers(self) -> list[Answer]:
        return self._answers

    # ── Private helpers ────────────────────────────────────────

    def _get_question_at(self, index: int) -> dict[str, Any]:
        '''Get question data at the given index (0-based).'''
        if index < len(self._core_questions):
            return self._core_questions[index]
        # Map into supplementary
        sup_idx = index - len(self._core_questions)
        if sup_idx < len(self._supplementary_questions):
            return self._supplementary_questions[sup_idx]
        raise IndexError(f'Question index {index} out of range.')

    def _estimate_total(self) -> int:
        '''Estimate total questions for progress display.'''
        if self._ambiguous_count >= 2:
            return CORE_QUESTION_COUNT + MAX_SUPPLEMENTARY
        return CORE_QUESTION_COUNT

    @staticmethod
    def _is_ambiguous(text: str) -> bool:
        if not text:
            return True
        return text.strip() in AMBIGUOUS_ANSWERS

    def _build_response(
        self,
        finished: bool,
        status: SessionStatus,
        next_question: Question | None,
    ) -> dict[str, Any]:
        return {
            'finished': finished,
            'status': status,
            'progress': self.get_progress(),
            'next_question': next_question,
        }

    # ── Serialization (for DB persistence) ─────────────────────

    def to_dict(self) -> dict[str, Any]:
        '''Serialize engine state for database storage.'''
        return {
            'agent_type': self.agent_type,
            'current_index': self._current_index,
            'answers': [a.model_dump() for a in self._answers],
            'ambiguous_count': self._ambiguous_count,
            'supplementary_used': self._supplementary_used,
            'in_supplementary': self._in_supplementary,
            'finished': self._finished,
            'status': self._status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'QuestionFlowEngine':
        '''Restore engine state from serialized dict.'''
        engine = cls(agent_type=data['agent_type'])
        engine._current_index = data['current_index']
        engine._answers = [Answer(**a) for a in data['answers']]
        engine._ambiguous_count = data['ambiguous_count']
        engine._supplementary_used = data['supplementary_used']
        engine._in_supplementary = data['in_supplementary']
        engine._finished = data['finished']
        engine._status = SessionStatus(data['status'])
        return engine
