import os
import sqlite3
from datetime import timedelta
from pathlib import Path
import click
from dotenv import load_dotenv
from flask import Flask, jsonify, send_from_directory, abort
from werkzeug.exceptions import HTTPException
from .db import init_db, close_db
from .auth import bp as auth_bp, configure_oauth, csrf_protect, register_user

ROOT = Path(__file__).resolve().parents[2]


def create_app(test_config=None):
    load_dotenv(ROOT / "backend" / ".env")
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", ""),
        DATABASE_PATH=os.getenv("DATABASE_PATH", str(ROOT / "instance" / "app.sqlite3")),
        GOOGLE_CLIENT_ID=os.getenv("GOOGLE_CLIENT_ID", ""),
        GOOGLE_CLIENT_SECRET=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        TEACHER_DOMAIN=os.getenv("TEACHER_DOMAIN", "cuatrovientos.org"),
        PUBLIC_BASE_URL=os.getenv("PUBLIC_BASE_URL", "http://localhost:5000").rstrip("/"),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "true").lower() == "true",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=1_000_000,
        FRONTEND_DIST=str(ROOT / "frontend" / "dist" / "browser"),
    )
    if test_config:
        app.config.update(test_config)
    if len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("Configura SECRET_KEY con al menos 32 caracteres en backend/.env.")
    app.teardown_appcontext(close_db)
    app.before_request(csrf_protect)
    configure_oauth(app)
    app.register_blueprint(auth_bp)
    from .classes import bp as classes_bp
    app.register_blueprint(classes_bp)
    from .students import bp as students_bp
    app.register_blueprint(students_bp)
    from .grouping import bp as grouping_bp
    app.register_blueprint(grouping_bp)
    from .reports import bp as reports_bp
    app.register_blueprint(reports_bp)

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(sqlite3.IntegrityError)
    def integrity_error(error):
        return jsonify(error="Los datos entran en conflicto con un registro existente."), 409

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    @app.get("/")
    @app.get("/<path:path>")
    def frontend(path=""):
        if path.startswith(("api/", "auth/")):
            abort(404)
        dist = Path(app.config["FRONTEND_DIST"])
        if path and (dist / path).is_file():
            return send_from_directory(dist, path)
        if not (dist / "index.html").is_file():
            abort(503, "Compila Angular siguiendo manual/01-desarrollo.md.")
        return send_from_directory(dist, "index.html")

    @app.cli.command("init-db")
    def initialize():
        """Create missing tables without deleting existing data."""
        init_db()
        email = os.getenv("ADMIN_EMAIL", "").strip()
        if email:
            register_user(email, email.split("@")[0], "ADMIN")
        click.echo("SQLite inicializado. Los datos existentes se conservan.")

    @app.cli.command("add-teacher")
    @click.argument("email")
    @click.option("--name", required=True)
    @click.option("--admin", is_flag=True)
    def add_teacher(email, name, admin):
        """Authorize a corporate Google account."""
        register_user(email, name, "ADMIN" if admin else "TEACHER")
        click.echo("Cuenta autorizada.")

    return app
