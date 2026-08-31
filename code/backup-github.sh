#!/bin/bash
# ============================================
# 📦 EkromVPN — Backup + Push to GitHub
# ============================================
DATE=$(date +%Y%m%d_%H%M)
BACKUP_DIR="/root/ekromvpn-backup"
REPO_DIR="/root/ekromvpn-backup"
PASS=$(cat $REPO_DIR/backup-password.txt 2>/dev/null || openssl rand -hex 16)

# 1. Backup files
mkdir -p $BACKUP_DIR/tmp
cp -r /root/hermes-commerce $BACKUP_DIR/tmp/
cp /etc/nginx/sites-available/hermes-commerce $BACKUP_DIR/tmp/nginx.conf 2>/dev/null
cp -r /root/cert $BACKUP_DIR/tmp/cert 2>/dev/null
cp /etc/x-ui/x-ui.db $BACKUP_DIR/tmp/x-ui.db 2>/dev/null
cp /etc/systemd/system/hermes-commerce.service $BACKUP_DIR/tmp/hermes-commerce.service 2>/dev/null

# 2. Compress
cd $BACKUP_DIR/tmp
tar -czf $BACKUP_DIR/ekromvpn-backup-$DATE.tar.gz .
cd $BACKUP_DIR
rm -rf tmp/

# 3. Encrypt (AES-256)
openssl enc -aes-256-cbc -salt -pbkdf2 \
  -in $BACKUP_DIR/ekromvpn-backup-$DATE.tar.gz \
  -out $BACKUP_DIR/ekromvpn-backup-$DATE.tar.gz.enc \
  -pass pass:"$PASS"

# 4. Save password
echo "$PASS" > $BACKUP_DIR/backup-password-$DATE.txt

# 5. Git Push
cd $REPO_DIR
cp $BACKUP_DIR/ekromvpn-backup-$DATE.tar.gz.enc .
git add *.enc
git commit -m "Auto backup $DATE"
git push origin main 2>/dev/null

# 6. Clean old (keep last 30 days)
find $BACKUP_DIR -name "ekromvpn-backup-*.tar.gz" -mtime +30 -delete
find $BACKUP_DIR -name "*.enc" -mtime +30 -delete

echo "✅ Backup $DATE — pushed to GitHub"
