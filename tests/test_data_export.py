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
    write_netcdf(_fake_real("yagis"), d / "bulut_orani__MERRA2.nc")       # Kademe 2 örneği
    write_netcdf(_fake_real("yagis").isel(time=0, drop=True), d / "rakim__SRTM.nc")  # kademesiz (0)
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
    assert names == ["bulut_orani__MERRA2.nc", "rakim__SRTM.nc", "sicaklik_2m__MERRA2.nc",
                     "yagis__GLDAS.nc", "yagis__GPM.nc"]
    with xr.open_dataset(out / "yagis__GPM.nc") as ds:
        a = ds.attrs
        assert ds["yagis"].shape[1:] == (28, 78)
    assert a["urun_surumu"] == "v0.1" and a["lisans"] == "CC BY 4.0"
    assert a["veri_seti_doi"] == "(yayında doldurulacak)" and a["doi"] == "10.0000/kaynak"
    assert int(a["kademe"]) == 1 and "dogrulanmadi" not in a
    assert "yayın kutusuna kırpıldı" in a["processing"] and a["yayin_kutusu"] == "25.5, 35.5, 45.0, 42.5"
    with xr.open_dataset(out / "yagis__GLDAS.nc") as ds:
        assert int(ds.attrs["kademe"]) == 1 and "dogrulanmadi" not in ds.attrs
    with xr.open_dataset(out / "bulut_orani__MERRA2.nc") as ds:
        assert int(ds.attrs["kademe"]) == 2 and ds.attrs["dogrulanmadi"] == "evet"
    with xr.open_dataset(out / "rakim__SRTM.nc") as ds:
        assert ds.attrs["kademe"] == 0 and ds.attrs["kademe"].dtype == np.int32 and "dogrulanmadi" not in ds.attrs
    with open(out / "ICINDEKILER.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == export.ICINDEKILER_COLS
    assert [r["kademe"] for r in rows] == ["1", "1", "1", "2", "0"]
    assert rows[0]["donem"] == "2001-01 … 2001-12" and rows[-1]["donem"] == "sabit"


def test_known_issue_attr_carried(src, tmp_path):
    p = src / "yagis__GLDAS.nc"
    with xr.open_dataset(p) as ds:
        ds = ds.load()
    ds.attrs["bilinen_sorunlar"] = "test notu"
    write_netcdf(ds, p)
    out = export.export("v0.1", src_dir=src, out_root=tmp_path / "outputs")
    with xr.open_dataset(out / "yagis__GLDAS.nc") as d:
        assert d.attrs["bilinen_sorunlar"] == "test notu"
    with xr.open_dataset(out / "yagis__GPM.nc") as d:
        assert "bilinen_sorunlar" not in d.attrs


def test_catalog_known_issue_gldas_precip():
    from data.catalog import variable
    assert "2025-12" in variable("yagis", "GLDAS")["bilinen_sorunlar"]
    assert "bilinen_sorunlar" not in variable("yagis", "GPM")


def test_kademe_mapping():
    assert export.kademe("ndvi", "MOD13C2") == 1 and export.kademe("evi", "MOD13C2") == 2
    assert export.kademe("toplam_su_depolama", "GRACE") == 1 and export.kademe("rakim", "SRTM") == 0


def test_data_period_static_and_empty():
    ds = _fake_real("yagis").isel(time=0, drop=True)
    assert export.data_period(ds) == "sabit"
    ds2 = _fake_real("yagis")
    ds2["yagis"][:] = np.nan
    assert export.data_period(ds2) == "veri yok"


def test_release_attrs_flags():
    ds = _fake_real("yagis")
    ds.attrs["dogrulanmadi"] = "evet — katalog kaydının bir kısmı doğrulanmadı"  # eski harmonize adı
    a1 = export.release_attrs(ds, "yagis", "GPM", "v0.1")
    assert "dogrulanmadi" not in a1 and a1["katalog_dogrulanmadi"].startswith("evet")
    assert a1["kademe"].dtype == np.int32
    a2 = export.release_attrs(ds, "evi", "MOD13C2", "v0.1")
    assert a2["dogrulanmadi"] == "evet" and a2["katalog_dogrulanmadi"].startswith("evet")


def test_catalog_flag_renamed():
    from data.catalog import load_catalog, unverified
    cat = load_catalog()
    recs = list(cat["urunler"].values()) + cat["degiskenler"]
    assert not any("dogrulanmadi" in r for r in recs)
    assert any(r.get("katalog_dogrulanmadi") for r in recs) and unverified()
