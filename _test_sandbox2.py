import urllib.request, json

def api(method, path, data=None):
    url = "http://127.0.0.1:8000" + path
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "body": e.read().decode()}

sid = "f25311e3-8488-4f19-941e-c840537aca8c"

# Continue: Answer path probe question for career
print("=== Turn 6: Answer path probe ===")
r = api("POST", "/sandbox/chat", {
    "user_id": "test_user_001",
    "session_id": sid,
    "message": "我做过一个Java Web的校园商铺项目，用了Spring Boot加MySQL，实现了一些基本的CRUD功能。对后端开发比较感兴趣。"
})
print("Phase:", r.get("phase"))
print("Message:", r.get("message", "")[:300])
print("Path selections:", r.get("path_selections", []))

print()
print("=== Turn 7: Continue path probe ===")
r = api("POST", "/sandbox/chat", {
    "user_id": "test_user_001",
    "session_id": sid,
    "message": "我想对比就业和考研这两条路。"
})
print("Phase:", r.get("phase"))
print("Message:", r.get("message", "")[:300])
print("Path selections:", r.get("path_selections", []))

print()
print("=== Turn 8: Answer more path questions ===")
r = api("POST", "/sandbox/chat", {
    "user_id": "test_user_001",
    "session_id": sid,
    "message": "考研的话我想考本校的计算机研究生，主要是想提升学历增加竞争力。但我担心备考时间不够，而且家里经济条件一般，继续读研有经济压力。"
})
print("Phase:", r.get("phase"))
print("Message:", r.get("message", "")[:300])
print("Path selections:", r.get("path_selections", []))
print("Finished:", r.get("finished"))
print("Path reports count:", len(r.get("path_reports") or {}))

print()
print("=== Turn 9: If still in path_probe ===")
r = api("POST", "/sandbox/chat", {
    "user_id": "test_user_001",
    "session_id": sid,
    "message": "好的，我的情况基本就这些了，请帮我分析对比吧。"
})
print("Phase:", r.get("phase"))
print("Finished:", r.get("finished"))
print("Message:", r.get("message", "")[:300])
path_reports = r.get("path_reports") or {}
print("Path reports count:", len(path_reports))
proj = r.get("projection_result")
if proj:
    print("Has projection result: YES")
    print("Summary:", proj.get("summary", "")[:200])
else:
    print("No projection result yet")
