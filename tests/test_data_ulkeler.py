"""Ülke parametresi: Türkiye varsayılanı değişmedi; sentetik ikinci ülkeyle kutu, maske, yollar, harmonize ve
export doğru (internetsiz; değerler yer tutucu)."""

import json

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from data import export, fetch
from data import grid as G
from data import regions as R
from data import ulkeler as U
from data.catalog import load_catalog, variable
from data.harmonize import harmonize_variable


# ------------------------------------------------------------------ Türkiye varsayılanı
def test_turkiye_ayarlari_eski_sabitlerle_ayni():
    tr = U.ulke("turkiye")
    assert U.aktif() == "turkiye" == U.VARSAYILAN
    assert tr["ic_kutu"] == G.TURKIYE_BBOX == tuple(load_catalog()["bbox"])
    assert U.yayin_kutusu() == export.YAYIN_BBOX and export.yayin_sekli(export.YAYIN_BBOX) == export.YAYIN_SHAPE
    assert export.paket_adi("v0.1") == "trend-dedektifi-turkiye-v0.1"


def test_turkiye_yollari_kutu_ve_maske_degismedi():
    lat, lon = G.grid_coords("025")
    lat0, lon0 = G.grid_coords("025", G.TURKIYE_BBOX)
    np.testing.assert_array_equal(lat, lat0)
    np.testing.assert_array_equal(lon, lon0)
    assert (lat.size, lon.size) == (34, 82)
    assert G.processed_path("ndvi", "MOD13C2") == G.PROCESSED_DIR / "turkiye" / "ndvi__MOD13C2.nc"
    assert G.processed_path("ndvi", "MOD13C2", "005") == G.TURKIYE_DIR / "ndvi__MOD13C2__005.nc"
    assert fetch.raw_dir("GLDAS") == G.RAW_DIR / "GLDAS"
    assert fetch._bbox_margin() == (24.0, 33.5, 46.5, 44.0)
    assert int(R.domain_mask("land", lat, lon).sum()) == 1303
    np.testing.assert_array_equal(R.ulke_maskesi(lat, lon), R.domain_mask("land", lat, lon, ulke="turkiye"))
    assert R.resolve_region("turkiye")["kind"] == "turkiye"


def test_baglam_doner_ve_bilinmeyen_ulke_hata():
    with U.ulke_baglami("yunanistan"):
        assert U.aktif() == "yunanistan"
        assert fetch.raw_dir("GLDAS") == G.RAW_DIR / "yunanistan" / "GLDAS"
        assert G.processed_path("ndvi", "MOD13C2").parent.name == "yunanistan"
        assert G.grid_coords("025")[1][0] == pytest.approx(19.125)
    assert U.aktif() == "turkiye"
    with pytest.raises(KeyError, match="Bilinmeyen ülke"):
        with U.ulke_baglami("atlantis"):
            pass
    assert U.aktif() == "turkiye"


def test_yunanistan_yayin_kutusu_sinirdan_hesaplanir():
    g = R.ulke_geometry("yunanistan")
    yk = U.yayin_kutusu_hesapla(tuple(round(v, 4) for v in g.bounds))
    assert yk == U.yayin_kutusu("yunanistan") == (19.5, 34.75, 28.25, 42.0)
    w, s, e, n = U.ic_kutu("yunanistan")
    assert yk[0] >= w and yk[1] >= s and yk[2] <= e and yk[3] <= n
    assert export.yayin_sekli(yk) == (29, 35)
    assert R.resolve_region("Greece")["key"] == "yunanistan" == R.resolve_region("grc")["key"]


def test_yayin_kutusu_hesapla_disa_yuvarlar():
    assert U.yayin_kutusu_hesapla((19.6265, 34.815, 28.2398, 41.7505)) == (19.5, 34.75, 28.25, 42.0)
    assert U.yayin_kutusu_hesapla((20.0, 35.0, 21.0, 36.0)) == (20.0, 35.0, 21.0, 36.0)   # zaten hizalı


# ------------------------------------------------------------------ sentetik ikinci ülke
@pytest.fixture()
def deneme(tmp_path, monkeypatch):
    """Kutusu 10–12 D, 50–52 K; karası 10,5–11,5 D × 50,5–51,5 K kare olan sentetik ülke."""
    kare = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {
        "type": "Polygon", "coordinates": [[[10.5, 50.5], [11.5, 50.5], [11.5, 51.5], [10.5, 51.5], [10.5, 50.5]]]}}]}
    (tmp_path / "kara.geojson").write_text(json.dumps(kare), encoding="utf-8")
    kayit = dict(U._kayitlar())
    kayit["deneme"] = {"anahtar": "deneme", "ad": "Deneme", "iso3": "DNM", "ne_adi": "Deneme",
                       "ic_kutu": (10.0, 50.0, 12.0, 52.0), "yayin_kutusu": (10.5, 50.5, 11.5, 51.5),
                       "kara": str(tmp_path / "kara.geojson"), "kutu_kara": str(tmp_path / "kara.geojson"),
                       "ek_uyarilar": {"toplam_su_depolama__GRACE": "kaba çözünürlük notu"}}
    monkeypatch.setattr(U, "_kayitlar", lambda: kayit)
    monkeypatch.setattr(G, "PROCESSED_DIR", tmp_path / "processed")
    R._ulke_geom.cache_clear()
    R._domain_mask_cached.cache_clear()
    yield tmp_path
    R._ulke_geom.cache_clear()
    R._domain_mask_cached.cache_clear()


