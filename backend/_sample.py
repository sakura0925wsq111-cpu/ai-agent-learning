import httpx, sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = "http://127.0.0.1:8004"

# Use existing user from earlier
import sqlite3
conn = sqlite3.connect(r"D:\ai-agent-learning\backend\data\campuspal.db")
cur = conn.cursor()
cur.execute("SELECT id FROM users ORDER BY rowid DESC LIMIT 1")
uid = cur.fetchone()[0]
conn.close()

# Start sandbox, go through discovery to get a real comparison output
r = httpx.post(BASE + "/sandbox/start", json={"user_id": uid}, timeout=30)
sid = r.json()["session_id"]

# Discovery
answers = [
    "软件工程大三，会Java和Python，做过两个Web项目，对后端和分布式感兴趣，GPA 3.4",
    "性格内敛但逻辑思维强，喜欢自己钻研问题，不太擅长公开演讲",
    "家境普通想早点工作减轻负担，但也觉得读研能去更好的平台",
    "能接受考研的辛苦和压力，但一定要考上985，否则觉得不划算",
    "如果就业的话目标是大厂后端开发，对AI方向也有兴趣但基础不够",
    "希望30岁前成为技术专家，走技术路线不要管理岗",
]
for ans in answers:
    r = httpx.post(BASE + "/sandbox/chat", json={
        "user_id": uid, "session_id": sid, "message": ans
    }, timeout=60)

# Select paths and push through
data = r.json()
if data["phase"] == "path_probe":
    r = httpx.post(BASE + "/sandbox/chat", json={
        "user_id": uid, "session_id": sid,
        "message": "对比考研和就业"
    }, timeout=60)
    data = r.json()
    
    # Answer probe questions - may need several rounds
    for i in range(10):
        r = httpx.post(BASE + "/sandbox/chat", json={
            "user_id": uid, "session_id": sid,
            "message": "方向明确，请继续进行分析对比"
        }, timeout=120)
        data = r.json()
        if data.get("finished"):
            break

print("Phase:", data.get("phase"))
print("Finished:", data.get("finished"))

result = data.get("projection_result")
if result and isinstance(result, dict):
    print("\n========== PROJECTION RESULT ==========")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:3000])
else:
    print("No projection result yet")
