"""data.load ve Giovanni karşılaştırması (geçici klasördeki sentetik dosyalarla)."""

import numpy as np
import pandas as pd
import pytest

import data.build as build
import data.grid as grid
from data.check_giovanni import compare, giovanni_convert, read_giovanni_csv
from data.grid import write_netcdf
from data.synthetic import make_synthetic


@pytest.fixture()
def tmp_processed(tmp_path, monkeypatch):
    monkeypatch.setattr(grid, "PROCESSED_DIR", tmp_path)
    write_netcdf(make_synthetic("sicaklik_2m", start="2001-01", end="2002-12"),
                 grid.processed_path("sicaklik_2m", "SENTETIK"))
    return tmp_path


def test_load_synthetic_fallback_warns(tmp_processed):
    with pytest.warns(UserWarning, match="SENTETİK"):
        da = build.load("sicaklik_2m", region="Erzurum")
    assert da.dims == ("time", "lat", "lon")
    assert da.attrs["region_label"] == "Erzurum" and da.attrs["source_product"] == "SENTETIK"


def test_load_real_only_raises(tmp_processed):
    with pytest.raises(FileNotFoundError):
        build.load("sicaklik_2m", sentetik=False)


def test_summarize(tmp_processed):
    df = build.summarize(tmp_processed / "turkiye")
    assert len(df) == 1 and 0 <= df.loc[0, "nan_orani"] < 0.01


GIOVANNI_CSV = """Title:,Area-Averaged of Precipitation monthly 0.1 deg. [GPM GPM_3IMERGM v07] mm/hr
User Start Date:,2001-01-01T00:00:00Z
Bounding Box:,"38.0,37.5,44.0,41.5"
Fill Value (mean_GPM_3IMERGM_07_precipitation):,-9999.9

time,mean_GPM_3IMERGM_07_precipitation
2001-01-01,0.10
2001-02-01,-9999.9
2001-03-01,0.05
2001-04-01,0.02
"""


def test_read_giovanni_csv_user_bbox(tmp_path):
    text = GIOVANNI_CSV.replace('Bounding Box:,"38.0,37.5,44.0,41.5"',
                                'User Bounding Box:,"40.5,39.5,42,40.5"\n'
                                'Data Bounding Box:,"40.625,39.5,41.875,40.5"')
    f = tmp_path / "g.csv"
    f.write_text(text.replace("time,", "time, "), encoding="utf-8")
    s, meta = read_giovanni_csv(f)
    assert meta["bbox"] == (40.5, 39.5, 42.0, 40.5)
    assert s.loc["2001-01-01"] == pytest.approx(0.10)


def test_read_giovanni_csv(tmp_path):
    f = tmp_path / "g.csv"
    f.write_text(GIOVANNI_CSV, encoding="utf-8")
    s, meta = read_giovanni_csv(f)
    assert meta["bbox"] == (38.0, 37.5, 44.0, 41.5)
    assert np.isnan(s.loc["2001-02-01"]) and s.loc["2001-01-01"] == pytest.approx(0.10)
    mm = giovanni_convert(s, "mm_saat_to_mm_ay")
    assert mm.loc["2001-01-01"] == pytest.approx(0.10 * 24 * 31)


def test_compare_metrics():
    idx = pd.date_range("2001-01-01", periods=24, freq="MS")
    a = pd.Series(np.sin(np.arange(24)), index=idx)
    r = compare(a + 1.0, a)
    assert r["korelasyon"] == pytest.approx(1.0) and r["ortalama_fark"] == pytest.approx(1.0)
    assert r["n"] == 24
