from uuid import uuid4
from unittest.mock import MagicMock
import smtplib
import pytest
from app.invitations import DeliveryError, deliver


@pytest.fixture
def roster(app,client,post):
    app.config.update(MAIL_USERNAME='sender@cuatrovientos.org',MAIL_PASSWORD='test-only-password',PUBLIC_BASE_URL='https://example.pythonanywhere.com')
    cid=post('/classes',{'name':'Curso de programación','academic_year':'2026-2027','evaluation_period':'INICIAL'}).json['id']
    post('/classes/'+cid+'/students',{'students':[{'name':'Ana','email':'ana@example.com'},{'name':'Luis','email':'luis@example.com'}]})
    students=client.get('/api/classes/'+cid).json['students']
    return cid,students


def issue(post,cid,student):
    return post(f'/classes/{cid}/students/{student["id"]}/link').json['url']


def send(post,cid,student,**data):
    return post(f'/classes/{cid}/students/{student["id"]}/invitation',{'request_id':str(uuid4()),**data})


def test_preview_and_individual_message(roster,client,post,monkeypatch):
    cid,students=roster
    preview=client.get(f'/api/classes/{cid}/invitations').json
    assert preview['configured'] and all(not r['eligible'] for r in preview['recipients'])
    link=issue(post,cid,students[0])
    other_link=issue(post,cid,students[1])
    sent=[]
    monkeypatch.setattr('app.invitations.deliver',sent.append)
    assert send(post,cid,students[0]).json['status']=='SENT'
    assert len(sent)==1
    message=sent[0]
    assert message['To']=='ana@example.com'
    assert message['Reply-To']=='admin@cuatrovientos.org'
    text=message.get_body(preferencelist=('plain',)).get_content()
    assert link in text and other_link not in text and '2026-2027' in text and 'Curso de programación' in text
    assert 'MAIL_PASSWORD' not in client.get(f'/api/classes/{cid}/invitations').get_data(as_text=True)


def test_duplicates_and_explicit_resend(roster,post,monkeypatch):
    cid,students=roster
    issue(post,cid,students[0]); sent=[]
    monkeypatch.setattr('app.invitations.deliver',sent.append)
    request_id=str(uuid4())
    assert send(post,cid,students[0],request_id=request_id).json['status']=='SENT'
    assert send(post,cid,students[0],request_id=request_id).json['repeated']
    assert send(post,cid,students[0]).json['status']=='SKIPPED'
    assert len(sent)==1
    assert send(post,cid,students[0],resend=True).json['status']=='SENT'
    assert len(sent)==2


def test_revoked_links_are_not_reactivated(roster,post,monkeypatch):
    cid,students=roster
    issue(post,cid,students[0])
    post(f'/classes/{cid}/students/{students[0]["id"]}/link',{'action':'revoke'})
    sent=[];monkeypatch.setattr('app.invitations.deliver',sent.append)
    assert send(post,cid,students[0]).status_code==409
    assert not sent


def test_uncertain_send_requires_explicit_resend(roster,post,client,monkeypatch):
    cid,students=roster
    issue(post,cid,students[0])
    def fail(message):
        raise DeliveryError('Sin confirmación',uncertain=True)
    monkeypatch.setattr('app.invitations.deliver',fail)
    assert send(post,cid,students[0]).json['status']=='UNKNOWN'
    assert send(post,cid,students[0]).status_code==409
    assert client.get(f'/api/classes/{cid}/invitations').json['recipients'][0]['status']=='UNKNOWN'
    monkeypatch.setattr('app.invitations.deliver',lambda m:None)
    assert send(post,cid,students[0],resend=True).json['status']=='SENT'


def test_unconfigured_mail_and_unauthorized_access(roster,app,post,client):
    cid,students=roster
    issue(post,cid,students[0])
    app.config['MAIL_PASSWORD']=''
    assert send(post,cid,students[0]).status_code==503
    anonymous=app.test_client()
    assert anonymous.get(f'/api/classes/{cid}/invitations').status_code==401
    from app.db import get_db
    with app.app_context():
        uid=get_db().execute("SELECT id FROM users WHERE role='TEACHER'").fetchone()['id']
    with client.session_transaction() as session:
        session['user_id']=uid
    assert client.get(f'/api/classes/{cid}/invitations').status_code==403


def test_smtp_uses_tls_and_one_recipient(roster,app,monkeypatch):
    from email.message import EmailMessage
    smtp=MagicMock();smtp.send_message.return_value={}
    factory=MagicMock(return_value=smtp)
    monkeypatch.setattr('app.invitations.smtplib.SMTP',factory)
    message=EmailMessage();message['To']='ana@example.com';message.set_content('Prueba')
    with app.app_context():
        deliver(message)
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with('sender@cuatrovientos.org','test-only-password')
    assert smtp.send_message.call_args.kwargs['to_addrs']==['ana@example.com']


def test_smtp_auth_failure_is_definite_and_quit_failure_does_not_repeat(roster,app,monkeypatch):
    from email.message import EmailMessage
    smtp=MagicMock();monkeypatch.setattr('app.invitations.smtplib.SMTP',lambda *a,**k:smtp)
    message=EmailMessage();message['To']='ana@example.com';message.set_content('Prueba')
    smtp.login.side_effect=smtplib.SMTPAuthenticationError(535,b'Credentials rejected')
    with app.app_context(),pytest.raises(DeliveryError) as err:
        deliver(message)
    assert not err.value.uncertain and smtp.send_message.call_count==0
    smtp.login.side_effect=None;smtp.quit.side_effect=smtplib.SMTPServerDisconnected()
    with app.app_context():
        deliver(message)
    assert smtp.send_message.call_count==1
