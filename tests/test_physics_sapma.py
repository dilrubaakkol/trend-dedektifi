"""physics/sapma.py testleri — sentetik küpler, internetsiz, yalnız tmp klasörüne yazar.

(a) iklimle uyumlu hücreler: sapma skoru 0, sulama izi ≈ 0
(b) yağıştan bağımsız "yaz yeşilliği/serinliği" eklenen hücreler: yüksek sulama izi, ilk küme
(c) rejime bağlı çiftin kurak hücredeki tersi sapma sayılmaz, nemli hücredeki sayılır
(d) sapma üretimi L4 çıktılarını değiştirmez (L4 regresyonu test_physics_ciftler_yaml.py'de)
ve çıktılarda nedensellik dili yok.
"""

import re

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from physics import run, sapma as SP
from physics.ciftler import ciftleri_yukle
from physics.ornek_l4 import LAT, LON, ZAMAN, ornek_veri

YASAK = re.compile(r"insan etkisi var|yüzünden|nedeniyle|sebebi|kanıtla|\bneden\b(?! göstermez)", re.I)


# ------------------------------------------------------------------ (a) + (c) sapma skoru
def test_uyumlu_hucreler_skor_sifir():
    et = {1: np.array([0.0, 0.0, np.nan]), 2: np.array([0.0, np.nan, np.nan])}
    s = SP.sapma_skoru(et, set(), np.zeros(3, bool))
    np.testing.assert_array_equal(s["sapma_sayisi"][:2], [0, 0])
    np.testing.assert_array_equal(s["degerlendirilen"], [2, 1, 0])
    assert np.isnan(s["sapma_sayisi"][2]) and np.isnan(s["sapma_orani"][2])   # değerlendirilemeyen
    np.testing.assert_array_equal(s["sapma_orani"][:2], [0, 0])


def test_rejime_bagli_ters_kurakta_sapma_sayilmaz():
    # hücre 0: kurak, çift 5 ters → rejimle açıklanır; hücre 1: nemli, çift 5 ters → sapma
    # hücre 2: kurak, çift 3 (rejime bağlı değil) ters → sapma
    et = {3: np.array([0.0, 0.0, 1.0]), 5: np.array([1.0, 1.0, 0.0])}
    kurak = np.array([True, False, True])
    s = SP.sapma_skoru(et, {5}, kurak)
    np.testing.assert_array_equal(s["sapma_sayisi"], [0, 1, 1])
    np.testing.assert_array_equal(s["rejimle_aciklanan"], [1, 0, 0])
    np.testing.assert_array_equal(s["sapma_sayisi_ham"], [1, 1, 1])
    np.testing.assert_allclose(s["sapma_orani"], [0, 0.5, 0.5])
    assert [SP.bit_listesi(b) for b in s["ters_bit"]] == ["", "5", "3"]
    assert [SP.bit_listesi(b) for b in s["rejim_bit"]] == ["5", "", ""]
    bos = SP.sapma_skoru({}, {5}, kurak)                 # etiket yok: çökmez, NaN
    assert np.isnan(bos["sapma_orani"]).all()


def test_gecikmeleri_birlestir():
    t = SP.etiket_birlestir([np.array([1.0, 0.0, np.nan, np.nan]), np.array([0.0, 0.0, 1.0, np.nan])])
    np.testing.assert_array_equal(t[:3], [1, 0, 1])
    assert np.isnan(t[3])


def test_il_etiketleri(tmp_path):
    df = pd.DataFrame({"cift_no": [3, 3, 3, 3, 5, 5], "gecikme_ay": [1, 2, 1, 2, 0, 0],
                       "bolge_turu": ["il"] * 6, "bolge_kodu": ["01", "01", "02", "02", "01", "02"],
                       "etiket": ["ters_yonde", "beklenen_yonde", "ters_yonde", "anlamsiz", "anlamsiz", ""]})
    yol = tmp_path / "ciftler.csv"
    df.to_csv(yol, index=False, encoding="utf-8-sig")
    et = SP.il_etiketleri(yol, ciftleri_yukle())
    assert et.loc["01", 3] == 0 and et.loc["02", 3] == 1         # bir gecikmede beklenen yön → 0
    assert et.loc["01", 5] == 0 and np.isnan(et.loc["02", 5])


def test_rejim_ayari_yamlda():
    c5 = {c.no: c for c in ciftleri_yukle()}[5]
    assert c5.rejime_bagli and "su sınırlı" in c5.rejim_gerekcesi.lower()
    assert sum(c.rejime_bagli for c in ciftleri_yukle()) == 1


