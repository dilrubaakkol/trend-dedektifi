"""physics/seriler.py ve physics/ciftler.py testleri (Faz 2; sentetik, internetsiz)."""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from physics import seriler as S
from physics.ciftler import CIFT, CIFTLER, cift_serileri
from physics.iliski import iliski_1d

ZAMAN = pd.date_range("2001-01", "2025-12", freq="MS")


def _seri(degerler, zaman=ZAMAN):
    return xr.DataArray(np.asarray(degerler, float), coords={"time": zaman}, dims="time")


def _ay_kodu(zaman=ZAMAN):
    """Her ayın değeri = yıl*100 + ay (ör. 200212) → hangi ayların toplandığı okunabilir."""
    return _seri(zaman.year * 100 + zaman.month, zaman)


# ------------------------------------------------------------------ mevsim serileri
def test_kis_aralik_ocak_subat_mart_yok():
    k = S.mevsim_serisi(_ay_kodu(), "kis")
    # Kış 2002 = Ara 2001 + Oca 2002 + Şub 2002
    assert float(k.sel(yil=2002)) == pytest.approx((200112 + 200201 + 200202) / 3)
    # Aralık 2000 yok → ilk kış (2001) NaN; Aralık 2025'in kışı (2026) eksik → NaN
    assert np.isnan(float(k.sel(yil=2001))) and np.isnan(float(k.sel(yil=2026)))
    assert int(k.notnull().sum()) == 24  # 2002–2025


def test_yaz_ve_yillik_aylari():
    v = _ay_kodu()
    assert float(S.mevsim_serisi(v, "yaz").sel(yil=2010)) == pytest.approx(201007)
    assert float(S.mevsim_serisi(v, "yillik").sel(yil=2010)) == pytest.approx(201006.5)
    assert float(S.mevsim_serisi(v, "ilkbahar").sel(yil=2010)) == pytest.approx(201004)
    assert float(S.mevsim_serisi(v, "sonbahar").sel(yil=2010)) == pytest.approx(201010)


def test_birikimli_toplam_digerleri_ortalama():
    v = _seri(np.full(len(ZAMAN), 30.0))          # her ay 30 mm
    assert float(S.mevsim_serisi(v, "yaz", toplam=True).sel(yil=2010)) == 90
    assert float(S.mevsim_serisi(v, "yaz").sel(yil=2010)) == 30
    assert S.toplam_mi("yagis") and S.toplam_mi("buharlasma") and not S.toplam_mi("sicaklik_2m")


def test_eksik_ay_mevsimi_nan_yapar():
    v = _seri(np.ones(len(ZAMAN)))
    v.loc["2010-07-01"] = np.nan
    assert np.isnan(float(S.mevsim_serisi(v, "yaz").sel(yil=2010)))
    assert np.isnan(float(S.mevsim_serisi(v, "yillik").sel(yil=2010)))
    # ortalamada min_ay gevşetilebilir, toplamda asla (eksik ay toplamı küçültür)
    assert float(S.mevsim_serisi(v, "yillik", min_ay=9).sel(yil=2010)) == 1
    assert np.isnan(float(S.mevsim_serisi(v, "yillik", toplam=True, min_ay=9).sel(yil=2010)))


def test_kup_girdi():
    lat, lon = [38.125, 38.375], [30.125, 30.375, 30.625]
    v = xr.DataArray(np.ones((len(ZAMAN), 2, 3)), coords={"time": ZAMAN, "lat": lat, "lon": lon},
                     dims=("time", "lat", "lon"))
    k = S.mevsim_serisi(v, "kis")
    assert k.dims == ("yil", "lat", "lon") and k.sizes["lat"] == 2


def test_aylik_olmayan_zaman_reddedilir():
    with pytest.raises(ValueError):
        S.mevsim_serisi(_seri(np.ones(10), pd.date_range("2001-01-15", periods=10, freq="D")), "kis")


# ------------------------------------------------------------------ anomaliler
def test_aylik_anomali_mevsim_dongusunu_siler():
    dongu = 10 * np.sin(2 * np.pi * (ZAMAN.month - 1) / 12)
    a = S.aylik_anomali(_seri(dongu + 5))
    assert np.allclose(a.values, 0, atol=1e-9)


