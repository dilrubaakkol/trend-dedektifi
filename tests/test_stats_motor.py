"""stats.trend_tests: Sen + Hamed-Rao motoru, Weatherhead ve BH-FDR (sentetik serilerle).

Kişi 2'nin ilk doğrulama betiğinin (tests/test_motor.py) pytest sürümü; aynı seri ve kontroller.
"""

import numpy as np
import pytest
import xarray as xr
from statsmodels.stats.multitest import multipletests

from stats.trend_tests import bh_fdr, trend_analizi, weatherhead_gereken_yil


def _seri(degerler, yillar=None):
    yillar = np.arange(2001, 2001 + len(degerler)) if yillar is None else yillar
    return xr.DataArray(np.asarray(degerler, float), dims=["yil"], coords={"yil": yillar})


@pytest.fixture()
def bilinen_trend():
    """25 yıllık seri, her yıl −0,5 (on yılda −5 birim) + küçük gürültü (tekrarlanabilir)."""
    rng = np.random.default_rng(42)
    yillar = np.arange(2001, 2026)
    return _seri(50 - 0.5 * (yillar - 2001) + rng.normal(0, 0.25, len(yillar)), yillar)


def test_motor_bilinen_egim(bilinen_trend):
    sonuc = trend_analizi(bilinen_trend)
    assert sonuc["durum"] == "ok" and sonuc["n"] == 25
    assert abs(sonuc["egim_10yil"] - (-5.0)) < 1.0
    assert sonuc["ci_alt"] <= sonuc["egim_10yil"] <= sonuc["ci_ust"]
    assert sonuc["trend"] == "decreasing" and sonuc["p_mk"] < 0.05
    assert "p_mk_kontrol" in sonuc and "belirsiz" in sonuc


def test_duzeltmeler_araligi_genisletir():
    rng = np.random.default_rng(1)
    e = np.zeros(25)
    for i in range(1, 25):                      # AR(1), φ = 0,6
        e[i] = 0.6 * e[i - 1] + rng.normal()
    s = _seri(0.05 * np.arange(25) + e)
    acik = trend_analizi(s)
    kapali = trend_analizi(s, kucuk_orneklem_duzeltmesi=False, t_duzeltmesi=False)
    assert acik["egim_10yil"] == pytest.approx(kapali["egim_10yil"])
    assert (acik["ci_ust"] - acik["ci_alt"]) > (kapali["ci_ust"] - kapali["ci_alt"])
    assert acik["r1"] > acik["r1_ham"] and acik["n_etkin"] <= kapali["n_etkin"]


def test_kontrol_kapali_ve_kenar_durumlar(bilinen_trend):
    assert "belirsiz" not in trend_analizi(bilinen_trend, kontrol=False)
    assert trend_analizi(_seri(np.arange(8.0)))["durum"] == "yetersiz_veri"
    sabit = trend_analizi(_seri(np.full(20, 3.0)))
    assert sabit["durum"] == "sabit_seri" and sabit["egim_10yil"] == 0.0 and sabit["p_mk"] == 1.0


def test_hamed_rao_tanimsizsa_yedek():
    """Güçlü trend + negatif artık otokorelasyonu: Hamed-Rao var_s < 0 → p NaN; yedek MK devreye girer."""
    import pymannkendall as mk
    y = [-1.592, -1.774, -3.55, -3.641, -5.21, -3.265, -3.21, -6.561, -6.815, -8.362, -6.937, -8.622,
         -6.412, -12.591, -10.475, -11.112, -13.521, -12.433, -17.277, -10.962, -18.684, -14.96, -19.842, -16.098]
    with np.errstate(invalid="ignore"):
        assert np.isnan(mk.hamed_rao_modification_test(np.array(y)).p)
    r = trend_analizi(_seri(y))
    assert r["mk_yedek"] is True and 0 <= r["p_mk"] < 0.001 and r["trend"] == "decreasing"
    assert trend_analizi(_seri(np.arange(20.0) + np.sin(np.arange(20))))["mk_yedek"] is False


def test_bosluklu_seri():
    yillar = np.r_[2001:2010, 2013:2026]             # 3 yıllık boşluk
    s = _seri(0.1 * (yillar - 2001), yillar)
    r = trend_analizi(s)
    assert r["n"] == len(yillar) and r["egim_10yil"] == pytest.approx(1.0)


def test_weatherhead_formul_ve_sqrt12():
    rng = np.random.default_rng(3)
    yillar = np.arange(2001, 2026)
    s = _seri(0.02 * (yillar - 2001) + rng.normal(0, 0.2, 25), yillar)
    n1 = weatherhead_gereken_yil(s)
    n12 = weatherhead_gereken_yil(s, ornek_per_yil=12)
    assert n1 > 0 and n1 / n12 == pytest.approx(12 ** (1 / 3), rel=1e-6)   # (√12)^(2/3)
    assert trend_analizi(s)["gereken_yil"] == pytest.approx(n1, rel=1e-6)
    gurultulu = _seri(0.02 * (yillar - 2001) + rng.normal(0, 0.8, 25), yillar)
    assert weatherhead_gereken_yil(gurultulu) > n1
    assert np.isnan(weatherhead_gereken_yil(_seri(np.full(25, 1.0))))


def test_bh_fdr_statsmodels_ile_ayni():
    rng = np.random.default_rng(7)
    p = np.r_[rng.uniform(size=40), rng.uniform(0, 0.005, 10), [np.nan] * 5].reshape(5, 11)
    q, anl = bh_fdr(p, alfa=0.10)
    ok = np.isfinite(p)
    rej, q_ref, _, _ = multipletests(p[ok], alpha=0.10, method="fdr_bh")
    np.testing.assert_allclose(q[ok], q_ref)
    assert (anl[ok] == rej).all() and np.isnan(q[~ok]).all() and not anl[~ok].any()
    assert q.shape == p.shape
