"""Yayın paketi: işlenmiş 0,25° gerçek veri küplerini yayın kutusuna kırpıp tek klasöre yazar.

    python -m data.export --surum v0.1

Çıktı:
    outputs/trend-dedektifi-turkiye-<surum>/L1_kup/<degisken>__<urun>.nc
    outputs/trend-dedektifi-turkiye-<surum>/L1_kup/ICINDEKILER.csv

Kurallar:
- Yalnız 0,25° (``__005`` dosyaları girmez) ve yalnız gerçek veri (SENTETIK girmez).
- İçeride ``TURKIYE_BBOX`` kullanılır; yayında kutu ``YAYIN_BBOX`` (25,5–45,0 D, 35,5–42,5 K),
  0,25°'de 28 enlem × 78 boylam hücre. Hücre kenarlarının kutu sınırına tam oturduğu denetlenir.
- Kademe 1 = ekip belgesindeki çekirdek dosyalar (``KADEME_1``); diğerleri Kademe 2 ve
  ``dogrulanmadi="evet"`` attr'ı taşır. Sabit alanlar (rakım) kademe dışıdır: ``kademe="-"``.
- Mevcut ``doi`` attr'ı NASA kaynak ürününün DOI'si olarak kalır; yayın DOI'si ``veri_seti_doi``.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from data.catalog import variables
from data.grid import GRID_RES, REPO_ROOT, TURKIYE_DIR, check_contract, write_netcdf

# (batı, güney, doğu, kuzey), derece — yayın kutusu
YAYIN_BBOX: tuple[float, float, float, float] = (25.5, 35.5, 45.0, 42.5)
YAYIN_SHAPE = (28, 78)  # (lat, lon) 0,25°'de

# Kademe 1 değişken × dosya kodu çiftleri (ekip belgesi); geri kalan gerçek dosyalar Kademe 2
KADEME_1 = {
    ("sicaklik_2m", "MERRA2"), ("sicaklik_2m", "GLDAS"),
    ("yagis", "GPM"), ("yagis", "GLDAS"), ("yagis", "MERRA2"),
    ("toprak_nemi", "GLDAS"), ("kar_ortusu", "MOD10CM"), ("kar_su_esdegeri", "GLDAS"),
    ("ndvi", "MOD13C2"), ("toplam_su_depolama", "GRACE"),
}
# Kademe dışı (sabit alanlar): kademe attr'ı "-", dogrulanmadi yok
KADEME_DISI = {"rakim"}

LISANS = "CC BY 4.0"
VERI_SETI_DOI = "(yayında doldurulacak)"
OUTPUTS_DIR = REPO_ROOT / "outputs"
ICINDEKILER_COLS = ["dosya", "degisken", "birim", "kaynak", "kaynak_doi", "donem", "kademe"]


def kademe(degisken: str, urun: str) -> int | str:
    """Değişken × dosya kodu için yayın kademesi: 1, 2 (doğrulanmadı) ya da "-" (kademe dışı, sabit)."""
    if degisken in KADEME_DISI:
        return "-"
    return 1 if (degisken, urun) in KADEME_1 else 2


def is_synthetic(ds: xr.Dataset) -> bool:
    """Dosya sentetik mi? (ürün kodu SENTETIK ya da synthetic_truth / yer_tutucu attrs'ı)."""
    return (str(ds.attrs.get("source_product", "")).upper() == "SENTETIK"
            or "synthetic_truth" in ds.attrs or "yer_tutucu" in ds.attrs)


def crop_to_bbox(ds: xr.Dataset, bbox=YAYIN_BBOX, res: float = GRID_RES["025"],
                 shape=YAYIN_SHAPE) -> xr.Dataset:
    """Hücre merkezi kutu içinde kalan hücreleri seçer ve kenarların ızgaraya oturduğunu doğrular.

    Hata verir: ızgara aralığı ``res`` değilse, kesit ``shape`` boyutunda değilse ya da ilk/son
    hücrenin kenarı kutu sınırıyla çakışmıyorsa.
    """
    west, south, east, north = bbox
    lat, lon = ds["lat"].values, ds["lon"].values
    for name, c in (("lat", lat), ("lon", lon)):
        if c.size < 2 or not np.allclose(np.diff(c), res, atol=1e-6):
            raise ValueError(f"{name} ızgara aralığı {res}° değil")
    out = ds.isel(lat=np.where((lat > south) & (lat < north))[0],
                  lon=np.where((lon > west) & (lon < east))[0])
    got = (out.sizes["lat"], out.sizes["lon"])
    if shape is not None and got != tuple(shape):
        raise ValueError(f"kesit boyutu {got}, beklenen {tuple(shape)}")
    half = res / 2
    edges = {"batı": (out["lon"].values[0] - half, west), "doğu": (out["lon"].values[-1] + half, east),
             "güney": (out["lat"].values[0] - half, south), "kuzey": (out["lat"].values[-1] + half, north)}
    bad = {k: v for k, v in edges.items() if not np.isclose(v[0], v[1], atol=1e-6)}
    if bad:
        raise ValueError(f"kutu kenarı ızgaraya oturmuyor: {bad}")
    return out


def data_period(ds: xr.Dataset) -> str:
    """Kesitte en az bir geçerli hücresi olan ilk ve son ay ("YYYY-MM … YYYY-MM"); sabit alanda "sabit"."""
    if "time" not in ds.dims:
        return "sabit"
    da = next(iter(ds.data_vars.values()))
    ok = da.notnull().any(dim=[d for d in da.dims if d != "time"]).values
    if not ok.any():
        return "veri yok"
    t = pd.DatetimeIndex(ds["time"].values[ok])
    return f"{t[0]:%Y-%m} … {t[-1]:%Y-%m}"


def release_attrs(ds: xr.Dataset, degisken: str, urun: str, surum: str, bbox=YAYIN_BBOX) -> dict:
    """Mevcut attrs'a yayın alanlarını ekler (doi = NASA kaynak DOI'si olarak kalır)."""
    k = kademe(degisken, urun)
    a = dict(ds.attrs)
    w, s, e, n = bbox
    a["processing"] = (f"{a.get('processing', '')}; yayın kutusuna kırpıldı "
                       f"(batı {w}, güney {s}, doğu {e}, kuzey {n})").lstrip("; ")
    a.update(urun_surumu=surum, veri_seti_doi=VERI_SETI_DOI,
             kademe=k if k == "-" else np.int32(k), lisans=LISANS,
             yayin_kutusu=f"{w}, {s}, {e}, {n}")
    if k == 2:
        a["dogrulanmadi"] = "evet"
    else:
        a.pop("dogrulanmadi", None)
    return a


def candidates(src_dir: Path = TURKIYE_DIR) -> list[tuple[str, str, Path]]:
    """Katalogdaki her değişken × ürün için var olan 0,25° gerçek dosyalar: (degisken, urun, yol)."""
    seen, out = set(), []
    for v in variables():
        key = (v["ad"], v["urun_bilgi"]["dosya_kodu"])
        p = Path(src_dir) / f"{key[0]}__{key[1]}.nc"
        if key not in seen and p.exists():
            seen.add(key)
            out.append((*key, p))
    return out


def export(surum: str, src_dir: Path = TURKIYE_DIR, out_root: Path = OUTPUTS_DIR,
           bbox=YAYIN_BBOX) -> Path:
    """Yayın paketini yazar; L1_kup klasörünün yolunu döndürür."""
    out_dir = Path(out_root) / f"trend-dedektifi-turkiye-{surum}" / "L1_kup"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for degisken, urun, path in candidates(src_dir):
        with xr.open_dataset(path) as ds:
            ds = ds.load()
        if is_synthetic(ds):
            print(f"  atlandı (sentetik): {path.name}")
            continue
        cut = crop_to_bbox(ds, bbox)
        cut.attrs = release_attrs(ds, degisken, urun, surum, bbox)
        problems = check_contract(cut, static="time" not in cut.dims)
        if problems:
            raise ValueError(f"{path.name} sözleşmeye uymuyor: {problems}")
        write_netcdf(cut, out_dir / path.name)
        rows.append({"dosya": path.name, "degisken": degisken, "birim": cut.attrs.get("units", ""),
                     "kaynak": f"{cut.attrs['source_product']} {cut.attrs['source_version']}",
                     "kaynak_doi": cut.attrs.get("doi", ""), "donem": data_period(cut),
                     "kademe": kademe(degisken, urun)})
        print(f"  yazıldı: {path.name} (kademe {rows[-1]['kademe']}, {rows[-1]['donem']})")
    rows.sort(key=lambda r: (str(r["kademe"]).replace("-", "9"), r["dosya"]))
    with open(out_dir / "ICINDEKILER.csv", "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=ICINDEKILER_COLS)
        wr.writeheader()
        wr.writerows(rows)
    return out_dir


def main(argv=None):
    ap = argparse.ArgumentParser(description="Yayın paketi (L1 küpleri) üretir.")
    ap.add_argument("--surum", required=True, help="ör. v0.1")
    ap.add_argument("--kaynak", default=str(TURKIYE_DIR), help="işlenmiş dosyaların klasörü")
    ap.add_argument("--cikti", default=str(OUTPUTS_DIR), help="çıktı kök klasörü")
    a = ap.parse_args(argv)
    out = export(a.surum, Path(a.kaynak), Path(a.cikti))
    print(f"Yayın paketi: {out}")


if __name__ == "__main__":
    main()
