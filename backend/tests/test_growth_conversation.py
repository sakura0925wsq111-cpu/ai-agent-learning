# -*- coding: utf-8 -*-

from __future__ import annotations

import unittest
import json
import os
import tempfile

from planning.agents.graduate import GraduatePlanningAgent
from planning.conversation import analyze_turn, normalize_advisory_text
from planning.knowledge import get_knowledge_context
from planning.readiness import evaluate_advice_readiness
from planning.graph import build_growth_graph
from planning.router import PlanningRouter
from planning.state import PlanningState, WorkflowStep, MAX_FOLLOW_UP_ROUNDS
from sandbox.prompts.discovery import DISCOVERY_SYSTEM_PROMPT
from sandbox.orchestrator import DecisionSandbox
from evals.growth_dialogues import DIALOGUE_CASES, cases_by_agent
from scripts.evaluate_growth_conversations import run_evaluation
from sandbox.state import MAX_TOTAL_QUESTIONS, SandboxPhase, SandboxSession


class _FakeLLM:
    def __init__(self, *, analysis: str | None = None, response: str = "") -> None:
        self.analysis = analysis
        self.response = response
        self.calls: list[dict] = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        if "单轮分析器" in kwargs.get("system_prompt", ""):
            if self.analysis is None:
                raise RuntimeError("analysis unavailable")
            return self.analysis
        return self.response

    def chat_stream(self, *args, **kwargs):
        for index in range(0, len(self.response), 17):
            yield self.response[index:index + 17]


class _SandboxReportLLM:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        if "中立的对比分析师" in kwargs.get("system_prompt", ""):
            return json.dumps({
                "projections": [
                    {
                        "core_insight": "就业可以较快验证方向",
                        "time_projection": {"short_term": "完成岗位调研"},
                        "strengths": [], "challenges": [], "best_for": "重视实践的人", "deal_breakers": "",
                    },
                    {
                        "core_insight": "考研适合需要学历门槛的目标",
                        "time_projection": {"short_term": "完成院校调研"},
                        "strengths": [], "challenges": [], "best_for": "目标明确的人", "deal_breakers": "",
                    },
                ],
                "comparison_matrix": {
                    "dimensions": ["匹配度", "风险", "时间成本"],
                    "scores": {"career": [8, 4, 3], "graduate": [7, 5, 8]},
                },
                "summary": "两条路径均可行，需要结合时间成本选择。",
            }, ensure_ascii=False)
        return json.dumps({
            "strengths": [{"point": "基础匹配", "detail": "已有相关积累"}],
            "challenges": [{"point": "需要持续投入", "detail": "需安排时间", "level": "medium"}],
            "best_for": "目标明确的用户", "deal_breakers": "无法投入时间",
            "time_projection": {"short_term": "完成信息收集", "mid_term": "形成阶段成果", "long_term": "进入目标方向"},
            "key_requirements": ["持续投入"], "risk_summary": "时间投入风险",
        }, ensure_ascii=False)

