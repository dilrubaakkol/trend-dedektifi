"""data.export: yayın kutusuna kırpma, kademe attrs ve içindekiler (sentetik verinin kopyalarıyla)."""

import csv

import numpy as np
import pytest
import xarray as xr

from data import export
from data.grid import write_netcdf
from data.synthetic import make_synthetic


def _fake_real(degisken, product="FAKE", doi="10.0000/kaynak"):
    """Sentetik küpü 'gerçek' gibi etiketler (yalnız test için; değerler yer tutucu)."""
    ds = make_synthetic(degisken, start="2001-01", end="2001-12")
    for k in ("synthetic_truth", "yer_tutucu"):
        ds.attrs.pop(k, None)
    ds.attrs.update(source_product=product, source_version="1", doi=doi)
    return ds


@pytest.fixture()
def src(tmp_path):
    d = tmp_path / "turkiye"
    write_netcdf(_fake_real("yagis"), d / "yagis__GPM.nc")
    write_netcdf(_fake_real("yagis"), d / "yagis__GLDAS.nc")
    write_netcdf(_fake_real("sicaklik_2m"), d / "sicaklik_2m__MERRA2.nc")
    write_netcdf(_fake_real("yagis"), d / "yagis__GPM__005.nc")       # 0,05° girmemeli
    write_netcdf(make_synthetic("toprak_nemi", start="2001-01", end="2001-12"),
                 d / "toprak_nemi__GLDAS.nc")                         # sentetik girmemeli
    return d


def test_crop_shape_and_edges():
    ds = _fake_real("yagis")
    cut = export.crop_to_bbox(ds)
    assert (cut.sizes["lat"], cut.sizes["lon"]) == (28, 78)
    assert cut["lon"].values[0] - 0.125 == pytest.approx(25.5)
    assert cut["lon"].values[-1] + 0.125 == pytest.approx(45.0)
    assert cut["lat"].values[0] - 0.125 == pytest.approx(35.5)
    assert cut["lat"].values[-1] + 0.125 == pytest.approx(42.5)


def test_crop_rejects_misaligned_box():
    with pytest.raises(ValueError, match="oturmuyor|boyutu"):
        export.crop_to_bbox(_fake_real("yagis"), bbox=(25.6, 35.5, 45.0, 42.5), shape=None)


def test_export_package(src, tmp_path):
    out = export.export("v0.1", src_dir=src, out_root=tmp_path / "outputs")
    names = sorted(p.name for p in out.glob("*.nc"))
    assert names == ["sicaklik_2m__MERRA2.nc", "yagis__GLDAS.nc", "yagis__GPM.nc"]
    with xr.open_dataset(out / "yagis__GPM.nc") as ds:
        a = ds.attrs
        assert ds["yagis"].shape[1:] == (28, 78)
    assert a["urun_surumu"] == "v0.1" and a["lisans"] == "CC BY 4.0"
    assert a["veri_seti_doi"] == "(yayında doldurulacak)" and a["doi"] == "10.0000/kaynak"
    assert int(a["kademe"]) == 1 and "dogrulanmadi" not in a
    with xr.open_dataset(out / "yagis__GLDAS.nc") as ds:
        assert int(ds.attrs["kademe"]) == 2 and ds.attrs["dogrulanmadi"] == "evet"
    with open(out / "ICINDEKILER.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == export.ICINDEKILER_COLS
    assert [r["kademe"] for r in rows] == ["1", "1", "2"]
    assert rows[0]["donem"] == "2001-01 … 2001-12"


def test_data_period_static_and_empty():
    ds = _fake_real("yagis").isel(time=0, drop=True)
    assert export.data_period(ds) == "sabit"
    ds2 = _fake_real("yagis")
    ds2["yagis"][:] = np.nan
    assert export.data_period(ds2) == "veri yok"
