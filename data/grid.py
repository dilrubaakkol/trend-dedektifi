"""Ortak ızgara, dosya yolu ve sözleşme attrs yardımcıları.

Tüm veri modülleri (synthetic, harmonize, dem, build) aynı ızgarayı ve aynı dosya adlarını
bu modülden alır. Sözleşme: docs/sozlesmeler.md.

Izgara tanımı: aktif ülkenin işleme kutusu (data/ulkeler.yaml, ``ic_kutu``). Varsayılan Türkiye + çevre
denizler kutusu TURKIYE_BBOX = (25.0, 34.5, 45.5, 43.0) (batı, güney, doğu, kuzey); TURKIYE_BBOX geriye
dönük uyumluluk için durur. Hücre kenarları kutu sınırlarına oturur; koordinatlar hücre
merkezidir (0,25° için lon 25.125 … 45.375, lat 34.625 … 42.875). lat güneyden kuzeye artar.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

# (batı, güney, doğu, kuzey), derece
TURKIYE_BBOX: tuple[float, float, float, float] = (25.0, 34.5, 45.5, 43.0)

GRID_RES = {"025": 0.25, "005": 0.05}

PERIOD = ("2001-01", "2025-12")

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "cache"
RAW_DIR = CACHE_DIR / "raw"
PROCESSED_DIR = CACHE_DIR / "processed"
TURKIYE_DIR = PROCESSED_DIR / "turkiye"

# Sözleşmedeki zorunlu attrs
REQUIRED_ATTRS = (
    "units", "long_name", "source_product", "source_version", "doi",
    "daac", "download_date", "processing", "grid", "domain", "valid_start",
)


def ulke_kutusu(ulke: str | None = None) -> tuple[float, float, float, float]:
    """Ülkenin işleme kutusu (``None`` → aktif ülke; varsayılan Türkiye = TURKIYE_BBOX)."""
    from data.ulkeler import ic_kutu
    return ic_kutu(ulke)


def grid_coords(grid: str = "025", bbox=None) -> tuple[np.ndarray, np.ndarray]:
    """Verilen ızgara kodu ("025" / "005") için (lat, lon) hücre merkezlerini döndürür.

    ``bbox`` verilmezse aktif ülkenin işleme kutusu (varsayılan Türkiye: TURKIYE_BBOX).
    lat güneyden kuzeye artar. Kayan nokta hatasını önlemek için koordinatlar yuvarlanır.
    """
    bbox = ulke_kutusu() if bbox is None else bbox
    res = GRID_RES[grid]
    west, south, east, north = bbox
    nlon = int(round((east - west) / res))
    nlat = int(round((north - south) / res))
    lon = np.round(west + res * (np.arange(nlon) + 0.5), 6)
    lat = np.round(south + res * (np.arange(nlat) + 0.5), 6)
    return lat, lon


def monthly_time(start: str = PERIOD[0], end: str = PERIOD[1]) -> pd.DatetimeIndex:
    """Ayın 1'i 00:00 damgalı aylık zaman ekseni (sözleşme)."""
    return pd.date_range(start=start, end=end, freq="MS")


def empty_grid_dataarray(grid: str = "025", time=None, fill=np.nan, name="x") -> xr.DataArray:
    """Sözleşme boyutlarında (time, lat, lon) ya da sabit alan için (lat, lon) boş DataArray."""
    lat, lon = grid_coords(grid)
    if time is None:
        return xr.DataArray(np.full((lat.size, lon.size), fill, dtype="float32"),
                            coords={"lat": lat, "lon": lon}, dims=("lat", "lon"), name=name)
    return xr.DataArray(np.full((len(time), lat.size, lon.size), fill, dtype="float32"),
                        coords={"time": time, "lat": lat, "lon": lon},
                        dims=("time", "lat", "lon"), name=name)


def ulke_dir(ulke: str | None = None) -> Path:
    """İşlenmiş dosyaların klasörü: ``cache/processed/<ulke>/`` (``None`` → aktif ülke)."""
    from data.ulkeler import aktif
    return PROCESSED_DIR / (ulke or aktif())


def processed_path(degisken: str, urun: str, grid: str = "025", bolge: str | None = None) -> Path:
    """İşlenmiş dosyanın yolu.

    0,25° dosyalar sözleşmedeki adla durur: ``cache/processed/<bolge>/<degisken>__<urun>.nc``.
    0,05° dosyalara ``__005`` eki gelir: ``<degisken>__<urun>__005.nc``.
    ``bolge`` verilmezse aktif ülke (varsayılan ``turkiye``).
    """
    suffix = "" if grid == "025" else f"__{grid}"
    return ulke_dir(bolge) / f"{degisken}__{urun}{suffix}.nc"


