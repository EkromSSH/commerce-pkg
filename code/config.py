"""
Configuration for Hermes Commerce LINE Bot + x-ui
[Template] — ลูกค้าต้องกรอกค่าผ่าน commerce-config.sh หรือแก้ที่นี่ก็ได้
"""
import os

# ===== x-ui Panel =====
# ใช้ Bearer token API (X-UI 3.2.6+) — ไม่ต้องใช้ user/pass
XUI_BASE_URL = ""              # เช่น http://xui.example.com:4433
XUI_BASE_PATH = ""             # เช่น /pZ9eUYH49EhZt3urIq (ถ้ามี secret path)
XUI_USERNAME = ""              # (เก็บไว้กรณี X-UI เก่า)
XUI_PASSWORD = ""              # (เก็บไว้กรณี X-UI เก่า)
XUI_API_TOKEN = ""             # Channel access token จาก X-UI panel

# ===== LINE Messaging API =====
LINE_CHANNEL_ACCESS_TOKEN = ""  # Long-lived Channel Access Token
LINE_CHANNEL_SECRET = ""       # Channel Secret

# ===== Webhook Server =====
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8443
SERVER_DOMAIN = ""             # โดเมนที่ LINE ส่ง webhook เช่น bot.myshop.com
SERVER_IP = ""                 # IP เครื่อง (auto detect ตอนติดตั้ง)

# SSL cert (auto-fill โดย install-commerce.sh)
SSL_CERT = ""                  # เช่น /etc/letsencrypt/live/bot.myshop.com/fullchain.pem
SSL_KEY = ""                   # เช่น /etc/letsencrypt/live/bot.myshop.com/privkey.pem

# ===== SlipOK (ตรวจสอบสลิป) =====
SLIPOK_API_KEY = ""            # API Key จาก https://slipok.com
SLIPOK_BRANCH_ID = ""          # เช่น 72480
SLIPOK_API_URL = ""            # เช่น https://api.slipok.com/api/line/apikey/72480

# ===== PromptPay (รับเงิน) =====
PROMPTPAY_ID = ""              # เบอร์โทร/เลขบัตร เช่น 0812345678

# ===== Bank accounts (บัญชีรับโอน) =====
BANK_ACCOUNTS = []             # [{"bank":"กสิกร","name":"ชื่อบัญชี","account":"xxx","promptpay":"0812345678"}]

# ===== Product Packages =====
PACKAGES = {
    "1": {"name": "1 เดือน", "price": 50, "days": 30, "limit_ip": 2, "total_gb": 0},
    "2": {"name": "3 เดือน", "price": 140, "days": 90, "limit_ip": 2, "total_gb": 0},
    "3": {"name": "6 เดือน", "price": 240, "days": 180, "limit_ip": 2, "total_gb": 0},
    "4": {"name": "1 ปี", "price": 420, "days": 365, "limit_ip": 2, "total_gb": 0},
}

# ===== Inbound selection =====
DEFAULT_INBOUND_ID = 1

# ===== Facebook Messenger =====
FB_APP_ID = ""
FB_APP_SECRET = ""
FB_PAGE_ID = ""
FB_ACCESS_TOKEN = ""
FB_VERIFY_TOKEN = ""           # ตั้งเองได้ เช่น myshop_fb_verify_2026
