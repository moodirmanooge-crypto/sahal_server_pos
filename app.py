from flask import Flask, render_template, request, redirect, jsonify, session
import sqlite3
import os
import qrcode
import socket
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = "static/uploads"
QR_FOLDER = "static/qr"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)


def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()
    finally:
        s.close()
    return ip

SERVER_IP = get_ip()


import sqlite3

# DATABASE
def init_db():
    print("INIT DB RUNNING...")  # 👈 si aad u aragto inuu shaqeynayo

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # RESTAURANTS
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

    # MENU
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

    # AI MESSAGES
    c.execute("""
    CREATE TABLE IF NOT EXISTS ai_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        restaurant_id INTEGER,
        table_no TEXT,
        message TEXT,
        time TEXT
    )
    """)

    # ADS
    c.execute("""
    CREATE TABLE IF NOT EXISTS ads(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER,
    image TEXT,
    title TEXT
    )
    """)

    # ORDERS
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

    # WAITER CALLS
    c.execute("""
    CREATE TABLE IF NOT EXISTS waiter_calls(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER,
    table_no TEXT,
    time TEXT
    )
    """)

    # STAFF
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

    # STAFF NEWS
    c.execute("""
    CREATE TABLE IF NOT EXISTS staff_news(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER,
    title TEXT,
    message TEXT
    )
    """)

    # RENEW REQUESTS
    c.execute("""
    CREATE TABLE IF NOT EXISTS renew_requests(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER,
    time TEXT
    )
    """)

    # 🔐 SETTINGS TABLE
    c.execute("""
    CREATE TABLE IF NOT EXISTS settings(
    id INTEGER PRIMARY KEY,
    admin_password TEXT,
    register_password TEXT
    )
    """)

    # 👉 default passwords (HAL MAR KALIYA)
    c.execute("SELECT * FROM settings WHERE id=1")
    if not c.fetchone():
        c.execute("INSERT INTO settings (id, admin_password, register_password) VALUES (1, '8880', '8880')")

    conn.commit()
    conn.close()

    print("DATABASE READY ✅")

@app.route("/")
def home():
    return render_template("home.html")


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
    return redirect("/admin")


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

@app.route("/register", methods=["GET", "POST"])
def register():

    # password check
    if request.method == "POST" and "access_password" in request.form:

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        c.execute("SELECT register_password FROM settings WHERE id=1")
        real_pass = c.fetchone()[0]

        if request.form.get("access_password") != real_pass:
            conn.close()
            return render_template("access_register.html", error="Wrong password")

        conn.close()
        return render_template("register.html")

    # register form
    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")
        username = request.form.get("username")
        password = request.form.get("password")
        price = request.form.get("price")
        payment = request.form.get("payment")

        kitchen_pass = str(os.urandom(2).hex())
        expiry = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        c.execute("""
        INSERT INTO restaurants(
            name, phone, username, password,
            price, expiry, active,
            payment_number, kitchen_password
        )
        VALUES(?,?,?,?,?,?,?,?,?)
        """, (
            name, phone, username, password,
            price, expiry, 1, payment, kitchen_pass
        ))

        conn.commit()
        conn.close()

        return redirect("/login")

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

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # check active status
    c.execute("SELECT active FROM restaurants WHERE id=?", (rid,))
    status = c.fetchone()

    if status and status[0] == 0:
        conn.close()
        return render_template("renew.html", rid=rid)

    # MENU
    c.execute("SELECT * FROM menu WHERE restaurant_id=?", (rid,))
    menu = c.fetchall()

    # ADS
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
@app.route("/restaurant_admin/<int:rid>", methods=["GET","POST"])
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

    # ✅ DOMAIN-KA SAXDA AH
    BASE_URL = "https://sahalserver.com"

    # ✅ QR URL
    url = f"{BASE_URL}/r/{rid}?table={table}"

    # ✅ QR GENERATOR
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

    # ✅ FILE NAME
    filename = f"qr_r{rid}_t{table}.png"

    # ✅ SAVE PATH
    path = os.path.join(QR_FOLDER, filename)

    # ✅ SAVE IMAGE
    img.save(path)

    # ✅ RETURN QR PAGE
    return render_template(
        "qr.html",
        img=filename,
        table=table,
        rid=rid,
        url=url
    )
@app.route("/r/<int:rid>")
def restaurant_menu(rid):

    table = request.args.get("table")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # 🍽️ MENU
    c.execute("SELECT * FROM menu WHERE restaurant_id=?", (rid,))
    food = c.fetchall()

    # 📢 ADS
    c.execute("SELECT * FROM ads WHERE restaurant_id=?", (rid,))
    ads = c.fetchall()

    # 🏪 RESTAURANT DATA
    c.execute("SELECT payment_number, name FROM restaurants WHERE id=?", (rid,))
    res_data = c.fetchone()

    conn.close()

    # ✅ HANDLE haddii uusan jirin
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
        name=name
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


@app.route("/update_status/<oid>/<status>")
def update_status(oid, status):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("UPDATE orders SET status=? WHERE id=?", (status, oid))
    conn.commit()
    conn.close()
    return "ok"


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
@app.route("/kitchen/<rid>", methods=["GET", "POST"])
def kitchen(rid):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # GET REAL PASSWORD
    c.execute("SELECT kitchen_password FROM restaurants WHERE id=?", (rid,))
    data = c.fetchone()

    real_pass = data[0] if data else None

    if request.method == "POST":
        user_pass = request.form["password"]

        if user_pass != real_pass:
            conn.close()
            return render_template("kitchen_login.html", rid=rid, error="Wrong password")

        # GET ORDERS
        c.execute("SELECT * FROM orders WHERE restaurant_id=? ORDER BY id DESC", (rid,))
        orders = c.fetchall()

        # GET WAITER CALLS
        c.execute("SELECT * FROM waiter_calls WHERE restaurant_id=? ORDER BY id DESC", (rid,))
        calls = c.fetchall()

        # ✅ NEW: AI MESSAGES
        c.execute("SELECT * FROM ai_messages WHERE restaurant_id=? ORDER BY id DESC", (rid,))
        ai_messages = c.fetchall()

        conn.close()
        return render_template("kitchen.html",
                               orders=orders,
                               rid=rid,
                               calls=calls,
                               ai_messages=ai_messages)

    conn.close()
    return render_template("kitchen_login.html", rid=rid)


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


# ====== HA TAABANIN ======
if __name__ == "__main__":
    print(f"SERVER RUNNING ON: http://{SERVER_IP}:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
