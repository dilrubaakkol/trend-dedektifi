"""Büyüklük testleri (physics/buyukluk.py): sentetik veriyle bilinen büyüklükler, etiket ve güven kuralı, dil,
mevcut dosyalara dokunmama. Bütün değerler yer tutucu (sentetik)."""

import re

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from physics import buyukluk as B
from physics.ornek_l4 import LAT, LON

YASAK = re.compile(r"insan etkisi var|yüzünden|nedeniyle|sebebi|kanıtla|\bneden\b", re.I)
YIL = np.arange(2001, 2026, dtype=float)


# ------------------------------------------------------------------ etiket ve güven kuralı
def test_etiket_kurali_oncelik_ve_sinirlar():
    assert B.etiketle(6.0, 7.0, 5.9, 7.3)[0] == B.TUTARLI
    assert B.etiketle(7.2, 9.0, 5.9, 7.3)[0] == B.TUTARLI              # kısmi kesişme yeter
    assert B.etiketle(2.0, 4.0, 5.9, 7.3)[0] == B.KUCUK
    assert B.etiketle(8.0, 9.0, 5.9, 7.3)[0] == B.BUYUK
    assert B.etiketle(0.0, 4.3, 5.9, 7.3)[0] == B.BELIRSIZ             # 4,3 > 3 × 1,4: genişlik önce gelir
    assert B.etiketle(3.1, 7.2, 5.9, 7.3)[0] == B.TUTARLI              # 4,1 < 3 × 1,4: belirsiz değil
    assert B.etiketle(np.nan, 1.0, 5.9, 7.3)[0] == B.HESAPLANAMADI
    assert set(B.ETIKETLER) == {B.TUTARLI, B.KUCUK, B.BUYUK, B.BELIRSIZ, B.HESAPLANAMADI}


def test_guven_kurali():
    g = B.GECTI
    assert B.guven_seviyesi(B.BELIRSIZ, {"a": g, "b": g, "c": g}, [])[0] == B.YOK
    assert B.guven_seviyesi(B.TUTARLI, {"a": g, "b": B.KALDI, "c": g}, [])[0] == B.DUSUK
    assert B.guven_seviyesi(B.TUTARLI, {"a": g, "b": B.UYG, "c": g}, [])[0] == B.DUSUK   # uygulanamaz ≠ geçti
    assert B.guven_seviyesi(B.KUCUK, {"a": g, "b": g, "c": g}, [])[0] == B.YUKSEK
    assert B.guven_seviyesi(B.KUCUK, {"a": g, "b": g, "c": g}, ["x Kademe 2"])[0] == B.ORTA
    assert B.guven_seviyesi(B.BUYUK, {"a": B.UYG, "b": g, "c": g}, [])[0] == B.ORTA
    assert B.guven_seviyesi(B.BUYUK, {"a": g, "b": g, "c": B.KALDI}, [])[0] == B.ORTA


def test_cc_bandi_denklemden():
    assert B.CC_BANT == (5.9, 7.3)
    assert B.cc_orani(0.0) == pytest.approx(7.27, abs=0.01)
    assert B.CC_BANT[0] <= B.CC_BEKLENEN <= B.CC_BANT[1]


# ------------------------------------------------------------------ bootstrap
def test_blok_bootstrap_indeksleri():
    rng = np.random.default_rng(0)
    idx = B.blok_bootstrap_indeksleri(25, 4, 999, rng)
    assert idx.shape == (999, 25) and idx.min() >= 0 and idx.max() <= 24
    fark = np.diff(idx[:, :4], axis=1) % 25                    # ilk blok ardışık (dairesel)
    assert (fark == 1).all()
    assert len({tuple(r) for r in idx[:50]}) > 40              # yerine koyarak, çeşitli
    a = B.bootstrap(B._sen_10yil, [YIL, YIL * 2.0], 3, "anahtar", tekrar=99)
    b = B.bootstrap(B._sen_10yil, [YIL, YIL * 2.0], 3, "anahtar", tekrar=99)
    assert a == b and a["gozlenen"] == pytest.approx(20.0)     # sabit tohum, aynı sonuç


