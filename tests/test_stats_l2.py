"""stats.l2 ve stats.preprocessing: sentetik küplerle eğim, anlamlılık, FDR, şema ve eksik veri kuralı.

Tüm değerler sentetiktir (yer tutucu); gerçek veri kullanılmaz.
"""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from stats import l2
from stats.preprocessing import MEVSIMLER, donem_serisi, l1_oku

ZAMAN = pd.date_range("2001-01", "2025-12", freq="MS")


def _kup(egim_10yil=0.0, nlat=6, nlon=8, phi=0.5, sigma=0.3, seed=0, zaman=ZAMAN,
         lat0=38.125, lon0=32.125):
    """Aylık küp: doğrusal trend + mevsim döngüsü + aylık AR(1) gürültü. Koordinatlar Türkiye karası."""
    rng = np.random.default_rng(seed)
    t_yil = np.asarray((zaman.year - 2001) + (zaman.month - 0.5) / 12)
    e = np.zeros((len(zaman), nlat, nlon))
    e[0] = rng.normal(0, sigma, (nlat, nlon))
    for i in range(1, len(zaman)):
        e[i] = phi * e[i - 1] + rng.normal(0, sigma * np.sqrt(1 - phi ** 2), (nlat, nlon))
    mevsim = 3 * np.sin(2 * np.pi * np.asarray(zaman.month) / 12)
    v = 10 + egim_10yil / 10 * t_yil[:, None, None] + mevsim[:, None, None] + e
    lat = lat0 + 0.25 * np.arange(nlat)
    lon = lon0 + 0.25 * np.arange(nlon)
    da = xr.DataArray(v.astype("float32"), coords={"time": zaman, "lat": lat, "lon": lon},
                      dims=("time", "lat", "lon"), name="sicaklik_2m")
    da.attrs = {"units": "°C", "long_name": "test", "kademe": np.int32(1), "lisans": "CC BY 4.0",
                "doi": "10.0000/test", "urun_surumu": "v0.1", "bilinen_sorunlar": "test notu",
                "kaynak_dosya": "sicaklik_2m__TEST.nc"}
    return da


def test_bilinen_egim_ve_anlamlilik():
    da = _kup(egim_10yil=0.5)
    ds = l2.l2_dosya(da, "sicaklik_2m", maske=np.ones((6, 8), bool))
    y = ds.sel(mevsim="yillik")
    assert float(y["sen_egimi"].median()) == pytest.approx(0.5, abs=0.1)
    assert float((y["anlamli"] == 1).mean()) > 0.9
    kapsar = (y["ga_alt"] <= 0.5) & (0.5 <= y["ga_ust"])
    assert float(kapsar.mean()) >= 0.8
    assert (y["etkin_n"] > 0).all() and (y["gereken_yil"] > 0).all()


def test_trendsiz_kupte_yanlis_pozitif():
    da = _kup(egim_10yil=0.0, nlat=20, nlon=20, seed=11)
    ds = l2.l2_dosya(da, "sicaklik_2m", maske=np.ones((20, 20), bool), mevsimler={"yillik": MEVSIMLER["yillik"]})
    p = ds["p_mk"].sel(mevsim="yillik").values
    oran = float((p <= 0.10).mean())
    assert 0.03 <= oran <= 0.20, oran                        # ham yanlış pozitif ≈ α = 0,10
    assert float((ds["anlamli"] == 1).mean()) <= 0.05         # FDR sonrası neredeyse hiç


def test_sema_sozlesme_2_1():
    da = _kup(egim_10yil=0.5)
    maske = np.ones((6, 8), bool)
    maske[0, :] = False
    ds = l2.l2_dosya(da, "sicaklik_2m", maske=maske)
    assert tuple(ds["sen_egimi"].dims) == ("mevsim", "lat", "lon")
    assert list(ds["mevsim"].values) == ["yillik", "kis", "ilkbahar", "yaz", "sonbahar"]
    for v in ("sen_egimi", "ga_alt", "ga_ust", "p_mk", "p_fdr", "etkin_n", "gereken_yil"):
        assert ds[v].dtype == np.float32, v
    assert ds["anlamli"].dtype == np.int8
    assert (ds["anlamli"].isel(lat=0) == -1).all() and ds["p_fdr"].isel(lat=0).isnull().all()
    assert set(np.unique(ds["anlamli"].values)) <= {-1, 0, 1}
    assert ds["sen_egimi"].attrs["units"] == "°C / 10 yıl"
    a = ds.attrs
    assert a["alfa_fdr"] == 0.10 and int(a["kademe"]) == 1 and a["bilinen_sorunlar"] == "test notu"
    assert a["lisans"] == "CC BY 4.0" and a["doi"] == "10.0000/test" and "olusturma_tarihi" in a
    assert "Hamed-Rao" in a["mk_yontemi"] and "kis: 2002–2025" in a["donem"]


