from flask import (
    Flask,
    render_template,
    request,
    redirect,
    jsonify,
    session
)

from flask_socketio import SocketIO, emit, join_room
import sqlite3
import os
import qrcode
import socket
import random
from datetime import datetime, timedelta


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

            # haddii waqtigu dhacay → auto disable
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

# 🔥 SOCKET IO
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
    # 🍔 MENU
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS menu(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        restaurant_id INTEGER,
        name TEXT,
        price REAL,
        image TEXT,
        category TEXT
    )
    """)

    # =========================
    # 🤖 AI MESSAGES
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS ai_messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        restaurant_id INTEGER,
        table_no TEXT,
        message TEXT,
        time TEXT
    )
    """)

    # =========================
    # 📢 ADS
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS ads(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        restaurant_id INTEGER,
        image TEXT,
        title TEXT
    )
    """)

    # =========================
    # 🧾 ORDERS
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        restaurant_id INTEGER,
        food TEXT,
        table_no TEXT,
        time TEXT,
        status TEXT
    )
    """)

    # =========================
    # 🧑‍🍳 WAITER CALLS
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS waiter_calls(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        restaurant_id INTEGER,
        table_no TEXT,
        time TEXT
    )
    """)

    # =========================
    # 👨‍💼 STAFF
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS staff(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        restaurant_id INTEGER,
        name TEXT,
        email TEXT,
        password TEXT,
        role TEXT
    )
    """)

    # =========================
    # 📰 STAFF NEWS
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS staff_news(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        restaurant_id INTEGER,
        title TEXT,
        message TEXT
    )
    """)

    # =========================
    # 🔄 RENEW REQUESTS
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS renew_requests(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        restaurant_id INTEGER,
        time TEXT
    )
    """)

    # =========================
    # ⚙️ SETTINGS
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS settings(
        id INTEGER PRIMARY KEY,
        admin_password TEXT,
        register_password TEXT
    )
    """)

    # =========================
    # 🗳️ EVOTE STUDENTS
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
    # 🧑‍💼 EVOTE CANDIDATES
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS candidates(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT,
        department TEXT,
        round INTEGER DEFAULT 1,
        votes INTEGER DEFAULT 0,
        percentage REAL DEFAULT 0
    )
    """)

    # image column haddii hore table-ku u jiray
    try:
        c.execute("ALTER TABLE candidates ADD COLUMN image TEXT")
        print("image column added ✅")
    except sqlite3.OperationalError:
        pass

    # =========================
    # 🗳️ ELECTION SETTINGS
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS election_settings(
        id INTEGER PRIMARY KEY,
        current_round INTEGER DEFAULT 1,
        round_end_time TEXT
    )
    """)

    # =========================
    # ⏱️ ELECTION TIMER
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS election_timer(
        id INTEGER PRIMARY KEY,
        round_time_minutes INTEGER DEFAULT 0,
        end_time TEXT
    )
    """)

    c.execute("SELECT * FROM election_timer WHERE id=1")
    if not c.fetchone():
        c.execute("""
            INSERT INTO election_timer
            (id, round_time_minutes, end_time)
            VALUES (1, 0, '')
        """)

    # =========================
    # 🔐 DEFAULT PASSWORDS
    # =========================
    c.execute("SELECT * FROM settings WHERE id=1")
    if not c.fetchone():
        c.execute("""
            INSERT INTO settings
            (id, admin_password, register_password)
            VALUES (1, '8880', '8880')
        """)

    # =========================
    # 🗳️ DEFAULT ROUND
    # =========================
    c.execute("SELECT * FROM election_settings WHERE id=1")
    if not c.fetchone():
        c.execute("""
            INSERT INTO election_settings
            (id, current_round, round_end_time)
            VALUES (1, 1, '')
        """)

    conn.commit()
    conn.close()

    print("DATABASE READY ✅")

@app.route("/")
def home():
    return render_template("home.html")

# =========================
# 🗳 EVOTE ROUTES
# =========================

