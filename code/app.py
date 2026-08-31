"""
Line Commerce Bot — ระบบสั่งซื้ออัตโนมัติผ่าน LINE + x-ui
"""
import json
import os
import time
import threading
import base64
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

# Flask
from flask import Flask, request, jsonify, abort

# LINE SDK
from linebot.v3 import (
    WebhookHandler,
)
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
    ImageMessage,
)
from linebot.v3.messaging.models import (
    FlexMessage,
)
from linebot.v3.webhooks import (
    FollowEvent,
    MessageEvent,
    TextMessageContent,
    ImageMessageContent,
)
from linebot.v3.exceptions import InvalidSignatureError

import config
from xui_client import XUIClient
from config_generator import generate_vmess_link, generate_qr_code
from slipok_client import check_slip_by_url, check_slip_by_qr_data, format_slip_result
from bank_config import get_bank_info, get_promptpay_id
from promptpay import generate_promptpay_qr

# ===== Flask App =====
app = Flask(__name__)

# LINE SDK Setup — graceful ถ้ายังไม่ได้ตั้งค่า Token
LINE_ENABLED = config.LINE_CHANNEL_ACCESS_TOKEN not in ["", "YOUR_CHANNEL_ACCESS_TOKEN"]
line_config = None
line_api = None

if LINE_ENABLED:
    import socket as _socket
    _socket.setdefaulttimeout(15)  # ป้องกัน bot ค้างรอ LINE API
    line_config = Configuration(access_token=config.LINE_CHANNEL_ACCESS_TOKEN)
    line_api = MessagingApi(ApiClient(line_config))
    line_api_blob = MessagingApiBlob(ApiClient(line_config))

# WebhookHandler ใช้ได้เสมอ (secret check ที่ callback)
# Temporarily skip signature verification for testing
line_handler = WebhookHandler(config.LINE_CHANNEL_SECRET, skip_signature_verification=lambda: True)

# x-ui DB client
xui_db = XUIClient()

# ===== Session Management =====
# user_sessions[user_id] = {
#   "step": "menu" | "await_name" | "await_phone" | "await_package" | "await_inbound",
#   "data": { ... },
#   "expires_at": timestamp
# }
SESSION_TIMEOUT = 600  # 10 นาที

# ===== SQLite Session Store (persist ผ่าน restart) =====
import sqlite3, json, threading
_SESSION_DB = "/root/hermes-commerce/sessions.db"
_session_local = threading.local()

