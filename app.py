import os
import secrets
import sqlite3
from datetime import datetime

from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for
)
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from openai import OpenAI
from werkzeug.security import (
    check_password_hash,
    generate_password_hash
)


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()


# =========================================================
# APP
# =========================================================

app = Flask(__name__)

secret_key = os.environ.get("FLASK_SECRET_KEY")

if not secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY is not configured."
    )

app.secret_key = secret_key


# =========================================================
# PRODUCTION SECURITY
# =========================================================

is_production = (
    os.environ.get("FLASK_ENV", "").lower()
    == "production"
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=is_production,
)


# =========================================================
# RATE LIMITING
# =========================================================

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[
        "200 per day",
        "50 per hour"
    ],
    storage_uri="memory://"
)


# =========================================================
# LOGIN
# =========================================================

login_manager = LoginManager()

login_manager.init_app(app)

login_manager.login_view = "login"


class User(UserMixin):

    def __init__(self, user_id, username):
        self.id = user_id
        self.username = username


@login_manager.user_loader
def load_user(user_id):

    connection = get_db()
    cursor = connection.cursor()

    if using_postgres():

        cursor.execute(
            """
            SELECT id, username
            FROM users
            WHERE id = %s
            """,
            (user_id,)
        )

    else:

        cursor.execute(
            """
            SELECT id, username
            FROM users
            WHERE id = ?
            """,
            (user_id,)
        )

    user = cursor.fetchone()

    cursor.close()
    connection.close()

    if user:
        return User(
            user[0],
            user[1]
        )

    return None


# =========================================================
# DATABASE
# =========================================================

DATABASE_URL = os.environ.get("DATABASE_URL")

SQLITE_DATABASE = "chatbot.db"


def using_postgres():

    return bool(DATABASE_URL)


def get_db():

    if using_postgres():

        import psycopg2

        database_url = DATABASE_URL

        # Some providers use postgres://.
        # psycopg2 expects postgresql://.
        if database_url.startswith("postgres://"):

            database_url = database_url.replace(
                "postgres://",
                "postgresql://",
                1
            )

        return psycopg2.connect(
            database_url
        )

    connection = sqlite3.connect(
        SQLITE_DATABASE
    )

    connection.row_factory = sqlite3.Row

    return connection


def init_database():

    connection = get_db()
    cursor = connection.cursor()

    if using_postgres():

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                response TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            chats_user_id_idx
            ON chats(user_id)
            """
        )

    else:

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                response TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            chats_user_id_idx
            ON chats(user_id)
            """
        )

    connection.commit()

    cursor.close()
    connection.close()


# =========================================================
# CSRF PROTECTION
# =========================================================

def get_csrf_token():

    if "csrf_token" not in session:

        session["csrf_token"] = secrets.token_urlsafe(32)

    return session["csrf_token"]


@app.context_processor
def inject_csrf_token():

    return {
        "csrf_token": get_csrf_token()
    }


def validate_csrf():

    token = request.form.get(
        "csrf_token"
    )

    if not token:

        token = request.headers.get(
            "X-CSRF-Token"
        )

    stored_token = session.get(
        "csrf_token"
    )

    if not token or not stored_token:

        return False

    return secrets.compare_digest(
        token,
        stored_token
    )


# =========================================================
# AI CLIENT
# =========================================================

hackclub_api_key = os.environ.get(
    "HACKCLUB_API_KEY"
)

if not hackclub_api_key:

    raise RuntimeError(
        "HACKCLUB_API_KEY is not configured."
    )


client = OpenAI(
    api_key=hackclub_api_key,
    base_url="https://ai.hackclub.com/proxy/v1"
)


# =========================================================
# SIGNUP
# =========================================================

