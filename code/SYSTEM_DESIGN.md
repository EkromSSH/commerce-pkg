# 🏗️ EkromVPN — ระบบเว็บครบวงจร (PHP + MySQL + Tailwind)

## 📁 โครงสร้างไฟล์

```
ekromvpn/
├── index.php                    # หน้าแรก แสดงสินค้า/แพ็กเกจ
├── login.php                    # เข้าสู่ระบบ
├── register.php                 # สมัครสมาชิก
├── logout.php                   # ออกจากระบบ
├── server.php                   # รายละเอียดเซิร์ฟเวอร์
├── order.php                    # สั่งซื้อ
├── payment.php                  # ชำระเงิน + QR
├── success.php                  # แสดง Config สำเร็จ
│
├── member/                      # หน้าสมาชิก
│   ├── index.php               # Dashboard
│   ├── wallet.php              # กระเป๋าเงิน
│   ├── topup.php               # เติมเงิน
│   ├── orders.php              # ประวัติซื้อ
│   └── buy.php                 # API ซื้อด้วย wallet
│
├── admin/                       # ระบบ Admin
│   ├── index.php               # Dashboard
│   ├── users.php               # จัดการผู้ใช้
│   ├── orders.php              # จัดการออเดอร์
│   ├── topups.php              # จัดการเติมเงิน
│   ├── servers.php             # จัดการเซิร์ฟเวอร์
│   └── api_add_wallet.php      # API เติมเงินโดย admin
│
├── api/                         # API endpoints
│   ├── check_slip.php          # ตรวจสลิป (SlipOK)
│   ├── create_user.php         # สร้าง user x-ui
│   └── topup_verify.php        # ยืนยันเติมเงิน
│
├── includes/                    # Core
│   ├── config.php              # DB + API Keys
│   ├── db.php                  # DB Connection (PDO)
│   ├── auth.php                # Auth functions
│   ├── functions.php           # Utility functions
│   ├── xui_client.php          # x-ui API Client
│   ├── slipok_client.php       # SlipOK API Client
│   └── promptpay.php           # PromptPay QR Generator
│
├── assets/
│   ├── css/
│   │   ├── tailwind.css        # Tailwind build
│   │   └── custom.css          # Custom styles
│   ├── js/
│   │   ├── main.js             # Core JS
│   │   └── sweetalert.js       # SweetAlert2
│   └── images/
│       ├── logo.png
│       └── banners/
│
├── uploads/
│   ├── qrcodes/                # QR images
│   └── temp/                   # temp slip images
│
└── .htaccess                   # URL rewrite + security
```

---

## 🗄️ ฐานข้อมูล MySQL

```sql
-- ===== ตารางผู้ใช้ =====
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,  -- bcrypt hashed
    email VARCHAR(100),
    phone VARCHAR(20),
    role ENUM('user', 'admin') DEFAULT 'user',
    wallet DECIMAL(10,2) DEFAULT 0.00,
    status ENUM('active', 'banned') DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_login TIMESTAMP NULL,
    INDEX idx_username (username),
    INDEX idx_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ===== ตารางคำสั่งซื้อ =====
CREATE TABLE orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_no VARCHAR(20) UNIQUE NOT NULL,  -- รหัสออเดอร์
    user_id INT NOT NULL,
    package_key VARCHAR(10) NOT NULL,
    server_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    payment_method ENUM('wallet', 'slip') DEFAULT 'slip',
    status ENUM('pending', 'paid', 'completed', 'cancelled') DEFAULT 'pending',
    config_link TEXT,
    expiry_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user (user_id),
    INDEX idx_status (status),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ===== ตารางเติมเงิน =====
CREATE TABLE topups (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    slip_path VARCHAR(255),
    status ENUM('pending', 'completed', 'rejected') DEFAULT 'pending',
    admin_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user (user_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ===== ตารางเซิร์ฟเวอร์ =====
CREATE TABLE servers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    carrier VARCHAR(50),
    protocol VARCHAR(50),
    port INT,
    price_monthly DECIMAL(10,2),
    price_quarterly DECIMAL(10,2),
    price_semiannual DECIMAL(10,2),
    price_yearly DECIMAL(10,2),
    speed VARCHAR(50),
    max_devices INT DEFAULT 2,
    unlimited_gb BOOLEAN DEFAULT TRUE,
    features TEXT,           -- JSON array
    addon_codes TEXT,        -- JSON array
    compatible TEXT,         -- JSON array
    note TEXT,
    banner_style VARCHAR(20),
    sort_order INT DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ===== ตาราง Sessions (ป้องกัน session hijacking) =====
CREATE TABLE sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    session_token VARCHAR(255) UNIQUE NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_token (session_token),
    INDEX idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ===== Admin เริ่มต้น =====
INSERT INTO users (username, password, role) VALUES 
('admin', '$2y$10$...', 'admin');  -- รหัส: admin123 (bcrypt)

-- ===== เซิร์ฟเวอร์เริ่มต้น =====
INSERT INTO servers (name, carrier, protocol, port, speed, features, addon_codes, compatible, banner_style, sort_order) VALUES
('AIS-VIP', 'AIS', 'VMESS · WebSocket', 80, '64Kbps-128Kbps',
 '["รองรับ AIS 4G/5G","ความเร็ว 64K-128K ไม่ลดสปีด","ไม่จำกัด GB","ใช้ร่วมกับ AIS PLAY ได้"]',
 '[{"name":"สมัครโปรกันรั้ว","code":"*777*7068#","price":"35 บ./ด."},{"name":"AISPLAY 1 วัน","code":"*777*7310#","price":"9.63 บ."}]',
 '["TRUE","DTAC","TOT","3BB"]', 'ais', 1),
('AIS-TCP', 'AIS', 'VMESS · TCP', 8080, '64Kbps-128Kbps',
 '["รองรับ AIS 4G/5G","TCP Protocol เสถียร","ไม่จำกัด GB"]',
 '[]',
 '["TRUE","DTAC","TOT"]', 'ais', 2),
('FB-GAMING', 'AIS/FB', 'VMESS · TLS', 8000, 'สูงสุด 128Kbps',
 '["TLS Encryption ป้องกัน DPI","เล่นเกมได้","ไม่จำกัด GB"]',
 '[]',
 '["TRUE","DTAC"]', 'fb', 3),
('TRUE VLESS', 'TRUE', 'VLESS · WebSocket', 2053, '64Kbps-128Kbps',
 '["รองรับ TRUE 4G/5G","VLESS Protocol ล่าสุด","ไม่จำกัด GB","ใช้ TRUE WiFi ได้"]',
 '[]',
 '["AIS","DTAC"]', 'true', 4);
```

