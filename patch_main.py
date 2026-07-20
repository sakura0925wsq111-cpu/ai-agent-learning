with open('D:/ai-agent-learning/backend/app/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add growth import
old_import = 'from app.api.v1.diagnosis import router as diagnosis_router_v1'
new_import = old_import + '\nfrom app.api.v1.growth import router as growth_router_v1'
content = content.replace(old_import, new_import)

# Add growth router
old_router = 'app.include_router(diagnosis_router_v1, prefix=\"/api/v1\")'
new_router = old_router + '\napp.include_router(growth_router_v1, prefix=\"/api/v1\")'
content = content.replace(old_router, new_router)

with open('D:/ai-agent-learning/backend/app/main.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
