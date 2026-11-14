"""physics/mirror.py ve bölge bazlı sınır yardımcısı testleri (sentetik, internetsiz)."""

import numpy as np
import pytest
import xarray as xr

from physics.mirror import find_mirror_clusters
from physics.synthetic import synthetic_dem, synthetic_trend_map


@pytest.fixture(scope="module")
def z():
    return synthetic_dem(seed=0)


def _anlamli(t, esik=0.5):
    """FDR maskesinin yerine geçici eşik (Kişi 2'nin maskesi gelene kadar)."""
    return np.abs(t) > esik


def test_rakima_bagli_trendde_eksen_rakim(z):
    t = synthetic_trend_map(z, z0=2650, a=-0.004, gurultu=0.3, seed=1)
    r = find_mirror_clusters(t, _anlamli(t), rakim=z, region="test")
    assert r["status"] == "ok" and r["suggested_axis"] == "rakim"
    assert r["n_clusters"]["pozitif"] >= 1 and r["n_clusters"]["negatif"] >= 1
    neg = [k for k in r["clusters"] if k["sign"] < 0]
    pos = [k for k in r["clusters"] if k["sign"] > 0]
    # azalan (negatif) kümeler yüksekte, artan kümeler alçakta
    assert min(k["mean_rakim_m"] for k in neg) > max(k["mean_rakim_m"] for k in pos)
    assert r["id"] == "ayna_kar_ortusu_test" and r["type"] == "mirror"


@pytest.mark.parametrize("eksen,koord", [("enlem", "lat"), ("boylam", "lon")])
def test_konuma_bagli_trendde_eksen(z, eksen, koord):
    K = xr.broadcast(z[koord], z)[0]
    orta = float(z[koord].mean())
    t = -1.0 * (K - orta) + 0.0 * z
    r = find_mirror_clusters(t, _anlamli(t, 0.2), rakim=z)
    assert r["suggested_axis"] == eksen


def test_tek_yon_ayna_yok(z):
    t = synthetic_trend_map(z, sinir_yok=True, seed=2)
    r = find_mirror_clusters(t, rakim=z)
    assert r["status"] == "no_mirror" and r["suggested_axis"] is None
    assert r["n_clusters"]["negatif"] == 0


def test_kucuk_kumeler_atilir(z):
    t = xr.zeros_like(z) + 1.0
    t[10:13, 10:13] = -1.0  # 9 piksellik negatif küme
    r = find_mirror_clusters(t, rakim=z, min_kume=20)
    assert r["n_clusters"]["negatif"] == 0 and r["status"] == "no_mirror"
    r2 = find_mirror_clusters(t, rakim=z, min_kume=5)
    assert r2["n_clusters"]["negatif"] == 1 and r2["status"] == "ok"


def test_anlamsiz_pikseller_kumeye_girmez(z):
    t = synthetic_trend_map(z, z0=2650, gurultu=0.3, seed=3)
    hic = xr.zeros_like(z, dtype=bool)
    r = find_mirror_clusters(t, hic, rakim=z)
    assert r["clusters"] == [] and r["status"] == "no_mirror"


def test_bolge_bazli_sinirlar_turkiye():
    """Türkiye geneli + 7 bölge; Kişi 1'in sentetik rakımı ve gerçek bölge sınırlarıyla."""
    import warnings
    from data.synthetic import synthetic_elevation
    from physics.boundary import TURKIYE_BOLGELERI, find_boundaries
    zt = synthetic_elevation("025")
    t = synthetic_trend_map(zt, z0=1500, a=-0.004, gurultu=0.3, seed=1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rs = find_boundaries(t, zt, n_boot=50, min_pixels=10)
    assert [r["region"] for r in rs] == list(TURKIYE_BOLGELERI)
    assert len({r["id"] for r in rs}) == len(rs)  # id'ler benzersiz
    for r in rs:
        if r["status"] == "ok":
            assert abs(r["boundary_m"] - 1500) <= 200  # 0,25°'de dilim 200 m


def test_birbirine_bagli_eksenlerde_uyari(z):
    """Rakım tamamen boylama bağlıysa veri ikisini ayıramaz → alternatif eksen + not."""
    LON = xr.broadcast(z.lat, z.lon)[1].transpose("lat", "lon")
    zb = 1000.0 + 200.0 * (LON - 38.0)  # rakım = boylamın doğrusal fonksiyonu
    t = -0.004 * (zb - 1600.0)
    r = find_mirror_clusters(t, np.abs(t) > 0.2, rakim=zb)
    assert {r["suggested_axis"], r["alternative_axis"]} == {"rakim", "boylam"}
    assert "ayırt edemiyor" in r["note"]


def test_bagimsiz_eksenlerde_uyari_yok(z):
    t = synthetic_trend_map(z, z0=2650, a=-0.004, gurultu=0.3, seed=1)
    r = find_mirror_clusters(t, np.abs(t) > 0.5, rakim=z)
    assert "alternative_axis" not in r