@app.route("/register_student", methods=["GET", "POST"])
def register_student():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    if request.method == "POST":
        student_id = request.form["student_id"]
        full_name = request.form["full_name"]
        class_name = request.form["class_name"]
        semester = request.form["semester"]

        vote_code = generate_vote_code()

        try:
            c.execute("""
                INSERT INTO students
                (student_id, full_name, class_name, semester, vote_code)
                VALUES (?, ?, ?, ?, ?)
            """, (
                student_id,
                full_name,
                class_name,
                semester,
                vote_code
            ))

            conn.commit()
            conn.close()

            return f"""
            <h2>Student Registered ✅</h2>
            <p>Name: <b>{full_name}</b></p>
            <p>Vote Code: <b>{vote_code}</b></p>
            """

        except Exception as e:
            conn.close()
            return f"Student already exists ❌ {e}"

    conn.close()
    return render_template("register_student.html")

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
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
        SELECT current_round
        FROM election_settings
        WHERE id=1
    """)

    row = c.fetchone()
    current_round = row[0] if row else 1

    if request.method == "POST":
        vote_code = request.form.get("student_id")
        candidate_id = request.form.get("candidate_id")

        if not vote_code or not candidate_id:
            conn.close()
            return "Missing vote code or candidate ❌"

        vote_column = f"has_voted_round{current_round}"

        c.execute(f"""
            SELECT student_id, {vote_column}
            FROM students
            WHERE vote_code=?
        """, (vote_code,))

        student = c.fetchone()

        if not student:
            conn.close()
            return "Invalid vote code ❌"

        if student[1] == 1:
            conn.close()
            return "Already voted in this round ❌"

        c.execute("""
            UPDATE candidates
            SET votes = votes + 1
            WHERE id=?
        """, (candidate_id,))

        c.execute(f"""
            UPDATE students
            SET {vote_column}=1
            WHERE vote_code=?
        """, (vote_code,))

        conn.commit()
        conn.close()

        return "Vote submitted successfully ✅"

    c.execute("""
        SELECT *
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

    # =========================
    # STEP 2: SUBMIT REAL VOTE
    # =========================
    if request.method == "POST" and "candidate_id" in request.form:
        student_id = request.form["student_id"]
        candidate_id = request.form["candidate_id"]

        vote_column = f"has_voted_round{current_round}"

        c.execute(f"""
            SELECT {vote_column}
            FROM students
            WHERE student_id=?
        """, (student_id,))
        student = c.fetchone()

        if not student:
            conn.close()
            return "Student not found ❌"

        if student[0] == 1:
            conn.close()
            return "Already voted in this round ❌"

        # add vote
        c.execute("""
            UPDATE candidates
            SET votes = votes + 1
            WHERE id=?
        """, (candidate_id,))

        # mark voted
        c.execute(f"""
            UPDATE students
            SET {vote_column}=1
            WHERE student_id=?
        """, (student_id,))

        conn.commit()
        conn.close()

        return "Vote submitted successfully ✅"

    # =========================
    # FIRST PAGE
    # =========================
    conn.close()
    return render_template(
        "vote_code.html",
        current_round=current_round
    )


