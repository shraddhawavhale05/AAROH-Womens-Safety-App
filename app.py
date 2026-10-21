from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import requests
from functools import wraps

app = Flask(__name__)
app.secret_key = "aaroh-local-development-key"

DB_NAME = "aaroh.db"
# Exotel SMS settings
EXOTEL_API_KEY = os.environ.get("EXOTEL_API_KEY")
EXOTEL_API_TOKEN = os.environ.get("EXOTEL_API_TOKEN")
EXOTEL_ACCOUNT_SID = os.environ.get("EXOTEL_ACCOUNT_SID")
EXOTEL_SENDER_ID = os.environ.get("EXOTEL_SENDER_ID")

EXOTEL_SUBDOMAIN = os.environ.get(
    "EXOTEL_SUBDOMAIN",
    "@api.in.exotel.com"
)

def send_emergency_sms(phone, message):
    if not all([
        EXOTEL_API_KEY,
        EXOTEL_API_TOKEN,
        EXOTEL_ACCOUNT_SID,
        EXOTEL_SENDER_ID
    ]):
        return False, "SMS gateway is not configured."

    url = (
        f"https://{EXOTEL_API_KEY}:{EXOTEL_API_TOKEN}"
        f"{EXOTEL_SUBDOMAIN}/v1/Accounts/"
        f"{EXOTEL_ACCOUNT_SID}/Sms/send"
    )

    payload = {
        "From": EXOTEL_SENDER_ID,
        "To": phone,
        "Body": message
    }

    try:
        response = requests.post(
            url,
            data=payload,
            timeout=15
        )

        if response.status_code in (200, 201):
            return True, "SMS request accepted."

        app.logger.error(
            "SMS provider returned HTTP %s",
            response.status_code
        )
        return False, "SMS provider rejected the request."

    except requests.RequestException:
        app.logger.exception("SMS provider request failed")
        return False, "Could not reach SMS provider."


# Create database and contacts table
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            user_id INTEGER
        )
    """)

    cursor.execute("PRAGMA table_info(contacts)")
    columns = [column[1] for column in cursor.fetchall()]

    if "user_id" not in columns:
        cursor.execute("ALTER TABLE contacts ADD COLUMN user_id INTEGER")

    conn.commit()
    conn.close()

# Sign Up route
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            return render_template(
                "signup.html",
                error="Please fill in all fields."
            )

        if len(password) < 8:
            return render_template(
                "signup.html",
                error="Password must be at least 8 characters."
            )

        hashed_password = generate_password_hash(password)

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (name, email, hashed_password)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return render_template(
                "signup.html",
                error="This email is already registered."
            )

        conn.close()
        return redirect(url_for("login"))

    return render_template("signup.html")

# Home route
# Create users table
def init_users_table():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# Home route
@app.route("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template("index.html")
# Login route
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, name, password FROM users WHERE email = ?",
            (email,)
        )
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session["user_id"] = user[0]
            session["user_name"] = user[1]
            return redirect(url_for("home"))

        return render_template(
            "login.html",
            error="Invalid email or password."
        )

    return render_template("login.html")
    # Logout route
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# Add emergency contact
@app.route("/contacts", methods=["POST"])
def add_contact():
    if "user_id" not in session:
        return jsonify({"error": "Please log in first"}), 401

    data = request.get_json(silent=True) or {}

    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()

    if not name or not phone:
        return jsonify({
            "error": "Name and phone are required"
        }), 400

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO contacts (name, phone, user_id) VALUES (?, ?, ?)",
        (name, phone, session["user_id"])
    )

    conn.commit()
    conn.close()

    return jsonify({
        "message": "Emergency contact saved successfully!"
    }), 201

# View emergency contacts
@app.route("/contacts", methods=["GET"])
def get_contacts():
    if "user_id" not in session:
        return jsonify({"error": "Please log in first"}), 401

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, name, phone FROM contacts WHERE user_id = ?",
        (session["user_id"],)
    )

    contacts = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return jsonify(contacts)
# Send SOS emergency SMS
@app.route("/send-sos", methods=["POST"])
def send_sos():
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "Please login first."
        }), 401

    data = request.get_json(silent=True) or {}

    latitude = data.get("latitude")
    longitude = data.get("longitude")

    if latitude is None or longitude is None:
        return jsonify({
            "success": False,
            "message": "Location not available."
        }), 400

    try:
        latitude = float(latitude)
        longitude = float(longitude)

        if not (-90 <= latitude <= 90 and
                -180 <= longitude <= 180):
            raise ValueError()

    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "message": "Invalid location."
        }), 400

    maps_link = (
        f"https://www.google.com/maps?q={latitude},{longitude}"
    )

    message = (
        "AAROH EMERGENCY ALERT! I need help. "
        f"My current location: {maps_link}"
    )

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name, phone FROM contacts WHERE user_id = ?",
        (session["user_id"],)
    )

    contacts = cursor.fetchall()
    conn.close()

    if not contacts:
        return jsonify({
            "success": False,
            "message": "Please add emergency contacts first."
        }), 400

    results = []

    for name, phone in contacts:
        success, status = send_emergency_sms(phone, message)

        results.append({
            "name": name,
            "success": success,
            "status": status
        })

    sent = sum(1 for item in results if item["success"])

    return jsonify({
        "success": sent > 0,
        "message": f"SMS accepted for {sent} of {len(contacts)} contacts.",
        "results": results
    })

init_db()
init_users_table()

if __name__ == "__main__":
    init_db()
    init_users_table()
    app.run(host="0.0.0.0", port=5000, debug=True)
