"""Sapma haritası v2 testleri (tarım maskesi + 0,05°) ve bağımsız doğrulama ölçütleri — sentetik, tmp klasörü."""

import inspect
import re
import shutil

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from physics import sapma as SP
from physics import sapma_dogrulama as DG
from physics.ornek_l4 import LAT, LON

YASAK = re.compile(r"insan etkisi var|yüzünden|nedeniyle|sebebi|kanıtla|\bneden\b(?! göstermez)", re.I)
ZAMAN = pd.date_range("2001-01", "2003-12", freq="MS")


# ------------------------------------------------------------------ maske
def test_maske_tarim_disini_nan_yapar():
    s = {"z_yesil": np.array([1.0, 2.0, 3.0, 4.0]), "z_serin": np.array([0.5, 0.5, 0.5, np.nan]),
         "sulama_izi": np.array([0.75, 1.25, 1.75, 4.0]), "n_bilesen": np.array([2, 2, 2, 1], np.int8)}
    tarim = np.array([0.1, 0.3, 0.9, np.nan])
    m = SP.tarim_maskesi(s, tarim)
    np.testing.assert_array_equal(m["tarim_disi"], [True, False, False, True])
    assert np.isnan(m["sulama_izi"][[0, 3]]).all() and np.isnan(m["z_yesil"][0])
    np.testing.assert_array_equal(m["sulama_izi"][1:3], [1.25, 1.75])   # tarım hücreleri değişmez
    np.testing.assert_array_equal(m["n_bilesen"], [0, 2, 2, 0])
    assert np.isnan(SP.tarim_maskesi(s, tarim, esik=0.5)["sulama_izi"][1])  # eşik parametresi


# ------------------------------------------------------------------ ölçütler
def test_auc_ve_precision():
    h = np.array([1, 1, 0, 0, 0, 0, 0, 0, 0, 0], bool)
    assert DG.auc(np.arange(10, 0, -1.0), h) == 1.0
    assert DG.auc(np.arange(10.0), h) == 0.0
    assert DG.auc(np.ones(10), h) == 0.5                       # bilgisiz skor
    # skorsuz hedef 8 karşılaştırmanın hepsini kaybeder, skoru 5 olan hedef hepsini kazanır: 8/16
    assert DG.auc(np.array([np.nan, 5, 1, 1, 1, 1, 1, 1, 1, 1.0]), h) == pytest.approx(0.5)
    assert DG.precision_ust(np.arange(20, 0, -1.0), np.r_[np.ones(1), np.zeros(19)].astype(bool)) == 1.0
    rng = np.random.default_rng(0)
    hh = rng.random(5000) < 0.1
    assert abs(DG.auc(rng.random(5000), hh) - 0.5) < 0.03


def test_degerlendir_skorsuz_hucre_en_dusuk():
    sk = np.array([np.nan, np.nan, 2.0, 1.0])
    sul = np.array([0.5, 0.5, 0.0, 0.0])
    d = DG.degerlendir(sk, sul, np.ones(4, bool))
    assert d["auc"] == 0.0 and d["hedef_hucre"] == 2 and d["skorlu_hucre"] == 2


# ------------------------------------------------------------------ sentetik paket
def _kup(v, lat, lon, ad):
    return xr.DataArray(v.astype("float32"), coords={"time": ZAMAN, "lat": lat, "lon": lon},
                        dims=("time", "lat", "lon")).rename(ad)


