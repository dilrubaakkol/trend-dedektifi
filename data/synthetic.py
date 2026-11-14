"""Sözleşmeye uygun SENTETİK NetCDF üretici (tüm Türkiye kutusu).

Gerçek veri gelene kadar ekip (istatistik, fizik, arayüz) bu dosyalarla çalışır.
Her değer şu modelden üretilir (t_yil = (zaman - başlangıç) / 365.25 gün):

    x(t, lat, lon) = taban(z, lat) + trend(z, lat) * t_yil
                     + genlik * cos(2*pi*(ay - tepe_ayi) / 12)
                     + gürültü(t, lat, lon)

    gürültü = sqrt(r) * ortak_AR1(t) + sqrt(1 - r) * yerel_AR1(t, lat, lon)
    AR1: e[t] = phi * e[t-1] + sigma * sqrt(1 - phi²) * N(0, 1)   (marjinal std = sigma)

Trend senaryoları:
  - "uniform":   her yerde aynı trend (``trend``)
  - "elevation": rakım ``esik`` altında ``trend_alt``, üstünde ``trend_ust`` (tanh geçişi, ``genislik``)
  - "latitude":  enlem ``esik`` altında ``trend_alt``, üstünde ``trend_ust``

Gerçek (doğru) parametrelerin tamamı ``attrs["synthetic_truth"]`` içinde JSON olarak durur;
``data.grid.truth(ds)`` ile sözlük olarak okunur. Rakım, sentetik bir topoğrafyadır
(``rakim__SENTETIK.nc``); rakıma bağlı senaryo bu alanı kullanır.

TÜM SAYILAR YER TUTUCUDUR: gerçek iklim değerleri değil, test için seçilmiş makul büyüklüklerdir.

Kullanım:
    python -m data.synthetic                      # tüm hazır değişkenler
    python -m data.synthetic --vars sicaklik_2m,kar_ortusu --phi 0.5 --seed 7
"""

from __future__ import annotations

import argparse
import copy
import json

import numpy as np
import xarray as xr

from data.grid import (PERIOD, finalize, grid_coords, monthly_time, processed_path,
                       today_iso, write_netcdf)

URUN = "SENTETIK"
VERSION = "synthetic-1"

# Hazır değişken ayarları — YER TUTUCU değerler.
# taban = b0 + b_z * rakim[m] + b_lat * (lat - 39);  genlik = a0 + a_z * rakim[m]
PRESETS: dict[str, dict] = {
    "sicaklik_2m": dict(units="°C", long_name="2 m hava sıcaklığı (sentetik)", domain="land",
                        b0=16.0, b_z=-0.0065, b_lat=-0.6, a0=11.0, a_z=0.0, tepe_ayi=7.3,
                        scenario="uniform", trend=0.045, phi=0.3, sigma=1.2, r=0.7, clip=None),
    "yagis": dict(units="mm/ay", long_name="Toplam yağış (sentetik)", domain="land",
                  b0=45.0, b_z=0.01, b_lat=2.0, a0=25.0, a_z=0.0, tepe_ayi=1.0,
                  scenario="latitude", esik=39.5, genislik=0.05, trend_alt=-0.15, trend_ust=0.05,
                  phi=0.1, sigma=18.0, r=0.4, clip=[0.0, None]),
    "kar_ortusu": dict(units="%", long_name="Kar örtüsü oranı (sentetik)", domain="land",
                       b0=-60.0, b_z=0.045, b_lat=3.0, a0=45.0, a_z=0.0, tepe_ayi=1.5,
                       scenario="elevation", esik=1800.0, genislik=25.0,
                       trend_alt=-0.6, trend_ust=0.3, phi=0.3, sigma=8.0, r=0.5,
                       clip=[0.0, 100.0], grids=["025", "005"]),
    "kar_su_esdegeri": dict(units="mm", long_name="Kar su eşdeğeri (sentetik)", domain="land",
                            b0=-150.0, b_z=0.12, b_lat=5.0, a0=100.0, a_z=0.0, tepe_ayi=2.5,
                            scenario="elevation", esik=2000.0, genislik=25.0,
                            trend_alt=-0.8, trend_ust=0.5, phi=0.4, sigma=20.0, r=0.5,
                            clip=[0.0, None]),
    "toprak_nemi": dict(units="kg/m²", long_name="Toprak nemi (sentetik)", domain="land",
                        b0=25.0, b_z=0.0, b_lat=1.5, a0=8.0, a_z=0.0, tepe_ayi=2.0,
                        scenario="uniform", trend=-0.05, phi=0.6, sigma=3.0, r=0.5,
                        clip=[0.0, None]),
    "buharlasma": dict(units="mm/ay", long_name="Buharlaşma (sentetik)", domain="land",
                       b0=40.0, b_z=-0.005, b_lat=0.0, a0=35.0, a_z=0.0, tepe_ayi=5.5,
                       scenario="uniform", trend=-0.1, phi=0.3, sigma=6.0, r=0.5,
                       clip=[0.0, None]),
    "yuzey_akisi": dict(units="mm/ay", long_name="Yüzey akışı (sentetik)", domain="land",
                        b0=5.0, b_z=0.001, b_lat=0.5, a0=4.0, a_z=0.0, tepe_ayi=3.0,
                        scenario="uniform", trend=-0.03, phi=0.3, sigma=2.0, r=0.4,
                        clip=[0.0, None]),
    "ndvi": dict(units="1", long_name="NDVI (sentetik)", domain="land",
                 b0=0.38, b_z=-0.0001, b_lat=0.02, a0=0.12, a_z=0.0, tepe_ayi=5.0,
                 scenario="latitude", esik=38.5, genislik=0.05,
                 trend_alt=-0.001, trend_ust=0.0015, phi=0.4, sigma=0.03, r=0.5,
                 clip=[-0.2, 1.0]),
    "deniz_yuzey_sicakligi": dict(units="°C", long_name="Deniz yüzeyi sıcaklığı (sentetik)",
                                  domain="ocean", b0=19.0, b_z=0.0, b_lat=-0.8, a0=6.0, a_z=0.0,
                                  tepe_ayi=8.0, scenario="uniform", trend=0.05,
                                  phi=0.5, sigma=0.5, r=0.8, clip=None),
}

