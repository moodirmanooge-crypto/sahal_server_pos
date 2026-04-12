from flask import (
    Flask,
    render_template,
    request,
    redirect,
    jsonify,
    session
)

from flask_socketio import SocketIO, emit, join_room
from werkzeug.utils import secure_filename

import sqlite3
import os
import qrcode
import socket
import random
import json

from zoneinfo import ZoneInfo
from google.cloud import firestore

from datetime import datetime, timedelta, timezone

# 🔥 FIREBASE
import firebase_admin
from firebase_admin import credentials, firestore

DB_PATH = os.environ.get("DB_PATH", "database.db")

# =========================
# 🔥 FIREBASE CONFIG
# =========================
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()


# =========================
# 🔥 FIREBASE HELPERS
# =========================
def save_student_firestore(data):
    db.collection("students").add(data)


def get_students_firestore():
    docs = db.collection("students").stream()
    return [doc.to_dict() for doc in docs]


def save_restaurant_firestore(data):
    db.collection("restaurants").add(data)


def get_restaurants_firestore():
    docs = db.collection("restaurants").stream()
    return [doc.to_dict() for doc in docs]


def save_supermarket_firestore(data):
    db.collection("supermarkets").add(data)


def get_supermarkets_firestore():
    docs = db.collection("supermarkets").stream()
    return [doc.to_dict() for doc in docs]


def save_order_firestore(data):
    db.collection("orders").add(data)


def get_orders_firestore():
    docs = db.collection("orders").stream()
    return [doc.to_dict() for doc in docs]

# =========================
# 🔐 SYSTEM PASSWORDS FROM FIREBASE
# =========================
def get_system_passwords():
    try:
        doc_ref = db.collection("evote").document("system")
        doc = doc_ref.get()

        if doc.exists:
            return doc.to_dict()

        # haddii document-ka uusan jirin
        return {
            "admin_password": "6993",
            "register_password": "6993",
            "student_password": "9751",
            "screen_password": "7890",
            "candidate_password": "0482",
            "evote_admin_password": "1851"
        }

    except Exception as e:
        print("Firebase password error:", e)

        # fallback haddii firebase cilad yeesho
        return {
            "admin_password": "6993",
            "register_password": "6993",
            "student_password": "9751",
            "screen_password": "7890",
            "candidate_password": "0482",
            "evote_admin_password": "1851"
        }

# =========================
# 🇸🇴 SOMALIA TIME
# =========================
def somalia_time():
    return datetime.now(timezone(timedelta(hours=3)))


# =========================
# ⏰ AUTO ROUND PROGRESS
# =========================
def auto_round_progress():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    try:
        c.execute("""
            SELECT current_round
            FROM election_settings
            WHERE id=1
        """)
        row = c.fetchone()
        current_round = row[0] if row else 1

        c.execute("""
            SELECT end_time
            FROM election_timer
            WHERE id=1
        """)
        timer_row = c.fetchone()

        if timer_row and timer_row[0]:
            end_time = datetime.strptime(
                timer_row[0],
                "%Y-%m-%d %H:%M:%S"
            )

            now = somalia_time().replace(tzinfo=None)

            # haddii waqtigu dhamaaday + 20 min wait
            if now >= end_time + timedelta(minutes=20):
                next_round_no = current_round + 1

                # max 3 rounds
                if next_round_no <= 3:
                    c.execute("""
                        UPDATE election_settings
                        SET current_round=?
                        WHERE id=1
                    """, (next_round_no,))

                    new_end = now + timedelta(minutes=60)

                    c.execute("""
                        UPDATE election_timer
                        SET round_time_minutes=60,
                            end_time=?
                        WHERE id=1
                    """, (
                        new_end.strftime("%Y-%m-%d %H:%M:%S"),
                    ))

                    conn.commit()

                    print(f"Auto moved to Round {next_round_no} ✅")

    except Exception as e:
        print("Auto Round Error:", e)

    conn.close()


# =========================
# ⏰ AUTO CHECK EXPIRY
# =========================
def auto_check_expiry(rid):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    try:
        c.execute("SELECT expiry, active FROM restaurants WHERE id=?", (rid,))
        row = c.fetchone()

        if row and row[0]:
            expiry_date = row[0]

            expiry = datetime.strptime(expiry_date, "%Y-%m-%d")

            if datetime.now() >= expiry:
                c.execute("""
                    UPDATE restaurants
                    SET active=0
                    WHERE id=?
                """, (rid,))
                conn.commit()

    except Exception as e:
        print("Auto Expiry Error:", e)

    conn.close()


# =========================
# 🔢 EVOTE CODE GENERATOR
# =========================
def generate_vote_code():
    return str(random.randint(100000, 999999))


# =========================
# 🚀 APP START
# =========================
app = Flask(__name__)
app.secret_key = "secret123"

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="eventlet"
)

UPLOAD_FOLDER = "static/uploads"
QR_FOLDER = "static/qr"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)


# =========================
# 🎤 WEBRTC SIGNALING EVENTS
# =========================
@socketio.on("voice_call")
def voice_call(data):
    emit("incoming_call", data, broadcast=True)


@socketio.on("offer")
def handle_offer(data):
    emit("offer", data, broadcast=True)


@socketio.on("answer")
def handle_answer(data):
    emit("answer", data, broadcast=True)


@socketio.on("ice_candidate")
def handle_ice(data):
    emit("ice_candidate", data, broadcast=True)


# =========================
# 🏠 SOCKET ROOM JOIN
# =========================
@socketio.on("join_customer_room")
def join_customer(data):
    room = f"{data['rid']}_{data['table']}"
    join_room(room)
    emit("joined_room", {"room": room})


@socketio.on("join_kitchen_room")
def join_kitchen(data):
    room = f"kitchen_{data['rid']}"
    join_room(room)
    emit("joined_kitchen", {"room": room})


# =========================
# 🌐 GET SERVER IP
# =========================
def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()

    return ip


SERVER_IP = get_ip()


# =========================
# DATABASE
# =========================
def init_db():
    print("INIT DB RUNNING...")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # =========================
    # 🍽️ RESTAURANTS
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS restaurants(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone TEXT,
        username TEXT,
        password TEXT,
        price INTEGER,
        expiry TEXT,
        active INTEGER,
        payment_number TEXT,
        kitchen_password TEXT
    )
    """)

    # =========================
    # ⚙️ SYSTEM SETTINGS
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS settings(
        id INTEGER PRIMARY KEY,
        admin_password TEXT,
        register_password TEXT
    )
    """)

    c.execute("SELECT id FROM settings WHERE id=1")
    existing_settings = c.fetchone()

    if not existing_settings:
        c.execute("""
            INSERT INTO settings
            (id, admin_password, register_password)
            VALUES (1, '8880', '8880')
        """)

    # =========================
    # 🔐 EVOTE PASSWORD SETTINGS
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS evote_passwords(
        id INTEGER PRIMARY KEY,
        student_password TEXT,
        candidate_password TEXT,
        evote_admin_password TEXT
    )
    """)

    c.execute("SELECT id FROM evote_passwords WHERE id=1")
    existing_passwords = c.fetchone()

    if not existing_passwords:
        c.execute("""
            INSERT INTO evote_passwords
            (id, student_password, candidate_password, evote_admin_password)
            VALUES (1, '12345', '12345', 'admin123')
        """)

    # =========================
    # 🎓 STUDENTS
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS students(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT UNIQUE,
        full_name TEXT,
        class_name TEXT,
        semester TEXT,
        vote_code TEXT UNIQUE,
        has_voted_round1 INTEGER DEFAULT 0,
        has_voted_round2 INTEGER DEFAULT 0,
        has_voted_round3 INTEGER DEFAULT 0
    )
    """)

    # =========================
    # 🧑‍💼 CANDIDATES
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS candidates(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT,
        department TEXT,
        round INTEGER DEFAULT 1,
        votes INTEGER DEFAULT 0,
        percentage REAL DEFAULT 0,
        image TEXT
    )
    """)

    # =========================
    # 🗳️ ROUND SETTINGS
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS election_settings(
        id INTEGER PRIMARY KEY,
        current_round INTEGER DEFAULT 1,
        round_end_time TEXT
    )
    """)

    c.execute("SELECT id FROM election_settings WHERE id=1")
    existing_round = c.fetchone()

    if not existing_round:
        c.execute("""
            INSERT INTO election_settings
            (id, current_round, round_end_time)
            VALUES (1, 1, '')
        """)

    # =========================
    # ⏰ ELECTION TIMER
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS election_timer(
        id INTEGER PRIMARY KEY,
        round_time_minutes INTEGER DEFAULT 60,
        end_time TEXT
    )
    """)

    c.execute("SELECT id FROM election_timer WHERE id=1")
    existing_timer = c.fetchone()

    if not existing_timer:
        c.execute("""
            INSERT INTO election_timer
            (id, round_time_minutes, end_time)
            VALUES (1, 60, '')
        """)

    # =========================
    # ⏰ EVOTE TIMER
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS evote_timer(
        id INTEGER PRIMARY KEY,
        minutes INTEGER,
        end_time TEXT
    )
    """)

    c.execute("SELECT id FROM evote_timer WHERE id=1")
    existing_evote_timer = c.fetchone()

    if not existing_evote_timer:
        c.execute("""
            INSERT INTO evote_timer
            (id, minutes, end_time)
            VALUES (1, 60, '')
        """)

    # =========================
    # 🛒 SUPERMARKETS
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS supermarkets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        username TEXT,
        password TEXT,
        price INTEGER,
        expiry TEXT,
        active INTEGER DEFAULT 1
    )
    """)

    # =========================
    # 🛒 SUPERMARKET PRODUCTS
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS supermarket_products(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        barcode TEXT UNIQUE,
        product_name TEXT,
        price REAL
    )
    """)

    # =========================
    # 🧾 SUPERMARKET ORDERS
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS supermarket_orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receipt_no TEXT,
        total REAL,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()

    print("DATABASE READY ✅")


