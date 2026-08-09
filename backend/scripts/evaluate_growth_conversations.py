# -*- coding: utf-8 -*-
"""Run the 40-case growth-conversation regression evaluation.

Usage:
    python backend/scripts/evaluate_growth_conversations.py
    python backend/scripts/evaluate_growth_conversations.py --live --workers 4
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from evals.growth_dialogues import DIALOGUE_CASES, cases_by_agent  # noqa: E402
from planning.knowledge import get_knowledge_context  # noqa: E402
from planning.router import PlanningRouter  # noqa: E402


FORBIDDEN_KNOWLEDGE_QUESTIONS = ("你知道", "你了解", "是否了解", "是否知道")
FORBIDDEN_HARSH_PHRASES = ("你必须", "你应该", "显然", "肯定会", "肯定是", "肯定不", "绝对", "不适合")
PREMATURE_PERSONALIZED_PHRASES = ("你更适合", "最适合你", "建议你选择", "建议你优先", "直接选择")
CONDITIONAL_MARKERS = ("如果", "前提", "假设", "情形", "取决于")


def _shares_user_signal(user_message: str, response_prefix: str) -> bool:
    ignored = {"我更", "比较", "目前", "大概", "可以", "就是", "这个", "那个", "还是"}
    compact = "".join(str(user_message).split())
    signals = {
        compact[index:index + 2]
        for index in range(max(0, len(compact) - 1))
        if compact[index:index + 2] not in ignored
    }
    return any(signal in response_prefix for signal in signals)


class OfflineAdvisoryLLM:
    """Deterministic structured output used for CI and code-contract checks."""

    def __init__(self, case: dict[str, Any]) -> None:
        self.case = case

    def chat(self, **_kwargs) -> str:
        ack_terms = self.case["ack_terms"]
        expected_terms = self.case["expected_terms"]
        acknowledgement = (
            f"你提到{ack_terms[0]}，这个取向我记下了。" if ack_terms else ""
        )
        insight = (
            f"从目前信息看，{expected_terms[0]}可以结合"
            f"{expected_terms[-1]}和时间成本逐步判断。"
        )
        if self.case["turn_analysis"].get("advice_level") == "conditional":
            insight = "如果未确认信息与当前判断一致，" + insight
        question = ""
        if self.case["expect_question"]:
            variable = self.case["turn_analysis"]["critical_variable"][:16]
            question = f"结合{variable}，你更倾向哪一种？"
        return json.dumps({
            "acknowledgement": acknowledgement,
            "insight": insight,
            "question": question,
        }, ensure_ascii=False)


def evaluate_response(case: dict[str, Any], response: str) -> dict[str, Any]:
    question_count = response.count("？") + response.count("?")
    violations: list[str] = []

    if len(response) > 160:
        violations.append(f"too_long:{len(response)}")
    expected_questions = 1 if case["expect_question"] else 0
    if question_count != expected_questions:
        violations.append(f"question_count:{question_count}!={expected_questions}")
    if any(phrase in response for phrase in FORBIDDEN_KNOWLEDGE_QUESTIONS):
        violations.append("knowledge_question")
    if any(phrase in response for phrase in FORBIDDEN_HARSH_PHRASES):
        violations.append("harsh_tone")
    advice_level = case["turn_analysis"].get("advice_level", "personalized")
    if advice_level == "general_only" and any(
        phrase in response for phrase in PREMATURE_PERSONALIZED_PHRASES
    ):
        violations.append("premature_personalized_advice")
    if advice_level == "conditional" and not any(
        marker in response for marker in CONDITIONAL_MARKERS
    ):
        violations.append("missing_uncertainty_marker")
    if case["ack_terms"] and not (
        any(term in response[:40] for term in case["ack_terms"])
        or _shares_user_signal(case["user_message"], response[:40])
    ):
        violations.append("missing_specific_acknowledgement")
    if case["turn_analysis"]["answerable_by_ai"] and case["expected_terms"] and not any(
        term in response for term in case["expected_terms"]
    ):
        violations.append("missing_domain_value")

    return {
        "id": case["id"],
        "agent_type": case["agent_type"],
        "response": response,
        "length": len(response),
        "question_count": question_count,
        "passed": not violations,
        "violations": violations,
    }


def run_case(case: dict[str, Any], llm: Any | None = None) -> dict[str, Any]:
    case_llm = llm or OfflineAdvisoryLLM(case)
    agent = PlanningRouter(case_llm).get_agent(case["agent_type"])
    agent.init_state(case["profile"])
    agent.state.last_asked_question = case["previous_question"]
    agent._last_asked_question = case["previous_question"]
    agent.state.record_follow_up(case["previous_question"], case["user_message"])
    knowledge = get_knowledge_context(
        case["agent_type"], case["knowledge_topics"]
    )["text"]
    response = agent._generate_dynamic_question(
        is_retry=False,
        last_answer=case["user_message"],
        turn_analysis=case["turn_analysis"],
        knowledge_context=knowledge,
    )
    return evaluate_response(case, response)


def run_evaluation(*, live: bool = False, workers: int = 4) -> list[dict[str, Any]]:
    if not live:
        return [run_case(case) for case in DIALOGUE_CASES]

    from services.llm_service import get_llm_service

    llm = get_llm_service()
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(run_case, case, llm): case["id"]
            for case in DIALOGUE_CASES
        }
        for future in as_completed(futures):
            case_id = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({
                    "id": case_id,
                    "agent_type": case_id.split("_", 1)[0],
                    "response": "",
                    "length": 0,
                    "question_count": 0,
                    "passed": False,
                    "violations": [f"runtime_error:{exc}"],
                })
    return sorted(results, key=lambda item: item["id"])


def print_report(results: list[dict[str, Any]], *, live: bool) -> None:
    labels = {"graduate": "考研", "career": "就业", "civil": "考公", "major": "转专业"}
    print(f"Growth conversation regression ({'live' if live else 'offline'})")
    print("=" * 68)
    total_passed = 0
    lengths: list[int] = []
    for agent_type, cases in cases_by_agent().items():
        ids = {case["id"] for case in cases}
        group = [result for result in results if result["id"] in ids]
        passed = sum(1 for result in group if result["passed"])
        total_passed += passed
        lengths.extend(result["length"] for result in group)
        average = sum(result["length"] for result in group) / max(1, len(group))
        print(f"{labels[agent_type]:<4}  {passed:>2}/{len(group):<2}  平均长度 {average:>5.1f}")
    print("-" * 68)
    print(f"总计  {total_passed}/{len(results)}  平均长度 {sum(lengths)/max(1, len(lengths)):.1f}")

    failed = [result for result in results if not result["passed"]]
    if failed:
        print("\n失败用例：")
        for result in failed:
            print(f"- {result['id']}: {', '.join(result['violations'])}")
            if result["response"]:
                print(f"  {result['response']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Use the configured real LLM")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    results = run_evaluation(live=args.live, workers=args.workers)
    print_report(results, live=args.live)
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
