"""Veri tabanını kurar, trend tablolarını yükler ve örnek araştırmacı/makale kayıtlarını ekler.

    python app/db/kur.py                    # veri tabanı + şema + tablolar (boşsa) + örnek kayıtlar
    python app/db/kur.py --tablolari-yenile # gerçek CSV'ler gelince trend tablolarını baştan yükle
    python app/db/kur.py --ornekleri-sil    # örnek kişileri ve makalelerini kaldır

Bağlantı Windows kimliğiyle yapılır (şifre yok); başka sunucu için TD_MSSQL_SERVER / TD_MSSQL_CONN.
Örnek hesapların şifresi TD_DEMO_SIFRE ortam değişkeninden alınır; yoksa rastgele üretilip yalnızca
ekrana bir kez yazılır (hiçbir dosyaya kaydedilmez). Örnek kişiler ve makaleler KURGUSALDIR.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
for p in (str(APP_DIR), str(APP_DIR.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

import urun_io as U  # noqa: E402
import veritabani as DB  # noqa: E402

SCHEMA = Path(__file__).with_name("sema.sql")

# KURGUSAL örnek araştırmacılar (gerçek kişi ya da kurum değildir).
EXAMPLE_USERS = [
    ("Dr. Elif Kaya", "Örnek Üniversitesi · Coğrafya Bölümü", "elif.kaya@ornek.edu.tr", "0000-0000-0000-0001"),
    ("Doç. Dr. Murat Demir", "Örnek Teknik Üniversitesi · Meteoroloji", "murat.demir@ornek.edu.tr", None),
    ("Arş. Gör. Zeynep Aydın", "Örnek Üniversitesi · Ziraat Fakültesi", "zeynep.aydin@ornek.edu.tr", None),
    ("Dr. Can Yıldız", "Örnek Su Araştırmaları Enstitüsü", "can.yildiz@ornek.edu.tr", "0000-0000-0000-0002"),
]
# KURGUSAL örnek vatandaşlar (kurum ve ORCID yok).
EXAMPLE_CITIZENS = [
    ("Ayşe Yılmaz", "ayse.yilmaz@ornek.com"),
    ("Mehmet Öztürk", "mehmet.ozturk@ornek.com"),
]
# KURGUSAL örnek makaleler: (ekleyen e-posta, alanlar). DOI bilerek boş bırakıldı.
EXAMPLE_ARTICLES = [
    ("elif.kaya@ornek.edu.tr", {
        "baslik": "Doğu Anadolu'da kış kar örtüsünün 2001–2025 değişimi (örnek kayıt)",
        "yazarlar": "Kaya, E.; Aydın, Z.", "dergi": "Örnek İklim Araştırmaları Dergisi", "yil": 2026,
        "ozet": "Trend Dedektifi v0.1 kar örtüsü ve kış sıcaklığı tablolarını kullanan kurgusal bir örnek çalışma.",
        "degiskenler": "kar_ortusu,sicaklik_2m", "iller": "Erzurum,Kars,Ardahan,Ağrı", "durum": "yayimlandi"}),
    ("murat.demir@ornek.edu.tr", {
        "baslik": "Türkiye'de yağışın üç NASA ürününde tutarlılığı (örnek kayıt)",
        "yazarlar": "Demir, M.", "dergi": "Örnek Meteoroloji Dergisi", "yil": 2026,
        "ozet": "GPM IMERG, GLDAS ve MERRA-2 yağış trendlerinin kaynak uyumu sütunuyla karşılaştırılması (kurgusal).",
        "degiskenler": "yagis", "iller": "", "durum": "degerlendirmede"}),
    ("zeynep.aydin@ornek.edu.tr", {
        "baslik": "Konya Kapalı Havzası'nda toprak nemi ile bitki örtüsü ilişkisi (örnek kayıt)",
        "yazarlar": "Aydın, Z.; Kaya, E.", "dergi": "Örnek Tarım Bilimleri Dergisi", "yil": 2026,
        "ozet": "Fizik kontrolünde 'ters yönde' çıkan illerde sulamanın olası etkisi üzerine kurgusal bir tez bölümü.",
        "degiskenler": "toprak_nemi,ndvi", "iller": "Konya,Aksaray,Karaman", "durum": "hazirlaniyor"}),
    ("can.yildiz@ornek.edu.tr", {
        "baslik": "GRACE ile İç Anadolu'da toplam su depolamasındaki azalma (örnek kayıt)",
        "yazarlar": "Yıldız, C.", "dergi": "Örnek Su Kaynakları Dergisi", "yil": 2025,
        "ozet": "Toplam su depolama trendinin yağış ilişkisiyle birlikte yorumlandığı kurgusal örnek.",
        "degiskenler": "toplam_su_depolama,yagis", "iller": "Konya,Ankara", "durum": "yayimlandi"}),
]


def run_schema() -> None:
    """Veri tabanını (yoksa) oluşturur ve sema.sql bloklarını çalıştırır."""
    with DB.connect(database="master", autocommit=True) as cn:
        cn.cursor().execute(f"IF DB_ID(N'{DB.DB_NAME}') IS NULL CREATE DATABASE [{DB.DB_NAME}]")
    blocks = [b.strip() for b in SCHEMA.read_text(encoding="utf-8").split("\nGO") if b.strip()]
    with DB.connect() as cn:
        cur = cn.cursor()
        for b in blocks:
            sql = "\n".join(line for line in b.splitlines() if not line.strip().startswith("--")).strip()
            if sql:
                cur.execute(sql)
    print(f"Şema hazır: {DB.SERVER} / {DB.DB_NAME}")


def table_count(table: str) -> int:
    """Bir tablodaki satır sayısı."""
    with DB.connect() as cn:
        return cn.cursor().execute(f"SELECT COUNT(*) FROM dbo.{table}").fetchone()[0]  # noqa: S608


def load_trend_tables(force: bool) -> None:
    """Trend tablolarını dosyalardan (yoksa sentetik yer tutucudan) veri tabanına yükler."""
    if not force and table_count("trend_iller"):
        print("Trend tabloları zaten dolu (yenilemek için --tablolari-yenile).")
        return
    tables = U.load_tables()
    counts = DB.replace_tables(tables)
    kind = "SENTETİK YER TUTUCU" if tables["yer_tutucu"] else "gerçek dosyalar"
    print(f"Trend tabloları yüklendi ({kind}): " + ", ".join(f"{k} {v}" for k, v in counts.items()))


def seed_examples() -> None:
    """Kurgusal örnek araştırmacıları ve makalelerini ekler (zaten varsa atlar)."""
    password = os.environ.get("TD_DEMO_SIFRE")
    generated = False
    if not password:
        password = secrets.token_urlsafe(8) + "7a"
        generated = True
    ids, added = {}, 0
    for name, inst, email, orcid in EXAMPLE_USERS:
        try:
            ids[email] = DB.register(name, email, inst, orcid or "", password, example=True)["id"]
            added += 1
        except ValueError:
            with DB.connect() as cn:
                ids[email] = cn.cursor().execute("SELECT id FROM dbo.kullanicilar WHERE eposta = ?", email).fetchone()[0]
    citizens = 0
    for name, email in EXAMPLE_CITIZENS:
        try:
            DB.register(name, email, "", "", password, example=True, role="vatandas")
            citizens += 1
        except ValueError:  # zaten kayıtlı
            pass
    added += citizens
    with DB.connect() as cn:
        have = {r[0] for r in cn.cursor().execute("SELECT baslik FROM dbo.makaleler WHERE ornek = 1").fetchall()}
    n_art = 0
    for email, art in EXAMPLE_ARTICLES:
        if art["baslik"] not in have:
            DB.add_article(ids[email], art, example=True)
            n_art += 1
    print(f"Örnek kayıtlar: {added - citizens} yeni araştırmacı, {citizens} yeni vatandaş, {n_art} yeni makale "
          "(hepsi kurgusal, ornek = 1).")
    if added and generated:
        print("\nÖrnek hesapların ortak şifresi (yalnızca şimdi gösterilir, hiçbir yere kaydedilmedi):")
        print(f"    {password}")
        print("Kalıcı bir demo şifresi istersen kurmadan önce TD_DEMO_SIFRE ortam değişkenini ayarla.")


def delete_examples() -> None:
    """Örnek kişileri ve (kaskadla) makalelerini siler."""
    with DB.connect() as cn:
        n = cn.cursor().execute("DELETE FROM dbo.kullanicilar WHERE ornek = 1").rowcount
    print(f"{n} örnek kullanıcı ve makaleleri silindi.")


def main() -> None:
    """Komut satırı girişi."""
    ap = argparse.ArgumentParser(description="Trend Dedektifi MS SQL kurulumu")
    ap.add_argument("--tablolari-yenile", action="store_true", help="trend tablolarını baştan yükle")
    ap.add_argument("--ornekleri-sil", action="store_true", help="örnek kişi ve makaleleri sil")
    ap.add_argument("--ornek-yok", action="store_true", help="örnek kayıt ekleme")
    args = ap.parse_args()
    run_schema()
    if args.ornekleri_sil:
        delete_examples()
        return
    load_trend_tables(args.tablolari_yenile)
    if not args.ornek_yok:
        seed_examples()
    print("Özet:", DB.stats())


if __name__ == "__main__":
    main()
