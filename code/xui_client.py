"""
x-ui API Client — จัดการผู้ใช้ใน x-ui panel
รองรับทั้ง API login และแก้ DB โดยตรง
"""
import requests
import json
import uuid
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import config

class XUIClient:
    """Client สำหรับเชื่อมต่อ x-ui panel ผ่าน API"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False
        self.base_url = config.XUI_BASE_URL
        self.base_path = "/panel/api"
        self.logged_in = False
        # 3X-UI v3.2.6 ใช้ Bearer token API (ไม่ใช่ login user/pass)
        self.token = getattr(config, "XUI_API_TOKEN", "")
    
    def login(self) -> bool:
        """3X-UI v3.2.6: ไม่ต้อง login — ใช้ Bearer token ใน header ทุก request"""
        try:
            if self.token:
                self.session.headers["Authorization"] = f"Bearer {self.token}"
                self.logged_in = True
                return True
            # fallback: login user/pass แบบเก่า (ถ้าไม่มี token)
            url = f"{self.base_url}/login"
            resp = self.session.post(url, data={
                "username": config.XUI_USERNAME,
                "password": config.XUI_PASSWORD,
            }, timeout=15)
            data = resp.json()
            if data.get("success"):
                self.logged_in = True
                return True
            else:
                print(f"x-ui login failed: {data.get('msg')}")
                return False
        except Exception as e:
            print(f"x-ui login error: {e}")
            return False
    
    def add_client(self, inbound_id: int, email: str, 
                   limit_ip: int = 2, total_gb: int = 0,
                   expiry_time: int = 0, enable: bool = True) -> Optional[Dict]:
        """
        เพิ่ม client ใน inbound
        returns: dict {client_id, uuid} หรือ None ถ้า fail
        """
        # Always try to login first / set bearer token
        self.login()
        
        client_id = str(uuid.uuid4())
        sub_id = self._generate_sub_id()
        
        # 3X-UI v3.2.6: POST /panel/api/clients/add with {client, inboundIds:[..]}
        client_obj = {
            "id": client_id,
            "flow": "",
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_gb,
            "expiryTime": expiry_time,
            "enable": enable,
            "tgId": 0,
            "subId": sub_id,
        }
        
        url = f"{self.base_url}{self.base_path}/clients/add"
        try:
            resp = self.session.post(url, json={
                "client": client_obj,
                "inboundIds": [inbound_id],
            }, timeout=20)
            data = resp.json()
            if data.get("success"):
                return {
                    "client_id": client_id,
                    "email": email,
                    "sub_id": sub_id,
                    "inbound_id": inbound_id,
                }
            else:
                print(f"clients/add failed: {data.get('msg')}")
                return None
        except Exception as e:
            print(f"clients/add error: {e}")
            return None
    
    def get_inbounds(self) -> list:
        """ดึงรายการ inbounds ทั้งหมด"""
        if not self.logged_in:
            if not self.login():
                return []
        url = f"{self.base_url}{self.base_path}/inbounds/list"
        try:
            resp = self.session.get(url, timeout=15)
            data = resp.json()
            if data.get("success"):
                return data.get("obj", [])
            return []
        except Exception as e:
            print(f"get_inbounds error: {e}")
            return []
    

    def get_inbound_by_id(self, inbound_id: int) -> Optional[Dict]:
        """ดึงข้อมูล inbound พร้อม settings"""
        self.login()
        url = f"{self.base_url}{self.base_path}/inbounds/get/{inbound_id}"
        try:
            resp = self.session.get(url, timeout=15)
            data = resp.json()
            if data.get("success") and data.get("obj"):
                return data["obj"]
            return None
        except Exception as e:
            print(f"get_inbound error: {e}")
            return None


    def find_client_by_email(self, email: str) -> Optional[Dict]:
        """ค้นหา client ที่มี email ตรงเป๊ะ (ใช้ตรวจชื่อซ้ำ)"""
        self.login()
        for inbound in self.get_inbounds():
            try:
                settings = json.loads(inbound["settings"]) if isinstance(inbound["settings"], str) else inbound["settings"]
            except Exception:
                continue
            for c in settings.get("clients", []):
                if c.get("email", "").strip() == email.strip():
                    return {
                        "inbound_id": inbound["id"],
                        "client_id": c.get("id"),
                        "email": c.get("email"),
                        "expiry_ms": c.get("expiryTime", 0),
                    }
        return None

    def get_clients_by_keyword(self, keyword: str) -> list:
        """ค้นหา client ทั้งหมดที่มีเบอร์โทร หรือ ชื่อ ใน email/remark
        (รองรับกรณีลูกค้าข้ามเบอร์ตอนสมัคร — ค้นด้วยชื่อได้)"""
        self.login()
        results = []
        inbounds = self.get_inbounds()
        kw = keyword.strip().lower()
        for inbound in inbounds:
            try:
                settings = json.loads(inbound["settings"]) if isinstance(inbound["settings"], str) else inbound["settings"]
            except Exception:
                continue
            for c in settings.get("clients", []):
                email = c.get("email", "")
                remark = c.get("remark", "")
                haystack = f"{email} {remark}".lower()
                if kw and kw in haystack:
                    results.append({
                        "inbound_id": inbound["id"],
                        "client_id": c.get("id"),
                        "email": email,
                        "expiry_ms": c.get("expiryTime", 0),
                        "enable": c.get("enable", True),
                    })
        return results

    def get_clients_by_phone(self, phone: str) -> list:
        """ค้นหา client ด้วยเบอร์โทร (ชื่อเดิม — เรียกใช้ get_clients_by_keyword)"""
        return self.get_clients_by_keyword(phone)

    def update_client_expiry(self, inbound_id: int, client_uuid: str,
                             new_expiry_ms: int) -> Optional[Dict]:
        """ต่ออายุ client — ขยาย expiryTime (3x-ui updateClient API)

        วิธีที่ถูกต้อง:
        - ส่งทั้ง Inbound object (เหมือน GET /get/:id)
        - client ที่จะแก้ต้องอยู่ตัวแรกใน settings.clients
        - email ห้ามเปลี่ยน (ข้ามตรวจ email ซ้ำ)
        """
        self.login()
        inbound = self.get_inbound_by_id(inbound_id)
        if not inbound:
            print(f"update_client_expiry: inbound {inbound_id} not found")
            return None
        try:
            settings = json.loads(inbound["settings"]) if isinstance(inbound["settings"], str) else inbound["settings"]
        except Exception as e:
            print(f"update_client_expiry: settings parse error: {e}")
            return None

        clients = settings.get("clients", [])
        target = next((c for c in clients if c.get("id") == client_uuid), None)
        if not target:
            print(f"update_client_expiry: client {client_uuid} not found")
            return None

        # แก้ค่า expiry + enable
        target["expiryTime"] = new_expiry_ms
        target["enable"] = True

        # เอาตัวที่จะแก้ไว้ตัวแรก (3x-ui ใช้ clients[0] แทนที่)
        others = [c for c in clients if c.get("id") != client_uuid]
        settings["clients"] = [target] + others

        # 3X-UI v3.2.6: /clients/update/{email} + ส่ง client object ที่แก้ expiry ใหม่
        client_id = target.get("id", client_uuid)
        email_p = target.get("email", "")
        if not email_p:
            print("update_client_expiry: client has no email")
            return None
        client_payload = dict(target)
        client_payload["expiryTime"] = new_expiry_ms
        client_payload["enable"] = True
        url = f"{self.base_url}{self.base_path}/clients/update/{email_p}"
        try:
            resp = self.session.post(url, json={"client": client_payload, "inboundIds": [inbound_id]}, timeout=20)
            data = resp.json()
            if data.get("success"):
                return {"client_id": client_id, "email": email_p}
            print(f"clients/update failed: {data.get('msg')}")
            return None
        except Exception as e:
            print(f"clients/update error: {e}")
            return None

    def _generate_sub_id(self) -> str:
        """สร้าง subscription ID สั้นๆ"""
        import string, random
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choices(chars, k=16))


class XUIDBClient:
    """Client สำหรับจัดการ x-ui โดยแก้ SQLite DB โดยตรง
       (ไม่ต้องพึ่ง API — ใช้ได้ตลอดแม้เปลี่ยนรหัสผ่าน)"""
    
    DB_PATH = "/etc/x-ui/x-ui.db"
    
    def __init__(self):
        self.conn: Optional[sqlite3.Connection] = None
    
    def _connect(self):
        if self.conn is None:
            self.conn = sqlite3.connect(self.DB_PATH)
            self.conn.row_factory = sqlite3.Row
    
    def add_client(self, inbound_id: int, email: str,
                   limit_ip: int = 2, total_gb: int = 0,
                   expiry_time: int = 0, enable: bool = True) -> Optional[Dict]:
        """
        เพิ่ม client โดยแก้ settings JSON ใน DB โดยตรง
        ต้อง restart x-ui หลังเพิ่มเสร็จ
        """
        self._connect()
        
        # ดึง inbound data
        row = self.conn.execute(
            "SELECT id, settings FROM inbounds WHERE id = ?", 
            (inbound_id,)
        ).fetchone()
        
        if not row:
            print(f"Inbound ID {inbound_id} not found")
            return None
        
        settings = json.loads(row["settings"])
        clients = settings.get("clients", [])
        
        # สร้าง client ใหม่
        client_id = str(uuid.uuid4())
        sub_id = self._generate_sub_id()
        now = int(time.time() * 1000)  # x-ui ใช้ millisecond timestamp
        
        new_client = {
            "id": client_id,
            "flow": "",
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_gb,
            "expiryTime": expiry_time if expiry_time > 0 else 0,
            "enable": enable,
            "tgId": "",
            "subId": sub_id,
            "comment": "",
        }
        
        # ถ้ามีฟิลด์อื่นๆ ใน client ตัวแรก ให้ copy มา
        if clients:
            template = clients[0]
            for k in template:
                if k not in new_client:
                    new_client[k] = template[k]
        
        clients.append(new_client)
        settings["clients"] = clients
        
        # อัปเดต DB
        self.conn.execute(
            "UPDATE inbounds SET settings = ? WHERE id = ?",
            (json.dumps(settings), inbound_id)
        )
        self.conn.commit()
        
        print(f"✅ Added client {email} → inbound {inbound_id} (DB)")
        
        return {
            "client_id": client_id,
            "email": email,
            "sub_id": sub_id,
            "inbound_id": inbound_id,
        }
    
    def restart_xui(self) -> bool:
        """รีสตาร์ท x-ui เพื่อให้ config ใหม่生效"""
        import subprocess
        try:
            result = subprocess.run(
                ["x-ui", "restart"], 
                capture_output=True, text=True, timeout=10
            )
            print(f"x-ui restart: {result.stdout.strip()}")
            return result.returncode == 0
        except Exception as e:
            print(f"x-ui restart error: {e}")
            return False
    

    def get_inbound_by_id(self, inbound_id: int) -> Optional[Dict]:
        """ดึงข้อมูล inbound พร้อม settings"""
        self.login()
        url = f"{self.base_url}{self.base_path}/inbounds/get/{inbound_id}"
        try:
            resp = self.session.get(url, timeout=15)
            data = resp.json()
            if data.get("success") and data.get("obj"):
                return data["obj"]
            return None
        except Exception as e:
            print(f"get_inbound error: {e}")
            return None


    def find_client_by_email(self, email: str) -> Optional[Dict]:
        """ค้นหา client ที่มี email ตรงเป๊ะ (ใช้ตรวจชื่อซ้ำ)"""
        self.login()
        for inbound in self.get_inbounds():
            try:
                settings = json.loads(inbound["settings"]) if isinstance(inbound["settings"], str) else inbound["settings"]
            except Exception:
                continue
            for c in settings.get("clients", []):
                if c.get("email", "").strip() == email.strip():
                    return {
                        "inbound_id": inbound["id"],
                        "client_id": c.get("id"),
                        "email": c.get("email"),
                        "expiry_ms": c.get("expiryTime", 0),
                    }
        return None

    def get_clients_by_keyword(self, keyword: str) -> list:
        """ค้นหา client ทั้งหมดที่มีเบอร์โทร หรือ ชื่อ ใน email/remark
        (รองรับกรณีลูกค้าข้ามเบอร์ตอนสมัคร — ค้นด้วยชื่อได้)"""
        self.login()
        results = []
        inbounds = self.get_inbounds()
        kw = keyword.strip().lower()
        for inbound in inbounds:
            try:
                settings = json.loads(inbound["settings"]) if isinstance(inbound["settings"], str) else inbound["settings"]
            except Exception:
                continue
            for c in settings.get("clients", []):
                email = c.get("email", "")
                remark = c.get("remark", "")
                haystack = f"{email} {remark}".lower()
                if kw and kw in haystack:
                    results.append({
                        "inbound_id": inbound["id"],
                        "client_id": c.get("id"),
                        "email": email,
                        "expiry_ms": c.get("expiryTime", 0),
                        "enable": c.get("enable", True),
                    })
        return results

    def get_clients_by_phone(self, phone: str) -> list:
        """ค้นหา client ด้วยเบอร์โทร (ชื่อเดิม — เรียกใช้ get_clients_by_keyword)"""
        return self.get_clients_by_keyword(phone)

    def update_client_expiry(self, inbound_id: int, client_uuid: str,
                             new_expiry_ms: int) -> Optional[Dict]:
        """ต่ออายุ client — ขยาย expiryTime (3x-ui updateClient API)

        วิธีที่ถูกต้อง:
        - ส่งทั้ง Inbound object (เหมือน GET /get/:id)
        - client ที่จะแก้ต้องอยู่ตัวแรกใน settings.clients
        - email ห้ามเปลี่ยน (ข้ามตรวจ email ซ้ำ)
        """
        self.login()
        inbound = self.get_inbound_by_id(inbound_id)
        if not inbound:
            print(f"update_client_expiry: inbound {inbound_id} not found")
            return None
        try:
            settings = json.loads(inbound["settings"]) if isinstance(inbound["settings"], str) else inbound["settings"]
        except Exception as e:
            print(f"update_client_expiry: settings parse error: {e}")
            return None

        clients = settings.get("clients", [])
        target = next((c for c in clients if c.get("id") == client_uuid), None)
        if not target:
            print(f"update_client_expiry: client {client_uuid} not found")
            return None

        # แก้ค่า expiry + enable
        target["expiryTime"] = new_expiry_ms
        target["enable"] = True

        # เอาตัวที่จะแก้ไว้ตัวแรก (3x-ui ใช้ clients[0] แทนที่)
        others = [c for c in clients if c.get("id") != client_uuid]
        settings["clients"] = [target] + others

        # 3X-UI v3.2.6: /clients/update/{email} + ส่ง client object ที่แก้ expiry ใหม่
        client_id = target.get("id", client_uuid)
        email_p = target.get("email", "")
        if not email_p:
            print("update_client_expiry: client has no email")
            return None
        client_payload = dict(target)
        client_payload["expiryTime"] = new_expiry_ms
        client_payload["enable"] = True
        url = f"{self.base_url}{self.base_path}/clients/update/{email_p}"
        try:
            resp = self.session.post(url, json={"client": client_payload, "inboundIds": [inbound_id]}, timeout=20)
            data = resp.json()
            if data.get("success"):
                return {"client_id": client_id, "email": email_p}
            print(f"clients/update failed: {data.get('msg')}")
            return None
        except Exception as e:
            print(f"clients/update error: {e}")
            return None

    def _generate_sub_id(self) -> str:
        import string, random
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choices(chars, k=16))
    
    def get_inbounds_meta(self) -> list:
        """ดึงข้อมูล inbounds แบบสั้นๆ"""
        self._connect()
        rows = self.conn.execute(
            "SELECT id, remark, port, protocol FROM inbounds WHERE enable = 1"
        ).fetchall()
        return [dict(r) for r in rows]
    
    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
