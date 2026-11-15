"""Sapma haritası v3 (bitki takvimi) testleri — sentetik veri, yalnız tmp klasörüne yazar."""

import inspect

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from physics import sapma_v3 as V3
from physics.ornek_l4 import LAT, LON
from physics.tablo import bolge_maskeleri

ZAMAN = pd.date_range("2001-01", "2014-12", freq="MS")
AY = ZAMAN.month.to_numpy()


def _kup(v, ad):
    return xr.DataArray(np.asarray(v, "float32"), coords={"time": ZAMAN, "lat": LAT, "lon": LON},
                        dims=("time", "lat", "lon")).rename(ad)


# ------------------------------------------------------------------ bileşenler
def test_takvim_farki_yaz_tepesi_pozitif():
    yaz_tepe = np.where(np.isin(AY, (7, 8)), 0.6, 0.3)          # sulanan: temmuz–ağustos yeşil
    ilk_tepe = np.where(np.isin(AY, (4, 5)), 0.6, 0.2)          # yağmurla: nisan–mayıs yeşil
    v = np.stack([yaz_tepe, ilk_tepe], 1)[:, None, :]
    da = xr.DataArray(v, coords={"time": ZAMAN, "lat": [0.0], "lon": [0.0, 1.0]}, dims=("time", "lat", "lon"))
    f = V3.takvim_farki(da)[0]
    assert f[0] == pytest.approx(0.3) and f[1] == pytest.approx(-0.2 - 0.2)


def test_kopukluk_yagisa_bagli_bitki_dusuk_skor():
    rng = np.random.default_rng(0)
    yil_yag = rng.normal(400, 80, size=ZAMAN.year.nunique() + 1)
    su_yili = np.where(AY >= 10, ZAMAN.year + 1, ZAMAN.year) - ZAMAN.year.min()
    p = np.where(np.isin(AY, V3.SU_YILI_AYLARI), yil_yag[su_yili] / 9, 2.0)
    yaz_yag = (yil_yag[ZAMAN.year - ZAMAN.year.min()] - 400) / 80
    bagli = 0.3 + 0.05 * yaz_yag                                   # yağışlı yıl = yeşil yaz
    kopuk = 0.3 + 0.05 * rng.standard_normal(len(ZAMAN))
    v = np.stack([bagli, kopuk], 1)[:, None, :]
    c = {"time": ZAMAN, "lat": [0.0], "lon": [0.0, 1.0]}
    nd = xr.DataArray(v, coords=c, dims=("time", "lat", "lon"))
    pp = xr.DataArray(np.stack([p, p], 1)[:, None, :], coords=c, dims=("time", "lat", "lon"))
    k = V3.kopukluk(nd, pp)[0]
    assert k[0] < -0.9 and abs(k[1]) < 0.7 and k[1] > k[0]


def test_kopukluk_az_yil_nan():
    t = ZAMAN[:12 * 5]
    c = {"time": t, "lat": [0.0], "lon": [0.0]}
    nd = xr.DataArray(np.random.default_rng(1).random((len(t), 1, 1)), coords=c, dims=("time", "lat", "lon"))
    assert np.isnan(V3.kopukluk(nd, nd * 100)).all()


def test_kurak_yaz_ve_zskor():
    p = np.array([10.0, 79.9, 80.0, np.nan, 10.0])
    z = np.array([100.0, 100.0, 100.0, 100.0, 1600.0])
    k = V3.kurak_yaz(p, z, np.ones(5, bool))
    np.testing.assert_array_equal(k, [True, True, False, False, False])
    alan = np.array([True, True, True, False, False])
    s = V3.zskor(np.array([1.0, 2.0, 3.0, 100.0, 5.0]), alan)
    np.testing.assert_allclose(s[:3], [-1.0, 0.0, 1.0])
    assert np.isnan(s[3:]).all()
    assert np.isnan(V3.zskor(s, k)).all()                    # alanda 3'ten az sonlu değer → NaN


def test_skorlar_kurak_disi_skorsuz():
    tk = np.array([0.1, 0.2, 0.3, 0.4])
    kurak = np.array([True, True, True, False])
    s = V3.skorlar(tk, np.full(4, np.nan), kurak, np.ones(4, bool))
    assert np.isnan(s["v3_ana"][3]) and np.isfinite(s["v3_maskesiz"]).all()
    np.testing.assert_allclose(s["v3_kopukluk"][:3], s["v3_ana"][:3])   # kopukluk yoksa tek bileşen


def test_skor_hesabi_dogrulama_katmanini_okumaz():
    for f in (V3.hesapla, V3.skorlar, V3.girdiler, V3.takvim_farki, V3.kopukluk):
        assert "dogrulama" not in inspect.getsource(f)


