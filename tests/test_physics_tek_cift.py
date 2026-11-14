"""physics.iliski (tek çift komutu) testleri — sentetik paket, internetsiz, yalnız tmp klasörüne yazar."""

import json

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from physics import tek_cift as T
from physics.ciftler import CIFT, Cift, cift_serileri
from physics.iliski import ALFA
from physics.ornek_l4 import LAT, LON, ZAMAN, ornek_veri
from physics.tablo import EK_SUTUNLAR, SUTUNLAR, bolge_maskeleri, cift_tablosu

GEREKEN = ["sicaklik_2m__MERRA2", "kar_ortusu__MOD10CM", "yagis__GPM", "yagis__GLDAS",
           "ndvi__MOD13C2", "toplam_su_depolama__GRACE"]


def _gercek_gibi(da: xr.DataArray, ad: str) -> xr.DataArray:
    d = da.copy()
    d.attrs = {"urun_surumu": "v0.1", "veri_seti_doi": "(yayında doldurulacak)", "lisans": "CC BY 4.0",
               "doi": "10.5067/TEST", "kademe": 1}
    return d.rename(ad.split("__")[0])


@pytest.fixture(scope="module")
def paket(tmp_path_factory):
    """Sentetik L1 paketi + ortak trendli iki deneme değişkeni (sahte korelasyon için)."""
    kok = tmp_path_factory.mktemp("td") / "paket"
    kup = kok / "L1_kup"
    kup.mkdir(parents=True)
    v = ornek_veri(seed=1)
    v["yagis__GLDAS"] = v["yagis__GPM"] * 1.1
    for ad in GEREKEN:
        _gercek_gibi(v[ad], ad).to_dataset().to_netcdf(kup / f"{ad}.nc")
    # ortak trend + bağımsız gürültü: ham r yüksek, trendi çıkarılmış r ≈ 0
    rng = np.random.default_rng(3)
    kara = bolge_maskeleri(LAT, LON)["turkiye"]
    yil = (ZAMAN.year + (ZAMAN.month - 1) / 12).to_numpy()
    for ad, olcek in (("deneme_a__TEST", 1.0), ("deneme_b__TEST", 2.0)):
        seri = olcek * (0.4 * (yil - 2001) + 0.5 * rng.standard_normal(len(ZAMAN)))
        kupd = np.where(kara[None], seri[:, None, None] + 0.01 * rng.standard_normal((len(ZAMAN), *kara.shape)), np.nan)
        da = xr.DataArray(kupd, coords={"time": ZAMAN, "lat": LAT, "lon": LON}, dims=("time", "lat", "lon"),
                          attrs={"kademe": 2, "dogrulanmadi": "evet", "bilinen_sorunlar": "deneme sorunu"})
        da.rename(ad.split("__")[0]).to_dataset().to_netcdf(kup / f"{ad}.nc")
    return kok


def _l1(paket, ad):
    d, u = ad.split("__")
    return T._l1_ac(paket, d, u)


# ------------------------------------------------------------------ seçim
def test_bolge_coz():
    assert T.bolge_coz("Elazığ") == ("elazig", ["il:elazig"], False)
    assert T.bolge_coz("23") == T.bolge_coz("elazig") == T.bolge_coz("ELAZIĞ")
    assert T.bolge_coz("Doğu Anadolu") == ("dogu_anadolu", ["bolge:dogu_anadolu"], False)
    assert T.bolge_coz("dogu anadolu bölgesi")[1] == ["bolge:dogu_anadolu"]
    assert T.bolge_coz("Türkiye") == ("turkiye", ["turkiye"], False)
    ad, k, fdr = T.bolge_coz("tum_iller")
    assert len(k) == 81 and fdr and all(x.startswith("il:") for x in k)
    assert len(T.bolge_coz("tum_bolgeler")[1]) == 8
    with pytest.raises(T.SecimHatasi, match=r"(?s)erzurum.*iller \(81\)"):
        T.bolge_coz("Erzrum")


def test_urun_sec():
    sec = {"yagis": ["GLDAS", "GPM", "MERRA2"], "no2": ["OMI"]}
    onc = {"yagis": ["GPM", "GLDAS", "MERRA2"]}
    assert T.urun_sec("yagis", None, sec, onc)[0] == "GPM"
    assert T.urun_sec("yagis", "MERRA2", sec, onc) == ("MERRA2", "kullanıcı seçti")
    assert T.urun_sec("no2", None, sec, onc) == ("OMI", "tek ürün")
    assert T.urun_sec("yagis", None, sec, {})[0] == "GLDAS"   # öncelik yoksa Kademe 1, alfabetik
    with pytest.raises(T.SecimHatasi, match=r"(?s)Bunu mu demek istediniz: yagis.*Mevcut değişkenler"):
        T.urun_sec("yagiss", None, sec, onc)
    with pytest.raises(T.SecimHatasi, match="Mevcut ürünler: GLDAS, GPM, MERRA2"):
        T.urun_sec("yagis", "TRMM", sec, onc)


