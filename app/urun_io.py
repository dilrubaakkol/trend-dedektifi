"""Yayımlanan veri setinin (Katman 1–4) dosyalarını bulan, okuyan ve paketleyen yardımcılar.

Site yeni hesap yapmaz: trendler `L3_ozet/<degisken>__<urun>__{il,bolge}.csv` (sözleşme 2.2), ilişkiler
`L4_iliski/ciftler.csv` (sözleşme 2.3) dosyalarından okunur. Paket kökü: `TD_PAKET` ortam değişkeni, sonra
`outputs/trend-dedektifi-turkiye-<surum>/`. Dosyalar henüz yoksa ekran akışını göstermek için
**SENTETİK YER TUTUCU** tablolar üretilir; bunlar her yerde işaretlenir ve indirilen dosya adı `YER_TUTUCU_`
ile başlar.

İç tablo biçimi: L3 sütunlarının hepsi korunur, üstüne ekranın kullandığı kısa adlar eklenir
(`il`, `plaka`, `bolge`, `egim_10yil`, `ci_alt`, `ci_ust`, `anlamli_fdr`, ...). Ürün adları L1 dosya
kodlarıdır (`MERRA2`, `GPM`, `GLDAS`, ...).
"""

from __future__ import annotations

import io
import json
import math
import os
import unicodedata
import zipfile
from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
BOUNDARIES = ROOT / "data" / "boundaries"
CATALOG = ROOT / "data" / "catalog.yaml"
VAR_CARDS = ROOT / "kb" / "degiskenler.yaml"

VERSION = "v0.1"
LICENSE = "CC BY 4.0"
try:  # yayın kutusu ve DOI Kişi 1'in yayın paketinden; içe aktarılamazsa aynı değerler
    from data.export import KADEME_1, VERI_SETI_DOI, YAYIN_BBOX  # noqa: F401
except Exception:  # noqa: BLE001
    YAYIN_BBOX = (25.5, 35.5, 45.0, 42.5)
    VERI_SETI_DOI = "(yayında doldurulacak)"
    KADEME_1 = set()

# Yayın paketi (python -m data.export / stats.l2 / stats.l3 / physics.run) kökleri, öncelik sırasıyla.
SEARCH_DIRS = [ROOT / "outputs" / f"trend-dedektifi-turkiye-{VERSION}"]
LAYERS = [
    ("L1_kup", "1 · Uyumlaştırılmış küp", "Her değişken: Türkiye, ortak 0,25° ızgara, aylık, ortak birim, ülke maskesi",
     "<degisken>__<urun>.nc", "Kişi 1"),
    ("L2_trend", "2 · Hücre trendleri", "Her 0,25° hücre ve 5 mevsim için Sen eğimi, Hamed-Rao MK, FDR",
     "<degisken>__<urun>__trend.nc", "Kişi 2"),
    ("L3_ozet", "3 · İl ve bölge özetleri", "81 il, 7 bölge ve Türkiye için alan ortalaması trendi; kaynak uyumu",
     "<degisken>__<urun>__il.csv · __bolge.csv · <degisken>__kaynak_uyumu__*.csv", "Kişi 2"),
    ("L4_iliski", "4 · İlişkiler", "6 değişken çiftinin ilişkisi ve fizik kontrolü",
     "ciftler.csv · iliski__<d1>__<d2>.nc", "Kişi 3"),
]


def package_dirs() -> list[Path]:
    """Paket kökleri: önce TD_PAKET (LLM katmanıyla aynı değişken), sonra SEARCH_DIRS."""
    env = os.environ.get("TD_PAKET")
    return ([Path(env)] if env else []) + list(SEARCH_DIRS)

TREND_COLS = ["il", "plaka", "bolge", "degisken", "urun", "mevsim", "donem", "n_yil", "n_hucre", "egim_10yil",
              "ci_alt", "ci_ust", "birim", "p_mk", "p_mk_kontrol", "p_ttest", "belirsiz", "anlamli_fdr",
              "yil_sayisi_gereken", "kaynak_uyumu"]
# L4_iliski/ciftler.csv sütunları (docs/sozlesmeler.md 2.3). İl, bölge ve Türkiye satırları aynı dosyada.
CIFTLER_COLS = ["cift_no", "cift", "degisken_1", "degisken_2", "seri", "gecikme_ay", "beklenen_yon", "bolge_turu",
                "bolge_kodu", "bolge_adi", "hucre_sayisi", "donem", "n", "r", "r1_1", "r1_2", "etkin_n", "p", "p_fdr",
                "anlamli", "etiket", "not", "urun_surumu", "veri_seti_doi", "lisans", "kademe", "dogrulanmadi",
                "doi_1", "doi_2"]
# L3_ozet il/bölge CSV sütunları (docs/sozlesmeler.md 2.2; stats/l3.py L3_COLS ile aynı sıra).
L3_COLS = ["bolge_kodu", "bolge_anahtari", "bolge_adi", "duzey", "ust_bolge", "mevsim", "hucre_sayisi",
           "sen_egimi", "ga_alt", "ga_ust", "p_mk", "p_fdr", "anlamli", "etkin_n", "gereken_yil", "mk_yedek",
           "anlamli_hucre_orani", "anlamli_artan_orani", "anlamli_azalan_orani", "medyan_hucre_egimi",
           "birim", "egim_birimi", "donem_baslangic", "donem_bitis", "trend_uyarisi", "not",
           "kademe", "dogrulanmadi", "urun_surumu", "veri_seti_doi", "lisans", "doi"]
# Ekranın her kaynakta (L3, sentetik, veri tabanı) bulduğu ek sütunlar: uyarı rozetleri bunlardan çıkar.
EXTRA_COLS = ["p_fdr", "anlamli", "etkin_n", "trend_uyarisi", "dogrulanmadi", "kademe", "not"]
TEXT_COLS = ("trend_uyarisi", "dogrulanmadi", "not", "kaynak_uyumu")
SEASONS = {"yillik": "Yıllık", "kis": "Kış", "ilkbahar": "İlkbahar", "yaz": "Yaz", "sonbahar": "Sonbahar"}
ALPHA_FDR = 0.10

# Kademe 1 değişkenleri: (değişken, L1 ürün kodları [ana ürün ilk], birim). data/export.py KADEME_1 ile aynı.
TIER1 = [
    ("sicaklik_2m", ["MERRA2", "GLDAS"], "°C"),
    ("yagis", ["GPM", "GLDAS", "MERRA2"], "mm"),
    ("toprak_nemi", ["GLDAS"], "kg/m²"),
    ("kar_ortusu", ["MOD10CM"], "%"),
    ("kar_su_esdegeri", ["GLDAS"], "mm"),
    ("ndvi", ["MOD13C2"], ""),
    ("toplam_su_depolama", ["GRACE"], "cm"),
]
# (değişken, L1 kodu) → NASA kısa adı (data/catalog.yaml short_name; atıf ve DOI için)
NASA_SHORT = {("sicaklik_2m", "MERRA2"): "M2TMNXSLV", ("yagis", "MERRA2"): "M2TMNXFLX", ("yagis", "GPM"): "GPM_3IMERGM",
              ("kar_ortusu", "MOD10CM"): "MOD10CM", ("ndvi", "MOD13C2"): "MOD13C2",
              ("toplam_su_depolama", "GRACE"): "TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4"}
