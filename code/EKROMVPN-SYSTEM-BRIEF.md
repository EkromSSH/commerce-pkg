# 🤖 EkromVPN — ระบบ Bot LINE + Facebook (เอกสารสำหรับ AI อื่น)

> สร้างโดย: แอด บังริง (Hermes Agent) · อัปเดตล่าสุด: 3 ส.ค. 2569
> เอกสารนี้สรุปความรู้ทั้งหมดของระบบ — AI ตัวอื่นอ่านแล้วทำงานต่อได้ทันที

---

## 1️⃣ ภาพรวมระบบ

**ธุรกิจ:** ขายบัญชี VPN (EkromVPN) — ลูกค้าสั่งซื้อผ่าน LINE/Facebook → จ่ายเงิน → ระบบสร้างบัญชี VPN ใน x-ui → ส่งคอนฟิกอัตโนมัติ

```
ลูกค้า (LINE OA / Facebook Page)
   │ ส่งข้อความ (สั่งซื้อ/ต่ออายุ/ส่งสลิป)
   ▼
hermes-bot (Flask, port 8443, systemd)  ← หัวใจระบบ
   │
   ├── LINE API (push/reply ข้อความ)
   ├── Facebook Graph API (ส่งข้อความ/รูป)
   ├── x-ui panel API (สร้าง/ลบบัญชี VPN)
   ├── SQLite sessions.db (สถานะการสนทนา)
   └── PromptPay QR (สร้าง QR จ่ายเงิน)
```

**จุดสำคัญ:** hermes-bot เป็น **systemd service อิสระ** — ไม่ต้องพึ่ง Hermes Agent ทำงานเอง 24/7
- `Restart=always` (ตายปุ๊บ restart ปั๊บ)
- `watchdog.sh` cron ทุก 5 นาที (ค้าง → restart)
- `cleanup_expired.py` cron ทุกวัน 04:00 (ลบบัญชีหมดอายุเกิน 7 วัน)

---

## 2️⃣ บัญชี & Platform

| รายการ | ค่า |
|--------|-----|
| LINE OA | @578infzg (ชื่อ EkromVPN) |
| Facebook Page | EkromTunnel (webhook 104217987659643) |
| Facebook App ID | 1649683947157116 |
| Facebook Page ID | 2391715224990945 |
| LINE webhook URL | https://vip4.idavpn.win/callback |
| FB webhook URL | https://vip4.idavpn.win/fb/callback |
| FB verify token | อยู่ใน config.py (`FB_VERIFY_TOKEN`) |
| Telegram แอดมิน | @ekrom_support |
| Facebook แอดมิน | m.me/EkromTunnel |

**Tokens ทั้งหมดอยู่ที่:** `/root/hermes-commerce/config.py`
- `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_CHANNEL_SECRET`
- `FB_APP_SECRET`, `FB_ACCESS_TOKEN`, `FB_VERIFY_TOKEN`
- `XUI_USERNAME` / `XUI_PASSWORD` (x-ui panel)

---

## 3️⃣ เซิร์ฟเวอร์ & x-ui

| รายการ | ค่า |
|--------|-----|
| VPS IP | 212.80.213.214 |
| x-ui panel | https://vip2.idavpn.win:4433 (user: EKROM) |
| x-ui API | /panel/api/inbounds/ |
| Domain หน้าเว็บ | vip4.idavpn.win |
| Nginx | 443 → x-ui (4443) / /callback → bot (8443) / /fb/callback → bot (8443) |

### Inbounds (3 ตัวจริงใน x-ui)
| ID | ชื่อ | พอร์ต | โปรโตคอล |
|----|------|-------|-----------|
| 10 | VIP2-AIS | 8080 | VMESS |
| 13 | TRUE-FB-GAMING | 443 | VLESS+TLS |
| 14 | NOPRO | 80 | VLESS |

### 7 เซิร์ฟเวอร์ที่ขาย (bot inbound → x-ui inbound)
| เซิร์ฟเวอร์ | พอร์ต | host | โปรโตคอล | x-ui ID |
|-----------|-------|------|-----------|---------|
| AIS-PLAY | 80 | aisplay.ais.co.th | VLESS+WS | 14 |
| TRUE-NOPRO | 80 | assets.opensignal.com (host: d2w9iashl5za4g.cloudfront.net) | VLESS+WS | 14 |
| TRUE-ROV | 8080 | truegame.idavpn.win | VMESS+WS | 10 |
| TRUE-FB-GAMING | 443 | vip2.idavpn.win (sni: fbcdn.idavpn.win) | VLESS+TCP+TLS | 13 |
| TRUE-ZOOM | 8080 | truegame.idavpn.win | VMESS+WS | 10 |
| DTAC-NOPRO | 80 | www.true.th | VLESS+WS | 14 |
| DTAC-GAMING | 80 | vip2.idavpn.win | VLESS+WS | 14 |

**Mapping โค้ด:** bot inbound 1-3→xui 14? ดูใน `create_order`: `13 if inbound_id==4 else (10 if inbound_id in [3,5] else 14)`

---

## 4️⃣ แพ็กเกจ & ราคา

| รหัส | แพ็กเกจ | ราคา | ระยะเวลา | เครื่อง |
|------|---------|------|----------|--------|
| 1 | 1 เดือน | 50 บาท | 30 วัน | 2 |
| 2 | 3 เดือน | 140 บาท | 90 วัน | 2 |
| 3 | 6 เดือน | 240 บาท | 180 วัน | 2 |
| 4 | 1 ปี | 420 บาท | 365 วัน | 2 |

