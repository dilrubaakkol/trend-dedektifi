"""subset() ve bölge çözümleme: il / bölge / bbox / GeoJSON / deniz."""

import numpy as np
import pytest
import shapely
import xarray as xr

from data.grid import grid_coords
from data.regions import (REGIONS, _bolgeler, _iller, get_bbox, list_regions, normalize_name,
                          polygon_mask, resolve_region, subset, turkiye_geometry)


def _cube(grid="025", domain="land", nt=3):
    lat, lon = grid_coords(grid)
    da = xr.DataArray(np.ones((nt, lat.size, lon.size)), dims=("time", "lat", "lon"),
                      coords={"time": np.arange(nt), "lat": lat, "lon": lon}, name="x")
    ds = da.to_dataset()
    ds.attrs["domain"] = domain
    return ds


def test_normalize_name():
    assert normalize_name("Şanlıurfa") == "sanliurfa"
    assert normalize_name("İSTANBUL") == "istanbul"
    assert normalize_name("Doğu Anadolu Bölgesi") == "dogu_anadolu_bolgesi"
    assert normalize_name("Hakkâri") == "hakkari"
    assert normalize_name("K. Maraş") == "k_maras"


def test_81_il_7_bolge():
    assert len(_iller()) == 81
    assert len(_bolgeler()) == 7
    all_il = [k for v in _bolgeler().values() for k in v["iller"]]
    assert sorted(all_il) == sorted(_iller())  # her il tam bir bölgede


@pytest.mark.parametrize("name,key", [
    ("Şanlıurfa", "sanliurfa"), ("Sanliurfa", "sanliurfa"), ("SANLIURFA", "sanliurfa"),
    ("Afyon", "afyonkarahisar"), ("Erzurum ili", "erzurum"), ("il:Konya", "konya"), ("Iğdır", "igdir"),
])
def test_resolve_il(name, key):
    r = resolve_region(name)
    assert r["kind"] == "il" and r["key"] == key


def test_resolve_bolge_and_conflicts():
    assert resolve_region("Doğu Anadolu Bölgesi")["key"] == "dogu_anadolu"
    assert resolve_region("dogu_anadolu")["kind"] == "bolge"
    assert resolve_region("konya")["kind"] == "il"
    assert resolve_region("Karadeniz")["kind"] == "bolge"
    assert resolve_region("deniz:Karadeniz")["key"] == "deniz_karadeniz"
    assert resolve_region("Marmara Denizi")["key"] == "deniz_marmara"
    assert resolve_region("demo:konya")["bbox"] == REGIONS["konya"]["bbox"]


def test_legacy_get_bbox():
    assert get_bbox("dogu_anadolu") == (38.0, 37.5, 44.0, 41.5)
    assert get_bbox("konya") == (31.5, 36.8, 34.5, 39.2)


def test_unknown_region():
    with pytest.raises(KeyError):
        resolve_region("Atlantis")
    with pytest.raises(ValueError):
        resolve_region((50, 50, 60, 60))


def test_subset_il_inside_polygon():
    ds = _cube()
    out = subset(ds, "Erzurum")
    geom = _iller()["erzurum"]["geom"]
    m = out["x"].isel(time=0).notnull()
    LON, LAT = np.meshgrid(out.lon, out.lat)
    assert shapely.contains_xy(geom, LON[m.values], LAT[m.values]).all()
    assert out.attrs["region_cells"] == int(m.sum()) > 10
    assert out.attrs["region_kind"] == "il"


def test_bolge_is_union_of_iller():
    ds = _cube()
    region = subset(ds, "ic_anadolu").attrs["region_cells"]
    per_il = sum(subset(ds, f"il:{k}").attrs["region_cells"] for k in _bolgeler()["ic_anadolu"]["iller"])
    assert region == per_il  # merkez kuralında her hücre tek ile düşer


def test_subset_bbox():
    out = subset(_cube(), (39.0, 39.0, 41.0, 40.0))
    assert float(out.lat.min()) >= 39.0 and float(out.lat.max()) <= 40.0
    assert float(out.lon.min()) >= 39.0 and float(out.lon.max()) <= 41.0
    assert out.sizes["lat"] == 4 and out.sizes["lon"] == 8


def test_geojson_rectangle_matches_bbox():
    ds = _cube()
    poly = {"type": "Polygon", "coordinates": [[[39, 39], [41, 39], [41, 40], [39, 40], [39, 39]]]}
    a = subset(ds, poly)
    b = subset(ds, (39.0, 39.0, 41.0, 40.0))
    assert a.attrs["region_cells"] == b.attrs["region_cells"]
    feat = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": poly, "properties": {}}]}
    assert subset(ds, feat).attrs["region_cells"] == a.attrs["region_cells"]


def test_small_il_never_empty_on_coarse_grid():
    out = subset(_cube(), "Yalova")
    assert out.attrs["region_cells"] >= 1


def test_turkiye_cells_match_land_mask():
    ds = _cube()
    lat, lon = grid_coords("025")
    n = int(polygon_mask(turkiye_geometry(), lat, lon).sum())
    assert subset(ds, "turkiye").attrs["region_cells"] == n
    # 0,25° hücre ~ 600 km²; Türkiye ~ 780 bin km² → ~1300 hücre
    assert 1150 < n < 1450


def test_ocean_variable_with_land_region():
    ds = _cube(domain="ocean")
    out = subset(ds, "Trabzon")
    assert out.attrs["region_method"].startswith("kıyı tamponu")
    assert subset(ds, "turkiye").attrs["region_method"] == "tüm kutu"


def test_list_regions():
    r = list_regions()
    assert len(r["il"]) == 81 and len(r["bolge"]) == 7 and len(r["deniz"]) == 5


def test_il_adi_duzeltme_tablosu():
    """Elâzığ (Natural Earth yazımı) → Elazığ; anahtar ve çözümleme değişmez."""
    from data.regions import _iller, il_adi, list_regions, resolve_region
    assert il_adi("Elâzığ") == "Elazığ" and il_adi("Erzurum") == "Erzurum"
    assert _iller()["elazig"]["ad"] == "Elazığ"
    assert ("elazig", "Elazığ") in list_regions()["il"]
    assert resolve_region("Elâzığ")["label"] == "Elazığ" and resolve_region("il:Elazığ")["key"] == "elazig"
    assert not any("â" in ad for _, ad in list_regions()["il"] if ad != "Hakkâri")
