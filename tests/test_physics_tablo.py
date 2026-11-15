"""physics/tablo.py testleri (Faz 4; sentetik, internetsiz).

Yayın ızgarası (28 × 78, 0,25°) ve Kişi 1'in gerçek il/bölge sınırları kullanılır; veri sentetiktir.
"""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from physics.ciftler import CIFT
from physics.tablo import (NOT_TERS, SUTUNLAR, bolge_maskeleri, cift_tablosu, ciftler_tablosu,
                           csv_yaz)

ZAMAN = pd.date_range("2001-01", "2025-12", freq="MS")
LAT = 35.625 + 0.25 * np.arange(28)
LON = 25.625 + 0.25 * np.arange(78)
AY = ZAMAN.month.to_numpy()


@pytest.fixture(scope="module")
def maske():
    return bolge_maskeleri(LAT, LON)


def _kup(v, kara, **attrs):
    v = np.where(kara[None], v, np.nan)
    return xr.DataArray(v, coords={"time": ZAMAN, "lat": LAT, "lon": LON},
                        dims=("time", "lat", "lon"), attrs=attrs)


def _cift(maske, seed=0, ters_bolge="il:konya", guc=0.8):
    """Her yerde pozitif ilişki; ``ters_bolge`` içinde negatif. Ortak mevsim döngüsü var."""
    rng = np.random.default_rng(seed)
    sekil = (len(ZAMAN), len(LAT), len(LON))
    a, g = rng.standard_normal(sekil), rng.standard_normal(sekil)
    isaret = np.where(maske[ters_bolge], -1.0, 1.0)[None] if ters_bolge else 1.0
    b = isaret * guc * a + np.sqrt(1 - guc ** 2) * g
    dongu = 12 * np.sin(2 * np.pi * (AY - 4) / 12)[:, None, None]
    kara = maske["turkiye"]
    return (_kup(10 + dongu + a, kara, urun_surumu="v0.1", veri_seti_doi="(yayında doldurulacak)",
                 lisans="CC BY 4.0", kademe=1, doi="10.5067/MERRA2"),
            _kup(15 + 1.3 * dongu + b, kara, kademe=2, dogrulanmadi="evet", doi="10.5067/MOD11C3"))


def test_satir_sayisi_ve_sutunlar(maske):
    df = cift_tablosu(6, *_cift(maske))
    assert list(df.columns) == SUTUNLAR
    assert len(df) == 81 + 7 + 1
    assert (df["bolge_turu"].value_counts().to_dict() == {"il": 81, "bolge": 7, "turkiye": 1})
    assert df.loc[df["bolge_turu"] == "turkiye", "hucre_sayisi"].item() == 1303
    assert df.loc[df["bolge_kodu"] == "42", "bolge_adi"].item() == "Konya"
    assert df.loc[df["bolge_kodu"] == "01", "bolge_adi"].item() == "Adana"   # iki haneli plaka


def test_konya_ters_yonde_digerleri_beklenen(maske):
    df = cift_tablosu(6, *_cift(maske))
    konya = df[df["bolge_kodu"] == "42"].iloc[0]
    assert konya["etiket"] == "ters_yonde" and NOT_TERS in konya["not"]
    diger = df[(df["bolge_turu"] == "il") & (df["bolge_kodu"] != "42")]
    assert (diger["etiket"] == "beklenen_yonde").all()
    assert df.loc[df["bolge_turu"] == "turkiye", "etiket"].item() == "beklenen_yonde"


def test_fdr_yalniz_il_satirlarinda(maske):
    df = cift_tablosu(6, *_cift(maske, guc=0.15, ters_bolge=None))
    il, obur = df[df["bolge_turu"] == "il"], df[df["bolge_turu"] != "il"]
    assert il["p_fdr"].notna().all() and obur["p_fdr"].isna().all()
    assert (il["p_fdr"] >= il["p"] - 1e-12).all()
    assert ((il["anlamli"] == 1) == (il["p_fdr"] <= 0.10)).all()
    assert ((obur["anlamli"] == 1) == (obur["p"] < 0.05)).all()


def test_ortak_alanlar_ve_kademe(maske):
    df = cift_tablosu(6, *_cift(maske))
    s = df.iloc[0]
    assert (s["urun_surumu"], s["lisans"], s["kademe"], s["dogrulanmadi"]) == \
        ("v0.1", "CC BY 4.0", 2, "evet")
    assert (s["doi_1"], s["doi_2"]) == ("10.5067/MERRA2", "10.5067/MOD11C3")
    assert s["cift"] == CIFT[6].kod and s["beklenen_yon"] == "+"


