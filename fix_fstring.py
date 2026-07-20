with open('D:/ai-agent-learning/backend/app/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the f-string backslash issue
content = content.replace(
    "logger.info(f'Environment: {\"debug\" if settings.debug else \"production\"}')",
    "env_label = 'debug' if settings.debug else 'production'\n    logger.info(f'Environment: {env_label}')"
)

with open('D:/ai-agent-learning/backend/app/main.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed f-string')
