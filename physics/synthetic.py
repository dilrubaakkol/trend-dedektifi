"""Kişi 3 testleri için sentetik veri: rakım, trend haritası ve kış kar örtüsü küpü.

TÜM SAYILAR YER TUTUCUDUR. Bu modül yalnızca testler ve geliştirme içindir; gerçek analizde
kullanılmaz. Bilinen "gerçek" değerler (sınır, kayma hızı) her çıktının ``attrs`` alanında
``synthetic_truth`` olarak durur, böylece fonksiyonların bunu geri bulup bulmadığı sınanır.

Izgara, ``data.grid.grid_coords`` ile sözleşmeye uygun kurulur (hücre merkezleri; ``lat`` artan).

VARSAYIM: Kış serisi için boyut adı ``kis`` (kış yılı, tamsayı; kış Y = Aralık Y−1 + Ocak–Mart Y).
Kişi 2'nin ``winter_series`` çıktı biçimi kesinleşince buna uydurulur.
"""

from __future__ import annotations

import numpy as np
import xarray as xr
from scipy.ndimage import gaussian_filter

from data.grid import GRID_RES, grid_coords

# Demo kutusu (batı, güney, doğu, kuzey) — data/regions.py'deki "demo:dogu_anadolu" ile aynı.
DOGU_ANADOLU_BBOX = (38.0, 37.5, 44.0, 41.5)
KISLAR = np.arange(2002, 2026)  # 24 kış (Kararlar, madde 5)


def _smooth_noise(shape, sigma_cells: float, rng: np.random.Generator) -> np.ndarray:
    """Standart sapması 1 olan, Gauss filtresiyle mekânsal olarak ilişkilendirilmiş gürültü."""
    w = rng.standard_normal(shape)
    if sigma_cells > 0:
        w = gaussian_filter(w, sigma=sigma_cells, mode="reflect")
    s = w.std()
    return w / s if s > 0 else w


def synthetic_dem(grid: str = "005", bbox=DOGU_ANADOLU_BBOX, seed: int = 0,
                  plato_m: float = 1750.0, n_dag: int = 14) -> xr.DataArray:
    """Doğu Anadolu benzeri sentetik rakım (m) — YER TUTUCU, gerçek DEM değildir.

    Geniş bir plato (çoğu hücre ~1400–2200 m) üzerine rastgele dağlar (Gauss tepeler) eklenir;
    yüksek dağlar az yer kaplar ama 100 m dilimlerde yeterli piksel bırakacak kadar geniştir.
    """
    rng = np.random.default_rng(seed)
    lat, lon = grid_coords(grid, bbox)
    LON, LAT = np.meshgrid(lon, lat)
    res = GRID_RES[grid]
    z = plato_m + 250.0 * _smooth_noise(LAT.shape, 1.0 / res, rng)  # ~1° ölçekli dalgalanma
    for _ in range(n_dag):
        c_lat = rng.uniform(lat.min(), lat.max())
        c_lon = rng.uniform(lon.min(), lon.max())
        yuk = rng.uniform(500.0, 1300.0)
        gen = rng.uniform(0.25, 0.6)
        z += yuk * np.exp(-(((LAT - c_lat) / gen) ** 2 + ((LON - c_lon) / gen) ** 2))
    z += 60.0 * _smooth_noise(LAT.shape, 0.1 / res, rng)  # küçük ölçekli pürüz
    z = np.clip(z, 0.0, None).astype("float64")
    return xr.DataArray(z, coords={"lat": lat, "lon": lon}, dims=("lat", "lon"), name="rakim",
                        attrs={"units": "m", "yer_tutucu": "evet", "grid": grid})


def synthetic_trend_map(rakim: xr.DataArray, z0=2650.0, a: float = -0.004,
                        gurultu: float = 0.5, korelasyon_derece: float = 0.15,
                        seed: int = 0, sinir_yok: bool = False) -> xr.DataArray:
    """Rakıma bağlı sentetik trend haritası: trend = a·(rakım − z0) + ilişkili gürültü.

    Parametreler
    ----------
    rakim : DataArray (lat, lon), m. NaN hücreler çıktıda da NaN.
    z0 : float ya da DataArray
        Bilinen sınır (m). Bölgeye göre farklı sınır için ``rakim`` ile aynı ızgarada bir
        DataArray verilebilir (ör. bir bölgede 2650, diğerinde 1800).
    a : float
        Rakım başına trend (birim/10 yıl/m). Negatif → sınırın altı pozitif, üstü negatif.
    gurultu : float
        Gürültünün standart sapması (trend birimi).
    korelasyon_derece : float
        Gauss filtresinin ölçeği (derece). 0 → beyaz gürültü.
    sinir_yok : bool
        True ise her yerde aynı işaret: işaret ``a``'nın tersi, değer sınırdan uzak tutulur.
    """
    rng = np.random.default_rng(seed)
    res = float(abs(rakim.lat.values[1] - rakim.lat.values[0]))
    z = rakim.values.astype(float)
    noise = gurultu * _smooth_noise(z.shape, korelasyon_derece / res, rng)
    z0_val = z0.values if isinstance(z0, xr.DataArray) else float(z0)

    if sinir_yok:
        zmin = np.nanmin(z)
        # Her yerde aynı işaret: |a|·(z − zmin) + 6σ kayma; gürültü ±5σ'da kırpılır.
        trend = -np.sign(a) * (abs(a) * (z - zmin) + 6.0 * gurultu) \
            + np.clip(noise, -5 * gurultu, 5 * gurultu)
        gercek = {"sinir_m": None}
    else:
        trend = a * (z - z0_val) + noise
        gercek = {"sinir_m": (None if isinstance(z0, xr.DataArray) else float(z0))}

    trend[~np.isfinite(z)] = np.nan
    gercek.update(a=a, gurultu=gurultu, korelasyon_derece=korelasyon_derece, seed=seed,
                  sinir_yok=sinir_yok)
    return xr.DataArray(trend, coords=rakim.coords, dims=rakim.dims, name="trend",
                        attrs={"units": "birim/10 yıl", "yer_tutucu": "evet",
                               "synthetic_truth": gercek})


