"""stats/karne.py testleri (trend karnesi ve ortak yardımcılar) — sentetik, internetsiz."""

import numpy as np
import pytest
import xarray as xr

from stats import karne as K
from stats.trend_tests import anlamli_kural, trend_analizi

YIL = np.arange(2001, 2026)


def _seri(y):
    return xr.DataArray(np.asarray(y, float), coords={"yil": YIL[:len(y)]}, dims="yil")


def _satir(s, anlamli=None):
    """L3 satırı gibi: tek seride FDR yok, p_fdr = p_mk."""
    r = trend_analizi(s, min_yil=12, kontrol=False)
    an = int(anlamli_kural(r["p_mk"], r["ci_alt"], r["ci_ust"])) if anlamli is None else anlamli
    return {"sen_egimi": r["egim_10yil"], "ga_alt": r["ci_alt"], "ga_ust": r["ci_ust"], "p_fdr": r["p_mk"],
            "anlamli": an, "etkin_n": r["n_etkin"], "gereken_yil": r["gereken_yil"]}


# ------------------------------------------------------------------ yardımcılar
@pytest.mark.parametrize("n, blok", [(25, 1), (25, 3), (25, 7), (22, 4), (300, 12)])
def test_dairesel_blok_tam_permutasyon(n, blok):
    idx = K.dairesel_blok_indeksleri(n, blok, 50, np.random.default_rng(0))
    assert idx.shape == (50, n)
    assert (np.sort(idx, axis=1) == np.arange(n)).all()          # her satır gerçek bir permütasyon
    if blok > 1:                                                    # blok içinde ardışıklık korunur
        ardisik = (np.diff(idx, axis=1) % n == 1).mean()
        assert ardisik >= (blok - 1) / blok * 0.8


def test_blok_uzunlugu():
    assert K.blok_uzunlugu(25, 25) == 1 and K.blok_uzunlugu(25, 8.3) == 4
    assert K.blok_uzunlugu(25, np.nan) == 1 and K.blok_uzunlugu(25, 1) == 12   # en az iki blok


def test_sen_egimi_scipy_ile_ayni():
    from scipy.stats import theilslopes
    rng = np.random.default_rng(1)
    y = 0.3 * np.arange(25) + rng.normal(0, 1, 25)
    assert K.sen_egimleri(y, np.arange(25.0))[0] == pytest.approx(theilslopes(y)[0])
    y[[3, 9]] = np.nan
    ok = np.isfinite(y)
    assert K.sen_egimleri(y, np.arange(25.0))[0] == pytest.approx(theilslopes(y[ok], np.arange(25.0)[ok])[0])


def test_perm_p():
    assert K.perm_p(1.0, np.zeros(499)) == pytest.approx(1 / 500)
    assert K.perm_p(0.0, np.zeros(9)) == 1.0


def test_tekrarlanabilir_sabit_tohum():
    s = _seri(0.05 * np.arange(25) + np.random.default_rng(2).normal(0, 0.5, 25))
    a = K.karistirma_trend(s, 20, "il|01|yillik")
    b = K.karistirma_trend(s, 20, "il|01|yillik")
    assert a == b                                                   # aynı satır → aynı sonuç
    assert K.tohum("x") == K.tohum("x") and K.tohum("x") != K.tohum("y")


# ------------------------------------------------------------------ güven seviyeleri
def test_guclu_trend_yuksek():
    s = _seri(0.1 * np.arange(25) + np.random.default_rng(3).normal(0, 0.3, 25))
    st = _satir(s)
    assert st["anlamli"] == 1
    k = K.trend_satiri_karnesi(st, s, (K.GECTI, "2/2"), [], [], "test|guclu")
    assert (k["b_karistirma"], k["c_donem"], k["d_esik"], k["e_yeterlilik"]) == (K.GECTI,) * 4
    assert k["guven"] == K.YUKSEK and k["gerekce"] == "anlamlı; bütün kontroller geçti"