def test_rejime_bagli_gerekcesiz_hata(tmp_path):
    yol = tmp_path / "c.yaml"
    yol.write_text("""ciftler:
  - no: 9
    x: {degisken: yagis, urun: GPM}
    y: {degisken: ndvi, urun: MOD13C2}
    mevsim: yaz
    beklenen: "+"
    kademe: 1
    rejime_bagli: true
""", encoding="utf-8")
    with pytest.raises(ValueError, match="rejim_gerekcesi"):
        ciftleri_yukle(yol)


# ------------------------------------------------------------------ (b) sulama izi
def _iklim_kupu(seed=0, ny=14, nx=16, yil=6, ek_yesil=0.0, ek_serin=0.0, blok=None):
    """Aylık küpler: yaz NDVI ve (LST − T2M) yağış + rakımla belirlenir; ``blok`` hücrelerine yazın
    yağıştan bağımsız yeşillik / serinlik eklenir."""
    rng = np.random.default_rng(seed)
    t = pd.date_range("2001-01", periods=12 * yil, freq="MS")
    lat = 36 + 0.25 * np.arange(ny)
    lon = 30 + 0.25 * np.arange(nx)
    p_alan = rng.uniform(5, 80, (ny, nx))                      # hücreye özgü yağış düzeyi (mm/ay)
    rakim = rng.uniform(0, 2000, (ny, nx))
    ay = t.month.to_numpy()
    yaz = np.isin(ay, (6, 7, 8))[:, None, None]
    p = p_alan[None] * (1 + 0.5 * np.cos(2 * np.pi * (ay - 1) / 12))[:, None, None]
    p = np.clip(p + rng.normal(0, 2, p.shape), 0, None)
    ndvi = 0.1 + 0.08 * np.log1p(p_alan)[None] - 0.00005 * rakim[None] + rng.normal(0, 0.01, p.shape)
    fark = 12 - 1.5 * np.log1p(p_alan)[None] + 0.001 * rakim[None] + rng.normal(0, 0.3, p.shape)
    t2m = 20 + 8 * np.sin(2 * np.pi * (ay - 4) / 12)[:, None, None] + np.zeros((1, ny, nx))
    m = np.zeros((ny, nx), bool)
    if blok is not None:
        m[blok] = True
    ndvi = ndvi + ek_yesil * (yaz & m[None])
    lst = t2m + fark - ek_serin * (yaz & m[None])

    def da(v):
        return xr.DataArray(v, coords={"time": t, "lat": lat, "lon": lon}, dims=("time", "lat", "lon"))
    rak = xr.DataArray(rakim, coords={"lat": lat, "lon": lon}, dims=("lat", "lon"))
    return da(ndvi), da(lst), da(t2m), da(p), rak, m


def test_iklimle_uyumlu_sulama_izi_dusuk():
    ndvi, lst, t2m, p, rak, _ = _iklim_kupu()
    kara = np.ones(rak.shape, bool)
    s = SP.sulama_izi(ndvi, lst, t2m, p, rak, kara)
    assert np.nanmax(np.abs(s["sulama_izi"])) < 3.0 and abs(np.nanmean(s["sulama_izi"])) < 1e-6
    assert (s["n_bilesen"] == 2).all()


def test_yagistan_bagimsiz_yaz_yesilligi_yuksek_iz():
    blok = (slice(3, 6), slice(4, 7))                          # 3 × 3 hücre
    ndvi, lst, t2m, p, rak, m = _iklim_kupu(ek_yesil=0.15, ek_serin=4.0, blok=blok)
    kara = np.ones(rak.shape, bool)
    s = SP.sulama_izi(ndvi, lst, t2m, p, rak, kara)
    assert np.nanmin(s["sulama_izi"][m]) > 1.5                 # her blok hücresi yüksek
    assert np.nanmedian(s["sulama_izi"][~m]) < 0.3
    assert np.nanmin(s["z_yesil"][m]) > 1 and np.nanmin(s["z_serin"][m]) > 1
    il_m = {"il:a": np.ones(rak.shape, bool)}
    k = SP.kumeler(s["sulama_izi"], rak["lat"].values, rak["lon"].values, il_m, {"il:a": "A"})
    yy, xx = np.nonzero(m)
    assert k.iloc[0]["kume"] == 1 and k.iloc[0]["hucre_sayisi"] >= 6
    assert rak["lat"].values[yy].min() <= k.iloc[0]["tepe_lat"] <= rak["lat"].values[yy].max()
    assert rak["lon"].values[xx].min() <= k.iloc[0]["tepe_lon"] <= rak["lon"].values[xx].max()


def test_eksik_bilesen_atlanir():
    ndvi, lst, t2m, p, rak, _ = _iklim_kupu()
    s = SP.sulama_izi(ndvi, None, None, p, rak, np.ones(rak.shape, bool))
    assert (s["n_bilesen"] == 1).all() and np.isnan(s["z_serin"]).all()
    np.testing.assert_allclose(s["sulama_izi"], s["z_yesil"])


