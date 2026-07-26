import sys
sys.stdout.reconfigure(encoding="utf-8")

with open("D:/ai-agent-learning/backend/sandbox/orchestrator.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix inner quotes: 说"开始比对" → 说【开始比对】
old = chr(35828) + chr(34) + chr(24320) + chr(22987) + chr(27604) + chr(23545) + chr(34)
new = chr(35828) + chr(12304) + chr(24320) + chr(22987) + chr(27604) + chr(23545) + chr(12305)
content = content.replace(old, new)

with open("D:/ai-agent-learning/backend/sandbox/orchestrator.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Fixed inner quotes")