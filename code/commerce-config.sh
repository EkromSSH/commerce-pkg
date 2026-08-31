#!/bin/bash
# ══════════════════════════════════════════════════════════
#  commerce-config.sh — เมนูตั้งค่าระบบ LINE + X-UI + SlipOK + FB
#  ใช้โดยลูกค้า หลังจากติดตั้ง install-commerce.sh แล้ว
#  วิธีใช้:  bash commerce-config.sh
# ══════════════════════════════════════════════════════════
set -e

CONFIG_FILE="/root/commerce/config.py"
BACKUP_FILE="/root/commerce/config.py.bak.$(date +%s)"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ ไม่พบ $CONFIG_FILE — ต้องรัน install-commerce.sh ก่อน"
    exit 1
fi

# ── helper: แก้ค่าใน config.py (ใช้ python เพื่อความปลอดภัย) ──
setval() {
    local key="$1" val="$2"
    python3 - "$CONFIG_FILE" "$key" "$val" <<'PYEOF'
import sys, re
path, key, val = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(path, encoding='utf-8').read()
# escape quotes
val_esc = val.replace('\\', '\\\\').replace('"', '\\"')
# รองรับ string/int/list/dict — pattern: KEY = "..." | KEY = [...] | KEY = {...}
patterns = [
    (rf'({re.escape(key)}\s*=\s*)"[^"]*"', rf'\1"{val_esc}"'),          # string
    (rf'({re.escape(key)}\s*=\s*)\[[^\]]*\]', rf'\1{val_esc}'),            # list
    (rf'({re.escape(key)}\s*=\s*)\{{[^\}}]*\}}', rf'\1{val_esc}'),        # dict
    (rf'({re.escape(key)}\s*=\s*)\d+', rf'\1{val_esc}'),                  # int
]
for pat, rep in patterns:
    new = re.sub(pat, rep, src, count=1)
    if new != src:
        open(path, 'w', encoding='utf-8').write(new)
        print(f'  ✅ {key} = {val[:30]}{"..." if len(val)>30 else ""}')
        sys.exit(0)
print(f'  ❌ ไม่พบ key: {key}')
sys.exit(1)
PYEOF
}

ask() {  # รับค่าจากแป้นพิมพ์ (Enter = ข้าม)
    local var="$1" msg="$2" cur="$3"
    if [ -n "$cur" ] && [ "$cur" != "None" ]; then
        read -p "  $msg [$cur]: " val < /dev/tty
        [ -z "$val" ] && val="$cur"
    else
        read -p "  $msg: " val < /dev/tty
    fi
    eval "$var=\"\$val\""
}

show_cur() {
    python3 - "$CONFIG_FILE" "$1" <<'PYEOF'
import sys
try:
    src = open(sys.argv[1], encoding='utf-8').read()
    key = sys.argv[2]
    import re
    m = re.search(rf'{re.escape(key)}\s*=\s*"([^"]*)"', src)
    if m:
        v = m.group(1)
        print(v[:20] + "..." if len(v) > 20 else v)
    else:
        print("(ยังไม่ตั้ง)")
except Exception as e:
    print("(error)")
PYEOF
}

# ── ดึงค่าปัจจุบัน ──
getval() {
    python3 - "$CONFIG_FILE" "$1" <<'PYEOF'
import sys, re
try:
    src = open(sys.argv[1], encoding='utf-8').read()
    m = re.search(rf'{re.escape(sys.argv[2])}\s*=\s*"([^"]*)"', src)
    print(m.group(1) if m else "")
except: print("")
PYEOF
}

LINE_TOK=$(getval LINE_CHANNEL_ACCESS_TOKEN)
LINE_SEC=$(getval LINE_CHANNEL_SECRET)
XUI_URL=$(getval XUI_BASE_URL)
XUI_TOK=$(getval XUI_API_TOKEN)
XUI_PATH=$(getval XUI_BASE_PATH)
SLIPOK=$(getval SLIPOK_API_KEY)
SLIPOK_B=$(getval SLIPOK_BRANCH_ID)
PROMPT=$(getval PROMPTPAY_ID)
FB_TOK=$(getval FB_ACCESS_TOKEN)
FB_SEC=$(getval FB_APP_SECRET)
FB_VER=$(getval FB_VERIFY_TOKEN)
DOMAIN=$(getval SERVER_DOMAIN)

