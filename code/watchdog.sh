#!/bin/bash
# Watchdog: เช็ค Bot ทุก 5 นาที ถ้าค้าง/ตาย → restart
# ติดตั้ง: cron job ทุก 5 นาที

# ถ้า service ไม่ active → restart
if ! systemctl is-active --quiet hermes-bot; then
    echo "$(date) Bot not active - restarting" >> /var/log/hermes-bot-watchdog.log
    systemctl restart hermes-bot
    exit 0
fi

# ถ้า active แต่ไม่ตอบสนอง (ค้าง) → restart
if ! curl -sk --max-time 8 -o /dev/null "https://vip4.idavpn.win/callback"; then
    echo "$(date) Bot hanging - restarting" >> /var/log/hermes-bot-watchdog.log
    fuser -k 8443/tcp 2>/dev/null
    sleep 2
    systemctl restart hermes-bot
fi
