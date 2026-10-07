import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from app import create_app
from app.db import get_db, init_db
from test_workflows import make_class, student_headers, complete


def test_expired_links_fail_and_current_rotates_them(app, client, post):
    detail = make_class(client, post, 1)
    cid, sid = detail['classInfo']['id'], detail['students'][0]['id']
    headers = student_headers(post,cid,sid)
    with app.app_context(), get_db() as db:
        db.execute("UPDATE enrollments SET token_expires_at=? WHERE student_id=?", ((datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),sid))
    assert client.get('/api/student',headers=headers).status_code == 401
    new = student_headers(post,cid,sid)
    assert new['X-Student-Token'] != headers['X-Student-Token']
    assert client.get('/api/student',headers=new).status_code == 200


def test_current_link_does_not_extend_expiry(app, client, post):
    detail = make_class(client,post,1)
    path = f"/classes/{detail['classInfo']['id']}/students/{detail['students'][0]['id']}/link"
    first = post(path).json
    second = post(path).json
    assert first == second


def test_logout_revokes_copied_cookie(app, client, post):
    cookie = client.get_cookie('session').value
    assert post('/logout').status_code == 200
    other = app.test_client()
    other.set_cookie('session',cookie)
    assert other.get('/api/classes').status_code == 401
    assert other.get('/api/session').json['user'] is None


def test_reactivation_does_not_revive_old_session(app, client, post):
    user = next(u for u in client.get('/api/users').json if u['role']=='TEACHER')
    other = app.test_client()
    with other.session_transaction() as session:
        session.update(user_id=user['id'],auth_version=1,csrf='test')
    assert post('/users/'+user['id'],method='DELETE').status_code == 200
    assert post('/users/'+user['id'],dict(name=user['name'],email=user['email'],role=user['role'],active=True),method='PATCH').status_code == 200
    assert other.get('/api/classes').status_code == 401


def populate(app, client, post):
    detail = make_class(client,post,2)
    cid = detail['classInfo']['id']; a,b = detail['students']
    complete(client,post,cid,a['id'])
    post(f"/classes/{cid}/students/{a['id']}/observation", {'free_text':'Nota sintética'})
    post(f"/classes/{cid}/relations",{'student_a':a['id'],'student_b':b['id'],'type':'MEJOR_SEPARADOS','comment':'Prueba'})
    with app.app_context(), get_db() as db:
        actor = db.execute("SELECT id FROM users WHERE role='ADMIN'").fetchone()[0]
        stamp=datetime.now(timezone.utc).isoformat()
        snapshot=json.dumps({'students':[a['id'],b['id']]})
        db.execute("INSERT INTO proposals(id,class_id,kind,data,source_model,created_by,created_at) VALUES(?,?,?,?,?,?,?)",('test-proposal',cid,'TEST',snapshot,snapshot,actor,stamp))
        db.execute("INSERT INTO manual_changes(proposal_id,before_data,created_at) VALUES(?,?,?)",('test-proposal',snapshot,stamp))
        db.execute("INSERT INTO invitation_deliveries VALUES(?,?,?,?,?,?,?,?,?)",('test-delivery',a['enrollment_id'],'test','a0@example.com','SENT','',stamp,stamp,actor))
    return detail


def test_retention_requires_config_closed_old_classes_and_selection(app,client,post):
    detail=make_class(client,post)
    cid=detail['classInfo']['id'];runner=app.test_cli_runner()
    assert runner.invoke(args=['purge-expired']).exit_code != 0
    app.config['RETENTION_DAYS']='30'
    assert runner.invoke(args=['purge-expired','--execute']).exit_code != 0
    args=['purge-expired','--class-id',cid,'--execute']
    assert runner.invoke(args=args).exit_code != 0
    post('/classes/'+cid,{'confirmation':detail['classInfo']['name']},method='DELETE')
    assert runner.invoke(args=args).exit_code != 0


def test_class_erasure_covers_snapshots_history_notes_and_invitations(app,client,post):
    detail=populate(app,client,post);cid=detail['classInfo']['id']
    post('/classes/'+cid,{'confirmation':detail['classInfo']['name']},method='DELETE')
    with app.app_context(),get_db() as db:
        db.execute("UPDATE classes SET privacy_updated_at=? WHERE id=?",((datetime.now(timezone.utc)-timedelta(days=60)).isoformat(),cid))
    app.config['RETENTION_DAYS']='30';runner=app.test_cli_runner()
    args=['purge-expired','--class-id',cid]
    assert runner.invoke(args=args).exit_code == 0
    with app.app_context(): assert get_db().execute('SELECT COUNT(*) FROM submissions').fetchone()[0] == 1
    result=runner.invoke(args=args+['--execute'])
    assert result.exit_code == 0,result.output
    with app.app_context():
        for table in ('classes','class_teachers','students','enrollments','submissions','observations','relations','proposals','manual_changes','invitation_deliveries','audit_log'):
            assert get_db().execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0,table
        assert get_db().execute('PRAGMA foreign_key_check').fetchall() == []
        assert get_db().execute('SELECT COUNT(*) FROM users').fetchone()[0] == 2


