"""
ที่อยู่บัญชีธนาคารสำหรับรับโอนเงิน
อ่านค่าจาก config.py (ลูกค้าตั้งผ่าน commerce-config.sh)
"""
import config as _cfg

BANK_ACCOUNTS = _cfg.BANK_ACCOUNTS or []

# PromptPay ID (ถ้าว่าง อ่านจาก accounts ตัวแรก)
PROMPTPAY_ID = _cfg.PROMPTPAY_ID or (BANK_ACCOUNTS[0].get("promptpay", "") if BANK_ACCOUNTS else "")


def get_promptpay_id():
    return PROMPTPAY_ID


def get_bank_info_display():
    """ส่งข้อมูลบัญชีสั้นๆ สำหรับใส่ในสรุป"""
    acc = BANK_ACCOUNTS[0]
    return (
        f"{acc['bank']}\n"
        f"👤 {acc['name']}\n"
        f"📄 {acc['account']}"
    )


def get_bank_info():
    """ส่งข้อมูลบัญชีให้ลูกค้า"""
    acc = BANK_ACCOUNTS[0]
    return (
        f"💳 ช่องทางชำระเงิน\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🏦 {acc['bank']}\n"
        f"👤 {acc['name']}\n"
        f"📄 เลขบัญชี: {acc['account']}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📸 หลังจากโอนแล้ว ส่งสลิปมาในแชทนี้ได้เลย!"
    )
