"""
EkromVPN Web — สั่งซื้อ + จ่าย QR + สลิป + รับ Config (เหมือน LINE Bot)
"""
import sys, os, time, hashlib, secrets, json
from urllib.request import urlopen, Request
from datetime import datetime, timedelta, timezone
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from xui_client import XUIDBClient
from config_generator import generate_vmess_link, generate_vless_link, generate_qr_code
from slipok_client import check_slip_by_url
from promptpay import generate_promptpay_qr
from bank_config import get_promptpay_id, get_bank_info_display
from server_details import SERVER_DETAILS

# ===== Google reCAPTCHA =====
RECAPTCHA_SITE_KEY = "6LcTjmwtAAAAAGgp7Qufe1puB1xMmnmvBjPBq5G9"
RECAPTCHA_SECRET_KEY = "6LcTjmwtAAAAAKJpq4X1-4tON_yytKwdBOGzbcpY"

def verify_recaptcha(response_token):
    try:
        data = f"secret={RECAPTCHA_SECRET_KEY}&response={response_token}".encode()
        req = Request("https://www.google.com/recaptcha/api/siteverify", data=data)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        res = json.loads(urlopen(req).read())
        return res.get("success", False)
    except:
        return False

from flask import (Flask, render_template, request, jsonify, session,
                   redirect, url_for, g, flash)

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# ===== DB =====
import sqlite3
DB_PATH = "/root/hermes-commerce/web_users.db"

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db: db.close()

def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                package TEXT, server_id TEXT,
                amount REAL, status TEXT DEFAULT 'pending',
                config_link TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
        # Auto-create admin
        admin_pass = hashlib.sha256("admin123".encode()).hexdigest()
        db.execute("INSERT OR IGNORE INTO users (username, password) VALUES (?, ?)",
                  ["admin", admin_pass])
init_db()

# ===== Auth =====
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('register'))
        return f(*args, **kwargs)
    return decorated