def test_individual_erasure_removes_proposals_and_preserves_other_student(app,client,post):
    detail=populate(app,client,post);sid=detail['students'][0]['id']
    args=['erase-student','--student-id',sid];runner=app.test_cli_runner()
    assert runner.invoke(args=args).exit_code == 0
    with app.app_context(): assert get_db().execute('SELECT COUNT(*) FROM students').fetchone()[0] == 2
    result=runner.invoke(args=args+['--execute'])
    assert result.exit_code == 0,result.output
    with app.app_context():
        for table in ('submissions','observations','relations','proposals','manual_changes','invitation_deliveries'):
            assert get_db().execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0,table
        assert get_db().execute('SELECT COUNT(*) FROM students').fetchone()[0] == 1
        assert get_db().execute('SELECT COUNT(*) FROM classes').fetchone()[0] == 1


def test_migration_preserves_old_accounts_and_revokes_undated_links(tmp_path):
    app=create_app({'TESTING':True,'SECRET_KEY':'s'*48,'DATABASE_PATH':str(tmp_path/'old.sqlite3')})
    with app.app_context():
        db=get_db()
        db.executescript((Path(__file__).parents[1]/'app/schema.sql').read_text(encoding='utf-8'))
        db.execute("INSERT INTO users VALUES('u','a@cuatrovientos.org','A','ADMIN',1,'2020-01-01')")
        db.execute("INSERT INTO classes VALUES('c','C','2020','INICIAL','CODE',0,'u','2020-01-01')")
        db.execute("INSERT INTO students VALUES('s','S','','')")
        db.execute("INSERT INTO enrollments VALUES('e','c','s',1,'old-hash',1)")
        db.commit();init_db();init_db()
        assert db.execute("SELECT name,auth_version FROM users WHERE id='u'").fetchone()[:] == ('A',1)
        assert db.execute("SELECT token_hash FROM enrollments WHERE id='e'").fetchone()[0] is None
        assert db.execute("SELECT privacy_updated_at FROM classes WHERE id='c'").fetchone()[0]


def test_privacy_notice_escapes_configuration(app,client):
    app.config['PRIVACY_CONTROLLER']='<script>bad()</script>'
    response=client.get('/privacidad')
    assert response.status_code==200 and b'&lt;script&gt;' in response.data
    assert response.headers['Cache-Control']=='no-store'


def test_shared_student_survives_class_erasure(app,client,post):
    detail=make_class(client,post,1);cid=detail['classInfo']['id'];sid=detail['students'][0]['id']
    other=make_class(client,post,1)['classInfo']['id']
    post('/classes/'+cid,{'confirmation':detail['classInfo']['name']},method='DELETE')
    with app.app_context(),get_db() as db:
        db.execute("UPDATE classes SET privacy_updated_at=? WHERE id=?",((datetime.now(timezone.utc)-timedelta(days=60)).isoformat(),cid))
    app.config['RETENTION_DAYS']='30'
    result=app.test_cli_runner().invoke(args=['purge-expired','--class-id',cid,'--execute'])
    assert result.exit_code==0,result.output
    with app.app_context():
        assert get_db().execute('SELECT id FROM students WHERE id=?',(sid,)).fetchone()
        assert get_db().execute('SELECT 1 FROM enrollments WHERE class_id=? AND student_id=?',(other,sid)).fetchone()


def test_audit_policy_is_independent_and_preview_does_not_delete(app,client,post):
    make_class(client,post)
    runner=app.test_cli_runner()
    assert runner.invoke(args=['purge-audit']).exit_code!=0
    app.config['AUDIT_RETENTION_DAYS']='30'
    with app.app_context(),get_db() as db:
        db.execute("UPDATE audit_log SET created_at=?",((datetime.now(timezone.utc)-timedelta(days=60)).isoformat(),))
    assert runner.invoke(args=['purge-audit']).exit_code==0
    with app.app_context(): assert get_db().execute('SELECT COUNT(*) FROM audit_log').fetchone()[0]>0
    assert runner.invoke(args=['purge-audit','--execute']).exit_code==0
    with app.app_context(): assert get_db().execute('SELECT COUNT(*) FROM audit_log').fetchone()[0]==0


def test_invalid_link_attempts_are_counted_without_storing_tokens(app,client):
    for _ in range(100):
        assert client.get('/api/student',headers={'X-Class-Code':'invalid','X-Student-Token':'private-token'}).status_code==401
    assert app.test_client().get('/api/student').status_code==429
    with app.app_context():
        row=get_db().execute('SELECT * FROM link_failures').fetchone()
        assert len(row['key'])==64 and row['attempts']==101