def test_sen_ve_ekk_satir():
    t = np.vstack([YIL, YIL])
    y = np.vstack([3.0 * YIL, -YIL])
    np.testing.assert_allclose(B.sen_satir(t, y), [3.0, -1.0])
    np.testing.assert_allclose(B.ekk_satir(t, y), [3.0, -1.0])
    y2 = y.copy()
    y2[0, :5] = np.nan
    assert B.ekk_satir(t, y2)[0] == pytest.approx(3.0)


# ------------------------------------------------------------------ test 1: Clausius-Clapeyron
def _cc_veri(oran_yuzde, gurultu, seed=0):
    rng = np.random.default_rng(seed)
    T = 12 + 0.04 * (YIL - 2001) + rng.normal(0, 0.5, YIL.size)
    q = 0.007 * np.exp(oran_yuzde / 100 * T + rng.normal(0, gurultu, YIL.size))
    return T, q


def test_cc_yuzde7_tutarli_yuzde3_kucuk():
    T, q = _cc_veri(7.0, 0.002)
    s = B.cc_yillar_arasi(YIL, T, q, "t7")
    assert s["gozlenen"] == pytest.approx(7.0, abs=0.5)
    assert B.etiketle(s["ga_alt"], s["ga_ust"], *B.CC_BANT)[0] == B.TUTARLI
    T, q = _cc_veri(3.0, 0.002)
    s = B.cc_yillar_arasi(YIL, T, q, "t3")
    assert s["gozlenen"] == pytest.approx(3.0, abs=0.5)
    assert B.etiketle(s["ga_alt"], s["ga_ust"], *B.CC_BANT)[0] == B.KUCUK


def test_cc_trend_orani_bilinen():
    T = 12 + 0.05 * (YIL - 2001) + np.random.default_rng(1).normal(0, 0.05, YIL.size)
    q = 0.007 * np.exp(0.07 * T)
    s = B.cc_trend_orani(YIL, T, q, "tb")
    assert s["gozlenen"] == pytest.approx(7.0, abs=0.7)


def test_gurultulu_veri_belirsiz():
    T, q = _cc_veri(7.0, 0.05, seed=3)
    s = B.cc_yillar_arasi(YIL, T, q, "gurultu")
    assert B.etiketle(s["ga_alt"], s["ga_ust"], *B.CC_BANT)[0] == B.BELIRSIZ


def test_kisa_seri_hesaplanamadi():
    T, q = _cc_veri(7.0, 0.002)
    s = B.cc_yillar_arasi(YIL[:6], T[:6], q[:6], "k")
    assert np.isnan(s["gozlenen"]) and "< 10" in s["neden"]


