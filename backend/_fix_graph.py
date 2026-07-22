import re
path = r"D:\ai-agent-learning\backend\planning\graph.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace import
content = content.replace(
    "from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver",
    "from langgraph.checkpoint.memory import InMemorySaver"
)

# Remove aiosqlite import
content = re.sub(r'\n\s*import aiosqlite\n', '\n', content)

# Replace the checkpointer creation - find from "import aiosqlite" to "return builder.compile"
# Simpler: find "db_path" and replace the whole block
pattern = r'(\n    # .*?checkpointer.*?\n).*?(?=\n    return builder\.compile)'
replacement = '''
    # InMemory checkpointer (no event-loop issues)
    checkpointer = InMemorySaver()
    logger.info("GrowthGraph: InMemorySaver ready")
'''
content = re.sub(pattern, replacement, content, flags=re.DOTALL)

# Also try simpler approach: just find the lines between "# ── SQLite" and "return builder.compile"
lines = content.split('\n')
new_lines = []
skip = False
for line in lines:
    if 'SQLite checkpointer' in line or 'aiosqlite' in line.strip():
        skip = True
        continue
    if skip and 'return builder.compile' in line:
        new_lines.append('')
        new_lines.append('    # InMemory checkpointer')
        new_lines.append('    checkpointer = InMemorySaver()')
        new_lines.append('    logger.info("GrowthGraph: InMemorySaver ready")')
        new_lines.append('')
        skip = False
    if not skip:
        new_lines.append(line)

content = '\n'.join(new_lines)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("OK: switched to InMemorySaver")