@app.route("/")
def home():
    return render_template("home.html")

# =========================
# 🗳 CANDIDATE LOGIN
# =========================
@app.route("/candidate_login", methods=["GET", "POST"])
def candidate_login():
    if request.method == "POST":
        password = request.form["password"]

        # 🔥 get password from Firebase
        passwords = get_system_passwords()
        real_pass = passwords.get("candidate_password")

        if password == real_pass:
            session["candidate_ok"] = True
            return redirect("/register_candidate")

        return "Wrong password ❌"

    return render_template(
        "password_login.html",
        title="Candidate Register"
    )

@app.route("/evote_admin_login", methods=["GET", "POST"])
def evote_admin_login():
    try:
        if request.method == "POST":
            password = request.form["password"]

            passwords = get_system_passwords()
            real_password = passwords.get("evote_admin_password")

            if password == real_password:
                session["evote_admin_ok"] = True
                return redirect("/evote_admin")

            return "Wrong password ❌"

        return render_template(
            "password_login.html",
            title="eVote Admin"
        )

    except Exception as e:
        return f"Login Error ❌ {str(e)}"

@app.route("/evote_admin")
def evote_admin():
    try:
        if not session.get("evote_admin_ok"):
            return redirect("/evote_admin_login")

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS evote_timer (
                id INTEGER PRIMARY KEY,
                minutes INTEGER,
                end_time TEXT
            )
        """)

        c.execute("""
            SELECT minutes, end_time
            FROM evote_timer
            WHERE id=1
        """)
        timer = c.fetchone()

        conn.close()

        current_timer = timer[0] if timer else 0
        end_time = timer[1] if timer else "Not Set"

        return render_template(
            "evote_admin.html",
            current_timer=current_timer,
            end_time=end_time
        )

    except Exception as e:
        return f"eVote Admin Error ❌ {str(e)}"


@app.route("/upload_ad", methods=["POST"])
def upload_ad():
    try:
        if not session.get("evote_admin_ok"):
            return redirect("/evote_admin_login")

        ad_file = request.files.get("ad_video")

        if not ad_file or ad_file.filename == "":
            return redirect("/evote_admin")

        folder = os.path.join("static", "ads")
        os.makedirs(folder, exist_ok=True)

        filepath = os.path.join(folder, "ad1.mp4")
        ad_file.save(filepath)

        return redirect("/evote_admin")

    except Exception as e:
        return f"Upload Error ❌ {str(e)}"


@app.route("/set_timer", methods=["POST"])
def set_timer():
    try:
        if not session.get("evote_admin_ok"):
            return redirect("/evote_admin_login")

        minutes = int(request.form["minutes"])
        end_time = datetime.now() + timedelta(minutes=minutes)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS evote_timer (
                id INTEGER PRIMARY KEY,
                minutes INTEGER,
                end_time TEXT
            )
        """)

        c.execute("""
            INSERT OR REPLACE INTO evote_timer
            (id, minutes, end_time)
            VALUES (1, ?, ?)
        """, (
            minutes,
            end_time.strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()
        conn.close()

        return redirect("/evote_admin")

    except Exception as e:
        return f"Timer Error ❌ {str(e)}"


@app.route("/get_evote_timer")
def get_evote_timer():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS evote_timer (
                id INTEGER PRIMARY KEY,
                minutes INTEGER,
                end_time TEXT
            )
        """)

        c.execute("""
            SELECT minutes, end_time
            FROM evote_timer
            WHERE id=1
        """)
        timer = c.fetchone()

        conn.close()

        if timer:
            return {
                "minutes": timer[0],
                "end_time": timer[1]
            }

        return {
            "minutes": 0,
            "end_time": None
        }

    except Exception as e:
        return {
            "error": str(e)
        }

# =========================
# 🎓 STUDENT LOGIN (OPEN ACCESS)
# =========================
@app.route("/student_login")
def student_login():
    return redirect("/register_student")


@app.route("/screen_login", methods=["GET", "POST"])
def screen_login():
    if request.method == "POST":
        password = request.form["password"]

        passwords = get_system_passwords()
        real_pass = passwords.get("screen_password")

        if password == real_pass:
            session["screen_access"] = True
            return redirect("/student_screen")

        return "Wrong password ❌"

    return render_template(
        "password_login.html",
        title="Student Screen"
    )


# =========================
# 🎓 FUTURE LEADER ACADEMY REGISTRATION
# =========================
@app.route("/register_student", methods=["GET", "POST"])
def register_student():

    if request.method == "POST":
        student_id = request.form["student_id"].strip()

        try:
            existing_student = db.collection("students").document(student_id).get()

            if existing_student.exists:
                return """
                <h2 style='text-align:center;color:red;'>
                    Student ID already exists ❌
                </h2>
                <div style='text-align:center; margin-top:20px;'>
                    <a href='/register_student'
                       style='padding:12px 20px;
                              background:#0a7cff;
                              color:white;
                              text-decoration:none;
                              border-radius:8px;'>
                       Try Another ID
                    </a>
                </div>
                """

            student_data = {
                "student_id": student_id,
                "full_name": request.form["full_name"],
                "phone_number": request.form["phone_number"],
                "department": request.form["department"],
                "student_class": request.form["student_class"],
                "payment_status": "paid",
                "created_at": datetime.now()
            }

            db.collection("students").document(student_id).set(student_data)

            return render_template(
                "register_student.html",
                student=student_data
            )

        except Exception as e:
            return f"Firebase Error ❌ {e}"

    return render_template("register_student.html")


# =========================
# 📋 STUDENT SCREEN
# =========================
@app.route("/student_screen", methods=["GET"])
def student_screen():
    if not session.get("screen_access"):
        return redirect("/screen_login")

    try:
        search_id = request.args.get("student_id", "").strip()
        students = []
        searched_student = None

        # 🔥 SEARCH SINGLE STUDENT
        if search_id:
            doc = db.collection("students").document(search_id).get()

            if doc.exists:
                searched_student = doc.to_dict()
                students.append(searched_student)

        else:
            # 🔥 GET ALL STUDENTS
            docs = db.collection("students").stream()

            for doc in docs:
                students.append(doc.to_dict())

        return render_template(
            "student_screen.html",
            students=students,
            searched_student=searched_student
        )

    except Exception as e:
        return f"Student Screen Error ❌ {e}"
    
    # =========================
# 🗑 DELETE STUDENT
# =========================
@app.route("/delete_student/<student_id>")
def delete_student(student_id):
    try:
        db.collection("students").document(student_id).delete()
        return redirect("/student_screen")
    except Exception as e:
        return f"Delete Error ❌ {e}"

@app.route("/register_candidate", methods=["GET", "POST"])
def register_candidate():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    if request.method == "POST":
        full_name = request.form["full_name"]
        department = request.form["department"]
        image = request.files["image"]

        filename = image.filename

        import os
        upload_path = os.path.join("static", "uploads")

        if not os.path.exists(upload_path):
            os.makedirs(upload_path)

        image.save(os.path.join(upload_path, filename))

        c.execute("""
            INSERT INTO candidates(full_name, department, image)
            VALUES (?, ?, ?)
        """, (full_name, department, filename))

        conn.commit()

    c.execute("SELECT * FROM candidates ORDER BY id DESC")
    candidates = c.fetchall()

    conn.close()

    return render_template(
        "register_candidate.html",
        candidates=candidates
    )

@app.route("/vote", methods=["GET", "POST"])
def vote():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    try:
        # current round
        c.execute("""
            SELECT current_round
            FROM election_settings
            WHERE id=1
        """)
        row = c.fetchone()
        current_round = row[0] if row else 1

        # submit vote
        if request.method == "POST":
            vote_code = request.form.get("student_id")
            candidate_id = request.form.get("candidate_id")

            if not vote_code or not candidate_id:
                conn.close()
                return "Missing vote code or candidate ❌"

            vote_column = f"has_voted_round{current_round}"

            # check student
            c.execute(f"""
                SELECT {vote_column}
                FROM students
                WHERE vote_code=?
            """, (vote_code,))
            student = c.fetchone()

            if not student:
                conn.close()
                return "Invalid vote code ❌"

            if student[0] == 1:
                conn.close()
                return "Already voted in this round ❌"

            # add vote
            c.execute("""
                UPDATE candidates
                SET votes = votes + 1
                WHERE id=?
            """, (candidate_id,))

            # mark student voted
            c.execute(f"""
                UPDATE students
                SET {vote_column}=1
                WHERE vote_code=?
            """, (vote_code,))

            conn.commit()

            return "Vote submitted successfully ✅"

        # get candidates
        c.execute("""
            SELECT id, full_name, department, image
            FROM candidates
            WHERE round=?
            ORDER BY votes DESC
        """, (current_round,))

        candidates = c.fetchall()
        conn.close()

        return render_template(
            "vote.html",
            candidates=candidates,
            current_round=current_round
        )

    except Exception as e:
        conn.close()
        return f"Vote Error ❌ {str(e)}"


@app.route("/admin_dashboard", methods=["GET", "POST"])
def admin_dashboard():

    # =========================
    # ⏰ AUTO ROUND CHECK
    # =========================
    auto_round_progress()

    # =========================
    # 🔐 EVOTE ADMIN PROTECTION
    # =========================
    if not session.get("evote_admin_ok"):
        return redirect("/evote_admin_login")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    try:
        # =========================
        # FIX: CREATE TIMER TABLE
        # =========================
        c.execute("""
            CREATE TABLE IF NOT EXISTS election_timer(
                id INTEGER PRIMARY KEY,
                round_time_minutes INTEGER DEFAULT 60,
                end_time TEXT
            )
        """)

        # =========================
        # DEFAULT TIMER ROW
        # =========================
        c.execute("SELECT * FROM election_timer WHERE id=1")
        if not c.fetchone():
            c.execute("""
                INSERT INTO election_timer
                (id, round_time_minutes, end_time)
                VALUES (1, 60, '')
            """)
            conn.commit()

        # =========================
        # DEFAULT ROUND SETTINGS
        # =========================
        c.execute("SELECT * FROM election_settings WHERE id=1")
        if not c.fetchone():
            c.execute("""
                INSERT INTO election_settings
                (id, current_round, round_end_time)
                VALUES (1, 1, '')
            """)
            conn.commit()

        # =========================
        # HANDLE FORM ACTIONS
        # =========================
        if request.method == "POST":
            action = request.form.get("action")

            # =========================
            # MOVE NEXT ROUND
            # =========================
            if action == "next_round":
                c.execute("""
                    UPDATE election_settings
                    SET current_round = current_round + 1
                    WHERE id=1
                """)

            # =========================
            # SET TIMER
            # =========================
            elif action == "set_timer":
                minutes = int(request.form.get("minutes", 60))

                end_time = somalia_time() + timedelta(minutes=minutes)

                c.execute("""
                    UPDATE election_timer
                    SET round_time_minutes=?,
                        end_time=?
                    WHERE id=1
                """, (
                    minutes,
                    end_time.strftime("%Y-%m-%d %H:%M:%S")
                ))

            conn.commit()

        # =========================
        # GET CURRENT ROUND
        # =========================
        c.execute("""
            SELECT current_round
            FROM election_settings
            WHERE id=1
        """)
        row = c.fetchone()
        current_round = row[0] if row else 1

        # =========================
        # GET RESULTS
        # =========================
        c.execute("""
            SELECT *
            FROM candidates
            WHERE round=?
            ORDER BY votes DESC
        """, (current_round,))
        results = c.fetchall()

        # =========================
        # GET TIMER
        # =========================
        c.execute("""
            SELECT round_time_minutes, end_time
            FROM election_timer
            WHERE id=1
        """)
        timer = c.fetchone()

        if not timer:
            timer = (60, "Not Set")

        conn.close()

        return render_template(
            "admin_dashboard.html",
            current_round=current_round,
            results=results,
            timer=timer
        )

    except Exception as e:
        conn.close()
        return f"Admin Dashboard Error ❌ {str(e)}"

@app.route("/submit_review/<rid>", methods=["POST"])
def submit_review(rid):
    try:
        rating = int(request.form.get("rating", 0))
        comment = request.form.get("comment", "").strip()

        if rating < 1 or rating > 5:
            return "Invalid rating ❌"

        restaurant_ref = db.collection("restaurants").document(rid)
        restaurant_doc = restaurant_ref.get()

        if not restaurant_doc.exists:
            return "Restaurant not found ❌"

        restaurant_name = restaurant_doc.to_dict().get("name", "Unknown")

        review_data = {
            "restaurant_id": rid,
            "restaurant_name": restaurant_name,
            "rating": rating,
            "comment": comment,
            "created_at": datetime.now()
        }

        # 🔥 reviews collection auto create
        db.collection("reviews").add(review_data)

        return redirect(f"/table/{rid}/1")

    except Exception as e:
        return f"Review Error ❌ {str(e)}"

@app.route("/submit_order", methods=["POST"])
def submit_order():
    try:
        rid = request.form.get("rid")
        table = request.form.get("table")
        item_name = request.form.get("item_name")
        price = request.form.get("price")

        db.collection("orders").add({
            "restaurant_id": rid,
            "table_no": table,
            "item_name": item_name,
            "price": price,
            "status": "pending"
        })

        return redirect(f"/menu/{rid}/{table}")

    except Exception as e:
        return f"Order Error ❌ {str(e)}"

# =========================
# 🎥 UPLOAD ADS ROUTE
# =========================
@app.route('/upload_break_ad_evote', methods=['POST'])
def upload_break_ad_evote():
    if 'ad_video' not in request.files:
        return redirect('/evote_admin')

    file = request.files['ad_video']

    if file.filename == '':
        return redirect('/evote_admin')

    filename = secure_filename(file.filename)
    filepath = os.path.join('static/break_ads', filename)

    os.makedirs('static/break_ads', exist_ok=True)

    file.save(filepath)

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS break_ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT
        )
    """)

    c.execute("DELETE FROM break_ads")
    c.execute("INSERT INTO break_ads (filename) VALUES (?)", (filename,))

    conn.commit()
    conn.close()

    return redirect('/evote_admin')

@app.route("/next_round", methods=["POST"])
def next_round():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT current_round FROM election_settings WHERE id=1")
    row = c.fetchone()

    current_round = row[0] if row else 1
    next_round_no = current_round + 1

    if current_round == 1:
        limit_num = 6
    elif current_round == 2:
        limit_num = 3
    else:
        conn.close()
        return "Final round reached ✅"

    c.execute("""
        SELECT id
        FROM candidates
        WHERE round=?
        ORDER BY votes DESC
        LIMIT ?
    """, (current_round, limit_num))

    winners = c.fetchall()

    for w in winners:
        c.execute("""
            UPDATE candidates
            SET round=?, votes=0
            WHERE id=?
        """, (next_round_no, w[0]))

    c.execute("""
        INSERT OR REPLACE INTO election_settings
        (id, current_round)
        VALUES (1, ?)
    """, (next_round_no,))

    conn.commit()
    conn.close()

    return redirect("/admin_dashboard")


@app.route("/live_results")
def live_results():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    try:
        # =========================
        # CURRENT ROUND
        # =========================
        c.execute("""
            SELECT current_round
            FROM election_settings
            WHERE id=1
        """)
        row = c.fetchone()
        current_round = row[0] if row else 1

        # =========================
        # TIMER INFO
        # =========================
        c.execute("""
            SELECT round_time_minutes, end_time
            FROM election_timer
            WHERE id=1
        """)
        timer = c.fetchone()

        remaining_seconds = 0
        break_mode = False

        if timer and timer[1]:
            end_time_obj = datetime.strptime(
                timer[1],
                "%Y-%m-%d %H:%M:%S"
            )

            now = datetime.now()
            diff = (end_time_obj - now).total_seconds()

            # =========================
            # TIMER RUNNING
            # =========================
            if diff > 0:
                remaining_seconds = int(diff)

            else:
                # =========================
                # 1 MIN BREAK ADS
                # =========================
                break_end = end_time_obj + timedelta(minutes=1)
                break_diff = (break_end - now).total_seconds()

                if break_diff > 0:
                    break_mode = True
                    remaining_seconds = int(break_diff)

                else:
                    # =========================
                    # AUTO MOVE NEXT ROUND
                    # =========================
                    c.execute("""
                        UPDATE election_settings
                        SET current_round = current_round + 1
                        WHERE id=1
                    """)

                    # reset next round timer to 60 mins
                    next_end = now + timedelta(minutes=60)

                    c.execute("""
                        UPDATE election_timer
                        SET round_time_minutes=?,
                            end_time=?
                        WHERE id=1
                    """, (
                        60,
                        next_end.strftime("%Y-%m-%d %H:%M:%S")
                    ))

                    conn.commit()

                    current_round += 1
                    remaining_seconds = 3600
                    break_mode = False

        # =========================
        # GET CANDIDATES
        # =========================
        c.execute("""
            SELECT id, full_name, department, round,
                   votes, percentage, image
            FROM candidates
            WHERE round=?
            ORDER BY votes DESC
        """, (current_round,))

        candidates = c.fetchall()

        # =========================
        # CUSTOM PERCENTAGE
        # 1 VOTE = 0.5%
        # =========================
        updated_candidates = []

        for candidate in candidates:
            votes = candidate[4]
            percent = round(votes * 0.5, 1)

            updated_candidates.append((
                candidate[0],
                candidate[1],
                candidate[2],
                candidate[3],
                votes,
                percent,
                candidate[6]
            ))

        conn.close()

        return render_template(
            "live_results.html",
            candidates=updated_candidates,
            current_round=current_round,
            remaining_seconds=remaining_seconds,
            break_mode=break_mode
        )

    except Exception as e:
        conn.close()
        return f"Live Results Error ❌ {str(e)}"
   

@app.route("/index")
def index():
    return render_template("index.html")

# =========================
# 🔐 SYSTEM PASSWORDS
# =========================
ADMIN_PASSWORD = "8880"
REGISTER_PASSWORD = "8880"


# =========================
# 🔐 ADMIN ROUTE
# =========================
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if session.get("admin_ok"):
        restaurants = get_restaurants_firestore()
        supermarkets = get_supermarkets_firestore()
        orders = get_orders_firestore()

        total = len(orders)

        # 🔥 TOP 3 REVIEWS
        top_reviews = []

        try:
            review_docs = db.collection("reviews").stream()
            review_count_map = {}

            for doc in review_docs:
                item = doc.to_dict()
                rid = item.get("restaurant_id")

                if rid:
                    review_count_map[rid] = review_count_map.get(rid, 0) + 1

            for r in restaurants:
                rid = r.get("id")
                r["review_count"] = review_count_map.get(rid, 0)

            top_reviews = sorted(
                restaurants,
                key=lambda x: x.get("review_count", 0),
                reverse=True
            )[:3]

        except Exception as e:
            print("Review Error:", e)

        return render_template(
            "admin.html",
            restaurants=restaurants,
            supermarkets=supermarkets,
            orders=orders,
            total=total,
            top_reviews=top_reviews
        )

    if request.method == "POST":
        passwords = get_system_passwords()
        real_pass = passwords.get("admin_password")

        if request.form.get("password") != real_pass:
            return render_template(
                "admin_login.html",
                error="Wrong password"
            )

        session["admin_ok"] = True
        return redirect("/admin")

    return render_template("admin_login.html")


# =========================
# 🔓 LOGOUT ADMIN
# =========================
@app.route("/logout_admin")
def logout_admin():
    session.pop("admin_ok", None)
    session.pop("register_ok", None)
    return redirect("/admin")


# =========================
# 🔓 LOGOUT REGISTER
# =========================
@app.route("/logout_register")
def logout_register():
    session.pop("register_ok", None)
    return redirect("/register")


# =========================
# 🔄 CHANGE PASSWORDS
# =========================

# =========================
# 🔐 CHANGE SYSTEM PASSWORDS
# =========================
@app.route("/change_passwords", methods=["POST"])
def change_passwords():
    new_admin = request.form.get("admin_pass")
    new_register = request.form.get("register_pass")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
        UPDATE settings
        SET admin_password=?,
            register_password=?
        WHERE id=1
    """, (new_admin, new_register))

    conn.commit()
    conn.close()

    return redirect("/admin")


# =========================
# 🗳️ CHANGE EVOTE PASSWORDS
# =========================
@app.route("/change_evote_passwords", methods=["POST"])
def change_evote_passwords():
    # =========================
    # 🔐 GET FORM VALUES
    # =========================
    student_pass = request.form.get("student_password")
    screen_pass = request.form.get("screen_password")
    candidate_pass = request.form.get("candidate_password")
    admin_pass = request.form.get("evote_admin_password")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # =========================
    # 🔧 ENSURE TABLE EXISTS
    # =========================
    c.execute("""
        CREATE TABLE IF NOT EXISTS evote_passwords(
            id INTEGER PRIMARY KEY,
            student_password TEXT,
            screen_password TEXT,
            candidate_password TEXT,
            evote_admin_password TEXT
        )
    """)

    # =========================
    # ➕ ADD MISSING COLUMN SAFELY
    # =========================
    try:
        c.execute("ALTER TABLE evote_passwords ADD COLUMN screen_password TEXT")
    except:
        pass

    # =========================
    # 🔍 CHECK EXISTING ROW
    # =========================
    c.execute("SELECT id FROM evote_passwords WHERE id=1")
    row = c.fetchone()

    # =========================
    # 🔄 UPDATE OR INSERT
    # =========================
    if row:
        c.execute("""
            UPDATE evote_passwords
            SET student_password=?,
                screen_password=?,
                candidate_password=?,
                evote_admin_password=?
            WHERE id=1
        """, (
            student_pass,
            screen_pass,
            candidate_pass,
            admin_pass
        ))
    else:
        c.execute("""
            INSERT INTO evote_passwords
            (id, student_password, screen_password, candidate_password, evote_admin_password)
            VALUES (1, ?, ?, ?, ?)
        """, (
            student_pass,
            screen_pass,
            candidate_pass,
            admin_pass
        ))

    conn.commit()
    conn.close()

    return redirect("/admin")


# =========================
# ✅ ACTIVATE RESTAURANT
# =========================
@app.route("/activate/<int:rid>")
def activate_restaurant(rid):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
        UPDATE restaurants
        SET active=1
        WHERE id=?
    """, (rid,))

    conn.commit()
    conn.close()

    return redirect("/admin")