def test_toplanan_degisken_birimi():
    eb, seri = l2.egim_birimi("mm/ay", "yagis")
    assert eb == "mm/dönem / 10 yıl" and seri["yillik"] == "mm/yıl" and seri["kis"] == "mm/mevsim"
    assert l2.egim_birimi("°C", "sicaklik_2m")[0] == "°C / 10 yıl"


def test_eksik_veri_kurali():
    da = _kup(nlat=1, nlon=1, zaman=pd.date_range("2001-01", "2025-09", freq="MS"))
    yil = donem_serisi(da, MEVSIMLER["yillik"])
    assert np.isnan(yil.sel(yil=2025)).all() and np.isfinite(yil.sel(yil=2024)).all()
    assert np.isfinite(donem_serisi(da, MEVSIMLER["yaz"]).sel(yil=2025)).all()
    assert np.isnan(donem_serisi(da, MEVSIMLER["sonbahar"]).sel(yil=2025)).all()
    kis = donem_serisi(da, MEVSIMLER["kis"], kis=True)
    assert int(kis["yil"].min()) == 2002
    # Toplanan değişken: 1 ay eksik → geçerli ay ortalaması × 12; 3 ay eksik → NaN
    bir = xr.ones_like(_kup(nlat=1, nlon=1))
    bir[5] = np.nan                                                # 2001-06 eksik
    bir[12 + 2: 12 + 5] = np.nan                                   # 2002'de 3 ay eksik
    toplam = donem_serisi(bir, MEVSIMLER["yillik"], toplama=True)
    assert toplam.sel(yil=2001).values.item() == pytest.approx(12.0) and np.isnan(toplam.sel(yil=2002)).all()


def _paket(tmp_path):
    """Geçici L1 paketi: yagis üç ürün (GPM 2025-09'da biter) + ICINDEKILER.csv."""
    kok = tmp_path / "outputs" / "trend-dedektifi-turkiye-v0.1" / "L1_kup"
    kok.mkdir(parents=True)
    rows = []
    for i, (urun, son) in enumerate([("GPM", "2025-09"), ("GLDAS", "2025-12"), ("MERRA2", "2025-12")]):
        da = _kup(egim_10yil=-8.0, nlat=4, nlon=4, seed=i, sigma=2.0,
                  zaman=pd.date_range("2001-01", son, freq="MS")).rename("yagis")
        da.attrs.update(units="mm/ay", kademe=np.int32(1))
        da.to_dataset().assign_attrs(da.attrs).to_netcdf(kok / f"yagis__{urun}.nc")
        rows.append({"dosya": f"yagis__{urun}.nc", "degisken": "yagis", "birim": "mm/ay", "kaynak": urun,
                     "kaynak_doi": "x", "donem": f"2001-01 … {son}", "kademe": 1})
    rows.append({"dosya": "rakim__SRTM.nc", "degisken": "rakim", "birim": "m", "kaynak": "SRTM",
                 "kaynak_doi": "x", "donem": "sabit", "kademe": 0})
    pd.DataFrame(rows).to_csv(kok / "ICINDEKILER.csv", index=False, encoding="utf-8-sig")
    return tmp_path / "outputs"


def test_uret_uctan_uca(tmp_path):
    kok = _paket(tmp_path)
    out = l2.uret("v0.1", kok=kok)
    assert sorted(p.name for p in out.glob("*.nc")) == [
        "yagis__GLDAS__trend.nc", "yagis__GPM__trend.nc", "yagis__MERRA2__trend.nc", "yagis__kaynak_uyumu.nc"]
    with xr.open_dataset(out / "yagis__kaynak_uyumu.nc") as ku:
        assert ku.attrs["ortak_donem"] == "2001-01 … 2025-09" and ku.attrs["urunler"] == "GPM, GLDAS, MERRA2"
        assert tuple(ku["k"].dims) == ("mevsim", "lat", "lon")
        k, m = ku["k"].values, ku["m"].values
        assert (k <= m).all() and (m == 3).all()
        assert float((ku["k"].sel(mevsim="yillik") == 3).mean()) > 0.5
    with xr.open_dataset(out / "yagis__GPM__trend.nc") as ds:
        assert ds["anlamli"].dtype == np.int8 and ds["sen_egimi"].attrs["units"] == "mm/dönem / 10 yıl"
    oz = pd.read_csv(out / "OZET.csv", encoding="utf-8-sig")
    assert len(oz) == 3 * 5 and (oz["kara_hucre"] == 16).all()
    assert list(oz.columns) == l2.OZET_COLS


