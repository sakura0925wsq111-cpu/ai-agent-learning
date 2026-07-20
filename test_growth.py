import requests, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = 'http://127.0.0.1:8000/api/v1/growth'

r = requests.post(f'{BASE}/start', json={'user_id': '1', 'agent_type': 'career'})
d = r.json()
sid = d['data']['session_id']
q = d['data']['question']
q_title = q['title']
q_options = q['options']
q_index = q['index']
q_total = q['total']
print('=== START ===')
print('Session:', sid[:8], '...')
print('Q{}/{}: {}'.format(q_index, q_total, q_title))
print('Options:', q_options)
print()

answers = [
    ('career_goal', '考研'),
    ('career_value', '成长'),
    ('career_style', '数据分析'),
    ('career_strength', '逻辑分析'),
    ('career_city', '新一线'),
]

for qid, ans in answers:
    r = requests.post(f'{BASE}/answer', json={
        'session_id': sid,
        'question_id': qid,
        'selected_option': ans,
    })
    d = r.json()
    data = d['data']
    if data['finished']:
        print('=== FINISHED! ===')
        report = data['report']
        p = report['profile']
        print('Personality:', p['personality'])
        print('Learning:', p['learning_style'])
        print('Direction:', p['career_direction'])
        print('Strengths:', p['strengths'])
        print('Weaknesses:', p['weaknesses'])
        print('Risk:', p['risk_tolerance'])
        print()
        print('Strengths Analysis:', report['strengths_analysis'][:150])
        print('Risk Analysis:', report['risk_analysis']['description'][:150])
        print('Risk Level:', report['risk_analysis']['level'])
        print()
        print('Career Directions:')
        for cd in report['career_directions']:
            stars = '\u2605' * cd['score'] + '\u2606' * (5 - cd['score'])
            print('  {} {} - {}'.format(cd['name'], stars, cd['reason']))
        print()
        print('30-Day Plan:')
        for item in report['thirty_day_plan']:
            print('  {}: {}'.format(item['day_range'], item['task']))
            print('    Goal:', item['goal'])
    else:
        nq = data['next_question']
        n_title = nq['title']
        n_options = nq['options']
        ni = nq['index']
        nt = nq['total']
        print('Q{}/{}: {}'.format(ni, nt, n_title))
        print('Options:', n_options)
        progress_pct = int(data['progress'] * 100)
        print('Progress:', progress_pct, '%')
    print()

print('=== DONE ===')
