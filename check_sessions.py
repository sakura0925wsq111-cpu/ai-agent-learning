import sqlite3, json
conn = sqlite3.connect('D:/ai-agent-learning/backend/data/campuspal.db')
rows = conn.execute("SELECT id, user_id, status, question_count, profile_json FROM diagnosis_sessions ORDER BY created_at DESC LIMIT 5").fetchall()
for i, r in enumerate(rows):
    print(f'--- Session {i+1} ---')
    print(f'ID: {r[0]}')
    print(f'User: {r[1]}')
    print(f'Status: {r[2]}')
    print(f'Questions: {r[3]}')
    if r[4]:
        p = json.loads(r[4])
        print(f'Profile: {json.dumps(p, ensure_ascii=False, indent=2)}')
    print()
conn.close()