def test_l1_secenekleri_sabit_alani_atlar(paket, tmp_path):
    xr.DataArray(np.ones((2, 2)), dims=("lat", "lon")).rename("rakim").to_dataset().to_netcdf(
        tmp_path / "rakim__SRTM.nc")
    (tmp_path / "L1_kup").mkdir()
    (tmp_path / "rakim__SRTM.nc").rename(tmp_path / "L1_kup" / "rakim__SRTM.nc")
    xr.DataArray(np.ones((2, 2)), dims=("lat", "lon")).rename("tarim_orani").to_dataset().to_netcdf(
        tmp_path / "L1_kup" / "tarim_orani__MCD12C1.nc")
    assert T.l1_secenekleri(tmp_path) == {}                      # zamansız katmanlar listelenmez
    assert T.l1_secenekleri(paket)["yagis"] == ["GLDAS", "GPM"]


def test_gecici_cift_yaml_ayarlarini_devralir():
    c, es = T.gecici_cift("sicaklik_2m", "MERRA2", "kar_ortusu", "MOD10CM", "kis", 0, -1, (CIFT[1],))
    assert es is CIFT[1] and c.no == 1 and c.kar_maskesi_esik == 10 and c.seri == "kis_DJF"
    c, es = T.gecici_cift("toprak_nemi", "GLDAS", "ndvi", "MOD13C2", "aylik", 2, 1, (CIFT[3],))
    assert es is CIFT[3] and c.gecikmeler == (2,) and c.aylar == (4, 5, 6, 7, 8, 9)
    c, es = T.gecici_cift("yagis", "GPM", "ndvi", "MOD13C2", "ilkbahar", 1, 1, (CIFT[3],))
    assert es is None and c.no == 0 and c.seri == "ilkbahar_MAM" and c.harita
    assert not T.gecici_cift("yagis", "GPM", "toplam_su_depolama", "GRACE", "yillik", 0, 0, ())[0].harita


def test_mevsim_gecikmesi_x_onceki_aylar():
    """İlkbahar + gecikme 1: x'in Şub–Nis ortalaması, y'nin Mar–May ortalamasıyla eşlenir."""
    rng = np.random.default_rng(0)
    a = xr.DataArray(rng.standard_normal(len(ZAMAN)), coords={"time": ZAMAN}, dims="time")
    b = a.shift(time=1)                                      # b(t) = a(t − 1)
    c = Cift(no=0, d1="toprak_nemi", u1="X", d2="ndvi", u2="Y", seri="ilkbahar_MAM", beklenen=1,
             kademe=1, gecikmeler=(1,), mevsim="ilkbahar")
    s = cift_serileri(c, a, b)[0]
    ok = np.isfinite(s["x"].values) & np.isfinite(s["y"].values)
    np.testing.assert_allclose(s["x"].values[ok], s["y"].values[ok], atol=1e-12)


# ------------------------------------------------------------------ hesap
def test_cift1_ile_ayni_sonuc(paket):
    """Komut, L4'teki çift 1 ile aynı sayıları verir (bölge + Türkiye ve 81 il + FDR)."""
    a, b = _l1(paket, "sicaklik_2m__MERRA2"), _l1(paket, "kar_ortusu__MOD10CM")
    ref = cift_tablosu(CIFT[1], a, b)
    kol = ["bolge_kodu", "donem", "n", "r", "etkin_n", "p", "p_fdr", "anlamli", "etiket", "not"]
    for bolge, secici in (("tum_bolgeler", ref["bolge_turu"] != "il"), ("tum_iller", ref["bolge_turu"] == "il")):
        s = T.hesapla("sicaklik_2m", "kar_ortusu", bolge, "kis", beklenen="-", paket=paket)
        assert s["yaml_cifti"] == 1
        pd.testing.assert_frame_equal(s["tablo"][kol].reset_index(drop=True),
                                      ref.loc[secici, kol].reset_index(drop=True))
    assert s["secim"]["fdr"] and s["tablo"]["p_fdr"].notna().any()


def test_tek_il_fdrsiz(paket):
    s = T.hesapla("yagis", "ndvi", "Konya", "ilkbahar", gecikme=1, beklenen="+", paket=paket)
    d = s["tablo"]
    assert len(d) == 1 and d["bolge_adi"].iloc[0] == "Konya" and d["p_fdr"].isna().all()
    assert d["anlamli"].iloc[0] == int(d["p"].iloc[0] < ALFA)
    assert s["secim"]["urun_x"] == "GPM" and "Kademe 1" in s["secim"]["urun_x_gerekce"]
    assert list(d.columns) == SUTUNLAR + EK_SUTUNLAR + ["yon"]