# =========================
# ❌ DISABLE RESTAURANT
# =========================
@app.route("/disable/<int:rid>")
def disable_restaurant(rid):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
        UPDATE restaurants
        SET active=0
        WHERE id=?
    """, (rid,))

    conn.commit()
    conn.close()

    return redirect("/admin")


@app.route("/delete_menu/<mid>/<rid>")
def delete_menu(mid, rid):
    try:
        restaurant_ref = db.collection("restaurants").document(rid)

        # menu item document
        menu_ref = restaurant_ref.collection("menu").document(mid)
        menu_doc = menu_ref.get()

        if not menu_doc.exists:
            return "Menu item not found ❌"

        menu_data = menu_doc.to_dict()

        # haddii image jiro
        image_name = menu_data.get("image")

        if image_name:
            image_path = os.path.join("static", "uploads", image_name)

            if os.path.exists(image_path):
                os.remove(image_path)

        # firestore delete
        menu_ref.delete()

        return redirect(f"/restaurant_admin/{rid}")

    except Exception as e:
        return f"Delete menu error ❌ {str(e)}"


@app.route("/renew/<int:rid>")
def renew_restaurant(rid):
    expiry = datetime.now() + timedelta(days=90)
    expiry_date = expiry.strftime("%Y-%m-%d")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
        UPDATE restaurants
        SET status=1,
            payment_status='active',
            expiry_date=?,
            plan='3months'
        WHERE id=?
    """, (expiry_date, rid))

    conn.commit()
    conn.close()

    return redirect("/admin")


