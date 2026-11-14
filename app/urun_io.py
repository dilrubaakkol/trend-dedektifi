"""Yayımlanan veri setinin (Katman 1–4) dosyalarını bulan, okuyan ve paketleyen yardımcılar.

Site yeni hesap yapmaz: tablolar `trend_iller.csv`, `trend_bolgeler.csv` ve `iliski_iller.csv`
dosyalarından okunur (sütunlar: ekip belgesi "Dosyalar ve tablo sütunları"). Bu dosyalar henüz
üretilmediyse ekran akışını göstermek için **SENTETİK YER TUTUCU** tablolar üretilir; bu tablolar
her yerde işaretlenir ve indirilen dosya adı `YER_TUTUCU_` ile başlar.
"""

from __future__ import annotations

import io
import json
import math
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

# Yayın klasörü (python -m data.export) ve ekip içi yol önerisi (cache/urun/L2_anomali/ vb.).
SEARCH_DIRS = [ROOT / "outputs" / f"trend-dedektifi-turkiye-{VERSION}", ROOT / "cache" / "urun"]
LAYERS = [
    ("L1_kup", "1 · Uyumlaştırılmış küp", "Her değişken: Türkiye, ortak 0,25° ızgara, aylık, ortak birim, ülke maskesi",
     "<degisken>__<urun>.nc", "Kişi 1"),
    ("L2_anomali", "2 · Anomali ve mevsim serileri", "12 aylık klimatoloji, aylık anomali, yıllık ve 4 mevsim ortalaması",
     "<degisken>__<urun>__anomali.nc", "Kişi 2"),
    ("L3_trend", "3 · Trend ürünleri", "Hücre trend haritası; il ve bölge trend tabloları; kaynaklar arası uyum",
     "trend_iller.csv · trend_bolgeler.csv · <degisken>__<urun>__trend.nc", "Kişi 2"),
    ("L4_iliski", "4 · İlişkiler", "6 değişken çiftinin ilişkisi ve fizik kontrolü",
     "iliski_iller.csv · iliski__<d1>__<d2>.nc", "Kişi 3"),
]

TREND_COLS = ["il", "plaka", "bolge", "degisken", "urun", "mevsim", "donem", "n_yil", "n_hucre", "egim_10yil",
              "ci_alt", "ci_ust", "birim", "p_mk", "p_mk_kontrol", "p_ttest", "belirsiz", "anlamli_fdr",
              "yil_sayisi_gereken", "kaynak_uyumu"]
ILISKI_COLS = ["il", "plaka", "cift_no", "degisken_1", "degisken_2", "zaman_olcegi", "gecikme_ay", "r", "p",
               "n_etkin", "anlamli_fdr", "beklenen_yon", "kontrol_etiketi"]
SEASONS = {"yillik": "Yıllık", "kis": "Kış", "ilkbahar": "İlkbahar", "yaz": "Yaz", "sonbahar": "Sonbahar"}
ALPHA_FDR = 0.10

