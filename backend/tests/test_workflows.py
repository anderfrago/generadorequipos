import json
from urllib.parse import urlparse, parse_qs
from app.db import get_db
from app.scoring import calculate, pattern, ITEMS
from app.grouping_engine import prepare_model, generate, evaluate, size_options


def make_class(client, post, count=0):
    result = post('/classes', dict(name="1.º Desarrollo web", academic_year="2026-2027"))
    assert result.status_code == 201
    class_id = result.json['id']
    if count:
        response = post('/classes/' + class_id + '/students', dict(students=[dict(name=f"Alumno {i}", email=f"a{i}@example.com") for i in range(count)]))
        assert response.status_code == 200
    return client.get('/api/classes/' + class_id).json


def student_headers(post, class_id, student_id):
    response = post(f'/classes/{class_id}/students/{student_id}/link')
    query = parse_qs(urlparse(response.json['url']).fragment)
    return {'X-Class-Code': query['code'][0], 'X-Student-Token': query['token'][0]}


def complete(client, post, class_id, student_id):
    headers = student_headers(post, class_id, student_id)
    sub = post('/student/start', {'confirmed': True}, headers=headers).json
    result = post('/student/submit', dict(id=sub['id'], answers={str(i[1]): 2 for i in ITEMS}, conditions=['CALM']), headers=headers)
    assert result.status_code == 200, result.json
    return headers, result.json


def test_csrf_and_anonymous_access(app, client):
    anonymous = app.test_client()
    assert anonymous.get('/api/classes').status_code == 401
    assert client.post('/api/classes', json={'name': 'Attack'}).status_code == 403
    assert anonymous.get('/api/session').json['user'] is None


def test_class_authorization(app, client, post):
    detail = make_class(client, post)
    with app.app_context():
        teacher_id = get_db().execute("SELECT id FROM users WHERE role='TEACHER'").fetchone()['id']
    with client.session_transaction() as session:
        session['user_id'] = teacher_id
    assert client.get('/api/classes').json == []
    assert client.get('/api/classes/' + detail['classInfo']['id']).status_code == 403
    assert client.get('/api/users').status_code == 403


def test_student_token_rotation_revocation_and_ownership(client, post):
    detail = make_class(client, post, 2)
    class_id = detail['classInfo']['id']
    a, b = detail['students']
    ha = student_headers(post, class_id, a['id'])
    hb = student_headers(post, class_id, b['id'])
    assert client.get('/api/student', headers=ha).status_code == 200
    sub = post('/student/start', {'confirmed': True}, headers=ha).json
    other = post('/student/start', {'confirmed': True}, headers=hb).json
    assert post('/student/save', {'id': sub['id'], 'answers': {}}, headers=hb).status_code == 409
    post(f'/classes/{class_id}/students/{a["id"]}/link', {'action': 'rotate'})
    assert client.get('/api/student', headers=ha).status_code == 401
    ha = student_headers(post, class_id, a['id'])
    post(f'/classes/{class_id}/students/{a["id"]}/link', {'action': 'revoke'})
    assert client.get('/api/student', headers=ha).status_code == 401
    assert client.get('/api/student', headers=hb).status_code == 200


def test_draft_validation_atomic_submit_and_reopen(client, post):
    detail = make_class(client, post, 1)
    class_id, student = detail['classInfo']['id'], detail['students'][0]
    headers = student_headers(post, class_id, student['id'])
    assert post('/student/start', {}, headers=headers).status_code == 400
    sub = post('/student/start', {'confirmed': True}, headers=headers).json
    assert post('/student/save', {'id':sub['id'], 'answers':{'1':True}}, headers=headers).status_code == 400
    assert post('/student/save', {'id':sub['id'], 'conditions':['NONE','CALM']}, headers=headers).status_code == 400
    assert post('/student/submit', {'id':sub['id'], 'answers':{'1':1}}, headers=headers).status_code == 400
    assert client.get('/api/student', headers=headers).json['submission']['status'] == 'DRAFT'
    payload = {'id':sub['id'], 'answers':{str(i[1]):2 for i in ITEMS}}
    assert post('/student/submit', payload, headers=headers).status_code == 200
    assert post('/student/save', payload, headers=headers).status_code == 409
    assert post(f'/classes/{class_id}/students/{student["id"]}/reopen').status_code == 200
    reopened = client.get('/api/student', headers=headers).json['submission']
    assert reopened['status'] == 'DRAFT' and reopened['id'] != sub['id']
    assert reopened['answers'] == payload['answers']


def test_foreign_students_cannot_enter_relations(client, post):
    a = make_class(client, post, 1)
    # Use a different email so the second class creates a distinct person.
    b = make_class(client, post)
    post('/classes/'+b['classInfo']['id']+'/students', {'students':[{'name':'Otra persona','email':'other@example.com'}]})
    b = client.get('/api/classes/'+b['classInfo']['id']).json
    response = post('/classes/'+a['classInfo']['id']+'/relations', dict(student_a=a['students'][0]['id'],student_b=b['students'][0]['id'],type='NO_JUNTAR'))
    assert response.status_code == 404


