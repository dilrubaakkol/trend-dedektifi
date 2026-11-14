"""physics/shift.py testleri (sentetik, internetsiz)."""

import numpy as np
import pytest

from physics._gecici_trend import winter_mean
from physics.shift import boundary_shift, snowline_series
from physics.synthetic import (synthetic_dem, synthetic_snow_cube,
                               synthetic_temperature)
from physics.tests_physical import climate_velocity


@pytest.fixture(scope="module")
def z():
    return synthetic_dem(seed=0)


def test_kar_cizgisi_bilinen_degerleri_izler(z):
    k = synthetic_snow_cube(z, kar_cizgisi_m=2200, kayma_m_per_decade=50, seed=0)
    s = snowline_series(k, z)
    gercek = np.array(k.attrs["synthetic_truth"]["yillik_cizgi_m"])
    assert s["n_gecerli"] == 24
    assert np.max(np.abs(np.array(s["rakim_m"]) - gercek)) < 60  # 100 m dilim içinde


def test_bilinen_kayma_araligin_icinde(z):
    """Bitti kriteri (Adım 6): bilinen +50 m/10 yıl kayma aralığın içinde."""
    k = synthetic_snow_cube(z, kayma_m_per_decade=50, seed=0)
    r = boundary_shift(k, z, region="test")
    lo, hi = r["observed_shift_m_per_decade"]
    assert lo <= 50 <= hi
    assert r["type"] == "boundary_shift" and r["id"] == "kayma_rakim_kar_ortusu_test"
    assert r["status"] == "ok" and len(r["snowline"]["kis"]) == 24
    assert r["rolling_15y"]["seri"] and "geçersiz" in r["rolling_15y"]["note"]


def test_kayma_kapsamasi_100_tohum(z):
    hit = sum(lo <= 50 <= hi for lo, hi in
              (boundary_shift(synthetic_snow_cube(z, seed=500 + s), z)["observed_shift_m_per_decade"]
               for s in range(100)))
    print(f"kapsama = {hit / 100:.2f}")
    assert hit >= 90


def test_kar_cizgisi_tanimsiz(z):
    k = synthetic_snow_cube(z, kar_cizgisi_m=7000, seed=1)  # hiçbir yerde %50 yok (kıyı gibi)
    r = boundary_shift(k, z, region="ege")
    assert r["status"] == "undefined" and r["label"] == "yetersiz"
    assert r["observed_shift_m_per_decade"] is None


def test_eksik_kislar_nan_kalir(z):
    k = synthetic_snow_cube(z, seed=2)
    k[3] = np.nan
    s = snowline_series(k, z)
    assert np.isnan(s["rakim_m"][3]) and s["n_gecerli"] == 23


def _tahmin(z025, isinma, seed=1, urun="MERRA2"):
    T = winter_mean(synthetic_temperature(z025, isinma_C_per_decade=isinma,
                                          lapse_C_per_km=6.0, seed=seed))
    return climate_velocity(T, z025, region="test", urun=urun)


@pytest.mark.parametrize("isinma,beklenen", [
    (0.3, "uyumlu"),     # tahmin ~50 m/10 yıl ≈ gözlenen 50
    (1.8, "celiskili"),  # tahmin ~300 m/10 yıl ≫ gözlenen
    (-0.6, "celiskili"), # soğuma: tahmin ters yönde
])
def test_uctan_uca_etiket(z, isinma, beklenen):
    """Gözlenen kayma (kar küpü) + iklim hızı tahmini (sıcaklık küpü) → etiket."""
    z025 = synthetic_dem(grid="025", seed=0)
    k = synthetic_snow_cube(z, kayma_m_per_decade=50, seed=0)
    r = boundary_shift(k, z, tahminler=[_tahmin(z025, isinma),
                                        _tahmin(z025, isinma, seed=2, urun="GLDAS")],
                       region="test")
    assert r["label"] == beklenen, r["label_reason"]
    assert r["predicted_product"] == "MERRA2"
    assert r["predicted_secondary"][0]["product"] == "GLDAS"


def test_kayma_yoksa_yetersiz(z):
    z025 = synthetic_dem(grid="025", seed=0)
    k = synthetic_snow_cube(z, kayma_m_per_decade=0, yillik_oynama_m=80, seed=4)
    r = boundary_shift(k, z, tahminler=[_tahmin(z025, 0.3)])
    assert r["mk_p"] >= 0.05                    # bu tohumda trend anlamsız (p ≈ 0,98)
    assert r["label"] == "yetersiz"             # anlamsız trend → yetersiz (öncelikli kural)
    assert "anlamlı değil" in r["label_reason"]


def test_run_uctan_uca(monkeypatch):
    """physics.run: veri okuma taklit edilir (diske/internete dokunmaz), tüm zincir çalışır."""
    import physics.run_yol_haritasi as run
    from physics.synthetic import synthetic_dem, synthetic_temperature

    z05, z25 = synthetic_dem(seed=0), synthetic_dem(grid="025", seed=0)
    kar_kis = synthetic_snow_cube(z05, seed=0)
    # aylık kar küpü: her kışın değerini o kışın 4 ayına yay (Ara Y-1 … Mar Y)
    import pandas as pd
    import xarray as xr
    zaman = pd.date_range("2001-01", "2025-12", freq="MS")
    kis_of = np.where(zaman.month == 12, zaman.year + 1, zaman.year)
    aylik = np.full((len(zaman),) + z05.shape, np.nan)
    for i, (k, ay) in enumerate(zip(kis_of, zaman.month)):
        if ay in (12, 1, 2, 3) and k in kar_kis.kis.values:
            aylik[i] = kar_kis.sel(kis=k).values
    kar = xr.DataArray(aylik, coords={"time": zaman, "lat": z05.lat, "lon": z05.lon},
                       dims=("time", "lat", "lon"))
    T = synthetic_temperature(z25, isinma_C_per_decade=0.3, seed=1)
    tablo = {("kar_ortusu", "005"): kar, ("rakim", "005"): z05, ("rakim", "025"): z25,
             ("sicaklik_2m", "025"): T}
    monkeypatch.setattr(run, "_yukle", lambda d, r, g, p=None, sentetik=None: (tablo[(d, g)], True))

    s = run.analyze_region("test", n_boot=50)
    tipler = [a["type"] for a in s["analyses"]]
    assert tipler == ["trend_map_summary", "boundary", "mirror", "climate_velocity",
                      "climate_velocity", "boundary_shift"]
    kayma = s["analyses"][-1]
    assert kayma["label"] in ("uyumlu", "celiskili", "yetersiz")
    assert s["sentetik"] is True
    d = run.results_dosyasi("dogu_anadolu", s)
    assert "YER TUTUCU" in d["_not"] and d["region"]["name"] == "dogu_anadolu"