def _alan(lat, lon, rng):
    """Hücreye özgü iklim: yağış düzeyi, rakım, yaz yeşilliği ve (LST − T2M) yağış/rakıma bağlı."""
    ny, nx = lat.size, lon.size
    p = rng.uniform(5, 80, (ny, nx))
    z = rng.uniform(0, 2000, (ny, nx))
    ay = ZAMAN.month.to_numpy()[:, None, None]
    yag = p[None] * (1 + 0.5 * np.cos(2 * np.pi * (ay - 1) / 12)) + 0 * ay
    ndvi = 0.1 + 0.08 * np.log1p(p)[None] - 5e-5 * z[None] + rng.normal(0, 0.01, (len(ZAMAN), ny, nx))
    t2m = 20 + 8 * np.sin(2 * np.pi * (ay - 4) / 12) + np.zeros((1, ny, nx))
    lst = t2m + 12 - 1.5 * np.log1p(p)[None] + 0.001 * z[None] + rng.normal(0, 0.3, (len(ZAMAN), ny, nx))
    return yag, ndvi, t2m, lst, z


@pytest.fixture(scope="module")
def paket(tmp_path_factory):
    kok = tmp_path_factory.mktemp("v2") / "paket"
    kup = kok / "L1_kup"
    kup.mkdir(parents=True)
    rng = np.random.default_rng(1)
    yag, ndvi, t2m, lst, z = _alan(LAT, LON, rng)
    for ad, urun, v in (("yagis", "GPM", yag), ("ndvi", "MOD13C2", ndvi), ("sicaklik_2m", "MERRA2", t2m),
                        ("yuzey_sicakligi_gunduz", "MOD11C3", lst)):
        _kup(v, LAT, LON, ad).to_dataset().to_netcdf(kup / f"{ad}__{urun}.nc")
    sabit = {"lat": LAT, "lon": LON}
    xr.DataArray(z, coords=sabit, dims=("lat", "lon")).rename("rakim").to_dataset().to_netcdf(kup / "rakim__SRTM.nc")
    tarim = np.where(np.arange(LON.size)[None, :] % 2 == 0, 0.6, 0.1) * np.ones((LAT.size, 1))
    xr.DataArray(tarim, coords=sabit, dims=("lat", "lon")).rename("tarim_orani").to_dataset().to_netcdf(
        kup / "tarim_orani__MCD12C1.nc")
    # doğrulama katmanı (sulama izine girmemeli)
    (kok / "dogrulama").mkdir()
    xr.DataArray(rng.random((LAT.size, LON.size)), coords=sabit, dims=("lat", "lon")).rename(
        "sulanan_oran").to_dataset().to_netcdf(kok / "dogrulama" / "sulanan_oran__GFSAD1KCM.nc")
    return kok


def test_025_maskesiz_v1_ile_ayni_maskeli_tarim_disi_nan(paket):
    ham = SP.sulama_izi_v2(paket, "025", maske=False)
    g = {k: SP._oku(paket / "L1_kup", *v) for k, v in SP.GIRDILER.items()}
    v1 = SP.sulama_izi(g["ndvi"], g["lst"], g["t2m"], g["yagis"], g["rakim"], ham["kara"])
    np.testing.assert_array_equal(ham["sulama"]["sulama_izi"], v1["sulama_izi"])   # yöntem v1 ile aynı
    m = SP.sulama_izi_v2(paket, "025", maske=True)
    dis = ham["tarim"] < SP.TARIM_ESIK
    assert np.isnan(m["sulama"]["sulama_izi"][dis]).all()
    ic = ~dis & np.isfinite(ham["sulama"]["sulama_izi"])
    np.testing.assert_array_equal(m["sulama"]["sulama_izi"][ic], ham["sulama"]["sulama_izi"][ic])


def test_dogrulama_katmani_silinse_de_sulama_izi_ayni(paket, tmp_path):
    kopya = tmp_path / "paket"
    shutil.copytree(paket, kopya)
    once = SP.sulama_izi_v2(kopya, "025", maske=True)["sulama"]["sulama_izi"]
    shutil.rmtree(kopya / "dogrulama")                         # testin kendi geçici kopyası
    sonra = SP.sulama_izi_v2(kopya, "025", maske=True)["sulama"]["sulama_izi"]
    np.testing.assert_array_equal(once, sonra)
    for f in (SP.sulama_izi_v2, SP.sulama_izi, SP.tarim_maskesi, SP.v2_uret_yaz):
        kod = inspect.getsource(f).lower()
        assert "sulanan" not in kod and "gfsad" not in kod and "dogrulama" not in kod, f.__name__


