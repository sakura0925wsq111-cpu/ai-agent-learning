import requests, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = 'http://127.0.0.1:8000/api/v1/diagnosis'

r = requests.post(f'{BASE}/start', json={'user_id': '1'})
d = r.json()
sid = d['data']['session_id']
first_q = d['data']['first_question']
results = []
results.append(f'🤖 AI: {first_q}')
results.append('')

# 每轮都提供充分信息，加速AI完成诊断
msgs = [
    '交通工程，大二，男生，性格比较内向稳重',
    '考研，因为我想进好的设计院或者转行做交通数据分析，本科学历竞争力不够',
    '自学Python一年多了，做过数据分析和可视化的小项目，执行力还不错，能坚持每天学习',
    '学习能力中等偏上，专业排名前30%，但我觉得自己还有提升空间',
    '我喜欢先做详细规划再执行，不喜欢冒险，做事比较踏实',
    '跨考计算机或者交通大数据方向，目标院校是东南大学或同济',
    '每天能保证3小时学习，周末5-6小时，偶尔也会因为学校课程压力打断计划，但能很快调整回来',
    '遇到问题喜欢先自己Google查资料解决，实在不行再问学长',
    '我觉得自己最大的优势是能坚持，缺点是有时候太谨慎不够大胆',
    '未来想做智慧交通或者数据分析相关的技术岗，希望工作稳定有成长空间',
]

for i, msg in enumerate(msgs):
    r = requests.post(f'{BASE}/chat', json={'session_id': sid, 'message': msg})
    d = r.json()
    reply = d['data']['reply']
    finish = d['data']['finish']
    results.append(f'👤 用户: {msg}')
    results.append(f'🤖 AI: {reply}')
    profile = d['data'].get('profile')
    if profile:
        results.append(f'📊 画像: {json.dumps(profile, ensure_ascii=False)}')
    results.append('')
    if finish:
        results.append('='*60)
        results.append('🏁 诊断完成！最终用户画像：')
        results.append(json.dumps(d['data']['profile'], ensure_ascii=False, indent=2))
        break

if not finish:
    results.append(f'⚠️ {len(msgs)}轮后仍在追问（AI很认真在了解你）')

with open('D:/ai-agent-learning/demo_final.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print('Done!')