class GrowthConversationTests(unittest.TestCase):
    def test_follow_up_question_cap_is_five(self):
        self.assertEqual(MAX_FOLLOW_UP_ROUNDS, 5)
        self.assertEqual(MAX_TOTAL_QUESTIONS, 5)

    def test_sandbox_question_cap_counts_only_visible_prompts(self):
        session = SandboxSession(session_id="question-cap", user_id="u1")
        for index in range(7):
            session.mark_question_asked(f"问题{index + 1}")

        self.assertEqual(session.questions_asked, 5)
        restored = SandboxSession.from_dict(session.to_dict())
        self.assertEqual(restored.questions_asked, 5)
        self.assertFalse(restored.can_ask_more())

    def test_long_advisory_text_trims_at_sentence_boundary(self):
        text = (
            "计算机就业不完全依赖研究生学历，工程实践岗位更看重项目与实习。"
            "算法和研究型岗位通常更重视研究生阶段训练。"
            "一个低成本验证动作是去招聘网站浏览目标岗位并记录要求。"
            "你目前对哪类技术问题更有热情？"
        )

        result = normalize_advisory_text(text, 80)

        self.assertLessEqual(len(result), 80)
        self.assertEqual(result.count("？"), 1)
        self.assertNotIn("招聘网站浏…", result)

    def test_each_direction_has_a_personalized_advice_standard(self):
        fixtures = {
            "graduate": ["target", "foundation", "motivation"],
            "career": ["target", "evidence", "preferences"],
            "civil": ["motivation", "target", "foundation"],
            "major": ["reason", "target", "foundation"],
        }
        for agent_type, dimensions in fixtures.items():
            with self.subTest(agent_type=agent_type):
                history = [
                    {"q": key, "a": "已提供具体信息", "dimension": key}
                    for key in dimensions
                ]
                result = evaluate_advice_readiness(
                    agent_type,
                    user_profile={"major": "计算机", "grade": "大三"},
                    follow_up_history=history,
                    questions_asked=3,
                )
                self.assertTrue(result["ready_for_personalized_advice"])
                self.assertEqual(result["advice_level"], "personalized")

    def test_missing_required_dimension_blocks_personalized_advice(self):
        result = evaluate_advice_readiness(
            "career",
            user_profile={"major": "计算机", "grade": "大三", "target": "后端"},
            follow_up_history=[
                {"q": "城市", "a": "杭州", "dimension": "preferences"},
                {"q": "强度", "a": "不接受长期加班", "dimension": "constraints"},
            ],
            questions_asked=2,
        )
        self.assertFalse(result["ready_for_personalized_advice"])
        self.assertEqual(result["advice_level"], "general_only")
        self.assertEqual(result["next_dimension"], "evidence")

    def test_user_information_question_is_not_miscounted_as_a_personal_answer(self):
        result = evaluate_advice_readiness(
            "graduate",
            user_profile={"major": "计算机", "grade": "大三"},
            questions_asked=1,
            current_question="你更倾向哪类目标岗位？",
            current_dimension="target",
            current_answer="考研和就业的薪资区别大吗？",
        )
        self.assertEqual(result["current_availability"], "not_answered")
        self.assertNotIn("target", result["covered_dimensions"])
        self.assertNotIn("target", result["unavailable_dimensions"])
        self.assertEqual(result["next_dimension"], "target")

    def test_unknown_answer_is_not_reasked_or_counted_as_information(self):
        llm = _FakeLLM(response=json.dumps({
            "acknowledgement": "这项暂时不确定也没关系。",
            "insight": "可以先从当前基础判断准备空间。",
            "question": "你目前的数学和英语基础大致怎么样？",
        }, ensure_ascii=False))
        agent = GraduatePlanningAgent(llm)
        agent.init_state({"major": "计算机", "grade": "大三"})
        agent.state.questions_asked = 1
        agent.state.last_asked_question = "你更倾向哪类目标岗位？"
        agent.state.last_asked_dimension = "target"
        readiness = evaluate_advice_readiness(
            "graduate",
            user_profile=agent.state.user_profile,
            questions_asked=agent.state.questions_asked,
            current_question=agent.state.last_asked_question,
            current_dimension="target",
            current_answer="不知道",
        )

        result = agent._handle_follow_up(
            "不知道",
            turn_analysis={
                "should_ask": readiness["can_ask"],
                "ready_for_advice": readiness["ready"],
                "advice_level": readiness["advice_level"],
                "critical_variable": readiness["next_dimension_label"],
                "readiness": readiness,
            },
        )

        self.assertEqual(result["step"], "follow_up")
        self.assertEqual(agent.state.follow_up_round, 0)
        self.assertEqual(agent.state.questions_asked, 2)
        self.assertEqual(agent.state.unavailable_dimensions["target"], "unknown")
        self.assertEqual(agent.state.last_asked_dimension, "foundation")

    def test_uncertain_answer_acknowledgement_keeps_concrete_choice_signal(self):
        agent = GraduatePlanningAgent(_FakeLLM())
        agent.init_state({"major": "通信工程", "grade": "大三"})

        acknowledgement = agent._fallback_acknowledgement(
            "我还没想好该冲985还是选稳一点的学校"
        )

        self.assertTrue("985" in acknowledgement or "稳" in acknowledgement)
        self.assertIn("拿不准", acknowledgement)

    def test_salary_acknowledgement_and_insight_trimming_keep_complete_meaning(self):
        agent = GraduatePlanningAgent(_FakeLLM())
        agent.init_state({"major": "计算机", "grade": "大三"})

        acknowledgement = agent._fallback_acknowledgement(
            "我想了解考研和就业的薪资差异。"
        )
        insight = agent._trim_advisory_part(
            "研究型岗位更看重研究训练，而工程岗位更看重项目和实习。"
            "薪资还会受城市、行业和个人能力影响。",
            42,
            "。",
        )

        self.assertEqual(acknowledgement, "你在比较考研和就业的薪资差异。")
        self.assertEqual(insight, "研究型岗位更看重研究训练，而工程岗位更看重项目和实习。")

    def test_fifth_unavailable_answer_produces_conditional_advice_without_more_questions(self):
        llm = _FakeLLM(response=json.dumps({
            "acknowledgement": "这项暂时不确定也没关系。",
            "insight": "可以先按不同目标岗位分别评估读研价值。",
            "question": "",
        }, ensure_ascii=False))
        agent = GraduatePlanningAgent(llm)
        agent.init_state({"major": "计算机", "grade": "大三"})
        agent.state.questions_asked = 5
        agent.state.last_asked_question = "你更倾向哪类目标岗位？"
        agent.state.last_asked_dimension = "target"
        readiness = evaluate_advice_readiness(
            "graduate",
            user_profile=agent.state.user_profile,
            questions_asked=5,
            current_question=agent.state.last_asked_question,
            current_dimension="target",
            current_answer="还没想好",
        )
        result = agent._handle_follow_up(
            "还没想好",
            turn_analysis={
                "should_ask": readiness["can_ask"],
                "ready_for_advice": readiness["ready"],
                "advice_level": readiness["advice_level"],
                "readiness": readiness,
            },
        )

        self.assertTrue(agent.state.follow_up_complete)
        self.assertEqual(agent.state.questions_asked, 5)
        self.assertEqual(readiness["advice_level"], "conditional")
        self.assertNotIn("？", result["message"])
        self.assertIn("条件式判断", result["message"])

    def test_sandbox_report_finishes_in_one_turn_with_valid_icons_and_scores(self):
        llm = _SandboxReportLLM()
        sandbox = DecisionSandbox(llm, PlanningRouter(llm))
        session = SandboxSession(
            session_id="sandbox-report-test",
            user_id="u1",
            current_phase=SandboxPhase.PATH_PROBE,
            phase_index=1,
            user_profile={"major": "计算机", "grade": "大三"},
            path_selections=["career", "graduate"],
            path_probe_history={"career": [{"q": "顾虑？", "a": "稳定"}], "graduate": []},
            path_probe_done={"career"},
        )
        sandbox._sessions[session.session_id] = session

        result = sandbox.chat(session, "我更看重长期发展")

        self.assertTrue(result["finished"])
        self.assertTrue(session.finished)
        self.assertEqual(session.current_phase, SandboxPhase.COMPLETED)
        self.assertEqual([card["match_score"] for card in result["cards"]], [80, 70])
        self.assertTrue(all(card["icon"].startswith("/images/icon-") for card in result["cards"]))
        self.assertTrue(all(card["icon"].endswith(".png") for card in result["cards"]))
        from sandbox.schemas import SandboxChatResponse
        validated = SandboxChatResponse(**result)
        self.assertEqual(
            [item.path_type for item in validated.projection_result.projections],
            ["career", "graduate"],
        )
        timed_calls = [call for call in llm.calls if "request_timeout" in call]
        self.assertEqual(len(timed_calls), 3)
        self.assertTrue(all(call["max_retries"] == 0 for call in timed_calls))

    def test_objective_question_is_never_delegated_back_to_user(self):
        llm = _FakeLLM(analysis='''{
            "intent":"personal_update",
            "answerable_by_ai":false,
            "needs_knowledge":false,
            "knowledge_topics":[],
            "critical_variable":"你是否了解薪资区别",
            "should_ask":true
        }''')

        result = analyze_turn(
            llm,
            agent_type="graduate",
            agent_label="考研规划",
            message="你知道考研和就业的薪资区别吗？",
            user_context="专业：计算机",
            follow_up_round=0,
            max_follow_up_rounds=MAX_FOLLOW_UP_ROUNDS,
        )

        self.assertTrue(result["answerable_by_ai"])
        self.assertTrue(result["needs_knowledge"])
        self.assertIn("salary", result["knowledge_topics"])
        self.assertIn("comparison", result["knowledge_topics"])
        self.assertNotIn("是否了解", result["critical_variable"])

    def test_fallback_turn_analysis_still_answers_knowledge_questions(self):
        result = analyze_turn(
            _FakeLLM(),
            agent_type="civil",
            agent_label="考公考编规划",
            message="公务员考试内容和竞争程度是什么？",
            user_context="",
            follow_up_round=0,
            max_follow_up_rounds=MAX_FOLLOW_UP_ROUNDS,
        )

        self.assertTrue(result["answerable_by_ai"])
        self.assertIn("exam", result["knowledge_topics"])
        self.assertIn("policy", result["knowledge_topics"])

    def test_follow_up_generates_only_one_user_facing_response(self):
        llm = _FakeLLM(
            response=(
                "考研方向可以先比较本专业深化、相近专业交叉和跨专业转换。"
                "真正影响选择的是目标岗位和时间成本。你更偏向研究型还是工程型岗位？"
            )
        )
        agent = GraduatePlanningAgent(llm)
        agent.init_state({"major": "计算机", "grade": "大二"})
        agent.state.last_asked_question = "你目前最想解决什么问题？"
        agent._last_asked_question = agent.state.last_asked_question

        result = agent._handle_follow_up(
            "想了解考研方向",
            turn_analysis={
                "answerable_by_ai": True,
                "should_ask": True,
                "critical_variable": "目标岗位偏好",
            },
            knowledge_context="- 方向可分为本专业深化、相近专业交叉和跨专业转换。",
        )

        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(result["step"], "follow_up")
        self.assertEqual(
            agent.state.follow_up_history[0]["q"],
            "你目前最想解决什么问题？",
        )
        self.assertNotIn("你知道", result["message"])

    def test_zero_question_turn_can_finish_information_collection(self):
        llm = _FakeLLM(response="根据现有信息，读研价值主要取决于目标岗位门槛和机会成本。")
        agent = GraduatePlanningAgent(llm)
        agent.init_state({"major": "计算机", "grade": "大三"})
        agent.state.last_asked_question = "你更看重短期收入还是长期发展？"

        result = agent._handle_follow_up(
            "长期发展",
            turn_analysis={"should_ask": False, "answerable_by_ai": False},
        )

        self.assertEqual(len(llm.calls), 1)
        self.assertTrue(agent.state.follow_up_complete)
        self.assertEqual(agent.state.current_step, WorkflowStep.AWAIT_TRIGGER)
        self.assertIn("已有信息足够", result["message"])

    def test_last_question_survives_state_round_trip(self):
        state = PlanningState(agent_type="graduate")
        state.last_asked_question = "你更看重短期收入还是长期发展？"
        restored = PlanningState.from_dict(state.to_dict())
        self.assertEqual(restored.last_asked_question, state.last_asked_question)

    def test_knowledge_is_grounded_and_marks_volatile_data_unverified(self):
        knowledge = get_knowledge_context("graduate", ["salary", "exam"])
        self.assertIn("不应给出精确薪资数字", knowledge["text"])
        self.assertIn("思想政治理论", knowledge["text"])
        self.assertFalse(knowledge["volatile_data_verified"])

    def test_discovery_prompt_is_advisory_not_questionnaire_only(self):
        self.assertIn("先基于已有信息给出初步分析", DISCOVERY_SYSTEM_PROMPT)
        self.assertIn("允许不提问", DISCOVERY_SYSTEM_PROMPT)
        self.assertNotIn("你的唯一任务是了解用户", DISCOVERY_SYSTEM_PROMPT)

    def test_sandbox_discovery_returns_analysis_before_question(self):
        llm = _FakeLLM(response=json.dumps({
            "response": (
                "考研与就业主要差在岗位门槛、时间成本和能力积累方式。"
                "真正需要结合你本人判断的是发展优先级。你更看重短期收入还是长期发展？"
            ),
            "next_question": "你更看重短期收入还是长期发展？",
            "reasoning": "先提供路径信息",
            "updated_profile": {"core_confusion": "考研与就业选择"},
            "finish": False,
        }, ensure_ascii=False))
        sandbox = DecisionSandbox(llm, PlanningRouter(llm))
        session = sandbox.start_session("u1")

        result = sandbox.chat(session, "想了解考研方向")

        self.assertTrue(result["message"].startswith("考研与就业主要差在"))
        self.assertIn("你更看重", result["message"])
        self.assertEqual(session.discovery_round, 1)

    def test_sandbox_decision_pushback_gets_direction_instead_of_repeat_question(self):
        llm = _FakeLLM(response=json.dumps({
            "response": (
                "理解，你希望我先给出方向参考，而不是继续追问。"
                "从目前信息看，两条路都可行，取决于你的偏好。"
            ),
            "next_question": "如果考研，你更看重薪资提升还是想避开就业压力？",
            "reasoning": "继续询问偏好",
            "updated_profile": {},
            "finish": True,
        }, ensure_ascii=False))
        sandbox = DecisionSandbox(llm, PlanningRouter(llm))
        session = SandboxSession(
            session_id="pushback",
            user_id="u1",
            discovery_round=1,
            discovery_history=[{
                "q": "你现在最纠结的选择是什么？",
                "a": "不知道考研还是就业",
            }],
            last_discovery_question="如果有实习机会，你会先就业还是读研？",
            last_discovery_response="两条路需要结合目标和投入成本判断。",
            user_profile={
                "major": "计算机科学与技术",
                "grade": "大三",
                "core_confusion": "就业与考研路径选择",
            },
            path_selections=["career", "graduate"],
        )

        result = sandbox.chat(session, "我就是不知道才问你啊")

        self.assertEqual(result["phase"], "discovery")
        self.assertIn("更建议先把就业准备作为验证主线", result["message"])
        self.assertNotIn("取决于你的偏好", result["message"])
        self.assertNotIn("你更看重薪资提升", result["message"])
        self.assertEqual(result["message"].count("？"), 1)
        self.assertLessEqual(len(result["message"]), 160)
        self.assertEqual(
            session.discovery_history[-1]["q"],
            "如果有实习机会，你会先就业还是读研？",
        )
        self.assertEqual(session.discovery_history[-1]["a"], "我就是不知道才问你啊")
        self.assertEqual(session.last_discovery_question, "你目前项目实践和数学英语，哪一边基础更扎实？")

    def test_sandbox_named_paths_are_remembered_and_transition_has_real_newlines(self):
        llm = _FakeLLM(response=json.dumps({
            "response": "我先比较现有信息，再进入两条路径的具体分析。",
            "next_question": "",
            "updated_profile": {},
            "finish": False,
        }, ensure_ascii=False))
        sandbox = DecisionSandbox(llm, PlanningRouter(llm))
        session = sandbox.start_session("u1")

        sandbox.chat(session, "不知道考研还是就业")
        transition = sandbox._transition_to_path_probe(SandboxSession(
            session_id="newline",
            user_id="u1",
            current_phase=SandboxPhase.DISCOVERY,
            phase_index=0,
        ))

        self.assertEqual(session.path_selections, ["career", "graduate"])
        self.assertNotIn("\\n", transition["message"])
        self.assertIn("\n", transition["message"])

    def test_sandbox_parses_card_values_and_natural_language_path_names(self):
        llm = _FakeLLM(response="")
        sandbox = DecisionSandbox(llm, PlanningRouter(llm))

        self.assertEqual(
            sandbox._parse_path_selections("career graduate"),
            ["career", "graduate"],
        )
        self.assertEqual(
            sandbox._parse_path_selections("就业和考研"),
            ["career", "graduate"],
        )

    def test_preselected_paths_remain_locked_during_discovery(self):
        llm = _FakeLLM(response=json.dumps({
            "response": "我会继续围绕已选路径补齐信息。你目前最受什么现实限制？",
            "next_question": "你目前最受什么现实限制？",
            "updated_profile": {},
            "finish": False,
        }, ensure_ascii=False))
        sandbox = DecisionSandbox(llm, PlanningRouter(llm))
        session = SandboxSession(
            session_id="locked-paths",
            user_id="u1",
            path_selections=["career", "graduate"],
            path_selection_source="preset",
            path_selection_locked=True,
        )

        sandbox.chat(session, "我也想了解考公和转专业")

        self.assertEqual(session.path_selections, ["career", "graduate"])
        restored = SandboxSession.from_dict(session.to_dict())
        self.assertTrue(restored.path_selection_locked)
        self.assertEqual(restored.path_selection_source, "preset")

    def test_locked_paths_replace_model_preference_question_with_a_fact_question(self):
        llm = _FakeLLM(response=json.dumps({
            "response": "你已有项目基础，可以继续补齐关键信息。你更倾向直接就业还是读研？",
            "next_question": "你更倾向直接就业还是读研？",
            "updated_profile": {},
            "finish": False,
        }, ensure_ascii=False))
        sandbox = DecisionSandbox(llm, PlanningRouter(llm))
        session = SandboxSession(
            session_id="locked-choice",
            user_id="u1",
            path_selections=["career", "graduate"],
            path_selection_source="preset",
            path_selection_locked=True,
        )

        result = sandbox.chat(session, "我做过一个课程项目")

        self.assertNotIn("更倾向", result["message"])
        self.assertNotIn("直接就业还是读研", result["message"])
        self.assertNotIn("你想对比哪些方向", result["message"])
        self.assertIn("岗位", result["message"])

    def test_unknown_discovery_answer_skips_that_dimension(self):
        repeated_values_question = "你更看重薪资还是成长？"
        llm = _FakeLLM(response=json.dumps({
            "response": f"这项暂时不确定没关系。{repeated_values_question}",
            "next_question": repeated_values_question,
            "updated_profile": {},
            "finish": False,
        }, ensure_ascii=False))
        sandbox = DecisionSandbox(llm, PlanningRouter(llm))
        session = SandboxSession(
            session_id="skip-dimension",
            user_id="u1",
            discovery_round=1,
            last_discovery_question="你更看重薪资还是稳定？",
            last_discovery_response="你更看重薪资还是稳定？",
        )

        result = sandbox.chat(session, "不知道")

        self.assertIn("values", session.unavailable_discovery_dimensions)
        self.assertNotIn("薪资", result["message"])
        self.assertNotIn("更看重", result["message"])

    def test_structured_response_is_short_soft_and_single_question(self):
        llm = _FakeLLM(response=json.dumps({
            "acknowledgement": "明白了。",
            "insight": (
                "你必须马上确定方向，否则肯定会错过机会。" * 8
            ),
            "question": "你应该选考研吗？还是应该直接就业？",
        }, ensure_ascii=False))
        agent = GraduatePlanningAgent(llm)
        agent.init_state({"major": "计算机", "grade": "大三"})

        response = agent._generate_dynamic_question(
            is_retry=False,
            last_answer="我更看重长期发展",
            turn_analysis={"should_ask": True, "critical_variable": "目标岗位"},
            knowledge_context="",
        )

        self.assertLessEqual(len(response), 140)
        self.assertEqual(response.count("？"), 1)
        self.assertIn("长期发展", response[:40])
        self.assertNotIn("你必须", response)
        self.assertNotIn("你应该", response)
        self.assertNotIn("肯定", response)

    def test_user_facing_knowledge_test_question_is_replaced(self):
        llm = _FakeLLM(response=json.dumps({
            "acknowledgement": "你担心延迟毕业，这个顾虑很实际。",
            "insight": "各校学分转换和补修规则不同，应以当学年政策为准。",
            "question": "你了解过本校转专业后的补修规则吗？",
        }, ensure_ascii=False))
        from planning.agents.major import MajorPlanningAgent
        agent = MajorPlanningAgent(llm)
        agent.init_state({"major": "生物工程", "grade": "大二"})

        response = agent._generate_dynamic_question(
            is_retry=False,
            last_answer="我担心延迟毕业",
            turn_analysis={"should_ask": True, "advice_level": "general_only"},
        )

        self.assertNotIn("你了解", response)
        self.assertNotIn("了解过", response)
        self.assertEqual(response.count("？"), 1)
        self.assertIn("时间成本", response)

    def test_unsupported_user_facts_and_numbers_are_not_exposed(self):
        llm = _FakeLLM(response=json.dumps({
            "acknowledgement": "你在北京读985，而且项目经历很丰富。",
            "insight": "你的学校是985，考研成功率有80%，建议直接冲刺。",
            "question": "你更倾向算法还是开发？",
            "user_facts_used": ["985", "项目经历很丰富"],
            "knowledge_evidence": "考研成功率有80%",
        }, ensure_ascii=False))
        agent = GraduatePlanningAgent(llm)
        agent.init_state({"major": "计算机", "grade": "大三"})

        response = agent._generate_dynamic_question(
            is_retry=False,
            last_answer="我想了解AI方向",
            turn_analysis={"should_ask": True, "advice_level": "general_only"},
        )

        self.assertNotIn("北京", response)
        self.assertNotIn("985", response)
        self.assertNotIn("80%", response)
        self.assertNotIn("项目经历很丰富", response)
        self.assertIn("AI方向", response[:40])

    def test_dialogue_dataset_has_ten_cases_per_growth_direction(self):
        groups = cases_by_agent()
        self.assertEqual(len(DIALOGUE_CASES), 40)
        self.assertEqual(
            {agent_type: len(cases) for agent_type, cases in groups.items()},
            {"graduate": 10, "career": 10, "civil": 10, "major": 10},
        )

    def test_all_40_offline_dialogue_regressions_pass(self):
        results = run_evaluation(live=False)
        failed = [result for result in results if not result["passed"]]
        self.assertEqual(failed, [])