# ── เมนูหลัก ──
while true; do
    echo ""
    echo "══════════════════════════════════════════"
    echo "  ⚙️  ตั้งค่าระบบ LINE Commerce Bot"
    echo "══════════════════════════════════════════"
    echo "  1. โดเมน              [$DOMAIN]"
    echo "  2. X-UI URL           [$XUI_URL]"
    echo "  3. X-UI Secret Path   [$XUI_PATH]"
    echo "  4. X-UI Bearer Token  [${XUI_TOK:0:10}...]"
    echo "  5. LINE Token         [${LINE_TOK:0:10}...]"
    echo "  6. LINE Secret        [${LINE_SEC:0:8}...]"
    echo "  7. SlipOK API Key     [${SLIPOK:0:10}...]"
    echo "  8. SlipOK Branch ID   [$SLIPOK_B]"
    echo "  9. PromptPay เบอร์/เลข  [$PROMPT]"
    echo "  10. Facebook Token    [${FB_TOK:0:10}...]"
    echo "  11. Facebook Secret   [${FB_SEC:0:8}...]"
    echo "  12. Facebook Verify   [$FB_VER]"
    echo "──────────────────────────────────────────"
    echo "  13. 🧪 ทดสอบการเชื่อมต่อ (LINE + X-UI)"
    echo "  14. 🔒 ติดตั้ง SSL สำหรับโดเมน"
    echo "  15. 🔄 Restart Service"
    echo "  16. 💾 บันทึก + ออก"
    echo "══════════════════════════════════════════"
    read -p "  เลือก (1-16): " ch < /dev/tty

    case "$ch" in
        1)  ask DOMAIN "โดเมน (เช่น bot.myshop.com)"
            setval SERVER_DOMAIN "$DOMAIN"
            setval SERVER_IP "$(curl -s -m 5 ifconfig.me 2>/dev/null || echo '')"
            XUI_PATH=$(getval XUI_BASE_PATH); SLIPOK=$(getval SLIPOK_API_KEY); FB_TOK=$(getval FB_ACCESS_TOKEN); FB_SEC=$(getval FB_APP_SECRET); FB_VER=$(getval FB_VERIFY_TOKEN)
            DOMAIN=$(getval SERVER_DOMAIN) ;;
        2)  ask XUI_URL "URL ของ X-UI (เช่น http://xui.myshop.com:4433)"
            setval XUI_BASE_URL "$XUI_URL"
            XUI_TOK=$(getval XUI_API_TOKEN); DOMAIN=$(getval SERVER_DOMAIN); XUI_PATH=$(getval XUI_BASE_PATH) ;;
        3)  ask XUI_PATH "Secret Path (เช่น /pZ9eUYH49EhZt3urIq หรือเว้นว่าง)"
            setval XUI_BASE_PATH "$XUI_PATH" ;;
        4)  ask XUI_TOK "X-UI Bearer Token (Channel access token จาก X-UI)"
            setval XUI_API_TOKEN "$XUI_TOK"
            XUI_URL=$(getval XUI_BASE_URL); XUI_PATH=$(getval XUI_BASE_PATH); DOMAIN=$(getval SERVER_DOMAIN) ;;
        5)  ask LINE_TOK "LINE Channel Access Token (long-lived)"
            setval LINE_CHANNEL_ACCESS_TOKEN "$LINE_TOK"
            LINE_SEC=$(getval LINE_CHANNEL_SECRET) ;;
        6)  ask LINE_SEC "LINE Channel Secret"
            setval LINE_CHANNEL_SECRET "$LINE_SEC" ;;
        7)  ask SLIPOK "SlipOK API Key"
            setval SLIPOK_API_KEY "$SLIPOK"
            setval SLIPOK_API_URL "https://api.slipok.com/api/line/apikey/$SLIPOK_B"
            PROMPT=$(getval PROMPTPAY_ID); SLIPOK_B=$(getval SLIPOK_BRANCH_ID) ;;
        8)  ask SLIPOK_B "SlipOK Branch ID (ตัวเลข เช่น 72480)"
            setval SLIPOK_BRANCH_ID "$SLIPOK_B"
            setval SLIPOK_API_URL "https://api.slipok.com/api/line/apikey/$SLIPOK_B"
            SLIPOK=$(getval SLIPOK_API_KEY) ;;
        9)  ask PROMPT "PromptPay เบอร์โทร/เลขบัตร (เช่น 0812345678)"
            setval PROMPTPAY_ID "$PROMPT"
            SLIPOK=$(getval SLIPOK_API_KEY); SLIPOK_B=$(getval SLIPOK_BRANCH_ID) ;;
        10) ask FB_TOK "Facebook Page Access Token"
            setval FB_ACCESS_TOKEN "$FB_TOK"
            FB_SEC=$(getval FB_APP_SECRET); FB_VER=$(getval FB_VERIFY_TOKEN) ;;
        11) ask FB_SEC "Facebook App Secret"
            setval FB_APP_SECRET "$FB_SEC"
            FB_TOK=$(getval FB_ACCESS_TOKEN); FB_VER=$(getval FB_VERIFY_TOKEN) ;;
        12) ask FB_VER "Facebook Verify Token (ตั้งเอง เช่น myshop_fb_2026)"
            setval FB_VERIFY_TOKEN "$FB_VER" ;;
        13)
            echo "  🧪 ทดสอบ..."
            python3 -c "
import config
print('  LINE token set:', bool(config.LINE_CHANNEL_ACCESS_TOKEN))
print('  X-UI token set:', bool(config.XUI_API_TOKEN))
print('  X-UI URL set:', bool(config.XUI_BASE_URL))
print('  SlipOK key set:', bool(config.SLIPOK_API_KEY))
print('  PromptPay set:', bool(config.PROMPTPAY_ID))
print('  Domain:', config.SERVER_DOMAIN or '(ยังไม่ตั้ง)')
# ทดสอบ LINE
if config.LINE_CHANNEL_ACCESS_TOKEN:
    import urllib.request, json
    req = urllib.request.Request('https://api.line.me/v2/bot/info')
    req.add_header('Authorization', 'Bearer ' + config.LINE_CHANNEL_ACCESS_TOKEN)
    try:
        r = json.load(urllib.request.urlopen(req, timeout=10))
        print('  ✅ LINE bot info:', r.get('displayName', '?'), r.get('basicId', '?'))
    except Exception as e:
        print('  ❌ LINE token ใช้ไม่ได้:', str(e)[:80])
" 2>&1 | head -15 ;;
        14)
            bash /root/commerce/install-ssl.sh
            ;;
        15)
            echo "  🔄 Restarting service..."
            systemctl restart commerce
            sleep 2
            systemctl is-active commerce && echo "  ✅ service active" || echo "  ❌ service fail"
            ;;
        16)
            echo "  💾 บันทึกเรียบร้อย"
            exit 0
            ;;
        *) echo "  ❌ เลือก 1-16 เท่านั้น" ;;
    esac
done
