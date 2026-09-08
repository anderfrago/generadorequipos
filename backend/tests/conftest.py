import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.auth import register_user
from app.db import init_db, get_db


@pytest.fixture
def app(tmp_path):
    app = create_app(dict(TESTING=True, SECRET_KEY="test-only-secret-" * 4, DATABASE_PATH=str(tmp_path / "app.sqlite3"), SESSION_COOKIE_SECURE=False))
    with app.app_context():
        init_db()
        register_user("admin@cuatrovientos.org", "Administración", "ADMIN")
        register_user("teacher@cuatrovientos.org", "Docente")
    return app


@pytest.fixture
def client(app):
    client = app.test_client()
    with app.app_context():
        user_id = get_db().execute("SELECT id FROM users WHERE role='ADMIN'").fetchone()["id"]
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["csrf"] = "test-csrf"
    return client


@pytest.fixture
def post(client):
    def call(path, data=None, method="POST", headers=None):
        return client.open('/api' + path, method=method, json=data or {}, headers={"X-CSRF-Token": "test-csrf", **(headers or {})})
    return call