PARAM_KEYS = ("b0", "b_z", "b_lat", "a0", "a_z", "tepe_ayi", "scenario", "trend", "esik",
              "genislik", "trend_alt", "trend_ust", "phi", "sigma", "r", "clip")


def synthetic_elevation(grid: str = "025") -> xr.DataArray:
    """Türkiye'ye kabaca benzeyen sentetik rakım (m) — YER TUTUCU, gerçek DEM değildir.

    Batıdan doğuya yükselen plato + Kuzey Anadolu (Karadeniz) ve Toros sırtları + Ağrı tepesi.
    Değerler 0 … ~4000 m arasında kalır.
    """
    lat, lon = grid_coords(grid)
    LON, LAT = np.meshgrid(lon, lat)
    z = 150.0 + 1700.0 * np.clip((LON - 26.0) / 18.0, 0.0, 1.0)            # doğuya yükselen plato
    z += 1400.0 * np.exp(-((LAT - 40.8) / 0.35) ** 2) * (LON > 31) * (LON < 42.5)  # Karadeniz sırtı
    z += 1500.0 * np.exp(-((LAT - 37.3) / 0.35) ** 2) * (LON > 29) * (LON < 37)    # Toroslar
    z += 2200.0 * np.exp(-(((LAT - 39.7) / 0.3) ** 2 + ((LON - 44.3) / 0.3) ** 2))  # Ağrı
    z = np.clip(z, 0.0, None).astype("float32")
    return xr.DataArray(z, coords={"lat": lat, "lon": lon}, dims=("lat", "lon"), name="rakim")


def trend_map(params: dict, z: np.ndarray, lat2d: np.ndarray) -> np.ndarray:
    """Senaryoya göre hücre başına gerçek trend (birim/yıl) haritasını döndürür."""
    sc = params["scenario"]
    if sc == "uniform":
        return np.full_like(z, params["trend"], dtype="float64")
    if sc in ("elevation", "latitude"):
        axis = z if sc == "elevation" else lat2d
        w = 0.5 * (1.0 + np.tanh((axis - params["esik"]) / params["genislik"]))
        return params["trend_alt"] + (params["trend_ust"] - params["trend_alt"]) * w
    raise ValueError(f"Bilinmeyen senaryo: {sc}")


