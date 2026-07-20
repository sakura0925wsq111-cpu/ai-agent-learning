import sqlite3
conn = sqlite3.connect(r"D:\ai-agent-learning\backend\data\campuspal.db")
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cur.fetchall()
print("Tables:", [t[0] for t in tables])

for table in ["users", "conversations", "memories"]:
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    count = cur.fetchone()[0]
    print(f"{table}: {count} records")

cur.execute("SELECT id, nickname, major, grade, target FROM users")
for row in cur.fetchall():
    print(f"User: {row}")

cur.execute("SELECT user_id, key, value, importance FROM memories")
for row in cur.fetchall():
    print(f"Memory: {row}")

conn.close()
print("DB verification complete")
