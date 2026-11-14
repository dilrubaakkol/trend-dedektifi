"""Birim dönüşümleri, bayraklar, zaman damgası, yeniden ızgaralama ve katalog tutarlılığı."""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from data.catalog import load_catalog, variable, variables
from data.fetch import _gctp_geo_axes, _parse_dmr, safe_name
from data.harmonize import (UNIT_CONVERSIONS, apply_flags, convert_units, overlap_weights,
                            regrid, regrid_conservative, to_month_start)


def _series(values, start="2024-01-01", freq="MS"):
    t = pd.date_range(start, periods=len(values), freq=freq)
    return xr.DataArray(np.asarray(values, float), coords={"time": t}, dims="time")


def test_k_to_c():
    assert float(convert_units(_series([273.15]), {"donusum": "K_to_C"})[0]) == pytest.approx(0.0)


def test_flux_to_mm_per_month_leap_year():
    # 1 kg m-2 s-1 sabit oran: Şubat 2024 (29 gün) ve Şubat 2023 (28 gün)
    a = convert_units(_series([1e-5], "2024-02-01"), {"donusum": "kg_m2_s_to_mm_ay"})
    b = convert_units(_series([1e-5], "2023-02-01"), {"donusum": "kg_m2_s_to_mm_ay"})
    assert float(a[0]) == pytest.approx(1e-5 * 86400 * 29)
    assert float(b[0]) == pytest.approx(1e-5 * 86400 * 28)


def test_gldas_acc_and_imerg():
    # GLDAS _acc: 3 saatlik birikim ortalaması 0,1 mm → 0,1 × 8 × 31 (Ocak)
    assert float(convert_units(_series([0.1]), {"donusum": "acc3h_to_mm_ay"})[0]) == pytest.approx(24.8)
    # IMERG 0,1 mm/saat Nisan → 0,1 × 24 × 30
    assert float(convert_units(_series([0.1], "2024-04-01"), {"donusum": "mm_saat_to_mm_ay"})[0]) == pytest.approx(72.0)


def test_scale_offset_modis():
    v = {"donusum": "olcek", "olcek": 0.02, "ofset": -273.15}
    assert float(convert_units(_series([15000]), v)[0]) == pytest.approx(26.85)
    assert float(convert_units(_series([5000]), {"donusum": "olcek", "olcek": 0.0001})[0]) == pytest.approx(0.5)


def test_other_conversions():
    assert float(convert_units(_series([101325.0]), {"donusum": "Pa_to_hPa"})[0]) == pytest.approx(1013.25)
    assert float(convert_units(_series([0.4]), {"donusum": "kesir_to_yuzde"})[0]) == pytest.approx(40)
    assert float(convert_units(_series([3e15]), {"donusum": "molek_to_1e15"})[0]) == pytest.approx(3)
    with pytest.raises(KeyError):
        convert_units(_series([1]), {"donusum": "bilinmeyen"})


def test_flags_range_quality():
    raw = xr.DataArray([0, 50, 100, 211, 250, 255], dims="x")
    out = apply_flags(raw, {"gecerli_aralik": [0, 100]})
    assert np.isnan(out[3:]).all() and float(out[1]) == 50
    out = apply_flags(xr.DataArray([0.0, 300.0], dims="x"), {"bayraklar": [0]})
    assert np.isnan(out[0]) and float(out[1]) == 300
    q = xr.DataArray([0, 1, 2, 3], dims="x")
    out = apply_flags(xr.DataArray([1, 2, 3, 4], dims="x"), {"kalite": {"degisken": "q", "izinli": [0, 1]}}, q)
    assert out.notnull().values.tolist() == [True, True, False, False]


def test_daily_to_monthly_min_days():
    t = pd.date_range("2024-01-01", "2024-02-29", freq="D")
    v = np.ones(t.size)
    v[31:] = np.nan
    v[31:34] = 5.0  # Şubat'ta yalnız 3 geçerli gün → NaN
    da = xr.DataArray(v, coords={"time": t}, dims="time")
    out, note = to_month_start(da, "gunluk")
    assert list(pd.DatetimeIndex(out.time)) == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01")]
    assert float(out[0]) == 1.0 and np.isnan(out[1])


def test_irregular_monthly_to_month_start():
    t = pd.to_datetime(["2003-01-16", "2003-02-14", "2003-02-27"])
    out, note = to_month_start(xr.DataArray([1.0, 2.0, 4.0], coords={"time": t}, dims="time"), "aylik_duzensiz")
    assert list(pd.DatetimeIndex(out.time).day) == [1, 1]
    assert float(out[1]) == 3.0


