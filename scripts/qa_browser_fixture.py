"""Ephemeral synthetic server for browser QA. Never deploy or use with real data."""
import json
import secrets
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app import create_app
from app.db import init_db,get_db
from app.auth import register_user
from app.scoring import ITEMS

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='equipos-qa-') as directory:
        app=create_app(dict(TESTING=True,SECRET_KEY=secrets.token_urlsafe(48),DATABASE_PATH=str(Path(directory)/'qa.sqlite3'),
                            SESSION_COOKIE_SECURE=False,PUBLIC_BASE_URL='http://127.0.0.1:5055',GOOGLE_CLIENT_ID='',GOOGLE_CLIENT_SECRET=''))
        with app.app_context():
            init_db()
            register_user('qa@cuatrovientos.org','Docente de prueba','ADMIN')
            user_id=get_db().execute('SELECT id FROM users').fetchone()['id']
        client=app.test_client()
        csrf=secrets.token_urlsafe(24)
        with client.session_transaction() as session:
            session.update(user_id=user_id,csrf=csrf)
        def post(path,data,headers=None):
            r=client.post('/api'+path,json=data,headers={'X-CSRF-Token':csrf,**(headers or {})})
            assert r.status_code<300,r.json
            return r.json
        cid=post('/classes',dict(name='1.º Desarrollo web',academic_year='2026-2027'))['id']
        names=['María García','Álvaro Muñoz','Lucía Fernández','José Martín','Iñaki Pérez','Nerea Jiménez','Sofía Alonso']
        post('/classes/'+cid+'/students',{'students':[{'name':n,'email':f'qa{i}@example.com'} for i,n in enumerate(names)]})
        students=client.get('/api/classes/'+cid).json['students']
        from urllib.parse import parse_qs,urlparse
        student_url=''
        for i,s in enumerate(students):
            link=post(f'/classes/{cid}/students/{s["id"]}/link',{})['url']
            if i==len(students)-1:
                student_url=link
                continue
            q=parse_qs(urlparse(link).fragment)
            headers={'X-Class-Code':q['code'][0],'X-Student-Token':q['token'][0]}
            sub=post('/student/start',{'confirmed':True},headers)
            post('/student/submit',{'id':sub['id'],'answers':{str(row[1]):(i+row[1])%4 for row in ITEMS}},headers)
        (ROOT/'tmp').mkdir(exist_ok=True)
        (ROOT/'tmp/browser-fixture.json').write_text(json.dumps(dict(cookie=client.get_cookie('session').value,student_url=student_url)),encoding='utf-8')
        app.run(host='127.0.0.1',port=5055,debug=False,use_reloader=False)