def test_tek_kaynak_ve_uyari_orta():
    s = _seri(0.1 * np.arange(25) + np.random.default_rng(3).normal(0, 0.3, 25))
    st = _satir(s)
    k = K.trend_satiri_karnesi(st, s, (K.UYG, "tek kaynak"), [], [], "test|tek")
    assert k["guven"] == K.ORTA and "kaynak uyumu uygulanamaz" in k["gerekce"]
    k = K.trend_satiri_karnesi(st, s, (K.GECTI, "2/2"), ["Kademe 2"], ["Kademe 2"], "test|uyari")
    assert k["guven"] == K.ORTA and "uyarı: Kademe 2" in k["gerekce"] and k["f_kritik"] == "evet"
    k = K.trend_satiri_karnesi(st, s, (K.GECTI, "2/2"), ["mk_yedek: …"], [], "test|mk")
    assert k["guven"] == K.YUKSEK and k["f_uyarilar"] == "mk_yedek: …"   # mk_yedek kritik değil


def test_gurultu_yok():
    s = _seri(np.random.default_rng(4).normal(0, 1, 25))
    st = _satir(s)
    assert st["anlamli"] == 0
    k = K.trend_satiri_karnesi(st, s, (K.UYG, "tek kaynak"), [], [], "test|gurultu")
    assert k["guven"] == K.YOK and k["gerekce"].startswith("anlamlı değil")


def test_uc_yillara_dayanan_trend_dusuk():
    """Trend yalnız son yıllardaki sıçramadan geliyor: uçlar çıkarılınca anlamlılık kayboluyor (c kalır).

    Motorun genişletilmiş güven aralığı böyle serileri çoğu zaman zaten anlamsız sayar; burada satırın
    "anlamlı" kararı L3'ten gelen bir girdi olarak verilir ve karnenin c kontrolü sınanır.
    """
    rng = np.random.default_rng(2)
    y = rng.normal(0, 0.3, 25) + 0.01 * np.arange(25)
    y[-3:] += 3.0
    s = _seri(y)
    st = _satir(s, anlamli=1)
    k = K.trend_satiri_karnesi(st, s, (K.GECTI, "2/2"), [], [], "test|uc")
    assert k["c_donem"] == K.KALDI and "anlamsız" in k["c_sayi"]
    assert k["guven"] == K.DUSUK and "dönem duyarlılığı kaldı" in k["gerekce"]


def test_veri_yetmiyor_notu():
    st = {"sen_egimi": 0.1, "anlamli": 0, "p_fdr": 0.5, "ga_alt": -1, "ga_ust": 1, "etkin_n": 20,
          "gereken_yil": 60}
    s = _seri(np.random.default_rng(5).normal(0, 1, 25))
    k = K.trend_satiri_karnesi(st, s, (K.UYG, "tek kaynak"), [], [], "test|yetmiyor")
    assert k["e_yeterlilik"] == K.KALDI and k["guven"] == K.YOK and "veri henüz yetmiyor" in k["gerekce"]


def test_kaynak_durumu():
    import pandas as pd
    ku = pd.DataFrame({"bolge_anahtari": ["turkiye"], "mevsim": ["yillik"], "m": [3], "isaret_uyumu": [1.0],
                       "egim_GPM": [5.0], "anlamli_GPM": [1], "egim_GLDAS": [3.0], "anlamli_GLDAS": [1],
                       "egim_MERRA2": [-1.0], "anlamli_MERRA2": [0], "egim_birimi": ["mm"]}
                      ).set_index(["bolge_anahtari", "mevsim"])
    d, s = K.kaynak_durumu(ku, "turkiye", "yillik", "GPM", 5.0, True)
    assert d == K.GECTI and s.startswith("2/3")
    d, s = K.kaynak_durumu(ku, "turkiye", "yillik", "MERRA2", -1.0, False)
    assert d == K.UYG and s.startswith("sonuç anlamlı değil")
    assert K.kaynak_durumu(ku, "turkiye", "yillik", "GPM", -5.0, True)[0] == K.KALDI   # ters yön: tek başına
    assert K.kaynak_durumu(None, "turkiye", "yillik", "GRACE", 1.0, True) == (K.UYG, "tek kaynak")


def test_kural_metni_dil():
    m = K.KURAL_METNI.lower()
    assert "kanıtland" not in m and " neden " not in m and "nedensellik göstermez" in m
    for s in ("YÜKSEK", "ORTA", "DÜŞÜK", "YOK"):
        assert s in K.KURAL_METNI
