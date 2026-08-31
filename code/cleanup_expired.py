"""
ลบบัญชี x-ui ที่หมดอายุเกิน 7 วัน อัตโนมัติ (รันทุกวันผ่าน cron)
- ตรวจ client ทุก inbound (1, 10, 13, 14)
- ถ้า expiryTime + 7 วัน < ตอนนี้ → ลบออก
- เขียน log ที่ /var/log/hermes-cleanup.log
"""
import sys
import json
import time
import datetime

sys.path.insert(0, "/root/hermes-commerce")

import config
from xui_client import XUIClient

LOG_FILE = "/var/log/hermes-cleanup.log"
GRACE_DAYS = 7  # หมดอายุเกิน 7 วันแล้วค่อยลบ


def log(msg):
    line = f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main():
    now_ms = int(time.time() * 1000)
    cutoff = now_ms - GRACE_DAYS * 86400 * 1000

    client = XUIClient()
    if not client.login():
        log("❌ Login x-ui ไม่สำเร็จ")
        return

    deleted = 0
    for inbound in client.get_inbounds():
        inbound_id = inbound["id"]
        try:
            settings = json.loads(inbound["settings"]) if isinstance(inbound["settings"], str) else inbound["settings"]
        except Exception:
            continue
        for c in settings.get("clients", []):
            expiry = c.get("expiryTime", 0)
            if expiry <= 0:
                continue  # ไม่จำกัดวัน ไม่ลบ
            expired_days = (now_ms - expiry) / 86400000.0
            if expired_days >= GRACE_DAYS:
                email = c.get("email", "?")
                url = f"{config.XUI_BASE_URL}/panel/api/inbounds/{inbound_id}/delClient/{c['id']}"
                try:
                    r = client.session.post(url, timeout=15)
                    ok = r.status_code == 200 and r.json().get("success") is True
                    if ok:
                        deleted += 1
                        log(f"🗑️ ลบ {email} (หมดอายุมา {expired_days:.1f} วัน) inbound={inbound_id}")
                    else:
                        log(f"⚠️ ลบไม่สำเร็จ {email}: {r.text[:80]}")
                except Exception as e:
                    log(f"⚠️ error ลบ {email}: {e}")

    log(f"✅ ตรวจเสร็จ: ลบ {deleted} บัญชีที่หมดอายุเกิน {GRACE_DAYS} วัน")


if __name__ == "__main__":
    main()
