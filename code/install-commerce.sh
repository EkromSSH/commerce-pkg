#!/bin/bash
# ══════════════════════════════════════════════════════════
#  install-commerce.sh — ติดตั้งระบบ LINE Commerce Bot อัตโนมัติ
#  รันบน VPS ใหม่ (Ubuntu 20.04/22.04/24.04)
#  วิธีใช้:  curl -s URL | bash   หรือ  bash install-commerce.sh
# ══════════════════════════════════════════════════════════
set -e

# ── ตั้งค่า ──
APP_DIR="/root/commerce"
APP_USER="root"
PYTHON_BIN="python3"
VENV_DIR="/opt/commerce-venv"
SERVICE_NAME="commerce"
DOMAIN_DEFAULT=""

# ── ตรวจสิทธิ์ root ──
if [ "$EUID" -ne 0 ]; then
    echo "❌ ต้องรันด้วย root (sudo bash install-commerce.sh)"
    exit 1
fi

echo "══════════════════════════════════════════"
echo "  🚀 ติดตั้ง LINE Commerce Bot"
echo "══════════════════════════════════════════"

# ── 1. ติดตั้ง dependencies ──
echo "📦 [1/7] ติดตั้ง packages..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
    python3 python3-venv python3-pip \
    nginx certbot python3-certbot-nginx \
    sqlite3 curl wget git cron 2>&1 | tail -2

# ── 2. สร้าง directory ──
echo "📁 [2/7] เตรียม directory..."
mkdir -p "$APP_DIR"/{configs,static,templates,temp_images,backups}
mkdir -p /var/www/cert

# ── 3. คัดลอก code ──
echo "📋 [3/7] คัดลอก source code..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$SCRIPT_DIR/code" ]; then
    cp -r "$SCRIPT_DIR/code/"* "$APP_DIR/"
else
    # กรณีรันผ่าน pipe (curl | bash) — ไฟล์มาจาก package
    cd "$APP_DIR"
    for f in app.py xui_client.py fb_bot.py slipok_client.py promptpay.py \
             config.py config_generator.py bank_config.py server_details.py \
             web_app.py web_demo.html commerce-config.sh cleanup_expired.py \
             check_app_status.py hermes-commerce.service install-ssl.sh \
             static templates; do
        [ -e "$SCRIPT_DIR/$f" ] && cp -r "$SCRIPT_DIR/$f" "$APP_DIR/"
    done
fi
chmod +x "$APP_DIR/commerce-config.sh"

# ── 4. สร้าง Python venv ──
echo "🐍 [4/7] ติดตั้ง Python venv..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet \
    flask line-bot-sdk requests promptpay-qr qrcode pillow gunicorn

# ── 5. สร้าง systemd service ──
echo "⚙️  [5/7] ตั้ง systemd service..."
cat > "/etc/systemd/system/$SERVICE_NAME.service" <<EOF
[Unit]
Description=LINE Commerce Bot — Auto Order + x-ui
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$VENV_DIR/bin/python3 $APP_DIR/app.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME" || true

# ── 6. ตั้ง nginx (proxy 443 → bot 8443 + cert) ──
echo "🌐 [6/7] ตั้ง nginx..."
if [ -t 0 ]; then
    read -p "  โดเมนสำหรับ webhook (เช่น bot.myshop.com) [ข้ามได้]: " DOMAIN < /dev/tty
else
    echo "  (ไม่มี tty — ข้ามการตั้ง nginx; รัน commerce-config.sh → เมนู 14 ภายหลัง)"
    DOMAIN=""
fi
DOMAIN=$(echo "$DOMAIN" | xargs)
if [ -n "$DOMAIN" ]; then
    # ตั้ง DNS A record ตรวจก่อน
    SHOPIP=$(hostname -I | awk '{print $1}')
    DNSIP=$(getent hosts "$DOMAIN" 2>/dev/null | awk '{print $1}' | head -1)
    if [ -z "$DNSIP" ]; then
        echo "  ⚠️  DNS ของ $DOMAIN ยังไม่ชี้มาที่ $SHOPIP — ตั้ง A record ก่อน แล้วรัน commerce-config.sh → เมนู 14"
    else
        bash "$APP_DIR/install-ssl.sh" "$DOMAIN"
    fi
    # nginx config
    cat > /etc/nginx/sites-available/commerce <<NGINX
server {
    listen 80;
    server_name $DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/cert; }
    location / {
        return 301 https://\$host\$request_uri;
    }
}
server {
    listen 443 ssl http2;
    server_name $DOMAIN;
    ssl_certificate     /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    location / {
        proxy_pass http://127.0.0.1:8443;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 60s;
    }
}
NGINX
    ln -sf /etc/nginx/sites-available/commerce /etc/nginx/sites-enabled/commerce
    nginx -t && systemctl reload nginx
fi

# ── 7. ตั้ง cert auto-renew + cron cleanup ──
echo "🔄 [7/7] ตั้ง cron + cert auto-renew..."
(crontab -l 2>/dev/null | grep -v 'certbot renew'; \
 echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'") | crontab -

# ── สรุป ──
echo ""
echo "══════════════════════════════════════════"
echo "  ✅ ติดตั้งเสร็จ!"
echo "══════════════════════════════════════════"
echo ""
echo "  📂 ไฟล์: $APP_DIR"
echo "  🐍 Python: $VENV_DIR"
echo "  ⚙️  Service: systemctl status $SERVICE_NAME"
echo ""
echo "  🎯 ขั้นต่อไป — ตั้งค่า LINE/X-UI/SlipOK:"
echo "     bash $APP_DIR/commerce-config.sh"
echo ""
echo "  หรือแก้ไฟล์ตรงๆ:  nano $APP_DIR/config.py"
echo ""
echo "  📖 เอกสาร:  cat $APP_DIR/SETUP.md"
echo "══════════════════════════════════════════"
