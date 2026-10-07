import secrets
from functools import wraps
from uuid import uuid4
from datetime import datetime, timezone
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, abort, current_app, g, jsonify, redirect, request, session
from .db import get_db

bp = Blueprint("auth", __name__)
oauth = OAuth()


def configure_oauth(app):
    oauth.init_app(app)
    oauth.register(
        name="google", client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile", "timeout": 15},
    )


def session_user():
    user = get_db().execute("SELECT * FROM users WHERE id=? AND active=1", (session.get("user_id"),)).fetchone()
    if not user or user["auth_version"] != session.get("auth_version") or not user["email"].endswith("@" + current_app.config["TEACHER_DOMAIN"]):
        return None
    return user


def teacher(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        g.user = session_user()
        if not g.user:
            abort(401, "Inicia sesión con tu cuenta docente.")
        return fn(*args, **kwargs)
    return wrapped


def class_access(class_id):
    cls = get_db().execute("SELECT * FROM classes WHERE id=? AND active=1", (class_id,)).fetchone()
    if not cls:
        abort(404, "Clase no encontrada.")
    if g.user["role"] != "ADMIN" and not get_db().execute(
        "SELECT 1 FROM class_teachers WHERE class_id=? AND user_id=?", (class_id, g.user["id"])
    ).fetchone():
        abort(403, "No tienes acceso a esta clase.")
    return cls


def csrf_protect():
    if request.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
        supplied = request.headers.get("X-CSRF-Token", "")
        expected = session.get("csrf", "")
        if not expected or not secrets.compare_digest(supplied, expected):
            abort(403, "La sesión ha caducado. Recarga la página.")


@bp.get("/api/session")
def current_session():
    session.setdefault("csrf", secrets.token_urlsafe(32))
    user = session_user()
    return jsonify(user={key:user[key] for key in ("id","email","name","role")} if user else None, csrf=session["csrf"])


@bp.get("/auth/google")
def login():
    if not current_app.config["GOOGLE_CLIENT_ID"]:
        abort(503, "Falta configurar Google OAuth. Consulta manual/02-google-oauth.md.")
    callback = current_app.config["PUBLIC_BASE_URL"] + "/auth/callback"
    return oauth.google.authorize_redirect(callback, hd=current_app.config["TEACHER_DOMAIN"], prompt="select_account")


@bp.get("/auth/callback")
def callback():
    try:
        token = oauth.google.authorize_access_token()
    except Exception:
        current_app.logger.warning("Google OAuth callback failed")
        abort(401, "No se pudo verificar el acceso de Google. Vuelve a iniciar sesión.")
    # Authlib verifies OIDC signature, issuer, audience, expiration and nonce.
    info = token.get("userinfo", {})
    email = str(info.get("email", "")).strip().lower()
    domain = current_app.config["TEACHER_DOMAIN"]
    if info.get("email_verified") is not True or info.get("hd") != domain or not email.endswith("@" + domain):
        abort(403, "Usa una cuenta corporativa de " + domain + ".")
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not user or not user["active"]:
        abort(403, "Tu cuenta todavía no está autorizada. Contacta con el administrador.")
    subject = info.get("sub")
    if not subject or (user["google_subject"] and user["google_subject"] != subject):
        abort(403, "La identidad de Google no coincide con la cuenta autorizada.")
    with db:
        db.execute("UPDATE users SET google_subject=? WHERE id=?", (subject,user["id"]))
    session.clear()
    session.update(user_id=user["id"], auth_version=user["auth_version"], csrf=secrets.token_urlsafe(32))
    session.permanent = True
    return redirect("/teacher")


@bp.post("/api/logout")
def logout():
    user = session_user()
    if user:
        with get_db():
            get_db().execute("UPDATE users SET auth_version=auth_version+1 WHERE id=?", (user["id"],))
    session.clear()
    return jsonify(ok=True)


def register_user(email, name, role="TEACHER"):
    email = email.strip().lower()
    if not email.endswith("@" + current_app.config["TEACHER_DOMAIN"]):
        raise ValueError("El correo debe pertenecer al dominio docente.")
    db = get_db()
    with db:
        db.execute(
            "INSERT INTO users(id,email,name,role,created_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(email) DO UPDATE SET name=excluded.name,role=excluded.role,active=1,auth_version=users.auth_version+1",
            (str(uuid4()), email, name, role, datetime.now(timezone.utc).isoformat()),
        )