---

## 🔒 มาตรฐานความปลอดภัย

### 1. การเข้ารหัส (Encryption)
| รายการ | วิธี |
|--------|-----|
| รหัสผ่าน | `password_hash(PASSWORD_BCRYPT, ['cost'=>12])` |
| Session Token | `bin2hex(random_bytes(32))` |
| CSRF Token | `bin2hex(random_bytes(32))` ต่อ session |
| XSS | `htmlspecialchars($var, ENT_QUOTES, 'UTF-8')` |
| SQL Injection | PDO Prepared Statements **เท่านั้น** |

### 2. Session Security
```php
// เก็บ session ใน DB ไม่ใช่ file
// ตรวจสอบ IP + User-Agent ทุก request
session_start();
$token = bin2hex(random_bytes(32));
$db->query("INSERT INTO sessions (user_id, session_token, ip_address, user_agent, expires_at) 
            VALUES (?, ?, ?, ?, DATE_ADD(NOW(), INTERVAL 24 HOUR))",
            [$user_id, $token, $_SERVER['REMOTE_ADDR'], $_SERVER['HTTP_USER_AGENT']]);
setcookie('session_token', $token, time()+86400, '/', '', true, true);
```

### 3. Rate Limiting
```php
// ทุก API call ต้องจำกัด
$ip = $_SERVER['REMOTE_ADDR'];
$count = $db->query("SELECT COUNT(*) FROM api_logs WHERE ip=? AND created_at > DATE_SUB(NOW(), INTERVAL 1 MINUTE)", [$ip]);
if ($count > 30) die(json_encode(['error'=>'Too many requests']));
```

### 4. File Upload Security
```php
// รับเฉพาะรูปภาพ + ตรวจ MIME + limit size
$allowed = ['image/jpeg', 'image/png', 'image/webp'];
$max_size = 5 * 1024 * 1024; // 5MB
if (!in_array($_FILES['slip']['type'], $allowed)) die('Invalid file type');
if ($_FILES['slip']['size'] > $max_size) die('File too large');
```

