"""MS SQL Server veri tabanı katmanı: kullanıcılar, makaleler, indirme kaydı ve trend tabloları.

Bağlantı: `TD_MSSQL_CONN` ortam değişkeni (tam ODBC bağlantı metni) ya da varsayılan olarak bu
bilgisayardaki SQL Server'a Windows kimliğiyle (şifresiz, Trusted_Connection). Koda ya da repoya
şifre yazılmaz. Sunucu/veri tabanı adı `TD_MSSQL_SERVER` / `TD_MSSQL_DB` ile değiştirilebilir.

Kurulum ve örnek veriler: `python app/db/kur.py`.
"""

from __future__ import annotations

import json
import os
import secrets
import warnings
from contextlib import contextmanager

import pandas as pd

import auth
import urun_io as U

DB_NAME = os.environ.get("TD_MSSQL_DB", "TrendDedektifi")
SERVER = os.environ.get("TD_MSSQL_SERVER", "localhost")
DRIVER = os.environ.get("TD_MSSQL_DRIVER", "ODBC Driver 18 for SQL Server")
TABLES = {"il": ("trend_iller", U.TREND_COLS + U.EXTRA_COLS), "bolge": ("trend_bolgeler", None),
          "iliski": ("ciftler", U.CIFTLER_COLS)}
# pandas, pyodbc bağlantısını SQLAlchemy olmadığı için uyarıyla kabul ediyor; okuma doğru çalışır.
warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")
BOLGE_COLS = ["bolge"] + [c for c in U.TREND_COLS if c not in ("il", "plaka", "bolge")] + U.EXTRA_COLS


def conn_str(database: str | None = "") -> str:
    """ODBC bağlantı metni (ortam değişkeni varsa o kullanılır). `database=""` → DB_NAME, None → yok."""
    env = os.environ.get("TD_MSSQL_CONN")
    if env:
        return env
    database = DB_NAME if database == "" else database
    db = f"Database={database};" if database else ""
    # Yalnızca yerel sunucu için sertifika doğrulaması atlanır (SQL Server'ın kendi imzalı sertifikası).
    return f"Driver={{{DRIVER}}};Server={SERVER};{db}Trusted_Connection=yes;TrustServerCertificate=yes;"


@contextmanager
def connect(database: str | None = "", autocommit: bool = False):
    """Bağlantı bağlam yöneticisi; hata olursa geri alır, sonunda kapatır."""
    import pyodbc  # isteğe bağlı bağımlılık: yoksa available() False döner

    cn = pyodbc.connect(conn_str(database), autocommit=autocommit, timeout=3)
    try:
        yield cn
        if not autocommit:
            cn.commit()
    except Exception:
        if not autocommit:
            cn.rollback()
        raise
    finally:
        cn.close()


def available() -> bool:
    """Veri tabanına bağlanılabiliyor ve şema kurulu mu?"""
    try:
        with connect() as cn:
            return cn.cursor().execute("SELECT OBJECT_ID('dbo.kullanicilar')").fetchone()[0] is not None
    except Exception:  # noqa: BLE001
        return False


