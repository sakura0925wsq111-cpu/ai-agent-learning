with open('D:/ai-agent-learning/backend/app/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = 'logger.info(f\"Environment: {\\\"debug\\\" if settings.debug else \\\"production\\\"}\")'
new = 'env_label = \"debug\" if settings.debug else \"production\"\n    logger.info(f\"Environment: {env_label}\")'

if old in content:
    content = content.replace(old, new)
    with open('D:/ai-agent-learning/backend/app/main.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('FIXED')
else:
    print('NOT FOUND - searching...')
    for i, line in enumerate(content.split('\n')):
        if 'debug' in line and 'production' in line:
            print(f'Line {i+1}: {repr(line)}')