def synthetic_snow_cube(rakim: xr.DataArray, kar_cizgisi_m: float = 2200.0,
                        kayma_m_per_decade: float = 50.0, gecis_genisligi_m: float = 250.0,
                        gurultu: float = 10.0, yillik_oynama_m: float = 60.0,
                        korelasyon_derece: float = 0.15, kislar=KISLAR,
                        seed: int = 0) -> xr.DataArray:
    """Sentetik kış ortalaması kar örtüsü (%), boyutlar (kis, lat, lon).

    Kar çizgisi ilk kışta ``kar_cizgisi_m``'dir ve ``kayma_m_per_decade`` hızıyla yükselir;
    her kış ayrıca ``yillik_oynama_m`` std'li rastgele oynar. Kar örtüsü rakımın lojistik
    fonksiyonudur (kar çizgisinde %50), üstüne ilişkili gürültü eklenir ve 0–100'e kırpılır.
    """
    rng = np.random.default_rng(seed)
    kislar = np.asarray(kislar)
    res = float(abs(rakim.lat.values[1] - rakim.lat.values[0]))
    z = rakim.values.astype(float)
    t = (kislar - kislar[0]) / 10.0
    cizgi = kar_cizgisi_m + kayma_m_per_decade * t + yillik_oynama_m * rng.standard_normal(t.size)

    out = np.empty((kislar.size,) + z.shape)
    for i, zc in enumerate(cizgi):
        cover = 100.0 / (1.0 + np.exp(-(z - zc) / (gecis_genisligi_m / 4.0)))
        cover += gurultu * _smooth_noise(z.shape, korelasyon_derece / res, rng)
        out[i] = np.clip(cover, 0.0, 100.0)
    out[:, ~np.isfinite(z)] = np.nan

    gercek = dict(kar_cizgisi_m=kar_cizgisi_m, kayma_m_per_decade=kayma_m_per_decade,
                  yillik_cizgi_m=[float(c) for c in cizgi], seed=seed)
    return xr.DataArray(out, coords={"kis": kislar, "lat": rakim.lat, "lon": rakim.lon},
                        dims=("kis", "lat", "lon"), name="kar_ortusu",
                        attrs={"units": "%", "yer_tutucu": "evet", "synthetic_truth": gercek})


def synthetic_temperature(rakim: xr.DataArray, isinma_C_per_decade: float = 0.4,
                          lapse_C_per_km: float = 6.0, t0_C: float = 8.0,
                          enlem_C_per_deg: float = -0.5, mevsim_genlik_C: float = 12.0,
                          ortak_gurultu_C: float = 0.8, yerel_gurultu_C: float = 0.4,
                          baslangic: str = "2000-12", bitis: str = "2025-12",
                          seed: int = 0) -> xr.DataArray:
    """Sentetik aylık 2 m sıcaklık (°C), boyutlar (time, lat, lon) — YER TUTUCU.

    T = t0 − lapse·rakım[km] + enlem_katsayısı·(lat − 39) + ısınma·yıl/10
        + mevsim (Ocak en soğuk) + bölge geneli yıllık gürültü + yerel gürültü.
    Bilinen değerler ``attrs["synthetic_truth"]``'ta: beklenen kar çizgisi kayması
    = ısınma / lapse × 1000 (m/10 yıl).
    """
    import pandas as pd
    rng = np.random.default_rng(seed)
    zaman = pd.date_range(baslangic, bitis, freq="MS")
    z = rakim.transpose("lat", "lon").values.astype(float) / 1000.0
    LAT = np.broadcast_to(rakim.lat.values[:, None], z.shape)
    taban = t0_C - lapse_C_per_km * z + enlem_C_per_deg * (LAT - 39.0)
    yil = (zaman.year + (zaman.month - 1) / 12.0 - zaman.year[0]).values
    mevsim = -mevsim_genlik_C * np.cos(2 * np.pi * (zaman.month.values - 1) / 12.0)
    ortak = ortak_gurultu_C * rng.standard_normal(len(zaman))
    out = (taban[None] + (isinma_C_per_decade * yil / 10.0 + mevsim + ortak)[:, None, None]
           + yerel_gurultu_C * rng.standard_normal((len(zaman),) + z.shape))
    out[:, ~np.isfinite(z)] = np.nan
    gercek = dict(isinma_C_per_decade=isinma_C_per_decade, lapse_C_per_km=lapse_C_per_km,
                  beklenen_kayma_m_per_decade=isinma_C_per_decade / lapse_C_per_km * 1000.0,
                  seed=seed)
    return xr.DataArray(out, coords={"time": zaman, "lat": rakim.lat, "lon": rakim.lon},
                        dims=("time", "lat", "lon"), name="sicaklik_2m",
                        attrs={"units": "°C", "yer_tutucu": "evet", "synthetic_truth": gercek})
