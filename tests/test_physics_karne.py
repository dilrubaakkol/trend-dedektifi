"""physics/karne.py (ilişki karnesi) ve physics.iliski --karne testleri — sentetik, yalnız tmp klasörü."""

import json

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from physics import karne as PK, run, tek_cift as T
from physics.ornek_l4 import ornek_veri
from physics.tablo import ham_iliski
from stats.karne import DUSUK, GECTI, KALDI, ORTA, UYG, YOK, YUKSEK


# ------------------------------------------------------------------ birim
def test_iki_trendli_iliskisiz_seri_c_kalir():
    """İki seri de trendli, yıldan yıla oynamaları ilişkisiz: ham r yüksek, trendsiz r küçük → c kalır."""
    rng = np.random.default_rng(0)
    t = np.arange(2001, 2026, dtype=float)
    x = 0.5 * (t - 2001) + rng.normal(0, 1, t.size)
    y = 0.4 * (t - 2001) + rng.normal(0, 1, t.size)
    h = ham_iliski(x, y, t)
    from physics.iliski import iliski_1d
    r = iliski_1d(x, y, 1, t=t)["r"]
    assert h["r_ham"] > 0.8 and abs(r) < 0.5
    c = PK.trend_kontrolu(r, h["r_ham"])
    assert c["durum"] == KALDI and "ham r" in c["sayi"]
    b = PK.karistirma_iliski(x, y, t, 20, "test|sahte")
    assert b["durum"] == KALDI and b["p_perm"] > 0.10                # trendsiz seriler ilişkisiz


def test_iliskili_seri_b_gecer_ve_tekrarlanabilir():
    rng = np.random.default_rng(1)
    t = np.arange(300) / 12 + 2001
    ortak = rng.normal(0, 1, 300)
    x, y = ortak + rng.normal(0, 0.5, 300), ortak + rng.normal(0, 0.5, 300)
    a = PK.karistirma_iliski(x, y, t, 250, "test|iliskili")
    assert a["durum"] == GECTI and a["p_perm"] == pytest.approx(1 / 500)
    assert a == PK.karistirma_iliski(x, y, t, 250, "test|iliskili")


def test_trend_kontrolu_sinirlar():
    assert PK.trend_kontrolu(-0.58, -0.63)["durum"] == GECTI
    assert PK.trend_kontrolu(0.30, 0.59)["durum"] == GECTI       # 0,30 ≥ 0,59 / 2 = 0,295 (sınırda geçer)
    assert PK.trend_kontrolu(0.20, 0.59)["durum"] == KALDI
    assert PK.trend_kontrolu(0.59, 0.30)["durum"] == GECTI       # trend ilişkiyi gizliyordu: geçer
    assert PK.trend_kontrolu(0.2, -0.3)["durum"] == KALDI
    assert PK.trend_kontrolu(np.nan, 0.3)["durum"] == UYG


# ------------------------------------------------------------------ uçtan uca (sentetik paket)
@pytest.fixture(scope="module")
def paket(tmp_path_factory):
    kok = tmp_path_factory.mktemp("karne") / "paket"
    kup = kok / "L1_kup"
    kup.mkdir(parents=True)
    v = ornek_veri(seed=1)
    v["sicaklik_2m__GLDAS"] = v["sicaklik_2m__MERRA2"] + 0.3
    for ad, da in v.items():
        d = da.copy()
        d.attrs = {"urun_surumu": "v0.1", "veri_seti_doi": "(yayında doldurulacak)", "lisans": "CC BY 4.0",
                   "doi": "10.5067/TEST", "kademe": 1}
        d.rename(ad.split("__")[0]).to_dataset().to_netcdf(kup / f"{ad}.nc")
    run.main(["--paket", str(kok), "--iller-yok"])
    return kok


def test_l4_karnesi_tutarli_ve_l4_degismez(paket):
    l4 = paket / "L4_iliski"
    once = {p.name: p.read_bytes() for p in l4.iterdir() if p.is_file()}
    df = PK.l4_karnesi(paket)
    assert once == {p.name: p.read_bytes() for p in l4.iterdir() if p.is_file()}   # L4 aynen kaldı
    ref = pd.read_csv(l4 / "ciftler.csv", dtype={"bolge_kodu": str}, encoding="utf-8-sig")
    assert len(df) == len(ref) and list(df.columns) == PK.SUTUNLAR
    assert set(df["guven"]) <= {YUKSEK, ORTA, DUSUK, YOK}
    # karnedeki r, ciftler.csv ile aynı (aynı seriler)
    m = df.merge(ref, on=["cift_no", "gecikme_ay", "bolge_kodu"], suffixes=("", "_ref"))
    np.testing.assert_allclose(m["r"], m["r_ref"], rtol=1e-5, equal_nan=True)
    # çift 1: alternatif ürün (sıcaklık GLDAS) denendi; çift 3: alternatif yok
    c1 = df[df["cift_no"] == 1]
    hesap = c1["r"].notna()
    assert c1.loc[hesap, "a_sayi"].str.contains("GLDAS~MOD10CM").all()
    assert (c1.loc[~hesap, "a_sayi"] == "r hesaplanamadı").all()     # kar örtüsü olmayan bölge
    assert (df.loc[df["cift_no"] == 3, "a_kaynak_uyumu"] == UYG).all()
    # çift 2 mevsimlik: gecikme kontrolü uygulanamaz; çift 5 rejime bağlı: kritik uyarı
    assert (df.loc[df["cift_no"] == 2, "d_gecikme"] == UYG).all()
    c5 = df[df["cift_no"] == 5]
    assert (c5["f_kritik"] == "evet").all() and c5["f_uyarilar"].str.contains("rejime bağlı").all()
    assert not (c5["guven"] == YUKSEK).any()
    # anlamsız satır her zaman YOK; anlamlı satır asla YOK
    assert (df.loc[df["anlamli"] != 1, "guven"] == YOK).all()
    assert (df.loc[df["anlamli"] == 1, "guven"] != YOK).all()
    # tekrarlanabilir
    pd.testing.assert_frame_equal(df, PK.l4_karnesi(paket))


def test_komut_karne_bayragi(paket, capsys):
    T.main(["--x", "sicaklik_2m", "--y", "kar_ortusu", "--bolge", "Doğu Anadolu", "--mevsim", "kis",
            "--beklenen", "-", "--paket", str(paket), "--karne"])
    out = capsys.readouterr().out
    assert "BULGU KARNESİ" in out and "güven" in out and "karne süresi" in out
    assert "nedensellik göstermez" in out and "kanıtland" not in out
    T.main(["--x", "sicaklik_2m", "--y", "kar_ortusu", "--bolge", "Doğu Anadolu", "--mevsim", "kis",
            "--beklenen", "-", "--paket", str(paket), "--karne", "--json"])
    d = json.loads(capsys.readouterr().out)
    assert len(d["karne"]) == 1 and d["karne"][0]["guven"] in {YUKSEK, ORTA, DUSUK, YOK}
    assert {"a_kaynak_uyumu", "b_p_perm", "c_trend", "d_gecikme", "e_esik"} <= set(d["karne"][0])
