"""physics/tests_physical.py — su bütçesi ve Clausius-Clapeyron testleri (sentetik, internetsiz)."""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from physics.synthetic import synthetic_budget, synthetic_cc
from physics.tests_physical import clausius_clapeyron, water_budget


def _butce(**kw):
    d = synthetic_budget(**kw)
    return d, water_budget(d["grace_cm"], d["yagis"], d["buharlasma"], d["yuzey_akisi"],
                           d["taban_akisi"], region="konya")


# ------------------------------------------------------------------ 7a su bütçesi
def test_gizli_kayip_celiskili_ve_insan_kaynakli_not():
    """Konya senaryosu: akılar dengede ama GRACE yılda 25 mm düşüyor → çelişkili."""
    _, r = _butce(kayip_mm_per_year=25.0, yagis_yayilim_mm_per_month=0.5, seed=1)
    assert r["label"] == "celiskili"
    assert r["residual_mm_per_year"] < -15
    assert "yeraltı suyu" in r["note"] and "GRACE" in r["note"]
    assert r["type"] == "water_budget" and r["id"] == "butce_konya"


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_kayip_yoksa_butce_kapanir(seed):
    _, r = _butce(kayip_mm_per_year=0.0, yagis_yayilim_mm_per_month=0.5, seed=seed)
    assert r["label"] == "uyumlu", (r["grace_slope_mm_per_year"], r["p_et_r_mean_mm_per_year"])


def test_birimler_ve_donem():
    d, r = _butce(kayip_mm_per_year=25.0, seed=4)
    assert r["period"] == ["2002-04", "2025-12"]
    # sağ taraf: aylık mm × 12 — GPM ürünü ortalaması 0 mm/yıl olacak şekilde kuruldu
    assert r["p_et_r_by_product"]["GPM"] == pytest.approx(0.0, abs=0.5)
    assert r["p_et_r_by_product"]["GLDAS"] == pytest.approx(12.0, abs=0.5)   # +1 mm/ay
    assert r["p_et_r_mean_mm_per_year"] == [min(r["p_et_r_by_product"].values()),
                                            max(r["p_et_r_by_product"].values())]
    # GRACE cm → mm: eğim −25 mm/yıl civarı (cm olsaydı −2,5 çıkardı)
    assert -40 < r["grace_slope_point_mm_per_year"] < -15


def test_grace_boslugu_nan_kalir_ve_sayilmaz():
    d, r = _butce(kayip_mm_per_year=25.0, seed=5)
    bosluk_ay = int(d["grace_cm"].isnull().sum())
    assert bosluk_ay == 11
    assert r["grace_n_months"] == d["grace_cm"].sizes["time"] - bosluk_ay


def test_taban_akisi_yoksa_not():
    d = synthetic_budget(seed=6)
    r = water_budget(d["grace_cm"], d["yagis"], d["buharlasma"], d["yuzey_akisi"], None)
    assert "R eksik" in r["note"]


def test_kisa_grace_yetersiz():
    d = synthetic_budget(baslangic="2024-01", bitis="2025-06", bosluk=("2030-01", "2030-02"))
    r = water_budget(d["grace_cm"], d["yagis"], d["buharlasma"], d["yuzey_akisi"],
                     d["taban_akisi"])
    assert r["label"] == "yetersiz"


def test_uzaysal_girdi_alan_ortalamasina_iner():
    """(time, lat, lon) girdi + maske: bölge ortalamasıyla aynı sonuç."""
    d = synthetic_budget(kayip_mm_per_year=25.0, yagis_yayilim_mm_per_month=0.5, seed=1)
    lat, lon = np.array([37.125, 37.375]), np.array([32.125, 32.375, 32.625])

    def yay(s):
        return s.expand_dims(lat=lat, lon=lon).transpose("time", "lat", "lon")
    maske = xr.DataArray(np.ones((2, 3), bool), coords={"lat": lat, "lon": lon},
                         dims=("lat", "lon"))
    r = water_budget(yay(d["grace_cm"]), {k: yay(v) for k, v in d["yagis"].items()},
                     yay(d["buharlasma"]), yay(d["yuzey_akisi"]), yay(d["taban_akisi"]),
                     mask=maske)
    assert r["label"] == "celiskili"


