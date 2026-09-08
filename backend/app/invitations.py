"""Explicit, individually addressed course invitations via authenticated TLS SMTP."""
import hashlib
import hmac
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from html import escape
from urllib.parse import urlencode, urlparse
from flask import Blueprint, abort, current_app, g, jsonify, request
from .auth import teacher, class_access
from .classes import enrollment, now, payload, audit
from .db import get_db
from .students import latest, make_token

bp = Blueprint('invitations', __name__, url_prefix='/api')


def valid_email(value):
    return bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value or ''))


def configuration():
    config = current_app.config
    sender = config['MAIL_FROM'] or config['MAIL_USERNAME']
    ready = bool(config['MAIL_USERNAME'] and config['MAIL_PASSWORD'] and valid_email(sender))
    return sender, ready


def fingerprint(en, email):
    return hashlib.sha256(f"{en['id']}|{en['token_hash']}|{email}".encode()).hexdigest()


def last_delivery(en_id):
    return get_db().execute('SELECT * FROM invitation_deliveries WHERE enrollment_id=? ORDER BY created_at DESC LIMIT 1', (en_id,)).fetchone()


def delivery_state(en, email):
    last = last_delivery(en['id'])
    if not last:
        return 'PENDING', ''
    if last['status'] == 'SENDING':
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(last['updated_at'])).total_seconds()
        if elapsed <= 120:
            return 'SENDING', last['updated_at']
        return 'UNKNOWN', last['updated_at']
    if last['fingerprint'] != fingerprint(en, email):
        return 'STALE', last['updated_at']
    return last['status'], last['updated_at']


def invitation_text(cls, name, link):
    subject = 'Invitación al curso: ' + ' '.join(cls['name'].split())
    text = (f"Hola, {name}:\n\nTe invitamos a completar el cuestionario inicial del curso {cls['name']} "
            f"({cls['academic_year']} · {cls['evaluation_period']}).\n\n"
            f"Abre tu enlace individual:\n{link}\n\n"
            "Responde pensando en cómo sueles trabajar. No hay respuestas correctas o incorrectas y el resultado no es una calificación. "
            "Nos ayudará a conocernos mejor y a organizar el trabajo en equipo.\n\n"
            "Puedes guardar tus respuestas y continuar más tarde. Al terminar, pulsa Enviar para finalizar.\n\n"
            "Este enlace es personal y permite acceder a tu cuestionario. No lo compartas.\n\n"
            "Si tienes alguna duda, responde a este correo para contactar con tu docente.\n\nGracias.\nCuatrovientos")
    return subject, text


def compose(cls, student, link, reply_to):
    sender, _ = configuration()
    subject, text = invitation_text(cls, student['name'], link)
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = formataddr((current_app.config['MAIL_FROM_NAME'], sender))
    message['To'] = student['email']
    message['Reply-To'] = reply_to
    message['Message-ID'] = make_msgid(domain=sender.split('@')[-1])
    message.set_content(text)
    paragraphs = ''.join('<p>' + escape(part).replace('\n', '<br>') + '</p>' for part in text.split('\n\n'))
    paragraphs = paragraphs.replace(escape(link), '<a href="' + escape(link, quote=True) + '" style="color:#0f4285">Abrir mi cuestionario</a>')
    message.add_alternative('<html lang="es"><body style="font-family:Segoe UI,Arial,sans-serif;background:white;color:#243247;line-height:1.6">'
                            '<div style="max-width:640px;margin:auto;padding:24px"><h1 style="color:#0f4285;font-size:24px">'
                            + escape(cls['name']) + '</h1>' + paragraphs + '</div></body></html>', subtype='html')
    return message


class DeliveryError(Exception):
    def __init__(self, message, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain


def deliver(message):
    config = current_app.config
    smtp = None
    transmitting = False
    try:
        smtp = smtplib.SMTP(config['MAIL_HOST'], config['MAIL_PORT'], timeout=15)
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(config['MAIL_USERNAME'], config['MAIL_PASSWORD'])
        transmitting = True
        smtp.send_message(message, from_addr=configuration()[0], to_addrs=[message['To']])
    except smtplib.SMTPAuthenticationError:
        raise DeliveryError('Google rechazó las credenciales de correo. Revisa la contraseña de aplicación y la política del centro.') from None
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError):
        raise DeliveryError('El servidor rechazó el mensaje. Revisa destinatario, remitente y cuota de envío.') from None
    except (OSError, smtplib.SMTPException):
        raise DeliveryError('No se pudo confirmar el envío. Comprueba la conexión y la cuenta de correo.', uncertain=transmitting) from None
    finally:
        if smtp:
            # A failure on QUIT must not turn an accepted message into a failed send.
            try:
                smtp.quit()
            except (OSError, smtplib.SMTPException):
                smtp.close()


