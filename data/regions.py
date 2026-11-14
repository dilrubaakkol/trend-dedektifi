"""Bölge seçimi ve kesme/maskeleme. Tek giriş noktası: ``subset(ds, region)``.

Veri bir kez tüm Türkiye kutusu (TURKIYE_BBOX) için işlenir; kullanıcının seçtiği bölge bu küpten
YEREL olarak kesilir, yeniden indirme yapılmaz.

``region`` şunlardan biri olabilir:
  - "turkiye"                         → Türkiye kara sınırı (deniz değişkenlerinde: çevre denizler)
  - 7 coğrafi bölge: "marmara", "ege", "akdeniz", "ic_anadolu", "karadeniz", "dogu_anadolu",
    "guneydogu_anadolu" (ya da "Doğu Anadolu Bölgesi" gibi yazımlar)
  - 81 il: "Erzurum", "Şanlıurfa" / "Sanliurfa", "Afyon", "K. Maraş" ...
  - denizler: "deniz_karadeniz", "deniz_marmara", "deniz_ege", "deniz_akdeniz", "cevre_denizler"
  - demo kutuları: "demo:dogu_anadolu", "demo:konya" (= "konya_kapali_havzasi")
  - bbox tuple'ı: (batı, güney, doğu, kuzey)
  - GeoJSON: dict (Feature / FeatureCollection / geometry), JSON metni, .geojson dosya yolu
    ya da shapely geometrisi

Ad çakışmalarında önek kullanılabilir: "il:Konya", "bolge:Karadeniz", "deniz:Karadeniz", "demo:konya".
Öneksiz adlarda öncelik: turkiye → bölge → il → deniz → demo. Yani "konya" = Konya ili,
"dogu_anadolu" = Doğu Anadolu Bölgesi (eski demo kutuları için "demo:" öneki ya da get_bbox()).

Maskeleme kuralı: hücre MERKEZİ çokgenin içindeyse hücre alınır. Küçük bir bölgede hiç merkez
düşmezse çokgenle kesişen hücreler alınır (attrs["region_method"] bunu yazar).
"""

from __future__ import annotations

import json
import re
import unicodedata
import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np
import shapely
import xarray as xr
import yaml
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry

from data.grid import TURKIYE_BBOX

BOUNDARY_DIR = Path(__file__).resolve().parent / "boundaries"

# Eski demo kutuları — anahtarlar ve get_bbox() aynen çalışmaya devam eder.
REGIONS = {
    "dogu_anadolu": {
        "label": "Doğu Anadolu (Erzurum–Kars–Van)",
        "bbox": (38.0, 37.5, 44.0, 41.5),
    },
    "konya": {
        "label": "Konya Kapalı Havzası",
        "bbox": (31.5, 36.8, 34.5, 39.2),
    },
}

# İl adı takma adları (normalize edilmiş biçimde) → resmî il adının anahtarı
IL_ALIASES = {
    "afyon": "afyonkarahisar", "maras": "kahramanmaras", "k_maras": "kahramanmaras",
    "icel": "mersin", "antep": "gaziantep", "urfa": "sanliurfa", "izmit": "kocaeli",
    "adapazari": "sakarya", "antakya": "hatay", "zinguldak": "zonguldak", "kinkkale": "kirikkale",
}
SEA_ALIASES = {
    "karadeniz_denizi": "deniz_karadeniz", "marmara_denizi": "deniz_marmara",
    "ege_denizi": "deniz_ege", "akdeniz_denizi": "deniz_akdeniz",
}
DEMO_ALIASES = {"konya_kapali_havzasi": "konya", "dogu_anadolu_demo": "dogu_anadolu"}
OCEAN_BUFFER_DEG = 0.5  # deniz değişkeninde kara bölgesi seçilirse kıyıdan bu kadar açığa bakılır