for _v, _prods, _ in TIER1:
    if "GLDAS" in _prods:
        NASA_SHORT[(_v, "GLDAS")] = "GLDAS_NOAH025_M"
# Eski sürüm (veri tabanındaki eski satırlar): NASA kısa adı → L1 kodu
FILE_CODE = {"M2TMNXSLV": "MERRA2", "M2TMNXFLX": "MERRA2", "GLDAS_NOAH025_M": "GLDAS", "GPM_3IMERGM": "GPM",
             "MOD10CM": "MOD10CM", "MOD13C2": "MOD13C2", "TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4": "GRACE"}
PAIRS = [  # (no, d1, d2, seri, gecikmeler, beklenen yön, mekanizma, kademe) — sözleşme 2.3
    (1, "sicaklik_2m", "kar_ortusu", "kis_DJF", [0], "-", "Sıcak kışta kar azalır", 1),
    (2, "yagis", "toprak_nemi", "mevsim_anomali", [0], "+", "Yağış toprağı besler", 1),
    (3, "toprak_nemi", "ndvi", "aylik_anomali_nis_eyl", [1, 2], "+", "Bitki nemli toprağa gecikmeyle tepki verir", 1),
    (4, "yagis", "toplam_su_depolama", "yillik", [0], "+", "Yağış depolamayı doldurur", 1),
    (5, "sicaklik_2m", "buharlasma", "yaz_JJA", [0], "+", "Isınma buharlaşmayı artırır (su yeterliyse)", 2),
    (6, "sicaklik_2m", "yuzey_sicakligi_gunduz", "aylik_anomali", [0], "+",
     "Aynı olgunun iki ölçümü (kalite kontrolü)", 2),
]
# Çift dizgesindeki ürün kodları (L1 dosya adlarıyla aynı)
PAIR_PRODUCTS = {1: ("MERRA2", "MOD10CM"), 2: ("GPM", "GLDAS"), 3: ("GLDAS", "MOD13C2"), 4: ("GPM", "GRACE"),
                 5: ("MERRA2", "GLDAS"), 6: ("MERRA2", "MOD11C3")}
REGION_ONLY_PAIRS = {4}  # GRACE çözünürlüğü kaba: il satırı yok, yalnız 7 bölge + turkiye
CONTROL_LABELS = {
    "beklenen_yonde": ("Beklenen yönde", "ok"),
    "ters_yonde": ("Ters yönde · incelenmeli", "bad"),
    "anlamsiz": ("Anlamlı ilişki yok", "info"),
}


# ------------------------------------------------------------------ yardımcılar
def norm_name(s: str) -> str:
    """İl adlarını karşılaştırmak için: Türkçe harfleri sadeleştirir, küçük harfe çevirir."""
    s = str(s).replace("ı", "i").replace("İ", "i").replace("I", "i")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


