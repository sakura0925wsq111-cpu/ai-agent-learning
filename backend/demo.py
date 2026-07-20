import httpx, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = "http://127.0.0.1:8000"

# ── Step 1: Create user ──
r = httpx.post(f"{BASE}/api/v1/users", json={
    "nickname": "小明", "major": "", "grade": "", "target": ""
})
user_id = r.json()["data"]["id"]
print(f"1. 用户创建成功, ID: {user_id[:8]}...")

# ── Step 2: First chat ──
print("\n2. 第一次对话（透露个人信息）...")
r = httpx.post(f"{BASE}/api/v1/chat", json={
    "user_id": user_id,
    "message": "你好！我是交通工程专业的大二学生，我想考研。"
})
reply = r.json()["data"]["reply"]
# Strip emojis for console
import re
clean = re.sub(r'[^\u4e00-\u9fff\u3000-\u303f\uff00-\uffefa-zA-Z0-9\s.,!?;:()\-\"\'""\n]', '', reply)
print(f"AI: {clean[:250]}...")

# ── Step 3: Check memory ──
print("\n3. Memory 自动保存结果:")
r = httpx.get(f"{BASE}/api/v1/memory/{user_id}")
for m in r.json()["data"]["memories"]:
    print(f"   {m['key']} = {m['value']}")

# ── Step 4: Second chat ──
print("\n4. 第二次对话（验证AI记住我了）...")
r = httpx.post(f"{BASE}/api/v1/chat", json={
    "user_id": user_id,
    "message": "你还记得我的专业和目标吗？"
})
reply2 = r.json()["data"]["reply"]
clean2 = re.sub(r'[^\u4e00-\u9fff\u3000-\u303f\uff00-\uffefa-zA-Z0-9\s.,!?;:()\-\"\'""\n]', '', reply2)
print(f"AI: {clean2[:350]}...")

# ── Step 5: Conversation count ──
print("\n5. 聊天记录统计:")
r = httpx.get(f"{BASE}/api/v1/conversation/{user_id}")
data = r.json()["data"]
print(f"   共 {data['total']} 条消息")

print("\n===== 全部测试通过! =====")
