"""Live file-to-choice-question API regression using an isolated SQLite database."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pipeline', default='knowledge-v1', choices=['knowledge-v1', 'doubao-vision-v2'])
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['DATABASE_URL'] = 'sqlite:///' + (out / 'test.sqlite').as_posix()
    os.environ['STUDY_UPLOAD_DIR'] = str(out / 'uploads')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from fastapi.testclient import TestClient
    from app.main import app
    from core.config import settings
    from database.base import Base
    from database.session import engine, SessionLocal
    from models.user import User
    from utils.auth import create_token, hash_password
    from models.study import StudyKnowledgeRun, StudyChoiceQuestionRun
    Base.metadata.create_all(engine)
    client = TestClient(app)
    report = {'source': str(args.source.resolve()), 'sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
              'pipeline': args.pipeline, 'model': settings.study_doubao_model if args.pipeline == 'doubao-vision-v2' else settings.llm_model,
              'stages': [], 'transport': 'FastAPI TestClient with real model calls'}
    started = time.monotonic()
    def save():
        report['elapsed_seconds'] = round(time.monotonic() - started, 2)
        (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    def call(method, path, headers, **kwargs):
        t = time.monotonic()
        print(json.dumps({'event': 'start', 'method': method, 'path': path}), flush=True)
        response = client.request(method, '/api/v1/study' + path, headers=headers, **kwargs)
        item = {'method': method, 'path': path, 'status': response.status_code, 'seconds': round(time.monotonic()-t, 2)}
        report['stages'].append(item)
        save()
        print(json.dumps(item), flush=True)
        if response.status_code >= 400:
            raise RuntimeError('HTTP '+str(response.status_code))
        return response.json()['data']
    with SessionLocal() as db:
        owner = User(student_id='live-'+uuid.uuid4().hex[:8], name='Live test', nickname='Live test', password_hash=hash_password(uuid.uuid4().hex))
        other = User(student_id='other-'+uuid.uuid4().hex[:8], name='Other', nickname='Other', password_hash=hash_password(uuid.uuid4().hex))
        db.add_all([owner, other]); db.commit()
        headers={'Authorization':'Bearer '+create_token(owner.id)}
        other_headers={'Authorization':'Bearer '+create_token(other.id)}
    try:
        with args.source.open('rb') as f:
            document=call('POST','/documents',headers,files={'file':(args.source.name,f,'application/pdf')})
        report['document_id']=document['id']
        report['parse']=call('POST','/documents/'+document['id']+'/parse',headers)
        extraction=call('POST','/documents/'+document['id']+'/knowledge-runs',headers,json={'pipeline_version':args.pipeline})
        kid=extraction['run']['id']
        report['knowledge_run']=call('GET','/knowledge-runs/'+kid,headers)
        if report['knowledge_run']['status']!='completed':
            raise RuntimeError('knowledge_run_failed:'+str(report['knowledge_run']['error_code']))
        units=[]
        page=1
        while True:
            data=call('GET',f'/knowledge-runs/{kid}/knowledge-units?disposition=usable&page_size=100&page={page}',headers)
            units.extend(data['units'])
            if len(units)>=data['total']: break
            page+=1
        report['usable_count']=len(units)
        (out/'knowledge-units.json').write_text(json.dumps(units,ensure_ascii=False,indent=2),encoding='utf-8')
        if not units: raise RuntimeError('no_usable_knowledge')
        choice_path='/knowledge-runs/'+kid+'/choice-question-runs'
        choice=call('POST',choice_path,headers)
        qid=choice['question_run_id']
        base='/choice-question-runs/'+qid
        report['choice_run']=call('GET',base,headers)
        questions=[]
        page=1
        while True:
            data=call('GET',base+f'/questions?page_size=100&page={page}',headers)
            questions.extend(data['questions'])
            if len(questions)>=data['total']: break
            page+=1
        (out/'questions.json').write_text(json.dumps(questions,ensure_ascii=False,indent=2),encoding='utf-8')
        checks=[]
        for q in questions:
            assert q['source_content'][q['answer_start']:q['answer_end']]==q['answer_text']
            assert len(q['options'])==len(set(q['options']))==4
            assert q['options']['ABCD'.index(q['correct_option'])]==q['answer_text']
            assert q['source_content'] in q['explanation']
            assert q['prompt'].endswith(q['source_content'][:q['answer_start']]+'____'+q['source_content'][q['answer_end']:])
        checks.append({'name':'source_span_options_explanation','passed':True,'questions':len(questions)})
        repeated=call('POST',choice_path,headers)
        assert repeated['reused'] and repeated['question_run_id']==qid
        checks.append({'name':'unchanged_reuse','passed':True})
        urls=[base,base+'/questions']
        if questions:
            single=base+'/questions/'+questions[0]['id']
            call('GET',single,headers)
            urls.append(single)
        for url in urls:
            assert client.get('/api/v1/study'+url,headers=other_headers).status_code==404
        assert client.post('/api/v1/study'+choice_path,headers=other_headers).status_code==404
        checks.append({'name':'owner_isolation','passed':True})
        report['checks']=checks
        with SessionLocal() as db:
            run=db.get(StudyChoiceQuestionRun,qid)
            report['generation_audit']=run.audit
            report['extraction_audit']=db.get(StudyKnowledgeRun,kid).audit
        report['result']='PASS' if questions and report['choice_run']['status']=='completed' else 'PARTIAL_OR_NO_QUESTIONS'
        save()
    except Exception as exc:
        report['result']='FAILED'
        report['error']=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
        save()
    print(json.dumps({'result':report['result'],'report':str(out/'report.json'),'elapsed_seconds':report['elapsed_seconds']},ensure_ascii=False),flush=True)


if __name__=='__main__': main()
