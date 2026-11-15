"""data/arazi.py testleri: tarım oranı formülü, GFSAD sulanan oranı, üzerine yazmama koruması (internetsiz)."""

import numpy as np
import pytest
import xarray as xr

from data import arazi as A


def _kesit(p12, p14):
    k = {"lat": [36.025, 36.075], "lon": [30.025, 30.075]}
    return xr.Dataset({"yuzde_12": (("lat", "lon"), np.asarray(p12, "float32")),
                       "yuzde_14": (("lat", "lon"), np.asarray(p14, "float32"))}, coords=k)


def test_tarim_orani_formulu_ve_yil_ortalamasi():
    k1 = _kesit([[100, 0], [40, np.nan]], [[0, 100], [20, 50]])
    k2 = _kesit([[100, 0], [60, 10]], [[0, 100], [0, 50]])
    to = A.tarim_orani_hesapla([k1, k2]).values
    # (p12 + ½ p14)/100: [1, 0,5] ; [(0,5+0,6)/2, ...]
    np.testing.assert_allclose(to[0], [1.0, 0.5])
    assert to[1, 0] == pytest.approx(((40 + 10) / 100 + 60 / 100) / 2)
    assert to[1, 1] == pytest.approx((10 + 25) / 100)            # NaN yıl atlanır
    assert np.nanmax(to) <= 1 and np.nanmin(to) >= 0


def test_gfsad_siniflari_belgeyle_uyumlu():
    assert A.SULANAN_SINIFLAR == (1, 2)                          # Irrigation major, minor
    assert 9 in A.KARA_SINIFLARI and 0 not in A.KARA_SINIFLARI   # 9 tarım dışı kara, 0 veri yok


def test_gfsad_oran_sentetik_tif(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    # 0,01° pikseller, 1°×1° alan (36–37 K, 30–31 D): sol yarı sınıf 1, sağ yarı 9; bir köşe 0 (veri yok)
    a = np.full((100, 100), 9, np.uint8)
    a[:, :50] = 1
    a[:10, 90:] = 0
    yol = tmp_path / "g.tif"
    with rasterio.open(yol, "w", driver="GTiff", height=100, width=100, count=1, dtype="uint8",
                       crs="EPSG:4326", transform=from_origin(30.0, 37.0, 0.01, 0.01)) as d:
        d.write(a, 1)
    o = A.gfsad_oran(yol, "025", bbox=(30.0, 36.0, 31.0, 37.0))
    assert o.shape == (4, 4)
    np.testing.assert_allclose(o.values[:, :2], 1.0)             # tamamen sulanan
    np.testing.assert_allclose(o.values[:, 2:], 0.0)             # tarım dışı kara (0 payda dışı)
    o5 = A.gfsad_oran(yol, "005", bbox=(30.0, 36.0, 31.0, 37.0))
    assert np.isnan(o5.values[-2:, -2:]).all()                   # yalnız veri yok → NaN


def test_yeni_dosya_yaz_uzerine_yazmaz(tmp_path):
    ds = xr.Dataset({"x": (("lat", "lon"), np.ones((2, 2)))}, coords={"lat": [1.0, 2.0], "lon": [1.0, 2.0]})
    p = A.yeni_dosya_yaz(ds, tmp_path / "a.nc")
    once = p.read_bytes()
    with pytest.raises(FileExistsError):
        A.yeni_dosya_yaz(ds * 2, p)
    assert p.read_bytes() == once


def test_katalog_kayitlari_toplu_akisa_girmez():
    from data.catalog import product
    from data.fetch import products_for
    for k, doi in (("MCD12C1", "10.5067/MODIS/MCD12C1.061"), ("GFSAD1KCM", "10.5067/MEASURES/GFSAD/GFSAD1KCM.001")):
        assert product(k)["doi"] == doi and product(k)["okuyucu"] == "ozel"
        assert k not in products_for()