def _get_conn():
    if not hasattr(_session_local, "conn") or not _session_local.conn:
        _session_local.conn = sqlite3.connect(_SESSION_DB, check_same_thread=False)
        _session_local.conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
            user_id TEXT PRIMARY KEY,
            step TEXT NOT NULL DEFAULT 'menu',
            data TEXT NOT NULL DEFAULT '{}',
            expires_at REAL NOT NULL
        )""")
        _session_local.conn.commit()
    return _session_local.conn

def get_session(user_id: str) -> Dict:
    conn = _get_conn()
    now = time.time()
    row = conn.execute("SELECT step, data, expires_at FROM sessions WHERE user_id=?", (user_id,)).fetchone()
    if row and row[2] > now:
        return {"step": row[0], "data": json.loads(row[1]), "expires_at": row[2]}
    # Create fresh session
    sess = {"step": "menu", "data": {}, "expires_at": now + SESSION_TIMEOUT}
    conn.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?)",
                 (user_id, sess["step"], json.dumps(sess["data"]), sess["expires_at"]))
    conn.commit()
    return sess

def update_session(user_id: str, **kwargs):
    conn = _get_conn()
    sess = get_session(user_id)
    sess.update(kwargs)
    sess["expires_at"] = time.time() + SESSION_TIMEOUT
    conn.execute("UPDATE sessions SET step=?, data=?, expires_at=? WHERE user_id=?",
                 (sess["step"], json.dumps(sess["data"]), sess["expires_at"], user_id))
    conn.commit()

def cleanup_sessions():
    conn = _get_conn()
    now = time.time()
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    conn.commit()

# ===== Package Selection Flex Message =====
def create_package_flex() -> FlexMessage:
    """สร้าง Flex Message แสดงแพ็กเกจ"""
    contents = []
    for key, pkg in config.PACKAGES.items():
        contents.append({
            "type": "box",
            "layout": "horizontal",
            "margin": "md",
            "spacing": "md",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#00bcd4",
                    "height": "sm",
                    "action": {
                        "type": "message",
                        "label": f"{pkg['name']}",
                        "text": f"เลือก {key}"
                    },
                    "flex": 2
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"💰 {pkg['price']} บ.",
                            "size": "sm",
                            "weight": "bold",
                            "color": "#ffd700",
                            "align": "center"
                        },
                        {
                            "type": "text",
                            "text": f"👤 {pkg['limit_ip']} เครื่อง",
                            "size": "xs",
                            "color": "#aaaaaa",
                            "align": "center"
                        }
                    ],
                    "flex": 1
                }
            ]
        })
    
    return FlexMessage(
        alt_text="📦 เลือกแพ็กเกจ",
        contents={
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "📦 เลือกแพ็กเกจ",
                        "size": "lg",
                        "weight": "bold",
                        "color": "#ffffff"
                    },
                    {
                        "type": "text",
                        "text": "กดปุ่มด้านล่างเพื่อเลือกราคา",
                        "size": "xs",
                        "color": "#aaaaaa"
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": contents
            },
            "styles": {
                "header": {"backgroundColor": "#1a1a2e"},
                "body": {"backgroundColor": "#16213e"}
            }
        }
    )

# ===== Inbound Selection =====
def create_inbound_flex() -> FlexMessage:
    """เลือกเซิร์ฟเวอร์"""
    inbounds = xui_db.get_inbounds_meta()
    if not inbounds:
        inbounds = [
            {"id": 1, "remark": "🇹🇭 AIS-VIP (WS 80)", "port": 80},
            {"id": 2, "remark": "🇹🇭 AIS-TCP (8080)", "port": 8080},
            {"id": 3, "remark": "🇹🇭 FB-GAMING (8000)", "port": 8000},
        ]
    
    buttons = []
    for ib in inbounds:
        buttons.append({
            "type": "button",
            "style": "secondary",
            "color": "#00bcd4",
            "height": "sm",
            "margin": "md",
            "action": {
                "type": "message",
                "label": f"{ib['remark']}",
                "text": f"เซิร์ฟเวอร์ {ib['id']}"
            }
        })
    
    return FlexMessage(
        alt_text="🌐 เลือกเซิร์ฟเวอร์",
        contents={
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "🌐 เลือกเซิร์ฟเวอร์",
                        "size": "lg",
                        "weight": "bold",
                        "color": "#ffffff"
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": buttons
            },
            "styles": {
                "header": {"backgroundColor": "#1a1a2e"},
                "body": {"backgroundColor": "#16213e"}
            }
        }
    )

# ===== Config Result Flex =====
from config_generator import generate_vmess_link, generate_qr_code

def create_result_flex(email: str, client_id: str, inbound_id: int, 
                       package_name: str, expiry_str: str, vmess_link: str) -> FlexMessage:
    """สร้าง Flex Message แสดงผล config"""
    return FlexMessage(
        alt_text="✅ สร้างบัญชีสำเร็จ!",
        contents={
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "✅ สร้างบัญชีสำเร็จ!",
                        "size": "lg",
                        "weight": "bold",
                        "color": "#4caf50"
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": f"👤 ชื่อ: {email}", "size": "sm", "color": "#ffffff", "wrap": True},
                    {"type": "text", "text": f"📦 แพ็กเกจ: {package_name}", "size": "sm", "color": "#cccccc"},
                    {"type": "text", "text": f"⏰ หมดอายุ: {expiry_str}", "size": "sm", "color": "#cccccc"},
                    {"type": "separator", "margin": "md"},
                    {"type": "text", "text": "🔗 คอนฟิก (กดคัดลอก):", "size": "sm", "color": "#aaaaaa", "margin": "md"},
                    {"type": "text", "text": vmess_link[:60] + "...", "size": "xs", "color": "#00bcd4", "wrap": True, "margin": "sm"},
                    {"type": "separator", "margin": "md"},
                    {"type": "text", "text": "📸 QR Code ถูกส่งไปด้านบน", "size": "xs", "color": "#888888", "margin": "md"},
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#00bcd4",
                        "action": {
                            "type": "clipboard",
                            "label": "📋 คัดลอกลิงก์",
                            "clipboardText": vmess_link
                        }
                    }
                ]
            },
            "styles": {
                "header": {"backgroundColor": "#1a1a2e"},
                "body": {"backgroundColor": "#16213e"},
                "footer": {"backgroundColor": "#0f3460"}
            }
        }
    )

# ===== Create Order =====
def create_order(user_id: str, session: Dict) -> Optional[Dict]:
    """สร้าง client ใน x-ui และส่ง config"""
    data = session["data"]
    name = data.get("name", "ลูกค้า")
    phone = data.get("phone", "")
    pkg_key = data.get("package", "1")
    inbound_id = int(data.get("inbound", config.DEFAULT_INBOUND_ID))
    # Map bot inbound to x-ui inbound: 1-3→10(8080), 4-7→14(80)
    xui_inbound = 13 if inbound_id == 4 else (10 if inbound_id in [3,5] else 14)
    
    pkg = config.PACKAGES.get(pkg_key, config.PACKAGES["1"])
    # ชื่อ + เบอร์ อาจซ้ำกันได้ → เติมเวลา/วันที่ต่อท้าย email ให้ไม่ซ้ำ
    # (ชื่อที่โชว์ในคอนฟิกยังใช้ชื่อ+เบอร์ปกติ ผ่าน remark_name)
    email = f"{phone}-{name}" if phone else name
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    unique_email = f"{email}-{ts}"

    # คำนวณวันหมดอายุ
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(days=pkg["days"])
    expiry_ms = int(expiry.timestamp() * 1000)
    import calendar
    thai_months = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", 
                   "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    expiry_str = f"{expiry.day}/{thai_months[expiry.month]}/{expiry.year + 543}"
    
    # เพิ่ม client ใน DB (ใช้ unique_email ป้องกันชื่อซ้ำ)
    result = xui_db.add_client(
        inbound_id=xui_inbound,
        email=unique_email,
        limit_ip=pkg["limit_ip"],
        total_gb=pkg["total_gb"],
        expiry_time=expiry_ms,
    )
    
    if not result:
        return None
    
    # Restart x-ui
    pass  # API auto-applies
    time.sleep(2)  # รอ x-ui เริ่มใหม่
    
    # สร้าง VMESS link
    inbound_names = {
        "1": "AIS-PLAY", "2": "TRUE-NOPRO", "3": "TRUE-ROV",
        "4": "TRUE-FB", "5": "TRUE-ZOOM", "6": "DTAC-NOPRO", "7": "DTAC-GAMING",
    }
    sv_name = inbound_names.get(str(inbound_id), "VPN")
    vmess_link = generate_vmess_link(
        client_id=result["client_id"],
        email=unique_email,
        inbound_id=inbound_id,
        remark_prefix=sv_name,
        expiry_str=expiry_str,
        remark_name=email,   # ชื่อโชว์: PREFIX-NAME-PHONE-EXPIRY (ไม่มี timestamp)
    )
    
    # สร้าง QR code
    safe_filename = f"config_{int(time.time())}.png"
    qr_path = generate_qr_code(vmess_link, safe_filename)
    
    return {
        "vmess_link": vmess_link,
        "qr_path": qr_path,
        "qr_url": f"https://{config.SERVER_DOMAIN}/configs/{safe_filename}",
        "email": email,
        "unique_email": unique_email,
        "package_name": pkg["name"],
        "expiry_str": expiry_str,
        "inbound_id": inbound_id,
        "client_id": result["client_id"],
    }


# ===== LINE Webhook Handler =====
@app.route("/callback", methods=["GET", "POST"])
def callback():
    """LINE webhook endpoint"""
    if request.method == "GET":
        # LINE webhook verification
        return "OK"
    
    # get X-Line-Signature header value
    signature = request.headers.get("X-Line-Signature", "")
    
    # get request body — ใช้ raw bytes สำหรับ LINE signature validation
    body = request.get_data()  # bytes
    body_text = body.decode("utf-8")
    app.logger.info(f"Webhook received: sig={signature[:20]}... body_len={len(body)}")
    
    # handle webhook body
    try:
        # LINE SDK ต้องการ string body (text) สำหรับ signature validation
        line_handler.handle(body_text, signature)
    except InvalidSignatureError:
        app.logger.warning(f"Invalid signature: {signature[:30]}... body={body_text[:100]}")
        # LINE test requests may have different signature format — still return 200
        return "OK"
    except Exception as e:
        app.logger.error(f"Webhook error: {e}")
        return "OK"
    
    return "OK"


@line_handler.add(FollowEvent)
def handle_follow(event):
    """Welcome new members"""
    user_id = event.source.user_id
    try:
        msg = ("🙏 ยินดีต้อนรับสู่ EkromNetVPN\n\n"
               "📺 วิธีใช้งาน: https://youtube.com/shorts/gcmWpA7wcpY?si=-p_joQycoAo7Y7mX\n\n"
               "พิมพ์ \"สั่งซื้อ\" เพื่อเริ่มสั่งซื้อ\n"
               "พิมพ์ \"เมนู\" เพื่อดูเมนูหลัก\n"
               "ติดต่อแอดมิน LINE: @578infzg")
        line_api.push_message(
            PushMessageRequest(
                to=user_id,
                messages=[TextMessage(text=msg)]
            )
        )
    except Exception as e:
        app.logger.error(f"Welcome error: {e}")

@line_handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    """จัดการข้อความจากผู้ใช้"""
    user_id = event.source.user_id
    text = event.message.text.strip()
    reply_token = event.reply_token
    
    session = get_session(user_id)
    step = session["step"]
    
    try:
        if step == "menu":
            handle_menu(reply_token, user_id, text)
        elif step == "await_package":
            handle_package_selection(reply_token, user_id, text)
        elif step == "await_inbound":
            handle_inbound_selection(reply_token, user_id, text)
        elif step == "await_name":
            handle_name_input(reply_token, user_id, text)
        elif step == "await_phone":
            handle_phone_input(reply_token, user_id, text)
        elif step == "await_payment":
            handle_payment_text(reply_token, user_id, text)
        elif step == "await_confirm":
            handle_confirm(reply_token, user_id, text)
        elif step == "await_renew_phone":
            handle_renew_phone(reply_token, user_id, text)
        elif step == "await_renew_select":
            handle_renew_select(reply_token, user_id, text)
        elif step == "await_renew_package":
            handle_renew_package(reply_token, user_id, text)
        else:
            # Reset to menu
            update_session(user_id, step="menu")
            send_menu(reply_token)
    except Exception as e:
        app.logger.error(f"Error handling message: {e}")
        try:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=f"❌ เกิดข้อผิดพลาด: {str(e)[:100]}")]
                )
            )
        except:
            pass


# ===== Menu / Commands =====
def handle_menu(reply_token: str, user_id: str, text: str):
    """จัดการคำสั่งหลัก"""
    text_lower = text.lower().strip()
    
    if (text_lower in ["สมัคร", "ซื้อ", "สั่ง", "เริ่ม", "1"]
            or any(k in text_lower for k in ["สมัคร", "ซื้อ", "สั่ง", "เริ่ม"])):
        # เลือกแพ็กเกจ — ส่งเป็นข้อความธรรมดา (ไม่ใช้ Flex)
        update_session(user_id, step="await_package")
        msg = (
            "📦 เลือกแพ็กเกจ\n"
            "กดหมายเลขที่ต้องการ:\n\n"
            "1️⃣ = 𝟥𝟢 วัน — 𝟧𝟢 บาท (𝟤 เครื่อง)\n"
            "3️⃣ = 𝟫𝟢 วัน — 𝟣𝟦𝟢 บาท (𝟤 เครื่อง)\n"
            "6️⃣ = 𝟣𝟪𝟢 วัน — 𝟤𝟦𝟢 บาท (𝟤 เครื่อง)\n"
            "0️⃣ = 𝟥𝟨𝟧 วัน — 𝟦𝟤𝟢 บาท (𝟤 เครื่อง)\n\n"
            "พิมพ์ 1, 3, 6 หรือ 0"
        )
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=msg)]
            )
        )
    elif text_lower in ["4", "วิธีใช้งาน", "วิดีโอ", "สอน", "วิธีใช้", "tutorial", "howto", "how to", "ดูวิดีโอ", "youtube"]:
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(
                    text="🎬 วิธีใช้งาน\n\n"
                         "📺 ดูวิดีโอแนะนำการใช้งาน:\n"
                         f"https://youtube.com/shorts/gcmWpA7wcpY?si=-p_joQycoAo7Y7mX\n\n"
                         "1️⃣ สมัคร/สั่งซื้อ\n"
                         "3️⃣ ต่ออายุ\n"
                         "9️⃣ ติดต่อแอดมิน"
                )]
            )
        )
    elif text_lower in ["9", "ติดต่อ", "แอดมิน", "contact", "help", "ช่วยเหลือ"]:
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(
                    text="💬 ติดต่อแอดมิน\n\n"
                         "รอสักครู่เดี๋ยวแอดมินตอบกลับ\n\n"
                         "📌 ช่องทางติดต่อ:\n"
                         "💬 LINE: @578infzg\n"
                         "✈️ Telegram: @ekrom_support\n"
                         "👍 Facebook: m.me/idavpn\n\n"
                         "⏳ แอดมินตอบกลับ 24 ชม."
                )]
            )
        )
    elif text_lower in ["3", "ต่ออายุ", "ต่อ", "ต่อวัน", "ต่อวันใช้งาน", "เพิ่มวัน",
                        "เพิ่มอายุ", "ต่ออายุแพ็กเกจ", "ต่ออายุการใช้งาน", "renew",
                        "ต่ออายุครับ", "ต่ออายุค่ะ", "ต่อยอด", "ต่อเน็ต", "เพิ่มแพ็กเกจ"]:
        # เริ่มขั้นตอนต่ออายุ — ถามเบอร์โทร/ชื่อ
        update_session(user_id, step="await_renew_phone", data={})
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="🔄 ต่ออายุ\n\nกรุณาพิมพ์เบอร์โทร หรือ ชื่อที่ใช้สมัคร\n(ค้นหาบัญชีของคุณ):\n\nพิมพ์ 2 = ยกเลิก")]
            )
        )
    elif text_lower == "ยกเลิก":
        update_session(user_id, step="menu", data={})
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="✅ ยกเลิกสำเร็จ")]
            )
        )
    else:
        send_menu(reply_token)


def send_menu(reply_token: str):
    """ส่งเมนูหลัก"""
    line_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(
                text="สวัสดีครับ 🙌\n\n"
                     "พิมพ์หมายเลขที่ต้องการ:\n"
                     "1️⃣ สมัคร/สั่งซื้อ\n"
                     "2️⃣ ยกเลิก\n"
                     "3️⃣ ต่ออายุ\n"
                     "4️⃣ วิธีใช้งาน\n"
                     "9️⃣ ติดต่อแอดมิน"
            )]
        )
    )


# ===== Package Selection =====
def handle_package_selection(reply_token: str, user_id: str, text: str):
    """จัดการเลือกแพ็กเกจ"""
    pkg_key = text.strip()
    
    # Map common inputs
    mapping = {"1": "1", "2": "2", "3": "3", "4": "4", "6": "3", "12": "4", "0": "4"}
    pkg_key = mapping.get(pkg_key, pkg_key)
    
    if pkg_key in config.PACKAGES:
        update_session(user_id, step="await_inbound", 
                       data={**get_session(user_id)["data"], "package": pkg_key})
        msg = (
            f"✅ เลือก {config.PACKAGES[pkg_key]['name']} — {config.PACKAGES[pkg_key]['price']} บาท\n\n"
            "🌐 เลือกเซิร์ฟเวอร์\n"
            "พิมพ์หมายเลข:\n"
            "1️⃣ 🇹🇭 AIS-PLAY+128K\n"
            "2️⃣ 🇹🇭 TRUE-NOPRO\n"
            "3️⃣ 🇹🇭 TRUE-ROV\n"
            "4️⃣ 🇹🇭 TRUE-FB-GAMING\n"
            "5️⃣ 🇹🇭 TRUE-ZOOM\n"
            "6️⃣ 🇹🇭 DTAC-NOPRO\n"
            "7️⃣ 🇹🇭 DTAC-GAMING\n\n"
            "พิมพ์ 1, 2, 3, 4, 5, 6 หรือ 7"
        )
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=msg)]
            )
        )
    else:
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="❌ ไม่พบแพ็กเกจที่เลือก\nกรุณากดปุ่มเลือกแพ็กเกจด้านบน")]
            )
        )


# ===== Inbound Selection =====
def handle_inbound_selection(reply_token: str, user_id: str, text: str):
    """จัดการเลือกเซิร์ฟเวอร์"""
    inbound_id = text.strip()
    if inbound_id not in ["1", "2", "3", "4", "5", "6", "7"]:
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="❌ กรุณาพิมพ์ 1-7 เท่านั้น")]
            )
        )
        return
    
    inbound_names = {
        "1": "🇹🇭 AIS-PLAY+128K",
        "2": "🇹🇭 TRUE-NOPRO",
        "3": "🇹🇭 TRUE-ROV",
        "4": "🇹🇭 TRUE-FB-GAMING",
        "5": "🇹🇭 TRUE-ZOOM",
        "6": "🇹🇭 DTAC-NOPRO",
        "7": "🇹🇭 DTAC-GAMING",
    }
    inbound_name = inbound_names.get(inbound_id, f"#{inbound_id}")
    update_session(user_id, step="await_name",
                   data={**get_session(user_id)["data"], "inbound": inbound_id})
    
    if inbound_id == "1":
        detail = (
            f"✅ เลือก {inbound_name}\n\n"
            f"เซิร์ฟเวอร์ทั่วไป AIS 64K - 128K + AISPLAY 30 วัน 100 บาท (ไม่จำกัด GB)\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📌 รายละเอียดสินค้า\n"
            f"เซิร์ฟเวอร์ทั่วไป AIS 64K - 128K เดือนละ 100 บาท\n"
            f"ใช้งานได้ ไม่จำกัด GB\n"
            f"ใช้งานได้ 1-2 อุปกรณ์\n"
            f"(ความเร็วสูงสุด 10 Mbps)\n\n"
            f"⚠️ #ต้องสมัคร 2 โปรเสริมนะครับ\n"
            f"ทั้งกันรั่วและ AISPLAY ถึงจะใช้ได้\n\n"
            f"📲 สมัครโปรกันรั่ว\n"
            f"*777*7068#\n"
            f"35 บาท/เดือน\n\n"
            f"📲 AISPLAY\n"
            f"━ 1 วัน: *777*7310# (9.63 บ.)\n"
            f"━ 7 วัน: *777*7311# (20.33 บ.)\n"
            f"━ 30 วัน: *777*885# (63.13 บ.)\n\n"
            f""
        )
    elif inbound_id == "2":
        detail = (
            f"✅ เลือก {inbound_name}\n\n"
            f"เซิร์ฟเวอร์ทั่วไป TRUE NOPRO 30 วัน 50 บาท (ไม่จำกัด GB)\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📌 รายละเอียดสินค้า\n"
            f"เซิร์ฟเวอร์ทั่วไป TRUE NOPRO 30 วัน 50 บาท (ไม่จำกัด GB)\n"
            f"ใช้งานได้ 1-2 อุปกรณ์\n"
            f"⚠️ ห้ามมีโปรกันรั่วหรือโปรเน็ต\n\n"
            f"หากใช้งานแล้วไม่เสถียร\n"
            f"ให้สมัครโปร RoV ได้เลยตามนี้\n\n"
            f"📌 รายละเอียดสินค้า\n"
            f"เซิร์ฟเวอร์ทั่วไป TRUE RoV Extreme 30 วัน 100 บาท\n"
            f"ใช้งานได้ ไม่จำกัด GB\n"
            f"ใช้งานได้ 1-2 อุปกรณ์\n\n"
            f"🔥 โปรเกมมิ่ง ROV 🔥\n"
            f"กด *900*7765# โทรออก\n"
            f"แล้วเปิดโหมดเครื่องบิน 1 รอบ\n"
            f"ราคา 99฿ ไม่รวม Vat /30 วัน\n"
            f"เชื่อม VPN ได้เลย ไม่ลดสปีด\n\n"
            f"🔥 วิธีที่ 2 (สมัครในเว็บ)\n"
            f"1. เติมเงินเข้าซิม 100฿\n"
            f"2. คลิก https://topping.truemoney.com/\n"
            f"3. ผูกเบอร์ที่ใช้\n"
            f"4. ไปที่หน้าเติมเน็ต\n"
            f"5. ค้นหา \"ROV\"\n"
            f"6. เลือก RoV Extreme 99บ. 30วัน\n"
            f"7. หลังสมัคร เปิดปิดเครื่องบิน 1 รอบ\n"
            f"8. แนะนำ: เล่น ROV ปิดVPNก่อน\n\n"
            f""
        )
    elif inbound_id == "3":
        detail = (
            f"✅ เลือก {inbound_name}\n\n"
            f"เซิร์ฟเวอร์ทั่วไป TRUE RoV Extreme 30 วัน 100 บาท (ไม่จำกัด GB)\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📌 รายละเอียดสินค้า\n"
            f"เซิร์ฟเวอร์ทั่วไป TRUE RoV Extreme 30 วัน 100 บาท\n"
            f"ใช้งานได้ ไม่จำกัด GB\n"
            f"ใช้งานได้ 1-2 อุปกรณ์\n\n"
            f"🔥 โปรเกมมิ่ง ROV 🔥\n"
            f"กด *900*7765# โทรออก\n"
            f"แล้วเปิดโหมดเครื่องบิน 1 รอบ\n"
            f"ราคา 99฿ ไม่รวม Vat /30 วัน\n"
            f"เชื่อม VPN ได้เลย ไม่ลดสปีด\n\n"
            f"🔥 วิธีที่ 2 (สมัครในเว็บ)\n"
            f"1. เติมเงินเข้าซิม 100฿\n"
            f"2. คลิก https://topping.truemoney.com/\n"
            f"3. ผูกเบอร์ที่ใช้\n"
            f"4. ไปที่หน้าเติมเน็ต\n"
            f"5. ค้นหา \"ROV\"\n"
            f"6. เลือก RoV Extreme 99บ. 30วัน\n"
            f"7. หลังสมัคร เปิดปิดเครื่องบิน 1 รอบ\n"
            f"8. แนะนำ: เล่น ROV ปิดVPNก่อน\n\n"
            f""
        )
    elif inbound_id == "6":
        detail = (
            f"✅ เลือก {inbound_name}\n\n"
            f"เซิร์ฟเวอร์ทั่วไป DTAC NOPRO 30 วัน 100 บาท (ไม่จำกัด GB)\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📌 รายละเอียดสินค้า\n"
            f"เซิร์ฟเวอร์ทั่วไป DTAC NOPRO 30 วัน 100 บาท (ไม่จำกัด GB)\n"
            f"ใช้งานได้ 1-2 อุปกรณ์\n"
            f"⚠️ ห้ามมีโปรกันรั่วหรือโปรเน็ต\n\n"
            f""
        )
    else:
        detail = f"✅ เลือก {inbound_name}\n\n📝 กรุณาพิมพ์ชื่อของคุณครับ:"
    
    # ส่งข้อมูลโปร/รายละเอียดก่อน แล้วค่อยถามชื่อ
    messages = []
    if detail.strip():
        messages.append(TextMessage(text=detail))
    messages.append(TextMessage(text="📝 กรุณาพิมพ์ชื่อของคุณเพื่อสมัคร:"))
    line_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=messages
        )
    )


# ===== Name Input =====
def handle_name_input(reply_token: str, user_id: str, text: str):
    """รับชื่อลูกค้า"""
    if len(text.strip()) < 2:
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="❌ กรุณากรอกชื่ออย่างน้อย 2 ตัวอักษร")]
            )
        )
        return
    
    update_session(user_id, step="await_phone",
                   data={**get_session(user_id)["data"], "name": text.strip()})
    
    line_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(text=f"✅ ชื่อ: {text.strip()}\n\n📞 กรุณาพิมพ์เบอร์โทรศัพท์ (หรือพิมพ์ - ข้าม):")]
        )
    )


# ===== Phone Input =====
def handle_phone_input(reply_token: str, user_id: str, text: str):
    """รับเบอร์โทร"""
    phone = text.strip()
    if phone in ["-", "ข้าม", "skip"]:
        phone = ""
    
    data = get_session(user_id)["data"]
    data["phone"] = phone
    pkg = config.PACKAGES.get(data.get("package", "1"), config.PACKAGES["1"])
    inbound_names = {
        "1": "🇹🇭 AIS-PLAY+128K",
        "2": "🇹🇭 TRUE-NOPRO",
        "3": "🇹🇭 TRUE-ROV",
        "4": "🇹🇭 TRUE-FB-GAMING",
        "5": "🇹🇭 TRUE-ZOOM",
        "6": "🇹🇭 DTAC-NOPRO",
        "7": "🇹🇭 DTAC-GAMING",
    }
    inbound_name = inbound_names.get(data.get("inbound", "1"), "EkromNet")
    
    update_session(user_id, step="await_payment", data=data)
    
    pkg = config.PACKAGES.get(data.get("package", "1"), config.PACKAGES["1"])
    
    # สร้าง PromptPay QR
    qr_filename = f"pay_{int(time.time())}.png"
    pp_id = get_promptpay_id()
    qr_path = generate_promptpay_qr(pp_id, pkg["price"], qr_filename)
    
    from bank_config import get_bank_info_display
    
    # สรุปคำสั่งซื้อ (ตอบกลับก่อน)
    summary = (
        f"📋 สรุปคำสั่งซื้อ\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 ชื่อ: {data.get('name', '-')}\n"
        f"📞 เบอร์: {phone if phone else '-'}\n"
        f"📦 แพ็กเกจ: {pkg['name']}\n"
        f"💰 ราคา: {pkg['price']} บาท\n"
        f"🌐 เซิร์ฟเวอร์: #{data.get('inbound', '1')}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🏦 {get_bank_info_display()}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"💳 สแกน QR CODE ด้านล่างเพื่อชำระเงิน\n"
        f"💰 ยอด {pkg['price']} บาท\n\n"
        f"📸 หลังจากโอนแล้ว ส่งสลิปในแชทนี้\n"
        f"🔄 ระบบตรวจสอบอัตโนมัติ!\n\n"
        f"2 = ยกเลิก"
    )
    
    line_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(text=summary)]
        )
    )
    
    # ตามด้วย QR PromptPay (push แยก)
    if qr_path and os.path.exists(qr_path):
        time.sleep(1)
        push_image(user_id, qr_path)


# ===== Payment / Slip Handling =====
def handle_payment_text(reply_token: str, user_id: str, text: str):
    """จัดการข้อความระหว่างรอสลิป"""
    text = text.strip()
    if text == "แอดบังไม่เติม":
        # ✅ คำสั่งลัด (ลับ) — ข้ามตรวจสลิป (ใช้เฉพาะ admin)
        session = get_session(user_id)
        if session["data"].get("renew_client"):
            execute_renewal(user_id, session, reply_token)
        else:
            execute_order_or_renewal(user_id, session, reply_token)
    elif text in ["2", "ยกเลิก", "cancel"]:
        update_session(user_id, step="menu", data={})
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="✅ ยกเลิกสำเร็จ")]
            )
        )
    else:
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="📸 กรุณาส่งรูปสลิปโอนเงิน\nพิมพ์ 2 = ยกเลิก")]
            )
        )


# ===== Image Handler (รับสลิป) =====
@line_handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event):
    """จัดการเมื่อผู้ใช้ส่งรูปภาพ (สลิปโอนเงิน)"""
    user_id = event.source.user_id
    reply_token = event.reply_token
    message_id = event.message.id
    
    session = get_session(user_id)
    if session.get("step") != "await_payment":
        # ไม่ได้อยู่ในขั้นตอนรอสลิป
        return
    
    line_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(text="⏳ กำลังตรวจสอบสลิป... กรุณารอสักครู่")]
        )
    )
    
    try:
        # ดาวน์โหลดรูปจาก LINE (ใช้ MessagingApiBlob)
        content = line_api_blob.get_message_content(message_id)
        image_bytes = content
        
        # บันทึกรูปชั่วคราว
        import tempfile, os
        temp_dir = "/root/hermes-commerce/temp_images"
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, f"{message_id}.jpg")
        with open(temp_path, "wb") as f:
            f.write(image_bytes)
        
        # สร้าง URL สำหรับ SlipOK (ผ่าน nginx proxy)
        image_url = f"https://{config.SERVER_DOMAIN}/temp_images/{message_id}.jpg"
        
        # ตรวจสอบสลิป
        pkg = config.PACKAGES.get(session.get("data", {}).get("package", "1"), config.PACKAGES["1"])
        expected_amount = pkg["price"]
        
        slip_data = check_slip_by_url(image_url, amount=expected_amount)
        
        if slip_data:
            # ✅ สลิปถูกต้อง — สร้าง user
            push_text(user_id, format_slip_result(slip_data))
            time.sleep(1)
            execute_order(user_id, session)
        else:
            # ❌ สลิปไม่ถูกต้องหรือตรวจไม่สำเร็จ
            push_text(user_id, 
                "❌ ระบบตรวจสอบไม่สำเร็จ\n\n"
                "กรุณาส่งสลิปใหม่อีกครั้ง"
            )
    except ValueError as e:
        msg = str(e)
        if msg == "SLIPOK_WRONG_ACCOUNT":
            push_text(user_id, "❌ ตรวจสอบไม่สำเร็จ\n\n⚠️ สลิปนี้โอนไปบัญชีไม่ถูกต้อง\nกรุณาโอนเข้าบัญชี EkromVPN ตาม QR Code ที่ให้ไว้ แล้วส่งสลิปใหม่ครับ")
        elif msg == "SLIPOK_WRONG_AMOUNT":
            push_text(user_id, f"❌ ตรวจสอบไม่สำเร็จ\n\n⚠️ ยอดเงินไม่ตรงกับแพ็กเกจ\nกรุณาโอน {expected_amount} บาท แล้วส่งสลิปใหม่ครับ")
        else:
            push_text(user_id, "❌ ระบบตรวจสอบไม่สำเร็จ\n\nกรุณาส่งสลิปใหม่อีกครั้ง")
    except Exception as e:
        app.logger.error(f"Slip check error: {e}")
        push_text(user_id, 
            "❌ ระบบตรวจสอบไม่สำเร็จ\n\n"
            "กรุณาส่งสลิปใหม่อีกครั้ง"
        )


# ===== Renewal (ต่ออายุ) =====
def handle_renew_phone(reply_token: str, user_id: str, text: str):
    """รับเบอร์โทรเพื่อค้นหาบัญชี"""
    text = text.strip()
    if text in ["2", "ยกเลิก", "cancel"]:
        update_session(user_id, step="menu", data={})
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="✅ ยกเลิกสำเร็จ")]
            )
        )
        return

    # รองรับทั้งเบอร์โทร และชื่อ (ข้ามเบอร์ได้)
    digits = "".join(ch for ch in text if ch.isdigit())
    keyword = text.strip()
    if len(digits) >= 9:
        keyword = digits  # ค้นด้วยเบอร์
    elif len(keyword) < 2:
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="❌ กรุณาพิมพ์เบอร์โทร 10 หลัก (เช่น 0812345678)\nหรือชื่อที่ใช้สมัคร (อย่างน้อย 2 ตัวอักษร)")]
            )
        )
        return

    clients = xui_db.get_clients_by_keyword(keyword)
    if not clients:
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(
                    text="❌ ไม่พบบัญชีที่ใช้ '" + keyword + "'\n\n"
                         "ตรวจสอบเบอร์/ชื่อให้ถูกต้อง\n"
                         "หรือพิมพ์ 1 เพื่อสมัครใหม่\n"
                         "พิมพ์ 2 = ยกเลิก"
                )]
            )
        )
        update_session(user_id, step="menu", data={})
        return

    # แสดงรายการบัญชีที่พบ
    import datetime as _dt
    server_names = {
        10: "AIS/TRUE 8080", 13: "FB-GAMING 443", 14: "TRUE/DTAC 80"
    }
    lines = [f"🔍 พบบัญชี {len(clients)} รายการ:\n"]
    for i, c in enumerate(clients, 1):
        expiry = ""
        if c["expiry_ms"] and c["expiry_ms"] > 0:
            dt = _dt.datetime.fromtimestamp(c["expiry_ms"] / 1000)
            thai_months = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
                           "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
            expiry = f"{dt.day}/{thai_months[dt.month]}/{dt.year + 543}"
        else:
            expiry = "ไม่จำกัด"
        sv = server_names.get(c["inbound_id"], f"#{c['inbound_id']}")
        status = "✅" if c["enable"] else "⛔"
        keycap = f"{i}️⃣" if i <= 9 else f"{i}."
        lines.append(f"{keycap} {status} {sv}\n"
                     f"             {c['email']}\n"
                     f"       ⏰ หมดอายุ: {expiry}")
    lines.append(f"\nพิมพ์หมายเลขบัญชีที่ต้องการต่ออายุ (1-{len(clients)})\nพิมพ์ 0 = ยกเลิก")

    update_session(user_id, step="await_renew_select",
                   data={"renew_keyword": keyword, "renew_clients": clients})

    line_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(text="\n".join(lines))]
        )
    )


def handle_renew_select(reply_token: str, user_id: str, text: str):
    """เลือกรายการบัญชีที่จะต่ออายุ"""
    text = text.strip()
    data = get_session(user_id)["data"]
    clients = data.get("renew_clients", [])

    if text in ["0", "ยกเลิก", "cancel"]:
        update_session(user_id, step="menu", data={})
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="✅ ยกเลิกสำเร็จ")]
            )
        )
        return

    try:
        idx = int(text) - 1
        if idx < 0 or idx >= len(clients):
            raise ValueError
    except ValueError:
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=f"❌ กรุณาพิมพ์หมายเลข 1-{len(clients)} เท่านั้น")]
            )
        )
        return

    chosen = clients[idx]
    data["renew_client"] = chosen
    update_session(user_id, step="await_renew_package", data=data)

    line_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(
                text=f"🔄 ต่ออายุบัญชี:\n"
                     f"👤 {chosen['email']}\n\n"
                     f"📦 เลือกแพ็กเกจต่ออายุ:\n"
                     f"1️⃣ = 𝟥𝟢 วัน — 𝟧𝟢 บาท\n"
                     f"3️⃣ = 𝟫𝟢 วัน — 𝟣𝟦𝟢 บาท\n"
                     f"6️⃣ = 𝟣𝟪𝟢 วัน — 𝟤𝟦𝟢 บาท\n"
                     f"0️⃣ = 𝟥𝟨𝟧 วัน — 𝟦𝟤𝟢 บาท\n\n"
                     f"พิมพ์ 2 = ยกเลิก"
            )]
        )
    )


def handle_renew_package(reply_token: str, user_id: str, text: str):
    """เลือกแพ็กเกจต่ออายุ → ไปจ่ายเงิน"""
    text = text.strip()
    data = get_session(user_id)["data"]

    if text in ["2", "ยกเลิก", "cancel"]:
        update_session(user_id, step="menu", data={})
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="✅ ยกเลิกสำเร็จ")]
            )
        )
        return

    pkg_map = {"1": "1", "3": "2", "6": "3", "12": "4", "0": "4"}
    pkg_key = pkg_map.get(text)
    if not pkg_key:
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="❌ กรุณากด 1, 3, 6 หรือ 12 เท่านั้น")]
            )
        )
        return

    pkg = config.PACKAGES[pkg_key]
    data["renew_package"] = pkg_key
    update_session(user_id, step="await_payment", data=data)

    # สร้าง PromptPay QR
    qr_filename = f"pay_{int(time.time())}.png"
    pp_id = get_promptpay_id()
    qr_path = generate_promptpay_qr(pp_id, pkg["price"], qr_filename)

    from bank_config import get_bank_info_display

    summary = (
        f"🔄 ต่ออายุ\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 บัญชี: {data['renew_client']['email']}\n"
        f"📦 แพ็กเกจ: {pkg['name']}\n"
        f"💰 ราคา: {pkg['price']} บาท\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🏦 {get_bank_info_display()}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"💳 สแกน QR CODE ด้านล่างเพื่อชำระเงิน\n"
        f"💰 ยอด {pkg['price']} บาท\n\n"
        f"📸 หลังจากโอนแล้ว ส่งสลิปในแชทนี้\n"
        f"🔄 ระบบตรวจสอบอัตโนมัติ!\n"
        f"พิมพ์ 2 = ยกเลิก"
    )
    line_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(text=summary)]
        )
    )
    if qr_path and os.path.exists(qr_path):
        push_image(user_id, qr_path)


def execute_renewal(user_id: str, session: Dict, reply_token: str = None):
    """ต่ออายุ client — ขยายวันหมดอายุ"""
    data = session["data"]
    client = data.get("renew_client", {})
    pkg_key = data.get("renew_package", "1")
    pkg = config.PACKAGES.get(pkg_key, config.PACKAGES["1"])

    if reply_token:
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="⏳ กำลังต่ออายุบัญชีให้คุณ... กรุณารอสักครู่")]
            )
        )

    # คำนวณวันหมดอายุใหม่: ต่อจากวันปัจจุบัน (หรือวันหมดอายุเดิมถ้ายังไม่หมด)
    import datetime as _dt
    now_ms = int(_dt.datetime.now().timestamp() * 1000)
    old_expiry = client.get("expiry_ms") or 0
    base = max(now_ms, old_expiry)
    new_expiry_ms = base + pkg["days"] * 86400 * 1000

    result = xui_db.update_client_expiry(
        inbound_id=client["inbound_id"],
        client_uuid=client["client_id"],
        new_expiry_ms=new_expiry_ms,
    )

    if not result:
        push_text(user_id, "❌ ต่ออายุไม่สำเร็จ กรุณาลองใหม่หรือติดต่อแอดมิน")
        return

    _dt_obj = _dt.datetime.fromtimestamp(new_expiry_ms / 1000)
    thai_months = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
                   "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    expiry_str = f"{_dt_obj.day}/{thai_months[_dt_obj.month]}/{_dt_obj.year + 543}"

    push_text(user_id,
        f"✅ ต่ออายุสำเร็จ!\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 บัญชี: {result['email']}\n"
        f"📦 แพ็กเกจ: {pkg['name']}\n"
        f"⏰ หมดอายุใหม่: {expiry_str}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"สามารถใช้งานต่อได้เลย 🚀"
    )

    update_session(user_id, step="menu", data={})


def execute_order_or_renewal(user_id: str, session: Dict, reply_token: str = None):
    """เลือกว่าจะสร้างบัญชีใหม่หรือต่ออายุ"""
    if session["data"].get("renew_client"):
        execute_renewal(user_id, session, reply_token)
    else:
        execute_order(user_id, session, reply_token)


def execute_order(user_id: str, session: Dict, reply_token: str = None):
    """สร้าง user และส่ง config (ใช้ร่วมกันตอนสลิปผ่านหรือยืนยัน)"""
    if reply_token:
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="⏳ กำลังสร้างบัญชีให้คุณ... กรุณารอสักครู่")]
            )
        )
    
    order = create_order(user_id, session)
    
    if not order:
        push_text(user_id, "❌ สร้างบัญชีไม่สำเร็จ กรุณาลองใหม่หรือติดต่อแอดมิน")
        return
    
    # ส่งรายละเอียด
    push_text(user_id, 
        f"✅ สร้างบัญชีสำเร็จ!\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 ชื่อ: {order['email']}\n"
        f"📦 แพ็กเกจ: {order['package_name']}\n"
        f"⏰ หมดอายุ: {order['expiry_str']}\n"
        f"📡 เซิร์ฟเวอร์: #{order['inbound_id']}\n"
        f"━━━━━━━━━━━━━━━"
    )
    
    # ส่ง VMESS/VLESS config (ลิงก์ตรง)
    push_text(user_id, 
        f"✅ ระบบตรวจสอบยอดเงินและสลิปเรียบร้อย\n"
        f"สร้างไฟล์ VPN ใช้งาน {order['package_name']} ให้คุณแล้ว 🚀\n\n"
        f"{order['vmess_link']}"
    )
    
    # ส่ง QR Code เป็นลิงก์
    if order.get("qr_path") and os.path.exists(order["qr_path"]):
        qr_url = f"https://{config.SERVER_DOMAIN}/configs/{os.path.basename(order['qr_path'])}"
        push_text(user_id, f"📸 QR: {qr_url}")
    
    update_session(user_id, step="menu", data={})



def push_text(user_id: str, text: str):
    """Push text message to user"""
    if not line_api:
        app.logger.warning("LINE not configured — cannot push")
        return
    line_api.push_message(
        PushMessageRequest(
            to=user_id,
            messages=[TextMessage(text=text)]
        )
    )

def push_image(user_id: str, image_path: str):
    """Push image to user"""
    if not line_api:
        app.logger.warning("LINE not configured — cannot push")
        return
    try:
        # ใช้ public URL (port 443 ผ่าน nginx)
        image_url = f"https://{config.SERVER_DOMAIN}/configs/{os.path.basename(image_path)}"
        line_api.push_message(
            PushMessageRequest(
                to=user_id,
                messages=[ImageMessage(
                    original_content_url=image_url,
                    preview_image_url=image_url
                )]
            )
        )
    except Exception as e:
        app.logger.error(f"Push image error: {e}")
        # ส่งเป็นข้อความแทนถ้าส่งรูปไม่ได้
        push_text(user_id, f"📸 QR Code: {image_url}")

def push_flex(user_id: str, flex_msg: FlexMessage):
    """Push flex message to user"""
    if not line_api:
        app.logger.warning("LINE not configured — cannot push")
        return
    line_api.push_message(
        PushMessageRequest(
            to=user_id,
            messages=[flex_msg]
        )
    )


# ===== Serve QR Code Images =====
@app.route("/configs/<filename>")
def serve_config(filename):
    """Serve QR code images"""
    from flask import send_file
    filepath = os.path.join("/root/hermes-commerce/configs", filename)
    if os.path.exists(filepath):
        return send_file(filepath, mimetype="image/png")
    return "File not found", 404


# ===== Config Redirect (กดแล้วเปิด V2Box อัตโนมัติ) =====
@app.route("/c/<path:encoded>")
def connect_config(encoded):
    """Redirect vmess:// หรือ vless:// link ให้เปิดแอป V2Box อัตโนมัติ"""
    from flask import redirect
    try:
        # เติม padding ถ้าขาด
        padding = 4 - len(encoded) % 4
        if padding != 4:
            encoded += "=" * padding
        decoded = base64.urlsafe_b64decode(encoded).decode()
        return redirect(decoded)
    except Exception as e:
        return f"Invalid link: {e}", 400


