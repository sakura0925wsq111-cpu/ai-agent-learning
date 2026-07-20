# -*- coding: utf-8 -*-
"""PlanningAgent Demo — run any agent directly from the command line.

Usage:
    cd backend
    python planning_demo.py career      # test employment agent
    python planning_demo.py graduate    # test postgraduate agent
    python planning_demo.py civil       # test civil service agent
    python planning_demo.py major       # test major transfer agent
"""

from __future__ import annotations

import json
import sys
import io

# Force UTF-8 for stdout on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from planning.router import PlanningRouter
from services.llm_service import get_llm_service


def run_demo(agent_type: str):
    """Run a complete planning demo for the given agent type."""
    llm = get_llm_service()
    router = PlanningRouter(llm)

    print(f"\n{'='*60}")
    print(f"  CampusPal PlanningAgent Demo: {agent_type}")
    print(f"{'='*60}\n")

    agent = router.get_agent(agent_type)
    print(f"[Agent] {agent.agent_label} ({agent.agent_type})")
    strategy = agent.build_analysis_strategy()
    dims = strategy['focus_dimensions'][:3]
    print(f"[Strategy] Focus dimensions: {', '.join(dims)}...")

    state = agent.init_state()
    print(f"[State] Step: {state.current_step.value}")

    print(f"\n{'-'*60}")
    print(f"  Follow-up phase (max 7 rounds)")
    print(f"{'-'*60}\n")

    simulated_answers = _get_simulated_answers(agent_type)

    result = None
    for i, answer in enumerate(simulated_answers):
        print(f"[Round {agent.state.follow_up_round + 1}] User: {answer[:80]}...")
        result = agent.chat(answer)
        step = result.get("step", "")
        msg = result.get("message", "")
        # Clean emojis from message for Windows console
        msg_clean = msg.replace('\u2705', '[OK]').replace('\u274c', '[X]').replace('\u26a0', '[WARN]')
        print(f"[AI] {msg_clean[:150]}{'...' if len(msg) > 150 else ''}")

        if result.get("finished"):
            break

    # If still not finished, force completion
    if result and not result.get("finished"):
        remaining = MAX_FOLLOW_UP_ROUNDS - agent.state.follow_up_round
        for i in range(remaining):
            print(f"[Round {agent.state.follow_up_round + 1}] User: Handling remaining questions...")
            result = agent.chat("各方面都考虑过了，可以开始分析了")
            if result.get("finished"):
                break

    # Print final report
    print(f"\n{'='*60}")
    print("  FINAL REPORT")
    print(f"{'='*60}\n")

    report = result.get("report", {}) if result else {}
    if report:
        summary = report.get('summary', 'N/A')[:150]
        print(f"[Summary] {summary}")
        print(f"\n[Current Status] {report.get('current_status', 'N/A')[:150]}")
        print(f"\n[Main Problem] {report.get('main_problem', 'N/A')}")
        print(f"\n[Goal] {report.get('goal', 'N/A')}")

        advantages = report.get("advantages", [])
        if advantages:
            print(f"\n[Advantages] ({len(advantages)} items)")
            for a in advantages[:3]:
                p = a.get('point', '')
                d = a.get('detail', '')[:80]
                print(f"  + {p}: {d}...")

        risks = report.get("risks", [])
        if risks:
            print(f"\n[Risks] ({len(risks)} items)")
            for r in risks[:3]:
                lvl = r.get('level', 'medium')
                p = r.get('point', '')
                print(f"  [{lvl}] {p}")

        plan = report.get("action_plan", [])
        if plan:
            print(f"\n[90-Day Plan] ({len(plan)} phases)")
            for p in plan:
                phase = p.get('phase', '')
                tasks = p.get('tasks', [])
                print(f"  > {phase}")
                for t in tasks[:2]:
                    print(f"    - {t[:100]}")

        next_q = report.get("next_question", "")
        if next_q:
            print(f"\n[Next] {next_q[:200]}")

        # Full JSON
        print(f"\n{'-'*60}")
        print("  Full JSON Report:")
        print(f"{'-'*60}")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("[FAIL] Report generation failed. Check LLM configuration.")
        print(f"[Debug] Result keys: {list(result.keys()) if result else 'None'}")

    # Validation checks
    print(f"\n{'='*60}")
    print("  VALIDATION")
    print(f"{'='*60}")
    checks = []
    if report:
        checks.append(("summary non-empty", bool(report.get("summary", "").strip())))
        checks.append(("advantages >= 3", len(report.get("advantages", [])) >= 3))
        checks.append(("risks >= 3", len(report.get("risks", [])) >= 3))
        checks.append(("action_plan 4 phases", len(report.get("action_plan", [])) == 4))
        checks.append(("main_problem non-empty", bool(report.get("main_problem", "").strip())))
        checks.append(("goal non-empty", bool(report.get("goal", "").strip())))
        for name, passed in checks:
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {name}")

    print(f"\n{'='*60}")
    print("  Demo Complete!")
    print(f"{'='*60}\n")

    return report


def _get_simulated_answers(agent_type: str) -> list[str]:
    answers = {
        "career": [
            "我是计算机科学专业大三学生，GPA 3.3左右",
            "想找后端开发方向的工作，对Java和Spring比较熟悉",
            "已经自学了Java和Spring框架，做过一个校园二手交易平台的小项目",
            "希望在杭州或上海工作，更看重技术成长空间",
            "担心没有实习经验，竞争力不够，而且感觉技术栈还不够深",
            "对互联网大厂和中小公司都有兴趣，主要看团队氛围和技术栈",
            "可以接受适度的加班，薪资期望在行业中位数以上就可以",
        ],
        "graduate": [
            "我是通信工程专业大二学生，GPA排名前30%",
            "感觉本科学历不够用，想通过考研提升竞争力",
            "目标是211院校的本专业，想留在长三角地区",
            "英语四级过了，六级还没考，英语基础一般",
            "数学基础还行，高数线代都在80分以上",
            "还没开始系统复习，想先了解怎么规划备考",
            "家里支持考研，没有经济压力，可以全身心备考",
        ],
        "civil": [
            "我是法学专业大三学生",
            "想考法院或者检察院的岗位，觉得学以致用",
            "目标省份是浙江或江苏，离家近",
            "行测做了一些题，感觉数量关系和资料分析比较弱",
            "申论还在了解阶段，写作能力一般",
            "可以接受备考6-8个月，家里也支持",
            "也考虑过事业编作为备选，不想把路走窄了",
        ],
        "major": [
            "我现在是材料科学与工程大二学生，GPA排名前25%",
            "对本专业没有兴趣，觉得和职业期待不匹配",
            "想转到计算机相关专业，自学过Python写过一些小程序",
            "学校转专业要求GPA排名前30%，目前满足条件",
            "担心转过去后跟不上课程，补修压力大",
            "也考虑过辅修计算机作为替代方案",
            "父母比较支持我的决定，经济上没有顾虑",
        ],
    }
    return answers.get(agent_type, answers["career"])


if __name__ == "__main__":
    from planning.state import MAX_FOLLOW_UP_ROUNDS
    agent_type = sys.argv[1] if len(sys.argv) > 1 else "career"

    valid_types = {"career", "graduate", "civil", "major"}
    if agent_type not in valid_types:
        print(f"Usage: python planning_demo.py <agent_type>")
        print(f"Available: {', '.join(sorted(valid_types))}")
        sys.exit(1)

    run_demo(agent_type)