@app.route("/register", methods=["GET", "POST"])
def register():
    try:
        # 🔐 access page password
        if not session.get("register_ok"):

            if request.method == "POST":
                passwords = get_system_passwords()
                real_pass = passwords.get("register_password", "6993")

                if request.form.get("access_password") == real_pass:
                    session["register_ok"] = True
                    return redirect("/register")

                return render_template(
                    "access_register.html",
                    error="Wrong password ❌"
                )

            return render_template("access_register.html")

        # 🔥 REAL REGISTER PAGE
        if request.method == "POST":
            months = int(request.form["months"])

            expiry_date = (
                datetime.now() + timedelta(days=months * 30)
            ).strftime("%Y-%m-%d")

            data = {
                "name": request.form["name"].strip(),
                "phone": request.form.get("phone", "").strip(),
                "username": request.form["username"].strip(),

                # restaurant login
                "password": request.form["password"].strip(),

                # kitchen login
                "kitchen_password": request.form["kitchen_password"].strip(),

                # 🔥 IMPORTANT
                "restaurant_admin_password":
                    request.form["restaurant_admin_password"].strip(),

                # admin info
                "admin_name": request.form.get("admin_name", "").strip(),
                "admin_email": request.form.get("admin_email", "").strip(),

                "price": request.form["price"].strip(),
                "payment": request.form["payment"].strip(),

                "expiry": expiry_date,
                "active": True,

                "review_count": 0,
                "average_rating": 0,

                "created_at": datetime.now()
            }

            # 🔥 SAVE TO FIREBASE
            doc_ref = db.collection("restaurants").add(data)
            rid = doc_ref[1].id

            restaurant_ref = db.collection("restaurants").document(rid)

            # create menu collection
            restaurant_ref.collection("menu").document("init").set({
                "created_at": datetime.now()
            })

            # create orders collection
            restaurant_ref.collection("orders").document("init").set({
                "created_at": datetime.now()
            })

            return redirect("/admin")

        return render_template("register.html")

    except Exception as e:
        print("Register Error:", e)
        return f"Register Error ❌ {str(e)}"