def ar1(shape: tuple, phi: float, sigma: float, rng: np.random.Generator) -> np.ndarray:
    """İlk eksen zaman olmak üzere durağan AR(1) gürültü (marjinal std = sigma)."""
    if not -1.0 < phi < 1.0:
        raise ValueError("phi (-1, 1) aralığında olmalı")
    out = np.empty(shape, dtype="float64")
    out[0] = sigma * rng.standard_normal(shape[1:])
    innov = sigma * np.sqrt(1.0 - phi ** 2)
    for t in range(1, shape[0]):
        out[t] = phi * out[t - 1] + innov * rng.standard_normal(shape[1:])
    return out


def _domain_mask(domain: str, grid: str) -> np.ndarray | None:
    """Kara/deniz maskesi (True = geçerli hücre). Sınır dosyaları yoksa None."""
    if domain == "all":
        return None
    try:
        from data.regions import domain_mask
    except Exception:  # regions henüz hazır değilse maskesiz devam
        return None
    lat, lon = grid_coords(grid)
    try:
        return domain_mask(domain, lat, lon)
    except FileNotFoundError:
        return None


def make_synthetic(degisken: str = "sicaklik_2m", grid: str = "025",
                   start: str = PERIOD[0], end: str = PERIOD[1], seed: int = 42,
                   mask: bool = True, **overrides) -> xr.Dataset:
    """Bir değişken için sözleşmeye uygun sentetik Dataset üretir.

    Parametreler:
        degisken: PRESETS içindeki ad ya da yeni bir ad (o zaman tüm parametreler overrides ile).
        grid: "025" ya da "005".
        seed: rastgele sayı tohumu (aynı tohum → aynı dosya).
        mask: True ise domain'e göre kara/deniz maskesi uygulanır (sınır dosyaları varsa).
        overrides: PRESETS anahtarlarını ezer (ör. phi=0.6, scenario="elevation", trend_alt=-1).

    Döndürür: tek değişkenli xr.Dataset, boyutlar (time, lat, lon), attrs sözleşmeye uygun +
    ``synthetic_truth``.
    """
    p = copy.deepcopy(PRESETS.get(degisken, {}))
    p.update(overrides)
    p.setdefault("units", "1")
    p.setdefault("long_name", f"{degisken} (sentetik)")
    p.setdefault("domain", "land")
    for k, v in dict(b0=0.0, b_z=0.0, b_lat=0.0, a0=1.0, a_z=0.0, tepe_ayi=1.0,
                     scenario="uniform", trend=0.0, phi=0.3, sigma=1.0, r=0.5, clip=None).items():
        p.setdefault(k, v)

    rng = np.random.default_rng(seed)
    time = monthly_time(start, end)
    lat, lon = grid_coords(grid)
    z = synthetic_elevation(grid).values.astype("float64")
    lat2d = np.broadcast_to(lat[:, None], z.shape)

    t_yil = ((time - time[0]).days.values / 365.25)[:, None, None]
    month = time.month.values[:, None, None]
    base = p["b0"] + p["b_z"] * z + p["b_lat"] * (lat2d - 39.0)
    amp = p["a0"] + p["a_z"] * z
    tr = trend_map(p, z, lat2d)

    shape = (time.size, lat.size, lon.size)
    common = ar1((time.size, 1, 1), p["phi"], p["sigma"], rng)
    local = ar1(shape, p["phi"], p["sigma"], rng)
    noise = np.sqrt(p["r"]) * common + np.sqrt(1.0 - p["r"]) * local

    x = base + tr * t_yil + amp * np.cos(2 * np.pi * (month - p["tepe_ayi"]) / 12.0) + noise
    if p["clip"] is not None:
        lo, hi = p["clip"]
        x = np.clip(x, lo if lo is not None else -np.inf, hi if hi is not None else np.inf)

    processing = ["sentetik üretim (taban + trend + mevsim + AR(1) gürültü)"]
    m = _domain_mask(p["domain"], grid) if mask else None
    if m is not None:
        x = np.where(m[None, :, :], x, np.nan)
        processing.append(f"{p['domain']} maskesi")
    elif p["domain"] != "all":
        processing.append("maske uygulanmadı (sınır dosyası yok)")
    if p["clip"] is not None:
        processing.append(f"aralığa kırpma {p['clip']}")

    truth = {k: p[k] for k in PARAM_KEYS if k in p}
    truth.update(
        degisken=degisken, seed=seed, trend_birimi=f"{p['units']}/yıl",
        t_tanimi=f"t_yil = (zaman - {time[0].date()}) / 365.25 gün",
        model="x = b0 + b_z*rakim + b_lat*(lat-39) + trend*t_yil + (a0 + a_z*rakim)"
              "*cos(2*pi*(ay - tepe_ayi)/12) + sqrt(r)*ortakAR1 + sqrt(1-r)*yerelAR1",
        rakim_kaynagi="rakim__SENTETIK.nc (synthetic_elevation)",
        not_="Kırpma (clip) varsa gözlenen trend, gerçek trendden sapabilir.",
    )
    if p["scenario"] == "uniform":
        truth["trend_per_decade"] = p["trend"] * 10
    else:
        truth["trend_alt_per_decade"] = p["trend_alt"] * 10
        truth["trend_ust_per_decade"] = p["trend_ust"] * 10

    da = xr.DataArray(x, coords={"time": time, "lat": lat, "lon": lon},
                      dims=("time", "lat", "lon"), name=degisken)
    attrs = dict(
        units=p["units"], long_name=p["long_name"], source_product=URUN,
        source_version=VERSION, doi="yok (sentetik veri)", daac="yok (sentetik veri)",
        download_date=today_iso(), processing="; ".join(processing), grid=grid,
        domain=p["domain"], valid_start=f"{time[0]:%Y-%m}", synthetic_truth=truth,
        yer_tutucu="EVET — bu dosya sentetiktir, gerçek gözlem değildir",
    )
    return finalize(da, attrs)