def today_iso() -> str:
    """Bugünün tarihi (UTC) ISO biçiminde; download_date için."""
    return datetime.now(timezone.utc).date().isoformat()


def add_coord_attrs(ds: xr.Dataset | xr.DataArray):
    """lat/lon/time koordinatlarına CF attrs ekler (yerinde)."""
    if "lat" in ds.coords:
        ds["lat"].attrs.update(units="degrees_north", standard_name="latitude", long_name="enlem")
    if "lon" in ds.coords:
        ds["lon"].attrs.update(units="degrees_east", standard_name="longitude", long_name="boylam")
    if "time" in ds.coords:
        ds["time"].attrs.update(standard_name="time", long_name="zaman (ayın 1'i 00:00 UTC)")
    return ds


def finalize(da: xr.DataArray, attrs: dict) -> xr.Dataset:
    """DataArray'i sözleşme attrs'ı ile Dataset'e çevirir ve boyut sırasını garanti eder.

    attrs hem Dataset'e hem değişkene yazılır (units/long_name değişkende de bulunur).
    dict/list değerler JSON metnine çevrilir (NetCDF attrs iç içe yapı tutamaz).
    """
    dims = [d for d in ("time", "lat", "lon") if d in da.dims]
    da = da.transpose(*dims).sortby("lat")
    clean = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list, tuple)) else v)
             for k, v in attrs.items() if v is not None}
    missing = [k for k in REQUIRED_ATTRS if k not in clean]
    if missing:
        raise ValueError(f"Zorunlu attrs eksik: {missing}")
    da = da.astype("float32")
    da.attrs = {k: clean[k] for k in ("units", "long_name") if k in clean}
    ds = da.to_dataset(name=da.name)
    ds.attrs = clean
    add_coord_attrs(ds)
    return ds


def write_netcdf(ds: xr.Dataset, path: Path) -> Path:
    """Sıkıştırılmış NetCDF4 yazar; zaman birimi 'days since 2001-01-01'."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    enc = {v: {"zlib": True, "complevel": 4, "_FillValue": np.float32(np.nan)} for v in ds.data_vars}
    if "time" in ds.coords:
        enc["time"] = {"units": "days since 2001-01-01 00:00:00", "calendar": "standard",
                       "dtype": "float64"}
    tmp = path.with_suffix(".nc.tmp")
    ds.to_netcdf(tmp, encoding=enc, engine="netcdf4")
    tmp.replace(path)
    return path


def check_contract(ds: xr.Dataset, static: bool = False) -> list[str]:
    """Bir Dataset'in veri sözleşmesine uyup uymadığını denetler; sorun listesi döndürür.

    Boş liste = uyumlu. Testler ve build özeti bu fonksiyonu kullanır.
    """
    problems = []
    for k in REQUIRED_ATTRS:
        if k not in ds.attrs:
            problems.append(f"attrs eksik: {k}")
    if len(ds.data_vars) != 1:
        problems.append(f"tek değişken bekleniyordu: {list(ds.data_vars)}")
    for name, da in ds.data_vars.items():
        want = ("lat", "lon") if static else ("time", "lat", "lon")
        if tuple(da.dims) != want:
            problems.append(f"{name} boyutları {da.dims}, beklenen {want}")
    if "lat" in ds.coords and not bool(np.all(np.diff(ds["lat"].values) > 0)):
        problems.append("lat güneyden kuzeye artmıyor")
    if "lon" in ds.coords and (ds["lon"].min() < -180 or ds["lon"].max() > 180):
        problems.append("lon -180..180 aralığında değil")
    if not static and "time" in ds.coords:
        t = pd.DatetimeIndex(ds["time"].values)
        if not ((t.day == 1).all() and (t.hour == 0).all()):
            problems.append("zaman damgası ayın 1'i 00:00 değil")
        if t.size > 1 and not (t == pd.date_range(t[0], periods=t.size, freq="MS")).all():
            problems.append("zaman ekseni aralıksız aylık değil")
    return problems


def truth(ds: xr.Dataset) -> dict | None:
    """Sentetik dosyadaki ``synthetic_truth`` attrs'ını sözlük olarak döndürür (yoksa None)."""
    raw = ds.attrs.get("synthetic_truth")
    return json.loads(raw) if raw else None


__all__ = [
    "TURKIYE_BBOX", "GRID_RES", "PERIOD", "REQUIRED_ATTRS", "grid_coords", "monthly_time",
    "processed_path", "finalize", "write_netcdf", "check_contract", "truth", "today_iso",
    "TURKIYE_DIR", "RAW_DIR", "PROCESSED_DIR", "CACHE_DIR", "ulke_kutusu", "ulke_dir",
]