@app.route("/login", methods=["GET", "POST"])
def login():
    try:
        if request.method == "POST":
            username = request.form["username"].strip()
            password = request.form["password"].strip()

            docs = db.collection("restaurants").stream()

            for doc in docs:
                data = doc.to_dict()

                if (
                    data.get("username") == username and
                    data.get("password") == password
                ):
                    if not data.get("active", True):
                        return "Account disabled ❌"

                    session["restaurant_login"] = True
                    session["restaurant_id"] = doc.id
                    session["restaurant_name"] = data.get("name")

                    return redirect(f"/dashboard/{doc.id}")

            return render_template(
                "login.html",
                error="Wrong username or password ❌"
            )

        return render_template("login.html")

    except Exception as e:
        print("Login Error:", e)
        return f"Login Error ❌ {str(e)}"

@app.route("/supermarket_register", methods=["GET", "POST"])
def supermarket_register():
    try:
        if request.method == "POST":
            data = {
                "name": request.form["name"],
                "username": request.form["username"],
                "password": request.form["password"],
                "created_at": datetime.now(),
                "active": True
            }

            db.collection("supermarkets").add(data)

            return redirect("/supermarket_login")

        return render_template("supermarket_register.html")

    except Exception as e:
        return f"Supermarket Register Error ❌ {str(e)}"

@app.route("/supermarket_login", methods=["GET", "POST"])
def supermarket_login():
    try:
        if request.method == "POST":
            username = request.form["username"]
            password = request.form["password"]

            docs = db.collection("supermarkets").stream()

            for doc in docs:
                data = doc.to_dict()

                if (
                    data.get("username") == username and
                    data.get("password") == password
                ):
                    session["market_id"] = doc.id
                    return redirect("/supermarket_dashboard")

            return "Wrong login ❌"

        return render_template("supermarket_login.html")

    except Exception as e:
        return f"Login Error ❌ {str(e)}"


@app.route("/register_supermarket", methods=["GET", "POST"])
def register_supermarket():
    try:
        if request.method == "POST":
            months = int(request.form["months"])

            expiry = (
                datetime.now() + timedelta(days=months * 30)
            ).strftime("%Y-%m-%d")

            data = {
                "name": request.form["name"],
                "username": request.form["username"],
                "password": request.form["password"],
                "price": request.form["price"],
                "expiry": expiry,
                "active": True,
                "created_at": datetime.now()
            }

            db.collection("supermarkets").add(data)

            return redirect("/supermarket_login")

        return render_template("supermarket_register.html")

    except Exception as e:
        return f"Register Error ❌ {str(e)}"

@app.route("/place_order", methods=["POST"])
def place_order():
    data = {
        "food_name": request.form["food_name"],
        "table_no": request.form["table_no"],
        "status": "Pending",
        "created_at": datetime.now()
    }

    save_order_firestore(data)

    return jsonify({"message": "Order placed successfully"})

