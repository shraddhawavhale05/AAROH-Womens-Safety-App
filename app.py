from flask import Flask, request, jsonify, render_template
import sqlite3

app = Flask(__name__)

DB_NAME = "aaroh.db"

# Create database and table
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# Home route
@app.route("/")
def home():
    return render_template("index.html")


# Add emergency contact
@app.route("/contacts", methods=["POST"])
def add_contact():
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
        "INSERT INTO contacts (name, phone) VALUES (?, ?)",
        (name, phone)
    )

    conn.commit()
    conn.close()

    return jsonify({
        "message": "Emergency contact saved successfully!"
    }), 201


# View emergency contacts
@app.route("/contacts", methods=["GET"])
def get_contacts():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, phone FROM contacts")
    contacts = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return jsonify(contacts)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)