def test_cift3_iki_gecikme_ayri_fdr(maske):
    a, b = _cift(maske, guc=0.0, ters_bolge=None)
    df = cift_tablosu(3, a, b)
    assert len(df) == 2 * 89 and set(df["gecikme_ay"]) == {1, 2}
    for g in (1, 2):
        assert df[(df["gecikme_ay"] == g) & (df["bolge_turu"] == "il")]["p_fdr"].notna().sum() == 81


def test_cift4_yalniz_bolge_ve_turkiye(maske):
    a, b = _cift(maske, ters_bolge=None)
    df = cift_tablosu(4, a.clip(min=0), b)
    assert set(df["bolge_turu"]) == {"bolge", "turkiye"} and len(df) == 8
    assert df["p_fdr"].isna().all()


def test_cift1_karsiz_bolgede_satir_bos(maske):
    """Kar yalnız doğuda (boylam > 38): Ege'de kapsamda hücre yok, Erzurum'da beklenen yönde."""
    rng = np.random.default_rng(5)
    sekil = (len(ZAMAN), len(LAT), len(LON))
    a = rng.standard_normal(sekil)
    T = -2 + 10 * np.sin(2 * np.pi * (AY - 4) / 12)[:, None, None] + 2 * a
    dogu = (LON > 38)[None, None, :]
    kar = np.where(dogu, np.clip(50 - 10 * a + rng.standard_normal(sekil), 0, 100), 1.0)
    df = cift_tablosu(1, _kup(T, maske["turkiye"]), _kup(kar, maske["turkiye"]))
    ege = df[df["bolge_kodu"] == "ege"].iloc[0]
    assert ege["hucre_sayisi"] == 0 and ege["etiket"] == "" and "kar" in ege["not"]
    erz = df[df["bolge_adi"] == "Erzurum"].iloc[0]
    assert erz["etiket"] == "beklenen_yonde" and erz["donem"] == "2002-2025" and erz["n"] == 24


def test_tum_ciftler_ve_eksik_girdi_atlanir(maske):
    a, b = _cift(maske, ters_bolge=None)
    veri = {"sicaklik_2m__MERRA2": a, "yuzey_sicakligi_gunduz__MOD11C3": b,
            "buharlasma__GLDAS": b.clip(min=0)}
    df = ciftler_tablosu(veri, iller=False)
    assert sorted(df["cift_no"].unique()) == [5, 6]
    with pytest.raises(ValueError):
        ciftler_tablosu({"ndvi__MOD13C2": a})


def test_csv_yazimi(maske, tmp_path):
    df = cift_tablosu(6, *_cift(maske))
    yol = csv_yaz(df, tmp_path / "L4_iliski" / "ciftler.csv")
    ham = yol.read_bytes()
    assert ham.startswith(b"\xef\xbb\xbf")                       # BOM (Excel için)
    geri = pd.read_csv(yol, encoding="utf-8-sig", dtype={"bolge_kodu": str})
    assert list(geri.columns) == SUTUNLAR and len(geri) == 89
    assert geri["p_fdr"].isna().sum() == 8                        # boş hücre
    assert "Konya" in geri["bolge_adi"].values and geri["anlamli"].dtype.kind == "i"
    assert ",0." in yol.read_text(encoding="utf-8-sig")            # ondalık ayıracı nokta
    assert ",il,01,Adana," in yol.read_text(encoding="utf-8-sig")  # plaka dosyada da "01"


def test_cift5_notu_etikete_gore(maske):
    """Çift 5: ters yönde çıkan il 'su sınırlı', beklenen yönde çıkan 'enerji sınırlı' notu alır."""
    NOT_CIFT5 = CIFT[5].etiket_notlari                    # ciftler.yaml'a taşındı (metin aynı)
    a, b = _cift(maske)                                   # Konya ters, diğerleri beklenen
    df = cift_tablosu(5, a, b.clip(min=0))
    konya = df[df["bolge_kodu"] == "42"].iloc[0]
    assert konya["etiket"] == "ters_yonde"
    assert NOT_CIFT5["ters_yonde"] in konya["not"] and NOT_TERS not in konya["not"]
    diger = df[(df["bolge_turu"] == "il") & (df["etiket"] == "beklenen_yonde")]
    assert len(diger) and diger["not"].str.contains("Enerji sınırlı").all()


def test_cift4_notu_8_satiri_aciklar(maske):
    a, b = _cift(maske, ters_bolge=None)
    df = cift_tablosu(4, a.clip(min=0), b)
    assert df["not"].str.contains("8 satır").all() and df["not"].str.contains("300 km").all()


def test_cift4_notu_baska_ulkede_ulke_metni():
    from physics import tablo as T
    try:
        T.ulke_ayarla("yunanistan")
        n = T._not(CIFT[4], "beklenen_yonde")
    finally:
        T.ulke_ayarla(None)
    assert "ülke satırı" in n and "7 bölge" not in n
    assert "7 bölge" in T._not(CIFT[4], "beklenen_yonde")