@app.route("/admin_dashboard", methods=["GET", "POST"])
def admin_dashboard():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "next_round":
            c.execute("""
                UPDATE election_settings
                SET current_round = current_round + 1
                WHERE id=1
            """)

        elif action == "set_timer":
            minutes = int(request.form.get("minutes", 0))
            end_time = datetime.now() + timedelta(minutes=minutes)

            c.execute("""
                UPDATE election_timer
                SET round_time_minutes=?,
                    end_time=?
                WHERE id=1
            """, (minutes, end_time.strftime("%Y-%m-%d %H:%M:%S")))

        conn.commit()

    c.execute("SELECT current_round FROM election_settings WHERE id=1")
    row = c.fetchone()
    current_round = row[0] if row else 1

    c.execute("""
        SELECT *
        FROM candidates
        WHERE round=?
        ORDER BY votes DESC
    """, (current_round,))
    results = c.fetchall()

    c.execute("""
        SELECT round_time_minutes, end_time
        FROM election_timer
        WHERE id=1
    """)
    timer = c.fetchone()

    conn.close()

    return render_template(
        "admin_dashboard.html",
        current_round=current_round,
        results=results,
        timer=timer
    )


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
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT current_round FROM election_settings WHERE id=1")
    row = c.fetchone()

    current_round = row[0] if row else 1

    c.execute("""
        SELECT *
        FROM candidates
        WHERE round=?
        ORDER BY votes DESC
    """, (current_round,))

    candidates = c.fetchall()

    conn.close()

    return render_template(
        "live_results.html",
        candidates=candidates
    )

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

    # haddii hore login sameeyay
    if session.get("admin_ok"):
        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        c.execute("SELECT * FROM restaurants")
        restaurants = c.fetchall()

        c.execute("SELECT * FROM orders")
        orders = c.fetchall()

        c.execute("SELECT COUNT(*) FROM orders")
        total = c.fetchone()[0]

        conn.close()

        return render_template("admin.html",
                               restaurants=restaurants,
                               orders=orders,
                               total=total)

    # haddii password la geliyo
    if request.method == "POST":

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        c.execute("SELECT admin_password FROM settings WHERE id=1")
        real_pass = c.fetchone()[0]

        if request.form.get("password") != real_pass:
            conn.close()
            return render_template("admin_login.html", error="Wrong password")

        conn.close()

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