### 5. การป้องกันเพิ่มเติม
- `.htaccess` ปิด directory listing
- headers: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`
- CORS: จำกัด origin
- Admin path ใช้ IP whitelist
- log ทุก action ที่ sensitive

---

## 🎨 UI/UX Design (Tailwind CSS)

### Color Palette
```css
:root {
  --bg-primary: #0d111c;
  --bg-card: #151d2e;
  --border: #1e2a45;
  --accent-1: #00d4ff;
  --accent-2: #7b2ff7;
  --accent-3: #00ff88;
  --text-primary: #ffffff;
  --text-secondary: #667799;
}
```

### หน้าต่างๆ

#### 1. หน้าแรก (index.php)
```
┌─────────────────────────────────┐
│  [Header] EkromVPN  [🔑] [👤]  │
├─────────────────────────────────┤
│  ┌──────┐ ┌──────┐              │
│  │ 50   │ │ 130  │  ← เลือก      │
│  │ 1 ด.  │ │ 3 ด. │    แพ็กเกจ   │
│  └──────┘ └──────┘              │
│  ┌──────┐ ┌──────┐              │
│  │ 240  │ │ 420  │              │
│  │ 6 ด. │ │ 12 ด.│              │
│  └──────┘ └──────┘              │
│                                 │
│  ┌─ เซิร์ฟเวอร์ ──────────────┐  │
│  │ 🇹🇭 AIS-VIP    ›          │  │
│  │ 🇹🇭 TRUE VLESS  ›         │  │
│  └───────────────────────────┘  │
│                                 │
│  [📦 สั่งซื้อตอนนี้เลย!]        │
└─────────────────────────────────┘
```

#### 2. Login (login.php) — Dark theme, centered card
```
┌─────────────────────────────────┐
│        [โลโก้ EkromVPN]          │
│                                 │
│  ┌─ เข้าสู่ระบบ ──────────────┐  │
│  │ 👤 ชื่อผู้ใช้              │  │
│  │ [________________]        │  │
│  │ 🔒 รหัสผ่าน               │  │
│  │ [________________]        │  │
│  │                           │  │
│  │ [🔑 เข้าสู่ระบบ]           │  │
│  │                           │  │
│  │ ยังไม่มีบัญชี? ลงทะเบียน   │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘
```

#### 3. Member Dashboard
```
┌─────────────────────────────────┐
│  👋 สวัสดี somchai     [🚪]    │
├─────────────────────────────────┤
│  💰 ยอดเงินคงเหลือ              │
│  ┌───────────────────────────┐  │
│  │       350.00 บาท          │  │
│  │  [💳 เติมเงิน] [🛒 ซื้อ]  │  │
│  └───────────────────────────┘  │
│                                 │
│  📦 คำสั่งซื้อล่าสุด             │
│  ┌───────────────────────────┐  │
│  │ AIS-VIP 1 เดือน · 50 บ.  │  │
│  │ ✅ ใช้งานถึง 27/ส.ค./69   │  │
│  │ 📋 vless://xxxx... (กดคัดลอก)│
│  └───────────────────────────┘  │
└─────────────────────────────────┘
```

#### 4. Admin Dashboard
```
┌─────────────────────────────────┐
│  👑 Admin Panel      [🚪]      │
├─────────────────────────────────┤
│  📊 สรุป: 42 users | 156 orders │
├─────────────────────────────────┤
│  👤 ผู้ใช้ทั้งหมด                │
│  ┌─ ID ── ชื่อ ── เงิน ── จัดการ ┐
│  │  1 │ admin  │ --   │ 👑     │
│  │  2 │ somchai│ 350  │ [เติม] │
│  │  3 │ narak  │ 120  │ [เติม] │
│  └─────────────────────────┘    │
│                                 │
│  💰 เติมเงิน pending: 3          │
│  ┌─ ID ── ชื่อ ── ยอด ── สลิป ─┐
│  │  5 │ somchai│ 200  │ [✅❌] │
│  └─────────────────────────┘    │
└─────────────────────────────────┘
```

### Tailwind Components หลัก

```html
<!-- Card Component -->
<div class="bg-[#151d2e] border border-[#1e2a45] rounded-2xl p-5">
  <h3 class="text-[#00d4ff] font-semibold text-sm mb-3">หัวข้อ</h3>
  <!-- content -->
</div>