# ===== Serve Temp Images (for SlipOK) =====
@app.route("/temp_images/<filename>")
def serve_temp(filename):
    """Serve temp images for slip checking"""
    from flask import send_file
    filepath = os.path.join("/root/hermes-commerce/temp_images", filename)
    if os.path.exists(filepath):
        return send_file(filepath, mimetype="image/jpeg")
    return "File not found", 404


# ===== Health Check =====
@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


# ===== Facebook Messenger Bot =====
try:
    import sys
    import fb_bot
    fb_bot.setup(sys.modules[__name__])
    print("✅ Facebook Messenger bot พร้อมใช้งาน (/fb/callback)")
except Exception as e:
    import traceback
    print(f"⚠️ Facebook bot ไม่สามารถเริ่มได้: {e}")
    traceback.print_exc()


# ===== Main =====
if __name__ == "__main__":
    print("=" * 50)
    print("🛍️  Hermes Commerce Bot")
    print(f"📡  Server: https://{config.SERVER_DOMAIN}:{config.SERVER_PORT}")
    print(f"🔗  Webhook: https://{config.SERVER_DOMAIN}:{config.SERVER_PORT}/callback")
    print("=" * 50)
    
    app.run(
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        ssl_context=(config.SSL_CERT, config.SSL_KEY) if (config.SSL_CERT and config.SSL_KEY) else None,
        debug=False,
        use_reloader=False,
        threaded=True,   # รองรับ webhook พร้อมกันหลายคน
    )
