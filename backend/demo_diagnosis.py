import json, urllib.request, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = 'http://127.0.0.1:8000/api/v1'

def post(path, data):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(data, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json; charset=utf-8'},
        method='POST'
    )
    resp = urllib.request.urlopen(req, timeout=120)
    return json.loads(resp.read().decode('utf-8'))

sep = '=' * 60

# Step 1: Create user
print(sep)
print('STEP 1: 创建测试用户')
print(sep)
user = post('/users', {'nickname': 'XiaoMing', 'major': '', 'grade': ''})
uid = user['data']['id']
print(f'用户ID: {uid}\n')

# Step 2: Start diagnosis
print(sep)
print('STEP 2: POST /api/v1/diagnosis/start')
print(sep)
start = post('/diagnosis/start', {'user_id': uid})
sid = start['data']['session_id']
print(f'会话ID: {sid}')
print(f'\nAI 说: {start["data"]["first_question"]}\n')

# Step 3: Turn 1
print(sep)
print('STEP 3: 第1轮对话')
print(sep)
msg = '你好，我在读交通工程，今年大二了'
print(f'用户: {msg}')
r = post('/diagnosis/chat', {'session_id': sid, 'message': msg})
print(f'\nAI 说: {r["data"]["reply"]}')
print(f'finish: {r["data"]["finish"]}\n')

# Step 4: Turn 2
print(sep)
print('STEP 4: 第2轮对话')
print(sep)
msg = '我想考研，因为感觉本科毕业竞争力不太够'
print(f'用户: {msg}')
r = post('/diagnosis/chat', {'session_id': sid, 'message': msg})
print(f'\nAI 说: {r["data"]["reply"]}')
print(f'finish: {r["data"]["finish"]}\n')

# Step 5: Turn 3
print(sep)
print('STEP 5: 第3轮对话')
print(sep)
msg = '我觉得自己学东西不算特别快，但能坚持，执行力还行吧'
print(f'用户: {msg}')
r = post('/diagnosis/chat', {'session_id': sid, 'message': msg})
print(f'\nAI 说: {r["data"]["reply"]}')
print(f'finish: {r["data"]["finish"]}\n')

# Step 6: Turn 4
print(sep)
print('STEP 6: 第4轮对话')
print(sep)
msg = '我性格比较稳健，不喜欢冒险的事情'
print(f'用户: {msg}')
r = post('/diagnosis/chat', {'session_id': sid, 'message': msg})
print(f'\nAI 说: {r["data"]["reply"]}')
print(f'finish: {r["data"]["finish"]}')
if r['data']['profile']:
    print(f'\n最终画像:\n{json.dumps(r["data"]["profile"], indent=2, ensure_ascii=False)}')

print(f'\n{sep}')
print('演示完成!')
print(sep)
