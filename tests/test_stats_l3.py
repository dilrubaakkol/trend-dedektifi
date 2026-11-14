"""stats.l3: il/bölge alan ortalaması trendi, L2 hücre özeti, kaynak uyumu ve CSV şeması.

Sentetik küp (yer tutucu değerler) ve shapely kutularıyla tanımlı küçük test bölgeleri kullanılır.
"""

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from shapely.geometry import box

from stats import l2, l3

LAT = 38.125 + 0.25 * np.arange(4)          # Türkiye karası (İç Anadolu)
LON = 32.125 + 0.25 * np.arange(6)
ZAMAN = pd.date_range("2001-01", "2025-12", freq="MS")

# Test bölgeleri: a (batı 3 sütun, eğim 0,5), b (doğu 3 sütun, eğim 1,0), kucuk (1 hücre), tum (bölge)
BOLGELER = [
    {"duzey": "il", "anahtar": "a", "ad": "A", "kod": "01", "ust": "tum", "sorgu": box(32.0, 38.0, 32.75, 39.0)},
    {"duzey": "il", "anahtar": "b", "ad": "B", "kod": "02", "ust": "tum", "sorgu": box(32.75, 38.0, 33.5, 39.0)},
    {"duzey": "il", "anahtar": "kucuk", "ad": "Küçük", "kod": "03", "ust": "tum",
     "sorgu": box(32.0, 38.0, 32.25, 38.25)},
    {"duzey": "bolge", "anahtar": "tum", "ad": "Tüm", "kod": "tum", "ust": "", "sorgu": box(32.0, 38.0, 33.5, 39.0)},
]


def _kup(ad="sicaklik_2m", birim="°C", zaman=ZAMAN, seed=0, sigma=0.2, olcek=1.0):
    """Batı yarıda 0,5, doğu yarıda 1,0 birim/10 yıl trend + mevsim döngüsü + gürültü."""
    rng = np.random.default_rng(seed)
    t = np.asarray((zaman.year - 2001) + (zaman.month - 0.5) / 12)
    egim = np.where(LON < 32.75, 0.5, 1.0)[None, None, :] * olcek
    v = 10 + egim / 10 * t[:, None, None] + 2 * np.sin(2 * np.pi * np.asarray(zaman.month) / 12)[:, None, None]
    v = v + rng.normal(0, sigma, (len(zaman), 4, 6))
    da = xr.DataArray(v.astype("float32"), coords={"time": zaman, "lat": LAT, "lon": LON},
                      dims=("time", "lat", "lon"), name=ad)
    da.attrs = {"units": birim, "kademe": np.int32(1), "lisans": "CC BY 4.0", "doi": "10.0000/test",
                "urun_surumu": "v0.1", "veri_seti_doi": "(yayında doldurulacak)", "domain": "land"}
    return da


@pytest.fixture(scope="module")
def maskeler():
    return l3.bolge_maskeleri(LAT, LON, BOLGELER)


def test_maskeler_ve_alan_ortalamasi(maskeler):
    assert int(maskeler["a"][0].sum()) == 12 and int(maskeler["b"][0].sum()) == 12
    assert int(maskeler["kucuk"][0].sum()) == 1 and int(maskeler["tum"][0].sum()) == 24
    da = _kup()
    s = l3.bolge_serileri(da, maskeler)
    assert s.dims == ("time", "bolge")
    w = np.cos(np.deg2rad(LAT))[:, None] * np.ones((4, 6))
    m = maskeler["a"][0].values
    elle = (da.values[:, m] * w[m]).sum(axis=1) / w[m].sum()
    np.testing.assert_allclose(s.sel(bolge="a").values, elle, rtol=1e-5)


def test_bilinen_egim_ve_fdr(maskeler):
    df = l3.bolge_trendleri(_kup(), "sicaklik_2m", BOLGELER, maskeler)
    y = df[df["mevsim"] == "yillik"].set_index("bolge_anahtari")
    assert y.loc["a", "sen_egimi"] == pytest.approx(0.5, abs=0.08)
    assert y.loc["b", "sen_egimi"] == pytest.approx(1.0, abs=0.08)
    assert y.loc["tum", "sen_egimi"] == pytest.approx(0.75, abs=0.08)
    assert (y["anlamli"] == 1).all() and (y["ga_alt"] < y["sen_egimi"]).all()
    # FDR düzey içinde: tek bölgeli grupta q = p
    assert y.loc["tum", "p_fdr"] == pytest.approx(y.loc["tum", "p_mk"])
    il = df[(df["duzey"] == "il") & (df["mevsim"] == "kis")]
    assert (il["p_fdr"] >= il["p_mk"] - 1e-12).all()