@app.route("/login", methods=["GET","POST"])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    if request.method == "POST":
        # reCAPTCHA verify
        recaptcha_resp = request.form.get("g-recaptcha-response", "")
        if not verify_recaptcha(recaptcha_resp):
            flash("กรุณายืนยันว่าไม่ใช่โปรแกรมอัตโนมัติ", "error")
            return render_template("login.html", site_key=RECAPTCHA_SITE_KEY)
        username = request.form.get("username", "")
        password = hashlib.sha256(request.form.get("password", "").encode()).hexdigest()
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=? AND password=?", 
                         (username, password)).fetchone()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('index'))
        flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "error")
    return render_template("login.html", site_key=RECAPTCHA_SITE_KEY)

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        # reCAPTCHA verify
        recaptcha_resp = request.form.get("g-recaptcha-response", "")
        if not verify_recaptcha(recaptcha_resp):
            flash("กรุณายืนยันว่าไม่ใช่โปรแกรมอัตโนมัติ", "error")
            return render_template("register.html", site_key=RECAPTCHA_SITE_KEY)
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        if len(username) < 3 or len(password) < 4:
            flash("ชื่อผู้ใช้ 3 ตัวขึ้นไป รหัสผ่าน 4 ตัวขึ้นไป", "error")
            return render_template("register.html")
        hashed = hashlib.sha256(password.encode()).hexdigest()
        db = get_db()
        try:
            db.execute("INSERT INTO users (username, password) VALUES (?,?)", (username, hashed))
            db.commit()
            flash("สมัครสำเร็จ! เข้าสู่ระบบได้เลย", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("ชื่อผู้ใช้นี้มีอยู่แล้ว", "error")
    return render_template("register.html", site_key=RECAPTCHA_SITE_KEY)

@app.route("/forgot-password", methods=["GET","POST"])
def forgot_password():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        new_pass = request.form.get("new_password", "")
        if len(new_pass) < 4:
            flash("รหัสผ่านต้อง 4 ตัวขึ้นไป", "error")
            return render_template("forgot_password.html")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not user:
            flash("ไม่พบชื่อผู้ใช้นี้", "error")
            return render_template("forgot_password.html")
        hashed = hashlib.sha256(new_pass.encode()).hexdigest()
        db.execute("UPDATE users SET password=? WHERE username=?", (hashed, username))
        db.commit()
        flash("ตั้งรหัสผ่านใหม่สำเร็จ! เข้าสู่ระบบได้เลย", "success")
        return redirect(url_for('login'))
    return render_template("forgot_password.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('register'))
@app.route("/")
def index():
    if 'user_id' not in session:
        return redirect(url_for('register'))
    return render_template("index.html", user=session.get('username'), line_oa="@578infzg")

@app.route("/server/<server_id>")
def server_detail(server_id):
    detail = SERVER_DETAILS.get(server_id)
    if not detail:
        return redirect(url_for("index"))
    return render_template("server_detail.html", detail=detail, server_id=server_id,
                         user=session.get('username'), line_oa="@578infzg")

@app.route("/order", methods=["GET","POST"])
def order_page():
    if 'user_id' not in session:
        return redirect(url_for('register'))
    if request.method == "POST":
        pkg_key = request.form.get("package","1")
        server_id = request.form.get("server","1")
        name = request.form.get("name","").strip()
        phone = request.form.get("phone","").strip()
        if not name:
            return jsonify({"error":"กรุณากรอกชื่อ"}), 400
        pkg = config.PACKAGES.get(pkg_key, config.PACKAGES["1"])
        session["order"] = {
            "order_id": str(int(time.time()))[-6:],
            "package": pkg_key, "server": server_id,
            "name": name, "phone": phone,
            "price": pkg["price"], "pkg_name": pkg["name"],
        }
        return redirect(url_for("payment_page"))
    return render_template("order.html", packages=config.PACKAGES, user=session.get('username'))

@app.route("/payment")
def payment_page():
    order = session.get("order")
    if not order:
        return redirect(url_for("index"))
    pp_id = get_promptpay_id()
    qr_filename = f"pay_{order['order_id']}.png"
    qr_path = generate_promptpay_qr(pp_id, order["price"], qr_filename)
    qr_url = f"/static/{qr_filename}" if qr_path else None
    bank_info = get_bank_info_display()
    return render_template("payment.html", order=order, qr_url=qr_url, 
                         bank_info=bank_info, user=session.get('username'))

@app.route("/api/check-slip", methods=["POST"])
def api_check_slip():
    order = session.get("order")
    if not order:
        return jsonify({"error":"ไม่มีคำสั่งซื้อ"}), 400
    image_file = request.files.get("slip")
    if not image_file:
        return jsonify({"error":"กรุณาเลือกรูปสลิป"}), 400
    ext = image_file.filename.split(".")[-1] if "." in image_file.filename else "jpg"
    temp_path = f"/root/hermes-commerce/temp_images/slip_{order['order_id']}.{ext}"
    image_file.save(temp_path)
    image_url = f"https://{config.SERVER_DOMAIN}/temp_images/slip_{order['order_id']}.{ext}"
    
    slip_data = check_slip_by_url(image_url, amount=order["price"])
    if slip_data:
        result = create_vpn_user({
            "package": order["package"], "server": order["server"],
            "name": order["name"], "phone": order.get("phone",""),
        })
        if result:
            session["result"] = result
            session["slip_data"] = slip_data
            # Save order
            db = get_db()
            db.execute("INSERT INTO orders (user_id,package,server_id,amount,status,config_link) VALUES (?,?,?,?,'completed',?)",
                      [session['user_id'], order["package"], order["server"], 
                       order["price"], result['vmess_link']])
            db.commit()
            return jsonify({"success":True, "redirect": url_for("success_page")})
        return jsonify({"error":"สร้างบัญชีไม่สำเร็จ"}), 500
    return jsonify({"error":"ตรวจสอบสลิปไม่สำเร็จ กรุณาลองใหม่"}), 400

@app.route("/success")
def success_page():
    result = session.get("result")
    slip_data = session.get("slip_data")
    order = session.get("order")
    if not result:
        return redirect(url_for("index"))
    qr_filename = f"config_{order['order_id']}.png"
    qr_path = generate_qr_code(result["vmess_link"], qr_filename)
    qr_url = f"/static/{qr_filename}" if qr_path else None
    return render_template("success.html", result=result, slip_data=slip_data, 
                         qr_url=qr_url, user=session.get('username'))

@app.route("/member")
@login_required
def member_page():
    db = get_db()
    orders = db.execute("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC",
                       [session['user_id']]).fetchall()
    return render_template("member.html", user=session.get('username'), orders=orders)

# ===== API create user =====
def create_vpn_user(order):
    pkg = config.PACKAGES.get(order["package"], config.PACKAGES["1"])
    inbound_id = int(order["server"])
    email = f"{order['phone']}-{order['name']}" if order.get('phone') else order['name']
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(days=pkg["days"])
    thai_months = ["","ม.ค.","ก.พ.","มี.ค.","เม.ย.","พ.ค.","มิ.ย.",
                   "ก.ค.","ส.ค.","ก.ย.","ต.ค.","พ.ย.","ธ.ค."]
    expiry_str = f"{expiry.day}/{thai_months[expiry.month]}/{expiry.year + 543}"
    xui = XUIDBClient()
    result = xui.add_client(inbound_id=inbound_id, email=email,
                           limit_ip=pkg["limit_ip"], total_gb=pkg["total_gb"],
                           expiry_time=int(expiry.timestamp()*1000))
    if not result:
        return None
    xui.restart_xui()
    time.sleep(2)
    if inbound_id == 4:
        vmess_link = generate_vless_link(result["client_id"], email, inbound_id)
    else:
        vmess_link = generate_vmess_link(result["client_id"], email, inbound_id)
    return {"vmess_link": vmess_link, "email": email,
            "package_name": pkg["name"], "expiry_str": expiry_str}

# ===== Static =====
@app.route("/static/<filename>")
def static_files(filename):
    from flask import send_from_directory
    return send_from_directory("/root/hermes-commerce/configs", filename)

@app.route("/temp_images/<filename>")
def temp_images(filename):
    from flask import send_from_directory
    return send_from_directory("/root/hermes-commerce/temp_images", filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8445, debug=True)
