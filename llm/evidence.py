"""L3/L4 analiz paketini (docs/sozlesmeler.md bölüm 2) LLM katmanının kanıt listesine çevirir.

Paket kökü: `outputs/trend-dedektifi-turkiye-<surum>/` (ya da TD_PAKET ortam değişkeni).
  L3_ozet/<degisken>__<urun>__il.csv, L3_ozet/<degisken>__<urun>__bolge.csv  -> "trend" kanıtları
  L4_iliski/ciftler.csv                                                     -> "iliski" kanıtları
Aynı değişkenin birden çok ürünü varsa bölge ortalaması üzerinden "kaynak_uyumu" kanıtı eklenir.

Bu modül SAYI ÜRETMEZ: değerler CSV'den olduğu gibi kopyalanır. Tek türetme, işaret ve anlamlılık
bayrağından etiket ("anlamli_artis" vb.) ve ürünlerin aynı yönde olup olmadığının SAYIMIDIR.
"""
from __future__ import annotations

import math
import os
import re
import unicodedata
from pathlib import Path

import pandas as pd
import yaml

REPO = Path(__file__).resolve().parent.parent
OUTPUTS = REPO / "outputs"
CATALOG = REPO / "data" / "catalog.yaml"

_TR = str.maketrans("çğıöşüÇĞİÖŞÜâîûÂÎÛ", "cgiosuCGIOSUaiuAIU")
# docs/sozlesmeler.md 2.2 (L3) sütunları
L3_FIELDS = ["sen_egimi", "ga_alt", "ga_ust", "p_mk", "p_fdr", "anlamli", "etkin_n", "gereken_yil",
             "mk_yedek", "hucre_sayisi", "anlamli_hucre_orani", "anlamli_artan_orani", "anlamli_azalan_orani",
             "medyan_hucre_egimi", "donem_baslangic", "donem_bitis"]
META_FIELDS = ["mevsim", "birim", "egim_birimi", "trend_uyarisi", "not", "kademe", "dogrulanmadi",
               "urun_surumu", "veri_seti_doi", "lisans", "doi", "bolge_adi", "duzey", "ust_bolge"]
MEVSIMLER = ("yillik", "kis", "ilkbahar", "yaz", "sonbahar")


def norm_key(name: str) -> str:
    """data/regions.normalize_name ile aynı kural: "Hakkâri" -> "hakkari", "Doğu Anadolu" -> "dogu_anadolu"."""
    s = unicodedata.normalize("NFKD", str(name).strip().translate(_TR))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _num(x):
    """CSV hücresini sayıya çevirir; boş/NaN -> None."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# --------------------------------------------------------------------------- paket
def find_package(root: Path | str | None = None) -> Path | None:
    """Analiz paketinin kökü: TD_PAKET > verilen yol > outputs/ altındaki en yeni sürüm."""
    env = os.environ.get("TD_PAKET")
    if env:
        return Path(env)
    if root is not None:
        return Path(root)
    found = sorted(OUTPUTS.glob("trend-dedektifi-turkiye-*")) if OUTPUTS.exists() else []
    return found[-1] if found else None


def products_of(pkg: Path, degisken: str) -> list[str]:
    """L3'te bu değişken için hangi ürünlerin özeti var (ör. yagis -> ['GLDAS', 'GPM', 'MERRA2'])."""
    return sorted({p.name.split("__")[1] for p in (pkg / "L3_ozet").glob(f"{degisken}__*__*.csv")
                   if p.name.split("__")[1] != "kaynak_uyumu"})


def provenance(degisken: str, urun_kodu: str, catalog_path: Path = CATALOG) -> dict:
    """Katalogdan ürün künyesi: short_name, version, doi, daac (veri atfı için)."""
    try:
        cat = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    for v in cat.get("degiskenler", []):
        u = cat["urunler"].get(v.get("urun"), {})
        if v.get("ad") == degisken and u.get("dosya_kodu") == urun_kodu:
            return {k: u.get(k) for k in ("short_name", "version", "doi", "daac")}
    return {}