def test_005_en_yakin_komsu_ve_v1_dosyalarina_dokunmaz(paket, tmp_path, monkeypatch):
    """0,05° yolu: NDVI/LST/rakım/tarım 0,05° dosyalardan, yağış ve T2M 0,25°'den en yakın komşu."""
    import data.grid as G
    rng = np.random.default_rng(2)
    lat5 = np.round(35.525 + 0.05 * np.arange(140), 6)
    lon5 = np.round(25.525 + 0.05 * np.arange(390), 6)
    yag, ndvi, t2m, lst, z = _alan(lat5, lon5, rng)
    d = tmp_path / "islenmis"
    d.mkdir()
    _kup(ndvi, lat5, lon5, "ndvi").to_dataset().to_netcdf(d / "ndvi__MOD13C2__005.nc")
    _kup(lst, lat5, lon5, "yuzey_sicakligi_gunduz").to_dataset().to_netcdf(d / "yuzey_sicakligi_gunduz__MOD11C3__005.nc")
    sabit = {"lat": lat5, "lon": lon5}
    xr.DataArray(z, coords=sabit, dims=("lat", "lon")).rename("rakim").to_dataset().to_netcdf(d / "rakim__SRTM__005.nc")
    xr.DataArray(np.full(z.shape, 0.5), coords=sabit, dims=("lat", "lon")).rename("tarim_orani").to_dataset() \
        .to_netcdf(d / "tarim_orani__MCD12C1__005.nc")
    monkeypatch.setattr(G, "processed_path", lambda dg, u, grid="025", bolge="turkiye":
                        d / f"{dg}__{u}{'' if grid == '025' else '__' + grid}.nc")
    v = SP.sulama_izi_v2(paket, "005", maske=True)
    assert v["sulama"]["sulama_izi"].shape == (140, 390)
    assert np.isfinite(v["sulama"]["sulama_izi"][v["kara"]]).mean() > 0.9

    hedef = paket / "L4_iliski" / "sapma"
    hedef.mkdir(parents=True, exist_ok=True)
    v1 = hedef / "sapma_haritasi.nc"
    v1.write_bytes(b"v1 dosyasi")
    r = SP.v2_uret_yaz(paket)
    assert v1.read_bytes() == b"v1 dosyasi"                     # v1 dosyasına dokunulmadı
    assert sorted(p.name for p in r["yollar"]) == sorted([*SP.V2_DOSYALARI.values(), SP.V2_KUMELER])
    with xr.open_dataset(hedef / SP.V2_DOSYALARI["005"]) as ds:
        assert ds.attrs["surum"] == "v2" and "en yakın komşu" in ds.attrs["yontem"]
        assert "neden göstermez" in ds.attrs["uyari"]
        metin = " ".join(str(x) for x in ds.attrs.values())
        assert int(ds["tarim_disi"].sum()) == 0                 # sentetik tarım oranı 0,5 ≥ 0,3
    assert not YASAK.search(metin)
    assert "tutarlı olabilir" in SP.SULAMA_NOTU and "doğrulanmadı" in SP.SULAMA_NOTU


def test_v2_maske_yoksa_anlasilir_hata(paket, tmp_path):
    kopya = tmp_path / "p"
    shutil.copytree(paket, kopya)
    (kopya / "L1_kup" / "tarim_orani__MCD12C1.nc").unlink()     # testin kendi geçici kopyası
    with pytest.raises(ValueError, match="python -m data.arazi"):
        SP.sulama_izi_v2(kopya, "025", maske=True)
    assert np.isfinite(SP.sulama_izi_v2(kopya, "025", maske=False)["sulama"]["sulama_izi"]).any()
