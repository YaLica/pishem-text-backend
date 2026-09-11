import os
import sqlite3
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, g, jsonify, request, session
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
DATABASE = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "instance", "app.sqlite3"))
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-key")
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "https://yalica.github.io")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=True,
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)

CORS(
    app,
    supports_credentials=True,
    origins=[FRONTEND_ORIGIN],
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def get_db():
    if "db" not in g:
        os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS works (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT 'Без названия',
            data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_works_user_updated
        ON works(user_id, updated_at DESC);
        """
    )
    db.commit()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_db().execute(
        "SELECT id, email, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()


def user_json(user):
    return {"id": user["id"], "email": user["email"], "created_at": user["created_at"]}


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return jsonify(error="Требуется вход в аккаунт"), 401
        return fn(*args, **kwargs)

    return wrapper


def valid_email(value):
    if not isinstance(value, str):
        return False
    value = value.strip()
    return 5 <= len(value) <= 254 and "@" in value and " " not in value


@app.get("/api/health")
def health():
    return jsonify(ok=True, service="pishem-text-backend")


@app.post("/api/auth/register")
def register():
    body = request.get_json(silent=True) or {}
    email = str(body.get("email", "")).strip().lower()
    password = body.get("password", "")

    if not valid_email(email):
        return jsonify(error="Введите корректный email"), 400
    if not isinstance(password, str) or len(password) < 8:
        return jsonify(error="Пароль должен содержать минимум 8 символов"), 400

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO users(email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, generate_password_hash(password), utc_now()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify(error="Пользователь с таким email уже зарегистрирован"), 409

    session.clear()
    session["user_id"] = cur.lastrowid
    user = db.execute(
        "SELECT id, email, created_at FROM users WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return jsonify(user=user_json(user)), 201


@app.post("/api/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    email = str(body.get("email", "")).strip().lower()
    password = body.get("password", "")
    user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    if user is None or not isinstance(password, str) or not check_password_hash(user["password_hash"], password):
        return jsonify(error="Неверный email или пароль"), 401

    session.clear()
    session["user_id"] = user["id"]
    return jsonify(user=user_json(user))


@app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/auth/me")
def me():
    user = current_user()
    return jsonify(user=user_json(user) if user else None)


@app.get("/api/works")
@login_required
def list_works():
    rows = get_db().execute(
        "SELECT id, title, created_at, updated_at FROM works WHERE user_id = ? ORDER BY updated_at DESC",
        (session["user_id"],),
    ).fetchall()
    return jsonify(works=[dict(row) for row in rows])


@app.post("/api/works")
@login_required
def create_work():
    body = request.get_json(silent=True) or {}
    title = str(body.get("title", "Без названия")).strip()[:200] or "Без названия"
    data = body.get("data")
    if not isinstance(data, str):
        return jsonify(error="Поле data должно быть строкой JSON"), 400
    if len(data.encode("utf-8")) > 1_500_000:
        return jsonify(error="Работа слишком большая"), 413

    now = utc_now()
    db = get_db()
    cur = db.execute(
        "INSERT INTO works(user_id, title, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (session["user_id"], title, data, now, now),
    )
    db.commit()
    return jsonify(id=cur.lastrowid, title=title, created_at=now, updated_at=now), 201


@app.get("/api/works/<int:work_id>")
@login_required
def get_work(work_id):
    row = get_db().execute(
        "SELECT id, title, data, created_at, updated_at FROM works WHERE id = ? AND user_id = ?",
        (work_id, session["user_id"]),
    ).fetchone()
    if row is None:
        return jsonify(error="Работа не найдена"), 404
    return jsonify(work=dict(row))


@app.put("/api/works/<int:work_id>")
@login_required
def update_work(work_id):
    body = request.get_json(silent=True) or {}
    title = str(body.get("title", "Без названия")).strip()[:200] or "Без названия"
    data = body.get("data")
    if not isinstance(data, str):
        return jsonify(error="Поле data должно быть строкой JSON"), 400
    if len(data.encode("utf-8")) > 1_500_000:
        return jsonify(error="Работа слишком большая"), 413

    now = utc_now()
    db = get_db()
    cur = db.execute(
        "UPDATE works SET title = ?, data = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (title, data, now, work_id, session["user_id"]),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="Работа не найдена"), 404
    return jsonify(id=work_id, title=title, updated_at=now)


@app.delete("/api/works/<int:work_id>")
@login_required
def delete_work(work_id):
    db = get_db()
    cur = db.execute(
        "DELETE FROM works WHERE id = ? AND user_id = ?",
        (work_id, session["user_id"]),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="Работа не найдена"), 404
    return jsonify(ok=True)


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