def test_grouping_full_flow_and_immutable_validation(client, post, monkeypatch):
    import app.grouping as grouping
    original = grouping.generate
    monkeypatch.setattr(grouping, 'generate', lambda *a, **kw: original(*a, **kw, seconds=.10))
    detail = make_class(client, post, 6)
    class_id = detail['classInfo']['id']
    for student in detail['students']:
        complete(client, post, class_id, student['id'])
    a,b = [s['id'] for s in detail['students'][:2]]
    assert post(f'/classes/{class_id}/relations',dict(student_a=a,student_b=b,type='NO_JUNTAR')).status_code == 200
    result = post(f'/classes/{class_id}/proposals', {'sizes':[3,3]})
    assert result.status_code == 200, result.json
    proposal = result.json
    assert all(not(a in t and b in t) for t in proposal['teams'])
    path = '/proposals/'+proposal['id']+'/change'
    locked = post(path,dict(action='lock',index=0,locked=True,version=proposal['version'])).json
    assert post(path,dict(action='validate',version=proposal['version'])).status_code == 409
    assert post(path,dict(action='swap',a=locked['teams'][0][0],b=locked['teams'][1][0],version=locked['version'])).status_code == 409
    validated = post(path,dict(action='validate',version=locked['version'])).json
    assert validated['status'] == 'VALIDATED'
    assert post(path,dict(action='undo',version=validated['version'])).status_code == 409
    assert client.get('/api/proposals/'+proposal['id']+'/report/student').data.startswith(b'%PDF')
    assert client.get('/api/proposals/'+proposal['id']+'/export/csv').status_code == 200


def test_single_team_and_impossible_constraints():
    result = calculate({str(i[1]):2 for i in ITEMS})
    students = [dict(id=str(i),profiles=result['profiles'],functional=result['functional'],conditions=[]) for i in range(3)]
    model = prepare_model(students,[],list(result['functional']))
    assert len(generate(model,[3])['teams']) == 1
    model['relations'] = [dict(a='0',b='1',type='NO_JUNTAR')]
    import pytest
    with pytest.raises(ValueError):
        generate(model,[3])
    assert size_options(8)[0]['sizes'] == [4,4]


def test_profile_patterns_reverse_scoring_and_mixed_evidence():
    assert pattern(dict.fromkeys(('IMP','ORG','EXP','INT'),0))['kind'] == 'NONE'
    assert pattern(dict(IMP=12,ORG=11,EXP=11,INT=2))['kind'] == 'NEAR_3'
    assert pattern(dict(IMP=9,ORG=9,EXP=2,INT=1))['kind'] == 'COMBINED_2'
    answers = {str(i[1]):3 for i in ITEMS}
    result = calculate(answers)
    assert all(v==1 for v in result['profiles'].values())
    assert result['functional']['AUT'] == .5
    assert result['details']['AUT']['mixed'] is True
    assert result['functional']['COMM'] == 1


def test_exports_pdf_and_formula_escaping(client, post):
    detail = make_class(client, post, 1)
    class_id = detail['classInfo']['id']
    sid = detail['students'][0]['id']
    complete(client,post,class_id,sid)
    report = client.get(f'/api/classes/{class_id}/students/{sid}/report')
    assert report.status_code == 200 and report.data.startswith(b'%PDF')
    assert 'attachment' in report.headers['Content-Disposition']
    exported = client.get(f'/api/classes/{class_id}/export/json')
    assert 'token_hash' not in exported.get_data(as_text=True)
    from app.reports import csv_response
    with client.application.app_context():
        assert "'=HYPERLINK" in csv_response([['=HYPERLINK("bad")']], 'test.csv').get_data(as_text=True)


def test_deleted_class_revokes_access(client, post):
    detail = make_class(client,post,1)
    cid = detail['classInfo']['id']
    headers = student_headers(post,cid,detail['students'][0]['id'])
    assert post('/classes/'+cid,{'confirmation':'wrong'},method='DELETE').status_code == 400
    assert post('/classes/'+cid,{'confirmation':detail['classInfo']['name']},method='DELETE').status_code == 200
    assert client.get('/api/student',headers=headers).status_code == 401


def test_google_callback_enforces_verified_domain_and_registered_user(app, monkeypatch):
    from app.auth import oauth
    client = app.test_client()
    for info in (
        dict(email='admin@cuatrovientos.org', email_verified=False, hd='cuatrovientos.org'),
        dict(email='admin@cuatrovientos.org', email_verified=True, hd='other.org'),
        dict(email='unknown@cuatrovientos.org', email_verified=True, hd='cuatrovientos.org'),
    ):
        monkeypatch.setattr(oauth.google, 'authorize_access_token', lambda: {'userinfo': info})
        assert client.get('/auth/callback').status_code == 403
    monkeypatch.setattr(oauth.google, 'authorize_access_token', lambda: {'userinfo': dict(email='admin@cuatrovientos.org', email_verified=True, hd='cuatrovientos.org')})
    assert client.get('/auth/callback').status_code == 302
    assert client.get('/api/session').json['user']['role'] == 'ADMIN'


def test_secret_rotation_invalidates_old_student_links(app, client, post):
    detail = make_class(client,post,1)
    headers = student_headers(post,detail['classInfo']['id'],detail['students'][0]['id'])
    app.config['SECRET_KEY'] = 'new-test-key-' * 5
    assert client.get('/api/student',headers=headers).status_code == 401


def test_student_removal_and_reenrollment(client,post):
    detail=make_class(client,post,1)
    cid=detail['classInfo']['id']
    student=detail['students'][0]
    assert post(f'/classes/{cid}/students/{student["id"]}',method='DELETE').status_code==200
    assert client.get('/api/classes/'+cid).json['students']==[]
    assert post(f'/classes/{cid}/students',{'students':[dict(name=student['name'],email=student['email'])]}).json['added']==1
    complete(client,post,cid,student['id'])
    assert post(f'/classes/{cid}/students/{student["id"]}',method='DELETE').status_code==409