def test_ikinci_ulke_kutu_ve_maske(deneme):
    with U.ulke_baglami("deneme"):
        lat, lon = G.grid_coords("025")
        assert (lat.size, lon.size) == (8, 8) and lon[0] == pytest.approx(10.125)
        kara = R.domain_mask("land", lat, lon)
        assert int(kara.sum()) == 16                                  # 4 × 4 hücre merkezi karede
        assert kara[2:6, 2:6].all() and not kara[:2].any()
        assert int(R.domain_mask("ocean", lat, lon).sum()) == 64 - 16
        assert fetch._bbox_margin() == (9.0, 49.0, 13.0, 53.0)
        assert R.resolve_region("deneme")["kind"] == "ulke"
        with pytest.raises(ValueError, match="Deneme kutusunun"):
            R.resolve_region((30.0, 38.0, 31.0, 39.0))               # Türkiye'de bir kutu, ülke kutusu dışında
    np.testing.assert_array_equal(R.ulke_maskesi(lat, lon, "deneme"), kara)
    assert int(R.domain_mask("land", lat, lon).sum()) == 0            # varsayılan (Türkiye) maskesi bu kutuda boş


def test_ikinci_ulke_harmonize_maske_ve_yol(deneme):
    v = variable("toprak_nemi", "GLDAS")
    t = pd.date_range("2001-01", "2001-03", freq="MS")
    lat = np.round(np.arange(49.125, 53.0, 0.25), 6)
    lon = np.round(np.arange(9.125, 13.0, 0.25), 6)
    raw = xr.Dataset({fetch.safe_name(v["dosya_degiskeni"]): (("time", "lat", "lon"),
                                                               np.full((3, lat.size, lon.size), 25.0))},
                     coords={"time": t, "lat": lat, "lon": lon})
    raw.attrs["_download_date"] = "2026-11-15"
    with U.ulke_baglami("deneme"):
        yollar = harmonize_variable(v, grids=["025"], raw=raw)
    assert yollar[0] == deneme / "processed" / "deneme" / "toprak_nemi__GLDAS.nc"
    with xr.open_dataset(yollar[0]) as ds:
        da = ds["toprak_nemi"]
        assert da.shape[1:] == (8, 8) and int(da.isel(time=0).notnull().sum()) == 16
        assert "Deneme kesiti" in ds.attrs["processing"]


def _sentetik_cache(klasor, ad, urun, lat, lon, static=False):
    shape = (lat.size, lon.size) if static else (2, lat.size, lon.size)
    dims = ("lat", "lon") if static else ("time", "lat", "lon")
    coords = {"lat": lat, "lon": lon} if static else {"time": pd.date_range("2001-01", periods=2, freq="MS"),
                                                      "lat": lat, "lon": lon}
    da = xr.DataArray(np.ones(shape, "float32"), coords=coords, dims=dims, name=ad)
    attrs = dict(units="1", long_name=ad, source_product=urun, source_version="1", doi="10.0000/x", daac="d",
                 download_date="2026-11-15", processing="sentetik (yer tutucu)", grid="025", domain="land",
                 valid_start="sabit" if static else "2001-01")
    G.write_netcdf(G.finalize(da, attrs), klasor / f"{ad}__{urun}.nc")


def test_ikinci_ulke_export(deneme):
    with U.ulke_baglami("deneme"):
        lat, lon = G.grid_coords("025")
        src = G.ulke_dir()
    _sentetik_cache(src, "ndvi", "MOD13C2", lat, lon)
    _sentetik_cache(src, "toplam_su_depolama", "GRACE", lat, lon)
    _sentetik_cache(src, "rakim", "SRTM", lat, lon, static=True)
    out = export.export("v0.1", out_root=deneme / "outputs", ulke="deneme")
    assert out == deneme / "outputs" / "trend-dedektifi-deneme-v0.1" / "L1_kup"
    assert U.aktif() == "turkiye"
    with xr.open_dataset(out / "toplam_su_depolama__GRACE.nc") as ds:
        assert ds["toplam_su_depolama"].shape == (2, 4, 4)
        assert ds.attrs["ulke"] == "deneme" and ds.attrs["ulke_iso3"] == "DNM"
        assert ds.attrs["bilinen_sorunlar"] == "kaba çözünürlük notu" and int(ds.attrs["kademe"]) == 1
        assert ds.attrs["yayin_kutusu"] == "10.5, 50.5, 11.5, 51.5"
    with xr.open_dataset(out / "ndvi__MOD13C2.nc") as ds:
        assert "bilinen_sorunlar" not in ds.attrs
    ic = pd.read_csv(out / "ICINDEKILER.csv", encoding="utf-8-sig")
    assert list(ic["dosya"]) == ["ndvi__MOD13C2.nc", "toplam_su_depolama__GRACE.nc", "rakim__SRTM.nc"]


def test_turkiye_export_ulke_attr_yazmaz():
    ds = xr.Dataset(attrs={"processing": "x"})
    a = export.release_attrs(ds, "ndvi", "MOD13C2", "v0.1")
    assert not {"ulke", "ulke_adi", "ulke_iso3"} & set(a)
    b = export.release_attrs(ds, "toplam_su_depolama", "GRACE", "v0.1", U.yayin_kutusu("yunanistan"), ulke="yunanistan")
    assert b["ulke"] == "yunanistan" and "300 km" in b["bilinen_sorunlar"]
