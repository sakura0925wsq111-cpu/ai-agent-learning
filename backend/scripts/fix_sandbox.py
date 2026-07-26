import sys
sys.stdout.reconfigure(encoding="utf-8")

# ═══════════════════════════════════════════════════════════════
# Fix 1: _transition_to_path_probe returns show_cards + cards
# ═══════════════════════════════════════════════════════════════
with open("D:/ai-agent-learning/backend/sandbox/orchestrator.py", "r", encoding="utf-8") as f:
    content = f.read()

old_transition = '''    def _transition_to_path_probe(self, session: SandboxSession) -> dict[str, Any]:
        """Transition from discovery to path probe phase.

        Asks the user which paths they want to compare.
        """
        session.advance_phase()
        logger.info("Sandbox[{}]: entering PATH_PROBE phase", session.session_id)

        # If user already specified paths (e.g., via API), skip the selection question
        if session.path_selections:
            first_path = session.path_selections[0]
            path_label = SANDBOX_PATHS.get(first_path, first_path)
            question = self._generate_path_probe_question(session, first_path)
            return self._build_response(
                session, question,
                extra={"phase": "path_probe", "current_path": first_path},
            )
        # Ask which paths to compare
        path_list = SANDBOX_PATH_LIST_STR
        question = (
            f"好的，我已经对你的情况有了基本了解。接下来我们来做路径对比。\\n\\n"
            f"目前有以下方向可以分析：{path_list}。\\n"
            f"你想对比哪些方向？（可以说多个，比如\"就业和考研\"）"
        )
        return self._build_response(
            session, question,
            extra={"phase": "path_probe", "selecting_paths": True},
        )'''

new_transition = '''    def _transition_to_path_probe(self, session: SandboxSession) -> dict[str, Any]:
        """Transition from discovery to path probe phase.

        Shows path selection cards so the user can pick paths to compare.
        """
        session.advance_phase()
        logger.info("Sandbox[{}]: entering PATH_PROBE phase", session.session_id)

        # If user already specified paths (e.g., via API), skip the selection question
        if session.path_selections:
            first_path = session.path_selections[0]
            question = self._generate_path_probe_question(session, first_path)
            return self._build_response(
                session, question,
                extra={"phase": "path_probe", "current_path": first_path},
            )

        # Build path selection cards
        path_cards = []
        icons = {"career": "career", "graduate": "graduate", "civil": "civil", "major": "major"}
        colors = {"career": "#4A90D9", "graduate": "#7B68EE", "civil": "#E8913A", "major": "#50C878"}
        bg_colors = {"career": "#EBF3FB", "graduate": "#F0EDFC", "civil": "#FDF3E8", "major": "#E8F8EF"}
        time_labels = {"career": "3-6个月准备", "graduate": "6-12个月备考", "civil": "6-12个月备考", "major": "1-2个学期"}
        risk_labels = {"career": "竞争激烈", "graduate": "录取率不确定", "civil": "上岸难度大", "major": "学分转换风险"}

        for pt, label in SANDBOX_PATHS.items():
            path_cards.append({
                "type": pt,
                "name": label,
                "icon": icons.get(pt, "default"),
                "color": colors.get(pt, "#333"),
                "bgColor": bg_colors.get(pt, "#F5F5F5"),
                "match_score": 0,
                "insight": f"探索{label}方向的可能性",
                "time_label": time_labels.get(pt, ""),
                "risk_label": risk_labels.get(pt, ""),
                "recommended": False,
            })

        question = "我已经对你的情况有了基本了解。请选择你想对比的方向（可多选），然后说\"开始比对\"。"

        response = self._build_response(
            session, question,
            extra={"phase": "path_probe", "selecting_paths": True},
        )
        response["show_cards"] = True
        response["cards"] = path_cards
        response["report_text"] = question
        return response'''

content = content.replace(old_transition, new_transition)

# ═══════════════════════════════════════════════════════════════
# Fix 2: Also fix the "我没能识别出" fallback in _handle_path_probe 
# to show cards instead of text
# ═══════════════════════════════════════════════════════════════
old_fallback = '''            if not selections:
                path_list = SANDBOX_PATH_LIST_STR
                return self._build_response(
                    session, f"我没能识别出你想对比的方向。请从以下选择：{path_list}。可以说多个。",
                    extra={"selecting_paths": True},
                )'''

new_fallback = '''            if not selections:
                # Re-show path selection cards
                path_cards = []
                icons = {"career": "career", "graduate": "graduate", "civil": "civil", "major": "major"}
                colors = {"career": "#4A90D9", "graduate": "#7B68EE", "civil": "#E8913A", "major": "#50C878"}
                bg_colors = {"career": "#EBF3FB", "graduate": "#F0EDFC", "civil": "#FDF3E8", "major": "#E8F8EF"}
                time_labels = {"career": "3-6个月准备", "graduate": "6-12个月备考", "civil": "6-12个月备考", "major": "1-2个学期"}
                risk_labels = {"career": "竞争激烈", "graduate": "录取率不确定", "civil": "上岸难度大", "major": "学分转换风险"}
                for pt, label in SANDBOX_PATHS.items():
                    path_cards.append({
                        "type": pt, "name": label, "icon": icons.get(pt, "default"),
                        "color": colors.get(pt, "#333"), "bgColor": bg_colors.get(pt, "#F5F5F5"),
                        "match_score": 0, "insight": f"探索{label}方向的可能性",
                        "time_label": time_labels.get(pt, ""), "risk_label": risk_labels.get(pt, ""),
                        "recommended": False,
                    })
                resp = self._build_response(
                    session, "请点击上方卡片选择你想对比的方向（可多选），然后说\"开始比对\"。",
                    extra={"selecting_paths": True},
                )
                resp["show_cards"] = True
                resp["cards"] = path_cards
                resp["report_text"] = "请选择对比方向"
                return resp'''

content = content.replace(old_fallback, new_fallback)

with open("D:/ai-agent-learning/backend/sandbox/orchestrator.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Fix 1+2: orchestrator now returns cards for path selection")

# ═══════════════════════════════════════════════════════════════
# Fix 3: API chat endpoint passes show_cards/cards/report_text
# ═══════════════════════════════════════════════════════════════
with open("D:/ai-agent-learning/backend/app/api/v1/sandbox.py", "r", encoding="utf-8") as f:
    content = f.read()

old_api_return = '''    return SandboxChatResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        phase=result["phase"],
        finished=result.get("finished", False),
        message=result["message"],
        discovery_round=result.get("discovery_round", 0),
        max_discovery_rounds=result.get("max_discovery_rounds", 7),
        path_selections=result.get("path_selections", []),
        path_reports=result.get("path_reports"),
        projection_result=_build_projection(result.get("projection_result")),
        state=result.get("state"),
        error=result.get("error"),
    )'''

new_api_return = '''    return SandboxChatResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        phase=result["phase"],
        finished=result.get("finished", False),
        message=result["message"],
        discovery_round=result.get("discovery_round", 0),
        max_discovery_rounds=result.get("max_discovery_rounds", 7),
        path_selections=result.get("path_selections", []),
        path_reports=result.get("path_reports"),
        projection_result=_build_projection(result.get("projection_result")),
        show_cards=result.get("show_cards", False),
        cards=result.get("cards", []),
        report_text=result.get("report_text", ""),
        state=result.get("state"),
        error=result.get("error"),
    )'''

content = content.replace(old_api_return, new_api_return)

with open("D:/ai-agent-learning/backend/app/api/v1/sandbox.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Fix 3: API now propagates show_cards/cards/report_text")

print("\nBackend fixes done!")