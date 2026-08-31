#!/bin/bash
# 🚀 EkromVPN — สคริปต์กู้คืนอัตโนมัติ (ก็อปปี้บรรทัดนี้ไฟลนเดียว)
# วิธีใช้: วางคำสั่งนี้ SSH แล้วรันเลย!
set -e

echo "⏳ กำลังกู้คืนระบบ EkromVPN..."

# 1. อัปเดต + ติดตั้ง
apt update && apt upgrade -y
apt install -y nginx python3 python3-pip sqlite3 git
pip3 install flask requests qrcode[pil] line-bot-sdk promptpay-qr
curl https://get.acme.sh | sh

# 2. ดาวน์โหลด Backup
cd /root
git clone https://github.com/EkromSSH/ekromvpn-backup.git
cd ekromvpn-backup

# 3. ถอดรหัส (ใส่รหัส)
echo ""
echo "🔐 ใส่รหัสผ่าน Backup:"
read PASS
openssl enc -aes-256-cbc -d -pbkdf2 -in backup-*.enc -out backup.tar.gz -pass pass:"$PASS"
tar -xzf backup.tar.gz

# 4. กู้คืน
cp -r hermes-commerce /root/
cp -r cert /root/cert/
cp nginx.conf /etc/nginx/sites-available/hermes-commerce
ln -sf /etc/nginx/sites-available/hermes-commerce /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# 5. x-ui
bash <(curl -Ls https://raw.githubusercontent.com/vaxilu/x-ui/master/install.sh)
systemctl stop x-ui
cp x-ui.db /etc/x-ui/x-ui.db
systemctl start x-ui

# 6. SSL + เริ่ม
/root/.acme.sh/acme.sh --issue -d vip4.idavpn.win --standalone
nginx -t && systemctl start nginx
cp hermes-commerce/hermes-commerce.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable hermes-commerce
systemctl start hermes-commerce

echo ""
echo "===================================="
echo "✅ กู้คืนเสร็จ!"
echo "🔗 LINE Bot: https://vip4.idavpn.win/health"
echo "🔗 เว็บ: https://vip4.idavpn.win/"
echo "📱 ทดสอบพิมพ์ 'สมัคร' ใน LINE OA"
echo "===================================="
