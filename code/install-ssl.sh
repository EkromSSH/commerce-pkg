#!/bin/bash
# install-ssl.sh — ติดตั้ง SSL Let's Encrypt ผ่าน Cloudflare DNS
# วิธีใช้:  bash install-ssl.sh yourdomain.com
# ต้องการ: CF_Token (Cloudflare API token ที่คุม zone ของโดเมน)
set -e
DOMAIN="${1:-}"
APP_DIR="/root/commerce"

if [ -z "$DOMAIN" ]; then
    echo "  🔐 ติดตั้ง SSL Let's Encrypt (Cloudflare DNS)"
    read -p "  โดเมน (เช่น bot.myshop.com): " DOMAIN < /dev/tty
    DOMAIN=$(echo "$DOMAIN" | xargs)
fi
if [ -z "$DOMAIN" ]; then
    echo "  ❌ ไม่ได้ใส่โดเมน"
    return 1 2>/dev/null || exit 1
fi

# หา acme.sh
ACME="/root/.acme.sh/acme.sh"
if [ ! -x "$ACME" ]; then
    echo "  📦 ติดตั้ง acme.sh..."
    curl -s https://get.acme.sh | sh -s email=admin@${DOMAIN#*.} 2>&1 | tail -2
    ACME="/root/.acme.sh/acme.sh"
fi

# ขอ CF token
read -p "  Cloudflare API Token (สิทธิ์ Zone.DNS Edit): " CF_TOKEN < /dev/tty
if [ -z "$CF_TOKEN" ]; then
    echo "  ❌ ไม่ได้ใส่ CF Token"
    exit 1
fi
export CF_Token="$CF_TOKEN"

echo "  🌐 ออก SSL สำหรับ $DOMAIN..."
"$ACME" --issue -d "$DOMAIN" --dns dns_cf --server letsencrypt 2>&1 | tail -5

if [ ! -f "/root/.acme.sh/${DOMAIN}_ecc/fullchain.cer" ]; then
    echo "  ❌ ออก SSL ไม่สำเร็จ"
    exit 1
fi

# ติดตั้ง cert
mkdir -p /etc/letsencrypt/live/"$DOMAIN"
cp /root/.acme.sh/${DOMAIN}_ecc/fullchain.cer /etc/letsencrypt/live/"$DOMAIN"/fullchain.pem
cp /root/.acme.sh/${DOMAIN}_ecc/${DOMAIN}.key /etc/letsencrypt/live/"$DOMAIN"/privkey.pem

# อัปเดต config.py ให้ชี้ cert
python3 - "$APP_DIR/config.py" "$DOMAIN" <<'PYEOF'
import sys
path, dom = sys.argv[1], sys.argv[2]
src = open(path, encoding='utf-8').read()
src = src.replace('SSL_CERT = ""', f'SSL_CERT = "/etc/letsencrypt/live/{dom}/fullchain.pem"')
src = src.replace('SSL_KEY = ""', f'SSL_KEY = "/etc/letsencrypt/live/{dom}/privkey.pem"')
open(path, 'w', encoding='utf-8').write(src)
print(f'  ✅ config.py: SSL_CERT/KEY ชี้ {dom}')
PYEOF

# ตั้ง cert auto-renew
(crontab -l 2>/dev/null | grep -v 'certbot renew'; \
 echo "0 3 * * * /root/.acme.sh/acme.sh --cron --renew-all --reloadcmd 'systemctl reload nginx' >/dev/null 2>&1") | crontab -

nginx -t && systemctl reload nginx 2>/dev/null
echo "  ✅ SSL ติดตั้งแล้ว! https://$DOMAIN"