_TR_MAP = str.maketrans({"İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s", "Ğ": "g", "ğ": "g",
                         "Ü": "u", "ü": "u", "Ö": "o", "ö": "o", "Ç": "c", "ç": "c",
                         "Â": "a", "â": "a", "Î": "i", "î": "i", "Û": "u", "û": "u"})


def get_bbox(region: str) -> tuple[float, float, float, float]:
    """Eski API: demo kutusunun bbox'ı (batı, güney, doğu, kuzey). Yeni bölgeler için region_bounds()."""
    if region in REGIONS:
        return REGIONS[region]["bbox"]
    return region_bounds(region)


def normalize_name(name: str) -> str:
    """Türkçe karakterli/karaktersiz, büyük/küçük harfli yazımları tek anahtara indirger.

    "Şanlıurfa" → "sanliurfa", "Doğu Anadolu Bölgesi" → "dogu_anadolu_bolgesi", "K. Maraş" → "k_maras".
    """
    s = name.strip().translate(_TR_MAP)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


# ---------------------------------------------------------------- sınır dosyaları

def _read_geojson(name: str) -> dict:
    path = BOUNDARY_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"{path} yok. Önce: python -m data.make_boundaries")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _il_ad_duzeltmeleri() -> dict[str, str]:
    """data/boundaries/il_adlari.yaml: Natural Earth yazımı → kullanılacak il adı (yoksa boş)."""
    path = BOUNDARY_DIR / "il_adlari.yaml"
    if not path.exists():
        return {}
    return dict((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("duzeltmeler") or {})


def il_adi(ad: str) -> str:
    """İl adını düzeltme tablosundan geçirir (ör. "Elâzığ" → "Elazığ"); tabloda yoksa aynen döner."""
    return _il_ad_duzeltmeleri().get(ad, ad)


@lru_cache(maxsize=1)
def _iller() -> dict[str, dict]:
    """anahtar → {"ad", "plaka", "geom"} (81 il). Ad, il_adlari.yaml düzeltmelerinden geçer."""
    out = {}
    for f in _read_geojson("iller.geojson")["features"]:
        p = f["properties"]
        out[p["anahtar"]] = {"ad": il_adi(p["ad"]), "plaka": p["plaka"],
                             "geom": shapely.make_valid(shape(f["geometry"]))}
    return out


@lru_cache(maxsize=1)
def _bolgeler() -> dict[str, dict]:
    """bölge anahtarı → {"ad", "iller": [il anahtarları]}."""
    raw = yaml.safe_load((BOUNDARY_DIR / "bolgeler.yaml").read_text(encoding="utf-8"))
    iller = _iller()
    out = {}
    for key, v in raw.items():
        keys = [normalize_name(n) for n in v["iller"]]
        bad = [k for k in keys if k not in iller]
        if bad:
            raise ValueError(f"bolgeler.yaml: bilinmeyen il(ler) {bad}")
        out[key] = {"ad": v["ad"], "iller": keys}
    return out


@lru_cache(maxsize=1)
def _seas() -> dict[str, dict]:
    out = {}
    for f in _read_geojson("denizler.geojson")["features"]:
        p = f["properties"]
        out[p["anahtar"]] = {"ad": p["ad"], "geom": shapely.make_valid(shape(f["geometry"]))}
    return out


@lru_cache(maxsize=1)
def turkiye_geometry() -> BaseGeometry:
    """Türkiye kara sınırı (81 ilin birleşimi)."""
    return shapely.union_all([v["geom"] for v in _iller().values()])


@lru_cache(maxsize=1)
def land_geometry() -> BaseGeometry:
    """Kutudaki tüm kara (komşu ülkeler dahil) — deniz maskesi bunun tersidir."""
    g = _read_geojson("kara.geojson")["features"][0]["geometry"]
    return shapely.make_valid(shape(g))


@lru_cache(maxsize=None)
def _bolge_geom(key: str) -> BaseGeometry:
    il = _iller()
    return shapely.union_all([il[k]["geom"] for k in _bolgeler()[key]["iller"]])


def list_regions() -> dict[str, list[tuple[str, str]]]:
    """Arayüz için seçenekler: {"bolge": [(anahtar, ad)], "il": [...], "deniz": [...], "demo": [...]}."""
    return {
        "turkiye": [("turkiye", "Türkiye (tamamı)")],
        "bolge": [(k, v["ad"]) for k, v in _bolgeler().items()],
        "il": sorted(((k, v["ad"]) for k, v in _iller().items()), key=lambda x: x[0]),
        "deniz": [(k, v["ad"]) for k, v in _seas().items()] + [("cevre_denizler", "Çevre denizler")],
        "demo": [(f"demo:{k}", v["label"]) for k, v in REGIONS.items()],
    }


def bolge_of_il(il: str) -> str:
    """Bir ilin bağlı olduğu coğrafi bölgenin anahtarı."""
    k = IL_ALIASES.get(normalize_name(il), normalize_name(il))
    for b, v in _bolgeler().items():
        if k in v["iller"]:
            return b
    raise KeyError(f"İl bulunamadı: {il}")


# ---------------------------------------------------------------- bölge çözümleme

def resolve_region(region) -> dict:
    """Bölge girdisini çözümler.

    Döndürür: {"kind": turkiye|bolge|il|deniz|demo|bbox|geojson, "key", "label",
               "geom": shapely geometrisi ya da None, "bbox": (batı, güney, doğu, kuzey)}
    """
    if isinstance(region, BaseGeometry):
        return _geom_result("geojson", "geojson", "Kullanıcı çokgeni", region)
    if isinstance(region, dict):
        return _geom_result("geojson", "geojson", "Kullanıcı çokgeni", _geojson_to_geom(region))
    if isinstance(region, (tuple, list)) and len(region) == 4 and \
            all(isinstance(v, (int, float, np.floating, np.integer)) for v in region):
        w, s, e, n = map(float, region)
        if not (w < e and s < n):
            raise ValueError(f"bbox (batı, güney, doğu, kuzey) sırasında olmalı: {region}")
        tw, ts, te, tn = TURKIYE_BBOX
        if e <= tw or w >= te or n <= ts or s >= tn:
            raise ValueError(f"bbox Türkiye kutusunun {TURKIYE_BBOX} dışında: {region}")
        return {"kind": "bbox", "key": f"bbox_{w:g}_{s:g}_{e:g}_{n:g}",
                "label": f"Kutu {w:g},{s:g},{e:g},{n:g}", "geom": None, "bbox": (w, s, e, n)}
    if not isinstance(region, str):
        raise TypeError(f"Desteklenmeyen bölge türü: {type(region)}")

    text = region.strip()
    if text.startswith("{"):
        return resolve_region(json.loads(text))
    if text.lower().endswith((".geojson", ".json")) and Path(text).exists():
        return resolve_region(json.loads(Path(text).read_text(encoding="utf-8")))

    prefix, _, rest = text.partition(":")
    if rest and normalize_name(prefix) in ("il", "bolge", "deniz", "demo"):
        kinds, key = [normalize_name(prefix)], normalize_name(rest)
    else:
        kinds, key = ["turkiye", "bolge", "il", "deniz", "demo"], normalize_name(text)

    for kind in kinds:
        r = _lookup(kind, key)
        if r is not None:
            return r
    raise KeyError(f"Bölge bulunamadı: {region!r}. Seçenekler için list_regions().")


def _lookup(kind: str, key: str) -> dict | None:
    if kind == "turkiye" and key in ("turkiye", "tr", "turkey", "tum_turkiye", "tumu"):
        return _geom_result("turkiye", "turkiye", "Türkiye (tamamı)", turkiye_geometry())
    if kind == "bolge":
        k = re.sub(r"_(bolgesi|bolge)$", "", key)
        if k in _bolgeler():
            return _geom_result("bolge", k, _bolgeler()[k]["ad"], _bolge_geom(k))
    if kind == "il":
        k = re.sub(r"_(ili|il)$", "", key)
        k = IL_ALIASES.get(k, k)
        if k in _iller():
            v = _iller()[k]
            return _geom_result("il", k, v["ad"], v["geom"])
    if kind == "deniz":
        k = SEA_ALIASES.get(key, key)
        if not k.startswith("deniz_") and f"deniz_{k}" in _seas():
            k = f"deniz_{k}"
        if k in _seas():
            return _geom_result("deniz", k, _seas()[k]["ad"], _seas()[k]["geom"])
        if k in ("cevre_denizler", "denizler", "deniz_tumu"):
            g = shapely.union_all([v["geom"] for v in _seas().values()])
            return _geom_result("deniz", "cevre_denizler", "Çevre denizler", g)
    if kind == "demo":
        k = DEMO_ALIASES.get(key, key)
        if k in REGIONS:
            return {"kind": "demo", "key": f"demo_{k}", "label": REGIONS[k]["label"],
                    "geom": None, "bbox": REGIONS[k]["bbox"]}
    return None


def _geom_result(kind, key, label, geom) -> dict:
    return {"kind": kind, "key": key, "label": label, "geom": geom, "bbox": tuple(geom.bounds)}


def _geojson_to_geom(obj: dict) -> BaseGeometry:
    t = obj.get("type")
    if t == "FeatureCollection":
        return shapely.union_all([_geojson_to_geom(f) for f in obj["features"]])
    if t == "Feature":
        return _geojson_to_geom(obj["geometry"])
    g = shapely.make_valid(shape(obj))
    if g.area == 0:
        raise ValueError("GeoJSON alanı sıfır (nokta/çizgi); çokgen gerekli")
    return g


def region_bounds(region) -> tuple[float, float, float, float]:
    """Bölgenin dış kutusu (batı, güney, doğu, kuzey)."""
    return resolve_region(region)["bbox"]


# ---------------------------------------------------------------- maskeler

def _cell_boxes(lat, lon):
    dlat = float(np.median(np.diff(lat))) if lat.size > 1 else 0.25
    dlon = float(np.median(np.diff(lon))) if lon.size > 1 else 0.25
    LON, LAT = np.meshgrid(lon, lat)
    return shapely.box(LON - dlon / 2, LAT - dlat / 2, LON + dlon / 2, LAT + dlat / 2)


def polygon_mask(geom: BaseGeometry, lat, lon, all_touched: bool = False) -> np.ndarray:
    """(lat, lon) ızgarasında çokgen maskesi. Varsayılan: hücre merkezi içeride mi."""
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    if all_touched:
        return shapely.intersects(geom, _cell_boxes(lat, lon))
    LON, LAT = np.meshgrid(lon, lat)
    shapely.prepare(geom)
    return shapely.contains_xy(geom, LON, LAT)


@lru_cache(maxsize=16)
def _domain_mask_cached(domain: str, lat_t: tuple, lon_t: tuple) -> np.ndarray:
    lat, lon = np.array(lat_t), np.array(lon_t)
    if domain == "land":
        return polygon_mask(turkiye_geometry(), lat, lon)
    if domain == "ocean":
        inside = polygon_mask(box(*TURKIYE_BBOX), lat, lon)
        return inside & ~polygon_mask(land_geometry(), lat, lon)
    raise ValueError(f"Bilinmeyen domain: {domain}")


def domain_mask(domain: str, lat, lon) -> np.ndarray | None:
    """domain maskesi (True = geçerli): "land" = Türkiye karası, "ocean" = kutudaki deniz, "all" = None."""
    if domain == "all":
        return None
    return _domain_mask_cached(domain, tuple(np.round(np.asarray(lat, float), 6)),
                               tuple(np.round(np.asarray(lon, float), 6)))


# ---------------------------------------------------------------- tek giriş noktası

def subset(ds: xr.Dataset | xr.DataArray, region, all_touched: bool = False):
    """Veriyi bölgeye keser ve maskeler. Bölge dışı hücreler NaN, dış kutu dışı kırpılır.

    Parametreler:
        ds: (time,) lat, lon boyutlu xarray (tüm Türkiye küpü).
        region: il / bölge / "turkiye" / deniz adı, bbox tuple'ı ya da GeoJSON (modül belgesine bakın).
        all_touched: True ise çokgene değen tüm hücreler alınır (varsayılan: merkezi içeride olanlar).

    Deniz değişkeni (attrs["domain"] == "ocean") için kara bölgesi seçilirse: "turkiye" → tüm çevre
    denizler; il/bölge → sınırın OCEAN_BUFFER_DEG derece açığına kadar olan deniz.

    Döndürür: aynı türde xarray; attrs'a region, region_label, region_kind, region_cells,
    region_method eklenir.
    """
    r = resolve_region(region)
    domain = ds.attrs.get("domain", "all")
    geom = r["geom"]
    method = "merkez"
    if domain == "ocean" and r["kind"] in ("turkiye", "bolge", "il"):
        if r["kind"] == "turkiye":
            geom = box(*TURKIYE_BBOX)
        else:
            geom = geom.buffer(OCEAN_BUFFER_DEG)
        method = f"kıyı tamponu {OCEAN_BUFFER_DEG}°" if r["kind"] != "turkiye" else "tüm kutu"
    elif domain == "land" and r["kind"] == "deniz":
        warnings.warn(f"Kara değişkeni deniz bölgesiyle ({r['label']}) kesiliyor; sonuç boş olabilir.")

    w, s, e, n = geom.bounds if geom is not None else r["bbox"]
    lat, lon = ds["lat"].values, ds["lon"].values
    dlat = float(np.median(np.diff(lat))) if lat.size > 1 else 0.0
    dlon = float(np.median(np.diff(lon))) if lon.size > 1 else 0.0

    if geom is None:  # bbox / demo kutusu: merkezi kutuda olan hücreler
        out = ds.sel(lat=slice(s, n), lon=slice(w, e))
        if out.sizes["lat"] == 0 or out.sizes["lon"] == 0:
            out = ds.sel(lat=[(s + n) / 2], lon=[(w + e) / 2], method="nearest")
            method = "en yakın hücre"
        else:
            method = "kutu"
        ncell = out.sizes["lat"] * out.sizes["lon"]
    else:
        out = ds.sel(lat=slice(s - dlat, n + dlat), lon=slice(w - dlon, e + dlon))
        m = polygon_mask(geom, out["lat"].values, out["lon"].values, all_touched=all_touched)
        if all_touched:
            method = "değen hücreler"
        elif not m.any():
            m = polygon_mask(geom, out["lat"].values, out["lon"].values, all_touched=True)
            method = "değen hücreler (merkez düşmedi)"
        mask = xr.DataArray(m, coords={"lat": out["lat"], "lon": out["lon"]}, dims=("lat", "lon"))
        # Bölgeyi saran en küçük kutuya kırp
        rows, cols = np.where(m)
        out = out.where(mask).isel(lat=slice(rows.min(), rows.max() + 1),
                                   lon=slice(cols.min(), cols.max() + 1))
        ncell = int(m.sum())

    out.attrs = dict(ds.attrs)
    out.attrs.update(region=r["key"], region_label=r["label"], region_kind=r["kind"],
                     region_cells=ncell, region_method=method)
    return out


def area_mean(da: xr.DataArray) -> xr.DataArray:
    """cos(enlem) ağırlıklı alan ortalaması (NaN hücreler atlanır)."""
    w = np.cos(np.deg2rad(da["lat"]))
    return da.weighted(w.fillna(0)).mean(("lat", "lon"), skipna=True)