def _rows(cur) -> list[dict]:
    """İmleçteki sonuçları sözlük listesine çevirir."""
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# ---------------------------------------------------------------- trend tabloları
def load_tables() -> dict | None:
    """Trend ve ilişki tablolarını veri tabanından okur (urun_io.load_tables ile aynı biçim).

    Tablolar boşsa None döner; çağıran taraf dosyalara düşer.
    """
    out, placeholder = {}, False
    with connect() as cn:
        for key, (table, cols) in TABLES.items():
            df = pd.read_sql(f"SELECT * FROM dbo.{table}", cn)  # noqa: S608 (tablo adı sabit listeden)
            if df.empty:
                return None
            placeholder |= bool(df["yer_tutucu"].astype(bool).any())
            cols = cols or BOLGE_COLS
            df = df[[c for c in cols if c in df.columns]].copy()  # eski şemada ek sütunlar olmayabilir
            for c in ("belirsiz", "anlamli_fdr"):
                if c in df:
                    df[c] = df[c].astype("Int64").fillna(0).astype(int)
            if "kaynak_uyumu" in df:
                df["kaynak_uyumu"] = df["kaynak_uyumu"].fillna("")
            if key == "iliski":  # ciftler: bölge kodu metin, boş etiket/not boş metin, yön '+'/'-'
                df["bolge_kodu"] = df["bolge_kodu"].astype(str)
                for c in ("etiket", "not", "dogrulanmadi"):
                    df[c] = df[c].fillna("")
                df["beklenen_yon"] = df["beklenen_yon"].map(U.norm_sign)
            else:  # trend: uyarı sütunları ve L1 ürün kodları
                df = U.ensure_trend_cols(df)
            out[key] = df
    src = {"trend_iller.csv": None, "trend_bolgeler.csv": None, "ciftler.csv": None} if placeholder else \
        {"trend_iller.csv": f"mssql:{DB_NAME}.dbo.trend_iller", "trend_bolgeler.csv": f"mssql:{DB_NAME}.dbo.trend_bolgeler",
         "ciftler.csv": f"mssql:{DB_NAME}.dbo.ciftler"}
    return {**out, "yer_tutucu": placeholder, "kaynak": src}


def replace_tables(tables: dict, version: str = U.VERSION) -> dict:
    """Trend/ilişki tablolarını veri tabanına yazar (önce o tablolar boşaltılır). Dönüş: satır sayıları."""
    counts = {}
    ph = 1 if tables["yer_tutucu"] else 0
    with connect() as cn:
        cur = cn.cursor()
        cur.fast_executemany = True
        for key, (table, cols) in TABLES.items():
            cols = cols or BOLGE_COLS
            df = tables[key].reindex(columns=cols).copy()
            df = df.astype(object).where(pd.notna(df), None)
            df["veri_surumu"], df["yer_tutucu"] = version, ph
            names = list(df.columns)
            cur.execute(f"DELETE FROM dbo.{table}")  # noqa: S608
            cols_sql = ", ".join(f"[{c}]" for c in names)  # 'not' gibi ayrılmış sözcükler için köşeli parantez
            cur.executemany(f"INSERT INTO dbo.{table} ({cols_sql}) VALUES ({', '.join('?' * len(names))})",
                            [tuple(r) for r in df.itertuples(index=False)])
            counts[table] = len(df)
    return counts


# ---------------------------------------------------------------- kullanıcılar
def register(name: str, email: str, institution: str, orcid: str, password: str, example: bool = False,
             role: str = "akademisyen") -> dict:
    """Yeni hesap açar (vatandaş ya da akademisyen). E-posta zaten varsa ValueError. Dönüş: oturum kullanıcısı."""
    if role not in auth.ROLES:
        raise ValueError("Geçersiz rol.")
    email = email.strip().lower()
    academic = role == "akademisyen"
    with connect() as cn:
        cur = cn.cursor()
        if cur.execute("SELECT 1 FROM dbo.kullanicilar WHERE eposta = ?", email).fetchone():
            raise ValueError("Bu e-posta ile zaten bir hesap var. Giriş yapmayı deneyin.")
        cur.execute(
            "INSERT INTO dbo.kullanicilar (rol, ad, kurum, eposta, orcid, sifre_ozeti, kurum_eposta, ornek) "
            "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            role, name.strip(), ((institution or "").strip() or None) if academic else None, email,
            ((orcid or "").strip() or None) if academic else None, auth.hash_password(password),
            int(academic and auth.is_academic_email(email)), int(example))
        uid = int(cur.fetchone()[0])
    return session_user(uid)


