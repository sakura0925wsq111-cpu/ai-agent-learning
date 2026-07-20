import httpx
BASE = "http://127.0.0.1:8000"

r = httpx.post(f"{BASE}/api/v1/users", json={"nickname": "张同学"})
uid = r.json()["data"]["id"]
print(f"User: {uid[:8]}...")

r = httpx.post(f"{BASE}/api/v1/chat", json={"user_id": uid, "message": "你好，我是交通工程专业大二学生，想考研。"})
reply = r.json()["data"]["reply"]
print(f"Reply len: {len(reply)}")
has_json = "memory_update" in reply
print(f"Has memory_update JSON: {has_json}")
print(f"First 100: {reply[:100]}")

r = httpx.get(f"{BASE}/api/v1/memory/{uid}")
mems = r.json()["data"]["memories"]
print(f"\nMemory count: {len(mems)}")
for m in mems:
    print(f"  {m['key']} = {m['value']}")

r = httpx.post(f"{BASE}/api/v1/chat", json={"user_id": uid, "message": "我的专业和目标是什么？"})
reply2 = r.json()["data"]["reply"]
print(f"\nSecond chat - has major: {'交通工程' in reply2}, has goal: {'考研' in reply2}")
print(f"First 150: {reply2[:150]}")