# ------------------------------------------------------------------ sentetik paket
def _paket(tmp_path):
    """Güney kurak (yaz yağışı düşük), kuzey yağışlı. Şanlıurfa'da sulama: yazın yeşil, yağıştan kopuk.
    Kuzeyde orman: yazın da yeşil ama kurak yaz değil (skorsuz kalmalı)."""
    rng = np.random.default_rng(3)
    m = bolge_maskeleri(LAT, LON, True)
    kara, sul = m["turkiye"], m["il:sanliurfa"]
    kuzey = (LAT >= 40.5)[:, None] & np.ones(LON.size, bool)[None]
    yil = ZAMAN.year.to_numpy() - ZAMAN.year.min()
    su_yili = np.where(AY >= 10, yil + 1, yil)
    yag_an = rng.normal(0, 1, size=(yil.max() + 2, LAT.size, LON.size))
    yaz = np.isin(AY, (6, 7, 8))[:, None, None]
    p = np.where(kuzey[None], 70.0, np.where(yaz, 3.0, 45.0)) + 8 * yag_an[su_yili]
    p = np.clip(p, 0, None)
    ilk = np.isin(AY, (4, 5))[:, None, None]
    tem = np.isin(AY, (7, 8))[:, None, None]
    yagmur = np.where(ilk, 0.55, np.where(tem, 0.18, 0.3)) + 0.04 * yag_an[su_yili]
    sulanan = np.where(tem, 0.6, np.where(ilk, 0.35, 0.3)) + 0.02 * rng.standard_normal(p.shape)
    orman = np.full(p.shape, 0.7)
    nd = np.where(sul[None], sulanan, np.where(kuzey[None], orman, yagmur))
    nd = np.where(kara[None], nd, np.nan)
    kup = tmp_path / "paket" / "L1_kup"
    kup.mkdir(parents=True)
    _kup(np.where(kara[None], p, np.nan), "yagis").assign_attrs(urun_surumu="v0.1").to_dataset().to_netcdf(
        kup / "yagis__GPM.nc")
    _kup(nd, "ndvi").to_dataset().to_netcdf(kup / "ndvi__MOD13C2.nc")
    xr.DataArray(np.full((LAT.size, LON.size), 500.0), coords={"lat": LAT, "lon": LON},
                 dims=("lat", "lon")).rename("rakim").to_dataset().to_netcdf(kup / "rakim__SRTM.nc")
    return tmp_path / "paket", sul, kuzey & kara


def test_uret_yaz_sulanan_alan_tepede(tmp_path, monkeypatch):
    import physics.sapma as SP
    monkeypatch.setattr(SP, "_cache_oku", lambda *a, **k: None)          # cache'teki gerçek 0,05° dosyalarına bakma
    paket, sul, orman = _paket(tmp_path)
    r = V3.uret_yaz(paket, ("025", "005"))
    assert r["atlanan"] and "005" in r["atlanan"][0]                      # 0,05° yoksa atlanır, hata yok
    g, h = r["sonuclar"]["025"]
    s = h["skor"]["v3_ana"]
    assert np.isnan(s[orman]).all()                                       # yağışlı yaz: skorsuz
    assert np.nanmean(s[sul]) > 2 and np.nanmean(s[~sul & h["kurak"]]) < 0
    assert r["kumeler"].iloc[0]["il"] == "Şanlıurfa"
    with xr.open_dataset(paket / "L4_iliski" / "sapma" / V3.DOSYALAR["025"]) as ds:
        assert ds.attrs["surum"] == "v3" and "Doğrulanmadı" in ds.attrs["uyari"]
        assert ds["kurak_yaz"].dtype == np.int8 and ds.attrs["urun_surumu"] == "v0.1"
    assert not (paket / "dogrulama").exists() and len(r["dogrulama"]) == 0
    assert (paket / "L4_iliski" / "sapma" / "KURAL_v3.txt").read_text(encoding="utf-8").startswith("SAPMA")


def test_dogrulama_varsa_olcer(tmp_path):
    paket, sul, _ = _paket(tmp_path)
    d = paket / "dogrulama"
    d.mkdir()
    oran = xr.DataArray(np.where(sul, 0.8, 0.0), coords={"lat": LAT, "lon": LON}, dims=("lat", "lon"))
    for ad in ("sulanan_oran__GFSAD1KCM.nc", "sulanan_oran__LGRIP30.nc"):
        oran.rename("sulanan_oran").to_dataset().to_netcdf(d / ad)
    r = V3.uret_yaz(paket, ("025",))
    t = r["dogrulama"]
    assert set(t["referans"]) == {"GFSAD1KCM", "LGRIP30"}
    ana = t[(t["yapilandirma"] == "v3_ana") & (t["referans"] == "LGRIP30")].iloc[0]
    assert ana["auc"] > 0.95 and ana["kaldirac_ust5"] > 5
    assert {"ana", "tanı", "duyarlılık"} <= set(t["tur"])
    assert (d / "sapma_v3_dogrulama.csv").exists()