class GrowthGraphRoundTests(unittest.IsolatedAsyncioTestCase):
    async def test_sandbox_start_does_not_consume_a_hidden_discovery_round(self):
        from app.api.v1.sandbox import start_session as start_sandbox_session
        from sandbox.schemas import SandboxStartRequest

        llm = _FakeLLM(response="should not be called")
        sandbox = DecisionSandbox(llm, PlanningRouter(llm))

        response = await start_sandbox_session(
            SandboxStartRequest(user_id="u1"),
            sandbox=sandbox,
            db=None,
            current_user_id="u1",
        )

        session = sandbox.get_session(response.session_id)
        self.assertIsNotNone(session)
        self.assertEqual(session.discovery_round, 0)
        self.assertEqual(session.discovery_history, [])
        self.assertEqual(llm.calls, [])
        self.assertEqual(
            session.last_discovery_question,
            "你现在最纠结的选择是什么？",
        )

    async def test_preselected_sandbox_starts_with_a_path_specific_question(self):
        from app.api.v1.sandbox import start_session as start_sandbox_session
        from sandbox.schemas import SandboxPathType, SandboxStartRequest

        llm = _FakeLLM(response=json.dumps({
            "question": "你最近完成的一项项目、实习或作品是什么？",
        }, ensure_ascii=False))
        sandbox = DecisionSandbox(llm, PlanningRouter(llm))
        response = await start_sandbox_session(
            SandboxStartRequest(
                user_id="u1",
                paths=[SandboxPathType.CAREER, SandboxPathType.GRADUATE],
            ),
            sandbox=sandbox,
            db=None,
            current_user_id="u1",
        )

        session = sandbox.get_session(response.session_id)
        self.assertTrue(response.message.startswith("已记录你选择的就业规划、考研规划。"))
        self.assertIn("第一轮：", response.message)
        self.assertNotIn("纠结的点", response.message)
        self.assertEqual(
            session.last_discovery_question,
            "你最近完成的一项项目、实习或作品是什么？",
        )
        self.assertNotIn("更希望", response.message)
        self.assertNotIn("还是愿意", response.message)
        self.assertEqual(session.questions_asked, 1)
        self.assertEqual(session.discovery_round, 0)
        self.assertEqual(len(llm.calls), 1)

    async def test_sandbox_stream_hides_internal_json(self):
        llm = _FakeLLM(response=json.dumps({
            "response": "考研方向要比较目标岗位、当前基础和时间成本。你更偏向研究还是工程实践？",
            "next_question": "你更偏向研究还是工程实践？",
            "reasoning": "internal",
            "updated_profile": {},
            "finish": False,
        }, ensure_ascii=False))
        sandbox = DecisionSandbox(llm, PlanningRouter(llm))
        session = sandbox.start_session("stream-user")

        events = []
        async for event, data in sandbox.chat_stream(session, "想了解考研方向"):
            events.append((event, data))

        token_text = "".join(data for event, data in events if event == "token")
        self.assertTrue(token_text.startswith("考研方向要比较"))
        self.assertNotIn('"reasoning"', token_text)
        self.assertNotIn('"updated_profile"', token_text)

    async def test_sandbox_stream_preserves_preselected_paths_and_advances_probe(self):
        class RoutingLLM:
            def chat(self, **kwargs):
                if "帮助用户比较成长路径" in kwargs.get("system_prompt", ""):
                    return json.dumps({
                        "insight": "就业方向要看能力证据和岗位匹配。",
                        "questions": ["你目前有哪些项目或实习证据？"],
                    }, ensure_ascii=False)
                return json.dumps({
                    "response": "我先按你的选择补齐必要信息。",
                    "next_question": "你目前更看重什么？",
                    "updated_profile": {},
                    "finish": False,
                }, ensure_ascii=False)

        llm = RoutingLLM()
        sandbox = DecisionSandbox(llm, PlanningRouter(llm))
        session = SandboxSession(
            session_id="stream-preselected",
            user_id="u1",
            discovery_round=2,
            path_selections=["career", "graduate"],
        )

        events = []
        async for event, data in sandbox.chat_stream(session, "我想继续了解"):
            events.append((event, data))
        result = json.loads([data for event, data in events if event == "done"][-1])

        self.assertEqual(result["phase"], "path_probe")
        self.assertEqual(result["path_selections"], ["career", "graduate"])
        self.assertNotIn("你想重点比较哪些方向", result["message"])

        events = []
        async for event, data in sandbox.chat_stream(session, "我做过一个项目"):
            events.append((event, data))
        result = json.loads([data for event, data in events if event == "done"][-1])

        self.assertEqual(session.path_probe_history["career"][0]["a"], "我做过一个项目")
        self.assertIn("就业方向要看", session.path_probe_history["career"][0]["q"])
        self.assertIn("career", session.path_probe_done)
        self.assertEqual(result["phase"], "path_probe")
        self.assertIn("graduate", result["path_selections"])
        restored = SandboxSession.from_dict(session.to_dict())
        self.assertEqual(
            restored.path_probe_pending_questions["graduate"],
            session.path_probe_pending_questions["graduate"],
        )

    async def test_sandbox_stream_replaces_knowledge_test_questions(self):
        bad_question = "你知道你所在专业目前薪资吗？"

        class BadQuestionLLM:
            def chat(self, **kwargs):
                if "帮助用户比较成长路径" in kwargs.get("system_prompt", ""):
                    return json.dumps({
                        "insight": "薪资会受城市和岗位影响。",
                        "questions": [bad_question],
                    }, ensure_ascii=False)
                return json.dumps({
                    "response": f"薪资会受城市和岗位影响。{bad_question}",
                    "next_question": bad_question,
                    "updated_profile": {},
                    "finish": False,
                }, ensure_ascii=False)

        llm = BadQuestionLLM()
        sandbox = DecisionSandbox(llm, PlanningRouter(llm))
        discovery = SandboxSession(session_id="safe-discovery", user_id="u1")
        events = []
        async for event, data in sandbox.chat_stream(discovery, "我想了解就业和考研的薪资差异"):
            events.append((event, data))
        discovery_result = json.loads([data for event, data in events if event == "done"][-1])

        self.assertNotIn(bad_question, discovery_result["message"])
        self.assertNotIn("你知道", discovery_result["message"])

        probe = SandboxSession(
            session_id="safe-probe",
            user_id="u1",
            current_phase=SandboxPhase.PATH_PROBE,
            phase_index=1,
            path_selections=["career", "graduate"],
        )
        events = []
        async for event, data in sandbox.chat_stream(probe, "我有一些项目"):
            events.append((event, data))
        probe_result = json.loads([data for event, data in events if event == "done"][-1])

        self.assertNotIn(bad_question, probe_result["message"])
        self.assertNotIn("你知道", probe_result["message"])

    async def test_sandbox_stream_persists_the_canonical_turn_state(self):
        class MemorySpy:
            def __init__(self):
                self.contexts = []

            def persist_sandbox_state(self, _db, **kwargs):
                self.contexts.append(kwargs)

            def extract_from_turn_async(self, **_kwargs):
                return None

        llm = _FakeLLM(response=json.dumps({
            "response": "先比较目标、基础和时间成本。你目前更看重什么？",
            "next_question": "你目前更看重什么？",
            "updated_profile": {},
            "finish": False,
        }, ensure_ascii=False))
        memory = MemorySpy()
        sandbox = DecisionSandbox(llm, PlanningRouter(llm), memory_service=memory)
        session = sandbox.start_session("stream-persist")

        async for _event, _data in sandbox.chat_stream(
            session, "我想了解考研", db_session=object(),
        ):
            pass

        self.assertEqual(len(memory.contexts), 1)
        self.assertEqual(
            memory.contexts[0]["session_state"]["discovery_history"][0]["a"],
            "我想了解考研",
        )

    async def test_growth_restores_persisted_sandbox_context_when_live_session_is_missing(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from unittest.mock import AsyncMock
        from database.base import Base
        import models  # noqa: F401
        from models.user import User
        from sandbox.state import SandboxSession
        from schemas.growth import GrowthStartRequest, AgentTypeEnum
        from services.growth_service import GrowthService
        from services.memory_service import memory_service

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        try:
            user_id = "growth-handoff-user"
            db.add(User(id=user_id, name="测试用户", nickname="测试用户"))
            db.commit()
            sandbox_session = SandboxSession(
                session_id="persisted-sandbox", user_id=user_id,
                user_profile={"major": "计算机", "core_confusion": "考研还是就业"},
                discovery_history=[{"q": "你更看重什么？", "a": "长期发展"}],
                path_probe_history={
                    "career": [{"q": "就业更担心什么？", "a": "项目不足"}],
                    "graduate": [{"q": "考研更担心什么？", "a": "数学基础"}],
                },
            )
            memory_service.save_context(
                db, user_id=user_id, context_kind="sandbox",
                context_id=sandbox_session.session_id,
                payload=sandbox_session.to_dict(),
            )

            class EmptySandbox:
                @staticmethod
                def get_session(_session_id):
                    return None

            service = GrowthService(_FakeLLM(), EmptySandbox())

            async def echo_state(state, _config):
                return {**state, "agent_message": "已继承沙盘信息。"}

            service._invoke = AsyncMock(side_effect=echo_state)
            await service.start_session(db, request=GrowthStartRequest(
                user_id=user_id,
                agent=AgentTypeEnum.CAREER,
                sandbox_session_id=sandbox_session.session_id,
            ))

            initial = service._invoke.await_args.args[0]
            planning_state = json.loads(initial["planning_state_json"])
            self.assertEqual(planning_state["user_profile"]["major"], "计算机")
            self.assertEqual(
                planning_state["follow_up_history"][0],
                {"q": "你更看重什么？", "a": "长期发展"},
            )
            self.assertEqual(len(planning_state["follow_up_history"]), 2)
            self.assertEqual(planning_state["questions_asked"], 3)
        finally:
            db.close()
            engine.dispose()

    async def test_graph_runs_analysis_knowledge_and_one_response_call(self):
        llm = _FakeLLM(
            analysis=json.dumps({
                "intent": "information",
                "answerable_by_ai": True,
                "needs_knowledge": True,
                "knowledge_topics": ["salary", "comparison"],
                "known_information": [],
                "missing_variables": ["价值排序"],
                "critical_variable": "短期收入与长期发展的价值排序",
                "should_ask": True,
                "reason": "test",
            }, ensure_ascii=False),
            response=(
                "考研与就业不能只比较起薪，还要看岗位门槛和时间成本。"
                "你更看重短期收入还是长期发展？"
            ),
        )

        previous_db = os.environ.get("GROWTH_CHECKPOINT_DB")
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["GROWTH_CHECKPOINT_DB"] = os.path.join(temp_dir, "growth.sqlite")
            graph = await build_growth_graph(llm, PlanningRouter(llm), None)
            try:
                state = PlanningState(agent_type="graduate")
                state.user_profile = {"major": "计算机", "grade": "大二"}
                state.has_profile = True
                state.advance_step()
                result = await graph.ainvoke({
                    "user_id": "u1",
                    "agent_type": "graduate",
                    "session_id": "s1",
                    "user_message": "想了解考研和就业的薪资区别",
                    "user_correction": "",
                    "planning_state_json": json.dumps(state.to_dict(), ensure_ascii=False),
                    "follow_up_round": 0,
                    "follow_up_complete": False,
                    "analysis": {},
                    "identified_problems": [],
                    "long_term_goal": "",
                    "action_plan": [],
                    "output": {},
                    "stage": "questioning",
                    "finished": False,
                    "agent_message": "",
                    "report": None,
                    "error_message": "",
                    "last_question": "你目前最想解决什么问题？",
                    "awaiting_trigger": False,
                    "report_requested": False,
                    "turn_analysis": {},
                    "knowledge_context": "",
                    "knowledge_evidence": {},
                }, {"configurable": {"thread_id": "growth-advisory-test"}})

                self.assertEqual(len(llm.calls), 2)
                self.assertEqual(result["follow_up_round"], 1)
                self.assertIn("不应给出精确薪资数字", result["knowledge_context"])
                saved = json.loads(result["planning_state_json"])
                self.assertEqual(
                    saved["follow_up_history"][0]["q"],
                    "你目前最想解决什么问题？",
                )
            finally:
                await graph.checkpointer.conn.close()
                if previous_db is None:
                    os.environ.pop("GROWTH_CHECKPOINT_DB", None)
                else:
                    os.environ["GROWTH_CHECKPOINT_DB"] = previous_db


if __name__ == "__main__":
    unittest.main()