@app.route(
    "/signup",
    methods=["GET", "POST"]
)
@limiter.limit("10 per minute")
def signup():

    if current_user.is_authenticated:

        return redirect(
            url_for("home")
        )

    error = None

    if request.method == "POST":

        if not validate_csrf():

            return "Invalid security token.", 400

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if not username or not password:

            error = (
                "Username and password are required."
            )

        elif len(username) < 3:

            error = (
                "Username must be at least "
                "3 characters."
            )

        elif len(username) > 30:

            error = (
                "Username must be 30 characters "
                "or fewer."
            )

        elif len(password) < 8:

            error = (
                "Password must be at least "
                "8 characters."
            )

        else:

            hashed_password = (
                generate_password_hash(password)
            )

            connection = get_db()
            cursor = connection.cursor()

            try:

                if using_postgres():

                    cursor.execute(
                        """
                        INSERT INTO users
                        (
                            username,
                            password,
                            created_at
                        )
                        VALUES (%s, %s, %s)
                        RETURNING id
                        """,
                        (
                            username,
                            hashed_password,
                            datetime.utcnow().isoformat()
                        )
                    )

                    user_id = cursor.fetchone()[0]

                else:

                    cursor.execute(
                        """
                        INSERT INTO users
                        (
                            username,
                            password,
                            created_at
                        )
                        VALUES (?, ?, ?)
                        """,
                        (
                            username,
                            hashed_password,
                            datetime.utcnow().isoformat()
                        )
                    )

                    user_id = cursor.lastrowid

                connection.commit()

                cursor.close()
                connection.close()

                user = User(
                    user_id,
                    username
                )

                login_user(user)

                return redirect(
                    url_for("home")
                )

            except Exception as error_message:

                connection.rollback()

                cursor.close()
                connection.close()

                print(
                    "SIGNUP ERROR:",
                    error_message
                )

                error = (
                    "That username already exists."
                )

    return render_template(
        "signup.html",
        error=error
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
@limiter.limit("10 per minute")
def login():

    if current_user.is_authenticated:

        return redirect(
            url_for("home")
        )

    error = None

    if request.method == "POST":

        if not validate_csrf():

            return "Invalid security token.", 400

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        connection = get_db()
        cursor = connection.cursor()

        if using_postgres():

            cursor.execute(
                """
                SELECT
                    id,
                    username,
                    password
                FROM users
                WHERE username = %s
                """,
                (username,)
            )

        else:

            cursor.execute(
                """
                SELECT
                    id,
                    username,
                    password
                FROM users
                WHERE username = ?
                """,
                (username,)
            )

        user_data = cursor.fetchone()

        cursor.close()
        connection.close()

        if user_data:

            user_id = user_data[0]
            stored_username = user_data[1]
            stored_password = user_data[2]

            if check_password_hash(
                stored_password,
                password
            ):

                user = User(
                    user_id,
                    stored_username
                )

                login_user(user)

                return redirect(
                    url_for("home")
                )

        error = (
            "Incorrect username or password."
        )

    return render_template(
        "login.html",
        error=error
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
@login_required
def logout():

    logout_user()

    return redirect(
        url_for("login")
    )


# =========================================================
# HOME
# =========================================================

@app.route("/")
@login_required
def home():

    return render_template(
        "index.html",
        username=current_user.username,
        user_id=current_user.id
    )


# =========================================================
# CHAT
# =========================================================

@app.route(
    "/chat",
    methods=["POST"]
)
@login_required
@limiter.limit("20 per minute")
def chat():

    if not validate_csrf():

        return jsonify({
            "error": "Invalid security token."
        }), 400

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "error": "Invalid request."
        }), 400

    message = data.get(
        "message",
        ""
    ).strip()

    if not message:

        return jsonify({
            "error": "Message is empty."
        }), 400

    if len(message) > 10000:

        return jsonify({
            "error": (
                "Message is too long. "
                "Maximum is 10,000 characters."
            )
        }), 400

    try:

        response = client.chat.completions.create(

            model="openai/gpt-4o-mini",

            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful, friendly "
                        "AI assistant."
                    )
                },
                {
                    "role": "user",
                    "content": message
                }
            ]
        )

        reply = (
            response.choices[0]
            .message
            .content
        )

        if not reply:

            reply = (
                "I couldn't generate a response."
            )

        connection = get_db()
        cursor = connection.cursor()

        if using_postgres():

            cursor.execute(
                """
                INSERT INTO chats
                (
                    user_id,
                    message,
                    response,
                    timestamp
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    current_user.id,
                    message,
                    reply,
                    datetime.utcnow().isoformat()
                )
            )

        else:

            cursor.execute(
                """
                INSERT INTO chats
                (
                    user_id,
                    message,
                    response,
                    timestamp
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    current_user.id,
                    message,
                    reply,
                    datetime.utcnow().isoformat()
                )
            )

        connection.commit()

        cursor.close()
        connection.close()

        return jsonify({
            "reply": reply
        })

    except Exception as error:

        print(
            "AI ERROR:",
            error
        )

        return jsonify({
            "error": (
                "The AI request failed. "
                "Please try again."
            )
        }), 500


# =========================================================
# CHAT HISTORY
# =========================================================

@app.route("/history")
@login_required
def history():

    connection = get_db()
    cursor = connection.cursor()

    if using_postgres():

        cursor.execute(
            """
            SELECT
                message,
                response,
                timestamp
            FROM chats
            WHERE user_id = %s
            ORDER BY id ASC
            """,
            (current_user.id,)
        )

    else:

        cursor.execute(
            """
            SELECT
                message,
                response,
                timestamp
            FROM chats
            WHERE user_id = ?
            ORDER BY id ASC
            """,
            (current_user.id,)
        )

    chats = cursor.fetchall()

    cursor.close()
    connection.close()

    history_data = []

    for chat in chats:

        history_data.append({
            "message": chat[0],
            "response": chat[1],
            "timestamp": chat[2]
        })

    return jsonify(history_data)


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():

    return jsonify({
        "status": "ok"
    })


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(429)
def rate_limit_error(error):

    return jsonify({
        "error": (
            "Too many requests. "
            "Please try again later."
        )
    }), 429


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

init_database()


# =========================================================
# LOCAL DEVELOPMENT
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    debug = (
        os.environ.get(
            "FLASK_DEBUG",
            "false"
        ).lower()
        == "true"
    )

    print()
    print("===================================")
    print("          SLOPBOT IS RUNNING")
    print("===================================")
    print()
    print(
        f"http://127.0.0.1:{port}"
    )
    print()

    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug
    )