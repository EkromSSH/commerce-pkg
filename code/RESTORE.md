# 🚀 กู้คืนระบบ EkromVPN — ฉบับมือใหม่
#
# สมมุติ: VPS เก่าตาย → ซื้อ VPS ใหม่ → ตั้ง Domain ชี้ IP ใหม่แล้ว
# ทำตามนี้ทีละขั้นตอน!


# === STEP 1: SSH เข้า VPS ใหม่ ===
ssh root@IPใหม่


# === STEP 2: รันคำสั่งติดตั้งพื้นฐาน (ก็อปไปวางทีละคำสั่ง) ===

apt update && apt upgrade -y
apt install -y nginx python3 python3-pip sqlite3 git
pip3 install flask requests qrcode[pil] line-bot-sdk promptpay-qr
curl https://get.acme.sh | sh


# === STEP 3: ดาวน์โหลด Backup จาก GitHub ===

git clone https://github.com/EkromSSH/ekromvpn-backup.git
cd ekromvpn-backup


# === STEP 4: ถอดรหัส Backup (ใส่รหัสตอนที่ให้สร้าง backup) ===

# หารหัสจาก README.md
cat README.md

# ถอดรหัส
openssl enc -aes-256-cbc -d -pbkdf2 -in backup-ล่าสุด.enc -out backup.tar.gz

# แตกไฟล์
tar -xzf backup.tar.gz
# → จะได้โฟลเดอร์ hermes-commerce/, cert/, nginx.conf, x-ui.db


# === STEP 5: กู้คืนไฟล์ทั้งหมด ===

cp -r hermes-commerce /root/
cp cert /root/cert/
cp nginx.conf /etc/nginx/sites-available/hermes-commerce
ln -sf /etc/nginx/sites-available/hermes-commerce /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default


# === STEP 6: ติดตั้ง x-ui ===

bash <(curl -Ls https://raw.githubusercontent.com/vaxilu/x-ui/master/install.sh)

# หยุด x-ui แล้วลง DB เก่า
systemctl stop x-ui
cp x-ui.db /etc/x-ui/x-ui.db
systemctl start x-ui


# === STEP 7: ต่ออายุ SSL ===

/root/.acme.sh/acme.sh --issue -d vip4.idavpn.win --standalone


# === STEP 8: เริ่มระบบทั้งหมด ===

# Nginx
nginx -t && systemctl start nginx

# LINE Bot
cp hermes-commerce/hermes-commerce.service /etc/systemd/system/
cd /root/hermes-commerce
python3 -c "import app"  # ทดสอบว่าไม่มี error

systemctl daemon-reload
systemctl enable hermes-commerce
systemctl start hermes-commerce


# === STEP 9: เช็คว่าทำงาน ===

curl -sk https://vip4.idavpn.win/health          # Bot
curl -sk https://vip4.idavpn.win/3HcGm595TZjDOO6F5z/login  # x-ui panel
curl -sk https://vip4.idavpn.win/                # Website


# === STEP 10: ทดสอบ LINE Bot ===

# ส่งข้อความ "สมัคร" ไปที่ LINE OA EkromVPN
# ถ้าตอบกลับ = ใช้ได้!

# ======== เสร็จแล้ว ========
