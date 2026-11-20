import os
import sqlite3
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask, g, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.middleware.proxy_fix import ProxyFix

from services.impl import hash_password, validate_credentials

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

PAGE_SIZE = 10
DB_PATH = os.environ.get("DATABASE_PATH") or os.path.join(BASE_DIR, "revision.db")
ALLOW_REGISTRATION = os.environ.get("ALLOW_REGISTRATION", "true").lower() == "true"
SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "true").lower() == "true"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

app = Flask(__name__)

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if len(SECRET_KEY) < 32:
    raise RuntimeError(
        "SECRET_KEY is missing or too short. Put a random value of 32+ characters in the .env file. "
        'Generate one with: python3 -c "import secrets; print(secrets.token_hex(32))"'
    )
app.secret_key = SECRET_KEY

app.config.update(
    SESSION_COOKIE_SECURE=SECURE_COOKIES,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,      # CSV upload limit
    # A page of 10 records x many columns posts many form fields; Werkzeug 3.1's
    # defaults (1000 parts / 500 kB) would reject wide CSVs.
    MAX_FORM_PARTS=20000,
    MAX_FORM_MEMORY_SIZE=8 * 1024 * 1024,
)

# One reverse proxy in front of the app (PythonAnywhere): trust it for client IP and HTTPS.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

csrf = CSRFProtect(app)
# Counters live in memory, per worker process.
limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")


SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS projects(
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    header TEXT NOT NULL,
    labels TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS records(
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    original_values_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS revisions(
    record_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    values_json TEXT NOT NULL,
    note TEXT DEFAULT '',
    revised_at TEXT NOT NULL,
    PRIMARY KEY(record_id, user_id));
CREATE TABLE IF NOT EXISTS page_reviews(
    project_id INTEGER,
    page INTEGER,
    user_id INTEGER,
    revised_at TEXT,
    PRIMARY KEY(project_id, page, user_id));
CREATE TABLE IF NOT EXISTS changes(
    id INTEGER PRIMARY KEY,
    record_id INTEGER,
    col TEXT,
    old_value TEXT,
    new_value TEXT,
    user_id INTEGER,
    changed_at TEXT);
CREATE INDEX IF NOT EXISTS idx_records_project ON records(project_id, position);
CREATE INDEX IF NOT EXISTS idx_revisions_user ON revisions(user_id);
CREATE INDEX IF NOT EXISTS idx_page_reviews_user ON page_reviews(user_id);
CREATE INDEX IF NOT EXISTS idx_changes_record ON changes(record_id);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=15)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    con = sqlite3.connect(DB_PATH, timeout=15)
    try:
        con.executescript(SCHEMA)
        con.commit()
        has_admin = con.execute("SELECT 1 FROM users WHERE is_admin=1 LIMIT 1").fetchone()
        if not has_admin:
            if not (ADMIN_EMAIL and ADMIN_PASSWORD):
                raise RuntimeError(
                    "No admin account exists. Set ADMIN_EMAIL and ADMIN_PASSWORD in the .env "
                    "file; the admin is created on startup."
                )
            email = validate_credentials(ADMIN_EMAIL, ADMIN_PASSWORD)
            existing = con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if existing:
                con.execute("UPDATE users SET is_admin=1 WHERE id=?", (existing[0],))
            else:
                con.execute(
                    "INSERT INTO users(email, password, is_admin) VALUES(?,?,1)",
                    (email, hash_password(ADMIN_PASSWORD)),
                )
            con.commit()
            print(f"Admin account ready: {email}")
    finally:
        con.close()


from views import create_blueprints  # noqa: E402

auth_bp, project_bp, admin_bp = create_blueprints(
    get_db=get_db,
    allow_registration=ALLOW_REGISTRATION,
    page_size=PAGE_SIZE,
    limiter=limiter,
)
app.register_blueprint(auth_bp, name="auth")
app.register_blueprint(project_bp, name="project")
app.register_blueprint(admin_bp, name="admin")


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


def _error(code, title, message):
    return render_template("error.html", code=code, title=title, message=message), code


@app.errorhandler(CSRFError)
def csrf_error(_):
    return _error(400, "Session expired", "Your form expired. Go back, reload the page and try again.")


@app.errorhandler(403)
def forbidden(_):
    return _error(403, "Not allowed", "You do not have access to this page.")


@app.errorhandler(404)
def not_found(_):
    return _error(404, "Page not found", "That page does not exist.")


@app.errorhandler(413)
def too_large(_):
    return _error(413, "File too large", "The upload is larger than 10 MB.")


@app.errorhandler(429)
def too_many(_):
    return _error(429, "Too many attempts", "Please wait a few minutes and try again.")


@app.errorhandler(500)
def server_error(_):
    return _error(500, "Something went wrong", "The error has been logged. Please try again.")


init_db()

if __name__ == "__main__":
    app.run(debug=False)
