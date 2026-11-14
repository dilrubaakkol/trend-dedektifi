"""physics/harita.py testleri (Faz 3; sentetik, internetsiz).

Sentetik harita: batı şeridine beklenen yönde ilişki, doğu şeridine ters ilişki gömülür,
ortası ilişkisiz; bir köşe deniz (NaN). Doğru yerler doğru etiketi almalı.
"""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from physics.ciftler import CIFT, cift_serileri
from physics.harita import ETIKET_KODU, ETIKET_YOK, cift_haritasi, etiket_ozeti, iliski_harita
from physics.iliski import iliski_1d

ZAMAN = pd.date_range("2001-01", "2025-12", freq="MS")
LAT = 36.125 + 0.25 * np.arange(8)
LON = 30.125 + 0.25 * np.arange(12)
BATI, DOGU = slice(0, 4), slice(8, 12)


def _kup(v):
    return xr.DataArray(v, coords={"time": ZAMAN, "lat": LAT, "lon": LON},
                        dims=("time", "lat", "lon"))


def _gomulu_harita(seed=0, guc=0.8):
    """Aylık sıcaklık ve yüzey sıcaklığı küpleri (çift 6 biçiminde), bilinen ilişki desenli."""
    rng = np.random.default_rng(seed)
    nt = len(ZAMAN)
    dongu = 12 * np.sin(2 * np.pi * (ZAMAN.month.to_numpy() - 4) / 12)[:, None, None]
    a = rng.standard_normal((nt, len(LAT), len(LON)))
    g = rng.standard_normal((nt, len(LAT), len(LON)))
    b = g.copy()
    b[:, :, BATI] = guc * a[:, :, BATI] + np.sqrt(1 - guc ** 2) * g[:, :, BATI]
    b[:, :, DOGU] = -guc * a[:, :, DOGU] + np.sqrt(1 - guc ** 2) * g[:, :, DOGU]
    T, Y = dongu + a, 1.3 * dongu + b
    T[:, :2, -2:] = np.nan                     # deniz köşesi
    Y[:, :2, -2:] = np.nan
    return _kup(T), _kup(Y)


def test_gomulu_desen_dogru_etiketlenir():
    (ad, ds), = cift_haritasi(6, *_gomulu_harita())
    assert ad == "iliski__sicaklik_2m__yuzey_sicakligi_gunduz.nc"
    e = ds["etiket"].values
    assert (e[:, BATI] == ETIKET_KODU["beklenen_yonde"]).all()
    deniz = np.zeros_like(e, bool)
    deniz[:2, -2:] = True
    assert (e[:, DOGU][~deniz[:, DOGU]] == ETIKET_KODU["ters_yonde"]).all()
    assert (e[deniz] == ETIKET_YOK).all() and (ds["anlamli"].values[deniz] == -1).all()
    orta = e[:, 4:8]
    assert (orta == ETIKET_KODU["anlamsiz"]).mean() >= 0.9
    assert ds.attrs["fdr_hucre_sayisi"] == e.size - 4
    assert ds.attrs["cift_no"] == 6 and ds.attrs["donem"].startswith("2001-01")


def test_hucre_sonucu_tek_seri_fonksiyonuyla_ayni():
    """Vektörel hesap = iliski_1d (r, etkin n, p) — her hücrede."""
    s, = cift_serileri(6, *_gomulu_harita(seed=1, guc=0.3))
    ds = iliski_harita(s["x"], s["y"], s["t"], 1)
    for i in range(len(LAT)):
        for j in range(len(LON)):
            r1 = iliski_1d(s["x"].values[:, i, j], s["y"].values[:, i, j], 1, t=s["t"])
            if r1["etiket"] is None:
                assert np.isnan(ds["r"].values[i, j])
                continue
            assert ds["r"].values[i, j] == pytest.approx(r1["r"], abs=1e-5)
            assert ds["etkin_n"].values[i, j] == pytest.approx(r1["etkin_n"], rel=1e-4)
            assert ds["p"].values[i, j] == pytest.approx(r1["p"], rel=1e-3, abs=1e-7)


