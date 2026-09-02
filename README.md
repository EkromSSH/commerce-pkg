# commerce-pkg

LINE/FB Commerce Bot — ระบบสั่งซื้อ VPN อัตโนมัติผ่าน LINE + Facebook + X-UI

## สิ่งที่มี

| ไฟล์ | หน้าที่ |
|---|---|
| `install-commerce.sh` | ติดตั้งอัตโนมัติ (apt + venv + systemd + nginx + cert ผ่าน CF DNS) |
| `commerce-config.sh` | 16 เมนูให้ลูกค้ากรอก LINE/X-UI/SlipOK/PromptPay/FB/โดเมน |
| `install-ssl.sh` | ออก SSL Let's Encrypt ผ่าน Cloudflare DNS API |
| `app.py` | Flask bot (LINE + FB + SlipOK + PromptPay) |
| `xui_client.py` | สร้าง/ต่ออายุ account ใน X-UI 3X-UI v3.2.6 |
| `slipok_client.py` | ตรวจสอบสลิปโอนเงิน |
| `bank_config.py` | บัญชีรับเงิน (PromptPay) |
| `config.py` | Template ค่าตั้งต้น (ให้ลูกค้ากรอกผ่าน commerce-config.sh) |

## ใช้งาน

```bash
# 1. ติดตั้ง (รันบน VPS ใหม่ Ubuntu 20.04+)
bash install-commerce.sh

# 2. ตั้งค่า (LINE Token, X-UI, SlipOK, PromptPay, FB, โดเมน)
bash commerce-config.sh

# 3. ตั้ง SSL (ถ้ามีโดเมน + Cloudflare)
bash install-ssl.sh
```

## ต้องเตรียม

1. **VPS** (Ubuntu 20.04/22.04/24.04) — root access
2. **X-UI panel** (3X-UI v3.2.6+) — ติดตั้งบน VPS อื่นได้
3. **LINE Official Account** + Messaging API
4. **SlipOK API Key** (https://slipok.com)
5. **Cloudflare API Token** (สิทธิ์ Zone.DNS Edit) — สำหรับ SSL

## Flow การทำงาน

```
ลูกค้า (LINE/FB) → สั่งซื้อ → เลือกแพ็กเกจ → กรอกชื่อ/เบอร์
    → ส่งสลิป → SlipOK ตรวจ → ผ่าน → สร้าง account X-UI
    → ส่ง config/QR → ลูกค้าใช้งาน
```

## ข้อควรรู้

- X-UI v3.2.6+ ใช้ Bearer token API (ไม่ใช้ login user/pass)
- SlipOK API ตรวจสลิปจาก URL รูปภาพ (ต้องเข้าถึงได้จากภายนอก)
- certbot + acme.sh รองรับ Cloudflare DNS challenge (ไม่ต้องเปิด port 80)