# ------------------------------------------------------------------ 7b Clausius-Clapeyron
@pytest.mark.parametrize("oran,beklenen", [(7.0, "uyumlu"), (6.5, "uyumlu"),
                                            (3.0, "celiskili"), (11.0, "celiskili")])
def test_cc_deniz_etiketi(oran, beklenen):
    q, T = synthetic_cc(oran, seed=2)
    r = clausius_clapeyron(q, T, region="deniz_karadeniz")
    lo, hi = r["slope_pct_per_C"]
    assert lo <= oran <= hi                            # mevsimsellik silindi, oran geri bulundu
    assert r["label"] == beklenen
    assert r["expected_pct_per_C"] == [6.0, 8.0]
    assert r["id"] == "cc_ozgul_nem_2m_MERRA2_deniz_karadeniz"


def test_cc_kara_etiketsiz():
    q, T = synthetic_cc(4.5, seed=3)
    r = clausius_clapeyron(q, T, region="turkiye", etiketli=False)
    assert "label" not in r and "bağıl nem" in r["note"]


def test_cc_gurultulu_kisa_seri_yetersiz():
    q, T = synthetic_cc(7.0, n_ay=18, gurultu=0.2, seed=4)
    r = clausius_clapeyron(q, T)
    assert r["label"] == "yetersiz"


def test_cc_kapsama_100_tohum():
    hit = 0
    for s in range(100):
        q, T = synthetic_cc(7.0, seed=1000 + s)
        lo, hi = clausius_clapeyron(q, T)["slope_pct_per_C"]
        hit += lo <= 7.0 <= hi
    assert hit >= 90


# ------------------------------------------------------------------ physics.run girişleri
def test_run_butce_ve_cc(monkeypatch):
    """Veri okuma taklit edilir; analyze_budget / analyze_cc doğru fonksiyonlara bağlanıyor."""
    import physics.run as run
    d = synthetic_budget(kayip_mm_per_year=25.0, yagis_yayilim_mm_per_month=0.5, seed=1)
    q, T = synthetic_cc(7.0, seed=2)
    tablo = {("toplam_su_depolama", None): d["grace_cm"], ("yagis", None): d["yagis"]["GPM"],
             ("yagis", "GLDAS"): d["yagis"]["GLDAS"], ("yagis", "MERRA2"): d["yagis"]["MERRA2"],
             ("buharlasma", None): d["buharlasma"], ("yuzey_akisi", None): d["yuzey_akisi"],
             ("taban_akisi", None): d["taban_akisi"], ("ozgul_nem_2m", None): q,
             ("sicaklik_2m", "MERRA2"): T}

    def sahte(degisken, region, grid, product=None, sentetik=None):
        if (degisken, product) not in tablo:
            raise FileNotFoundError(degisken)
        return tablo[(degisken, product)], True
    monkeypatch.setattr(run, "_yukle", sahte)

    b = run.analyze_budget("demo:konya")
    assert b["analyses"][0]["label"] == "celiskili" and b["analyses"][0]["id"] == "butce_konya"
    c = run.analyze_cc()
    etiketli = [a for a in c["analyses"] if "label" in a]
    assert [a["region"] for a in c["analyses"]] == ["deniz_karadeniz", "turkiye"]
    assert len(etiketli) == 1 and etiketli[0]["label"] == "uyumlu"
    sar = run.results_dosyasi("demo:konya", b, run.KART["butce"])
    assert sar["region"]["name"] == "konya" and sar["card_id"] == "su_kaynaklari"
