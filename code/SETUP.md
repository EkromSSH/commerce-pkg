# 📱 ขั้นตอนสร้าง LINE Official Account + เชื่อมระบบ

## ขั้นตอนที่ 1: สร้าง LINE OA

### 1. เปิดเว็บ LINE OA Manager
เข้า **https://manager.line.biz** ด้วย LINE ส่วนตัวของคุณ

### 2. กด "สร้างบัญชีผู้ใช้ใหม่"
- เลือก **"ธุรกิจ"**
- ใส่ชื่อร้าน (เช่น **VIP SERVER** หรือ **DA VPN**)
- เลือกหมวดหมู่: Internet / Telecom
- เลือกไอคอนโปรไฟล์
- กดสร้าง

### 3. เปิด Messaging API
- ไปที่ **Settings (ตั้งค่า)** → **Messaging API**
- กด **"Connect"** หรือ **"เชื่อมต่อ"**
- มันจะพาคุณไป LINE Developers Console
- กด OK / ยืนยัน

### 4. ใน LINE Developers Console
- ถ้ายังไม่มี **Provider** → กด Create New Provider (ชื่ออะไรก็ได้)
- ถ้ามีแล้ว → เลือก Provider ที่มีชื่อร้านคุณ
- กด **Create Channel** → เลือก **Messaging API**
- กรอก:
  - **Channel name:** VIP Server (หรือชื่อร้าน)
  - **Channel description:** จำหน่ายเซิร์ฟเวอร์ VPN
  - **Category:** Business
  - **Subcategory:** Communication/Internet
- กด **Create**

### 5. เอา Keys
**Basic Settings** tab → จะเห็น:
- **Channel ID** (ตัวเลข)
- **Channel Secret** (กด Issue)

**Messaging API** tab → เลื่อนลงไป:
- **Channel Access Token** → กด **Issue**
- จะได้ token ยาวๆ คัดลอกเก็บไว้

---

## ขั้นตอนที่ 2: ใส่ Token เข้าระบบ

SSH เข้า VPS แล้วรัน:

```bash
nano /root/hermes-commerce/config.py
```

แก้ 2 บรรทัดนี้:

```python
LINE_CHANNEL_ACCESS_TOKEN = "Bearer YOUR_CHANNEL_ACCESS_TOKEN"
LINE_CHANNEL_SECRET = "YOUR_CHANNEL_SECRET"
```

ให้ใส่ค่าจริงแทน `YOUR_...`

---

## ขั้นตอนที่ 3: ตั้งค่า Webhook ใน LINE Developers

กลับไปที่ LINE Developers Console → **Messaging API** tab

### Webhook settings:
1. **Webhook URL** → ใส่:
   ```
   https://vip4.idavpn.win:8443/callback
   ```
2. กด **Update**
3. กด **Verify** → ควรขึ้น **Success**

### ปิด Auto-reply:
- กลับไปที่ LINE OA Manager (manager.line.biz)
- **Settings** → **Reply settings**
- ปิด **Auto-reply messages**
- ปิด **Greeting messages**
- เปิด **Webhook** ไว้เท่านั้น

---

## ขั้นตอนที่ 4: รีสตาร์ท Bot

```bash
systemctl restart hermes-commerce
journalctl -u hermes-commerce -f
```

---

## ขั้นตอนที่ 5: ทดสอบ

1. เพิ่ม LINE OA ของคุณเป็นเพื่อน (ด้วย LINE ส่วนตัว)
2. พิมพ์ "สมัคร"
3. Bot ควรตอบกลับ

---

## เปลี่ยนแพ็กเกจ/ราคา

แก้ไฟล์ `/root/hermes-commerce/config.py`:

```python
PACKAGES = {
    "1": {"name": "1 เดือน", "price": 50, "days": 30, "limit_ip": 2, "total_gb": 0},
    "2": {"name": "3 เดือน", "price": 120, "days": 90, "limit_ip": 3, "total_gb": 0},
    "3": {"name": "6 เดือน", "price": 200, "days": 180, "limit_ip": 3, "total_gb": 0},
    "4": {"name": "1 ปี", "price": 350, "days": 365, "limit_ip": 5, "total_gb": 0},
}
```

แล้ว restart:
```bash
systemctl restart hermes-commerce
```

---

## คำสั่งที่มีประโยชน์

```bash
# ดูสถานะ
systemctl status hermes-commerce

# ดู log
journalctl -u hermes-commerce -f

# รีสตาร์ท
systemctl restart hermes-commerce

# หยุด
systemctl stop hermes-commerce

# แก้ไข config
nano /root/hermes-commerce/config.py
```
