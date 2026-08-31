"""
PromptPay QR Code Generator — ใช้ library promptpay-qr
"""
import qrcode
import os
from typing import Optional
from promptpay_qr import generate_payload

QR_DIR = "/root/hermes-commerce/configs"


def generate_promptpay_payload(promptpay_id: str, amount: float) -> str:
    """
    สร้าง payload สำหรับ PromptPay QR
    ใช้ library promptpay-qr ที่ผ่านการทดสอบแล้ว
    
    รองรับ:
    - เบอร์โทร 10 หลัก (0812345678)
    - เบอร์ +66 (66812345678)
    - เลขบัตรประชาชน 13 หลัก
    """
    return generate_payload(promptpay_id, amount)


def generate_promptpay_qr(promptpay_id: str, amount: float, filename: str) -> Optional[str]:
    """สร้าง QR Code รูปภาพสำหรับ PromptPay"""
    payload = generate_payload(promptpay_id, amount)
    
    os.makedirs(QR_DIR, exist_ok=True)
    filepath = os.path.join(QR_DIR, filename)
    
    qr = qrcode.QRCode(
        version=10,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(filepath)
    return filepath
