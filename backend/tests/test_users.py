from app.db import get_db


def test_admin_user_crud(client, post):
    created=post('/users',dict(name='Nueva docente',email='new@cuatrovientos.org',role='TEACHER',active=True))
    assert created.status_code==201
    uid=created.json['id']
    assert post('/users',dict(name='Duplicada',email='new@cuatrovientos.org')).status_code==409
    assert post('/users/'+uid,dict(name='Administradora',email='changed@cuatrovientos.org',role='ADMIN',active=True),method='PATCH').status_code==200
    user=next(u for u in client.get('/api/users').json if u['id']==uid)
    assert user['role']=='ADMIN' and user['email']=='changed@cuatrovientos.org'
    assert post('/users/'+uid,method='DELETE').status_code==200
    user=next(u for u in client.get('/api/users').json if u['id']==uid)
    assert not user['active']
    assert post('/users/'+uid,dict(name='Docente',email=user['email'],role='TEACHER',active=True),method='PATCH').status_code==200


def test_last_admin_and_role_validation(client,post):
    admin=next(u for u in client.get('/api/users').json if u['role']=='ADMIN')
    assert post('/users/'+admin['id'],method='DELETE').status_code==409
    assert post('/users/'+admin['id'],dict(name=admin['name'],email=admin['email'],role='TEACHER',active=True),method='PATCH').status_code==409
    assert post('/users',dict(name='Test',email='test@example.com')).status_code==400
    assert post('/users',dict(name='Test',email='test@cuatrovientos.org',role='INVALID')).status_code==400


def test_teacher_cannot_mutate_users_and_deleted_session_is_denied(app,client,post):
    users=client.get('/api/users').json
    teacher=next(u for u in users if u['role']=='TEACHER')
    other=app.test_client()
    with other.session_transaction() as session:
        session.update(user_id=teacher['id'],csrf='test')
    for method,path in [('POST','/api/users'),('PATCH','/api/users/'+teacher['id']),('DELETE','/api/users/'+teacher['id'])]:
        assert other.open(path,method=method,json={},headers={'X-CSRF-Token':'test'}).status_code==403
    assert post('/users/'+teacher['id'],method='DELETE').status_code==200
    assert other.get('/api/classes').status_code==401
