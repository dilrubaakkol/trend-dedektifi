"""physics/iliski.py testleri (Faz 1; sentetik, internetsiz).

Kabul ölçütleri (KISI3_PLAN.md, Faz 1):
- ilişkisiz ve otokorelasyonlu seri çiftlerinde "anlamlı" oranı %3–7,
- bilinen korelasyon geri bulunur,
- tuzak: ikisi de artan ama ilgisiz seriler ``anlamsiz`` çıkar,
- işaret ters verilirse ``ters_yonde``.
"""

import numpy as np
import pytest
from scipy.signal import lfilter
from statsmodels.stats.multitest import multipletests

from physics.iliski import bh_fdr, etkin_n, gecikme1, iliski_1d, p_degeri, trend_cikar


def _ar1(rng, n, phi):
    return lfilter([1], [1, -phi], rng.standard_normal(n + 50))[50:]


def _iliskili(rng, n, rho, phi=0.0):
    """Korelasyonu ``rho`` olan iki AR(1) seri (ortak bileşen yöntemi)."""
    a, b = _ar1(rng, n, phi), _ar1(rng, n, phi)
    return a, rho * a + np.sqrt(1 - rho ** 2) * b


# ------------------------------------------------------------------ kabul testi: sahte alarm
@pytest.mark.parametrize("n,phi", [(24, 0.0), (24, 0.6), (99, 0.3)])
def test_iliskisiz_seride_anlamli_orani_3_7(n, phi):
    rng = np.random.default_rng(10)
    k = sum(iliski_1d(_ar1(rng, n, phi), _ar1(rng, n, phi), 1)["anlamli"] for _ in range(1000))
    print(f"n={n} phi={phi} anlamlı oranı = {k / 1000:.3f}")
    assert 0.03 <= k / 1000 <= 0.07


def test_kucuk_orneklem_duzeltmesi_gerekli():
    """Düzeltme kapalıyken 24 yıllık hafızalı serilerde sahte alarm %7'yi aşar (neden açık?)."""
    rng = np.random.default_rng(10)
    k = sum(iliski_1d(_ar1(rng, 24, 0.6), _ar1(rng, 24, 0.6), 1,
                      kucuk_orneklem_duzeltmesi=False)["anlamli"] for _ in range(1000))
    assert k / 1000 > 0.07


# ------------------------------------------------------------------ bilinen ilişki
def test_bilinen_korelasyon_geri_bulunur():
    rng = np.random.default_rng(1)
    rs = [iliski_1d(*_iliskili(rng, 99, 0.6), 1)["r"] for _ in range(300)]
    assert np.mean(rs) == pytest.approx(0.6, abs=0.03)


@pytest.mark.parametrize("rho,beklenen,sonuc", [
    (0.8, 1, "beklenen_yonde"),
    (-0.8, -1, "beklenen_yonde"),   # ör. sıcaklık ~ kar: zıt yönde beklenir
    (-0.8, 1, "ters_yonde"),
    (0.8, -1, "ters_yonde"),
])
def test_etiket_isaret(rho, beklenen, sonuc):
    x, y = _iliskili(np.random.default_rng(2), 24, rho)
    r = iliski_1d(x, y, beklenen)
    assert r["anlamli"] and r["etiket"] == sonuc


def test_ilgisiz_seri_anlamsiz_etiketi():
    rng = np.random.default_rng(3)
    etiketler = [iliski_1d(_ar1(rng, 24, 0), _ar1(rng, 24, 0), 1)["etiket"] for _ in range(200)]
    assert etiketler.count("anlamsiz") / 200 > 0.9


# ------------------------------------------------------------------ tuzak: ortak trend
def test_ortak_trend_tuzagi():
    """İki seri de yıllar içinde artıyor ama yıldan yıla oynamaları ilgisiz → anlamsiz.

    Trend çıkarılmasaydı neredeyse her seferinde güçlü "ilişki" çıkardı.
    """
    rng = np.random.default_rng(4)
    t = np.arange(24.0)
    anlamli, ham_r = 0, []
    for _ in range(500):
        x = 0.3 * t + rng.standard_normal(24)
        y = 0.5 * t + rng.standard_normal(24)
        ham_r.append(np.corrcoef(x, y)[0, 1])
        anlamli += iliski_1d(x, y, 1, t=t)["anlamli"]
    assert np.mean(ham_r) > 0.8          # tuzak gerçek: ham korelasyon çok yüksek
    assert anlamli / 500 <= 0.07         # trend çıkarılınca tesadüf düzeyinde


# ------------------------------------------------------------------ eksik veri ve sınır durumları
def test_nan_adimlar_iki_seriden_de_atilir():
    x, y = _iliskili(np.random.default_rng(5), 24, 0.8)
    x[[0, 5]] = np.nan
    y[[5, 10, 17]] = np.nan                 # GRACE boşluğu gibi
    r = iliski_1d(x, y, 1)
    assert r["n"] == 20 and r["etiket"] == "beklenen_yonde"


def test_kisa_seri_hesaplanmaz():
    r = iliski_1d(np.arange(6.0), np.arange(6.0) ** 2, 1)
    assert r["etiket"] is None and not r["anlamli"] and np.isnan(r["p"])


def test_sabit_seri_hesaplanmaz():
    r = iliski_1d(np.ones(24), np.random.default_rng(0).standard_normal(24), 1)
    assert r["etiket"] is None


def test_beklenen_isaret_dogrulanir():
    with pytest.raises(ValueError):
        iliski_1d(np.zeros(10), np.zeros(10), 0)


def test_etkin_n_sinirlari():
    assert etkin_n(24, 0.0, 0.5) == 24
    assert etkin_n(24, 0.5, 0.5) == pytest.approx(24 * 0.75 / 1.25)
    assert etkin_n(24, -0.5, 0.5) == 24          # n'yi aşamaz
    assert etkin_n(24, 0.99, 0.99) == 3          # en az 3


def test_p_degeri_bilinen():
    # r = 0, p = 1; r büyüdükçe p küçülür
    assert p_degeri(0.0, 24) == pytest.approx(1.0)
    assert p_degeri(0.6, 24) < p_degeri(0.6, 10) < 0.1


def test_trend_cikar_dogruyu_siler():
    t = np.arange(20.0)
    assert np.allclose(trend_cikar(3 + 2 * t, t), 0, atol=1e-9)


def test_gecikme1_bosluklu_seri():
    z = np.array([1, 2, np.nan, 4, 5, 6, 7, 8, 9, 10], float)
    assert np.isfinite(gecikme1(z))


# ------------------------------------------------------------------ FDR
def test_bh_fdr_statsmodels_ile_ayni():
    p = np.random.default_rng(6).uniform(0, 0.2, 300)
    p[::17] = np.nan
    q = bh_fdr(p)
    ok = np.isfinite(p)
    beklenen = multipletests(p[ok], method="fdr_bh")[1]
    assert np.allclose(q[ok], beklenen) and np.all(np.isnan(q[~ok]))
