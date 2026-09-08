import hashlib
import hmac
import json
from urllib.parse import urlencode
from flask import Blueprint, abort, current_app, jsonify, request
from .auth import teacher, class_access
from .classes import audit, enrollment, now, payload, uid, text_field
from .db import get_db
from .scoring import QUESTIONNAIRE, ITEMS, SCALE, calculate

bp = Blueprint("students", __name__, url_prefix="/api")


def make_token(enrollment_id, version):
    return hmac.new(current_app.config["SECRET_KEY"].encode(), f"student:{enrollment_id}:{version}".encode(), hashlib.sha256).hexdigest()


def access():
    token = request.headers.get("X-Student-Token", "")
    code = request.headers.get("X-Class-Code", "")
    if not token or not code or len(token) > 200:
        abort(401, "Necesitas tu enlace individual.")
    row = get_db().execute("SELECT e.*,s.name student_name,c.name class_name,c.academic_year FROM enrollments e "
                            "JOIN classes c ON c.id=e.class_id JOIN students s ON s.id=e.student_id "
                            "WHERE c.code=? AND e.token_hash=? AND e.active=1 AND c.active=1",
                            (code, hashlib.sha256(token.encode()).hexdigest())).fetchone()
    if not row or not hmac.compare_digest(token, make_token(row["id"], row["token_version"])):
        abort(401, "Este enlace no es válido o ha sido revocado. Solicita uno nuevo al docente.")
    return row


def latest(enrollment_id):
    return get_db().execute("SELECT * FROM submissions WHERE enrollment_id=? ORDER BY revision DESC LIMIT 1", (enrollment_id,)).fetchone()


def state(sub):
    return dict(id=sub["id"], status=sub["status"], confirmed=bool(sub["confirmed"]), answers=json.loads(sub["answers"]),
                conditions=json.loads(sub["conditions"]), other_condition=sub["other_condition"], open_response=sub["open_response"],
                saved_at=sub["saved_at"], result=json.loads(sub["result"]) if sub["result"] else None)


@bp.post("/classes/<class_id>/students/<student_id>/link")
@teacher
def student_link(class_id, student_id):
    cls = class_access(class_id)
    en = enrollment(class_id, student_id)
    action = payload().get("action", "current")
    if action not in ("current", "rotate", "revoke"):
        abort(400, "Acción no válida.")
    version = en["token_version"]
    db = get_db()
    with db:
        if action == "revoke":
            db.execute("UPDATE enrollments SET token_hash=NULL WHERE id=?", (en["id"],))
            audit("REVOKE_LINK", en["id"])
            return jsonify(ok=True)
        if action == "rotate" or not en["token_hash"]:
            version += 1
        token = make_token(en["id"], version)
        db.execute("UPDATE enrollments SET token_version=?,token_hash=? WHERE id=?",
                   (version, hashlib.sha256(token.encode()).hexdigest(), en["id"]))
        audit("ISSUE_LINK", en["id"])
    link = current_app.config["PUBLIC_BASE_URL"] + "/student#" + urlencode(dict(code=cls["code"], token=token))
    return jsonify(url=link)


@bp.get("/student")
def bootstrap():
    en = access()
    sub = latest(en["id"])
    if not sub:
        # Initialization in an explicit POST keeps this read endpoint side-effect free.
        submission = None
    else:
        submission = state(sub)
    return jsonify(student=en["student_name"], className=en["class_name"], submission=submission,
                   questionnaire=dict(items=[dict(id=str(n), block=b, number=n, text=t) for b, n, t, d, r in ITEMS],
                                      conditions=[dict(code=c, text=t) for c, t in QUESTIONNAIRE["conditions"]], scale=SCALE))


@bp.post("/student/start")
def start():
    en = access()
    if payload().get("confirmed") is not True:
        abort(400, "Confirma que has leído la información inicial.")
    db = get_db()
    with db:
        db.execute("BEGIN IMMEDIATE")
        sub = latest(en["id"])
        if not sub:
            db.execute("INSERT INTO submissions(id,enrollment_id,revision,confirmed,questionnaire_version,created_at,saved_at) VALUES(?,?,1,1,?,?,?)",
                       (uid(), en["id"], QUESTIONNAIRE["version"], now(), now()))
        elif sub["status"] == "DRAFT":
            db.execute("UPDATE submissions SET confirmed=1 WHERE id=?", (sub["id"],))
    return jsonify(state(latest(en["id"])))


@bp.post("/student/save")
@bp.post("/student/submit")
def save():
    en = access()
    data = payload()
    answers = data.get("answers", {})
    allowed = {str(row[1]) for row in ITEMS}
    if not isinstance(answers, dict) or any(k not in allowed or type(v) is not int or v not in range(4) for k, v in answers.items()):
        abort(400, "Respuesta no válida.")
    conditions = data.get("conditions", [])
    if not isinstance(conditions, list) or any(not isinstance(c, str) or c not in dict(QUESTIONNAIRE["conditions"]) for c in conditions):
        abort(400, "Condición no válida.")
    conditions = list(dict.fromkeys(conditions))
    if "NONE" in conditions and len(conditions) != 1:
        abort(400, "Ninguna especialmente no puede combinarse con otras opciones.")
    other = text_field(data, "other_condition", 500)
    open_response = text_field(data, "open_response", 2000)
    submit = request.path.endswith("/submit")
    result = None
    if submit:
        try:
            result = calculate(answers, conditions, other)
        except ValueError as error:
            abort(400, str(error))
    db = get_db()
    with db:
        db.execute("BEGIN IMMEDIATE")
        sub = latest(en["id"])
        if not sub or sub["id"] != data.get("id"):
            abort(409, "El cuestionario ha cambiado. Recarga la página.")
        if sub["status"] != "DRAFT":
            abort(409, "El cuestionario ya está enviado.")
        if not sub["confirmed"]:
            abort(400, "Debes confirmar la información inicial.")
        db.execute("UPDATE submissions SET answers=?,conditions=?,other_condition=?,open_response=?,saved_at=?,status=?,result=?,submitted_at=? WHERE id=?",
                   (json.dumps(answers), json.dumps(conditions), other, open_response, now(), "SUBMITTED" if submit else "DRAFT",
                    json.dumps(result) if result else None, now() if submit else None, sub["id"]))
    return jsonify(state(latest(en["id"])))


@bp.post("/classes/<class_id>/students/<student_id>/reopen")
@teacher
def reopen(class_id, student_id):
    class_access(class_id)
    en = enrollment(class_id, student_id)
    db = get_db()
    with db:
        db.execute("BEGIN IMMEDIATE")
        previous = latest(en["id"])
        if not previous or previous["status"] != "SUBMITTED":
            abort(400, "No hay un cuestionario enviado que reabrir.")
        db.execute("INSERT INTO submissions(id,enrollment_id,revision,confirmed,answers,conditions,other_condition,open_response,questionnaire_version,created_at,saved_at) VALUES(?,?,?,1,?,?,?,?,?,?,?)",
                   (uid(), en["id"], previous["revision"] + 1, previous["answers"], previous["conditions"], previous["other_condition"],
                    previous["open_response"], previous["questionnaire_version"], now(), now()))
        audit("REOPEN_SUBMISSION", student_id)
    return jsonify(ok=True)
