import requests, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = 'http://127.0.0.1:8000/api/v1/diagnosis'

r = requests.post(f'{BASE}/start', json={'user_id': '1'})
d = r.json()
sid = d['data']['session_id']
first_q = d['data']['first_question']
results = []
results.append(f'{"="*60}')
results.append('🎓 CampusPal 成长诊断 完整演示')
results.append(f'{"="*60}')
results.append(f'【第1轮 - 启动诊断】 Session: {sid[:8]}...')
results.append(f'🤖 AI: {first_q}')
results.append('')

# 模拟完整对话
msgs = [
    '我学交通工程，现在大二',
    '想考研，感觉现在本科学历不太够',
    '因为本科竞争力不够，我们专业好的设计院都要研究生',
    '主要是我们专业本科毕业大多去施工单位，我不想下工地',
    '我对编程和数据分析感兴趣，自学过Python，也做过一些小项目',
    '执行力还不错，我喜欢定计划然后按计划推进，不太会半途而废',
    '学习效率中等吧，不算学霸但也能保持中上游',
    '我觉得自己比较稳健，做事会先想清楚再动手，风险偏好比较低',
    '跨考计算机或者交通+AI结合的方向',
    '每天大概能学2-3小时，周末会多一些',
    '嗯我觉得性格偏内向一点，但做事比较踏实认真',
]

for i, msg in enumerate(msgs):
    r = requests.post(f'{BASE}/chat', json={'session_id': sid, 'message': msg})
    d = r.json()
    reply = d['data']['reply']
    finish = d['data']['finish']
    results.append(f'【第{i+2}轮】')
    results.append(f'👤 用户: {msg}')
    results.append(f'🤖 AI: {reply}')
    profile = d['data'].get('profile')
    if profile:
        results.append(f'📊 当前画像: {json.dumps(profile, ensure_ascii=False)}')
    results.append('')
    if finish:
        results.append(f'{"="*60}')
        results.append('🏁 诊断完成！最终画像：')
        results.append(f'{"="*60}')
        results.append(json.dumps(d['data']['profile'], ensure_ascii=False, indent=2))
        break

if not finish:
    results.append('⚠️ 对话已进行12轮，AI仍在追问中...（正常现象，画像越精准追问越多）')

with open('D:/ai-agent-learning/demo_output2.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print('Full demo completed!')