def test_overlap_weights_rows_sum_to_one():
    src = np.arange(25.025, 45.5, 0.05)
    dst = np.arange(25.125, 45.5, 0.25)
    w = overlap_weights(src, dst)
    np.testing.assert_allclose(w.sum(1), 1.0)
    w2 = overlap_weights(np.round(np.arange(24.05, 46.5, 0.1), 6), dst)  # IMERG gibi hizasız
    np.testing.assert_allclose(w2.sum(1), 1.0, atol=1e-9)


def test_conservative_block_mean_and_nan_threshold():
    lat = np.round(np.arange(34.525, 43.0, 0.05), 6)
    lon = np.round(np.arange(25.025, 45.5, 0.05), 6)
    x = np.add.outer(lat, lon)
    x[:5, :5] = np.nan              # ilk 0,25° hücrenin tamamı NaN
    x[5:10, 0:2] = np.nan           # ikinci satırdaki hücrenin %40'ı NaN → hâlâ değer
    da = xr.DataArray(x, dims=("lat", "lon"), coords={"lat": lat, "lon": lon})
    out, note = regrid(da, "025")
    assert out.shape == (34, 82) and "blok ortalama" in note
    assert np.isnan(out[0, 0])
    expected = np.nanmean(x[5:10, 0:5])
    assert float(out[1, 0]) == pytest.approx(expected)
    assert float(out[3, 3]) == pytest.approx(np.mean(x[15:20, 15:20]))


def test_coarse_product_interpolated():
    lat = np.arange(33.0, 45.0, 0.5)
    lon = np.arange(24.0, 47.0, 0.625)
    da = xr.DataArray(np.add.outer(lat, np.zeros_like(lon)), dims=("lat", "lon"), coords={"lat": lat, "lon": lon})
    out, note = regrid(da, "025")
    assert "bilineer" in note
    np.testing.assert_allclose(out.isel(lon=0).values, out.lat.values)  # lat'a doğrusal alan korunur


def test_catalog_consistency():
    cat = load_catalog()
    for v in cat["degiskenler"]:
        for k in ("ad", "urun", "kategori", "domain", "dosya_degiskeni", "birim", "donusum", "long_name"):
            assert k in v, (v["ad"], k)
        assert v["donusum"] in UNIT_CONVERSIONS
        assert v["domain"] in ("land", "ocean", "all")
    for key, p in cat["urunler"].items():
        for k in ("short_name", "version", "daac", "doi", "dosya_kodu", "erisim", "zaman", "valid_start"):
            assert k in p, (key, k)
    names = {v["ad"] for v in cat["degiskenler"]}
    for n in ("sicaklik_2m", "yagis", "kar_ortusu", "kar_su_esdegeri", "toprak_nemi", "buharlasma",
              "yuzey_akisi", "ndvi", "rakim"):
        assert n in names
        assert variable(n).get("ana")
    assert {v["ad"] for v in variables(categories=["hava_kalitesi"])} >= {"no2", "aerosol_optik_derinlik"}


def test_safe_name_matches_opendap_naming():
    assert safe_name("CMG 0.05 Deg Monthly NDVI") == "CMG_0_05_Deg_Monthly_NDVI"


def test_gctp_geo_axes_modis_cmg():
    sm = "UpperLeftPointMtrs=(-180000000.000000,90000000.000000)\nLowerRightMtrs=(180000000.000000,-90000000.000000)"
    lat, lon = _gctp_geo_axes(sm, 3600, 7200)
    assert lat[0] == pytest.approx(89.975) and lat[-1] == pytest.approx(-89.975)
    assert lon[0] == pytest.approx(-179.975)
    assert np.any(np.isclose(lat, 42.975)) and np.any(np.isclose(lon, 25.025))


def test_parse_dmr():
    xml = """<Dataset xmlns="http://xml.opendap.org/ns/DAP/4.0#" name="x">
      <Dimension name="lat" size="600"/><Dimension name="lon" size="1440"/>
      <Float32 name="lat"><Dim name="/lat"/></Float32>
      <Group name="Grid"><Float32 name="precipitation"><Dim name="/lon"/><Dim name="/lat"/></Float32></Group>
    </Dataset>"""
    d = _parse_dmr(xml)
    assert d["sizes"]["/lat"] == 600
    assert d["vars"]["/Grid/precipitation"]["dims"] == ["/lon", "/lat"]