def test_l3_dosya_sema(maskeler):
    da = _kup("yagis", "mm/ay", olcek=20)
    res = l2.l2_dosya(da, "yagis", maske=np.ones((4, 6), bool))
    res.attrs["trend_uyarisi"] = l2.trend_uyarisi("yagis", "GLDAS", res, np.ones((4, 6), bool))
    df = l3.l3_dosya(da, "yagis", "GLDAS", BOLGELER, maskeler, res)
    assert list(df.columns) == l3.L3_COLS and len(df) == 4 * 5
    assert list(df["mevsim"].unique()) == list(l2.MEVSIMLER)
    a = df[(df["bolge_anahtari"] == "a") & (df["mevsim"] == "yillik")].iloc[0]
    assert a["hucre_sayisi"] == 12 and a["anlamli_hucre_orani"] == pytest.approx(1.0)
    assert a["anlamli_artan_orani"] == pytest.approx(1.0) and a["anlamli_azalan_orani"] == 0
    assert a["birim"] == "mm/yıl" and a["egim_birimi"] == "mm/dönem / 10 yıl"
    assert a["medyan_hucre_egimi"] == pytest.approx(a["sen_egimi"], rel=0.1)
    assert "GLDAS-2.1" in a["trend_uyarisi"] and a["kademe"] == 1 and a["lisans"] == "CC BY 4.0"
    assert a["donem_baslangic"] == 2001 and a["donem_bitis"] == 2025
    assert df[df["mevsim"] == "kis"]["donem_baslangic"].eq(2002).all()
    k = df[df["bolge_anahtari"] == "kucuk"].iloc[0]
    assert k["not"] == "az hücre" and k["ust_bolge"] == "tum" and k["bolge_kodu"] == "03"
    assert set(df["duzey"]) == {"il", "bolge"}


def _paket(tmp_path):
    """L1 paketi: yagis GPM (2025-09'da biter) ve GLDAS + ICINDEKILER.csv."""
    kok = tmp_path / "outputs" / "trend-dedektifi-turkiye-v0.1" / "L1_kup"
    kok.mkdir(parents=True)
    rows = []
    for i, (urun, son) in enumerate([("GPM", "2025-09"), ("GLDAS", "2025-12")]):
        da = _kup("yagis", "mm/ay", zaman=pd.date_range("2001-01", son, freq="MS"), seed=i, olcek=-20)
        da.to_dataset().assign_attrs(da.attrs).to_netcdf(kok / f"yagis__{urun}.nc")
        rows.append({"dosya": f"yagis__{urun}.nc", "degisken": "yagis", "birim": "mm/ay", "kaynak": urun,
                     "kaynak_doi": "x", "donem": f"2001-01 … {son}", "kademe": 1})
    pd.DataFrame(rows).to_csv(kok / "ICINDEKILER.csv", index=False, encoding="utf-8-sig")
    return tmp_path / "outputs"


def test_uret_uctan_uca(tmp_path):
    kok = _paket(tmp_path)
    l2.uret("v0.1", kok=kok)
    out = l3.uret("v0.1", kok=kok, bolgeler=BOLGELER)
    adlar = sorted(p.name for p in out.glob("*.csv"))
    assert adlar == ["ICINDEKILER.csv", "yagis__GLDAS__bolge.csv", "yagis__GLDAS__il.csv", "yagis__GPM__bolge.csv",
                     "yagis__GPM__il.csv", "yagis__kaynak_uyumu__bolge.csv", "yagis__kaynak_uyumu__il.csv"]
    il = pd.read_csv(out / "yagis__GPM__il.csv", encoding="utf-8-sig", dtype={"bolge_kodu": str},
                     keep_default_na=False)
    assert list(il.columns) == l3.L3_COLS and set(il["duzey"]) == {"il"} and len(il) == 3 * 5
    assert il["bolge_kodu"].iloc[0] == "01"
    assert il[il["mevsim"] == "yillik"]["donem_bitis"].eq(2024).all()      # GPM 2025 yılı düşer
    assert pd.to_numeric(il["anlamli_hucre_orani"]).notna().all()         # L2 özeti bağlandı
    ku = pd.read_csv(out / "yagis__kaynak_uyumu__il.csv", encoding="utf-8-sig", dtype={"bolge_kodu": str})
    assert {"k", "m", "isaret_uyumu", "egim_GPM", "egim_GLDAS", "anlamli_GPM", "ortak_donem"} <= set(ku.columns)
    assert (ku["ortak_donem"] == "2001-01 … 2025-09").all() and (ku["k"] <= ku["m"]).all()
    assert (ku["isaret_uyumu"] >= ku["k"] / ku["m"]).all()
    y = ku[(ku["mevsim"] == "yillik") & (ku["bolge_anahtari"] == "b")].iloc[0]
    assert y["m"] == 2 and y["k"] == 2 and y["isaret_uyumu"] == 1
    ic = pd.read_csv(out / "ICINDEKILER.csv", encoding="utf-8-sig")
    assert len(ic) == 6 and set(ic["tur"]) == {"trend", "kaynak_uyumu"}
    assert (ic[ic["tur"] == "trend"]["l2_ozeti"] == "evet").all()