def test_bosluklu_gecikmeli_seri_de_ayni():
    """Çift 3 (Nisan–Eylül dışı NaN, gecikme) — boşluklu seride de vektörel = tek seri."""
    rng = np.random.default_rng(2)
    nem = rng.standard_normal((len(ZAMAN), len(LAT), len(LON)))
    ndvi = np.roll(nem, 1, axis=0) * 0.4 + rng.standard_normal(nem.shape)
    sonuc = cift_haritasi(3, _kup(nem), _kup(ndvi))
    assert [a for a, _ in sonuc] == ["iliski__toprak_nemi__ndvi__gecikme1.nc",
                                     "iliski__toprak_nemi__ndvi__gecikme2.nc"]
    s = cift_serileri(3, _kup(nem), _kup(ndvi))[0]
    ds = sonuc[0][1]
    for i, j in [(0, 0), (3, 7), (7, 11)]:
        r1 = iliski_1d(s["x"].values[:, i, j], s["y"].values[:, i, j], 1, t=s["t"])
        assert ds["p"].values[i, j] == pytest.approx(r1["p"], rel=1e-3, abs=1e-7)
    assert etiket_ozeti(ds)["beklenen_yonde"] >= 0.9 * ds["r"].size   # gecikme 1 güçlü
    assert sonuc[1][1].attrs["gecikme_ay"] == 2


def test_tamamen_iliskisiz_haritada_fdr_sahte_alarmi_ayiklar():
    """İlişki yok: FDR olmadan ~%5 hücre 'anlamlı' çıkardı; FDR sonrası neredeyse hiç."""
    rng = np.random.default_rng(3)
    lat = 36.125 + 0.25 * np.arange(28)
    lon = 26.125 + 0.25 * np.arange(40)          # 1.120 hücre (Türkiye karası kadar)
    k = {"coords": {"yil": np.arange(2002, 2026), "lat": lat, "lon": lon},
         "dims": ("yil", "lat", "lon")}
    x = xr.DataArray(rng.standard_normal((24, 28, 40)), **k)
    y = xr.DataArray(rng.standard_normal((24, 28, 40)), **k)
    ds = iliski_harita(x, y, np.arange(2002, 2026.0), 1)
    ham = float((ds["p"] < 0.05).mean())
    fdr = float((ds["anlamli"] == 1).mean())
    print(f"ham p<0,05 oranı {ham:.3f}, FDR sonrası {fdr:.4f}")
    assert 0.03 <= ham <= 0.07 and fdr <= 0.01


def test_cift1_kar_maskesi_haritada_hesaplanamadi():
    rng = np.random.default_rng(4)
    a = rng.standard_normal((len(ZAMAN), len(LAT), len(LON)))
    T = -3 + 10 * np.sin(2 * np.pi * (ZAMAN.month.to_numpy() - 4) / 12)[:, None, None] + 2 * a
    kar = np.clip(50 - 10 * a + rng.standard_normal(a.shape), 0, 100)
    kar[:, :, :3] = 1.0 + 0.1 * rng.standard_normal((len(ZAMAN), len(LAT), 3))  # karsız şerit
    (ad, ds), = cift_haritasi(1, _kup(T), _kup(kar))
    assert (ds["etiket"].values[:, :3] == ETIKET_YOK).all()
    assert (ds["etiket"].values[:, 3:] == ETIKET_KODU["beklenen_yonde"]).mean() > 0.9
    assert ds.attrs["fdr_hucre_sayisi"] == len(LAT) * (len(LON) - 3)   # FDR yalnız kapsamda


def test_cift4_harita_yok():
    with pytest.raises(ValueError):
        cift_haritasi(4, *_gomulu_harita())


def test_tipler_ve_netcdf_yazilir(tmp_path):
    (ad, ds), = cift_haritasi(6, *_gomulu_harita())
    assert ds["etiket"].dtype == np.int8 and ds["anlamli"].dtype == np.int8
    assert ds["r"].dtype == np.float32 and ds["r"].dims == ("lat", "lon")
    ds.to_netcdf(tmp_path / ad)
    geri = xr.open_dataset(tmp_path / ad)
    assert list(geri["etiket"].attrs["flag_values"]) == [1, -1, 0, -99]
    assert geri.attrs["cift"] == CIFT[6].kod
    geri.close()
