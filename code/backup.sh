#!/bin/bash
# ============================================
# 📦 EkromVPN — สคริปต์สำรองข้อมูล (Backup)
# ============================================
BACKUP_DIR="/root/ekromvpn-backup"
DATE=$(date +%Y%m%d_%H%M%S)

echo "⏳ กำลังสำรองข้อมูล... ($DATE)"

mkdir -p $BACKUP_DIR/$DATE

# 1. โค้ดระบบทั้งหมด
cp -r /root/hermes-commerce $BACKUP_DIR/$DATE/
echo "✅ โค้ดระบบ"

# 2. Nginx config
cp /etc/nginx/sites-available/hermes-commerce $BACKUP_DIR/$DATE/
echo "✅ Nginx config"

# 3. SSL Certificate
cp -r /root/cert $BACKUP_DIR/$DATE/
echo "✅ SSL Cert"

# 4. x-ui database (ผู้ใช้ + การตั้งค่า)
cp /etc/x-ui/x-ui.db $BACKUP_DIR/$DATE/
echo "✅ x-ui database"

# 5. Systemd service
cp /etc/systemd/system/hermes-commerce.service $BACKUP_DIR/$DATE/
echo "✅ Systemd service"

# 6. LINE Webhook URL (จดไว้)
echo "https://vip4.idavpn.win/callback" > $BACKUP_DIR/$DATE/line_webhook.txt
echo "✅ LINE Webhook"

# 7. บีบอัด
cd $BACKUP_DIR
tar -czf ekromvpn-backup-$DATE.tar.gz $DATE/
rm -rf $DATE/

echo ""
echo "===================================="
echo "✅ สำรองข้อมูลเสร็จ!"
echo "📦 ไฟล์: $BACKUP_DIR/ekromvpn-backup-$DATE.tar.gz"
echo "📦 ขนาด: $(du -h $BACKUP_DIR/ekromvpn-backup-$DATE.tar.gz | cut -f1)"
echo ""
echo "📥 ดาวน์โหลด: scp root@212.80.213.214:$BACKUP_DIR/ekromvpn-backup-$DATE.tar.gz ."
echo "===================================="