# --------------------------------------------------------------------------- L3
def _read_l3(f: Path) -> pd.DataFrame | None:
    """L3 CSV'si (bolge_kodu metin; boş hücre NaN). Boş ya da bozuk dosyada None.

    Sözleşme 2.2 öncesi biçime (bolge_anahtari / duzey / mevsim sütunu olmayan; ör. arayüzün eski yer
    tutucu paketi) uyum: anahtar addan (bölgede koddan) türetilir, düzey dosya adından, mevsim "yillik"."""
    if not f.exists():
        return None
    try:
        df = pd.read_csv(f, dtype={"bolge_kodu": str}, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return None
    if df.empty or not ({"bolge_anahtari"} <= set(df.columns) or {"bolge_kodu", "bolge_adi"} <= set(df.columns)):
        return None
    if "bolge_anahtari" not in df.columns:
        kod = df["bolge_kodu"].astype(str)
        df["bolge_anahtari"] = [norm_key(k) if not k.strip().isdigit() else norm_key(a)
                                for k, a in zip(kod, df["bolge_adi"])]
    if "duzey" not in df.columns:
        il_dosyasi = f.stem.endswith("__il")
        df["duzey"] = ["il" if il_dosyasi else ("ulke" if k == "turkiye" else "bolge")
                       for k in df["bolge_anahtari"]]
    if "mevsim" not in df.columns:
        df["mevsim"] = "yillik"
    return df


def _levels(region: dict) -> list[tuple[str, str, str]]:
    """Denenecek (dosya düzeyi, satır düzeyi, anahtar) sırası: il -> ilin bölgesi -> Türkiye.
    Türkiye satırı bölge dosyasında `duzey = ulke` olarak durur (sözleşme 2.2)."""
    out = []
    if region["level"] == "il":
        out.append(("il", "il", region["key"]))
        if region.get("bolge"):
            out.append(("bolge", "bolge", region["bolge"]))
    elif region["level"] == "bolge":
        out.append(("bolge", "bolge", region["key"]))
    out.append(("bolge", "ulke", "turkiye"))
    return out


def _l3_row(pkg: Path, stem: str, region: dict, mevsim: str) -> tuple[dict | None, str | None, str]:
    """Bölge × mevsim satırı. `stem`: "<degisken>__<urun>" ya da "<degisken>__kaynak_uyumu".
    Dönen: (satır, paket köküne göreli dosya yolu, kullanılan düzey "il"|"bolge"|"turkiye").
    Kullanılan bölge anahtarı satıra `_anahtar` olarak eklenir (karne eşleşmesi için)."""
    for file_level, row_level, key in _levels(region):
        f = pkg / "L3_ozet" / f"{stem}__{file_level}.csv"
        df = _read_l3(f)
        if df is None:
            continue
        hit = df[(df["bolge_anahtari"].map(norm_key) == key) & (df["duzey"].astype(str) == row_level)
                 & (df["mevsim"] == mevsim)]
        if len(hit):
            level = "turkiye" if row_level == "ulke" else row_level
            row = hit.iloc[0].to_dict()
            row["_anahtar"] = key
            return row, f.relative_to(pkg).as_posix(), level
    return None, None, region["level"]


def trend_label(row: dict) -> str:
    """İşaret + anlamlılık bayrağı -> etiket (hesap değil, sınıflandırma). `anlamli` sözleşme 2.1
    kuralıyla Kişi 2 tarafından belirlenir (p_fdr ≤ 0,10 ve GA sıfırı dışlıyor)."""
    s, a = _num(row.get("sen_egimi")), _num(row.get("anlamli"))
    if s is None or a is None or a < 0:
        return "yetersiz"
    if a == 1:
        return "anlamli_artis" if s > 0 else "anlamli_azalis"
    return "anlamsiz"


def _suffix(mevsim: str) -> str:
    return "" if mevsim == "yillik" else f"__{mevsim}"


def _meta(row: dict, keys) -> dict:
    return {k: (None if pd.isna(row.get(k)) or row.get(k) == "" else row.get(k)) for k in keys if k in row}


def _trend_evidence(pkg, degisken, urun, region, mevsim) -> dict | None:
    row, path, level = _l3_row(pkg, f"{degisken}__{urun}", region, mevsim)
    if row is None:
        return None
    e = {"id": f"trend__{degisken}__{urun}{_suffix(mevsim)}", "type": "trend", "variable": degisken,
         "product": urun, "region_level": level, "region_key": row["_anahtar"],
         "region_name": row.get("bolge_adi"), "file": path, "label": trend_label(row)}
    e.update({k: _num(row.get(k)) for k in L3_FIELDS})
    e.update(_meta(row, META_FIELDS))
    if e.get("donem_baslangic") is not None and e.get("donem_bitis") is not None:
        e["donem"] = f"{int(e['donem_baslangic'])}–{int(e['donem_bitis'])}"
    e["dogrulanmadi"] = str(row.get("dogrulanmadi", "")).strip().lower() == "evet"
    e["provenance"] = provenance(degisken, urun)
    return e


def _agreement(pkg: Path, trends: list[dict], degisken: str, region: dict, mevsim: str) -> dict | None:
    """Ürünler arası yön uyumu. Önce Kişi 2'nin L3 kaynak uyumu dosyası (ortak döneme kırpılmış,
    sözleşme 2.2); yoksa elimizdeki trend satırlarının etiket SAYIMI (yedek, farklı dönemler olabilir)."""
    row, path, level = _l3_row(pkg, f"{degisken}__kaynak_uyumu", region, mevsim)
    if row is not None and _num(row.get("m")) is not None:
        k, m = int(_num(row["k"]) or 0), int(_num(row["m"]))
        if m < 1:
            return None
        return {"id": f"uyum__{degisken}{_suffix(mevsim)}", "type": "kaynak_uyumu", "variable": degisken,
                "k": k, "m": m, "isaret_uyumu": _num(row.get("isaret_uyumu")),
                "urunler": [u.strip() for u in str(row.get("urunler", "")).split(",") if u.strip()],
                "ortak_donem": row.get("ortak_donem"), "mevsim": mevsim, "region_level": level,
                "label": "uyumlu" if k == m else ("kismen" if k > 0 else "uyumsuz"),
                "kapsam": "bölge ortalaması serileri, ortak dönem", "file": path}
    usable = [t for t in trends if t["variable"] == degisken and t.get("sen_egimi") is not None]
    if len(usable) < 2:
        return None
    up = sum(t["label"] == "anlamli_artis" for t in usable)
    down = sum(t["label"] == "anlamli_azalis" for t in usable)
    k, m = max(up, down), len(usable)
    return {"id": f"uyum__{degisken}{_suffix(mevsim)}", "type": "kaynak_uyumu", "variable": degisken,
            "k": k, "m": m, "urunler": [t["product"] for t in usable], "mevsim": mevsim,
            "label": "uyumlu" if k == m else ("kismen" if k > 0 else "uyumsuz"),
            "kapsam": "ürün satırlarının sayımı (kaynak uyumu dosyası yok; dönemler farklı olabilir)"}


# --------------------------------------------------------------------------- L4
L4_FIELDS = ["r", "p", "p_fdr", "anlamli", "etkin_n", "n", "r1_1", "r1_2", "hucre_sayisi"]
L4_META = ["cift_no", "seri", "beklenen_yon", "donem", "kademe", "not", "doi_1", "doi_2", "bolge_adi",
           "urun_surumu", "veri_seti_doi", "lisans"]


def _pair_vars(cift: str) -> list[tuple[str, str]]:
    """"sicaklik_2m__MERRA2~kar_ortusu__MOD10CM" -> [("sicaklik_2m", "MERRA2"), ("kar_ortusu", "MOD10CM")]"""
    return [tuple(p.split("__", 1)) for p in str(cift).split("~")]


def _region_mask(df: pd.DataFrame, level: str, key: str) -> pd.Series:
    """L4 satırlarını bölgeye göre seçer: bolge_turu + (bolge_kodu ya da bolge_adi) — L3 ile aynı kural."""
    turu = df["bolge_turu"].astype(str).str.strip().str.lower()
    if level == "turkiye":
        return turu == "turkiye"
    same = (df["bolge_kodu"].map(norm_key) == key) | (df["bolge_adi"].map(norm_key) == key)
    return (turu == level) & same


def _relation_id(v1, u1, v2, u2, gecikme) -> str:
    """Kanıt kimliği; gecikmeli çiftlerde (çift 3: 1 ve 2 ay) gecikme kimliğe girer, yoksa çakışır."""
    base = f"iliski__{v1}__{u1}__{v2}__{u2}"
    return f"{base}__g{gecikme}" if gecikme else base


def _relation_evidence(pkg: Path, variables: set[str], targets: set[str], region: dict) -> list[dict]:
    """L4 (docs/sozlesmeler.md 2.3): plandaki değişkenlerle ilgili çiftler.

    Bir çift alınır: değişkenlerinden biri belirti (hedef) ise ya da ikisi de plandaysa.
    Her çift × gecikme için EN AYRINTILI mevcut düzey seçilir (il -> ilin bölgesi -> Türkiye);
    ör. yağış~GRACE yalnız bölge/Türkiye düzeyinde vardır, il sorusunda bölge satırı kullanılır.
    """
    f = pkg / "L4_iliski" / "ciftler.csv"
    if not f.exists():
        return []
    try:
        df = pd.read_csv(f, dtype={"bolge_kodu": str}, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return []
    if df.empty or not {"cift", "bolge_turu", "bolge_kodu", "bolge_adi"} <= set(df.columns):
        return []
    if "gecikme_ay" not in df.columns:
        df["gecikme_ay"] = 0
    df["gecikme_ay"] = pd.to_numeric(df["gecikme_ay"], errors="coerce").fillna(0).astype(int)

    levels = []
    if region["level"] == "il":
        levels = [("il", region["key"]), ("bolge", region.get("bolge")), ("turkiye", "turkiye")]
    elif region["level"] == "bolge":
        levels = [("bolge", region["key"]), ("turkiye", "turkiye")]
    else:
        levels = [("turkiye", "turkiye")]
    levels = [(lv, k) for lv, k in levels if k]

    out = []
    for (cift, gecikme), grp in df.groupby(["cift", "gecikme_ay"], sort=True):
        (v1, u1), (v2, u2) = _pair_vars(cift)
        vs = {v1, v2}
        if not (vs & targets or vs <= variables):
            continue
        for level, key in levels:
            hit = grp[_region_mask(grp, level, key)]
            if len(hit):
                r = hit.iloc[0].to_dict()
                etiket = r.get("etiket")
                e = {"id": _relation_id(v1, u1, v2, u2, gecikme), "type": "iliski", "pair": cift,
                     "variables": [v1, v2], "products": [u1, u2], "gecikme_ay": int(gecikme),
                     "region_level": level, "region_key": key,
                     "label": etiket if isinstance(etiket, str) and etiket.strip() else "hesaplanamadi",
                     "file": f.relative_to(pkg).as_posix()}
                e.update({k: _num(r.get(k)) for k in L4_FIELDS})
                e.update({k: (None if pd.isna(r.get(k)) else r.get(k)) for k in L4_META if k in r})
                e["dogrulanmadi"] = str(r.get("dogrulanmadi", "")).strip().lower() == "evet"
                e["provenance"] = [provenance(v1, u1), provenance(v2, u2)]
                out.append(e)
                break
    return out


# --------------------------------------------------------------------------- karne ve büyüklük (2.4, 2.5)
KONTROL_ADLARI = {
    "trend": [("a_kaynak_uyumu", "a_sayi", "kaynak uyumu"), ("b_karistirma", "b_p_perm", "karıştırma testi"),
              ("c_donem", "c_sayi", "dönem kırpma"), ("d_esik", "d_sayi", "sıkı eşik (α = 0,05)"),
              ("e_yeterlilik", "e_sayi", "veri yeterliliği")],
    "iliski": [("a_kaynak_uyumu", "a_sayi", "kaynak uyumu"), ("b_karistirma", "b_p_perm", "karıştırma testi"),
               ("c_trend", "c_sayi", "trendden arındırma"), ("d_gecikme", "d_sayi", "gecikme ±1 ay"),
               ("e_esik", "e_sayi", "sıkı eşik (α = 0,05)")],
    "buyukluk": [("a_kaynak_uyumu", "a_sayi", "kaynak uyumu"), ("b_donem", "b_sayi", "dönem kırpma"),
                 ("c_ga_genisligi", "c_sayi", "güven aralığı genişliği")],
}
# Metin sütunlarında paketten gelen sayılar (ör. "2/3 ürün", "Held ve Soden 2006"): doğrulayıcı bunları da
# kanıt sayısı kabul eder. Yalnız bu sütunlar açılır; rakam içeren her metin değil.
SAYI_METIN_SUTUNLARI = ["gerekce", "a_sayi", "c_sayi", "d_sayi", "e_sayi", "b_sayi", "f_uyarilar",
                        "beklenen_kaynak", "etiket_gerekce", "yorum", "donem"]
BUYUKLUK_TESTLERI = ("cc", "butce", "kar_cizgisi")


def _read_any(f: Path, str_cols=("bolge_kodu",)) -> pd.DataFrame | None:
    """Karne/büyüklük CSV'si; yoksa ya da boşsa None."""
    if not f.exists():
        return None
    try:
        df = pd.read_csv(f, dtype={c: str for c in str_cols}, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return None
    return None if df.empty else df


def _same_region(df: pd.DataFrame, key: str) -> pd.Series:
    return (df["bolge_adi"].map(norm_key) == key) | (df["bolge_kodu"].map(norm_key) == key)


def _checks(row: dict, kind: str) -> list[dict]:
    """Karne kontrolleri: [{"ad", "durum" (geçti/kaldı/uygulanamaz), "sayi"}]."""
    out = []
    for durum_col, sayi_col, ad in KONTROL_ADLARI[kind]:
        if durum_col in row:
            out.append({"ad": ad, "durum": None if pd.isna(row.get(durum_col)) else str(row[durum_col]),
                        "sayi": None if pd.isna(row.get(sayi_col)) else row.get(sayi_col)})
    return out


def _karne_evidence(row: dict, about: str, kind: str, path: str) -> dict:
    e = {"id": f"karne__{about}", "type": "karne", "about": about, "kind": kind, "file": path,
         "label": str(row.get("guven") or "YOK"), "guven": row.get("guven"),
         "gerekce": None if pd.isna(row.get("gerekce")) else str(row.get("gerekce")),
         "kontroller": _checks(row, kind), "b_p_perm": _num(row.get("b_p_perm")),
         "f_kritik": None if pd.isna(row.get("f_kritik")) else row.get("f_kritik"),
         "kural_surumu": row.get("kural_surumu")}
    e["sayi_metinleri"] = [str(row[c]) for c in SAYI_METIN_SUTUNLARI if c in row and not pd.isna(row[c])]
    return e


def _trend_karne(pkg: Path, t: dict, mevsim: str) -> dict | None:
    """Trend kanıtının karne satırı (karne/trend_karne_{il,bolge}.csv)."""
    level = t["region_level"]
    f = pkg / "karne" / f"trend_karne_{'il' if level == 'il' else 'bolge'}.csv"
    df = _read_any(f)
    if df is None:
        return None
    duzey = {"il": "il", "bolge": "bolge", "turkiye": "ulke"}[level]
    hit = df[(df["degisken"] == t["variable"]) & (df["urun"] == t["product"]) & (df["mevsim"] == mevsim)
             & (df["duzey"].astype(str) == duzey) & _same_region(df, t["region_key"])]
    return _karne_evidence(hit.iloc[0].to_dict(), t["id"], "trend", f.relative_to(pkg).as_posix()) if len(hit) else None


def _relation_karne(pkg: Path, r: dict) -> dict | None:
    """İlişki kanıtının karne satırı (karne/iliski_karne.csv): çift + gecikme + bölge."""
    f = pkg / "karne" / "iliski_karne.csv"
    df = _read_any(f)
    if df is None:
        return None
    gec = pd.to_numeric(df.get("gecikme_ay", 0), errors="coerce").fillna(0).astype(int)
    hit = df[(df["cift"] == r["pair"]) & (gec == int(r.get("gecikme_ay") or 0))
             & (df["bolge_turu"].astype(str) == r["region_level"]) & _same_region(df, r["region_key"])]
    return _karne_evidence(hit.iloc[0].to_dict(), r["id"], "iliski", f.relative_to(pkg).as_posix()) if len(hit) else None


def _buyukluk_evidence(pkg: Path, tests: list[str], region: dict, mevsim: str) -> tuple[list[dict], list[str]]:
    """Büyüklük testleri (L4_iliski/buyukluk/<test>__{il,bolge}.csv). İl satırı yoksa (ör. su bütçesinde
    hiç yok) ilin bölgesine, o da yoksa Türkiye'ye düşülür. Kar çizgisinde `yol` mevsimdir: soru/kart mevsimi
    kis ya da ilkbahar ise yalnız o yol alınır."""
    out, warn = [], []
    for test in tests:
        hit, used = None, None
        for file_level, row_level, key in _levels(region):
            f = pkg / "L4_iliski" / "buyukluk" / f"{test}__{file_level}.csv"
            df = _read_any(f)
            if df is None:
                continue
            turu = df["bolge_turu"].astype(str)
            m = (turu == ("turkiye" if row_level == "ulke" else row_level)) & _same_region(df, key)
            if test == "kar_cizgisi" and mevsim in set(df["yol"].astype(str)):
                m &= df["yol"].astype(str) == mevsim
            if m.any():
                hit, used = df[m], (f, "turkiye" if row_level == "ulke" else row_level)
                break
        if hit is None:
            continue
        if used[1] != region["level"]:
            warn.append(f"Büyüklük testi '{test}' için seçilen düzeyde satır yok; daha geniş bölge kullanıldı.")
        for row in hit.to_dict("records"):
            e = {"id": f"buyukluk__{test}__{row['yol']}__{row['degisken']}", "type": "buyukluk",
                 "test": test, "yol": str(row["yol"]), "variable": row.get("degisken"),
                 "product": row.get("urun"), "region_level": used[1], "bolge_adi": row.get("bolge_adi"),
                 "file": used[0].relative_to(pkg).as_posix(), "label": row.get("etiket"),
                 "kontroller": _checks(row, "buyukluk")}
            e.update({k: _num(row.get(k)) for k in ("gozlenen", "ga_alt", "ga_ust", "beklenen", "beklenen_alt",
                                                    "beklenen_ust", "n", "hucre_sayisi")})
            e.update(_meta(row, ["birim", "beklenen_kaynak", "etiket_gerekce", "yorum", "guven", "gerekce",
                                 "kritik", "donem", "kural_surumu", "urun_surumu", "veri_seti_doi", "lisans"]))
            e["sayi_metinleri"] = [str(row[c]) for c in SAYI_METIN_SUTUNLARI if c in row and not pd.isna(row[c])]
            out.append(e)
    return out, warn


# --------------------------------------------------------------------------- ana giriş
def collect_evidence(plan: dict, pkg: Path | str | None = None) -> dict:
    """Plan için kanıt listesi (answer() bunu `results` olarak kullanır).

    Dönen: {"package", "region", "period", "analyses": [...], "warnings": [...]}
    """
    pkg = find_package(pkg)
    region = {"key": plan["region"], "level": plan.get("region_level", "bolge"),
              "bolge": plan.get("region_bolge"), "name": plan.get("region_name")}
    out = {"package": str(pkg) if pkg else None, "region": region, "period": None,
           "analyses": [], "warnings": []}
    if pkg is None or not (pkg / "L3_ozet").exists():
        out["warnings"].append("Analiz paketi (L3) bulunamadı; önce istatistik çıktıları üretilmeli.")
        return out

    mevsim = plan.get("mevsim") or "yillik"
    out["mevsim"] = mevsim
    targets = {b["degisken"] for b in plan.get("belirti", [])}
    variables = targets | {s["degisken"] for s in plan.get("supheliler", [])}
    trends = []
    for v in sorted(variables, key=lambda x: (x not in targets, x)):
        prods = products_of(pkg, v)
        if not prods:
            out["warnings"].append(f"{v} için L3 özeti yok.")
        for u in prods:
            e = _trend_evidence(pkg, v, u, region, mevsim)
            if e is None and mevsim != "yillik" and plan.get("mevsim_kaynak") != "soru":
                e = _trend_evidence(pkg, v, u, region, "yillik")   # kartın varsayılan mevsimi yoksa
                if e:
                    out["warnings"].append(f"{v} ({u}): {mevsim} satırı yok, yıllık sonuç kullanıldı.")
            elif e is None and plan.get("mevsim_kaynak") == "soru":
                out["warnings"].append(f"{v} ({u}): istenen mevsim ({mevsim}) için L3 satırı yok.")
            if e:
                trends.append(e)
    out["analyses"] += trends
    for v in sorted(variables):
        a = _agreement(pkg, trends, v, region, mevsim)
        if a:
            out["analyses"].append(a)
    rel = _relation_evidence(pkg, variables, targets, region)
    out["analyses"] += rel
    # Bulgu karnesi (2.4): her trend ve ilişki kanıtının hemen ardından kendi karne satırı.
    karneler = [k for k in ([_trend_karne(pkg, t, t.get("mevsim") or mevsim) for t in trends]
                            + [_relation_karne(pkg, r) for r in rel]) if k]
    out["analyses"] += karneler
    if (trends or rel) and not karneler and (pkg / "karne").exists():
        out["warnings"].append("Bu sonuçlar için bulgu karnesi satırı bulunamadı.")
    # Büyüklük testleri (2.5): kartın listesindeki testler.
    tests = [t for t in plan.get("buyukluk_testleri", []) if t in BUYUKLUK_TESTLERI]
    if tests:
        buy, w = _buyukluk_evidence(pkg, tests, region, mevsim)
        out["analyses"] += buy
        out["warnings"] += w
    fell = sorted({f"{a['pair']} → {a.get('bolge_adi') or a['region_key']}" for a in rel
                   if a["region_level"] != region["level"]})
    if fell:
        out["warnings"].append("Bu çiftler için seçilen düzeyde ilişki (L4) satırı yok, daha geniş bölgenin "
                               "sonucu kullanıldı: " + "; ".join(fell) + ".")
    if trends and any(t["region_level"] != region["level"] for t in trends):
        out["warnings"].append("Bazı değişkenlerde il özeti yok; bağlı olduğu bölgenin sonucu kullanıldı.")
    donemler = sorted({t.get("donem") for t in trends if t.get("donem")})
    out["period"] = donemler[0] if len(donemler) == 1 else (donemler or None)
    return out