@lru_cache(maxsize=1)
def provinces_geojson() -> dict:
    """Natural Earth tabanlı il sınırları (data/boundaries/iller.geojson)."""
    return json.loads((BOUNDARIES / "iller.geojson").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def regions_map() -> dict:
    """{bölge_anahtarı: {"ad": ..., "iller": [...]}} — data/boundaries/bolgeler.yaml."""
    return yaml.safe_load((BOUNDARIES / "bolgeler.yaml").read_text(encoding="utf-8"))


def _coords(geom: dict):
    """Bir (Multi)Polygon geometrisinin tüm köşe noktaları."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        for ring in poly:
            yield from ring


@lru_cache(maxsize=1)
def provinces() -> pd.DataFrame:
    """İl listesi: ad, plaka, bölge anahtarı, yaklaşık merkez ve kaba hücre sayısı tahmini."""
    by_name = {norm_name(il): key for key, v in regions_map().items() for il in v["iller"]}
    rows = []
    for f in provinces_geojson()["features"]:
        pts = np.array(list(_coords(f["geometry"])))
        lon0, lat0 = pts.min(axis=0)
        lon1, lat1 = pts.max(axis=0)
        rows.append({
            "il": f["properties"]["ad"], "plaka": int(f["properties"]["plaka"]),
            "bolge": by_name.get(norm_name(f["properties"]["ad"]), ""),
            "lat": float(pts[:, 1].mean()), "lon": float(pts[:, 0].mean()),
            "bbox_hucre": max(1, int((lon1 - lon0) * (lat1 - lat0) / 0.0625 * 0.55)),
        })
    return pd.DataFrame(rows).sort_values("plaka").reset_index(drop=True)


def bh_fdr(p: np.ndarray, alpha: float = ALPHA_FDR) -> np.ndarray:
    """Benjamini-Hochberg: FDR düzeltmesinden sonra anlamlı kalanlar için True (NaN'lar False)."""
    p = np.asarray(p, dtype=float)
    out = np.zeros(p.shape, dtype=bool)
    ok = ~np.isnan(p)
    m = int(ok.sum())
    if m == 0:
        return out
    order = np.argsort(p[ok])
    ranked = p[ok][order]
    passed = ranked <= alpha * np.arange(1, m + 1) / m
    if passed.any():
        k = np.max(np.nonzero(passed)[0])
        idx = np.nonzero(ok)[0][order[: k + 1]]
        out[idx] = True
    return out


# ------------------------------------------------------------------ sentetik yer tutucu
def _slope_pattern(var: str, season: str, lat: float, lon: float) -> tuple[float, float]:
    """SENTETİK: (ortalama eğim, gürültü ölçeği). Yalnızca ekranı denemek için; gerçek sonuç değildir."""
    east = (lon - 35.0) / 10.0
    if var == "sicaklik_2m":
        return 0.38 + 0.12 * east + {"yaz": 0.18, "kis": -0.05}.get(season, 0.0), 0.16
    if var == "yagis":
        scale = 1.0 if season == "yillik" else 0.35
        return scale * (-12.0 - 8.0 * east + 9.0 * (lat - 39.0)), scale * 18.0
    if var == "toprak_nemi":
        return -0.9 - 0.5 * east, 0.9
    if var in ("kar_ortusu", "kar_su_esdegeri"):
        if season in ("yaz", "sonbahar"):
            return 0.0, 0.2
        k = 1.6 if var == "kar_ortusu" else 2.2
        return -k * max(0.1, 1.0 + 1.3 * east), 1.4
    if var == "ndvi":
        return 0.006 - 0.003 * east, 0.006
    if var == "toplam_su_depolama":
        return -1.3 - (2.4 if 36.5 < lat < 39.5 and 31.0 < lon < 35.5 else 0.0), 0.9
    return 0.0, 1.0


@lru_cache(maxsize=1)
def synthetic_tables(seed: int = 2026) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """SENTETİK YER TUTUCU il, bölge ve ilişki tabloları (sütunlar gerçek dosyalarla aynı).

    Sayılar gerçek analiz sonucu değildir. FDR, belirsizlik ve kaynak uyumu sütunları yine de
    belgedeki kurallarla hesaplanır ki ekrandaki mantık gerçek veriyle aynı çalışsın.
    """
    rng = np.random.default_rng(seed)
    il = provinces()
    reg = regions_map()
    units = {"sicaklik_2m": "°C", "yagis": "mm", "toprak_nemi": "kg/m²", "kar_ortusu": "%",
             "kar_su_esdegeri": "mm", "ndvi": "", "toplam_su_depolama": "cm"}

    def rows_for(places: pd.DataFrame, key: str) -> pd.DataFrame:
        rows = []
        for var, products, _ in TIER1:
            for season in SEASONS:
                if var == "toplam_su_depolama" and season != "yillik":
                    continue
                grace = var == "toplam_su_depolama"
                n = 22 if grace else (24 if season == "kis" else 25)
                donem = "2002-2025" if grace else "2001-2025"
                for _, pl in places.iterrows():
                    mu, sd = _slope_pattern(var, season, pl["lat"], pl["lon"])
                    base = mu + rng.normal(0, sd * 0.55)
                    for j, prod in enumerate(products):
                        egim = base + (rng.normal(0, sd * 0.25) if j else 0.0)
                        hw = abs(sd) * (0.9 + 0.4 * rng.random()) * (0.6 if key == "bolge" else 1.0)
                        z = egim / (hw / 1.96) if hw else 0.0
                        p = float(2 * stats.norm.sf(abs(z)))
                        pk = float(min(1.0, p * math.exp(rng.normal(0, 0.35))))
                        pt = float(min(1.0, p * math.exp(rng.normal(-0.2, 0.3))))
                        need = np.nan
                        if p >= 0.05:
                            ratio = hw / max(abs(egim), 1e-9)
                            need = float(min(100, max(1, round(n * ratio ** (2 / 3) - n))))
                        unit = units[var]
                        rows.append({
                            key: pl[key], **({"plaka": int(pl["plaka"]), "bolge": pl["bolge"]} if key == "il" else {}),
                            "degisken": var, "urun": prod, "mevsim": season, "donem": donem, "n_yil": n,
                            "n_hucre": int(pl["bbox_hucre"]), "egim_10yil": round(egim, 4),
                            "ci_alt": round(egim - hw * 1.08, 4), "ci_ust": round(egim + hw, 4),
                            "birim": f"{unit}/10 yil".strip() if unit else "1/10 yil",
                            "p_mk": round(p, 4), "p_mk_kontrol": round(pk, 4), "p_ttest": round(pt, 4),
                            "belirsiz": int((p < 0.05) != (pk < 0.05)), "anlamli_fdr": 0,
                            "yil_sayisi_gereken": need, "kaynak_uyumu": "",
                        })
        df = pd.DataFrame(rows)
        # FDR: her değişken × ürün × mevsim haritası için ayrı (il tablosunda 81 il üzerinde)
        for _, idx in df.groupby(["degisken", "urun", "mevsim"]).groups.items():
            p = df.loc[idx, "p_mk"].to_numpy()
            df.loc[idx, "anlamli_fdr"] = (bh_fdr(p) & (p < 0.05)).astype(int)
        # Kaynak uyumu: m kaynaktan kaçı ana kaynakla aynı yönde anlamlı
        for (place, var, season), g in df.groupby([key, "degisken", "mevsim"]):
            if g["urun"].nunique() < 2:
                continue
            main = g.iloc[0]
            sign = np.sign(main["egim_10yil"])
            k = int(((np.sign(g["egim_10yil"]) == sign) & (g["p_mk"] < 0.05)).sum()) if main["p_mk"] < 0.05 else 0
            df.loc[g.index, "kaynak_uyumu"] = f"{k}/{len(g)}"
        return df

    il_df = rows_for(il, "il")
    il_df = il_df[[c for c in TREND_COLS]]

    bolge_places = il.groupby("bolge")[["lat", "lon", "bbox_hucre"]].agg({"lat": "mean", "lon": "mean",
                                                                          "bbox_hucre": "sum"}).reset_index()
    bolge_places = bolge_places[bolge_places["bolge"].isin(reg)]
    tr = pd.DataFrame([{"bolge": "turkiye", "lat": il["lat"].mean(), "lon": il["lon"].mean(),
                        "bbox_hucre": 1300}])
    bolge_df = rows_for(pd.concat([bolge_places, tr], ignore_index=True), "bolge")
    bolge_df = bolge_df[["bolge"] + [c for c in TREND_COLS if c not in ("il", "plaka", "bolge")]]

    rel_df = synthetic_pairs(il, bolge_places, rng)
    return il_df, bolge_df, rel_df


def bh_qvalues(p) -> np.ndarray:
    """Benjamini-Hochberg düzeltilmiş p değerleri (q). NaN'lar NaN kalır."""
    p = np.asarray(p, dtype=float)
    q = np.full(p.shape, np.nan)
    ok = ~np.isnan(p)
    m = int(ok.sum())
    if m:
        order = np.argsort(p[ok])
        ranked = p[ok][order] * m / np.arange(1, m + 1)
        ranked = np.minimum.accumulate(ranked[::-1])[::-1]
        out = np.empty(m)
        out[order] = np.minimum(ranked, 1.0)
        q[ok] = out
    return q


def synthetic_pairs(il: pd.DataFrame, regions: pd.DataFrame, rng) -> pd.DataFrame:
    """SENTETİK YER TUTUCU `ciftler.csv` (sütunlar sözleşme 2.3 ile aynı; sayılar gerçek değil).

    Çift 4 yalnız bölge + Türkiye; çift 1'de kar olmayan iller "kapsamda hücre yok" satırıdır.
    """
    reg_names = {k: v["ad"] for k, v in regions_map().items()}
    places = ([("il", str(int(r.plaka)), r.il, r.lat, r.lon, int(r.bbox_hucre)) for r in il.itertuples()]
              + [("bolge", r.bolge, reg_names.get(r.bolge, r.bolge), r.lat, r.lon, int(r.bbox_hucre))
                 for r in regions.itertuples()]
              + [("turkiye", "turkiye", "Türkiye", il["lat"].mean(), il["lon"].mean(), 1300)])
    n_of = {"kis_DJF": 24, "mevsim_anomali": 100, "aylik_anomali_nis_eyl": 150, "yillik": 22, "yaz_JJA": 25,
            "aylik_anomali": 300}
    rows = []
    for no, d1, d2, seri, lags, sign, _, kademe in PAIRS:
        u1, u2 = PAIR_PRODUCTS[no]
        for lag in lags:
            for kind, code, name, lat, lon, cells in places:
                if no in REGION_ONLY_PAIRS and kind == "il":
                    continue
                base = {"cift_no": no, "cift": f"{d1}__{u1}~{d2}__{u2}", "degisken_1": d1, "degisken_2": d2,
                        "seri": seri, "gecikme_ay": lag, "beklenen_yon": sign, "bolge_turu": kind, "bolge_kodu": code,
                        "bolge_adi": name, "urun_surumu": "YER TUTUCU", "veri_seti_doi": VERI_SETI_DOI,
                        "lisans": LICENSE, "kademe": kademe, "dogrulanmadi": "evet" if kademe == 2 else "",
                        "doi_1": f"YER TUTUCU ({u1})", "doi_2": f"YER TUTUCU ({u2})", "not": ""}
                east = (lon - 35.0) / 10.0
                if no == 1 and kind == "il" and lon < 33.5 and lat < 39.5:
                    rows.append({**base, "hucre_sayisi": 0, "not": "kapsamda hücre yok (kış kar örtüsü < %10)"})
                    continue
                r0 = {1: -0.25 - 0.3 * east, 2: 0.55, 3: 0.35 - 0.08 * lag, 4: 0.45,
                      5: 0.35 - 0.6 * max(0.0, 38.5 - lat), 6: 0.88}[no]
                if no == 3 and name in ("Konya", "Şanlıurfa", "Aksaray", "Karaman"):
                    r0 = -0.45  # sulama gibi insan etkisini canlandıran örnek (SENTETİK)
                r = float(np.clip(r0 + rng.normal(0, 0.18 if kind == "il" else 0.08), -0.97, 0.97))
                n = n_of[seri]
                r1a, r1b = rng.uniform(-0.1, 0.5, 2)
                n_eff = max(5.0, n * (1 - r1a * r1b) / (1 + r1a * r1b))
                t = r * math.sqrt((n_eff - 2) / max(1e-9, 1 - r * r))
                p = float(2 * stats.t.sf(abs(t), df=n_eff - 2))
                rows.append({**base, "hucre_sayisi": cells, "donem": "2002-2023" if no == 4 else "2001-2025",
                             "n": n, "r": round(r, 4), "r1_1": round(r1a, 4), "r1_2": round(r1b, 4),
                             "etkin_n": round(n_eff, 2), "p": p})
    df = pd.DataFrame(rows)
    df["p_fdr"] = np.nan
    for _, idx in df[df["bolge_turu"] == "il"].groupby(["cift_no", "gecikme_ay"]).groups.items():
        df.loc[idx, "p_fdr"] = bh_qvalues(df.loc[idx, "p"])
    sig = np.where(df["bolge_turu"] == "il", df["p_fdr"] <= ALPHA_FDR, df["p"] < 0.05)
    df["anlamli"] = np.where(df["r"].isna(), np.nan, sig.astype(float))
    df["etiket"] = [control_label(r, s, a) if pd.notna(r) else ""
                    for r, s, a in zip(df["r"], df["beklenen_yon"], df["anlamli"])]
    df.loc[(df["etiket"] == "ters_yonde") & (df["not"] == ""), "not"] = "olası neden: veri sorunu ya da insan etkisi"
    df.loc[(df["cift_no"] == 5) & (df["etiket"] != "beklenen_yonde") & (df["not"] == ""),
           "not"] = "kurak bölgede buharlaşmayı sıcaklık değil su sınırlar"
    return df[CIFTLER_COLS]


def norm_sign(x) -> str:
    """Beklenen yön: '+' / '-' (sözleşme), '−' (Unicode eksi) ve eski 'pozitif'/'negatif' kabul edilir."""
    x = str(x).strip().lower()
    return "-" if x in ("-", "−", "–", "negatif") else "+"


def control_label(r: float, expected: str, significant: int) -> str:
    """Fizik kontrolü etiketi: beklenen_yonde / ters_yonde / anlamsiz."""
    if not significant or pd.isna(significant):
        return "anlamsiz"
    same = (r > 0) == (norm_sign(expected) == "+")
    return "beklenen_yonde" if same else "ters_yonde"


# ------------------------------------------------------------------ gerçek dosyalar
def find_file(layer: str, name: str) -> Path | None:
    """Paket köklerinde (`package_dirs`) `<katman>/<ad>` dosyasını arar."""
    for base in package_dirs():
        p = base / layer / name
        if p.exists():
            return p
    return None


def _is_trend_file(p: Path) -> bool:
    """`<degisken>__<urun>__{il,bolge}.csv` mi? (kaynak uyumu ve ICINDEKILER hariç)"""
    parts = p.stem.split("__")
    return len(parts) == 3 and parts[1] != "kaynak_uyumu" and parts[2] in ("il", "bolge")


def l3_dir() -> Path | None:
    """İçinde en az bir il trend dosyası olan ilk `L3_ozet/` klasörü."""
    for base in package_dirs():
        d = base / "L3_ozet"
        if d.is_dir() and any(_is_trend_file(p) and p.stem.endswith("__il") for p in d.glob("*.csv")):
            return d
    return None


def _read_l3_csv(p: Path) -> pd.DataFrame:
    """L3 CSV'si: BOM'lu UTF-8, kodlar ve metin alanları metin olarak (sözleşme 2.2)."""
    return pd.read_csv(p, encoding="utf-8-sig", dtype={c: str for c in ("bolge_kodu", "bolge_anahtari", "ust_bolge",
                                                                        "trend_uyarisi", "not", "dogrulanmadi")})


def _agreement(d: Path, level: str) -> pd.DataFrame:
    """`<degisken>__kaynak_uyumu__<düzey>.csv` → [degisken, bolge_anahtari, mevsim, kaynak_uyumu = "k/m"]."""
    parts = []
    for p in sorted(d.glob(f"*__kaynak_uyumu__{level}.csv")):
        df = _read_l3_csv(p)
        if df.empty or not {"bolge_anahtari", "mevsim", "k", "m"} <= set(df.columns):
            continue
        k, m = pd.to_numeric(df["k"], errors="coerce"), pd.to_numeric(df["m"], errors="coerce")
        ku = [f"{int(a)}/{int(b)}" if pd.notna(a) and pd.notna(b) else "" for a, b in zip(k, m)]
        parts.append(pd.DataFrame({"degisken": p.stem.split("__")[0], "bolge_anahtari": df["bolge_anahtari"],
                                   "mevsim": df["mevsim"], "kaynak_uyumu": ku}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=["degisken", "bolge_anahtari", "mevsim", "kaynak_uyumu"])


def from_l3(df: pd.DataFrame, level: str, agreement: pd.DataFrame | None = None) -> pd.DataFrame:
    """L3 satırlarına ekranın kısa adlarını ekler; L3 sütunlarının hepsi olduğu gibi kalır.

    - `anlamli` 1 / 0 / -1 (hesaplanamadı) korunur; `anlamli_fdr` = (anlamli == 1).
    - `yil_sayisi_gereken`: Weatherhead `gereken_yil` ile serinin uzunluğu arasındaki fark (≥ 1 ise).
    - `belirsiz` L3'te yoktur (tek test motoru); 0 yazılır.
    """
    out = df.copy()
    for c in L3_COLS:
        if c not in out:
            out[c] = np.nan
    if level == "il":
        out["il"] = out["bolge_adi"]
        out["plaka"] = pd.to_numeric(out["bolge_kodu"], errors="coerce").astype("Int64")
        out["bolge"] = out["ust_bolge"]
        out = out[out["plaka"].notna()]
    else:
        out["bolge"] = out["bolge_anahtari"].fillna(out["bolge_kodu"])
    a, b = pd.to_numeric(out["donem_baslangic"], errors="coerce"), pd.to_numeric(out["donem_bitis"], errors="coerce")
    out["donem"] = [f"{int(x)}-{int(y)}" if pd.notna(x) and pd.notna(y) else "" for x, y in zip(a, b)]
    out["n_yil"] = np.nan  # geçerli yıl sayısı L3'te yok; uydurulmaz
    out["n_hucre"] = out["hucre_sayisi"]
    out["egim_10yil"], out["ci_alt"], out["ci_ust"] = out["sen_egimi"], out["ga_alt"], out["ga_ust"]
    out["p_mk_kontrol"], out["p_ttest"], out["belirsiz"] = np.nan, np.nan, 0
    out["anlamli"] = pd.to_numeric(out["anlamli"], errors="coerce").fillna(-1).astype(int)
    out["anlamli_fdr"] = (out["anlamli"] == 1).astype(int)
    extra = pd.to_numeric(out["gereken_yil"], errors="coerce") - (b - a + 1)
    out["yil_sayisi_gereken"] = extra.where(extra >= 1).round()
    out = out.drop(columns=["kaynak_uyumu"], errors="ignore")
    if agreement is not None and len(agreement):
        out = out.merge(agreement, on=["degisken", "bolge_anahtari", "mevsim"], how="left")
    else:
        out["kaynak_uyumu"] = ""
    return ensure_trend_cols(out)


def ensure_trend_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Her kaynaktan gelen trend tablosunda uyarı sütunları bulunsun; ürün adları L1 kodu olsun."""
    df = df.copy()
    if "urun" in df:
        df["urun"] = df["urun"].map(lambda u: FILE_CODE.get(u, u))
    fallback = df["anlamli_fdr"] if "anlamli_fdr" in df else -1
    if "anlamli" in df:
        df["anlamli"] = pd.to_numeric(df["anlamli"], errors="coerce").fillna(fallback).astype(int)
    else:
        df["anlamli"] = pd.Series(fallback, index=df.index).astype(int)
    for c in EXTRA_COLS:
        if c not in df:
            df[c] = np.nan
    for c in TEXT_COLS:
        df[c] = df[c].astype(object).where(df[c].notna(), "").astype(str).str.strip() if c in df else ""
    df["dogrulanmadi"] = df["dogrulanmadi"].str.lower()
    return df.reset_index(drop=True)


def read_l3(d: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`L3_ozet/` klasöründeki bütün trend dosyalarını il ve bölge tablolarına toplar.

    Değişken ve ürün dosya adından gelir. Türkiye satırı (`duzey = "ulke"`) bölge tablosundadır.
    """
    parts: dict[str, list[pd.DataFrame]] = {"il": [], "bolge": []}
    for p in sorted(d.glob("*.csv")):
        if not _is_trend_file(p):
            continue
        var, prod, level = p.stem.split("__")
        try:
            df = _read_l3_csv(p)
        except pd.errors.EmptyDataError:
            continue
        if df.empty:
            continue
        parts[level].append(df.assign(degisken=var, urun=prod))
    if not parts["il"]:
        raise FileNotFoundError(f"{d} içinde il trend dosyası yok")
    il = pd.concat(parts["il"], ignore_index=True)
    bolge = pd.concat(parts["bolge"], ignore_index=True) if parts["bolge"] else il.iloc[0:0].copy()
    return from_l3(il, "il", _agreement(d, "il")), from_l3(bolge, "bolge", _agreement(d, "bolge"))


def has_placeholder_rows(df: pd.DataFrame) -> bool:
    """Gerçek klasöre yanlışlıkla yer tutucu dosya kopyalandıysa yakalar (`urun_surumu` "YER TUTUCU")."""
    return "urun_surumu" in df and df["urun_surumu"].astype(str).str.contains("YER TUTUCU", case=False).any()


# ------------------------------------------------------------------ bulgu karnesi ve büyüklük testleri
GUVEN = ("YÜKSEK", "ORTA", "DÜŞÜK", "YOK")
GUVEN_CLASS = {"YÜKSEK": "ok", "ORTA": "warn", "DÜŞÜK": "bad", "YOK": "info"}
KARNE_STATES = {"geçti": "ok", "kaldı": "bad", "uygulanamaz": "info"}
TREND_CHECKS = [("a_kaynak_uyumu", "a_sayi", "Başka NASA ürünleri aynı sonucu veriyor mu?"),
                ("b_karistirma", "b_p_perm", "Yıllar karıştırılınca trend kayboluyor mu?"),
                ("c_donem", "c_sayi", "İlk ya da son 3 yıl çıkarılınca sonuç değişiyor mu?"),
                ("d_esik", "d_sayi", "Daha sıkı eşikte (α = 0,05) de anlamlı mı?"),
                ("e_yeterlilik", "e_sayi", "Yıl sayısı bu büyüklükte trend için yeterli mi?")]
PAIR_CHECKS = [("a_kaynak_uyumu", "a_sayi", "Başka NASA ürünleriyle aynı etiket çıkıyor mu?"),
               ("b_karistirma", "b_p_perm", "Yıllar karıştırılınca ilişki kayboluyor mu?"),
               ("c_trend", "c_sayi", "Ortak trend çıkarılınca ilişki duruyor mu?"),
               ("d_gecikme", "d_sayi", "±1 ay kaydırınca yön korunuyor mu?"),
               ("e_esik", "e_sayi", "Daha sıkı eşikte (α = 0,05) etiket aynı mı?")]


def _pkg_file(*parts: str) -> Path | None:
    """Paket köklerinde (`package_dirs`) bir dosyanın ilk bulunduğu yer."""
    for base in package_dirs():
        p = base.joinpath(*parts)
        if p.exists():
            return p
    return None


def _read_text_csv(p: Path) -> pd.DataFrame:
    """BOM'lu UTF-8 CSV; kodlar metin, metin alanlarındaki boşluklar boş metin."""
    df = pd.read_csv(p, encoding="utf-8-sig", dtype={"bolge_kodu": str})
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].fillna("")
    return df


def load_karne() -> dict:
    """Bulgu karnesi (sözleşme 2.4): {"trend_il", "trend_bolge", "iliski": DataFrame | None}."""
    out = {}
    for key, name in (("trend_il", "trend_karne_il.csv"), ("trend_bolge", "trend_karne_bolge.csv"),
                      ("iliski", "iliski_karne.csv")):
        p = _pkg_file("karne", name)
        out[key] = _read_text_csv(p) if p else None
    return out


def trend_confidence(karne: pd.DataFrame | None, var: str, prod: str, season: str) -> pd.DataFrame:
    """Bir değişken × ürün × mevsim için karne satırları (bolge_kodu → guven, gerekce, kontroller)."""
    if karne is None or karne.empty:
        return pd.DataFrame()
    k = karne[(karne["degisken"] == var) & (karne["urun"] == prod) & (karne["mevsim"] == season)]
    return k.drop_duplicates("bolge_kodu").set_index("bolge_kodu")


def pair_confidence(karne: pd.DataFrame | None, no: int, lag: int) -> pd.DataFrame:
    """Bir çift × gecikme için karne satırları (bolge_kodu → guven, ...)."""
    if karne is None or karne.empty:
        return pd.DataFrame()
    k = karne[(karne["cift_no"] == no) & (karne["gecikme_ay"] == lag)]
    return k.drop_duplicates("bolge_kodu").set_index("bolge_kodu")


def load_magnitude() -> dict:
    """Büyüklük testleri (sözleşme 2.5): {"ozet", "cc_il", "cc_bolge", "butce_bolge", "kar_il", "kar_bolge"}."""
    names = {"ozet": "ozet.csv", "cc_il": "cc__il.csv", "cc_bolge": "cc__bolge.csv", "butce_bolge": "butce__bolge.csv",
             "kar_il": "kar_cizgisi__il.csv", "kar_bolge": "kar_cizgisi__bolge.csv"}
    out = {}
    for key, name in names.items():
        p = _pkg_file("L4_iliski", "buyukluk", name)
        out[key] = _read_text_csv(p) if p else None
    return out


def read_pairs(path) -> pd.DataFrame:
    """`ciftler.csv` okur: BOM'lu UTF-8, bölge kodu metin; beklenen yön '+'/'-' biçimine getirilir."""
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"bolge_kodu": str, "etiket": str, "not": str,
                                                         "dogrulanmadi": str})
    for c in CIFTLER_COLS:
        if c not in df:
            df[c] = np.nan
    df["beklenen_yon"] = df["beklenen_yon"].map(norm_sign)
    for c in ("etiket", "not", "dogrulanmadi"):
        df[c] = df[c].fillna("")
    return df[CIFTLER_COLS]


