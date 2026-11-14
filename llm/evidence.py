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
L3_FIELDS = ["sen_egimi", "ga_alt", "ga_ust", "p_mk", "p_fdr", "anlamli", "anlamli_hucre_orani",
             "etkin_n", "gereken_yil", "hucre_sayisi"]
META_FIELDS = ["birim", "donem", "seri", "kademe", "dogrulanmadi", "urun_surumu", "veri_seti_doi",
               "lisans", "doi"]


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
    return sorted({p.name.split("__")[1] for p in (pkg / "L3_ozet").glob(f"{degisken}__*__*.csv")})


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
def _l3_row(pkg: Path, degisken: str, urun: str, region: dict) -> tuple[dict | None, str | None, str]:
    """Bölgenin L3 satırı. İl için il dosyası (ad eşleşmesi); yoksa ilin bölgesine düşülür.

    Dönen: (satır, kaynak dosya yolu, gerçekte kullanılan bölge düzeyi "il"|"bolge"|"turkiye")
    """
    tries = []
    if region["level"] == "il":
        tries += [("il", region["key"]), ("bolge", region.get("bolge"))]
    elif region["level"] == "bolge":
        tries += [("bolge", region["key"])]
    else:
        tries += [("bolge", "turkiye")]
    for level, key in tries:
        if not key:
            continue
        f = pkg / "L3_ozet" / f"{degisken}__{urun}__{'il' if level == 'il' else 'bolge'}.csv"
        if not f.exists():
            continue
        try:
            df = pd.read_csv(f, dtype={"bolge_kodu": str}, encoding="utf-8-sig")
        except pd.errors.EmptyDataError:   # boş özet dosyası: bu düzeyi atla
            continue
        if df.empty or not {"bolge_kodu", "bolge_adi"} <= set(df.columns):
            continue
        hit = df[(df["bolge_kodu"].map(norm_key) == key) | (df["bolge_adi"].map(norm_key) == key)]
        if len(hit):
            return hit.iloc[0].to_dict(), f.relative_to(pkg).as_posix(), "turkiye" if key == "turkiye" else level
    return None, None, region["level"]


def trend_label(row: dict) -> str:
    """İşaret + anlamlılık bayrağı -> etiket (hesap değil, sınıflandırma)."""
    s, a = _num(row.get("sen_egimi")), _num(row.get("anlamli"))
    if s is None or a is None or a < 0:
        return "yetersiz"
    if a == 1:
        return "anlamli_artis" if s > 0 else "anlamli_azalis"
    return "anlamsiz"


def _trend_evidence(pkg, degisken, urun, region) -> dict | None:
    row, path, level = _l3_row(pkg, degisken, urun, region)
    if row is None:
        return None
    e = {"id": f"trend__{degisken}__{urun}", "type": "trend", "variable": degisken, "product": urun,
         "region_level": level, "region_name": row.get("bolge_adi"), "file": path,
         "label": trend_label(row)}
    e.update({k: _num(row.get(k)) for k in L3_FIELDS})
    e.update({k: (None if pd.isna(row.get(k)) else row.get(k)) for k in META_FIELDS if k in row})
    e["dogrulanmadi"] = str(e.get("dogrulanmadi", "")).strip().lower() == "evet"
    e["provenance"] = provenance(degisken, urun)
    return e


def _agreement(trends: list[dict], degisken: str) -> dict | None:
    """Aynı değişkenin ürünleri arasında yön uyumu: k ürün aynı yönde anlamlı / m ürünün verisi var."""
    usable = [t for t in trends if t["variable"] == degisken and t.get("sen_egimi") is not None]
    if len(usable) < 2:
        return None
    up = sum(t["label"] == "anlamli_artis" for t in usable)
    down = sum(t["label"] == "anlamli_azalis" for t in usable)
    k, m = max(up, down), len(usable)
    return {"id": f"uyum__{degisken}", "type": "kaynak_uyumu", "variable": degisken,
            "k": k, "m": m, "yon": "artis" if up >= down else "azalis",
            "urunler": [t["product"] for t in usable],
            "label": "uyumlu" if k == m else ("kismen" if k > 0 else "uyumsuz"),
            "kapsam": "bölge ortalaması (L3) üzerinden"}


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

    targets = {b["degisken"] for b in plan.get("belirti", [])}
    variables = targets | {s["degisken"] for s in plan.get("supheliler", [])}
    trends = []
    for v in sorted(variables, key=lambda x: (x not in targets, x)):
        prods = products_of(pkg, v)
        if not prods:
            out["warnings"].append(f"{v} için L3 özeti yok.")
        for u in prods:
            e = _trend_evidence(pkg, v, u, region)
            if e:
                trends.append(e)
    out["analyses"] += trends
    for v in variables:
        a = _agreement(trends, v)
        if a:
            out["analyses"].append(a)
    rel = _relation_evidence(pkg, variables, targets, region)
    out["analyses"] += rel
    fell = sorted({f"{a['pair']} → {a.get('bolge_adi') or a['region_key']}" for a in rel
                   if a["region_level"] != region["level"]})
    if fell:
        out["warnings"].append("Bu çiftler için seçilen düzeyde ilişki (L4) satırı yok, daha geniş bölgenin "
                               "sonucu kullanıldı: " + "; ".join(fell) + ".")
    if trends and any(t["region_level"] != region["level"] for t in trends):
        out["warnings"].append("Bazı değişkenlerde il özeti yok; bağlı olduğu bölgenin sonucu kullanıldı.")
    donemler = {t.get("donem") for t in trends if t.get("donem")}
    out["period"] = sorted(donemler)[0] if len(donemler) == 1 else (sorted(donemler) or None)
    return out
