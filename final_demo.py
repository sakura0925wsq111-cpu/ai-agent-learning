import requests, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = 'http://127.0.0.1:8000/api/v1/diagnosis'

r = requests.post(f'{BASE}/start', json={'user_id': '1'})
d = r.json()
sid = d['data']['session_id']
first_q = d['data']['first_question']

print('='*60)
print('🎓 CampusPal 成长诊断 - 完整端到端演示')
print('='*60)
print()
print(f'【启动】POST /api/v1/diagnosis/start')
print(f'  Session ID: {sid}')
print(f'  AI: {first_q}')
print()

msgs = [
    '交通工程大二，男生，性格稳健偏内向',
    '考研跨考计算机/交通大数据，目标东南/同济，本科竞争力不够不想下工地',
    '自学Python一年多做过项目，执行力较高每天坚持学习，学习能力中上，专业前30%',
    '风险偏好低，喜欢规划再执行，做事踏实',
    '未来想做智慧交通技术岗，稳定有成长空间，失利会先就业再二战',
    '优势是自律能坚持，劣势是太谨慎不够果断，我觉得信息已经够全面了',
]

for i, msg in enumerate(msgs):
    r = requests.post(f'{BASE}/chat', json={'session_id': sid, 'message': msg})
    d = r.json()
    reply = d['data']['reply']
    finish = d['data']['finish']
    profile = d['data'].get('profile')
    
    lines = reply.split('\n')
    short_reply = lines[0] if lines else reply
    print(f'【第{i+1}轮】POST /api/v1/diagnosis/chat')
    print(f'  👤 用户: {msg}')
    if finish:
        print(f'  🏁 finish=true!')
        print(f'  🤖 AI 回复:')
        for line in lines:
            print(f'     {line}')
        print()
        print(f'  📊 最终画像:')
        for k, v in profile.items():
            print(f'     {k}: {v}')
    else:
        print(f'  🤖 AI: {short_reply}')
    print()

print('='*60)
print('✅ 诊断流程完整演示完成！')
print('='*60)