def test_mevsim_anomali_dizilisi():
    rng = np.random.default_rng(0)
    dongu = 10 * np.sin(2 * np.pi * (ZAMAN.month - 1) / 12)
    a = S.mevsim_anomali(_seri(dongu + rng.standard_normal(len(ZAMAN))))
    assert a.dims == ("t",)
    assert list(a["mevsim"].values[:4]) == ["kis", "ilkbahar", "yaz", "sonbahar"]
    assert np.all(np.diff(a["t"].values) > 0)
    for m in ("kis", "ilkbahar", "yaz", "sonbahar"):  # her mevsimin ortalaması 0
        assert abs(float(a.where(a["mevsim"] == m).mean())) < 1e-9
    assert int(a.notnull().sum()) == 24 + 25 * 3  # kış 24, öteki mevsimler 25'er


def test_gecikme_eslesmesi():
    x, y = _ay_kodu(), _ay_kodu()
    xg, yg = S.gecikmeli(x, y, 1)
    assert float(yg.sel(time="2010-05-01")) == 201005
    assert float(xg.sel(time="2010-05-01")) == 201004      # Mayıs NDVI ↔ Nisan toprak nemi
    assert np.isnan(float(yg.sel(time="2010-11-01")))       # Nisan–Eylül dışı NaN
    with pytest.raises(ValueError):                          # kesintili zaman
        S.gecikmeli(x.drop_sel(time="2010-03-01"), y.drop_sel(time="2010-03-01"), 1)


def test_alan_ortalamasi_cos_agirlikli_ve_maske():
    lat, lon = [0.0, 60.0], [10.0, 11.0]
    v = xr.DataArray(np.array([[[1, 1], [3, 3]]], float),
                     coords={"time": ZAMAN[:1], "lat": lat, "lon": lon}, dims=("time", "lat", "lon"))
    # ağırlık cos0 = 1, cos60 = 0,5 → (1·1 + 3·0,5)/1,5
    assert float(S.alan_ortalamasi(v)[0]) == pytest.approx(2.5 / 1.5)
    m = xr.DataArray([[True, True], [False, False]], coords={"lat": lat, "lon": lon},
                     dims=("lat", "lon"))
    assert float(S.alan_ortalamasi(v, m)[0]) == 1


# ------------------------------------------------------------------ 6 çift
def test_cift_tablosu_sozlesmeyle_ayni():
    assert [c.no for c in CIFTLER] == [1, 2, 3, 4, 5, 6]
    assert CIFT[1].kod == "sicaklik_2m__MERRA2~kar_ortusu__MOD10CM" and CIFT[1].beklenen == -1
    assert CIFT[3].harita_dosyasi(2) == "iliski__toprak_nemi__ndvi__gecikme2.nc"
    assert CIFT[6].harita_dosyasi() == "iliski__sicaklik_2m__yuzey_sicakligi_gunduz.nc"
    assert not CIFT[4].harita and {c.no for c in CIFTLER if c.kademe == 2} == {5, 6}


def _kup(rng, ny=3, nx=3):
    lat = 38.125 + 0.25 * np.arange(ny)
    lon = 40.125 + 0.25 * np.arange(nx)
    return lat, lon


def test_cift1_kis_iliskisi_ve_kar_maskesi():
    """Karlı hücrede sıcak kış = az kar (beklenen_yonde); karsız hücre maskelenir."""
    rng = np.random.default_rng(1)
    lat, lon = [39.125, 39.375], [41.125]
    anom = rng.standard_normal(len(ZAMAN))                     # her ayın sıcaklık sapması
    T = (-5 + 15 * np.sin(2 * np.pi * (ZAMAN.month - 4) / 12) + 2 * anom)
    T = np.stack([T, T])[..., None].transpose(1, 0, 2)
    kar = np.empty_like(T)
    kar[:, 0, 0] = np.clip(60 - 8 * anom * 2 + rng.standard_normal(len(ZAMAN)), 0, 100)  # karlı
    kar[:, 1, 0] = 2.0 + 0.1 * rng.standard_normal(len(ZAMAN))                           # karsız
    k = {"coords": {"time": ZAMAN, "lat": lat, "lon": lon}, "dims": ("time", "lat", "lon")}
    s, = cift_serileri(1, xr.DataArray(T, **k), xr.DataArray(kar, **k))
    assert s["boyut"] == "yil" and s["donem"] == "2002-2025"
    assert s["y"].isel(lat=1).isnull().all()                    # %10 altı → kapsam dışı
    r = iliski_1d(s["x"].isel(lat=0, lon=0).values, s["y"].isel(lat=0, lon=0).values,
                  CIFT[1].beklenen, t=s["t"])
    assert r["etiket"] == "beklenen_yonde" and r["r"] < -0.8


