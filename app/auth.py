"""Giriş paneli için rol tanımları, form doğrulama ve şifre özeti.

Araştırmacı hesapları MS SQL veri tabanında tutulur (bkz. `app/db/`). Şifre asla düz metin saklanmaz:
PBKDF2-SHA256 (rastgele tuz, 200.000 tur) özeti yazılır. Veri tabanı yoksa site demo girişine düşer;
o durumda bilgiler yalnızca tarayıcı oturumunda (`st.session_state`) kalır.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

ROLES = {
    "vatandas": {
        "ad": "Merak ediyorum",
        "ikon": "🌍",
        "ozet": "Formsuz, tek tıkla",
        "haklar": [
            "İlimde iklim nasıl değişiyor?",
            "Türkiye haritasında sıcaklık, yağış, kar, su",
            "Her sonuç sade bir cümleyle",
        ],
        "sayfalar": ["kesfet", "il", "iliski", "lab", "fizik", "soru", "indir", "yontem"],
    },
    "akademisyen": {
        "ad": "Araştırmacıyım",
        "ikon": "🎓",
        "ozet": "Makale, tez ya da proje için",
        "haklar": [
            "Tüm istatistikler ve tablolar",
            "Seçtiğin veriyi tek tıkla indir (CSV + NetCDF)",
            "Hazır atıf metni (APA / BibTeX)",
        ],
        "sayfalar": ["kesfet", "il", "iliski", "lab", "fizik", "soru", "indir", "makale", "yontem"],
    },
}
PAGES = {
    "kesfet": "Genel bakış",
    "il": "İl profili",
    "iliski": "İlişkiler",
    "lab": "İlişki laboratuvarı",
    "fizik": "Büyüklük testleri",
    "soru": "Soru sor",
    "indir": "Veri indir",
    "makale": "Çalışmalarım",
    "yontem": "Yöntem",
}
ACADEMIC_DOMAINS = (".edu", ".edu.tr", ".ac.uk", ".ac.jp", ".ac.at", ".ac.il", ".ac.nz", ".ac.za", ".ac.kr",
                    ".ac.in", ".edu.au", ".edu.cn", ".gov.tr")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


def is_academic_email(email: str) -> bool:
    """Kurum e-postası mı? (.edu, .edu.tr, .ac.xx vb. ile biten alan adları)."""
    domain = email.strip().lower().rsplit("@", 1)[-1]
    return any(domain.endswith(d) for d in ACADEMIC_DOMAINS)


def validate(role: str, name: str, email: str = "", institution: str = "", orcid: str = "") -> list[str]:
    """Giriş formunu denetler; hata mesajlarının listesini döndürür (boş liste = geçerli)."""
    errors = []
    if role not in ROLES:
        errors.append("Bir rol seçin.")
    if len(name.strip()) < 2:
        errors.append("Adınızı yazın.")
    if role == "akademisyen":
        if not EMAIL_RE.match(email.strip()):
            errors.append("Geçerli bir e-posta adresi yazın.")
        if len(institution.strip()) < 2:
            errors.append("Kurumunuzu yazın.")
        if orcid.strip() and not ORCID_RE.match(orcid.strip()):
            errors.append("ORCID 0000-0000-0000-0000 biçiminde olmalı.")
    return errors


def make_user(role: str, name: str, email: str = "", institution: str = "", orcid: str = "") -> dict:
    """Oturumda tutulacak kullanıcı kaydı (diske yazılmaz)."""
    user = {"rol": role, "ad": name.strip()}
    if role == "akademisyen":
        user.update({"eposta": email.strip(), "kurum": institution.strip(), "orcid": orcid.strip() or None,
                     "kurum_eposta": is_academic_email(email)})
    return user


def pages_for(user: dict | None) -> list[str]:
    """Kullanıcının rolüne göre gezinme sayfaları."""
    return ROLES.get((user or {}).get("rol"), ROLES["vatandas"])["sayfalar"]


def is_academic(user: dict | None) -> bool:
    """Akademisyen rolü mü?"""
    return bool(user) and user.get("rol") == "akademisyen"


# ---------------------------------------------------------------- şifre
PBKDF2_ITER = 200_000
MIN_PASSWORD = 8


def validate_password(pw: str, pw2: str | None = None) -> list[str]:
    """Şifre kuralı: en az 8 karakter, en az bir harf ve bir rakam; tekrar alanı eşleşmeli."""
    errors = []
    if len(pw) < MIN_PASSWORD:
        errors.append(f"Şifre en az {MIN_PASSWORD} karakter olmalı.")
    if not re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", pw) or not re.search(r"\d", pw):
        errors.append("Şifrede en az bir harf ve bir rakam olmalı.")
    if pw2 is not None and pw != pw2:
        errors.append("Şifreler aynı değil.")
    return errors


def hash_password(pw: str, salt: bytes | None = None, iterations: int = PBKDF2_ITER) -> str:
    """Şifrenin saklanacak özeti: 'pbkdf2_sha256$tur$tuz_hex$ozet_hex'."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(pw: str, stored: str | None) -> bool:
    """Girilen şifre saklanan özetle eşleşiyor mu? (zamanlama saldırısına dayanıklı karşılaştırma)."""
    try:
        algo, iterations, salt_hex, digest_hex = (stored or "").split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
    return hmac.compare_digest(digest.hex(), digest_hex)


def validate_signup(role: str, name: str, email: str, pw: str, pw2: str, institution: str = "", orcid: str = "",
                    consent: bool = True) -> list[str]:
    """Yeni üye formu: rol kuralları + e-posta + şifre + aydınlatma onayı."""
    errors = validate(role, name, email, institution, orcid)
    if role == "vatandas" and not EMAIL_RE.match(email.strip()):
        errors.append("Geçerli bir e-posta adresi yazın.")
    errors += validate_password(pw, pw2)
    if not consent:
        errors.append("Devam etmek için aydınlatma metnini onaylayın.")
    return errors