@app.route("/add_product", methods=["POST"])
def add_product():
    barcode = request.form["barcode"]
    product_name = request.form["product_name"]
    price = request.form["price"]

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
        INSERT INTO supermarket_products
        (barcode, product_name, price)
        VALUES (?, ?, ?)
    """, (
        barcode,
        product_name,
        price
    ))

    conn.commit()
    conn.close()

    return redirect("/supermarket_dashboard")

# =====================================
# 📊 RESTAURANT DASHBOARD (CLEAN VERSION)
# =====================================
@app.route("/dashboard/<rid>")
def dashboard(rid):
    try:
        # 🔐 login protection
        if not session.get("restaurant_login"):
            return redirect("/login")

        # 🔥 get restaurant
        restaurant_ref = db.collection("restaurants").document(rid)
        restaurant_doc = restaurant_ref.get()

        if not restaurant_doc.exists:
            return "Restaurant not found ❌"

        restaurant = restaurant_doc.to_dict()

        # 🔥 active check
        if not restaurant.get("active", True):
            return render_template("renew.html", rid=rid)

        # 🔥 expiry check
        expiry = restaurant.get("expiry", "")
        if expiry:
            try:
                expiry_date = datetime.strptime(expiry, "%Y-%m-%d")
                if datetime.now() >= expiry_date:
                    restaurant_ref.update({"active": False})
                    return render_template("renew.html", rid=rid)
            except Exception as expiry_error:
                print("Expiry Error:", expiry_error)

        # =====================================
        # 🍽 MENU
        # =====================================
        menu = []
        menu_docs = restaurant_ref.collection("menu").stream()

        for doc in menu_docs:
            item = doc.to_dict()
            item["id"] = doc.id
            item["name"] = item.get("name", "No Name")
            item["price"] = item.get("price", 0)
            item["image"] = item.get("image", "")
            menu.append(item)

        # =====================================
        # 📢 ADS
        # =====================================
        ads = []
        ad_docs = restaurant_ref.collection("ads").stream()

        for doc in ad_docs:
            ad = doc.to_dict()
            ad["id"] = doc.id
            ad["title"] = ad.get("title", "")
            ad["image"] = ad.get("image", "")
            ad["audio"] = ad.get("audio", "")
            ad["created_at"] = ad.get("created_at", None)

            print("DASHBOARD AD:", ad)   # debug
            ads.append(ad)

        # 🔥 newest first
        ads = list(reversed(ads))

        return render_template(
            "dashboard.html",
            rid=rid,
            restaurant=restaurant.get("name", "Restaurant"),
            menu=menu,
            ads=ads
        )

    except Exception as e:
        print("Dashboard Error:", e)
        return f"Dashboard Error ❌ {str(e)}"

# =====================================
# 📱 CUSTOMER MOBILE MENU ROUTE (LAST COMPLETE VERSION)
# =====================================
@app.route("/menu/<rid>/<table_no>")
def mobile_menu(rid, table_no):
    try:
        # 🔥 get restaurant document
        restaurant_ref = db.collection("restaurants").document(rid)
        restaurant_doc = restaurant_ref.get()

        if not restaurant_doc.exists:
            return "Restaurant not found ❌"

        restaurant = restaurant_doc.to_dict()

        # =====================================
        # 💳 PAYMENT
        # =====================================
        payment = restaurant.get("payment", "")
        payment_name = restaurant.get("payment_name", "")
        payment_number = restaurant.get("payment_number", payment)

        # =====================================
        # 🍽 MENU ITEMS
        # =====================================
        menu = []
        menu_docs = restaurant_ref.collection("menu").stream()

        for doc in menu_docs:
            item = doc.to_dict()

            # skip empty init docs
            if doc.id == "init":
                continue

            item["id"] = doc.id
            item["image"] = item.get("image", "")
            item["name"] = item.get("name", "No Name")
            item["price"] = item.get("price", 0)

            menu.append(item)

        # =====================================
        # 📢 ADS
        # =====================================
        ads = []
        ads_docs = restaurant_ref.collection("ads").stream()

        for doc in ads_docs:
            ad = doc.to_dict()

            # skip init docs
            if doc.id == "init":
                continue

            ad["id"] = doc.id
            ad["image"] = ad.get("image", "")
            ad["audio"] = ad.get("audio", "")
            ad["title"] = ad.get("title", "")

            print("CUSTOMER AD:", ad)   # debug log

            ads.append(ad)

        # newest ads first
        ads = list(reversed(ads))

        print("TOTAL ADS:", len(ads))
        print("TOTAL MENU:", len(menu))

        # =====================================
        # 📄 RENDER TEMPLATE
        # =====================================
        return render_template(
            "customer_menu.html",
            menu=menu,
            table=table_no,
            rid=rid,
            ads=ads,
            restaurant=restaurant.get("name", "Restaurant"),
            payment=payment,
            payment_name=payment_name,
            payment_number=payment_number,
            order_status=None
        )

    except Exception as e:
        print("Menu Error:", e)
        return f"Menu Error ❌ {str(e)}"


@app.route("/customer_order/<rid>", methods=["POST"])
def customer_order(rid):
    try:
        # 🔥 Get form data
        items = request.form.get("items", "")
        price = request.form.get("price", "0")
        table = request.form.get("table", "")

        drink_option = request.form.get("drink_option", "")
        food_option = request.form.get("food_option", "")
        tea_option = request.form.get("tea_option", "")

        # 🔥 Validation
        if not items:
            return "No items selected ❌"

        if not table:
            return "Table number missing ❌"

        # 🔥 Save order to Firestore
        db.collection("restaurants").document(rid)\
            .collection("orders").add({
                "items": items,
                "price": float(price),
                "table": str(table),
                "drink_option": drink_option,
                "food_option": food_option,
                "tea_option": tea_option,
                "status": "pending",
                "created_at": datetime.utcnow()
            })

        # 🔥 Return to menu page
        return redirect(f"/menu/{rid}/{table}")

    except Exception as e:
        print("Order Error:", e)
        return f"Order failed ❌ {str(e)}"

@app.route("/sales_data/<rid>")
def sales_data(rid):
    try:
        from_date = request.args.get("from")
        to_date = request.args.get("to")

        order_docs = db.collection("orders") \
            .where("restaurant_id", "==", rid) \
            .stream()

        data = []
        total_sales = 0

        for doc in order_docs:
            item = doc.to_dict()

            created_at = str(item.get("created_at", ""))

            if from_date and to_date:
                if created_at[:10] < from_date or created_at[:10] > to_date:
                    continue

            total_sales += float(item.get("total", 0))

            data.append({
                "table": item.get("table_no"),
                "food": item.get("food"),
                "total": item.get("total"),
                "date": created_at
            })

        return jsonify({
            "orders": data,
            "total_orders": len(data),
            "total_sales": total_sales
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        })
# =====================================
# 🍽 RESTAURANT ADMIN PANEL
# =====================================
from datetime import datetime, timedelta
from google.cloud import firestore

@app.route("/restaurant_admin/<rid>", methods=["GET", "POST"])
def restaurant_admin(rid):
    try:
        if not session.get("admin_" + str(rid)):
            return redirect(f"/restaurant_admin_login/{rid}")

        restaurant_ref = db.collection("restaurants").document(rid)
        restaurant_doc = restaurant_ref.get()

        if not restaurant_doc.exists:
            return "Restaurant not found ❌"

        restaurant = restaurant_doc.to_dict()
        restaurant["id"] = rid

        # 🔥 UPDATE SETTINGS TO FIREBASE
        if request.method == "POST":
            update_data = {
                "name": request.form.get("name", "").strip(),
                "username": request.form.get("username", "").strip(),
                "password": request.form.get("password", "").strip(),
                "kitchen_password": request.form.get("kitchen_password", "").strip(),
                "restaurant_admin_password": request.form.get("restaurant_admin_password", "").strip(),
                "updated_at": datetime.now(timezone.utc)
            }

            restaurant_ref.update(update_data)

            return redirect(f"/restaurant_admin/{rid}")

        # MENU
        menu = []
        menu_docs = restaurant_ref.collection("menu").stream()

        for doc in menu_docs:
            item = doc.to_dict()
            item["id"] = doc.id
            menu.append(item)

        # ORDERS
        orders = []
        total = 0

        order_docs = restaurant_ref.collection("orders").stream()

        for doc in order_docs:
            order = doc.to_dict()
            order["id"] = doc.id

            try:
                total += float(order.get("price", 0))
            except:
                pass

            orders.append(order)

        return render_template(
            "restaurant_admin.html",
            r=restaurant,
            menu=menu,
            orders=orders,
            total=round(total, 2),
            profit=round(total, 2),
            loss=0,
            compare_text="System working",
            rid=rid
        )

    except Exception as e:
        return f"Error ❌ {str(e)}"

# =====================================
# 🧹 CLEAR KITCHEN VIEW ONLY
# =====================================
@app.route("/clear_kitchen_orders/<rid>")
def clear_kitchen_orders(rid):
    try:
        if not session.get("admin_" + str(rid)):
            return redirect(f"/restaurant_admin_login/{rid}")

        orders_ref = db.collection("restaurants") \
            .document(rid) \
            .collection("orders")

        docs = orders_ref.stream()

        for doc in docs:
            data = doc.to_dict()

            # 🔥 keep history + sales
            # only hide from kitchen screen
            doc.reference.update({
                "kitchen_cleared": True,
                "cleared_at": datetime.now(timezone.utc)
            })

        return redirect(f"/restaurant_admin/{rid}")

    except Exception as e:
        return f"Kitchen clear error ❌ {str(e)}"


# =====================================
# 🗑 CLEAR ALL ADS
# =====================================
@app.route("/clear_ads/<rid>")
def clear_ads(rid):
    try:
        if not session.get("admin_" + str(rid)):
            return redirect(f"/restaurant_admin_login/{rid}")

        ads_ref = db.collection("restaurants") \
            .document(rid) \
            .collection("ads")

        docs = ads_ref.stream()

        for doc in docs:
            doc.reference.delete()

        return redirect(f"/restaurant_admin/{rid}")

    except Exception as e:
        return f"Ads clear error ❌ {str(e)}"

# =====================================
# 🔐 RESTAURANT ADMIN LOGIN
# =====================================
@app.route("/restaurant_admin_login/<rid>", methods=["GET", "POST"])
def restaurant_admin_login(rid):
    try:
        restaurant_ref = db.collection("restaurants").document(rid)
        restaurant_doc = restaurant_ref.get()

        if not restaurant_doc.exists:
            return "Restaurant not found ❌"

        restaurant = restaurant_doc.to_dict()

        if request.method == "POST":
            entered_password = request.form.get(
                "password",
                ""
            ).strip()

            # 🔥 SUPPORT OLD + NEW FIREBASE FIELD
            real_password = str(
                restaurant.get("restaurant_admin_password")
                or restaurant.get("resturen_admin password")
                or ""
            ).strip()

            print("ENTERED PASSWORD:", entered_password)
            print("REAL PASSWORD:", real_password)

            if entered_password == real_password:
                session["admin_" + str(rid)] = True
                return redirect(f"/restaurant_admin/{rid}")

            return f'''
            <div style="max-width:400px;margin:50px auto;font-family:Arial;">
                <h3 style="color:red;">Wrong password ❌</h3>
                <a href="/restaurant_admin_login/{rid}">Try again</a>
            </div>
            '''

        return f'''
        <form method="post"
              style="max-width:400px;
                     margin:50px auto;
                     font-family:Arial;
                     background:white;
                     padding:25px;
                     border-radius:12px;
                     box-shadow:0 0 10px rgba(0,0,0,0.1);">

            <h2 style="text-align:center;">Admin Login 🔐</h2>

            <input type="password"
                   name="password"
                   placeholder="Enter admin password"
                   required
                   style="width:100%;
                          padding:12px;
                          margin:15px 0;
                          border:1px solid #ddd;
                          border-radius:8px;
                          box-sizing:border-box;">

            <button type="submit"
                    style="width:100%;
                           padding:12px;
                           background:#0a7cff;
                           color:white;
                           border:none;
                           border-radius:8px;
                           font-weight:bold;
                           cursor:pointer;">
                Login
            </button>
        </form>
        '''

    except Exception as e:
        print("Login Error:", e)
        return f"Login error ❌ {str(e)}"

# 🔥 ADD STAFF
@app.route("/add_staff/<rid>", methods=["POST"])
def add_staff(rid):
    try:
        staff_data = {
            "restaurant_id": rid,
            "name": request.form["name"],
            "email": request.form["email"],
            "password": request.form["password"],
            "role": "staff",
            "created_at": datetime.now()
        }

        db.collection("restaurants") \
            .document(rid) \
            .collection("staff") \
            .add(staff_data)

        return redirect("/dashboard/" + rid)

    except Exception as e:
        return f"Add staff error ❌ {str(e)}"


# 🔥 STAFF LIST
@app.route("/staff_list/<rid>")
def staff_list(rid):
    try:
        docs = db.collection("restaurants") \
            .document(rid) \
            .collection("staff") \
            .stream()

        staff = []
        for doc in docs:
            item = doc.to_dict()
            item["id"] = doc.id
            staff.append(item)

        return render_template("staff_list.html", staff=staff)

    except Exception as e:
        return f"Staff list error ❌ {str(e)}"


# 🔥 SEND NEWS
@app.route("/send_news/<rid>", methods=["POST"])
def send_news(rid):
    try:
        news_data = {
            "title": request.form["title"],
            "message": request.form["message"],
            "created_at": datetime.now()
        }

        db.collection("restaurants") \
            .document(rid) \
            .collection("staff_news") \
            .add(news_data)

        return redirect("/dashboard/" + rid)

    except Exception as e:
        return f"Send news error ❌ {str(e)}"


# 🔥 STAFF NEWS
@app.route("/staff_news/<rid>")
def staff_news(rid):
    try:
        docs = db.collection("restaurants") \
            .document(rid) \
            .collection("staff_news") \
            .stream()

        news = []
        for doc in docs:
            item = doc.to_dict()
            item["id"] = doc.id
            news.append(item)

        return render_template("staff_news.html", news=news)

    except Exception as e:
        return f"Staff news error ❌ {str(e)}"


@app.route("/stats/<rid>")
def stats(rid):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM orders WHERE restaurant_id=?", (rid,))
    orders = c.fetchone()[0]

    c.execute("SELECT AVG(CAST(price AS FLOAT)) FROM menu WHERE restaurant_id=?", (rid,))
    avg_price = c.fetchone() or 0

    revenue = orders * avg_price
    profit = round(revenue * 0.7, 2)

    conn.close()
    return jsonify({
        "orders": orders,
        "revenue": round(revenue, 2),
        "profit": profit
    })


@app.route("/get_calls/<rid>")
def get_calls(rid):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM waiter_calls WHERE restaurant_id=?", (rid,))
    count = c.fetchone()
    conn.close()
    return jsonify({"count": count})

# ✅ ADD MENU (UPDATED WITH SAFE CATEGORY GET)
@app.route("/add_menu/<rid>", methods=["POST"])
def add_menu(rid):
    try:
        name = request.form["name"]
        price = request.form["price"]
        image_file = request.files["image"]

        filename = secure_filename(image_file.filename)
        image_path = os.path.join(UPLOAD_FOLDER, filename)
        image_file.save(image_path)

        menu_data = {
            "name": name,
            "price": price,
            "image": filename,
            "created_at": datetime.now()
        }

        db.collection("restaurants")\
            .document(rid)\
            .collection("menu")\
            .add(menu_data)

        return redirect(f"/dashboard/{rid}")

    except Exception as e:
        return f"Add Menu Error ❌ {str(e)}"


# 🔹 (B) ADD AD ROUTE (NEW UPDATE)
@app.route("/add_ad/<rid>", methods=["POST"])
def add_ad(rid):
    try:
        restaurant_ref = db.collection("restaurants").document(rid)

        title = request.form.get("title", "").strip()

        image_file = request.files.get("image")
        audio_file = request.files.get("audio")

        image_name = ""
        audio_name = ""

        # save image
        if image_file and image_file.filename:
            image_name = image_file.filename
            image_path = os.path.join("static/uploads", image_name)
            image_file.save(image_path)

        # save audio
        if audio_file and audio_file.filename:
            audio_name = audio_file.filename
            audio_path = os.path.join("static/uploads", audio_name)
            audio_file.save(audio_path)

        # save firestore
        restaurant_ref.collection("ads").add({
            "title": title,
            "image": image_name,
            "audio": audio_name,
            "created_at": datetime.utcnow()
        })

        return redirect(f"/dashboard/{rid}")

    except Exception as e:
        print("Add Ad Error:", e)
        return f"Add Ad Error ❌ {str(e)}"


from urllib.parse import quote
import os
import qrcode

# 🔥 GENERATE QR ROUTE
@app.route("/generate_qr/<rid>", methods=["POST"])
def generate_qr(rid):
    try:
        table = request.form.get("table", "").strip()

        # 🔥 force numeric table only
        if not table.isdigit():
            return "<p>Table number must be number only ❌</p>"

        restaurant_ref = db.collection("restaurants").document(rid)
        restaurant_doc = restaurant_ref.get()

        if not restaurant_doc.exists:
            return "Restaurant not found ❌"

        restaurant = restaurant_doc.to_dict()
        restaurant_name = restaurant.get("name", "Restaurant")

        filename = f"qr_{rid}_{table}.png"

        qr_folder = os.path.join("static", "qr")
        os.makedirs(qr_folder, exist_ok=True)

        file_path = os.path.join(qr_folder, filename)

        # 🔥 FIXED DOMAIN URL
        url = f"https://sahalserver.com/menu/{rid}/{table}"

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4
        )

        qr.add_data(url)
        qr.make(fit=True)

        img = qr.make_image(
            fill_color="black",
            back_color="white"
        )

        img.save(file_path)

        return render_template(
            "qr.html",
            rid=rid,
            img=filename,
            url=url,
            table=table,
            restaurant=restaurant_name
        )

    except Exception as e:
        print("QR Error:", e)
        return f"QR Error ❌ {str(e)}"


# 🔥 CLEAN MENU ROUTE
@app.route("/<restaurant_slug>/table-<table_no>")
def clean_table_menu(restaurant_slug, table_no):
    try:
        rid = request.args.get("rid")

        if not rid:
            return "Restaurant ID missing ❌"

        restaurant_ref = db.collection("restaurants").document(rid)
        restaurant_doc = restaurant_ref.get()

        if not restaurant_doc.exists:
            return "Restaurant not found ❌"

        restaurant = restaurant_doc.to_dict()

        menu_docs = restaurant_ref.collection("menu").stream()

        menu = []
        for doc in menu_docs:
            item = doc.to_dict()
            item["id"] = doc.id
            menu.append(item)

        return render_template(
            "customer_menu.html",
            menu=menu,
            table=table_no,
            rid=rid,
            restaurant=restaurant.get("name", "Restaurant")
        )

    except Exception as e:
        print("Menu Error:", e)
        return f"Menu Error ❌ {str(e)}"

@app.route("/order/<rid>", methods=["POST"])
def order(rid):
    food = request.form["food"]
    table = request.form["table"]
    time = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("""
    INSERT INTO orders(restaurant_id,food,table_no,time,status)
    VALUES(?,?,?,?,?)
    """, (rid, food, table, time, "pending"))
    conn.commit()
    conn.close()
    return "ok"


@app.route("/update_status/<rid>/<order_id>/<status>")
def update_status(rid, order_id, status):
    try:
        order_ref = db.collection("restaurants") \
            .document(rid) \
            .collection("orders") \
            .document(order_id)

        order_doc = order_ref.get()

        if not order_doc.exists:
            return {
                "success": False,
                "message": "Order not found ❌"
            }

        # ✅ update status
        order_ref.update({
            "status": status,
            "updated_at": datetime.utcnow()
        })

        # ✅ get updated data
        updated_doc = order_ref.get()
        updated_data = updated_doc.to_dict()

        return {
            "success": True,
            "message": f"Status updated to {updated_data.get('status')} ✅",
            "status": updated_data.get("status"),
            "order_id": order_id,
            "table": updated_data.get("table"),
            "items": updated_data.get("items")
        }

    except Exception as e:
        print("Update Status Error:", e)

        return {
            "success": False,
            "message": f"Update failed ❌ {str(e)}"
        }


# 🔔 KITCHEN SOUND COUNT ROUTE
@app.route("/get_orders_count/<int:rid>")
def get_orders_count(rid):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute(
        "SELECT COUNT(*) FROM orders WHERE restaurant_id=?",
        (rid,)
    )

    count = c.fetchone()[0]
    conn.close()

    return {"count": count}


@app.route("/call_waiter/<rid>", methods=["POST"])
def call_waiter(rid):
    try:
        table = request.form.get("table")

        restaurant_ref = db.collection("restaurants").document(rid)

        restaurant_ref.collection("waiter_calls").add({
            "table": table,
            "created_at": firestore.SERVER_TIMESTAMP
        })

        return "success"

    except Exception as e:
        return str(e)


@app.route("/order_status/<rid>")
def order_status(rid):
    table = request.args.get("table")
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("""
    SELECT status FROM orders
    WHERE restaurant_id=? AND table_no=?
    ORDER BY id DESC LIMIT 1
    """, (rid, table))
    data = c.fetchone()
    conn.close()

    return data if data else "waiting"


import sqlite3
from flask import request, jsonify, render_template
from datetime import datetime

# =========================
# 🍳 KITCHEN ROUTE (CLEAN VERSION)
# =========================
from zoneinfo import ZoneInfo
from google.cloud import firestore

@app.route("/kitchen/<rid>", methods=["GET", "POST"])
def kitchen(rid):
    try:
        restaurant_ref = db.collection("restaurants").document(rid)
        restaurant_doc = restaurant_ref.get()

        if not restaurant_doc.exists:
            return "Restaurant not found ❌"

        restaurant = restaurant_doc.to_dict()
        real_pass = restaurant.get("kitchen_password", "7890")

        # 🔐 LOGIN
        if request.method == "POST":
            user_pass = request.form.get("password", "").strip()

            if user_pass != str(real_pass).strip():
                return render_template(
                    "kitchen_login.html",
                    rid=rid,
                    error="Wrong password ❌"
                )

            session["kitchen_" + str(rid)] = True

        # 🔐 SESSION CHECK
        if not session.get("kitchen_" + str(rid)):
            return render_template(
                "kitchen_login.html",
                rid=rid
            )

        # =========================
        # 📦 ORDERS (ONLY ACTIVE KITCHEN)
        # =========================
        order_docs = (
            restaurant_ref.collection("orders")
            .order_by(
                "created_at",
                direction=firestore.Query.DESCENDING
            )
            .stream()
        )

        orders = []

        for doc in order_docs:
            order = doc.to_dict()
            order["id"] = doc.id

            # 🔥 HIDE CLEARED FROM KITCHEN ONLY
            if order.get("kitchen_cleared") == True:
                continue

            created_at = order.get("created_at")

            if created_at:
                try:
                    order["created_at"] = created_at.astimezone(
                        ZoneInfo("Africa/Mogadishu")
                    ).strftime("%Y-%m-%d %I:%M:%S %p")
                except:
                    order["created_at"] = str(created_at)
            else:
                order["created_at"] = "N/A"

            orders.append(order)

        # =========================
        # 🔔 WAITER CALLS
        # =========================
        calls = []
        call_docs = restaurant_ref.collection("waiter_calls").stream()

        for doc in call_docs:
            call_item = doc.to_dict()
            call_item["id"] = doc.id
            calls.append(call_item)

        return render_template(
            "kitchen.html",
            orders=orders,
            calls=calls,
            rid=rid
        )

    except Exception as e:
        print("Kitchen Error:", e)
        return f"Kitchen error ❌ {str(e)}"

# =========================
# 🤖 AI CHAT ROUTE (NEW)
# =========================
@app.route("/ai_chat/<int:rid>", methods=["POST"])
def ai_chat(rid):

    msg = request.form.get("message")
    table = request.form.get("table")

    reply = "Mahadsanid 🙏 fariintaada waa la gudbiyey"

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
    INSERT INTO ai_messages (restaurant_id, table_no, message, time)
    VALUES (?,?,?,?)
    """, (rid, table, msg, datetime.now().strftime("%Y-%m-%d %H:%M")))

    conn.commit()
    conn.close()

    return jsonify({"reply": reply})

