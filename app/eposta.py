"""Şifre sıfırlama kodunu e-postayla gönderir (isteğe bağlı SMTP).

Sunucu bilgileri koda yazılmaz; ortam değişkenlerinden okunur:
    TD_SMTP_HOST, TD_SMTP_PORT (varsayılan 587), TD_SMTP_USER, TD_SMTP_PASS, TD_SMTP_FROM
Bu değişkenler yoksa `configured()` False döner ve arayüz demo kipine geçer (kod ekranda gösterilir,
bunun bir demo olduğu açıkça yazılır).
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def configured() -> bool:
    """SMTP ayarları ortam değişkenlerinde var mı?"""
    return bool(os.environ.get("TD_SMTP_HOST") and os.environ.get("TD_SMTP_FROM"))


def reset_message(to: str, name: str, code: str, minutes: int) -> EmailMessage:
    """Şifre sıfırlama e-postası."""
    msg = EmailMessage()
    msg["Subject"] = "Trend Dedektifi · şifre sıfırlama kodu"
    msg["From"] = os.environ.get("TD_SMTP_FROM", "")
    msg["To"] = to
    msg.set_content(
        f"Merhaba {name},\n\nŞifre sıfırlama kodun: {code}\n\nKod {minutes} dakika geçerlidir ve tek kullanımlıktır. "
        "Bu isteği sen yapmadıysan bu e-postayı yok sayabilirsin.\n\nTrend Dedektifi")
    return msg


def send_reset_code(to: str, name: str, code: str, minutes: int) -> None:
    """Kodu SMTP ile gönderir (STARTTLS). Ayar yoksa RuntimeError verir."""
    if not configured():
        raise RuntimeError("SMTP ayarlı değil")
    host, port = os.environ["TD_SMTP_HOST"], int(os.environ.get("TD_SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=10) as s:
        s.starttls()
        if os.environ.get("TD_SMTP_USER"):
            s.login(os.environ["TD_SMTP_USER"], os.environ.get("TD_SMTP_PASS", ""))
        s.send_message(reset_message(to, name, code, minutes))