def test_kuraklik_gostergesi():
    t = pd.date_range("2001-01", periods=24, freq="MS")
    p = xr.DataArray(np.full((24, 1, 2), 50.0), coords={"time": t, "lat": [36.0], "lon": [30.0, 30.25]},
                     dims=("time", "lat", "lon"))
    e = p.copy(data=np.stack([np.full((24, 1), 45.0), np.full((24, 1), 20.0)], -1))
    np.testing.assert_allclose(SP.kuraklik_gostergesi(p, e).values, [[0.9, 0.4]])


# ------------------------------------------------------------------ (d) uçtan uca + dil
@pytest.fixture(scope="module")
def paket(tmp_path_factory):
    """Sentetik paket: L1 (gerçek gibi işaretli) + physics.run ile üretilmiş L4."""
    kok = tmp_path_factory.mktemp("sapma") / "paket"
    kup = kok / "L1_kup"
    kup.mkdir(parents=True)
    v = ornek_veri(seed=2)
    v["yagis__GLDAS"] = v["yagis__GPM"] * 1.05
    rakim = xr.DataArray(np.random.default_rng(0).uniform(0, 2500, (len(LAT), len(LON))),
                         coords={"lat": LAT, "lon": LON}, dims=("lat", "lon"))
    for ad, da in list(v.items()) + [("rakim__SRTM", rakim)]:
        d = da.copy()
        d.attrs = {"urun_surumu": "v0.1", "veri_seti_doi": "(yayında doldurulacak)", "lisans": "CC BY 4.0",
                   "doi": "10.5067/TEST", "kademe": 1}
        d.rename(ad.split("__")[0]).to_dataset().to_netcdf(kup / f"{ad}.nc")
    run.main(["--paket", str(kok)])
    return kok


def test_uctan_uca_l4_degismez_ve_dil(paket, capsys):
    l4 = paket / "L4_iliski"
    once = {p.name: p.read_bytes() for p in l4.iterdir() if p.is_file()}
    SP.main(["--paket", str(paket)])
    out = capsys.readouterr().out
    sonra = {p.name: p.read_bytes() for p in l4.iterdir() if p.is_file()}
    assert once == sonra                                       # L4 dosyaları aynen kaldı

    hedef = l4 / "sapma"
    assert sorted(p.name for p in hedef.iterdir()) == ["sapma_haritasi.nc", "sapma_iller.csv",
                                                       "sulama_izi_kumeleri.csv"]
    with xr.open_dataset(hedef / "sapma_haritasi.nc") as ds:
        for v in ("sapma_sayisi", "sapma_orani", "rejimle_aciklanan", "sulama_izi", "z_yesil", "z_serin",
                  "kuraklik_gostergesi", "ters_ciftler"):
            assert v in ds
        assert dict(ds.sizes) == {"lat": len(LAT), "lon": len(LON)}
        assert "neden göstermez" in ds.attrs["uyari"] and "Doğrulanmadı" in ds.attrs["uyari"]
        assert ds.attrs["lisans"] == "CC BY 4.0" and ds.attrs["yontem"]
        metin = " ".join(str(v) for v in ds.attrs.values())
    il = pd.read_csv(hedef / "sapma_iller.csv", encoding="utf-8-sig", dtype={"bolge_kodu": str})
    assert len(il) == 81 and il["bolge_kodu"].iloc[0] == "01"
    for k in ("il", "sapma_orani", "ters_ciftler", "sulama_izi", "en_yuksek_bilesen", "not"):
        assert k in il
    km = pd.read_csv(hedef / "sulama_izi_kumeleri.csv", encoding="utf-8-sig")
    assert 1 <= len(km) <= 10 and km["tepe_sulama_izi"].is_monotonic_decreasing and km["il"].notna().all()

    tum = " ".join([metin, out, il["not"].fillna("").str.cat(sep=" "), il["uyari"].iloc[0]])
    assert not YASAK.search(tum), YASAK.search(tum)
    assert "tutarlı olabilir" in SP.SULAMA_NOTU and "doğrulanmadı" in SP.SULAMA_NOTU


def test_kod_yer_adi_icermez():
    """Yöntem kör: sapma.py'de yer adı ya da sabit koordinat yok."""
    from pathlib import Path
    kod = Path(SP.__file__).read_text(encoding="utf-8").lower()
    for ad in ("konya", "harran", "şanlıurfa", "sanliurfa", "çukurova", "cukurova", "iğdır", "igdir",
               "menemen", "gediz", "adana", "gap"):
        assert not re.search(rf"\b{ad}\b", kod), ad


def test_l4_yoksa_anlasilir_hata(tmp_path):
    with pytest.raises(SystemExit, match="L4 çıktısı yok"):
        SP.main(["--paket", str(tmp_path)])
