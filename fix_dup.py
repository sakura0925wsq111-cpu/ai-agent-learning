with open('D:/ai-agent-learning/backend/app/main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Remove duplicate growth imports, keep only one
seen_growth_import = False
new_lines = []
for line in lines:
    if 'from app.api.v1.growth import' in line:
        if not seen_growth_import:
            seen_growth_import = True
            new_lines.append(line)
        # else skip duplicate
    else:
        new_lines.append(line)

with open('D:/ai-agent-learning/backend/app/main.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print('Fixed duplicates')
