"""physics/_gecici_trend.py testleri (sentetik, internetsiz)."""

import numpy as np
import pytest

from physics._gecici_trend import lag1_autocorr, trend_1d


def _ar1(n, phi, rng):
    e = np.empty(n)
    e[0] = rng.standard_normal()
    for t in range(1, n):
        e[t] = phi * e[t - 1] + np.sqrt(1 - phi ** 2) * rng.standard_normal()
    return e


def test_dogrusal_seri_tam_egim():
    x = np.arange(2002, 2026)
    y = 3.0 + 0.5 * (x - 2002)
    r = trend_1d(y, x)
    assert r["slope"] == pytest.approx(5.0)  # 0,5/yıl → 5/10 yıl
    assert r["ci95"][0] <= 5.0 <= r["ci95"][1]
    assert r["n"] == 24


def test_nan_atilir_ve_kisa_seri_nan_doner():
    y = np.array([1.0, np.nan, 3.0, 4.0, 5.0, 6.0])
    assert trend_1d(y)["n"] == 5
    kisa = trend_1d([1.0, 2.0, np.nan])
    assert kisa["n"] == 2 and np.isnan(kisa["slope"])


def test_genisletilmis_aralik_ham_araliktan_dar_degil():
    rng = np.random.default_rng(1)
    y = 0.05 * np.arange(24) + _ar1(24, 0.6, rng)
    r = trend_1d(y)
    assert r["ci95"][0] <= r["ci95_ham"][0]
    assert r["ci95"][1] >= r["ci95_ham"][1]
    assert r["genisletme"] >= 1.0


def test_lag1_beyaz_gurultude_sifira_yakin():
    rng = np.random.default_rng(2)
    assert abs(lag1_autocorr(rng.standard_normal(5000))) < 0.05


def test_kapsama_ar1_phi05_24_kis():
    """Bitti kriteri (Adım 2): 1000 seride gerçek trend genişletilmiş aralıkta ≥ %90."""
    rng = np.random.default_rng(2026)
    b, n, N = 0.05, 24, 1000
    x = np.arange(n, dtype=float)
    hit = 0
    for _ in range(N):
        y = b * x + _ar1(n, 0.5, rng)
        lo, hi = trend_1d(y, x, per=1.0)["ci95"]
        hit += lo <= b <= hi
    kapsama = hit / N
    print(f"kapsama = {kapsama:.3f}")
    assert kapsama >= 0.90


def test_duzeltmeler_kapaliyken_planin_formulu():
    rng = np.random.default_rng(3)
    y = 0.05 * np.arange(24) + _ar1(24, 0.5, rng)
    r = trend_1d(y, kucuk_orneklem_duzeltmesi=False, t_duzeltmesi=False)
    assert r["genisletme"] == pytest.approx(np.sqrt(r["n"] / r["n_etkin"]))
