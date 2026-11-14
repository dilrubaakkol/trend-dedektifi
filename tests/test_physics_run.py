"""physics/run.py testleri (Faz 5; sentetik, internetsiz, yalnız tmp klasörüne yazar)."""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from physics import run
from physics.ornek_l4 import ornek_veri


@pytest.fixture(scope="module")
def veri():
    return ornek_veri(seed=1)


def _gercek_gibi(da: xr.DataArray) -> xr.DataArray:
    """Sentetik küpü 'gerçek L1 dosyası' gibi göster (yalnız test için)."""
    d = da.copy()
    d.attrs = {"urun_surumu": "v0.1", "veri_seti_doi": "(yayında doldurulacak)",
               "lisans": "CC BY 4.0", "doi": "10.5067/TEST", "kademe": 1,
               "source_product": "TEST"}
    return d


def _paket(tmp_path, veri, adlar, donustur=_gercek_gibi):
    kup = tmp_path / "paket" / "L1_kup"
    kup.mkdir(parents=True)
    for ad in adlar:
        donustur(veri[ad]).rename(ad.split("__")[0]).to_dataset().to_netcdf(kup / f"{ad}.nc")
    return tmp_path / "paket"


def test_l4_yaz_tum_dosyalar(veri, tmp_path):
    oz = run.l4_yaz(veri, tmp_path / "L4", iller=False)
    adlar = sorted(p.name for p in (tmp_path / "L4").iterdir())
    assert adlar == sorted([
        "ciftler.csv", "iliski__sicaklik_2m__kar_ortusu.nc", "iliski__yagis__toprak_nemi.nc",
        "iliski__toprak_nemi__ndvi__gecikme1.nc", "iliski__toprak_nemi__ndvi__gecikme2.nc",
        "iliski__sicaklik_2m__buharlasma.nc", "iliski__sicaklik_2m__yuzey_sicakligi_gunduz.nc"])
    assert oz["sentetik"] is True
    with xr.open_dataset(tmp_path / "L4" / "iliski__sicaklik_2m__buharlasma.nc") as ds:
        assert "YER TUTUCU" in ds.attrs["yer_tutucu"]
        assert ds.attrs["kademe"] == 2 and ds.attrs["dogrulanmadi"] == "evet"
        assert ds["etiket"].dtype == np.int8 and "_FillValue" not in ds["etiket"].encoding
        assert ds["r"].dtype == np.float32
    df = pd.read_csv(tmp_path / "L4" / "ciftler.csv", encoding="utf-8-sig")
    assert df["not"].str.startswith("Bu dosyadaki sayılar YER TUTUCUDUR").all()


def test_paketten_okur_ve_pakete_yazar(veri, tmp_path):
    paket = _paket(tmp_path, veri, ["sicaklik_2m__MERRA2", "yuzey_sicakligi_gunduz__MOD11C3"])
    run.main(["--paket", str(paket), "--iller-yok"])
    l4 = paket / "L4_iliski"
    assert (l4 / "iliski__sicaklik_2m__yuzey_sicakligi_gunduz.nc").exists()
    df = pd.read_csv(l4 / "ciftler.csv", encoding="utf-8-sig")
    assert set(df["cift_no"]) == {6}                    # yalnız girdisi olan çift
    assert not df["not"].fillna("").str.contains("YER TUTUCU").any()
    assert (df["urun_surumu"] == "v0.1").all() and (df["doi_1"] == "10.5067/TEST").all()
    with xr.open_dataset(l4 / "iliski__sicaklik_2m__yuzey_sicakligi_gunduz.nc") as ds:
        assert "yer_tutucu" not in ds.attrs and ds.attrs["veri_seti_doi"] == "(yayında doldurulacak)"


def test_sentetik_l1_pakete_yazilmaz(veri, tmp_path):
    """Yayın paketine asla sentetik sonuç girmez."""
    paket = _paket(tmp_path, veri, ["sicaklik_2m__MERRA2", "yuzey_sicakligi_gunduz__MOD11C3"],
                   donustur=lambda d: d)                # attrs: source_product = SENTETIK
    with pytest.raises(SystemExit, match="sentetik"):
        run.main(["--paket", str(paket), "--iller-yok"])
    assert not (paket / "L4_iliski").exists()


def test_l1_yoksa_anlasilir_hata(tmp_path):
    with pytest.raises(SystemExit, match="data.export"):
        run.main(["--paket", str(tmp_path / "yok")])


def test_sentetik_tanima():
    d = xr.DataArray([1.0])
    assert not run.sentetik_mi(d)
    for attrs in ({"source_product": "SENTETIK"}, {"yer_tutucu": "evet"},
                  {"file": "kar_ortusu__SENTETIK.nc"}, {"urun_surumu": "YER TUTUCU"}):
        d.attrs = attrs
        assert run.sentetik_mi(d)
