"""Teacher administration and class roster, independent of questionnaire scoring."""
import json
import secrets
import re
import unicodedata
from datetime import datetime, timezone
from uuid import uuid4
from flask import Blueprint, abort, g, jsonify, request
from .auth import teacher, class_access, register_user
from .db import get_db

bp = Blueprint("classes", __name__, url_prefix="/api")


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid4())


def payload():
    value = request.get_json()
    if not isinstance(value, dict):
        abort(400, "Se esperaba un objeto JSON.")
    return value


def text_field(data, key, limit=200, required=False):
    value = data.get(key, "")
    if not isinstance(value, str) or len(value) > limit:
        abort(400, "Campo no válido: " + key)
    value = value.strip()
    if required and not value:
        abort(400, "Falta el campo: " + key)
    return value


def audit(action, entity):
    get_db().execute("INSERT INTO audit_log(actor,action,entity_id,created_at) VALUES(?,?,?,?)",
                     (g.user["email"], action, entity, now()))


def enrollment(class_id, student_id):
    row = get_db().execute("SELECT * FROM enrollments WHERE class_id=? AND student_id=? AND active=1",
                           (class_id, student_id)).fetchone()
    if not row:
        abort(404, "Alumno no matriculado en esta clase.")
    return row


@bp.get("/classes")
@teacher
def list_classes():
    rows = get_db().execute(
        "SELECT c.*, (SELECT COUNT(*) FROM enrollments e WHERE e.class_id=c.id AND e.active=1) total "
        "FROM classes c WHERE c.active=1 AND (?='ADMIN' OR EXISTS "
        "(SELECT 1 FROM class_teachers t WHERE t.class_id=c.id AND t.user_id=?)) ORDER BY c.created_at DESC",
        (g.user["role"], g.user["id"]),
    ).fetchall()
    return jsonify([dict(row) for row in rows])


@bp.post("/classes")
@teacher
def create_class():
    data = payload()
    name = text_field(data, "name", required=True)
    year = text_field(data, "academic_year", 40, True)
    period = text_field(data, "evaluation_period", 80) or "INICIAL"
    class_id = uid()
    db = get_db()
    with db:
        db.execute("INSERT INTO classes(id,name,academic_year,evaluation_period,code,created_by,created_at) VALUES(?,?,?,?,?,?,?)",
                   (class_id, name, year, period, secrets.token_hex(4).upper(), g.user["id"], now()))
        db.execute("INSERT INTO class_teachers VALUES(?,?)", (class_id, g.user["id"]))
        audit("CREATE_CLASS", class_id)
    return jsonify(id=class_id), 201


@bp.patch("/classes/<class_id>")
@teacher
def update_class(class_id):
    class_access(class_id)
    data = payload()
    with get_db():
        get_db().execute("UPDATE classes SET name=?,academic_year=?,evaluation_period=? WHERE id=?",
                         (text_field(data, "name", required=True), text_field(data, "academic_year", 40, True),
                          text_field(data, "evaluation_period", 80) or "INICIAL", class_id))
        audit("UPDATE_CLASS", class_id)
    return jsonify(ok=True)


@bp.delete("/classes/<class_id>")
@teacher
def delete_class(class_id):
    cls = class_access(class_id)
    if payload().get("confirmation") != cls["name"]:
        abort(400, "Escribe el nombre exacto de la clase para eliminarla.")
    with get_db():
        get_db().execute("UPDATE classes SET active=0 WHERE id=?", (class_id,))
        get_db().execute("UPDATE enrollments SET active=0,token_hash=NULL WHERE class_id=?", (class_id,))
        audit("DELETE_CLASS", class_id)
    return jsonify(ok=True)


@bp.get("/classes/<class_id>")
@teacher
def class_detail(class_id):
    cls = class_access(class_id)
    db = get_db()
    students = []
    for row in db.execute("SELECT s.*,e.id enrollment_id,e.token_hash IS NOT NULL link_active FROM students s "
                          "JOIN enrollments e ON e.student_id=s.id WHERE e.class_id=? AND e.active=1 ORDER BY s.name", (class_id,)):
        student = dict(row)
        sub = db.execute("SELECT * FROM submissions WHERE enrollment_id=? ORDER BY revision DESC LIMIT 1",
                         (row["enrollment_id"],)).fetchone()
        student.update(status=sub["status"] if sub else "PENDING", result=json.loads(sub["result"]) if sub and sub["result"] else None,
                       conditions=json.loads(sub["conditions"]) if sub else [], open_response=sub["open_response"] if sub else "")
        obs = db.execute("SELECT data FROM observations WHERE enrollment_id=?", (row["enrollment_id"],)).fetchone()
        student["observation"] = json.loads(obs["data"]) if obs else {}
        students.append(student)
    relations = [dict(r) for r in db.execute("SELECT * FROM relations WHERE class_id=?", (class_id,))]
    teachers = [dict(r) for r in db.execute("SELECT u.id,u.name,u.email FROM users u JOIN class_teachers t ON t.user_id=u.id WHERE t.class_id=?", (class_id,))]
    return jsonify(classInfo=dict(cls), students=students, relations=relations, teachers=teachers)


