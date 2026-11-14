"""physics/synthetic.py testleri (internetsiz)."""

import numpy as np
import xarray as xr

from physics.synthetic import (KISLAR, synthetic_dem, synthetic_snow_cube,
                               synthetic_trend_map)


def test_dem_izgara_ve_dagilim():
    z = synthetic_dem(seed=0)
    lat, lon = z.lat.values, z.lon.values
    assert np.all(np.diff(lat) > 0)  # lat artan
    assert np.allclose((lat * 1000).round() % 50, 25)  # hücre merkezleri x,x25 / x,x75
    assert np.allclose((lon * 1000).round() % 50, 25)
    v = z.values
    assert 0.5 <= np.mean((v > 1500) & (v < 2200)) <= 0.8  # çoğunluk platoda
    h, e = np.histogram(v, bins=np.arange(0, 5000, 100))
    assert e[np.nonzero(h >= 30)[0].max()] >= 3000  # sınırın üstünde yeterli piksel


def test_trend_isareti_sinirin_iki_yaninda_zit():
    z = synthetic_dem(seed=0)
    t = synthetic_trend_map(z, z0=2650, a=-0.004, gurultu=0.3, seed=1)
    alt = t.values[z.values < 2300]
    ust = t.values[z.values > 3000]
    assert np.median(alt) > 0 > np.median(ust)
    assert t.attrs["synthetic_truth"]["sinir_m"] == 2650


def test_bolgeye_gore_farkli_sinir():
    z = synthetic_dem(seed=0)
    z0 = xr.where(z.lon < 41.0, 1800.0, 2650.0)
    t = synthetic_trend_map(z, z0=z0, gurultu=0.0, korelasyon_derece=0.0)
    bati = (z.lon < 41.0) & (z > 1900) & (z < 2500)
    dogu = (z.lon >= 41.0) & (z > 1900) & (z < 2500)
    assert float(t.where(bati).max()) < 0 < float(t.where(dogu).min())


def test_sinir_yok_her_yerde_ayni_isaret():
    z = synthetic_dem(seed=0)
    t = synthetic_trend_map(z, a=-0.004, gurultu=0.5, sinir_yok=True, seed=3)
    assert np.all(t.values > 0)


def test_nan_rakim_korunur_ve_tohum_tekrarlanir():
    z = synthetic_dem(seed=0)
    z[0, 0] = np.nan
    t1 = synthetic_trend_map(z, seed=5)
    t2 = synthetic_trend_map(z, seed=5)
    assert np.isnan(t1.values[0, 0])
    np.testing.assert_array_equal(t1.values, t2.values)


def test_kar_kupu():
    z = synthetic_dem(seed=0)
    k = synthetic_snow_cube(z, kar_cizgisi_m=2200, kayma_m_per_decade=50, seed=0)
    assert k.dims == ("kis", "lat", "lon")
    assert list(k.kis.values) == list(KISLAR)
    assert float(k.min()) >= 0 and float(k.max()) <= 100
    ilk = k.isel(kis=0)
    assert float(ilk.where(z > 3200).mean()) > 90
    assert float(ilk.where(z < 1400).mean()) < 10
    tr = k.attrs["synthetic_truth"]
    assert tr["kayma_m_per_decade"] == 50 and len(tr["yillik_cizgi_m"]) == len(KISLAR)