@bp.get('/classes/<class_id>/invitations')
@teacher
def preview(class_id):
    cls = class_access(class_id)
    sender, ready = configuration()
    rows = []
    for en in get_db().execute('SELECT e.*,s.name,s.email FROM enrollments e JOIN students s ON s.id=e.student_id WHERE e.class_id=? AND e.active=1 ORDER BY s.name', (class_id,)):
        status, sent_at = delivery_state(en, en['email'])
        sub = latest(en['id'])
        reason = ''
        if not valid_email(en['email']):
            reason = 'Falta un correo válido.'
        elif not en['token_hash'] or not hmac.compare_digest(en['token_hash'], hashlib.sha256(make_token(en['id'], en['token_version']).encode()).hexdigest()):
            reason = 'Genera o renueva el enlace individual antes de enviar.'
        elif sub and sub['status'] == 'SUBMITTED':
            reason = 'Cuestionario ya enviado.'
        elif status in ('SENDING', 'UNKNOWN'):
            reason = 'Envío en curso o sin confirmación. Revisa antes de reenviar.'
        rows.append(dict(student_id=en['student_id'], name=en['name'], email=en['email'], status=status, updated_at=sent_at,
                         reason=reason, eligible=not reason, last_message=(last_delivery(en['id']) or {'message':''})['message']))
    subject, body = invitation_text(cls, '[Nombre del alumno/a]', '[Enlace individual del alumno/a]')
    return jsonify(sender=sender, configured=ready, reply_to=g.user['email'], subject=subject, body=body, recipients=rows)


@bp.post('/classes/<class_id>/students/<student_id>/invitation')
@teacher
def send_invitation(class_id, student_id):
    cls = class_access(class_id)
    sender, ready = configuration()
    if not ready:
        abort(503, 'Configura el correo en backend/.env siguiendo manual/07-correo.md.')
    base = current_app.config['PUBLIC_BASE_URL']
    if urlparse(base).scheme != 'https':
        abort(503, 'PUBLIC_BASE_URL debe ser la dirección HTTPS pública de la aplicación para enviar invitaciones.')
    data = payload()
    request_id = data.get('request_id')
    resend = data.get('resend', False)
    if not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,64}', request_id) or type(resend) is not bool:
        abort(400, 'Identificador o modo de envío no válido.')
    db = get_db()
    with db:
        db.execute('BEGIN IMMEDIATE')
        en = enrollment(class_id, student_id)
        previous_request = db.execute('SELECT * FROM invitation_deliveries WHERE id=?', (request_id,)).fetchone()
        if previous_request:
            if previous_request['enrollment_id'] != en['id']:
                abort(409, 'Identificador de envío ya utilizado.')
            return jsonify(status=previous_request['status'], message=previous_request['message'], repeated=True)
        student = db.execute('SELECT * FROM students WHERE id=?', (student_id,)).fetchone()
        if not valid_email(student['email']):
            abort(400, 'El alumno necesita un correo válido.')
        token = make_token(en['id'], en['token_version'])
        if not en['token_hash'] or not hmac.compare_digest(en['token_hash'], hashlib.sha256(token.encode()).hexdigest()):
            abort(409, 'Genera o renueva el enlace individual antes de enviar la invitación.')
        sub = latest(en['id'])
        if sub and sub['status'] == 'SUBMITTED':
            abort(409, 'El cuestionario ya está enviado. Reábrelo si el alumno debe volver a responder.')
        state, _ = delivery_state(en, student['email'])
        if state == 'SENDING':
            abort(409, 'Ya hay un envío en curso para este alumno.')
        if state == 'UNKNOWN' and not resend:
            abort(409, 'El envío anterior no tiene confirmación. Revisa el buzón antes de reenviar explícitamente.')
        if state == 'SENT' and not resend:
            return jsonify(status='SKIPPED', message='Esta invitación ya fue aceptada por el servidor.')
        link = base + '/student#' + urlencode(dict(code=cls['code'], token=token))
        message = compose(cls, student, link, g.user['email'])
        db.execute('INSERT INTO invitation_deliveries VALUES(?,?,?,?,?,?,?,?,?)',
                   (request_id, en['id'], fingerprint(en, student['email']), student['email'], 'SENDING', '', now(), now(), g.user['id']))
    status, info = 'SENT', 'El servidor de correo aceptó la invitación. La entrega en el buzón no está confirmada.'
    try:
        deliver(message)
    except DeliveryError as error:
        status, info = ('UNKNOWN' if error.uncertain else 'FAILED'), str(error)
    with db:
        db.execute('UPDATE invitation_deliveries SET status=?,message=?,updated_at=? WHERE id=?', (status, info, now(), request_id))
        audit('INVITATION_' + status, student_id)
    return jsonify(status=status, message=info)
