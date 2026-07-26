import requests, json, sys

base = "http://127.0.0.1:8000"
ok = 0
fail = 0

def test(name, fn):
    global ok, fail
    try:
        fn()
        ok += 1
        print(f"  [PASS] {name}")
    except Exception as e:
        fail += 1
        print(f"  [FAIL] {name}: {e}")

# Login
r = requests.post(f"{base}/api/v1/users/login", json={
    "student_id": "fixtest01", "password": "test123456"
}, timeout=5)
uid = r.json()["data"]["user_id"]

# Start sandbox
r = requests.post(f"{base}/api/v1/sandbox/start", json={
    "user_id": uid
}, timeout=15)
sid = r.json()["session_id"]
print(f"Session: {sid}")

# Run through discovery quickly
answers = ["软件工程大三", "成绩不错", "迷茫不知道选什么方向", "对技术有兴趣", "想赚钱也想稳定"]
for i, a in enumerate(answers):
    r = requests.post(f"{base}/api/v1/sandbox/chat", json={
        "session_id": sid, "user_id": uid, "message": a
    }, timeout=30)
    d = r.json()
    phase = d.get("phase", "")
    show_cards = d.get("show_cards", False)
    cards_count = len(d.get("cards", []))
    print(f"  Round {i+1}: phase={phase}, show_cards={show_cards}, cards={cards_count}")
    
    if show_cards:
        # Test the path selection cards
        cards = d.get("cards", [])
        def t_cards():
            assert len(cards) >= 4, f"Expected 4 path cards, got {len(cards)}"
            # Each card should have type, name, icon
            for c in cards:
                assert "type" in c, f"Card missing type: {c}"
                assert "name" in c, f"Card missing name: {c}"
            print(f"  Card types: {[c['type'] for c in cards]}")
        
        def t_select():
            # Select career and graduate paths
            r2 = requests.post(f"{base}/api/v1/sandbox/chat", json={
                "session_id": sid, "user_id": uid, 
                "message": "开始比对 就业和考研"
            }, timeout=30)
            d2 = r2.json()
            paths = d2.get("path_selections", [])
            print(f"  Selected paths: {paths}")
            assert "career" in paths or "graduate" in paths, f"Paths not parsed: {paths}"
        
        test("Path cards returned", t_cards)
        test("Path selection parsed", t_select)
        break

print(f"\nResults: {ok} passed, {fail} failed")
sys.exit(0 if fail == 0 else 1)