# 📊 TODAY vs YESTERDAY (ADVANCED)
@app.route("/today_stats/<rid>")
def today_stats(rid):

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # TODAY
    c.execute("SELECT COUNT(*) FROM orders WHERE restaurant_id=? AND time LIKE ?", (rid, today + "%"))
    today_orders = c.fetchone()[0]

    # YESTERDAY
    c.execute("SELECT COUNT(*) FROM orders WHERE restaurant_id=? AND time LIKE ?", (rid, yesterday + "%"))
    yesterday_orders = c.fetchone()[0]

    # AVG PRICE
    c.execute("SELECT AVG(CAST(price AS FLOAT)) FROM menu WHERE restaurant_id=?", (rid,))
    avg_price = c.fetchone()[0] or 0

    conn.close()

    # CALCULATIONS
    today_revenue = round(today_orders * avg_price, 2)
    yesterday_revenue = round(yesterday_orders * avg_price, 2)
    today_profit = round(today_revenue * 0.7, 2)
    yesterday_profit = round(yesterday_revenue * 0.7, 2)
    diff_profit = round(today_profit - yesterday_profit, 2)

    return jsonify({
        "today_orders": today_orders,
        "today_revenue": today_revenue,
        "today_profit": today_profit,
        "yesterday_orders": yesterday_orders,
        "yesterday_revenue": yesterday_revenue,
        "yesterday_profit": yesterday_profit,
        "diff_profit": diff_profit
    })



