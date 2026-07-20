import requests, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = 'http://127.0.0.1:8000/api/v1/diagnosis'

# Pick an existing active session and add more context to trigger finish
# Let's use a session that already has a lot of profile info
r = requests.post(f'{BASE}/start', json={'user_id': '1'})
d = r.json()
sid = d['data']['session_id']
print(f'NEW Session: {sid[:8]}...')
print()

# Send very comprehensive answers in one go to trigger finish
msgs = [
    '交通工程，大二男生',
    '考研，目标东南大学交通大数据方向',
    '因为我想进好的设计院或者做智慧交通，本科竞争力不够，而且我性格偏稳健求稳',
    '学习能力中等偏上，专业排名前30%，Python自学一年，执行力较高，能坚持每天学习3小时',
    '风险偏好低，做事比较谨慎，喜欢先规划再执行',
    '我性格偏内向但做事踏实认真，遇到问题喜欢自己先查资料解决',
    '我觉得我的优势是执行力强能坚持，劣势是太谨慎不够大胆',
    '未来想做交通数据分析的技术岗，希望工作稳定有成长空间，如果考研失利会考虑先就业再二战',
]

for i, msg in enumerate(msgs):
    r = requests.post(f'{BASE}/chat', json={'session_id': sid, 'message': msg})
    d = r.json()
    reply = d['data']['reply']
    finish = d['data']['finish']
    profile = d['data'].get('profile')
    
    print(f'Round {i+1} | finish={finish}')
    print(f'  User: {msg}')
    print(f'  AI: {reply}')
    if profile:
        print(f'  Profile: {json.dumps(profile, ensure_ascii=False)}')
    print()
    
    if finish:
        print('='*60)
        print('FINAL PROFILE:')
        print(json.dumps(d['data']['profile'], ensure_ascii=False, indent=2))
        break
