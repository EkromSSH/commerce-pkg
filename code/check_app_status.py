#!/usr/bin/env python3
"""
ตรวจสถานะ App Review (pages_messaging) ของแอป EkromVPN ทุกวัน
- ถ้าสถานะเปลี่ยน → รายงาน
- ถ้าอนุมัติแล้ว → รายงานชัดเจน
- ถ้าไม่เปลี่ยน → เงียบ (ไม่มี output)
"""
import json
import os
import requests

APP_ID = "1649683947157116"
APP_SECRET = "81bebf6f4db23b7501ed5131a7c63e8f"
STATE_FILE = "/root/hermes-commerce/app_review_status.txt"

app_token = f"{APP_ID}|{APP_SECRET}"

try:
    r = requests.get(
        f"https://graph.facebook.com/v19.0/{APP_ID}/permissions",
        params={"access_token": app_token},
        timeout=20,
    )
    data = r.json().get("data", []) if r.status_code == 200 else []
except Exception:
    data = []

status_map = {}
for p in data:
    perm = p.get("permission", "")
    status_map[perm] = p.get("status", "")

msg_status = status_map.get("pages_messaging", "ไม่พบ")
# สถานะที่เป็นไปได้: granted / in_review / not_submitted / approved
state = msg_status

# อ่านสถานะเก่า
old_state = ""
if os.path.exists(STATE_FILE):
    with open(STATE_FILE) as f:
        old_state = f.read().strip()

# ตรวจโหมดแอป (Development/Live)
mode = "ไม่ทราบ"
try:
    r2 = requests.get(
        f"https://graph.facebook.com/v19.0/{APP_ID}",
        params={"access_token": app_token, "fields": "name"},
        timeout=15,
    )
    if r2.status_code == 200:
        name = r2.json().get("name", "?")
except Exception:
    pass

lines = []
if msg_status in ("approved", "granted") or "approved" in msg_status.lower():
    lines.append(f"🎉 แอป {APP_ID} ผ่านอนุมัติแล้ว! (pages_messaging: {msg_status})")
    lines.append("✅ ไปเปลี่ยน App Mode เป็น Live เพื่อให้ลูกค้าทุกคนใช้บอทได้!")
    lines.append("แล้วแจ้งให้ผมตรวจสอบ/ตั้งค่าให้ด้วยครับ")
elif msg_status == "in_review":
    if old_state != msg_status:
        lines.append(f"📋 สถานะ pages_messaging: กำลังรีวิว (In Review) — รอ Meta ตรวจสอบครับ")
elif msg_status in ("not_submitted", "development", "ไม่พบ"):
    if old_state != msg_status:
        lines.append(f"⏳ pages_messaging: ยังไม่ถูกส่งรีวิว ({msg_status})")
        lines.append("ยังต้องทำ: ยืนยันธุรกิจ → ส่ง App Review → รออนุมัติ")
else:
    if old_state != msg_status:
        lines.append(f"📋 สถานะ pages_messaging เปลี่ยนเป็น: {msg_status}")

# บันทึกสถานะปัจจุบัน
with open(STATE_FILE, "w") as f:
    f.write(state)

if lines:
    print("\n".join(lines))
