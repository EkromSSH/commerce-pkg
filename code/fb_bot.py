"""
Facebook Messenger Bot — ใช้ระบบเดียวกับ LINE bot (app.py)
- รับ webhook จาก Meta → ส่งต่อเข้า flow เดิมของ app.py
- ส่งข้อความผ่าน Graph API
"""
import json
import time
import hashlib
import hmac
import os
import requests
from types import SimpleNamespace

from flask import request, Response

import config

GRAPH = "https://graph.facebook.com/v19.0"


def send_fb(psid, payload):
    """ส่งข้อความ/attachment ไปยังผู้ใช้ผ่าน Messenger Send API"""
    try:
        resp = requests.post(
            f"{GRAPH}/me/messages",
            params={"access_token": config.FB_ACCESS_TOKEN},
            json={"recipient": {"id": psid}, "message": payload},
            timeout=15,
        )
        data = resp.json()
        if resp.status_code != 200 or data.get("error"):
            print(f"FB send error: {data}")
            return False
        return True
    except Exception as e:
        print(f"FB send exception: {e}")
        return False


def send_text(psid, text):
    return send_fb(psid, {"text": text})


def send_image(psid, image_url):
    return send_fb(psid, {
        "attachment": {"type": "image", "payload": {"url": image_url}}
    })


class FakeLineApi:
    """แปลง LINE SDK calls → Facebook Send API (monkey-patch เข้า app.py)"""

    def reply_message(self, req):
        for m in req.messages:
            self._send(req.reply_token, m)

    def push_message(self, req):
        for m in req.messages:
            self._send(req.to, m)

    def _send(self, psid, msg):
        # TextMessage / ImageMessage จาก linebot SDK
        text = getattr(msg, "text", None)
        if text is not None:
            send_text(psid, text)
            return
        img_url = getattr(msg, "original_content_url", None)
        if img_url:
            send_image(psid, img_url)
            return
        send_text(psid, str(msg))


def verify_webhook_signature(body, signature):
    """ตรวจ X-Hub-Signature-256 (App Secret)"""
    if not signature:
        return False
    expected = "sha256=" + hmac.new(
        config.FB_APP_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def register_routes(app, bot):
    """เพิ่ม /fb/callback ลงใน Flask app — bot = module app.py"""

    @app.route("/fb/callback", methods=["GET", "POST"])
    def fb_callback():
        if request.method == "GET":
            # Webhook verification จาก Meta
            mode = request.args.get("hub.mode")
            token = request.args.get("hub.verify_token")
            challenge = request.args.get("hub.challenge")
            if mode == "subscribe" and token == config.FB_VERIFY_TOKEN:
                return Response(challenge, status=200)
            return Response("Verification failed", status=403)

        # POST — webhook events
        body = request.get_data()
        sig = request.headers.get("X-Hub-Signature-256", "")
        if not verify_webhook_signature(body, sig):
            print(f"FB invalid signature: {sig[:30]}...")
            return Response("OK", status=200)

        try:
            data = json.loads(body)
        except Exception:
            return Response("OK", status=200)

        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                handle_fb_event(bot, event)
        return Response("OK", status=200)


def handle_fb_event(bot, event):
    """ประมวลผล event จาก Messenger"""
    sender = event.get("sender", {})
    psid = sender.get("id")
    if not psid:
        return

    msg = event.get("message", {})
    if not msg or msg.get("is_echo"):
        return

    # ---- ข้อความรูปภาพ (สลิป) ----
    if msg.get("attachments"):
        for att in msg["attachments"]:
            if att.get("type") == "image":
                url = att.get("payload", {}).get("url")
                if url:
                    handle_fb_image(bot, psid, url)
                return

    # ---- ข้อความธรรมดา ----
    text = msg.get("text", "")
    if not text.strip():
        return

    # สร้าง fake LINE event แล้วส่งเข้า flow เดิม
    fake_event = SimpleNamespace(
        source=SimpleNamespace(user_id=psid),
        message=SimpleNamespace(text=text, id=f"fb_{int(time.time())}"),
        reply_token=psid,  # ไม่ได้ใช้จริง — FakeLineApi ส่งตรง
    )
    try:
        enter_fb_mode(bot)
        bot.handle_message(fake_event)
    except Exception as e:
        print(f"FB handle_message error: {e}")
        send_text(psid, "❌ เกิดข้อผิดพลาด กรุณาลองใหม่หรือติดต่อแอดมิน")
    finally:
        exit_fb_mode(bot)


def handle_fb_image(bot, psid, image_url):
    """รับสลิปจาก Facebook — ตรวจสอบแล้วสร้างบัญชี/ต่ออายุ"""
    session = bot.get_session(psid)
    if session.get("step") != "await_payment":
        return

    send_text(psid, "⏳ กำลังตรวจสอบสลิป... กรุณารอสักครู่")

    try:
        enter_fb_mode(bot)
        # ดาวน์โหลดรูป
        r = requests.get(image_url, timeout=20)
        if r.status_code != 200:
            raise Exception(f"download failed: {r.status_code}")

        temp_dir = "/root/hermes-commerce/temp_images"
        os.makedirs(temp_dir, exist_ok=True)
        filename = f"fb_{int(time.time())}.jpg"
        temp_path = os.path.join(temp_dir, filename)
        with open(temp_path, "wb") as f:
            f.write(r.content)

        # URL สาธารณะสำหรับ SlipOK
        public_url = f"https://{config.SERVER_DOMAIN}/temp_images/{filename}"

        pkg = config.PACKAGES.get(session.get("data", {}).get("package", "1"), config.PACKAGES["1"])
        expected_amount = pkg["price"]

        slip_data = bot.check_slip_by_url(public_url, amount=expected_amount)

        if slip_data:
            bot.push_text(psid, bot.format_slip_result(slip_data))
            time.sleep(1)
            bot.execute_order_or_renewal(psid, session)
        else:
            bot.push_text(psid, "❌ ระบบตรวจสอบไม่สำเร็จ\n\nกรุณาส่งสลิปใหม่อีกครั้ง")
        exit_fb_mode(bot)
    except Exception as e:
        print(f"FB slip error: {e}")
        try:
            bot.push_text(psid, "❌ ระบบตรวจสอบไม่สำเร็จ\n\nกรุณาส่งสลิปใหม่อีกครั้ง")
        finally:
            exit_fb_mode(bot)


def setup(bot):
    """ลงทะเบียน /fb/callback — ไม่แตะ line_api ของ LINE (สลับเฉพาะตอน FB event)"""
    register_routes(bot.app, bot)
    return bot


def enter_fb_mode(bot):
    """สลับ line_api → ส่งผ่าน Facebook (ใช้เฉพาะตอนประมวลผล FB event)"""
    bot._real_line_api = bot.line_api
    bot.line_api = FakeLineApi()

    def fb_push_image(user_id, image_path):
        image_url = f"https://{config.SERVER_DOMAIN}/configs/{os.path.basename(image_path)}"
        ok = send_image(user_id, image_url)
        if not ok:
            send_text(user_id, f"📸 QR Code: {image_url}")

    bot._real_push_image = bot.push_image
    bot.push_image = fb_push_image


def exit_fb_mode(bot):
    """คืนค่า line_api/push_image กลับเป็นของ LINE"""
    bot.line_api = bot._real_line_api
    bot.push_image = bot._real_push_image