@bp.post("/classes/<class_id>/students")
@teacher
def add_students(class_id):
    class_access(class_id)
    rows = payload().get("students")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        abort(400, "Añade entre 1 y 200 alumnos por operación.")
    db = get_db()
    added = 0
    with db:
        for row in rows:
            if not isinstance(row, dict):
                abort(400, "Alumno no válido.")
            name = unicodedata.normalize("NFC", " ".join(text_field(row, "name", required=True).split()))
            email = text_field(row, "email", 254).lower()
            if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
                abort(400, "Correo no válido: " + email)
            external = text_field(row, "external_ref", 100)
            existing = db.execute("SELECT id FROM students WHERE (email<>'' AND email=?) OR (external_ref<>'' AND external_ref=?)", (email, external)).fetchone()
            student_id = existing["id"] if existing else uid()
            if not existing:
                db.execute("INSERT INTO students VALUES(?,?,?,?)", (student_id, name, email, external))
            enrolled = db.execute("SELECT id,active FROM enrollments WHERE class_id=? AND student_id=?", (class_id, student_id)).fetchone()
            if not enrolled:
                db.execute("INSERT INTO enrollments(id,class_id,student_id) VALUES(?,?,?)", (uid(), class_id, student_id))
                added += 1
            elif not enrolled["active"]:
                db.execute("UPDATE enrollments SET active=1,token_hash=NULL WHERE id=?", (enrolled["id"],))
                added += 1
        audit("ADD_STUDENTS", class_id)
    return jsonify(added=added)


@bp.delete("/classes/<class_id>/students/<student_id>")
@teacher
def remove_student(class_id, student_id):
    class_access(class_id)
    en = enrollment(class_id, student_id)
    db = get_db()
    with db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM submissions WHERE enrollment_id=?", (en["id"],)).fetchone() or db.execute("SELECT 1 FROM observations WHERE enrollment_id=?", (en["id"],)).fetchone():
            abort(409, "No se puede retirar a una persona que ya tiene respuestas u observaciones.")
        db.execute("UPDATE enrollments SET active=0,token_hash=NULL WHERE id=?", (en["id"],))
        db.execute("DELETE FROM relations WHERE class_id=? AND (student_a=? OR student_b=?)", (class_id,student_id,student_id))
        audit("REMOVE_STUDENT", student_id)
    return jsonify(ok=True)


@bp.post("/classes/<class_id>/students/<student_id>/observation")
@teacher
def observation(class_id, student_id):
    class_access(class_id)
    en = enrollment(class_id, student_id)
    data = payload()
    clean = {k: text_field(data, k, n) for k, n in [("free_text", 4000), ("other_functional_needs", 2000)]}
    for k in ("autonomy_observed", "responsibility_observed", "organization_observed"):
        value = data.get(k, "")
        if str(value) not in ("", "1", "2", "3", "4"):
            abort(400, "Las observaciones deben estar entre 1 y 4 o sin valorar.")
        clean[k] = str(value)
    with get_db():
        get_db().execute("INSERT INTO observations VALUES(?,?,?,?) ON CONFLICT(enrollment_id) DO UPDATE SET "
                         "author_id=excluded.author_id,data=excluded.data,updated_at=excluded.updated_at",
                         (en["id"], g.user["id"], json.dumps(clean), now()))
        audit("SAVE_OBSERVATION", student_id)
    return jsonify(ok=True)


@bp.post("/classes/<class_id>/relations")
@teacher
def save_relation(class_id):
    class_access(class_id)
    data = payload()
    a, b = sorted([text_field(data, "student_a", required=True), text_field(data, "student_b", required=True)])
    enrollment(class_id, a)
    enrollment(class_id, b)
    kind = data.get("type")
    if a == b or kind not in ("NO_JUNTAR", "MEJOR_SEPARADOS", "CONVIENE_JUNTOS"):
        abort(400, "Selecciona dos alumnos diferentes y una relación válida.")
    with get_db():
        get_db().execute("INSERT INTO relations VALUES(?,?,?,?,?,?) ON CONFLICT(class_id,student_a,student_b) "
                         "DO UPDATE SET type=excluded.type,comment=excluded.comment",
                         (uid(), class_id, a, b, kind, text_field(data, "comment", 1000)))
        audit("SAVE_RELATION", class_id)
    return jsonify(ok=True)


@bp.delete("/classes/<class_id>/relations/<relation_id>")
@teacher
def delete_relation(class_id, relation_id):
    class_access(class_id)
    with get_db():
        get_db().execute("DELETE FROM relations WHERE class_id=? AND id=?", (class_id, relation_id))
        audit("DELETE_RELATION", relation_id)
    return jsonify(ok=True)


@bp.post("/classes/<class_id>/teachers")
@teacher
def assign_teacher(class_id):
    class_access(class_id)
    email = text_field(payload(), "email", 254, True).lower()
    user = get_db().execute("SELECT id FROM users WHERE email=? AND active=1", (email,)).fetchone()
    if not user:
        abort(400, "El administrador debe autorizar primero esta cuenta docente.")
    with get_db():
        get_db().execute("INSERT OR IGNORE INTO class_teachers VALUES(?,?)", (class_id, user["id"]))
        audit("ASSIGN_TEACHER", class_id)
    return jsonify(ok=True)


@bp.get("/users")
@teacher
def users():
    if g.user["role"] != "ADMIN":
        abort(403)
    return jsonify([dict(r) for r in get_db().execute("SELECT id,email,name,role,active FROM users ORDER BY name")])


@bp.post("/users")
@teacher
def authorize_user():
    if g.user["role"] != "ADMIN":
        abort(403)
    data = payload()
    role = data.get("role", "TEACHER")
    if role not in ("ADMIN", "TEACHER"):
        abort(400, "Rol no válido.")
    try:
        register_user(text_field(data, "email", 254, True), text_field(data, "name", required=True), role)
    except ValueError as error:
        abort(400, str(error))
    return jsonify(ok=True)
