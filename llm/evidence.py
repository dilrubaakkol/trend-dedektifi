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
            return hit.iloc[0].to_dict(), str(f.relative_to(pkg)), "turkiye" if key == "turkiye" else level
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
def _pair_vars(cift: str) -> list[tuple[str, str]]:
    return [tuple(p.split("__", 1)) for p in str(cift).split("~")]


def _relation_evidence(pkg: Path, variables: set[str], targets: set[str], region: dict) -> tuple[list, str | None]:
    """L4 satırları: en az bir hedef (belirti) değişkeni ve plandaki başka bir değişkeni içeren çiftler.
    İl için L4 satırı yoksa ilin bölgesine, o da yoksa Türkiye'ye düşülür."""
    f = pkg / "L4_iliski" / "ciftler.csv"
    if not f.exists():
        return [], None
    df = pd.read_csv(f, dtype={"bolge": str}, encoding="utf-8-sig")
    df["_k"] = df["bolge"].map(norm_key)
    for key in [region["key"], region.get("bolge"), "turkiye"]:
        if not key:
            continue
        rows = []
        for r in df[df["_k"] == key].to_dict("records"):
            vs = {v for v, _ in _pair_vars(r["cift"])}
            if vs & targets and vs <= variables:
                (v1, u1), (v2, u2) = _pair_vars(r["cift"])
                rows.append({"id": f"iliski__{v1}__{u1}__{v2}__{u2}", "type": "iliski",
                             "pair": r["cift"], "variables": [v1, v2], "products": [u1, u2],
                             "region_key": key, "r": _num(r.get("r")), "p": _num(r.get("p")),
                             "etkin_n": _num(r.get("etkin_n")), "label": r.get("etiket"),
                             "file": str(f.relative_to(pkg))})
        if rows:
            return rows, key
    return [], None


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
    rel, rel_key = _relation_evidence(pkg, variables, targets, region)
    out["analyses"] += rel
    if rel and rel_key != region["key"]:
        out["warnings"].append(f"Bu bölge için ilişki (L4) satırı yok; '{rel_key}' sonuçları gösteriliyor.")
    if trends and any(t["region_level"] != region["level"] for t in trends):
        out["warnings"].append("Bazı değişkenlerde il özeti yok; bağlı olduğu bölgenin sonucu kullanıldı.")
    donemler = {t.get("donem") for t in trends if t.get("donem")}
    out["period"] = sorted(donemler)[0] if len(donemler) == 1 else (sorted(donemler) or None)
    return out
