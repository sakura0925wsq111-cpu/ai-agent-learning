import httpx, sys, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = "http://127.0.0.1:8005"
LOG = []

def log(section, role, text):
    LOG.append(f"\n{'='*60}\n【{section}】{role}\n{'='*60}\n{text}")

# ====================================================
# STEP 1: 注册
# ====================================================
r = httpx.post(BASE + "/api/v1/users", json={
    "nickname": "林同学",
    "major": "软件工程",
    "grade": "大三"
}, timeout=30)
uid = r.json()["data"]["id"]
log("1. 注册", "系统", f"用户创建成功，ID: {uid[:8]}...\n昵称: 林同学, 专业: 软件工程, 年级: 大三")

# ====================================================
# STEP 2: 沙盘 Discovery
# ====================================================
r = httpx.post(BASE + "/sandbox/start", json={"user_id": uid}, timeout=30)
sid = r.json()["session_id"]
q1 = r.json()["message"]
log("2. 沙盘 · Discovery", "AI", q1)
LOG.append("\n---\n")

# Discovery rounds
user_answers = [
    ("林同学", "你好！我目前软件工程大三，平时成绩中等偏上，会Java和Python，但对未来方向比较迷茫。身边同学有的准备考研，有的在找实习，我不太确定哪条路更适合自己。"),
    ("林同学", "性格方面我比较内向但做事认真，喜欢一个人钻研技术问题。不太擅长社交和演讲，但对写代码和调试bug很有耐心。"),
    ("林同学", "家庭条件算是一般吧，父母都是普通工薪阶层，没有特别大的人脉资源。他们支持我考研，但也尊重我直接工作的选择。我自己希望能尽快经济独立，减轻家里负担。"),
    ("林同学", "技术上我比较熟悉Java后端，Spring Boot框架用了一年多，做过一个校园二手交易平台的项目。对数据库和系统设计也有一些了解。最近在自学Docker和微服务。"),
    ("林同学", "我觉得自己最大的优点是执行力还不错，定下来的事情一般能坚持做完。缺点是容易纠结，做重大决定时会想很多。"),
    ("林同学", "如果考研的话我想考本校或者更好的211/985的计算机专业。如果就业的话想去杭州或者上海的互联网公司做后端开发。两个方向我觉得都有吸引力，但确实拿不定主意。"),
]

for i, (_, ans) in enumerate(user_answers):
    log(f"2.{i+1}", "林同学", ans)
    r = httpx.post(BASE + "/sandbox/chat", json={
        "user_id": uid, "session_id": sid, "message": ans
    }, timeout=60)
    reply = r.json()["message"]
    log(f"2.{i+1}", "AI", reply)
    LOG.append("---")

phase = r.json()["phase"]
log("2.7", "系统", f"Discovery完成，进入阶段: {phase}")

# ====================================================
# STEP 3: 沙盘 Path Probe
# ====================================================
LOG.append(f"\n{'='*60}\n【3. 沙盘 · Path Probe】\n{'='*60}")

# Select paths
log("3.1", "林同学", "我想对比「就业」和「考研」这两个方向")
r = httpx.post(BASE + "/sandbox/chat", json={
    "user_id": uid, "session_id": sid,
    "message": "我想对比「就业」和「考研」这两个方向"
}, timeout=60)
data = r.json()
log("3.1", "AI", data["message"])
LOG.append("---")

# Answer path probe questions
probe_answers = [
    ("林同学", "就业的话我比较倾向去中大型互联网公司做后端开发，Java技术栈，对创业公司兴趣不大。期望薪资应届的话15k左右吧。"),
    ("林同学", "考研的话目标本校或者浙大计算机，主要想提升学历和深入学一些分布式系统、AI相关的知识。但也担心考不上好学校浪费时间。"),
    ("林同学", "关于就业，我对工作城市没有特别的执念，杭州、上海、深圳都可以。"),
    ("林同学", "考研方面，我英语基础还行，数学一般，政治完全没概念。如果要考研的话可能需要报班。"),
]

for i, (_, ans) in enumerate(probe_answers):
    log(f"3.{i+2}", "林同学", ans)
    r = httpx.post(BASE + "/sandbox/chat", json={
        "user_id": uid, "session_id": sid, "message": ans
    }, timeout=120)
    data = r.json()
    log(f"3.{i+2}", "AI", data.get("message", ""))
    LOG.append("---")
    if data.get("finished"):
        break

# Final sandbox result
projection = data.get("projection_result")
log("沙盘结果", "系统", f"沙盘完成!\n\n最终对比报告:\n{json.dumps(projection, ensure_ascii=False, indent=2) if projection else '无'}")

# ====================================================
# STEP 4: Handoff to Planning Agent
# ====================================================
r = httpx.get(BASE + f"/sandbox/handoff?session_id={sid}&path_type=career", timeout=60)
h = r.json()
log("4. 交接", "系统", f"用户选择「就业规划」方向\n上下文已从沙盘交接给就业规划Agent")
log("4.1", "AI（就业规划Agent）", h["initial_question"])

# Save agent_state for growth chat
agent_state = h.get("agent_state", {})

# ====================================================
# STEP 5: 规划 Agent 深度追问
# ====================================================
# Start growth session with handoff context
r = httpx.post(BASE + "/api/v1/growth/start", json={
    "user_id": uid, "agent": "career"
}, timeout=60)
gsid = r.json()["data"]["session_id"]
LOG.append("---")

planning_answers = [
    ("林同学", "我目前最拿得出手的是那个校园二手交易平台，Spring Boot + Vue + MySQL，我负责了整个后端的设计和开发，包括用户认证、商品发布、订单管理等模块。能独立完成CRUD到部署的完整链路。"),
    ("林同学", "理想的公司类型是BAT或者TMD这种级别的互联网公司，如果进不了大厂的话，像有赞、涂鸦智能这种中型技术公司也可以接受。关键是要有技术成长空间。"),
    ("林同学", "薪资方面应届的话15k-20k吧，更看重前两年的成长速度。不太在意加班，只要做的事情有意义、能学到东西就行。"),
    ("林同学", "技术上的短板主要是分布式系统和高并发方面经验不足，目前只会单机部署。另外算法方面刷过一些LeetCode但不够系统。"),
    ("林同学", "对，我接下来半年可以全职投入求职准备。目标是秋招拿到满意offer。"),
]

for i, (_, ans) in enumerate(planning_answers):
    log(f"5.{i+1}", "林同学", ans)
    r = httpx.post(BASE + "/api/v1/growth/chat", json={
        "user_id": uid, "agent": "career",
        "session_id": gsid, "message": ans
    }, timeout=60)
    data = r.json()["data"]
    log(f"5.{i+1}", "AI（就业规划Agent）", data.get("message", ""))
    LOG.append("---")
    if data.get("finished") or data.get("stage") == "report":
        break

final_report = data.get("report")
log("规划结果", "系统", f"规划Agent完成!\n\n最终规划报告:\n{json.dumps(final_report, ensure_ascii=False, indent=2) if final_report else '无'}")

# ====================================================
# Save full log
# ====================================================
full = "\n".join(LOG)
with open(r"D:\ai-agent-learning\backend\user_journey_log.txt", "w", encoding="utf-8") as f:
    f.write(full)

print("Full journey saved to user_journey_log.txt")
print(f"Log length: {len(full)} chars")
