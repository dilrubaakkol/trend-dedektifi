"""physics/tests_physical.py testleri (sentetik, internetsiz): label() ve iklim hızı."""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from physics._gecici_trend import winter_mean
from physics.synthetic import synthetic_dem, synthetic_temperature
from physics.tests_physical import climate_velocity, label, lapse_rate


# ------------------------------------------------------------------ label()
@pytest.mark.parametrize("gozlenen,tahmin,beklenen", [
    ([40, 95], [55, 110], "uyumlu"),          # örtüşüyor
    ([150, 250], [55, 110], "celiskili"),     # örtüşmüyor (fazla hızlı)
    ([-80, -20], [55, 110], "celiskili"),     # ters yön
    ([60, 70], [55, 110], "uyumlu"),          # tamamen içinde
])
def test_label_temel(gozlenen, tahmin, beklenen):
    assert label(gozlenen, tahmin)["label"] == beklenen


def test_label_yetersiz_oncelikli():
    # örtüşmese bile önce yetersizlik kontrol edilir (öncelik sırası)
    assert label([150, 250], [55, 110], anlamli=False)["label"] == "yetersiz"
    assert label([40, 95], [55, 110], n=6)["label"] == "yetersiz"
    assert label([-500, 600], [55, 110], max_genislik=300)["label"] == "yetersiz"
    assert label([np.nan, 5], [55, 110])["label"] == "yetersiz"
    assert label([40, 95], None)["label"] == "yetersiz"


def test_label_gerekce_var():
    r = label([150, 250], [55, 110])
    assert set(r) == {"label", "label_reason"} and r["label_reason"]


# ------------------------------------------------------------------ kış ortalaması
def test_winter_mean_aralik_onceki_yildan():
    zaman = pd.date_range("2001-01", "2003-12", freq="MS")
    da = xr.DataArray(np.arange(len(zaman), dtype=float), coords={"time": zaman}, dims="time")
    k = winter_mean(da)
    assert np.isnan(k.sel(kis=2001))                       # Aralık 2000 yok → 2001 kışı düşer
    # 2002 kışı = Ara 2001 (11) + Oca–Mar 2002 (12, 13, 14)
    assert float(k.sel(kis=2002)) == pytest.approx(np.mean([11, 12, 13, 14]))
    assert 2004 not in k.kis.values or np.isnan(k.sel(kis=2004))


# ------------------------------------------------------------------ iklim hızı
@pytest.fixture(scope="module")
def z025():
    return synthetic_dem(grid="025", seed=0)


@pytest.fixture(scope="module")
def kis_T(z025):
    return winter_mean(synthetic_temperature(z025, isinma_C_per_decade=0.4,
                                             lapse_C_per_km=6.0, seed=1))


def test_lapse_rate_olculur(z025, kis_T):
    lr = lapse_rate(kis_T.mean("kis"), z025)
    assert lr["dTdz_C_per_km"] == pytest.approx(-6.0, abs=0.1)


def test_tahmin_gercegi_kapsar(z025, kis_T):
    r = climate_velocity(kis_T, z025, region="test")
    lo, hi = r["predicted_shift_m_per_decade"]
    assert lo <= 0.4 / 6.0 * 1000 <= hi                    # 66,7 m/10 yıl
    assert r["type"] == "climate_velocity" and r["id"].endswith("_MERRA2_test")
    assert "label" not in r                                 # gözlenen yokken etiket yok


def test_tahmin_kapsamasi_20_tohum(z025):
    hit = 0
    for s in range(20):
        k = winter_mean(synthetic_temperature(z025, seed=100 + s))
        lo, hi = climate_velocity(k, z025, seed=s, n_mc=500)["predicted_shift_m_per_decade"]
        hit += lo <= 66.67 <= hi
    assert hit >= 17                                        # ~%95 hedef, 20'de ≥ 17


@pytest.mark.parametrize("gozlenen,beklenen", [
    ({"ci95": [45, 95], "anlamli": True, "n": 24}, "uyumlu"),
    ({"ci95": [180, 260], "anlamli": True, "n": 24}, "celiskili"),
    ({"ci95": [-60, -10], "anlamli": True, "n": 24}, "celiskili"),
    ({"ci95": [45, 95], "anlamli": False, "n": 24}, "yetersiz"),
])
def test_uc_etiket_sentetik(z025, kis_T, gozlenen, beklenen):
    """Bitti kriteri (Adım 5): sentetik girdiyle üç etiketin her biri doğru üretiliyor."""
    r = climate_velocity(kis_T, z025, gozlenen=gozlenen)
    assert r["label"] == beklenen
    assert r["observed_shift_m_per_decade"] == gozlenen["ci95"]


def test_sicaklik_rakimla_azalmiyorsa_yetersiz(z025):
    k = winter_mean(synthetic_temperature(z025, lapse_C_per_km=-2.0, seed=3))  # ters gradyan
    r = climate_velocity(k, z025, gozlenen={"ci95": [40, 90], "anlamli": True, "n": 24})
    assert r["predicted_shift_m_per_decade"] is None
    assert r["label"] == "yetersiz" and "UYARI" in r["note"]


def test_maske_ve_izgara_kontrolu(z025, kis_T):
    m = z025.lon > 41.0
    r = climate_velocity(kis_T, z025, mask=m, region="dogu")
    assert r["dTdz_n_cells"] == int(m.broadcast_like(z025).sum())
    with pytest.raises(ValueError):
        climate_velocity(kis_T, z025.isel(lat=slice(1, None)))