def test_sahte_korelasyon_uyarisi(paket):
    """İki seri de trendli: ham r yüksek, trendi çıkarılmış r küçük → 'şişiriyor' uyarısı."""
    s = T.hesapla("deneme_a", "deneme_b", "turkiye", "yillik", paket=paket)
    r = s["tablo"].iloc[0]
    assert r["r_ham"] > 0.8 and abs(r["r"]) < 0.5
    assert r["egim_x_10yil"] > 0 and r["egim_y_10yil"] > 0
    assert any("şişiriyor" in u for u in s["uyarilar"])
    assert any("bilinen_sorunlar: deneme sorunu" in u for u in s["uyarilar"])
    assert any("Kademe 2" in u for u in s["uyarilar"])
    assert r["etiket"] in ("", "anlamsiz") and s["secim"]["beklenen"] == ""   # beklenen verilmedi


def test_ortak_trend_gizliyor():
    df = pd.DataFrame({"bolge_adi": ["A", "B"], "r_ham": [0.1, 0.5], "r": [0.6, 0.45]})
    u = T.ortak_trend_uyarilari(df)
    assert len(u) == 1 and "gizliyor" in u[0] and "A (ham +0.10 → trendsiz +0.60)" in u[0]


def test_hatalar(paket):
    with pytest.raises(T.SecimHatasi, match="il ölçeğinde"):
        T.hesapla("yagis", "toplam_su_depolama", "Konya", "yillik", paket=paket)
    with pytest.raises(T.SecimHatasi, match="aynı dosya"):
        T.hesapla("yagis", "yagis", "turkiye", "yillik", paket=paket)
    with pytest.raises(T.SecimHatasi, match="mevsim"):
        T.hesapla("yagis", "ndvi", "turkiye", "bahar", paket=paket)
    with pytest.raises(ValueError, match="beklenen"):
        T.hesapla("yagis", "ndvi", "turkiye", "yillik", beklenen="?", paket=paket)


def test_grace_bolge_olceginde(paket):
    s = T.hesapla("yagis", "toplam_su_depolama", "tum_bolgeler", "yillik", beklenen="+", paket=paket)
    assert s["yaml_cifti"] == 4 and len(s["tablo"]) == 8


def test_kaydet_ve_json(paket, capsys):
    T.main(["--x", "yagis", "--y", "ndvi", "--bolge", "Konya", "--mevsim", "ilkbahar", "--gecikme", "1",
            "--beklenen", "+", "--paket", str(paket), "--kaydet", "--json"])
    d = json.loads(capsys.readouterr().out)
    assert set(d) == {"secim", "yaml_cifti", "uyarilar", "satirlar", "sure_sn"}
    assert d["satirlar"][0]["bolge_adi"] == "Konya" and d["secim"]["gecikme_ay"] == 1
    yol = paket / "L4_iliski" / "ozel" / "yagis__ndvi__konya__ilkbahar__gecikme1.csv"
    df = pd.read_csv(yol, encoding="utf-8-sig", dtype={"bolge_kodu": str})
    assert list(df.columns) == SUTUNLAR + EK_SUTUNLAR + ["yon", "uyari"] and df["bolge_kodu"].iloc[0] == "42"


def test_ekran_ciktisi_ve_hata_kodu(paket, capsys):
    T.main(["--x", "sicaklik_2m", "--y", "kar_ortusu", "--bolge", "Erzurum", "--mevsim", "kis",
            "--beklenen", "−", "--paket", str(paket)])
    out = capsys.readouterr().out
    assert "İLİŞKİ: sicaklik_2m (MERRA2) ~ kar_ortusu (MOD10CM) · Erzurum · kis" in out
    assert "ham r" in out and "r (trendsiz)" in out and "nedensellik göstermez" in out
    assert "çift 1 ayarları" in out and " neden " not in out
    with pytest.raises(SystemExit) as e:
        T.main(["--x", "sicaklk_2m", "--y", "kar_ortusu", "--bolge", "Erzurum", "--mevsim", "kis",
                "--paket", str(paket)])
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "Bunu mu demek istediniz: sicaklik_2m" in err and "Mevcut değişkenler" in err


def test_python_m_physics_iliski_girisi():
    """``python -m physics.iliski`` istatistik modülündeki main üzerinden komuta ulaşır."""
    from physics import iliski
    assert callable(iliski.main)