# ------------------------------------------------------------------ test 2: su bütçesi
def _butce(eksik_mm_ay=0.0, seed=0, n=240):
    rng = np.random.default_rng(seed)
    ay = np.tile(np.arange(1, 13), n // 12)
    P = 50 + 30 * np.cos(2 * np.pi * (ay - 1) / 12) + rng.gamma(2, 5, n)
    ET = 30 + 20 * np.sin(2 * np.pi * (ay - 4) / 12) + rng.normal(0, 2, n)
    R = 8 + rng.gamma(2, 1, n)
    akı = P - ET - R - eksik_mm_ay                     # gerçek depolama değişimi (ölçülmeyen kayıp dahil)
    S = np.cumsum(akı) - akı / 2                       # ay ortası depolama: merkezî fark akıyı verir
    return ay, P, ET, R, S


def test_kapanan_butce_fark_sifir():
    ay, P, ET, R, S = _butce()
    r = B.depolama_degisimi(S) - (P - ET - R)
    s = B.butce_ortalama(r, "kapanan")
    assert abs(s["gozlenen"]) < 15 and s["ga_alt"] < 0 < s["ga_ust"]
    yari = B.BUTCE_ORAN * np.mean(P) * 12
    assert B.etiketle(s["ga_alt"], s["ga_ust"], -yari, yari)[0] == B.TUTARLI
    t = 2001 + np.arange(ay.size) / 12
    st = B.butce_trend(t, ay, r, "kapanan_trend")
    assert abs(st["gozlenen"]) < 10


def test_olculmeyen_kayip_beklenenden_kucuk():
    ay, P, ET, R, S = _butce(eksik_mm_ay=15.0)          # 180 mm/yıl ölçülmeyen kayıp
    r = B.depolama_degisimi(S) - (P - ET - R)
    s = B.butce_ortalama(r, "kayip")
    assert s["gozlenen"] == pytest.approx(-180, abs=15)
    yari = B.BUTCE_ORAN * np.mean(P) * 12
    assert B.etiketle(s["ga_alt"], s["ga_ust"], -yari, yari)[0] == B.KUCUK


def test_depolama_degisimi_bosluk():
    s = np.array([0.0, 1, 2, np.nan, 4, 5])
    d = B.depolama_degisimi(s)
    assert np.isnan(d[[0, 2, 4, 5]]).all() and d[1] == 1.0


# ------------------------------------------------------------------ test 3: kar çizgisi
def _kar_alani(kayma_m_10yil, seed=0):
    """Rakım batıdan doğuya 0 → 3900 m; kar örtüsü kar çizgisinin üstünde %100'e yaklaşır."""
    rng = np.random.default_rng(seed)
    lat = np.round(38.125 + 0.25 * np.arange(6), 3)
    lon = np.round(30.125 + 0.25 * np.arange(40), 3)
    z = np.tile(np.linspace(0, 3900, lon.size), (lat.size, 1))
    cizgi = 1800 + kayma_m_10yil / 10 * (YIL - 2001)
    v = 100 / (1 + np.exp(-(z[None] - cizgi[:, None, None]) / 150)) + rng.normal(0, 2, (YIL.size, *z.shape))
    km = xr.DataArray(np.clip(v, 0, 100), coords={"yil": YIL.astype(int), "lat": lat, "lon": lon},
                      dims=("yil", "lat", "lon"))
    rk = xr.DataArray(z, coords={"lat": lat, "lon": lon}, dims=("lat", "lon"))
    return km, rk


def test_bilinen_kar_cizgisi_kaymasi():
    km, rk = _kar_alani(60.0)
    seri = B.kar_cizgisi_serisi(km, rk, np.ones(rk.shape, bool))
    assert seri["dilim"] >= B.KAR_MIN_DILIM
    s = B.egim_10yil(seri["yil"], seri["rakim_m"], "kar60")
    assert s["gozlenen"] == pytest.approx(60, abs=10)
    assert s["ga_alt"] < 60 < s["ga_ust"]


def test_beklenen_kar_kaymasi_bandi():
    nokta, alt, ust = B.beklenen_kar_kaymasi(0.39)
    assert nokta == pytest.approx(60.0) and alt == pytest.approx(52.0) and ust == pytest.approx(70.909, abs=1e-3)
    assert B.beklenen_kar_kaymasi(-0.39)[1] < B.beklenen_kar_kaymasi(-0.39)[2] < 0   # soğuma: bant sıralı


def test_dar_yukselti_araligi_dilim_sayisi():
    assert B.kar_dilim_sayisi(np.full(50, 1200.0)) == 1
    assert B.kar_dilim_sayisi(np.r_[np.full(3, 100.0), np.full(3, 500.0), np.full(2, 900.0)]) == 2


# ------------------------------------------------------------------ paket düzeyi (sentetik L1)
ZAMAN = pd.date_range("2001-01", "2025-12", freq="MS")


def _kup(v, ad, attrs=None):
    da = xr.DataArray(v.astype("float32"), coords={"time": ZAMAN, "lat": LAT, "lon": LON}, dims=("time", "lat", "lon"))
    ds = da.rename(ad).to_dataset()
    ds.attrs = {"urun_surumu": "v0.1", "veri_seti_doi": "(yayında doldurulacak)", "lisans": "CC BY 4.0",
                **(attrs or {})}
    return ds


@pytest.fixture(scope="module")
def paket(tmp_path_factory):
    kok = tmp_path_factory.mktemp("buyukluk") / "paket"
    kup = kok / "L1_kup"
    kup.mkdir(parents=True)
    rng = np.random.default_rng(5)
    nt, sh = len(ZAMAN), (LAT.size, LON.size)
    ay = ZAMAN.month.to_numpy()[:, None, None]
    yil = (ZAMAN.year.to_numpy() + (ZAMAN.month.to_numpy() - 1) / 12)[:, None, None]
    z = np.tile(np.linspace(0, 4000, LON.size), (LAT.size, 1))
    yillik = np.repeat(rng.normal(0, 0.4, 25), 12)[:, None, None]
    T = 12 + 10 * np.sin(2 * np.pi * (ay - 4) / 12) + 0.04 * (yil - 2001) + yillik - 0.0065 * z[None]
    T2 = T + rng.normal(0, 0.05, (nt, *sh))
    q = 0.007 * np.exp(0.07 * T) * np.exp(rng.normal(0, 0.002, (nt, *sh)))
    yaz = lambda ds, ad: ds.to_netcdf(kup / ad)  # noqa: E731
    yaz(_kup(T, "sicaklik_2m", {"kademe": np.int32(1)}), "sicaklik_2m__MERRA2.nc")
    yaz(_kup(T2, "sicaklik_2m", {"kademe": np.int32(1)}), "sicaklik_2m__GLDAS.nc")
    yaz(_kup(q, "ozgul_nem_2m", {"kademe": np.int32(2), "dogrulanmadi": "evet"}), "ozgul_nem_2m__MERRA2.nc")
    P = 50 + 30 * np.cos(2 * np.pi * (ay - 1) / 12) + rng.gamma(2, 5, (nt, *sh))
    ET = 30 + 20 * np.sin(2 * np.pi * (ay - 4) / 12) + np.zeros((nt, *sh))
    Rs, Rb = np.full((nt, *sh), 5.0), np.full((nt, *sh), 3.0)
    aki = P - ET - Rs - Rb
    S_mm = np.cumsum(aki, axis=0) - aki / 2
    S_mm -= S_mm.mean(0)
    for ad, v in (("yagis__GPM", P), ("yagis__MERRA2", P * 1.02)):
        yaz(_kup(v, "yagis", {"kademe": np.int32(1)}), f"{ad}.nc")
    for ad, v in (("buharlasma", ET), ("yuzey_akisi", Rs), ("taban_akisi", Rb)):
        yaz(_kup(v, ad, {"kademe": np.int32(2), "dogrulanmadi": "evet"}), f"{ad}__GLDAS.nc")
    g = _kup(S_mm / 10.0, "toplam_su_depolama", {"kademe": np.int32(1)}).isel(time=slice(15, None))
    g["toplam_su_depolama"][100:110] = np.nan                           # GRACE boşluğu
    yaz(g, "toplam_su_depolama__GRACE.nc")
    cizgi = 1800 + 6.0 * (yil - 2001)                                   # 60 m / 10 yıl
    kar = 100 / (1 + np.exp(-(z[None] - cizgi) / 150))
    kar[ZAMAN.get_loc("2016-02-01")] = np.nan                           # bilinen boş ay
    yaz(_kup(kar, "kar_ortusu", {"kademe": np.int32(1)}), "kar_ortusu__MOD10CM.nc")
    xr.DataArray(z, coords={"lat": LAT, "lon": LON}, dims=("lat", "lon")).rename("rakim").to_dataset().to_netcdf(
        kup / "rakim__SRTM.nc")
    # L2 uyarısı (yalnız okunur) ve mevcut L4 / karne dosyaları (değişmemeli)
    (kok / "L2_trend").mkdir()
    xr.Dataset(attrs={"trend_uyarisi": "GLDAS-2.1 zorlama verisi homojen olmayabilir"}).to_netcdf(
        kok / "L2_trend" / "yuzey_akisi__GLDAS__trend.nc")
    for d, ad in (("L4_iliski", "ciftler.csv"), ("karne", "karne_trend.csv"), ("L4_iliski/sapma", "x.csv")):
        (kok / d).mkdir(parents=True, exist_ok=True)
        (kok / d / ad).write_text("mevcut dosya", encoding="utf-8")
    return kok


@pytest.fixture(scope="module")
def sonuc(paket):
    once = {p: p.read_bytes() for p in paket.rglob("*") if p.is_file()}
    r = B.uret(paket, iller=False, tekrar=199)
    return r, once


def test_paket_dosyalari_ve_mevcutlara_dokunmama(paket, sonuc):
    r, once = sonuc
    for p, b in once.items():
        assert p.read_bytes() == b, p                                    # L1/L2/L4/karne değişmedi
    d = paket / "L4_iliski" / "buyukluk"
    adlar = sorted(p.name for p in d.iterdir())
    assert adlar == ["KURAL.txt", "butce__bolge.csv", "cc__bolge.csv", "kar_cizgisi__bolge.csv", "ozet.csv"]
    for t in B.TESTLER:
        df = pd.read_csv(d / f"{t}__bolge.csv", encoding="utf-8-sig")
        assert list(df.columns) == B.SUTUNLAR
        assert set(df["bolge_turu"]) == {"bolge", "turkiye"} and (df["bolge_kodu"] == "turkiye").sum() >= 1
        assert set(df["etiket"]) <= set(B.ETIKETLER) and set(df["guven"]) <= {"YÜKSEK", "ORTA", "DÜŞÜK", "YOK"}
        assert (df["kural_surumu"] == B.KURAL_SURUMU).all()


def test_paket_cc_tutarli_ve_kademe2_kritik(sonuc):
    df = sonuc[0]["cc"]
    tr = df[(df["bolge_kodu"] == "turkiye") & (df["yol"] == "a_yillar_arasi")].iloc[0]
    assert tr["etiket"] == B.TUTARLI and tr["gozlenen"] == pytest.approx(7.0, abs=0.5)
    assert tr["kritik"] == "evet" and tr["guven"] in ("ORTA", "DÜŞÜK")   # Kademe 2 nem → en çok ORTA
    assert tr["a_kaynak_uyumu"] == B.GECTI and "GLDAS" in tr["a_sayi"]


def test_paket_butce_kapanir_ve_trend_uyarisi_tasinir(sonuc):
    df = sonuc[0]["butce"]
    assert set(df["yol"]) == {"ortalama", "trend"} and "il" not in set(df["bolge_turu"])
    tr = df[(df["bolge_kodu"] == "turkiye") & (df["yol"] == "ortalama")].iloc[0]
    assert abs(tr["gozlenen"]) < 20 and tr["etiket"] == B.TUTARLI
    assert "trend_uyarisi" in tr["uyarilar"] and tr["kritik"] == "evet"
    assert "dS_dt_trend" in df[df["yol"] == "trend"].iloc[0]["ek"]


def test_paket_kar_cizgisi_bilinen_kayma(sonuc):
    df = sonuc[0]["kar_cizgisi"]
    tr = df[(df["bolge_kodu"] == "turkiye") & (df["yol"] == "ilkbahar")].iloc[0]
    assert tr["gozlenen"] == pytest.approx(60, abs=12)
    assert tr["beklenen"] == pytest.approx(0.4 * 1000 / 6.5, rel=0.25)   # sentetik ısınma 0,4 °C/10 yıl
    kis = df[(df["bolge_kodu"] == "turkiye") & (df["yol"] == "kis")].iloc[0]
    assert "2016" in kis["ek"] and "2016-02" in kis["ek"]                # bilinen boş ay → düşen kış
    assert (df["etiket"] == B.HESAPLANAMADI).any() or df["n"].min() >= B.KAR_MIN_YIL


def test_dil_kurali(paket, sonuc):
    d = paket / "L4_iliski" / "buyukluk"
    metin = " ".join(p.read_text(encoding="utf-8-sig") for p in d.iterdir())
    metin += B.KURAL_METNI + B.CC_KARA_YORUMU + B.BUTCE_YORUMU + B.KAR_YORUMU + B.BUTCE_IL_NOTU
    assert not YASAK.search(metin), YASAK.search(metin)
    assert "nedensellik göstermez" in B.KURAL_METNI
