"""Rakım ızgaraları: SRTMGL30 (30″) → 0,05° ve 0,25° ortalama rakım (tüm Türkiye, kara maskeli).

    python -m data.dem          # indir (2 karo, ~40 MB) + işle

Çıktı: cache/processed/turkiye/rakim__SRTM.nc ve rakim__SRTM__005.nc (boyutlar: lat, lon).
"""

from __future__ import annotations

import xarray as xr

from data.catalog import variable
from data.grid import processed_path


def build_dem(force: bool = False) -> list:
    """SRTMGL30'u çekip 0,05° ve 0,25° rakım dosyalarını üretir; yolları döndürür."""
    from data.fetch import fetch_product
    from data.harmonize import harmonize_variable
    v = variable("rakim")
    paths = [processed_path("rakim", v["urun_bilgi"]["dosya_kodu"], g) for g in v["grids"]]
    if all(p.exists() for p in paths) and not force:
        return paths
    fetch_product(v["urun"])
    return harmonize_variable(v)


def load_dem(grid: str = "025") -> xr.DataArray:
    """Rakım DataArray'i (m). Gerçek DEM yoksa sentetik rakıma düşer ve uyarır."""
    import warnings
    v = variable("rakim")
    path = processed_path("rakim", v["urun_bilgi"]["dosya_kodu"], grid)
    if not path.exists():
        syn = processed_path("rakim", "SENTETIK", grid)
        if not syn.exists():
            raise FileNotFoundError(f"{path} yok. Önce: python -m data.dem")
        warnings.warn("Gerçek rakım yok; SENTETİK rakım kullanılıyor (yer tutucu).")
        path = syn
    with xr.open_dataset(path) as ds:
        return ds["rakim"].load()


if __name__ == "__main__":
    for p in build_dem(force=True):
        print(p)
