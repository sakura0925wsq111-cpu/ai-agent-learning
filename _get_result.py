import urllib.request, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def api(method, path, data=None):
    url = "http://127.0.0.1:8000" + path
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())

sid = "f25311e3-8488-4f19-941e-c840537aca8c"

print("=== FINAL RESULT ===")
r = api("GET", "/sandbox/result/" + sid)
print("Session ID:", r.get("session_id"))
print("Finished:", r.get("finished"))
print("Path selections:", r.get("path_selections"))

reports = r.get("path_reports") or {}
print("\n--- Path Reports ({0} paths) ---".format(len(reports)))
for pt, report in reports.items():
    s = report.get("summary", "")[:150]
    print("  [{0}]: {1}".format(pt, s))

proj = r.get("projection_result")
if proj:
    print("\n--- Projection Summary ---")
    print(proj.get("summary", "")[:400])
    
    print("\n--- Timeline Projections ---")
    for p in proj.get("projections", []):
        pt = p.get("path_type", "?")
        ci = p.get("core_insight", "")[:200]
        tp = p.get("time_projection", {})
        st = tp.get("short_term", "")[:120]
        print("  [{0}] insight: {1}".format(pt, ci))
        print("       short_term: {0}".format(st))
    
    print("\n--- Comparison Matrix ---")
    cm = proj.get("comparison_matrix", {})
    dims = cm.get("dimensions", [])
    scores = cm.get("scores", {})
    print("  Dimensions:", dims)
    for pt, sc in scores.items():
        print("  {0}: {1}".format(pt, sc))
    
    print("\n--- Decision Guide (If X then Y) ---")
    dg = proj.get("decision_guide", {})
    for item in dg.get("if_you_value_X_then_Y", [])[:5]:
        cond = item.get("condition", "")
        rec = item.get("recommendation", "")[:150]
        print("  If {0} -> {1}".format(cond, rec))
    
    print("\n--- Key Uncertainties ---")
    for u in proj.get("key_uncertainties", [])[:5]:
        print("  - {0}: {1}".format(u.get("factor", ""), u.get("impact", "")[:100]))
else:
    print("No projection result available")