# Kademe 1 değişkenleri: (değişken, ürünler [ana ürün ilk], birim). Ekip belgesindeki tabloyla aynı.
TIER1 = [
    ("sicaklik_2m", ["M2TMNXSLV", "GLDAS_NOAH025_M"], "°C"),
    ("yagis", ["GPM_3IMERGM", "GLDAS_NOAH025_M", "M2TMNXFLX"], "mm"),
    ("toprak_nemi", ["GLDAS_NOAH025_M"], "kg/m²"),
    ("kar_ortusu", ["MOD10CM"], "%"),
    ("kar_su_esdegeri", ["GLDAS_NOAH025_M"], "mm"),
    ("ndvi", ["MOD13C2"], ""),
    ("toplam_su_depolama", ["TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4"], "cm"),
]
PAIRS = [  # (no, d1, d2, zaman ölçeği, gecikmeler, beklenen yön, mekanizma, kademe)
    (1, "sicaklik_2m", "kar_ortusu", "kis", [0], "negatif", "Sıcak kışta kar azalır", 1),
    (2, "yagis", "toprak_nemi", "mevsimlik", [0], "pozitif", "Yağış toprağı besler", 1),
    (3, "toprak_nemi", "ndvi", "aylik_nisan_eylul", [1, 2], "pozitif", "Bitki nemli toprağa gecikmeyle tepki verir", 1),
    (4, "yagis", "toplam_su_depolama", "yillik", [0], "pozitif", "Yağış depolamayı doldurur", 1),
    (5, "sicaklik_2m", "buharlasma", "yaz", [0], "pozitif", "Isınma buharlaşmayı artırır (su yeterliyse)", 2),
    (6, "sicaklik_2m", "yuzey_sicakligi_gunduz", "aylik", [0], "pozitif", "Aynı olgunun iki ölçümü (kalite kontrolü)", 2),
]
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

    # İlişkiler
    rel = []
    for no, d1, d2, scale, lags, sign, _, _ in PAIRS:
        for lag in lags:
            for _, pl in il.iterrows():
                east = (pl["lon"] - 35.0) / 10.0
                r0 = {1: -0.25 - 0.3 * east, 2: 0.55, 3: 0.35 - 0.08 * lag, 4: 0.45,
                      5: 0.35 - 0.6 * max(0.0, 38.5 - pl["lat"]), 6: 0.88}[no]
                if no == 3 and pl["il"] in ("Konya", "Şanlıurfa", "Aksaray", "Karaman"):
                    r0 = -0.45  # sulama gibi insan etkisini canlandıran örnek (SENTETİK)
                r = float(np.clip(r0 + rng.normal(0, 0.18), -0.97, 0.97))
                n = {"kis": 24, "mevsimlik": 100, "aylik_nisan_eylul": 150, "yillik": 22, "yaz": 25, "aylik": 300}[scale]
                n_eff = max(5.0, n * (0.55 + 0.3 * rng.random()))
                t = r * math.sqrt((n_eff - 2) / max(1e-9, 1 - r * r))
                p = float(2 * stats.t.sf(abs(t), df=n_eff - 2))
                rel.append({"il": pl["il"], "plaka": int(pl["plaka"]), "cift_no": no, "degisken_1": d1,
                            "degisken_2": d2, "zaman_olcegi": scale, "gecikme_ay": lag, "r": round(r, 3),
                            "p": round(p, 4), "n_etkin": round(n_eff, 1), "anlamli_fdr": 0, "beklenen_yon": sign,
                            "kontrol_etiketi": ""})
    rel_df = pd.DataFrame(rel)
    for _, idx in rel_df.groupby(["cift_no", "gecikme_ay"]).groups.items():
        p = rel_df.loc[idx, "p"].to_numpy()
        rel_df.loc[idx, "anlamli_fdr"] = (bh_fdr(p) & (p < 0.05)).astype(int)
    rel_df["kontrol_etiketi"] = [control_label(r, s, f) for r, s, f in
                                 zip(rel_df["r"], rel_df["beklenen_yon"], rel_df["anlamli_fdr"])]
    return il_df, bolge_df, rel_df[ILISKI_COLS]


def control_label(r: float, expected: str, significant: int) -> str:
    """Fizik kontrolü etiketi: beklenen_yonde / ters_yonde / anlamsiz."""
    if not significant:
        return "anlamsiz"
    same = (r > 0) == (expected == "pozitif")
    return "beklenen_yonde" if same else "ters_yonde"


# ------------------------------------------------------------------ gerçek dosyalar
def find_file(layer: str, name: str) -> Path | None:
    """Önce yayın klasöründe, sonra ekip içi `cache/urun/` altında dosyayı arar."""
    for base in SEARCH_DIRS:
        p = base / layer / name
        if p.exists():
            return p
    return None


def load_tables() -> dict:
    """Trend ve ilişki tablolarını döndürür.

    Dönüş: {"il", "bolge", "iliski": DataFrame, "yer_tutucu": bool, "kaynak": {ad: yol ya da None}}.
    Üç dosyadan biri bile eksikse o tablo sentetik yer tutucudur ve `yer_tutucu` True olur.
    """
    syn = None
    out, src, placeholder = {}, {}, False
    for key, layer, name in (("il", "L3_trend", "trend_iller.csv"), ("bolge", "L3_trend", "trend_bolgeler.csv"),
                             ("iliski", "L4_iliski", "iliski_iller.csv")):
        p = find_file(layer, name)
        if p is not None:
            out[key] = pd.read_csv(p, encoding="utf-8")
            src[name] = p
        else:
            syn = syn or synthetic_tables()
            out[key] = {"il": syn[0], "bolge": syn[1], "iliski": syn[2]}[key].copy()
            src[name] = None
            placeholder = True
    return {**out, "yer_tutucu": placeholder, "kaynak": src}