def pair_rows(df: pd.DataFrame, level: str = "il") -> pd.DataFrame:
    """Bir düzeyin satırları; il satırlarına haritada kullanılan tamsayı `plaka` sütunu eklenir."""
    d = df[df["bolge_turu"] == level].copy()
    if level == "il":
        d["plaka"] = pd.to_numeric(d["bolge_kodu"], errors="coerce").astype("Int64")
    return d


def load_tables() -> dict:
    """Trend ve ilişki tablolarını döndürür.

    Dönüş: {"il", "bolge", "iliski": DataFrame, "yer_tutucu": bool, "yer_tutucu_tablolar": [ad],
    "kaynak": {ad: yol ya da None}}.
    - "il", "bolge": `L3_ozet/<degisken>__<urun>__{il,bolge}.csv` (sözleşme 2.2), `read_l3` ile.
    - "iliski": `L4_iliski/ciftler.csv` (il + bölge + Türkiye satırları, sözleşme 2.3).
    Bir katman bulunamazsa o tablo sentetik yer tutucudur ve `yer_tutucu` True olur.
    """
    syn = synthetic_tables
    out, src, missing = {}, {}, []
    d = l3_dir()
    if d is not None:
        try:
            out["il"], out["bolge"] = read_l3(d)
            src["trend_iller.csv"] = src["trend_bolgeler.csv"] = d
        except Exception:  # noqa: BLE001 — bozuk paket: yer tutucuya düş, ekranda işaretlenir
            d = None
    if d is None:
        out["il"], out["bolge"] = ensure_trend_cols(syn()[0]), ensure_trend_cols(syn()[1])
        src["trend_iller.csv"] = src["trend_bolgeler.csv"] = None
        missing += ["trend_iller.csv", "trend_bolgeler.csv"]
    p = find_file("L4_iliski", "ciftler.csv")
    if p is not None:
        out["iliski"], src["ciftler.csv"] = read_pairs(p), p
    else:
        out["iliski"], src["ciftler.csv"] = syn()[2].copy(), None
        missing.append("ciftler.csv")
    for name, key in (("trend_iller.csv", "il"), ("trend_bolgeler.csv", "bolge"), ("ciftler.csv", "iliski")):
        if name not in missing and has_placeholder_rows(out[key]):
            missing.append(name)
    return {**out, "yer_tutucu": bool(missing), "yer_tutucu_tablolar": missing, "kaynak": src}


