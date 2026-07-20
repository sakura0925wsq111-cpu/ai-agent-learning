import urllib.request, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def api(method, path, data=None):
    url = "http://127.0.0.1:8000" + path
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())

# Start a fresh session and run a complete flow
print("=" * 60)
print("CAMPUSPAL DECISION SANDBOX - COMPLETE CHAT LOG")
print("=" * 60)

# Step 1: Start session
print("\n[SYSTEM] Starting new sandbox session...")
r = api("POST", "/sandbox/start", {"user_id": "demo_user_001"})
sid = r["session_id"]

def show(msg, label):
    if isinstance(msg, str) and len(msg) > 500:
        msg = msg[:500] + "..."
    print("{0}: {1}".format(label, msg))

# Discovery Phase
show(r["message"], "\n[Phase 1 - Discovery]\n[SANDBOX R1]")

# Turn 1
msg1 = "我是计算机专业大三的学生，成绩中等偏上，目前在纠结是直接就业还是考研。我对编程有兴趣但不算特别强，性格偏稳，家里人希望我考公。"
show(msg1, "\n[USER T1]")
r = api("POST", "/sandbox/chat", {"user_id": "demo_user_001", "session_id": sid, "message": msg1})
show(r["message"], "[SANDBOX R2]")

# Turn 2
msg2 = "我最看重的是稳定性和收入，但也希望工作能有成长空间。家里经济条件一般，不想给父母增加负担。"
show(msg2, "\n[USER T2]")
r = api("POST", "/sandbox/chat", {"user_id": "demo_user_001", "session_id": sid, "message": msg2})
show(r["message"], "[SANDBOX R3]")

# Turn 3
msg3 = "我英语一般过了四级，数学基础还可以。以后想去杭州或者成都发展，不太想去一线城市卷。"
show(msg3, "\n[USER T3]")
r = api("POST", "/sandbox/chat", {"user_id": "demo_user_001", "session_id": sid, "message": msg3})
show(r["message"], "[SANDBOX R4]")

# Turn 4
msg4 = "我平时喜欢钻研技术博客，也参加过学校的ACM社团但没拿过奖。执行力一般吧，有时候会比较拖延。"
show(msg4, "\n[USER T4]")
r = api("POST", "/sandbox/chat", {"user_id": "demo_user_001", "session_id": sid, "message": msg4})
show(r["message"], "[SANDBOX R5]")

# Turn 5
msg5 = "我觉得自己抗压能力还行，大学期间也做过几个课程项目，有一个Java Web的项目做得还不错。目前没有实习经历，比较担心这点。"
show(msg5, "\n[USER T5]")
r = api("POST", "/sandbox/chat", {"user_id": "demo_user_001", "session_id": sid, "message": msg5})
msg = r["message"]
phase = r["phase"]
show(msg, "[SANDBOX R6]")
print("\n[Phase transition: {0}]".format(phase))

# Turns 6-7: Path probe
msg6 = "我想对比就业、考研这两条路，考公也帮我顺便看看吧。"
show(msg6, "\n[Phase 2 - Path Probe]\n[USER T6]")
r = api("POST", "/sandbox/chat", {"user_id": "demo_user_001", "session_id": sid, "message": msg6})
show(r["message"], "[SANDBOX R7]")
print("[Selected paths: {0}]".format(r.get("path_selections", [])))

# Turn 7: answer path probe
msg7 = "就业的话我对后端开发比较感兴趣，希望去中型互联网公司。考研的话想考本校计算机研究生，提升学历。没报班。"
show(msg7, "\n[USER T7]")
r = api("POST", "/sandbox/chat", {"user_id": "demo_user_001", "session_id": sid, "message": msg7})
show(r["message"], "[SANDBOX R8]")

# Turn 8 - continue probing
msg8 = "就业主要担心技术不够深面试过不了。考研担心英语拖后腿。考公觉得行测申论完全没接触过。"
show(msg8, "\n[USER T8]")
r = api("POST", "/sandbox/chat", {"user_id": "demo_user_001", "session_id": sid, "message": msg8})

phase = r["phase"]
msg = r["message"]
finished = r.get("finished", False)
show(msg, "[SANDBOX R9]")
print("[Phase: {0}, Finished: {1}]".format(phase, finished))

# Check if completed
if finished:
    show(r.get("message", ""), "\n[Phase 3+4 - Simulation + Projection Complete!]\n[SANDBOX FINAL]")
    
    print("\n" + "=" * 60)
    print("FINAL COMPARISON RESULT")
    print("=" * 60)
    
    proj = r.get("projection_result", {})
    if proj:
        print("\n--- Summary ---")
        print(proj.get("summary", "")[:600])
        
        print("\n--- Timeline Projections ---")
        for p in proj.get("projections", []):
            print("\n  [{0}] {1}".format(p["path_type"], p.get("core_insight", "")[:300]))
            tp = p.get("time_projection", {})
            print("    3 months: " + tp.get("short_term", "")[:200])
            print("    1 year:   " + tp.get("mid_term", "")[:200])
            print("    2-3 years: " + tp.get("long_term", "")[:200])
        
        print("\n--- Comparison Matrix ---")
        cm = proj.get("comparison_matrix", {})
        dims = cm.get("dimensions", [])
        print("  Dimensions: " + ", ".join(dims))
        for pt, sc in cm.get("scores", {}).items():
            print("  {0}: {1}".format(pt, sc))
        
        print("\n--- Decision Guide ---")
        dg = proj.get("decision_guide", {})
        for item in dg.get("if_you_value_X_then_Y", []):
            print("  {0} -> {1}".format(
                item.get("condition", ""), item.get("recommendation", "")[:200]
            ))
        
        print("\n--- Key Uncertainties ---")
        for u in proj.get("key_uncertainties", []):
            print("  * {0}: {1}".format(u.get("factor", ""), u.get("impact", "")[:150]))
else:
    # Ask one more time
    msg9 = "差不多了，帮我做对比分析吧。"
    show(msg9, "\n[USER T9]")
    r = api("POST", "/sandbox/chat", {"user_id": "demo_user_001", "session_id": sid, "message": msg9})
    show(r.get("message", ""), "[SANDBOX R10]")
    print("[Phase: {0}, Finished: {1}]".format(r.get("phase"), r.get("finished")))
    if r.get("finished"):
        show(r.get("projection_result", {}).get("summary", "")[:300], "[RESULT SUMMARY]")

print("\n[DONE] Session ID: {0}".format(sid))
