import httpx

r = httpx.get("http://127.0.0.1:8000/api/v1/conversation/86c5bda1-6202-4e6f-9cf0-53bf102ccb34")
data = r.json()
for m in data["data"]["messages"]:
    role = m["role"]
    content = m["content"]
    print(f"=== {role} ({len(content)} chars) ===")
    # Show last 400 chars where JSON would be
    print(content[-400:])
    print()