def test_l1_oku(tmp_path):
    kok = _paket(tmp_path)
    da = l1_oku("yagis", "GPM", kok=kok)
    assert da.attrs["kaynak_dosya"] == "yagis__GPM.nc" and da.dims == ("time", "lat", "lon")
    with pytest.raises(FileNotFoundError):
        l1_oku("yagis", "YOK", kok=kok)


def test_isaret_uyumu_ve_uyarilar(tmp_path):
    out = l2.uret("v0.1", kok=_paket(tmp_path))
    with xr.open_dataset(out / "yagis__kaynak_uyumu.nc") as ku:
        iu, k, m = ku["isaret_uyumu"].values, ku["k"].values, ku["m"].values
        assert ku["isaret_uyumu"].dtype == np.float32 and tuple(ku["isaret_uyumu"].dims) == ("mevsim", "lat", "lon")
        ok = m > 0
        assert np.nanmin(iu) >= 1 / 3 - 1e-6 and np.nanmax(iu) <= 1
        assert (iu[ok] >= k[ok] / m[ok] - 1e-6).all()          # anlamlılık şartı yok → k/m'den küçük olamaz
    with xr.open_dataset(out / "yagis__GLDAS__trend.nc") as ds:
        assert "GLDAS-2.1" in ds.attrs["trend_uyarisi"]
    with xr.open_dataset(out / "yagis__GPM__trend.nc") as ds:
        assert "trend_uyarisi" not in ds.attrs
    oz = pd.read_csv(out / "OZET.csv", encoding="utf-8-sig", keep_default_na=False)
    gldas = oz[oz["dosya"] == "yagis__GLDAS.nc"]
    assert gldas["trend_uyarisi"].str.contains("GLDAS-2.1").all()
    assert (oz[oz["dosya"] == "yagis__GPM.nc"]["trend_uyarisi"] == "").all()
    assert pd.to_numeric(oz["mk_yedek_hucre"]).ge(0).all()


def test_isaretle_trendi_degistirmez(tmp_path):
    kok = _paket(tmp_path)
    out = l2.uret("v0.1", kok=kok)
    with xr.open_dataset(out / "yagis__GLDAS__trend.nc") as ds:
        once = ds.load()
    bos = once.copy()
    bos.attrs.pop("trend_uyarisi")
    l2.yaz_nc(bos, out / "yagis__GLDAS__trend.nc")
    oz_once = pd.read_csv(out / "OZET.csv", encoding="utf-8-sig")
    (out / "OZET.csv").unlink()
    (out / "yagis__kaynak_uyumu.nc").unlink()
    l2.isaretle("v0.1", kok=kok)
    with xr.open_dataset(out / "yagis__GLDAS__trend.nc") as ds:
        assert ds.attrs["trend_uyarisi"] == once.attrs["trend_uyarisi"]
        for v in l2.L2_DEGISKENLERI + ("p_fdr", "anlamli"):
            np.testing.assert_array_equal(ds[v].values, once[v].values)
    pd.testing.assert_frame_equal(pd.read_csv(out / "OZET.csv", encoding="utf-8-sig"), oz_once)
    assert (out / "yagis__kaynak_uyumu.nc").exists()


def test_mevsimlik_uyari():
    p = np.full((5, 2, 3), 0.5, dtype="float32")
    p[1, 0, :] = np.nan                                           # kış: 3 hücre hesaplanamadı
    ds = xr.Dataset({"p_mk": (("mevsim", "lat", "lon"), p)}, coords={"mevsim": list(MEVSIMLER)})
    metin = l2.trend_uyarisi("ndvi", "MOD13C2", ds, np.ones((2, 3), bool))
    assert metin == "[kis] kar/bulut nedeniyle kış serisi seyrek (3 hücre)"
    assert l2.mevsim_uyarisi(metin, "kis") == "kar/bulut nedeniyle kış serisi seyrek (3 hücre)"
    assert l2.mevsim_uyarisi(metin, "yaz") == ""
    assert l2.trend_uyarisi("ndvi", "SENTETIK", ds, np.ones((2, 3), bool)) == ""
    hepsi = l2.trend_uyarisi("yuzey_sicakligi_gece", "MOD11C3", ds, np.ones((2, 3), bool))
    assert "Terra" in hepsi and l2.mevsim_uyarisi(hepsi, "yaz") == hepsi
    assert l2.yedek_sayilari("yillik: 1; kis: 0") == {"yillik": 1, "kis": 0}