@app.route("/change_passwords", methods=["POST"])
def change_passwords():

    new_admin = request.form.get("admin_pass")
    new_register = request.form.get("register_pass")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
    UPDATE settings 
    SET admin_password=?, register_password=?
    WHERE id=1
    """, (new_admin, new_register))

    conn.commit()
    conn.close()

    return redirect("/admin")
@app.route("/activate/<int:rid>")
def activate_restaurant(rid):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("UPDATE restaurants SET active=1 WHERE id=?", (rid,))

    conn.commit()
    conn.close()

    return redirect("/admin")


@app.route("/disable/<int:rid>")
def disable_restaurant(rid):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("UPDATE restaurants SET active=0 WHERE id=?", (rid,))

    conn.commit()
    conn.close()

    return redirect("/admin")


@app.route("/delete_menu/<int:mid>/<int:rid>")
def delete_menu(mid, rid):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # marka hore sawirka hel
    c.execute("SELECT image FROM menu WHERE id=?", (mid,))
    row = c.fetchone()

    if row and row[0]:
        image_path = os.path.join(UPLOAD_FOLDER, row[0])

        # haddii file-ku jiro, tirtir
        if os.path.exists(image_path):
            os.remove(image_path)

    # menu-ga ka tirtir database
    c.execute("DELETE FROM menu WHERE id=?", (mid,))
    conn.commit()
    conn.close()

    return redirect(f"/dashboard/{rid}")


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

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # haddii hore password-ka loo saxay
    if session.get("register_ok"):

        if request.method == "POST":

            name = request.form["name"]
            phone = request.form["phone"]
            username = request.form["username"]
            password = request.form["password"]
            kitchen_password = request.form["kitchen_password"]
            price = request.form["price"]
            payment = request.form["payment"]

            months = int(request.form["months"])

            expiry_date = datetime.now() + timedelta(days=months * 30)
            expiry_date = expiry_date.strftime("%Y-%m-%d")

            c.execute("""
            INSERT INTO restaurants
            (name, phone, username, password, price, expiry, active, payment_number, kitchen_password)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name,
                phone,
                username,
                password,
                price,
                expiry_date,
                1,
                payment,
                kitchen_password
            ))

            conn.commit()
            conn.close()

            return redirect("/admin")

        conn.close()
        return render_template("register.html")

    # haddii password la geliyo
    if request.method == "POST":

        c.execute("SELECT register_password FROM settings WHERE id=1")
        real_pass = c.fetchone()[0]

        user_pass = request.form.get("access_password")

        if user_pass == real_pass:
            session["register_ok"] = True
            conn.close()
            return redirect("/register")

        conn.close()
        return render_template(
            "access_register.html",
            error="Wrong password"
        )

    conn.close()
    return render_template("access_register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("SELECT * FROM restaurants WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()

        if user:
            # ✔ SAX: Waxaan u beddelay user si uu ID-ga saxda ah u qaado
            return redirect("/dashboard/" + str(user[0]))

    return render_template("login.html")


@app.route("/dashboard/<rid>")
def dashboard(rid):

    auto_check_expiry(rid)

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT active FROM restaurants WHERE id=?", (rid,))
    status = c.fetchone()

    if status and status[0] == 0:
        conn.close()
        return render_template("renew.html", rid=rid)

    c.execute("SELECT * FROM menu WHERE restaurant_id=?", (rid,))
    menu = c.fetchall()

    c.execute("SELECT * FROM ads WHERE restaurant_id=?", (rid,))
    ads = c.fetchall()

    conn.close()

    return render_template("dashboard.html", menu=menu, ads=ads, rid=rid)

# ✅ 4. KU DAR HALKAN (COPY PASTE) - SALES DATA ROUTE
@app.route("/sales_data/<int:rid>")
def sales_data(rid):

    from_date = request.args.get("from")
    to_date = request.args.get("to")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    query = """
    SELECT table_no, food, total, created_at
    FROM orders
    WHERE restaurant_id=?
    """

    params = [rid]

    if from_date and to_date:
        query += " AND date(created_at) BETWEEN ? AND ?"
        params.append(from_date)
        params.append(to_date)

    c.execute(query, params)
    data = c.fetchall()

    total = len(data) if data else 0

    conn.close()

    return jsonify({
        "orders": [
            {
                "table": row,
                "food": row,
                "total": row,
                "date": row
            } for row in data
        ],
        "total": total
    })


# 🔥 NEW ROUTE (ADMIN RESTAURANT)
@app.route("/restaurant_admin/<int:rid>", methods=["GET", "POST"])
def restaurant_admin(rid):

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    if request.method == "POST":
        name = request.form["name"]
        username = request.form["username"]
        password = request.form["password"]
        kitchen_password = request.form["kitchen_password"]

        c.execute("""
            UPDATE restaurants
            SET name=?, username=?, password=?, kitchen_password=?
            WHERE id=?
        """, (name, username, password, kitchen_password, rid))

        conn.commit()

        # update kadib xogta cusub isla markiiba dib u soo qaado
        return redirect(f"/restaurant_admin/{rid}")

    # MENU
    c.execute("SELECT * FROM menu WHERE restaurant_id=?", (rid,))
    menu = c.fetchall()

    # ADS
    c.execute("SELECT * FROM ads WHERE restaurant_id=?", (rid,))
    ads = c.fetchall()

    # ORDERS
    c.execute("SELECT * FROM orders WHERE restaurant_id=?", (rid,))
    orders = c.fetchall()

    # RESTAURANT INFO
    c.execute("SELECT * FROM restaurants WHERE id=?", (rid,))
    r = c.fetchone()

    conn.close()

    return render_template(
        "restaurant_admin.html",
        r=r,
        menu=menu,
        ads=ads,
        orders=orders
    )

@app.route("/add_staff/<rid>", methods=["POST"])
def add_staff(rid):
    name = request.form["name"]
    email = request.form["email"]
    password = request.form["password"]

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("""
    INSERT INTO staff(restaurant_id,name,email,password,role)
    VALUES(?,?,?,?,?)
    """, (rid, name, email, password, "staff"))
    conn.commit()
    conn.close()
    return redirect("/dashboard/" + rid)


@app.route("/staff_list/<rid>")
def staff_list(rid):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM staff WHERE restaurant_id=?", (rid,))
    staff = c.fetchall()
    conn.close()
    return render_template("staff_list.html", staff=staff)


@app.route("/send_news/<rid>", methods=["POST"])
def send_news(rid):
    title = request.form["title"]
    message = request.form["message"]

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("""
    INSERT INTO staff_news(restaurant_id,title,message)
    VALUES(?,?,?)
    """, (rid, title, message))
    conn.commit()
    conn.close()
    return redirect("/dashboard/" + rid)


@app.route("/staff_news/<rid>")
def staff_news(rid):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT title,message FROM staff_news WHERE restaurant_id=?", (rid,))
    news = c.fetchall()
    conn.close()
    return render_template("staff_news.html", news=news)


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
    name = request.form["name"]
    price = request.form["price"]
    # ✅ FIX: This ensures the app doesn't break if category is missing
    category = request.form.get("category", "food")
    image_file = request.files["image"]

    filename = image_file.filename
    image_file.save(os.path.join(UPLOAD_FOLDER, filename))

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
    INSERT INTO menu (restaurant_id, name, price, image, category) 
    VALUES (?, ?, ?, ?, ?)
    """, (rid, name, price, filename, category))

    conn.commit()
    conn.close()

    return redirect("/dashboard/" + rid)


# 🔹 (B) ADD AD ROUTE (NEW UPDATE)
@app.route("/add_ad/<rid>", methods=["POST"])
def add_ad(rid):
    import time
    title = request.form["title"]
    image = request.files["image"]

    filename = str(int(time.time())) + "_" + image.filename
    image.save(os.path.join(UPLOAD_FOLDER, filename))

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("INSERT INTO ads (restaurant_id,image,title) VALUES (?,?,?)",
              (rid, filename, title))
    conn.commit()
    conn.close()

    return redirect("/dashboard/" + rid)


@app.route("/generate_qr/<rid>", methods=["POST"])
def generate_qr(rid):
    table = request.form.get("table")

    # haddii table uusan jirin
    if not table:
        return "<p>Table number is required ❌</p>"

    # DOMAIN
    BASE_URL = "https://sahalserver.com"

    # QR URL
    url = f"{BASE_URL}/r/{rid}?table={table}"

    # QR GENERATOR
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

    # FILE NAME
    filename = f"qr_r{rid}_t{table}.png"

    # SAVE PATH
    path = os.path.join(QR_FOLDER, filename)

    # SAVE IMAGE
    img.save(path)

    # RETURN HTML WITH DOWNLOAD + PRINT
    return f"""
    <div style="margin-top:20px;text-align:center;">
        <img src="/static/qr/{filename}" 
             style="width:220px;border-radius:10px;">
        <br><br>

        <p><b>Table:</b> {table}</p>
        <p style="word-break:break-all;">{url}</p>

        <a href="/static/qr/{filename}" target="_blank"
           style="
           background:#0a7cff;
           color:white;
           padding:10px 15px;
           border-radius:8px;
           text-decoration:none;
           display:inline-block;
           margin:5px;
           ">
           Open QR
        </a>

        <a href="/static/qr/{filename}" download
           style="
           background:#28a745;
           color:white;
           padding:10px 15px;
           border-radius:8px;
           text-decoration:none;
           display:inline-block;
           margin:5px;
           ">
           ⬇ Download QR
        </a>

        <br><br>

        <button onclick="window.print()"
           style="
           background:#ff9800;
           color:white;
           padding:10px 15px;
           border:none;
           border-radius:8px;
           cursor:pointer;
           ">
           🖨 Print QR
        </button>
    </div>
    """
@app.route("/r/<int:rid>")
def restaurant_menu(rid):

    # ⏰ marka hore hubi expiry
    auto_check_expiry(rid)

    table = request.args.get("table", "00")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # 🔒 check haddii restaurant-ku disabled yahay
    c.execute("SELECT active FROM restaurants WHERE id=?", (rid,))
    status = c.fetchone()

    if not status:
        conn.close()
        return "<h1>Restaurant Not Found ❌</h1>"

    if status[0] == 0:
        conn.close()
        return """
        <h1>Subscription Expired ❌</h1>
        <p>This restaurant subscription has expired.</p>
        <p>Please contact admin for renewal.</p>
        """

    # 🍽️ MENU
    c.execute("SELECT * FROM menu WHERE restaurant_id=?", (rid,))
    food = c.fetchall()

    # 📢 ADS
    c.execute("SELECT * FROM ads WHERE restaurant_id=?", (rid,))
    ads = c.fetchall()

    # 🏪 RESTAURANT DATA
    c.execute("""
        SELECT payment_number, name
        FROM restaurants
        WHERE id=?
    """, (rid,))
    res_data = c.fetchone()

    # 📦 ORDER STATUS (table-kan)
    order_status = "waiting"

    if table:
        c.execute("""
            SELECT status
            FROM orders
            WHERE restaurant_id=? AND table_no=?
            ORDER BY id DESC
            LIMIT 1
        """, (rid, table))

        last_order = c.fetchone()

        if last_order:
            order_status = last_order[0]

    conn.close()

    # 🏪 restaurant data fallback
    if res_data:
        payment = res_data[0]
        name = res_data[1]
    else:
        payment = "No Payment Set"
        name = "Restaurant"

    return render_template(
        "customer.html",
        food=food,
        ads=ads,
        rid=rid,
        table=table,
        payment=payment,
        name=name,
        order_status=order_status
    )


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


@app.route("/update_status/<int:id>/<status>")
def update_status(id, status):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # ✅ update order status
    c.execute(
        "UPDATE orders SET status=? WHERE id=?",
        (status, id)
    )

    conn.commit()

    # ✅ xaqiiji update
    c.execute("""
        SELECT id, status, restaurant_id
        FROM orders
        WHERE id=?
    """, (id,))

    result = c.fetchone()
    conn.close()

    if result:
        return {
            "success": True,
            "message": f"Status updated to {result[1]} ✅",
            "status": result[1],
            "order_id": result[0]
        }
    else:
        return {
            "success": False,
            "message": "Order not found ❌"
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
    table = request.form["table"]
    time = datetime.now().strftime("%H:%M")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("""
    INSERT INTO waiter_calls(restaurant_id,table_no,time)
    VALUES(?,?,?)
    """, (rid, table, time))
    conn.commit()
    conn.close()
    return "ok"


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
# 🍳 KITCHEN ROUTE (FIXED)
# =========================
@app.route("/kitchen/<int:rid>", methods=["GET", "POST"])
def kitchen(rid):

    auto_check_expiry(rid)

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # GET PASSWORD
    c.execute("SELECT kitchen_password FROM restaurants WHERE id=?", (rid,))
    data = c.fetchone()

    real_pass = data[0] if data else None

    # haddii user login sameeyo
    if request.method == "POST":
        user_pass = request.form.get("password")

        if user_pass != real_pass:
            conn.close()
            return render_template("kitchen_login.html", rid=rid, error="Wrong password")

        # save session
        session["kitchen_"+str(rid)] = True

    # haddii aan login jirin
    if not session.get("kitchen_"+str(rid)):
        conn.close()
        return render_template("kitchen_login.html", rid=rid)

    try:
        # GET ORDERS
        c.execute("SELECT * FROM orders WHERE restaurant_id=? ORDER BY id DESC", (rid,))
        orders = c.fetchall()

        # GET WAITER CALLS
        c.execute("SELECT * FROM waiter_calls WHERE restaurant_id=? ORDER BY id DESC", (rid,))
        calls = c.fetchall()

        # AI MESSAGES
        c.execute("SELECT * FROM ai_messages WHERE restaurant_id=? ORDER BY id DESC", (rid,))
        ai_messages = c.fetchall()

    except Exception as e:
        print("KITCHEN ERROR:", e)
        orders = []
        calls = []
        ai_messages = []

    conn.close()

    return render_template(
        "kitchen.html",
        orders=orders,
        calls=calls,
        ai_messages=ai_messages,
        rid=rid
    )

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
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("DELETE FROM orders WHERE restaurant_id=?", (rid,))
    conn.commit()
    conn.close()
    return "ok"


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
