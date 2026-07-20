import urllib.request, json, sys

def api(method, path, data=None):
    url = "http://127.0.0.1:8000" + path
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "body": e.read().decode()}

print("=== Step 1: List paths ===")
r = api("GET", "/sandbox/paths")
print(json.dumps(r, ensure_ascii=False, indent=2))

print("\n=== Step 2: Start session ===")
r = api("POST", "/sandbox/start", {"user_id": "test_user_001"})
phase = r.get("phase", "?")
msg = r.get("message", "")[:300]
dr = r.get("discovery_round", -1)
sid = r["session_id"]
print("Phase:", phase)
print("Message:", msg)
print("Discovery round:", dr)
print("Session ID:", sid)

print("\n=== Step 3: Chat turn 1 ===")
r = api("POST", "/sandbox/chat", {
    "user_id": "test_user_001",
    "session_id": sid,
    "message": "我是计算机专业大三的学生，成绩中等偏上，目前在纠结是直接就业还是考研。我对编程有兴趣但不算特别强，性格偏稳，家里人希望我考公。"
})
print("Phase:", r.get("phase"))
print("Message:", r.get("message", "")[:300])
print("Discovery round:", r.get("discovery_round"))
prof = r.get("state", {}).get("user_profile", {})
if prof:
    print("Profile so far:", json.dumps({k:v for k,v in prof.items() if v}, ensure_ascii=False, indent=2))

print("\n=== Step 4: Chat turn 2 ===")
r = api("POST", "/sandbox/chat", {
    "user_id": "test_user_001",
    "session_id": sid,
    "message": "我最看重的是稳定性和收入，但也希望工作能有成长空间。家里经济条件一般，不想给父母增加负担。"
})
print("Phase:", r.get("phase"))
print("Message:", r.get("message", "")[:300])
print("Discovery round:", r.get("discovery_round"))
prof = r.get("state", {}).get("user_profile", {})
if prof:
    print("Profile so far:", json.dumps({k:v for k,v in prof.items() if v}, ensure_ascii=False, indent=2))

print("\n=== Step 5: Chat turn 3 ===")
r = api("POST", "/sandbox/chat", {
    "user_id": "test_user_001",
    "session_id": sid,
    "message": "我英语一般过了四级，数学基础还可以。以后想去杭州或者成都发展，不太想去一线城市卷。"
})
print("Phase:", r.get("phase"))
print("Message:", r.get("message", "")[:300])
print("Discovery round:", r.get("discovery_round"))
prof = r.get("state", {}).get("user_profile", {})
if prof:
    print("Profile:", json.dumps({k:v for k,v in prof.items() if v}, ensure_ascii=False, indent=2))

print("\n=== Step 6: Chat turn 4 ===")
r = api("POST", "/sandbox/chat", {
    "user_id": "test_user_001",
    "session_id": sid,
    "message": "我平时喜欢钻研技术博客，也参加过学校的ACM社团但没拿过奖。执行力一般吧，有时候会比较拖延。"
})
print("Phase:", r.get("phase"))
print("Message:", r.get("message", "")[:300])
print("Discovery round:", r.get("discovery_round"))
prof = r.get("state", {}).get("user_profile", {})
if prof:
    print("Profile:", json.dumps({k:v for k,v in prof.items() if v}, ensure_ascii=False, indent=2))

print("\n=== Step 7: Chat turn 5 ===")
r = api("POST", "/sandbox/chat", {
    "user_id": "test_user_001",
    "session_id": sid,
    "message": "我觉得自己抗压能力还行，大学期间也做过几个课程项目，有一个Java Web的项目做得还不错。目前没有实习经历，比较担心这点。"
})
print("Phase:", r.get("phase"))
print("Message:", r.get("message", "")[:300])
print("Discovery round:", r.get("discovery_round"))
print("Path selections:", r.get("path_selections", []))