def authenticate(email: str, password: str) -> dict | None:
    """E-posta + şifre doğruysa oturum kullanıcısını (kendi rolüyle) döndürür, değilse None."""
    with connect() as cn:
        cur = cn.cursor()
        row = cur.execute("SELECT id, sifre_ozeti FROM dbo.kullanicilar WHERE eposta = ?",
                          email.strip().lower()).fetchone()
        if not row or not auth.verify_password(password, row[1]):
            return None
        cur.execute("UPDATE dbo.kullanicilar SET son_giris = SYSUTCDATETIME() WHERE id = ?", row[0])
    return session_user(int(row[0]))


# ---------------------------------------------------------------- şifre sıfırlama
RESET_MINUTES = 15
RESET_MAX_TRIES = 5


def request_reset(email: str) -> tuple[str, str] | None:
    """Kayıtlı e-posta için 6 haneli tek kullanımlık kod üretir; özetini 15 dk geçerli olarak saklar.

    Dönüş: (kod, kullanıcı adı) ya da hesap yoksa None. Kod yalnızca e-postayla iletilmek üzere döner;
    veri tabanına düz metin yazılmaz. Önceki kullanılmamış kodlar geçersiz olur.
    """
    with connect() as cn:
        cur = cn.cursor()
        row = cur.execute("SELECT id, ad FROM dbo.kullanicilar WHERE eposta = ?", email.strip().lower()).fetchone()
        if not row:
            return None
        code = f"{secrets.randbelow(10**6):06d}"
        cur.execute("UPDATE dbo.sifre_sifirlama SET kullanildi = 1 WHERE kullanici_id = ? AND kullanildi = 0", row[0])
        cur.execute("INSERT INTO dbo.sifre_sifirlama (kullanici_id, kod_ozeti, son_gecerlilik) "
                    "VALUES (?, ?, DATEADD(MINUTE, ?, SYSUTCDATETIME()))",
                    row[0], auth.hash_password(code, iterations=50_000), RESET_MINUTES)
    return code, row[1]


def reset_password(email: str, code: str, new_password: str) -> bool:
    """Kod doğru, süresi geçmemiş ve deneme hakkı varsa şifreyi değiştirir. Dönüş: başarılı mı?"""
    with connect() as cn:
        cur = cn.cursor()
        row = cur.execute(
            "SELECT TOP 1 r.id, r.kod_ozeti, r.deneme, k.id FROM dbo.sifre_sifirlama r "
            "JOIN dbo.kullanicilar k ON k.id = r.kullanici_id WHERE k.eposta = ? AND r.kullanildi = 0 "
            "AND r.son_gecerlilik > SYSUTCDATETIME() ORDER BY r.id DESC", email.strip().lower()).fetchone()
        if not row or row[2] >= RESET_MAX_TRIES:
            return False
        if not auth.verify_password(code.strip(), row[1]):
            cur.execute("UPDATE dbo.sifre_sifirlama SET deneme = deneme + 1 WHERE id = ?", row[0])
            return False
        cur.execute("UPDATE dbo.kullanicilar SET sifre_ozeti = ? WHERE id = ?", auth.hash_password(new_password), row[3])
        cur.execute("UPDATE dbo.sifre_sifirlama SET kullanildi = 1 WHERE id = ?", row[0])
    return True


def session_user(uid: int) -> dict:
    """Oturumda tutulacak kullanıcı kaydı (şifre özeti dahil edilmez)."""
    with connect() as cn:
        r = _rows(cn.cursor().execute(
            "SELECT id, rol, ad, kurum, eposta, orcid, kurum_eposta, ornek FROM dbo.kullanicilar WHERE id = ?", uid))[0]
    return {"id": r["id"], "rol": r["rol"], "ad": r["ad"], "kurum": r["kurum"], "eposta": r["eposta"],
            "orcid": r["orcid"], "kurum_eposta": bool(r["kurum_eposta"]), "ornek": bool(r["ornek"])}


# ---------------------------------------------------------------- makaleler
ARTICLE_FIELDS = ["baslik", "yazarlar", "dergi", "yil", "doi", "ozet", "degiskenler", "iller", "durum"]