def inventory() -> list[dict]:
    """Katman klasörlerindeki gerçek dosyalar: [{katman, dosya, yol, boyut_mb}]."""
    seen, rows = set(), []
    for base in SEARCH_DIRS:
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
    wanted = {p for _, prods, _ in TIER1 for p in prods} | {"SRTMGL30"}
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


def build_bundle(tables: dict, variables, seasons, provinces_sel, user: dict, include_nc: bool = False,
                 git_commit: str | None = None) -> tuple[bytes, str]:
    """Akademisyen için seçime göre hazır veri paketi (zip) üretir. Dönüş: (zip baytları, dosya adı).

    İçerik: süzülmüş trend_iller.csv / trend_bolgeler.csv / iliski_iller.csv, BENIOKU.txt,
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
    if provinces_sel:
        rel_f = rel_f[rel_f["il"].isin(provinces_sel)]

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
        "satir_sayisi": {"trend_iller": len(il_f), "trend_bolgeler": len(bolge_f), "iliski_iller": len(rel_f)},
        "kaynak_dosyalar": {k: (v.relative_to(ROOT).as_posix() if v else "SENTETİK YER TUTUCU")
                            for k, v in tables["kaynak"].items()},
        "netcdf": [r["dosya"] for r in files_nc], "git_commit": git_commit,
        "kullanici_rolu": user.get("rol"),
    }
    warn = ("UYARI: Bu paketteki sayılar SENTETİK YER TUTUCUDUR, gerçek analiz sonucu değildir. "
            "Makalede kullanmayın; gerçek sürüm yayımlanınca yeniden indirin.\n\n") if ph else ""
    readme = (
        f"{warn}Trend Dedektifi — Türkiye iklim trendi veri seti, sürüm {VERSION} (ön sürüm)\n"
        f"Lisans: {LICENSE}. DOI: {VERI_SETI_DOI}\n\n"
        "Dosyalar\n"
        "  trend_iller.csv     il bazında trendler (Sen eğimi / 10 yıl, %95 genişletilmiş aralık, Hamed-Rao MK, FDR)\n"
        "  trend_bolgeler.csv  7 coğrafi bölge ve Türkiye\n"
        "  iliski_iller.csv    6 değişken çifti, trendi çıkarılmış anomali korelasyonu ve fizik kontrolü\n"
        "  NASA_KAYNAKLARI.csv kullanılan NASA ürünleri ve DOI'leri (bunlara da atıf yapın)\n"
        "  manifest.json       seçim, sürüm ve kaynak dosyalar\n\n"
        "CSV kuralı: UTF-8, ondalık ayıracı nokta, boş değer boş hücre.\n"
        "Anlamlılık: p_mk < 0,05 (Hamed-Rao). Harita ve il tablosunda Benjamini-Hochberg, α_FDR = 0,10.\n"
        "belirsiz = 1: ana test ile kontrol testi farklı sonuç veriyor.\n"
        "kaynak_uyumu = k/m: m kaynaktan k'si ana kaynakla aynı yönde anlamlı (tutarlılık, bağımsız doğrulama değil).\n"
        "İlişkiler için 'neden' değil 'ilişki' ifadesini kullanın.\n\n"
        f"Atıf (APA):\n  {cit['apa']}\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{prefix}trend_iller.csv", il_f.to_csv(index=False))
        z.writestr(f"{prefix}trend_bolgeler.csv", bolge_f.to_csv(index=False))
        z.writestr(f"{prefix}iliski_iller.csv", rel_f.to_csv(index=False))
        z.writestr("BENIOKU.txt", readme)
        z.writestr("CITATION.bib", cit["bibtex"] + "\n")
        z.writestr("NASA_KAYNAKLARI.csv", pd.DataFrame(nasa_sources()).to_csv(index=False))
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for r in files_nc:
            z.write(r["yol"], f"L1_kup/{r['dosya']}")
    name = f"{prefix}trend-dedektifi-turkiye-{VERSION}-paket.zip"
    return buf.getvalue(), name
