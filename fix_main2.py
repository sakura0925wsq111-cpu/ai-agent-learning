with open('D:/ai-agent-learning/backend/app/main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix line 44 - replace the bad f-string
for i, line in enumerate(lines):
    if 'Environment:' in line and 'f-string' not in line and 'debug' in line:
        indent = line[:len(line) - len(line.lstrip())]
        lines[i] = indent + 'env_label = \"debug\" if settings.debug else \"production\"\n'
        lines.insert(i+1, indent + 'logger.info(f\"Environment: {env_label}\")\n')
        break

with open('D:/ai-agent-learning/backend/app/main.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Fixed line 44')
