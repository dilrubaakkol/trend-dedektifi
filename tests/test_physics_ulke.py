"""Başka ülke paketi (Yunanistan) ile L4: tek "ulke" satırı + haritalar (sentetik, yalnız tmp klasörü)."""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from physics import run
from physics import tablo as T

LAT = 34.875 + 0.25 * np.arange(29)      # Yunanistan yayın kutusu (data/ulkeler.yaml), 29 × 35
LON = 19.625 + 0.25 * np.arange(35)
ZAMAN = pd.date_range("2001-01", "2025-12", freq="MS")
GIRDILER = ["sicaklik_2m__MERRA2", "kar_ortusu__MOD10CM", "yagis__GPM", "toprak_nemi__GLDAS", "ndvi__MOD13C2",
            "toplam_su_depolama__GRACE", "buharlasma__GLDAS", "yuzey_sicakligi_gunduz__MOD11C3"]


@pytest.fixture(autouse=True)
def _turkiye_geri():
    yield
    T.ulke_ayarla(None)                  # modül düzeyi ayar: diğer testleri etkilemesin


def _paket(tmp_path, ulke="yunanistan"):
    from data.regions import ulke_maskesi
    kara = ulke_maskesi(LAT, LON, "yunanistan")
    rng = np.random.default_rng(0)
    sekil = (len(ZAMAN), len(LAT), len(LON))
    ay = ZAMAN.month.to_numpy()
    dongu = np.sin(2 * np.pi * (ay - 4) / 12)[:, None, None]
    ortak = rng.standard_normal(sekil)
    deger = {
        "sicaklik_2m__MERRA2": 12 + 10 * dongu + 2 * ortak,
        "kar_ortusu__MOD10CM": np.clip(30 - 30 * dongu - 8 * ortak, 0, 100),
        "yagis__GPM": np.clip(50 - 30 * dongu + 10 * ortak, 0, None),
        "toprak_nemi__GLDAS": 25 - 5 * dongu + 2 * ortak + rng.standard_normal(sekil),
        "ndvi__MOD13C2": 0.5 + 0.1 * dongu + 0.02 * ortak,
        "toplam_su_depolama__GRACE": 3 * ortak + rng.standard_normal(sekil),
        "buharlasma__GLDAS": np.clip(50 + 30 * dongu + 5 * ortak, 0, None),
        "yuzey_sicakligi_gunduz__MOD11C3": 18 + 14 * dongu + 2.5 * ortak + rng.standard_normal(sekil),
    }
    kup = tmp_path / "paket" / "L1_kup"
    kup.mkdir(parents=True)
    for ad in GIRDILER:
        v = np.where(kara[None], deger[ad], np.nan)
        attrs = {"urun_surumu": "v0.1", "veri_seti_doi": "(yayında doldurulacak)", "lisans": "CC BY 4.0",
                 "doi": "10.5067/TEST", "kademe": 1, "source_product": "TEST", "ulke": ulke}
        xr.DataArray(v, coords={"time": ZAMAN, "lat": LAT, "lon": LON}, dims=("time", "lat", "lon"),
                     attrs=attrs).rename(ad.split("__")[0]).to_dataset().to_netcdf(kup / f"{ad}.nc")
    return tmp_path / "paket", int(kara.sum())


def test_yunanistan_paketi_tek_ulke_satiri(tmp_path):
    paket, kara = _paket(tmp_path)
    run.main(["--paket", str(paket)])
    df = pd.read_csv(paket / "L4_iliski" / "ciftler.csv", encoding="utf-8-sig", dtype={"bolge_kodu": str})
    assert set(df["bolge_turu"]) == {"ulke"} and set(df["bolge_adi"]) == {"Yunanistan"}
    assert sorted(df["cift_no"].unique()) == [1, 2, 3, 4, 5, 6] and len(df) == 7     # çift 3: iki gecikme
    assert df["p_fdr"].isna().all()                                                  # il yok → FDR yok
    assert df.loc[df["cift_no"] == 6, "hucre_sayisi"].item() == kara
    assert df.loc[df["cift_no"] == 6, "etiket"].item() == "beklenen_yonde"
    assert (paket / "L4_iliski" / "iliski__sicaklik_2m__yuzey_sicakligi_gunduz.nc").exists()


def test_ulke_tutarsizsa_durur(tmp_path):
    paket, _ = _paket(tmp_path)
    with pytest.raises(SystemExit, match="tutarsız"):
        run.main(["--paket", str(paket), "--ulke", "turkiye"])


def test_turkiye_varsayilani_degismedi():
    T.ulke_ayarla(None)
    b = T.bolge_listesi()
    assert len(b) == 89 and b[-1]["anahtar"] == "turkiye"
    T.ulke_ayarla("yunanistan")
    assert T.bolge_listesi() == [{"bolge_turu": "ulke", "bolge_kodu": "yunanistan", "bolge_adi": "Yunanistan",
                                  "anahtar": "ulke:yunanistan"}]


def test_ulke_karsilastirma(tmp_path):
    from physics.ulke_karsilastirma import karsilastir
    ortak = {"cift": "x~y", "seri": "kis_DJF", "gecikme_ay": 0, "beklenen_yon": "-", "hucre_sayisi": 10,
             "donem": "2002-2025", "n": 24, "etkin_n": 20.0, "p": 0.001}
    for ad, tur, r, et in (("tr", "turkiye", -0.9, "beklenen_yonde"), ("gr", "ulke", -0.7, "beklenen_yonde")):
        d = tmp_path / ad / "L4_iliski"
        d.mkdir(parents=True)
        pd.DataFrame([{"cift_no": 1, **ortak, "bolge_turu": tur, "bolge_kodu": tur,
                       "bolge_adi": "Türkiye" if ad == "tr" else "Yunanistan", "r": r, "etiket": et},
                      {"cift_no": 1, **ortak, "bolge_turu": "bolge", "bolge_kodu": "x", "bolge_adi": "X",
                       "r": 0.1, "etiket": "anlamsiz"}]).to_csv(d / "ciftler.csv", index=False, encoding="utf-8-sig")
    df = karsilastir(tmp_path / "tr", tmp_path / "gr")
    assert len(df) == 1 and df["ayni_etiket"].all()
    assert df["r_Türkiye"].item() == -0.9 and df["r_Yunanistan"].item() == -0.7