def test_cift3_gecikme_bir_ay():
    """NDVI, bir ay önceki toprak nemine bağlı → gecikme 1 güçlü, gecikme 2 zayıf."""
    rng = np.random.default_rng(2)
    nem = rng.standard_normal(len(ZAMAN))
    ndvi = np.r_[0, nem[:-1]] + 0.5 * rng.standard_normal(len(ZAMAN))
    g1, g2 = cift_serileri(3, _seri(nem), _seri(ndvi))
    assert (g1["gecikme"], g2["gecikme"]) == (1, 2)
    r1 = iliski_1d(g1["x"].values, g1["y"].values, 1, t=g1["t"])
    r2 = iliski_1d(g2["x"].values, g2["y"].values, 1, t=g2["t"])
    assert r1["n"] == 25 * 6 and r1["r"] > 0.8 and abs(r2["r"]) < 0.3


def test_cift4_grace_bosluk_yillari_atilir():
    rng = np.random.default_rng(3)
    yagis = _seri(np.abs(30 + 10 * rng.standard_normal(len(ZAMAN))))
    g = rng.standard_normal(len(ZAMAN))
    g[ZAMAN < "2002-04"] = np.nan                                       # GRACE 2002-04'te başlar
    g[(ZAMAN >= "2017-07") & (ZAMAN <= "2018-05")] = np.nan             # büyük boşluk (11 ay)
    g[ZAMAN == "2013-02-01"] = np.nan                                   # dağınık tek eksik ay
    s, = cift_serileri(4, yagis, _seri(g))
    y = s["y"].to_series()
    assert y[[2017, 2018]].isna().all()                                 # boşluk yılları atıldı
    assert np.isfinite(y[2013]) and np.isfinite(y[2002])                # 11 ve 9 ay → tutuldu
    assert np.isnan(y[2001])


def test_cift2_mevsim_anomali_ve_farkli_bitis():
    """GPM 2025-09'da bitiyor; ortak dönem yağışın son tam mevsimine kadar."""
    rng = np.random.default_rng(4)
    p = rng.gamma(2, 15, len(ZAMAN))
    p[ZAMAN > "2025-09"] = np.nan
    s, = cift_serileri(2, _seri(p), _seri(20 + rng.standard_normal(len(ZAMAN))))
    assert s["boyut"] == "t" and s["donem"] == "2001-2025"   # ilkbahar 2001 var
    assert np.isnan(float(s["x"].sel(t=2025.75)))                  # 2025 sonbaharı eksik


def test_cift6_ortak_mevsim_dongusu_tuzagi():
    """İki değişken aynı yaz–kış döngüsünü paylaşıyor ama sapmaları ilgisiz → anlamsiz.

    Anomali alınmasaydı mevsim döngüsü yüzünden r ≈ 1 çıkardı.
    """
    rng = np.random.default_rng(5)
    dongu = 12 * np.sin(2 * np.pi * (ZAMAN.month - 4) / 12)
    a = _seri(dongu + rng.standard_normal(len(ZAMAN)))
    b = _seri(1.3 * dongu + rng.standard_normal(len(ZAMAN)))
    assert np.corrcoef(a, b)[0, 1] > 0.95                         # tuzak gerçek
    s, = cift_serileri(6, a, b)
    r = iliski_1d(s["x"].values, s["y"].values, 1, t=s["t"])
    assert r["etiket"] == "anlamsiz" and r["n"] == 300


def test_farkli_izgara_reddedilir():
    k1 = xr.DataArray(np.ones((len(ZAMAN), 1, 1)),
                      coords={"time": ZAMAN, "lat": [38.125], "lon": [30.125]}, dims=("time", "lat", "lon"))
    k2 = k1.assign_coords(lat=[38.1])
    with pytest.raises(ValueError):
        cift_serileri(5, k1, k2)