def make_synthetic_elevation(grid: str = "025", mask: bool = True) -> xr.Dataset:
    """Sentetik rakım Dataset'i (sabit alan: boyutlar lat, lon)."""
    da = synthetic_elevation(grid)
    processing = ["sentetik topoğrafya (plato + sırtlar)"]
    m = _domain_mask("land", grid) if mask else None
    if m is not None:
        da = da.where(m)
        processing.append("land maskesi")
    attrs = dict(units="m", long_name="Rakım (sentetik)", source_product=URUN,
                 source_version=VERSION, doi="yok (sentetik veri)", daac="yok (sentetik veri)",
                 download_date=today_iso(), processing="; ".join(processing), grid=grid,
                 domain="land", valid_start="sabit",
                 synthetic_truth={"aciklama": "synthetic_elevation() formülü"},
                 yer_tutucu="EVET — bu dosya sentetiktir, gerçek gözlem değildir")
    return finalize(da, attrs)


def main(argv=None) -> None:
    """Komut satırı: seçili değişkenler için sentetik dosyaları cache/processed/turkiye/ altına yazar."""
    ap = argparse.ArgumentParser(description="Sentetik Trend Dedektifi verisi üret.")
    ap.add_argument("--vars", default="all",
                    help=f"virgülle ayrılmış liste ya da 'all'. Hazır: {','.join(PRESETS)},rakim")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--phi", type=float, default=None, help="tüm değişkenler için AR(1) phi")
    ap.add_argument("--scenario", choices=["uniform", "elevation", "latitude"], default=None)
    ap.add_argument("--no-mask", action="store_true", help="kara/deniz maskesi uygulama")
    a = ap.parse_args(argv)

    names = list(PRESETS) + ["rakim"] if a.vars == "all" else a.vars.split(",")
    ov = {}
    if a.phi is not None:
        ov["phi"] = a.phi
    if a.scenario is not None:
        ov["scenario"] = a.scenario
        ov.setdefault("esik", 1800.0 if a.scenario == "elevation" else 39.0)
        ov.setdefault("genislik", 25.0 if a.scenario == "elevation" else 0.05)
        ov.setdefault("trend_alt", -0.5)
        ov.setdefault("trend_ust", 0.5)

    for i, name in enumerate(names):
        name = name.strip()
        grids = ["025", "005"] if name == "rakim" else PRESETS.get(name, {}).get("grids", ["025"])
        for g in grids:
            if name == "rakim":
                ds = make_synthetic_elevation(g, mask=not a.no_mask)
            else:
                ds = make_synthetic(name, grid=g, seed=a.seed + i, mask=not a.no_mask, **ov)
            path = write_netcdf(ds, processed_path(name, URUN, g))
            da = ds[name]
            nan = float(da.isnull().mean())
            t = ds.attrs.get("synthetic_truth", "{}")
            sc = json.loads(t).get("scenario", "-")
            print(f"  {path.relative_to(path.parents[3])}  {dict(da.sizes)}  "
                  f"senaryo={sc}  NaN={nan:.0%}")
    print("Bitti. Tüm değerler YER TUTUCU (sentetik).")


if __name__ == "__main__":
    main()
