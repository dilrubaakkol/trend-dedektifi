"""physics.kalibrasyon testleri (sentetik, internetsiz, az tekrarlı; sabit tohum)."""

import numpy as np
import pandas as pd
import pytest

from physics import kalibrasyon as K


def test_saptanabilir_r_bilinen_degerler():
    assert K.saptanabilir_r(25) == pytest.approx(0.54, abs=0.01)     # Fisher z, %80 güç, α 0,05
    assert K.saptanabilir_r(300) == pytest.approx(0.16, abs=0.01)
    assert np.isnan(K.saptanabilir_r(3)) and np.isnan(K.saptanabilir_r(float("nan")))
    seri = [K.saptanabilir_r(n) for n in (10, 20, 50, 100)]
    assert all(a > b for a, b in zip(seri, seri[1:]))                # daha çok veri → daha zayıf ilişki görülür
    assert K.saptanabilir_r(25, alfa=0.10) < K.saptanabilir_r(25)


def test_ar1_cift_korelasyon_ve_hafiza():
    rng = np.random.default_rng(0)
    x, y = K.ar1_cift(20000, 0.6, 0.5, rng, trend=0.0)
    assert np.corrcoef(x, y)[0, 1] == pytest.approx(0.5, abs=0.03)
    assert np.corrcoef(x[1:], x[:-1])[0, 1] == pytest.approx(0.6, abs=0.03)
    a, b = K.ar1_cift(1000, 0.0, 0.0, rng, trend=10.0, ortak_trend=True)
    assert np.corrcoef(a, b)[0, 1] > 0.8          # ortak trend sahte korelasyon üretir (beklenen ≈ 8,3/9,3)


def test_yanlis_alarm_ve_yakalama():
    rng = np.random.default_rng(1)
    bos = K.deneme(25, 0.3, 0.0, 300, rng)
    assert bos["oran_anlamli"] < 0.10                                 # hedef %5; 300 tekrarda pay
    guclu = K.deneme(25, 0.3, 0.8, 200, rng)
    assert guclu["oran_beklenen_yonde"] > 0.9 and guclu["oran_ters_yonde"] == 0


def test_ortak_trend_motor_tuzaga_dusmez():
    rng = np.random.default_rng(2)
    d = K.deneme(300, 0.3, 0.0, 200, rng, ortak_trend=True)
    assert d["oran_anlamli"] < 0.10 < d["oran_anlamli_trendsiz_olmasa"]


def test_fdr_deneme_calisir():
    d = K.fdr_deneme(gercek_pay=0.3, ortak=0.5, tekrar=20, iller=30)
    assert 0 <= d["gerceklesen_fdr"] < 0.3 and d["yakalama_orani"] > 0.2
    assert set(d) >= {"gerceklesen_fdr", "hedef_fdr", "yakalama_orani", "il_basi_yanlis_alarm"}


def test_gercek_satirlar_okuma(tmp_path):
    l4 = tmp_path / "L4_iliski"
    l4.mkdir()
    pd.DataFrame({"cift_no": [1, 1, 1], "cift": ["a"] * 3, "seri": ["kis_DJF"] * 3, "gecikme_ay": [0] * 3,
                  "bolge_turu": ["bolge", "bolge", "turkiye"], "bolge_kodu": ["x", "y", "turkiye"],
                  "bolge_adi": ["X", "Y", "Türkiye"], "n": [25] * 3, "etkin_n": [25.0, 25.0, np.nan],
                  "r": [0.2, -0.7, 0.1], "p": [0.3, 0.001, np.nan], "etiket": ["anlamsiz", "beklenen_yonde", ""]}
                 ).to_csv(l4 / "ciftler.csv", index=False, encoding="utf-8-sig")
    df = K.gercek_satirlar(tmp_path)
    assert len(df) == 2                                               # etkin n'si olmayan satır atlanır
    assert df.iloc[0]["okuma"].startswith("ilişki bu veri uzunluğunda") and df.iloc[1]["okuma"] == "anlamlı"
    oz = K.guc_ozeti(df)
    assert oz.iloc[0]["anlamsiz_zayif"] == 1
