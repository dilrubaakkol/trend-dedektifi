"""Sentetik üretici: sözleşmeye uygunluk ve bilinen parametrelerin geri kazanımı.

Not: Ortak AR(1) bileşeni (r > 0) tüm hücrelerde aynı seridir; bölge ortalamasında bile trend
tahminine örnekleme hatası ekler (gerçekçi). Deterministik kısmı sınayan testler r=0 kullanır.
"""

import numpy as np
import pandas as pd
import pytest

from data.grid import REQUIRED_ATTRS, check_contract, grid_coords, truth
from data.synthetic import ar1, make_synthetic, make_synthetic_elevation, synthetic_elevation


def _ols_trend(ds, name):
    """Hücre başına aylık kukla değişkenli OLS trendi (birim/yıl)."""
    x = ds[name].values
    t = (ds.time.values - ds.time.values[0]).astype("timedelta64[D]").astype(float) / 365.25
    m = ds.time.dt.month.values
    X = np.column_stack([t] + [(m == k).astype(float) for k in range(1, 13)])
    flat = x.reshape(len(t), -1)
    ok = np.isfinite(flat).all(0)
    b = np.full(flat.shape[1], np.nan)
    b[ok] = np.linalg.lstsq(X, flat[:, ok], rcond=None)[0][0]
    return b.reshape(x.shape[1:])


@pytest.fixture(scope="module")
def temp_ds():
    return make_synthetic("sicaklik_2m", seed=1)


def test_contract(temp_ds):
    assert check_contract(temp_ds) == []
    for k in REQUIRED_ATTRS:
        assert k in temp_ds.attrs
    assert temp_ds["sicaklik_2m"].dims == ("time", "lat", "lon")
    assert temp_ds.attrs["source_product"] == "SENTETIK"
    assert "yer_tutucu" in temp_ds.attrs


def test_monthly_time_and_grid(temp_ds):
    t = pd.DatetimeIndex(temp_ds.time.values)
    assert t[0] == pd.Timestamp("2001-01-01") and t[-1] == pd.Timestamp("2025-12-01")
    assert len(t) == 300 and (t.day == 1).all()
    lat, lon = grid_coords("025")
    np.testing.assert_allclose(temp_ds.lat, lat)
    np.testing.assert_allclose(temp_ds.lon, lon)
    assert lat[0] == pytest.approx(34.625) and lon[-1] == pytest.approx(45.375)


def test_land_mask_applied(temp_ds):
    frac = float(temp_ds["sicaklik_2m"].isel(time=0).notnull().mean())
    assert 0.3 < frac < 0.6  # kutunun yaklaşık yarısı Türkiye karası


def test_uniform_trend_recovered():
    ds = make_synthetic("sicaklik_2m", seed=3, sigma=0.5, r=0.0)
    b = _ols_trend(ds, "sicaklik_2m")
    assert np.nanmean(b) == pytest.approx(truth(ds)["trend"], abs=0.005)


def test_elevation_scenario_sign_change():
    ds = make_synthetic("kar_su_esdegeri", seed=4, clip=None, sigma=5.0, r=0.0)
    tr = truth(ds)
    z = synthetic_elevation().values
    b = _ols_trend(ds, "kar_su_esdegeri")
    low = np.nanmean(b[z < tr["esik"] - 300])
    high = np.nanmean(b[z > tr["esik"] + 300])
    assert low == pytest.approx(tr["trend_alt"], abs=0.05)
    assert high == pytest.approx(tr["trend_ust"], abs=0.05)
    assert np.sign(low) != np.sign(high)


def test_latitude_scenario():
    ds = make_synthetic("ndvi", seed=5, clip=None, mask=False, r=0.0)
    tr = truth(ds)
    b = _ols_trend(ds, "ndvi")
    lat = ds.lat.values
    assert np.nanmean(b[lat < tr["esik"] - 0.5]) == pytest.approx(tr["trend_alt"], abs=3e-4)
    assert np.nanmean(b[lat > tr["esik"] + 0.5]) == pytest.approx(tr["trend_ust"], abs=3e-4)


def test_ar1_phi_and_sigma():
    rng = np.random.default_rng(0)
    e = ar1((5000, 1), phi=0.6, sigma=2.0, rng=rng)[:, 0]
    assert np.corrcoef(e[:-1], e[1:])[0, 1] == pytest.approx(0.6, abs=0.05)
    assert e.std() == pytest.approx(2.0, rel=0.1)


def test_truth_attrs_and_determinism():
    a = make_synthetic("yagis", seed=9)
    b = make_synthetic("yagis", seed=9)
    np.testing.assert_array_equal(a["yagis"].values, b["yagis"].values)
    tr = truth(a)
    for k in ("phi", "sigma", "scenario", "seed", "model", "trend_birimi"):
        assert k in tr
    assert float(a["yagis"].min()) >= 0  # clip [0, None]


def test_overrides_and_005():
    ds = make_synthetic("kar_ortusu", grid="005", phi=0.5, start="2001-01", end="2002-12")
    assert truth(ds)["phi"] == 0.5
    assert ds["kar_ortusu"].shape == (24, 170, 410)
    assert float(ds["kar_ortusu"].max()) <= 100


def test_static_elevation():
    ds = make_synthetic_elevation("025")
    assert check_contract(ds, static=True) == []
    assert ds["rakim"].dims == ("lat", "lon")
