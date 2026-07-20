import requests, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = 'http://127.0.0.1:8000/api/v1/diagnosis'

# Try one more time with max info upfront - trigger force-finish after 12 rounds
r = requests.post(f'{BASE}/start', json={'user_id': '1'})
d = r.json()
sid = d['data']['session_id']
first_q = d['data']['first_question']
print(f'Session: {sid[:8]}...')
print(f'Round 0: {first_q}')
print()

msgs = [
    '交通工程大二，男生，性格稳健偏内向，做事踏实',
    '考研跨考计算机或交通大数据，目标东南大学/同济，因为想进好设计院，本科竞争力不够',
    '自学Python一年多，做过数据分析项目，学习能力中等偏上，执行力比较高，能每天坚持学习',
    '风险偏好低，喜欢先规划再执行，不喜欢冒险',
    '未来想做智慧交通技术岗，希望稳定有成长空间，考研失利的话会先就业再二战',
    '我觉得自己最大的优势是自律能坚持，缺点是太谨慎有时候不够果断',
    '是的，我已经充分了解自己了，以上信息就是我的完整画像，请帮我生成诊断报告',
]

for i, msg in enumerate(msgs):
    r = requests.post(f'{BASE}/chat', json={'session_id': sid, 'message': msg})
    d = r.json()
    reply = d['data']['reply']
    finish = d['data']['finish']
    profile = d['data'].get('profile')
    print(f'Round {i+1} | finish={finish} | reply={reply[:80]}...')
    if profile:
        print(f'  Profile: {json.dumps(profile, ensure_ascii=False)}')
    print()
    if finish:
        print('='*60)
        print('FINAL PROFILE:')
        print(json.dumps(profile, ensure_ascii=False, indent=2) if profile else 'N/A')
        break