**การชำระเงิน:**
- ธนาคาร: กสิกรไทย / อับดุลซการิง ลอเต / 1741779060
- PromptPay: 1940100143709
- ลูกค้าส่งสลิป → ตรวจผ่าน (slipok/bank_config) → ปล่อยบัญชี

---

## 5️⃣ ไฟล์หลัก (โฟลเดอร์ /root/hermes-commerce/)

| ไฟล์ | หน้าที่ |
|------|--------|
| `app.py` | ⭐ หัวใจ — Flask webhook (8443), LINE+FB events, ฟลอว์ซื้อขายทั้งหมด |
| `fb_bot.py` | Facebook Messenger handler (สลับ line_api → FakeLineApi เฉพาะตอน FB) |
| `xui_client.py` | คุยกับ x-ui API (add/del client, get inbounds) |
| `config.py` | ค่าทั้งหมด (tokens, ราคา, เซิร์ฟเวอร์) |
| `config_generator.py` | สร้าง vless/vmess link + ชื่อคอนฟิก |
| `bank_config.py` | ตรวจสลิปโอนเงิน |
| `promptpay.py` | สร้าง QR PromptPay |
| `slipok_client.py` | ตรวจสลิปผ่าน SlipOK |
| `web_app.py` | หน้าเว็บ (port 8445) |
| `watchdog.sh` | เช็คสุขภาพ bot ทุก 5 นาที |
| `cleanup_expired.py` | ลบบัญชีหมดอายุเกิน 7 วัน |
| `check_app_status.py` | เช็คสถานะ FB App Review |
| `backup.sh` / `backup-github.sh` | สำรองข้อมูล → GitHub EkromSSH/ekromvpn-backup |

---

## 6️⃣ ฟลอว์การสั่งซื้อ (สำคัญ!)

```
ลูกค้าพิมพ์ "1" / "สั่งซื้อ" / "สมัคร"
  → เลือกแพ็กเกจ (กด 1-4)
  → เลือกเซิร์ฟเวอร์ (1-7)
  → กรอกชื่อ (≥2 ตัวอักษร)
  → กรอกเบอร์ (ข้ามได้)
  → ระบบสร้าง QR จ่ายเงิน + แจ้งยอด
  → ลูกค้าส่งสลิป (รูป) → ตรวจ
  → ✅ "กำลังสร้างบัญชีให้คุณ..." → create_order()
  → ส่งคอนฟิก (vless://...) + QR ลงในแชท
```

**คำสั่งลับ (พิมพ์ในแชท):**
- `สมัคร` / `ซื้อ` / `สั่ง` → หน้าสมัคร
- `ต่ออายุ` / `ต่อวัน` / `เพิ่มวัน` → หน้าต่ออายุ
- `แพ็กเกจ` 365วัน = กด 0
- เมนู: 1 สั่งซื้อ / 2 ยกเลิก / 3 ต่ออายุ / 4 วิธีใช้ / 9 ติดต่อแอดมิน

**config ที่ส่งลูกค้า:** `[ServerPrefix]-[Name]-[Phone]-[Expiry]` เช่น `AIS-PLAY-สมชาย-0812345678-1/ก.ย./2569`

**ชื่อซ้ำ:** email ในระบบต่อท้าย timestamp อัตโนมัติ (`ชื่อ-เบอร์-20260803-002355`) ป้องกัน error ซ้ำ — ชื่อที่โชว์ในคอนฟิกยังปกติ

---

## 7️⃣ การบริหารระบบ (คำสั่ง)

```bash
systemctl status hermes-bot      # เช็คสถานะ
systemctl restart hermes-bot     # รีสตาร์ท (หลังแก้โค้ด)
journalctl -u hermes-bot -n 50   # ดู log
crontab -l                       # ดู cron ทั้งหมด
# log ตรวจสลิป: /var/log/hermes-bot-watchdog.log
# log ลบบัญชี: /var/log/hermes-cleanup.log
```

**หลังแก้โค้ดทุกครั้ง:** `systemctl restart hermes-bot` + ทดสอบจริง (สั่งซื้อ test)

---

## 8️⃣ สถานะค้าง & ข้อควรรู้

- **Facebook App Review:** ยังไม่ผ่าน (แอปโหมด Development) — ตอนนี้ Meta ส่ง webhook เฉพาะแอดมินเพจ คนอื่นทักไม่ตอบ จนกว่าแอปผ่าน `pages_messaging` review
- **ตรวจสถานะ:** cron 09:00 ทุกวัน (`check_app_status.py`) — ผ่านเมื่อไหร่แจ้งอัตโนมัติ
- **QR ในแชทขึ้นเมนู "โอนด้วย K PLUS":** ฟีเจอร์ของ LINE/FB เอง (จดจำ QR PromptPay) — ปิดไม่ได้ ไม่ใช่บั๊ก
- **เมนู "โอนเงินผ่าน QR" ใน LINE:** เหมือนกัน เป็นตัวแอป ไม่ใช่ระบบเรา

---

## 9️⃣ Backup

- ระบบ backup อัตโนมัติ → GitHub Private: `EkromSSH/ekromvpn-backup`
- ไฟล์: `backup.sh` + `backup-github.sh`
- ฐานข้อมูล session: `/root/hermes-commerce/sessions.db`

---

*เอกสารนี้ให้ AI ตัวอื่นทำงานต่อได้ — ถ้าต้องการ token จริง เปิด `/root/hermes-commerce/config.py`*