def inventory() -> list[dict]:
    """Katman klasörlerindeki gerçek dosyalar: [{katman, dosya, yol, boyut_mb}]."""
    seen, rows = set(), []
    for base in package_dirs():
        for layer, *_ in LAYERS:
            d = base / layer
            if not d.is_dir():
                continue
            for p in sorted(d.iterdir()):
                if p.is_file() and p.name not in seen and p.suffix in (".nc", ".csv"):
                    seen.add(p.name)
                    rows.append({"katman": layer, "dosya": p.name, "yol": p,
                                 "boyut_mb": round(p.stat().st_size / 1e6, 2)})
    return rows


# ------------------------------------------------------------------ meta bilgiler
@lru_cache(maxsize=1)
def variable_cards() -> dict:
    """kb/degiskenler.yaml → {ad: kart}; yoksa boş sözlük."""
    try:
        return {c["ad"]: c for c in yaml.safe_load(VAR_CARDS.read_text(encoding="utf-8"))}
    except Exception:  # noqa: BLE001
        return {}


@lru_cache(maxsize=1)
def nasa_sources() -> list[dict]:
    """Kademe 1 ürünlerinin NASA atıf bilgisi (data/catalog.yaml): short_name, version, daac, doi."""
    wanted = set(NASA_SHORT.values()) | {"SRTMGL30"}
    try:
        cat = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))["urunler"]
    except Exception:  # noqa: BLE001
        return []
    return [{"short_name": v["short_name"], "version": str(v.get("version", "")), "daac": v.get("daac", ""),
             "doi": v.get("doi")} for v in cat.values() if v.get("short_name") in wanted]


