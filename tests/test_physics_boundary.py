"""physics/boundary.py testleri (sentetik, internetsiz).

Uzun kapsama testi varsayılan olarak atlanır; çalıştırmak için:
    YAVAS_TEST=1 pytest tests/test_physics_boundary.py -k kapsama
"""

import os
import time

import numpy as np
import pytest
import xarray as xr

from physics.boundary import find_boundary
from physics.synthetic import synthetic_dem, synthetic_trend_map

yavas = pytest.mark.skipif(os.environ.get("YAVAS_TEST") != "1",
                           reason="uzun test; YAVAS_TEST=1 ile çalışır")


@pytest.fixture(scope="module")
def z():
    return synthetic_dem(seed=0)


def test_bilinen_sinir_100m_icinde(z):
    t = synthetic_trend_map(z, z0=2650, a=-0.004, gurultu=0.5, seed=1)
    r = find_boundary(t, rakim=z, region="test", n_boot=200, seed=1)
    assert r["status"] == "ok"
    assert abs(r["boundary_m"] - 2650) <= 100
    lo, hi = r["boundary_ci95_m"]
    assert lo <= r["boundary_m"] <= hi
    assert r["id"] == "sinir_rakim_kar_ortusu_test" and r["type"] == "boundary"
    assert len(r["curve"]["x_m"]) == len(r["curve"]["median_trend"]) > 5


def test_sinir_yok(z):
    t = synthetic_trend_map(z, a=-0.004, gurultu=0.5, sinir_yok=True, seed=2)
    r = find_boundary(t, rakim=z, n_boot=100)
    assert r["status"] == "no_boundary" and r["boundary_m"] is None


def test_bolge_maskesiyle_farkli_sinirlar(z):
    """Aynı haritada batıda 1900 m, doğuda 2650 m sınır: her bölge kendi sınırını bulur."""
    z0 = xr.where(z.lon < 41.0, 1900.0, 2650.0)
    t = synthetic_trend_map(z, z0=z0, a=-0.004, gurultu=0.3, seed=3)
    bati = find_boundary(t, rakim=z, mask=z.lon < 41.0, region="bati", n_boot=100)
    dogu = find_boundary(t, rakim=z, mask=z.lon >= 41.0, region="dogu", n_boot=100)
    assert abs(bati["boundary_m"] - 1900) <= 100
    assert abs(dogu["boundary_m"] - 2650) <= 100
    assert bati["id"] != dogu["id"]


def test_enlem_ekseni(z):
    """Kuzeyde azalış, güneyde artış: enlem ekseninde sınır 39,5° civarında."""
    LAT = xr.broadcast(z.lat, z.lon)[0]
    t = -1.0 * (LAT - 39.5) + 0.0 * z
    r = find_boundary(t, axis="enlem", n_boot=50)
    assert r["status"] == "ok" and abs(r["boundary_deg"] - 39.5) <= 0.25


def test_az_pikselli_bolge(z):
    t = synthetic_trend_map(z, seed=4)
    kucuk = (z.lat < 37.6) & (z.lon < 38.2)  # birkaç piksel
    r = find_boundary(t, rakim=z, mask=kucuk, n_boot=10)
    assert r["status"] == "no_boundary" and "note" in r


def test_izgara_uyusmazligi_hata_verir(z):
    t = synthetic_trend_map(z, seed=5)
    with pytest.raises(ValueError):
        find_boundary(t, rakim=z.isel(lat=slice(1, None)))


def test_1000_bootstrap_birkac_saniye(z):
    t = synthetic_trend_map(z, seed=6)
    t0 = time.time()
    find_boundary(t, rakim=z, n_boot=1000)
    assert time.time() - t0 < 10.0


@yavas
def test_kapsama_60_tohum(z):
    """Bitti kriteri (Adım 3): 60 tohumda %95 aralık gerçek sınırı ≥ %90 kapsamalı.

    BİLİNEN DURUM (2026-11-14): 0,5° ve 1° bloklarla kapsama ≈ %82. Tahmin yansız
    (ortalama 2648 m), ama bootstrap saçılımı (~20 m) gerçek saçılımdan (~28 m) dar.
    Plan gereği ölçüt gevşetilmedi; sonuç KISI3_PLAN.md "Kararlar" bölümünde raporlandı.
    """
    hit, N = 0, 60
    for s in range(100, 100 + N):
        t = synthetic_trend_map(z, z0=2650, a=-0.004, gurultu=0.5, seed=s)
        lo, hi = find_boundary(t, rakim=z, seed=s)["boundary_ci95_m"]
        hit += lo <= 2650 <= hi
    print(f"kapsama = {hit / N:.3f}")
    assert hit / N >= 0.90
