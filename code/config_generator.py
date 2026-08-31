"""
VMESS/VLESS Config Generator — สร้าง share link + QR code
"""
import json
import base64
import qrcode
from io import BytesIO
import os
from typing import Optional
import config

CONFIG_DIR = "/root/hermes-commerce/configs"


def generate_vmess_link(client_id: str, email: str, inbound_id: int = 1,
                          remark_prefix: str = "EkromNet", expiry_str: str = "",
                          remark_name: str = None) -> str:
    """Create vmess/vless link with remark: PREFIX-NAME-PHONE-EXPIRY
    remark_name = ชื่อที่โชว์ในคอนฟิก (ถ้าไม่ส่ง ใช้ email)"""
    inbound_id = int(inbound_id)
    ps_name = f"{remark_prefix}-{remark_name if remark_name else email}"
    if expiry_str:
        ps_name += f"-{expiry_str}"
    
    if inbound_id == 3:
        # TRUE-ROV - VMESS+WS port 8080 via truegame.idavpn.win
        vmess_config = {
            "v": "2", "ps": ps_name,
            "add": "truegame.idavpn.win", "port": 8080,
            "id": client_id, "aid": 0, "scy": "auto",
            "net": "ws", "type": "none", "host": "vip2.idavpn.win",
            "path": "/", "tls": "", "sni": "", "alpn": "", "fp": ""
        }
    elif inbound_id == 2:
        # TRUE-NOPRO -> VLESS+WS port 80
        return generate_vless_link(client_id, email, inbound_id,
                                    remark_prefix=remark_prefix, expiry_str=expiry_str)
    elif inbound_id == 1:
        # AIS-PLAY - VLESS+WS port 80 via aisplay.ais.co.th
        return generate_vless_link(client_id, email, inbound_id,
                                    remark_prefix=remark_prefix, expiry_str=expiry_str)
    elif inbound_id == 5:
        # TRUE-ZOOM - VMESS+WS port 8080 via truegame.idavpn.win
        vmess_config = {
            "v": "2", "ps": ps_name,
            "add": "truegame.idavpn.win", "port": 8080,
            "id": client_id, "aid": 0, "scy": "auto",
            "net": "ws", "type": "none", "host": "vip2.idavpn.win",
            "path": "/", "tls": "", "sni": "", "alpn": "", "fp": ""
        }
    else:
        # Use port 80 - VLESS+WS
        return generate_vless_link(client_id, email, inbound_id,
                                    remark_prefix=remark_prefix, expiry_str=expiry_str)
    
    json_str = json.dumps(vmess_config, ensure_ascii=False)
    b64 = base64.b64encode(json_str.encode()).decode()
    return f"vmess://{b64}"


def generate_vless_link(client_id: str, email: str, inbound_id: int = 4,
                           remark_prefix: str = "EkromNet", expiry_str: str = "") -> str:
    """Create vless:// link - port 80 VLESS+WS"""
    import urllib.parse
    ps_name = f"{remark_prefix}-{email}"
    if expiry_str:
        ps_name += f"-{expiry_str}"
    
    if int(inbound_id) == 4:
        # TRUE-FB-GAMING - VLESS+TCP+TLS port 443 via fbcdn.idavpn.win
        import urllib.parse
        params = {
            "type": "tcp",
            "encryption": "none",
            "security": "tls",
            "fp": "chrome",
            "alpn": "",
            "sni": "fbcdn.idavpn.win"
        }
        query = urllib.parse.urlencode(params)
        return f"vless://{client_id}@vip2.idavpn.win:443/?{query}#{urllib.parse.quote(ps_name)}"
    
    if int(inbound_id) == 1:
        # AIS-PLAY via aisplay.ais.co.th
        add_host = "d2w9iashl5za4g.cloudfront.net"
        dest_addr = "aisplay.ais.co.th"
    elif int(inbound_id) == 2:
        # TRUE-NOPRO via assets.opensignal.com
        add_host = "d2w9iashl5za4g.cloudfront.net:assets.opensignal.com"
        dest_addr = "assets.opensignal.com"
    elif int(inbound_id) == 6:
        # DTAC-NOPRO via www.true.th
        add_host = "d2w9iashl5za4g.cloudfront.net"
        dest_addr = "www.true.th"
    else:
        add_host = "d2w9iashl5za4g.cloudfront.net"
        dest_addr = "vip2.idavpn.win"
    
    params = {
        "path": "/", "encryption": "none",
        "host": add_host,
        "type": "ws",
    }
    query = urllib.parse.urlencode(params)
    return f"vless://{client_id}@{dest_addr}:80?{query}#{urllib.parse.quote(ps_name)}"


def generate_qr_code(data: str, filename: str) -> Optional[str]:
    """สร้าง QR Code image จาก vmess link"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    filepath = os.path.join(CONFIG_DIR, filename)
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(filepath)
    return filepath


def generate_subscription_url(sub_id: str) -> str:
    """สร้าง subscription URL"""
    return f"https://{config.SERVER_DOMAIN}:{config.SERVER_PORT}/sub/{sub_id}"
