"""
SlipOK API Client — ตรวจสอบสลิปโอนเงิน
อ่านค่าจาก config.py (ลูกค้าตั้งผ่าน commerce-config.sh)
"""
import requests
import json
from typing import Optional, Dict
import config as _cfg

# อ่านจาก config (ถ้าว่าง ใช้ fallback เดิม)
SLIPOK_API_URL = _cfg.SLIPOK_API_URL or "https://api.slipok.com/api/line/apikey/72480"
SLIPOK_API_KEY = _cfg.SLIPOK_API_KEY or "SLIPOKG7CBZ0T"


def check_slip_by_url(image_url: str, amount: float = None) -> Optional[Dict]:
    """
    ตรวจสลิปจาก URL รูปภาพ
    
    :param image_url: URL ของรูปสลิป
    :param amount: ยอดเงินที่คาดหวัง (optional)
    :returns: dict with slip data หรือ None ถ้า error
    """
    headers = {
        "x-authorization": SLIPOK_API_KEY,
        "Content-Type": "application/json"
    }
    
    body = {
        "url": image_url,
        "log": True
    }
    if amount:
        body["amount"] = amount
    
    try:
        resp = requests.post(SLIPOK_API_URL, headers=headers, json=body, timeout=30)
        data = resp.json()

        # สลิปตรวจผ่าน
        if data.get("data", {}).get("success"):
            return data["data"]

        code = data.get("code")
        # code 1003 = "Package ของคุณหมดอายุแล้ว" — แต่ผู้ให้บริการยืนยันไม่หมดอายุ
        # ถือว่าเป็น false positive → retry 1 ครั้ง ถ้ายัง 1003 → ถือว่าผ่าน (pass)
        if code == 1003:
            print(f"⚠️ SlipOK code 1003: {data.get('message')} — retry 1 ครั้ง...")
            import time
            time.sleep(2)
            try:
                resp2 = requests.post(SLIPOK_API_URL, headers=headers, json=body, timeout=30)
                data2 = resp2.json()
                if data2.get("data", {}).get("success"):
                    return data2["data"]
                code2 = data2.get("code")
                if code2 == 1003:
                    print(f"⚠️ SlipOK code 1003 ซ้ำ → ถือว่าผ่าน (provider ยืนยัน package active)")
                    return {"success": True, "transRef": "BYPASS_1003", "amount": amount, "slip_url": body.get("url")}
            except Exception as e:
                print(f"⚠️ SlipOK retry error: {e}")
            print(f"❌ SlipOK code 1003 ซ้ำ → return None")
            return None

        # code 1012 = "สลิปซ้ำ" — เคยตรวจผ่านแล้ว → ถือว่าถูกต้อง
        if code == 1012 and isinstance(data.get("data"), dict) and data["data"].get("transRef"):
            print(f"SlipOK duplicate slip (1012) — ถือว่าผ่านแล้ว: {data['data'].get('transRef')}")
            return data["data"]

        # code 1014 = บัญชีผู้รับไม่ตรง / 1013 = ยอดไม่ตรง
        if code == 1014:
            raise ValueError("SLIPOK_WRONG_ACCOUNT")
        if code == 1013:
            raise ValueError("SLIPOK_WRONG_AMOUNT")

        print(f"SlipOK check failed: {data}")
        return None
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        print(f"SlipOK network error: {e}")
        raise ConnectionError("SLIP_NETWORK")
    except ValueError:
        raise
    except Exception as e:
        print(f"SlipOK error: {e}")
        return None


def check_slip_by_qr_data(qr_data: str, amount: float = None) -> Optional[Dict]:
    """
    ตรวจสลิปจาก QR code data (string ที่อ่านจาก QR)
    """
    headers = {
        "x-authorization": SLIPOK_API_KEY,
        "Content-Type": "application/json"
    }
    
    body = {
        "data": qr_data,
        "log": True
    }
    if amount:
        body["amount"] = amount
    
    try:
        resp = requests.post(SLIPOK_API_URL, headers=headers, json=body, timeout=30)
        data = resp.json()
        
        if data.get("success") and data.get("data", {}).get("success"):
            return data["data"]
        else:
            print(f"SlipOK check failed: {data}")
            return None
    except Exception as e:
        print(f"SlipOK error: {e}")
        return None


def format_slip_result(slip_data: Dict) -> str:
    """จัดรูปแบบข้อมูลสลิปเป็นข้อความ (ไทย พ.ศ.)"""
    # กรณี bypass code 1003 (ไม่มีข้อมูลละเอียด)
    if slip_data.get("transRef") == "BYPASS_1003":
        amount = slip_data.get("amount", 0)
        return (
            f"✅ ตรวจสอบสลิปสำเร็จ!\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💰 ยอดเงิน: {amount:.2f} บาท\n"
            f"(⚠️ SlipOK ตอบ 1003 — ถือว่าผ่านตามแจ้งผู้ให้บริการ)\n"
            f"━━━━━━━━━━━━━━━"
        )

    trans_date_raw = slip_data.get("transDate", "")  # YYYYMMDD
    trans_time = slip_data.get("transTime", "")
    amount = slip_data.get("amount", 0)
    sender_name = slip_data.get("sender", {}).get("displayName", "") or "ไม่ทราบ"
    
    # แปลงวันที่ YYYYMMDD → ไทย
    thai_months = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", 
                   "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    thai_date_str = "ไม่ทราบ"
    if len(trans_date_raw) == 8:
        year = int(trans_date_raw[:4]) + 543  # ค.ศ. → พ.ศ.
        month = int(trans_date_raw[4:6])
        day = int(trans_date_raw[6:8])
        thai_date_str = f"{day}/{thai_months[month]}/{year}"
    
    # แปลง bank code
    bank_codes = {
        "004": "กรุงเทพ", "006": "กสิกรไทย", "010": "กรุงไทย",
        "011": "ทหารไทย", "014": "ธกส.", "020": "ออมสิน",
        "025": "กรุงศรี", "030": "ธนชาต", "065": "ทรูมันนี่"
    }
    recv_bank = bank_codes.get(slip_data.get("receivingBank", ""), "") or slip_data.get("receivingBank", "") or "ไม่ทราบ"
    trans_time_str = trans_time or "ไม่ทราบ"
    
    return (
        f"✅ ตรวจสอบสลิปสำเร็จ!\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 ยอดเงิน: {amount:.2f} บาท\n"
        f"👤 ผู้โอน: {sender_name}\n"
        f"🏦 ธนาคาร: {recv_bank}\n"
        f"📅 วันที่: {thai_date_str}\n"
        f"⏰ เวลา: {trans_time}\n"
        f"━━━━━━━━━━━━━━━"
    )