def citation(version: str = VERSION, doi: str = VERI_SETI_DOI, year: int = 2026) -> dict:
    """Veri seti atıf metni: {"apa": ..., "bibtex": ...} (ekip belgesindeki şablon)."""
    doi_url = f"https://doi.org/{doi}" if doi and not doi.startswith("(") else "https://doi.org/…"
    title = "Trend Dedektifi: NASA uydu ve model verisinden Türkiye için analize hazır iklim trendi veri seti"
    apa = f"Ekip üyeleri ({year}). {title} (Sürüm {version}) [Veri seti]. Zenodo. {doi_url}"
    bib = (f"@dataset{{trend_dedektifi_{year}_{version.replace('.', '_')},\n"
           f"  author    = {{{{Trend Dedektifi Ekibi}}}},\n"
           f"  title     = {{{title}}},\n"
           f"  year      = {{{year}}},\n"
           f"  version   = {{{version}}},\n"
           f"  publisher = {{Zenodo}},\n"
           + (f"  doi       = {{{doi}}},\n" if doi and not doi.startswith("(") else "")
           + f"  note      = {{Lisans: {LICENSE}}}\n}}")
    return {"apa": apa, "bibtex": bib}


# ------------------------------------------------------------------ paketleme
def filter_trends(df: pd.DataFrame, variables=None, seasons=None, places=None, key: str = "il") -> pd.DataFrame:
    """Trend tablosunu değişken, mevsim ve yer seçimine göre süzer (boş seçim = hepsi)."""
    m = pd.Series(True, index=df.index)
    if variables:
        m &= df["degisken"].isin(variables)
    if seasons:
        m &= df["mevsim"].isin(seasons)
    if places:
        m &= df[key].isin(places)
    return df[m]