def validate_article(a: dict) -> list[str]:
    """Makale formu denetimi."""
    errors = []
    if len((a.get("baslik") or "").strip()) < 5:
        errors.append("Makale başlığını yazın.")
    if len((a.get("yazarlar") or "").strip()) < 2:
        errors.append("Yazarları yazın.")
    doi = (a.get("doi") or "").strip()
    if doi and not doi.startswith("10."):
        errors.append("DOI 10. ile başlamalı (ör. 10.1234/abcd).")
    y = a.get("yil")
    if y and not (1990 <= int(y) <= 2100):
        errors.append("Yıl geçerli değil.")
    return errors


def add_article(user_id: int, a: dict, example: bool = False) -> int:
    """Makale ekler; yeni kaydın kimliğini döndürür."""
    a = {**a, "durum": a.get("durum") or "yayimlandi"}
    vals = [(a.get(f) or None) if not isinstance(a.get(f), str) else (a.get(f).strip() or None) for f in ARTICLE_FIELDS]
    with connect() as cn:
        cur = cn.cursor()
        cur.execute(f"INSERT INTO dbo.makaleler (kullanici_id, {', '.join(ARTICLE_FIELDS)}, veri_surumu, ornek) "
                    f"OUTPUT INSERTED.id VALUES (?, {', '.join('?' * len(ARTICLE_FIELDS))}, ?, ?)",
                    user_id, *vals, U.VERSION, int(example))
        return int(cur.fetchone()[0])


def delete_article(user_id: int, article_id: int) -> bool:
    """Kullanıcının kendi makalesini siler (başkasınınkini silemez)."""
    with connect() as cn:
        cur = cn.cursor()
        cur.execute("DELETE FROM dbo.makaleler WHERE id = ? AND kullanici_id = ?", article_id, user_id)
        return cur.rowcount > 0


def list_articles(user_id: int | None = None) -> pd.DataFrame:
    """Makaleler (yazarın adı ve kurumuyla); `user_id` verilirse yalnızca o kullanıcınınkiler."""
    sql = ("SELECT m.id, m.baslik, m.yazarlar, m.dergi, m.yil, m.doi, m.ozet, m.degiskenler, m.iller, m.durum, "
           "m.veri_surumu, m.ornek, m.olusturma, k.ad AS ekleyen, k.kurum "
           "FROM dbo.makaleler m JOIN dbo.kullanicilar k ON k.id = m.kullanici_id")
    params = []
    if user_id is not None:
        sql += " WHERE m.kullanici_id = ?"
        params.append(user_id)
    sql += " ORDER BY m.yil DESC, m.olusturma DESC"
    with connect() as cn:
        df = pd.read_sql(sql, cn, params=params)
    # Boş alanlar NaN değil None olsun (ekranda "nan" ya da hata çıkmasın)
    return df.astype(object).where(pd.notna(df), None)


# ---------------------------------------------------------------- indirmeler
def log_download(user_id: int | None, file_name: str, rows: int, selection: dict) -> None:
    """İndirme kaydı (hangi kullanıcı hangi seçimi indirdi)."""
    with connect() as cn:
        cn.cursor().execute("INSERT INTO dbo.indirmeler (kullanici_id, dosya, satir_sayisi, secim) VALUES (?, ?, ?, ?)",
                            user_id, file_name, rows, json.dumps(selection, ensure_ascii=False))


def stats() -> dict:
    """Vitrin için sayılar: araştırmacı, makale ve indirme sayısı."""
    with connect() as cn:
        cur = cn.cursor()
        return {
            "arastirmaci": cur.execute("SELECT COUNT(*) FROM dbo.kullanicilar WHERE rol = N'akademisyen'").fetchone()[0],
            "makale": cur.execute("SELECT COUNT(*) FROM dbo.makaleler").fetchone()[0],
            "indirme": cur.execute("SELECT COUNT(*) FROM dbo.indirmeler").fetchone()[0],
        }