<!-- Button Primary -->
<button class="w-full py-3.5 rounded-xl font-semibold text-white
         bg-gradient-to-r from-[#00d4ff] to-[#7b2ff7]
         hover:shadow-lg hover:shadow-[#00d4ff]/20
         transition-all duration-300">
  ➡️ ดำเนินการ
</button>

<!-- Input Field -->
<div class="mb-3">
  <label class="block text-xs text-[#667799] mb-1.5">ชื่อผู้ใช้</label>
  <input type="text" class="w-full p-3.5 bg-[#0d111c] border border-[#1e2a45]
                rounded-xl text-white text-sm
                focus:border-[#00d4ff] focus:outline-none
                transition-colors duration-200">
</div>

<!-- Responsive Grid - product cards -->
<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
  <!-- Product Card -->
</div>

<!-- Mobile Bottom Nav -->
<nav class="md:hidden fixed bottom-0 w-full bg-[#151d2e] border-t border-[#1e2a45] px-4 py-2
            flex justify-around">
  <a href="/" class="text-[#00d4ff] text-xs text-center">🏠 หน้าแรก</a>
  <a href="/member/wallet" class="text-[#667799] text-xs text-center">💳 เติมเงิน</a>
  <a href="/member" class="text-[#667799] text-xs text-center">👤 สมาชิก</a>
</nav>
```

### SweetAlert2 Examples

```javascript
// สั่งซื้อสำเร็จ
Swal.fire({
  icon: 'success',
  title: '✅ สั่งซื้อสำเร็จ!',
  text: 'สร้างบัญชี VPN ให้คุณแล้ว',
  footer: '<a href="/member/orders" style="color:#00d4ff;">ดูประวัติคำสั่งซื้อ</a>',
  confirmButtonColor: '#00d4ff',
  background: '#151d2e',
  color: '#fff',
});

// ยืนยันเติมเงิน
Swal.fire({
  icon: 'question',
  title: 'ยืนยันเติมเงิน 200 บาท?',
  showCancelButton: true,
  confirmButtonText: '✅ ยืนยัน',
  cancelButtonText: '❌ ยกเลิก',
  confirmButtonColor: '#00d4ff',
  cancelButtonColor: '#7b2ff7',
  background: '#151d2e',
  color: '#fff',
}).then((result) => {
  if (result.isConfirmed) {
    // submit slip
  }
});

// Admin - ยืนยันสลิป
Swal.fire({
  icon: 'warning',
  title: 'ยืนยันการเติมเงิน?',
  text: `ผู้ใช้: somchai จำนวน: 200 บาท`,
  showDenyButton: true,
  confirmButtonText: '✅ ยืนยัน',
  denyButtonText: '❌ ปฏิเสธ',
  background: '#151d2e',
  color: '#fff',
});
```

---

## 🔄 API Flow

### 1. สั่งซื้อด้วย Wallet
```
User → POST /member/buy.php
     Body: { package: "1", server_id: "1" }
     → ตรวจสอบ wallet > ราคา
     → สร้าง user ใน x-ui
     → หักเงิน wallet
     → บันทึก order
     → ตอบกลับ config link
     → SweetAlert แสดง Config
```

### 2. เติมเงินผ่านสลิป
```
User → POST /member/topup.php
     Body: { amount: 200 }
     → สร้าง PromptPay QR
     → แสดง QR ให้ user สแกนจ่าย
     → User ส่งสลิปรูป
     → POST /api/check_slip.php
       → SlipOK API verify
       → ถ้าจริง → +wallet → บันทึก topup
       → SweetAlert success
```

### 3. Admin ยืนยันสลิป (Manual)
```
Admin → เห็นรายการ pending ที่ admin/topups.php
     → กด ✅ → POST /admin/api_confirm_topup.php?id=5
     → +wallet ให้ user
     → update status = completed
     → SweetAlert success
```

---

## 📋 ฟังก์ชั่นครบถ้วน

### หน้าบ้าน (User/Public)
- [x] หน้าแรกแสดงแพ็กเกจ + ราคาทั้งหมด
- [x] ดูรายละเอียดเซิร์ฟเวอร์
- [x] สมัครสมาชิก / เข้าสู่ระบบ / ออกจากระบบ
- [x] สั่งซื้อด้วยการโอน (สแกน QR → ส่งสลิป)
- [x] สั่งซื้อด้วย wallet (เงินในระบบ)
- [x] เติมเงิน wallet ผ่านสลิป
- [x] ประวัติคำสั่งซื้อ
- [x] ประวัติการเติมเงิน
- [x] คัดลอก Config
- [x] responsive ทุกขนาดจอ

### หลังบ้าน (Admin)
- [x] Dashboard สรุป
- [x] จัดการผู้ใช้ (เพิ่ม wallet, แบน)
- [x] จัดการออเดอร์
- [x] ยืนยัน/ปฏิเสธ การเติมเงิน
- [x] จัดการเซิร์ฟเวอร์
- [x] ดูประวัติทั้งหมด
- [x] แจ้งเตือนสลิปรอ確認

---

## 🚀 Deploy Instructions
```bash
# 1. สร้าง Database MySQL
mysql -u root -p -e "CREATE DATABASE ekromvpn CHARACTER SET utf8mb4"

# 2. Import table structure
mysql -u root -p ekromvpn < schema.sql

# 3. ติดตั้ง x-ui API
# แก้ไข /includes/xui_client.php ให้ใช้ API ของ x-ui

# 4. Config
cp includes/config.example.php includes/config.php
nano includes/config.php
# → ใส่ DB credentials
# → ใส่ SlipOK API Key
# → ใส่ LINE Channel credentials

# 5. Set permissions
chmod -R 755 uploads/
chmod -R 755 temp/
```

---

🎯 **สรุป:** ระบบนี้พร้อมให้ Agentic Coding (Claude/GPT/Codex) สร้างตาม spec ได้ทันที!

ทุกฟังก์ชั่นที่มีใน LINE Bot + Web App เก่า ถูกย้ายมาเป็น PHP + MySQL + Tailwind CSS + SweetAlert2 ครบถ้วน ปลอดภัย สวยงาม responsive จัดวางเป็นระบบ 🚀
