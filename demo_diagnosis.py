import requests, json

BASE = 'http://127.0.0.1:8000/api/v1/diagnosis'

r = requests.post(f'{BASE}/start', json={'user_id': '1'})
d = r.json()
sid = d['data']['session_id']
first_q = d['data']['first_question']
print('='*60)
print('【第1轮 - 启动诊断】')
print(f'Session ID: {sid}')
print(f'AI: {first_q}')
print()

msgs = [
    '我学交通工程，现在大二',
    '考研',
    '因为本科竞争力不够，好工作难找',
    '主要是我们专业本科毕业都去了施工单位，我不想下工地',
    '编程和数据分析吧，我对技术比较感兴趣，也自学过一些Python',
    '算是吧，我喜欢按计划来，先把事情想清楚再动手',
]

for i, msg in enumerate(msgs):
    r = requests.post(f'{BASE}/chat', json={'session_id': sid, 'message': msg})
    d = r.json()
    reply = d['data']['reply']
    finish = d['data']['finish']
    print(f'【第{i+2}轮】')
    print(f'用户: {msg}')
    print(f'AI: {reply}')
    profile = d['data'].get('profile')
    if profile:
        print(f'当前画像: {json.dumps(profile, ensure_ascii=False)}')
    print()
    if finish:
        print('='*60)
        print('最终画像:')
        print(json.dumps(d['data']['profile'], ensure_ascii=False, indent=2))
        break