@app.route("/analytics/<rid>")
def analytics(rid):
    return render_template("stats.html", rid=rid)


# 📊 GET ORDERS BY DATE
@app.route("/orders_by_date/<int:rid>")
def orders_by_date(rid):
    date = request.args.get("date")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
    SELECT table_no, food, time
    FROM orders
    WHERE restaurant_id=? AND time LIKE ?
    """, (rid, date + "%"))

    data = c.fetchall()

    total_orders = len(data)

    conn.close()

    return jsonify({
        "orders": [
            {
                "table": row[0],
                "food": row[1],
                "time": row[2]
            } for row in data
        ],
        "total": total_orders
    })


# 📊 TODAY VS YESTERDAY
@app.route("/compare/<int:rid>")
def compare(rid):
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        # Today orders
        c.execute(
            "SELECT COUNT(*) FROM orders WHERE restaurant_id=? AND time LIKE ?",
            (rid, today + "%")
        )
        today_orders = c.fetchone()[0] or 0

        # Yesterday orders
        c.execute(
            "SELECT COUNT(*) FROM orders WHERE restaurant_id=? AND time LIKE ?",
            (rid, yesterday + "%")
        )
        yesterday_orders = c.fetchone()[0] or 0

        # Average price
        c.execute(
            "SELECT AVG(CAST(price AS FLOAT)) FROM menu WHERE restaurant_id=?",
            (rid,)
        )
        avg_price = c.fetchone()[0] or 0

        # Calculations
        today_total = round(today_orders * avg_price, 2)
        yesterday_total = round(yesterday_orders * avg_price, 2)

        diff = round(today_total - yesterday_total, 2)

        if diff > 0:
            status = "PROFIT 📈"
        elif diff < 0:
            status = "LOSS 📉"
        else:
            status = "EVEN ⚖️"

        conn.close()

        return jsonify({
            "today": today_total,
            "yesterday": yesterday_total,
            "difference": diff,
            "status": status
        })

    except Exception as e:
        return jsonify({"error": str(e)})
def delete_ad(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # SAWIRKA KA QAAD FOLDER-KA
    c.execute("SELECT image FROM ads WHERE id=?", (id,))
    data = c.fetchone()

    if data:
        filename = data
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(filepath):
            os.remove(filepath)

    # DATABASE KA TIR
    c.execute("DELETE FROM ads WHERE id=?", (id,))

    conn.commit()
    conn.close()

    return redirect(request.referrer)


# ====== HALKAAN KU DAR ======

@app.route("/clear_orders/<rid>")
def clear_orders(rid):
    try:
        orders_ref = db.collection("restaurants") \
            .document(rid) \
            .collection("orders")

        docs = orders_ref.stream()

        for doc in docs:
            data = doc.to_dict()

            data["cleared_from_kitchen"] = True

            orders_ref.document(doc.id).update(data)

        return "OK"

    except Exception as e:
        return f"Error ❌ {str(e)}"


@app.route("/clear_calls/<rid>")
def clear_calls(rid):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("DELETE FROM waiter_calls WHERE restaurant_id=?", (rid,))
    conn.commit()
    conn.close()
    return "ok"


@app.route("/waiter_done/<rid>", methods=["POST"])
def waiter_done(rid):
    table = request.form.get("table")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("DELETE FROM waiter_calls WHERE restaurant_id=? AND table_no=?", (rid, table))

    conn.commit()
    conn.close()

    return "ok"


# ======= HA TAABANIN =======
if __name__ == "__main__":
    init_db()
    socketio.run(app, host="0.0.0.0", port=5000)