L3_README = (
    "  trend_iller.csv     81 il × mevsim: L3_ozet/<degisken>__<urun>__il.csv dosyalarının birleşimi (sözleşme 2.2).\n"
    "                      sen_egimi / ga_alt / ga_ust birimi egim_birimi sütununda; bolge_kodu = iki haneli plaka\n"
    "  trend_bolgeler.csv  7 coğrafi bölge ve Türkiye (duzey = ulke) × mevsim\n"
    "                      kaynak_uyumu = k/m: m üründen k'si aynı yönde anlamlı (L3_ozet/*__kaynak_uyumu__*.csv)\n"
)


def _rel(v) -> str:
    """Manifest için kaynak yolu: repo içindeyse göreli, değilse olduğu gibi."""
    try:
        return Path(v).resolve().relative_to(ROOT).as_posix()
    except (ValueError, TypeError):
        return str(v)


def build_bundle(tables: dict, variables, seasons, provinces_sel, user: dict, include_nc: bool = False,
                 git_commit: str | None = None, extra: list[tuple[Path, str]] | None = None) -> tuple[bytes, str]:
    """Akademisyen için seçime göre hazır veri paketi (zip) üretir. Dönüş: (zip baytları, dosya adı).

    İçerik: süzülmüş trend_iller.csv / trend_bolgeler.csv / ciftler.csv, BENIOKU.txt,
    CITATION.bib, NASA_KAYNAKLARI.csv, manifest.json ve istenirse mevcut L1 NetCDF küpleri.
    CSV kuralı: UTF-8, ondalık ayıracı nokta, boş değer boş hücre.
    """
    ph = tables["yer_tutucu"]
    prefix = "YER_TUTUCU_" if ph else ""
    il_f = filter_trends(tables["il"], variables, seasons, provinces_sel, "il")
    regions_sel = sorted({*il_f["bolge"].unique(), "turkiye"}) if provinces_sel else None
    bolge_f = filter_trends(tables["bolge"], variables, seasons, regions_sel, "bolge")
    rel = tables["iliski"]
    rel_f = rel[(rel["degisken_1"].isin(variables) | rel["degisken_2"].isin(variables)) if variables else
                pd.Series(True, index=rel.index)]
    if provinces_sel:  # seçilen illerin satırları + bağlı oldukları bölgeler + Türkiye
        keep = ((rel_f["bolge_turu"] == "il") & rel_f["bolge_adi"].isin(provinces_sel)) | \
               ((rel_f["bolge_turu"] == "bolge") & rel_f["bolge_kodu"].isin(regions_sel or [])) | \
               (rel_f["bolge_turu"] == "turkiye")
        rel_f = rel_f[keep]

    l3 = "sen_egimi" in il_f.columns and not ph  # gerçek L3: sözleşme 2.2 sütunları aynen
    if l3:
        il_f, bolge_f = (x[["degisken", "urun"] + L3_COLS + ["kaynak_uyumu"]] for x in (il_f, bolge_f))
    else:
        il_f = il_f[[c for c in TREND_COLS if c in il_f.columns]]
        bolge_f = bolge_f[["bolge"] + [c for c in TREND_COLS if c in bolge_f.columns
                                       and c not in ("il", "plaka", "bolge")]]

    cit = citation()
    files_nc = []
    if include_nc and variables:
        files_nc = [r for r in inventory() if r["katman"] == "L1_kup"
                    and r["dosya"].split("__")[0] in variables and r["boyut_mb"] < 300]

    manifest = {
        "veri_seti": "Trend Dedektifi — Türkiye", "surum": VERSION, "doi": VERI_SETI_DOI, "lisans": LICENSE,
        "yer_tutucu": ph, "olusturma_tarihi": date.today().isoformat(),
        "secim": {"degiskenler": list(variables or []) or "hepsi", "mevsimler": list(seasons or []) or "hepsi",
                  "iller": list(provinces_sel or []) or "hepsi"},
        "satir_sayisi": {"trend_iller": len(il_f), "trend_bolgeler": len(bolge_f), "ciftler": len(rel_f)},
        "kaynak_dosyalar": {k: ("SENTETİK YER TUTUCU" if not v else _rel(v)) for k, v in tables["kaynak"].items()},
        "netcdf": [r["dosya"] for r in files_nc], "ek_dosyalar": [a for _, a in extra or []],
        "git_commit": git_commit,
        "kullanici_rolu": user.get("rol"),
    }
    warn = ("UYARI: Bu paketteki sayılar SENTETİK YER TUTUCUDUR, gerçek analiz sonucu değildir. "
            "Makalede kullanmayın; gerçek sürüm yayımlanınca yeniden indirin.\n\n") if ph else ""
    readme = (
        f"{warn}Trend Dedektifi — Türkiye iklim trendi veri seti, sürüm {VERSION} (ön sürüm)\n"
        f"Lisans: {LICENSE}. DOI: {VERI_SETI_DOI}\n\n"
        "Dosyalar\n"
        + (L3_README if l3 else
           "  trend_iller.csv     il bazında trendler (Sen eğimi / 10 yıl, %95 genişletilmiş aralık, Hamed-Rao MK, FDR)\n"
           "  trend_bolgeler.csv  7 coğrafi bölge ve Türkiye\n") +
        "  ciftler.csv         6 değişken çifti; il, bölge ve Türkiye satırları (bolge_turu). Trendi çıkarılmış\n"
        "                      serilerin korelasyonu, etkin_n, p / p_fdr, anlamli, etiket (BOM'lu UTF-8)\n"
        "  NASA_KAYNAKLARI.csv kullanılan NASA ürünleri ve DOI'leri (bunlara da atıf yapın)\n"
        "  manifest.json       seçim, sürüm ve kaynak dosyalar\n\n"
        "CSV kuralı: UTF-8 (BOM'lu), ondalık ayıracı nokta, boş değer boş hücre.\n"
        + ("Anlamlılık: anlamli = 1 ⇔ p_fdr ≤ 0,10 (Benjamini-Hochberg, düzey × mevsim içinde) ve %95 genişletilmiş\n"
           "aralık sıfırı dışlıyor; -1 = hesaplanamadı. trend_uyarisi doluysa sonucu yorumlamadan önce okuyun;\n"
           "dogrulanmadi = evet olan (Kademe 2) satırlar doğrulanmamış üründendir.\n" if l3 else
           "Anlamlılık: p_mk < 0,05 (Hamed-Rao). Harita ve il tablosunda Benjamini-Hochberg, α_FDR = 0,10.\n"
           "belirsiz = 1: ana test ile kontrol testi farklı sonuç veriyor.\n") +
        "kaynak_uyumu = k/m: m kaynaktan k'si ana kaynakla aynı yönde anlamlı (tutarlılık, bağımsız doğrulama değil).\n"
        "İlişkiler için 'neden' değil 'ilişki' ifadesini kullanın.\n\n"
        f"Atıf (APA):\n  {cit['apa']}\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{prefix}trend_iller.csv", il_f.to_csv(index=False).encode("utf-8-sig"))
        z.writestr(f"{prefix}trend_bolgeler.csv", bolge_f.to_csv(index=False).encode("utf-8-sig"))
        z.writestr(f"{prefix}ciftler.csv", rel_f.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"))
        z.writestr("BENIOKU.txt", readme)
        z.writestr("CITATION.bib", cit["bibtex"] + "\n")
        z.writestr("NASA_KAYNAKLARI.csv", pd.DataFrame(nasa_sources()).to_csv(index=False))
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for r in files_nc:
            z.write(r["yol"], f"L1_kup/{r['dosya']}")
        for path, arcname in extra or []:  # bulgu karnesi, büyüklük testleri (paketteki dosyalar aynen)
            z.write(path, arcname)
    name = f"{prefix}trend-dedektifi-turkiye-{VERSION}-paket.zip"
    return buf.getvalue(), name


# ------------------------------------------------------------------ LLM katmanı için yer tutucu paket
PLACEHOLDER_PACKAGE = ROOT / "cache" / "yer_tutucu_paket" / f"trend-dedektifi-turkiye-{VERSION}"
L3_OZET_COLS = ["bolge_kodu", "bolge_adi", "hucre_sayisi", "sen_egimi", "ga_alt", "ga_ust", "p_mk", "p_fdr", "anlamli",
                "etkin_n", "gereken_yil", "anlamli_hucre_orani", "birim", "donem", "seri", "kademe", "dogrulanmadi",
                "urun_surumu", "veri_seti_doi", "lisans", "doi"]


def _l3_ozet(df: pd.DataFrame, level: str, doi: str | None) -> pd.DataFrame:
    """Sentetik trend satırlarını sözleşme 2.2 L3_ozet sütunlarına çevirir (yıllık seri).

    `birim` temel birimdir (ör. "%"); "/10 yıl" ekini LLM katmanı kendisi ekler.
    """
    reg = regions_map()
    out = pd.DataFrame({
        "bolge_kodu": df["plaka"].astype(int).astype(str) if level == "il" else df["bolge"],
        "bolge_adi": df["il"] if level == "il" else df["bolge"].map(
            lambda k: "Türkiye" if k == "turkiye" else reg.get(k, {}).get("ad", k)),
        "hucre_sayisi": df["n_hucre"], "sen_egimi": df["egim_10yil"], "ga_alt": df["ci_alt"], "ga_ust": df["ci_ust"],
        "p_mk": df["p_mk"], "p_fdr": bh_qvalues(df["p_mk"]), "anlamli": df["anlamli_fdr"].astype(int),
        "etkin_n": df["n_yil"].astype(float), "gereken_yil": df["yil_sayisi_gereken"], "anlamli_hucre_orani": np.nan,
        "birim": df["birim"].str.replace("/10 yil", "").str.strip(), "donem": df["donem"], "seri": "yillik_ortalama",
        "kademe": 1, "dogrulanmadi": "", "urun_surumu": "YER TUTUCU", "veri_seti_doi": VERI_SETI_DOI,
        "lisans": LICENSE, "doi": doi or "",
    })
    return out[L3_OZET_COLS]


def write_placeholder_package(dest: Path = PLACEHOLDER_PACKAGE) -> Path:
    """SENTETİK YER TUTUCU analiz paketi yazar (sözleşme 2.2 L3_ozet + 2.3 L4_iliski/ciftler.csv).

    Gerçek paket (`outputs/…`) üretilene kadar LLM katmanının (llm.answer) demoda çalışabilmesi içindir.
    Konum `cache/` altındadır, git'e girmez. Her satırda `urun_surumu = "YER TUTUCU"` yazar.
    """
    il, bolge, rel = synthetic_tables()
    dois = {s["short_name"]: s["doi"] for s in nasa_sources()}
    (dest / "L3_ozet").mkdir(parents=True, exist_ok=True)
    (dest / "L4_iliski").mkdir(parents=True, exist_ok=True)
    for var, products, _ in TIER1:
        for code in products:
            for level, df in (("il", il), ("bolge", bolge)):
                d = df[(df["degisken"] == var) & (df["urun"] == code) & (df["mevsim"] == "yillik")]
                if len(d):
                    _l3_ozet(d, level, dois.get(NASA_SHORT.get((var, code)))).to_csv(
                        dest / "L3_ozet" / f"{var}__{code}__{level}.csv", index=False, encoding="utf-8-sig")
    rel.to_csv(dest / "L4_iliski" / "ciftler.csv", index=False, encoding="utf-8-sig")
    (dest / "YER_TUTUCU.txt").write_text("Bu paketteki sayılar SENTETİK YER TUTUCUDUR; gerçek analiz sonucu değildir.\n",
                                         encoding="utf-8")
    return dest
