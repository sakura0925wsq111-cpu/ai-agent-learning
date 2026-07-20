import sqlite3
for path in ['D:/ai-agent-learning/backend/campuspal.db', 'D:/ai-agent-learning/backend/data/campuspal.db']:
    try:
        conn = sqlite3.connect(path)
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print(f'=== {path} ===')
        for t in tables:
            print(f'  {t[0]}')
        conn.close()
    except Exception as e:
        print(f'Error: {e}')
