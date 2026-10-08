import os
import sqlite3
from datetime import datetime

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from openai import OpenAI


# =========================================================
# SETUP
# =========================================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "change-this-secret-key"
)

DATABASE = "chatbot.db"


# =========================================================
# AI CLIENT
# =========================================================

client = OpenAI(
    api_key=os.environ["HACKCLUB_API_KEY"],
    base_url="https://ai.hackclub.com/proxy/v1"
)


# =========================================================
# LOGIN SYSTEM
# =========================================================

login_manager = LoginManager()

login_manager.init_app(app)

# Anyone trying to access a protected page gets sent here
login_manager.login_view = "login"


class User(UserMixin):

    def __init__(self, user_id, username):

        self.id = user_id
        self.username = username


@login_manager.user_loader
def load_user(user_id):

    connection = sqlite3.connect(DATABASE)

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id, username
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    )

    user = cursor.fetchone()

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

def init_database():

    connection = sqlite3.connect(DATABASE)

    cursor = connection.cursor()

    # Users
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

    # Chat messages
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

        )
        """
    )

    connection.commit()

    connection.close()


# =========================================================
# SIGNUP
# =========================================================

@app.route("/signup", methods=["GET", "POST"])
def signup():

    # Already logged in
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        # Validation
        if not username or not password:

            return "Username and password are required."

        if len(username) < 3:

            return "Username must be at least 3 characters."

        if len(password) < 6:

            return "Password must be at least 6 characters."

        # Hash password
        hashed_password = generate_password_hash(
            password
        )

        connection = sqlite3.connect(DATABASE)

        cursor = connection.cursor()

        try:

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
                    datetime.now().isoformat()
                )
            )

            connection.commit()

            user_id = cursor.lastrowid

        except sqlite3.IntegrityError:

            connection.close()

            return "That username already exists."

        connection.close()

        # Automatically log user in
        user = User(
            user_id,
            username
        )

        login_user(user)

        return redirect(url_for("home"))

    return render_template("signup.html")


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        connection = sqlite3.connect(DATABASE)

        cursor = connection.cursor()

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

        connection.close()

        if user_data:

            user_id = user_data[0]

            stored_username = user_data[1]

            stored_password = user_data[2]

            # Check password
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

        return "Invalid username or password."

    return render_template("login.html")


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
# CHATBOT HOME
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
# SEND MESSAGE
# =========================================================

@app.route("/chat", methods=["POST"])
@login_required
def chat():

    data = request.get_json()

    message = data.get(
        "message",
        ""
    ).strip()

    if not message:

        return jsonify({
            "error": "Message is empty."
        }), 400

    try:

        # Ask AI
        response = client.chat.completions.create(

            model="openai/gpt-4o-mini",

            messages=[
                {
                    "role": "system",
                    "content":
                    "You are a helpful, friendly AI assistant."
                },
                {
                    "role": "user",
                    "content": message
                }
            ]
        )

        reply = response.choices[0].message.content

        # =================================================
        # SAVE CHAT
        # =================================================

        connection = sqlite3.connect(DATABASE)

        cursor = connection.cursor()

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
                datetime.now().isoformat()
            )
        )

        connection.commit()

        connection.close()

        return jsonify({
            "reply": reply
        })

    except Exception as error:

        print("AI ERROR:", error)

        return jsonify({
            "error": "The AI request failed."
        }), 500


# =========================================================
# CHAT HISTORY
# =========================================================

@app.route("/history")
@login_required
def history():

    connection = sqlite3.connect(DATABASE)

    cursor = connection.cursor()

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
# START SERVER
# =========================================================

if __name__ == "__main__":

    init_database()

    print()
    print("===================================")
    print("        MY BOT IS RUNNING")
    print("===================================")
    print()
    print("Open:")
    print("http://127.0.0.1:5000")
    print()
    print("Signup:")
    print("http://127.0.0.1:5000/signup")
    print()
    print("Login:")
    print("http://127.0.0.1:5000/login")
    print()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )