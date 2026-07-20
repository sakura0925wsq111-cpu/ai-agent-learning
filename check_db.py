import sqlite3
conn = sqlite3.connect('D:/ai-agent-learning/backend/campuspal.db')
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
for t in tables:
    print(t[0])
conn.close()
