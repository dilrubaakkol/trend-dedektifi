"""physics/ciftler.yaml testleri: çift tanımları, doğrulama, regresyon (sentetik) ve yeni çift ekleme.

Regresyon referansı (physics/ornekler/l4_regresyon*__YER_TUTUCU.*) çift tanımları koddan YAML'a
taşınmadan ÖNCEKİ kodla üretildi; taşıma davranışı değiştirmediyse çıktı birebir aynı kalmalı.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from physics import run
from physics.ciftler import CIFT, CIFTLER, ayar_oku, beklenen_kodu, ciftleri_yukle, seri_adi
from physics.harita import cift_haritasi
from physics.ornek_l4 import ornek_veri
from physics.tablo import ciftler_tablosu, csv_yaz

ORNEK = Path(__file__).resolve().parents[1] / "physics" / "ornekler"

# Taşımadan önce physics/ciftler.py'de elle yazılı duran 6 çift (beklenen değerler).
ESKI = {
    1: ("sicaklik_2m", "MERRA2", "kar_ortusu", "MOD10CM", "kis_DJF", -1, 1, (0,), True),
    2: ("yagis", "GPM", "toprak_nemi", "GLDAS", "mevsim_anomali", 1, 1, (0,), True),
    3: ("toprak_nemi", "GLDAS", "ndvi", "MOD13C2", "aylik_anomali_nis_eyl", 1, 1, (1, 2), True),
    4: ("yagis", "GPM", "toplam_su_depolama", "GRACE", "yillik", 1, 1, (0,), False),
    5: ("sicaklik_2m", "MERRA2", "buharlasma", "GLDAS", "yaz_JJA", 1, 2, (0,), True),
    6: ("sicaklik_2m", "MERRA2", "yuzey_sicakligi_gunduz", "MOD11C3", "aylik_anomali", 1, 2, (0,), True),
}


def _yaml_yaz(tmp_path, ciftler_metni: str) -> Path:
    yol = tmp_path / "ciftler.yaml"
    yol.write_text("ciftler:\n" + ciftler_metni, encoding="utf-8")
    return yol


# ------------------------------------------------------------------ tanımlar
def test_yaml_eski_tanimlarla_ayni():
    assert [c.no for c in CIFTLER] == [1, 2, 3, 4, 5, 6]
    for no, (d1, u1, d2, u2, seri, bek, kad, gec, har) in ESKI.items():
        c = CIFT[no]
        assert (c.d1, c.u1, c.d2, c.u2, c.seri, c.beklenen, c.kademe, c.gecikmeler, c.harita) == \
               (d1, u1, d2, u2, seri, bek, kad, gec, har)
    assert CIFT[1].not_ == "Yalnız kış ortalaması kar örtüsü ≥ %10 olan hücreler."
    assert CIFT[1].kar_maskesi_esik == 10 and CIFT[1].kar_tarafi == "y"
    assert CIFT[2].not_ == "" and CIFT[3].aylar == (4, 5, 6, 7, 8, 9)
    assert set(CIFT[5].etiket_notlari) == {"ters_yonde", "beklenen_yonde", "anlamsiz"}
    assert CIFT[6].kalite_kontrolu and not CIFT[5].kalite_kontrolu
    assert all(c.fiziksel_gerekce for c in CIFTLER)
    assert not any("neden" in c.fiziksel_gerekce.lower() for c in CIFTLER)   # ilişki dili


def test_kodda_cift_tanimi_kalmadi():
    """physics/*.py içinde çift numarasına göre dal (c.no == …) ya da Cift(…) tanımı yok."""
    import re
    kok = Path(__file__).resolve().parents[1] / "physics"
    for f in kok.glob("*.py"):
        metin = f.read_text(encoding="utf-8")
        assert not re.search(r"\bc\.no\s*==\s*\d", metin), f.name
        assert not re.search(r"^\s*Cift\(\d", metin, flags=re.M), f.name


def test_seri_adi_ve_beklenen():
    assert seri_adi("kis") == "kis_DJF" and seri_adi("ilkbahar") == "ilkbahar_MAM"
    assert seri_adi("aylik", [4, 5, 6, 7, 8, 9]) == "aylik_anomali_nis_eyl"
    assert seri_adi("aylik", range(1, 13)) == "aylik_anomali"
    assert seri_adi("aylik", [6, 7]) == "aylik_anomali_6-7"
    assert [beklenen_kodu(v) for v in ("+", "-", "−", "0", " + ")] == [1, -1, -1, 0, 1]
    with pytest.raises(ValueError, match="beklenen"):
        beklenen_kodu("?")
    with pytest.raises(ValueError, match="mevsim"):
        seri_adi("bahar")


TEMEL = """  - no: 7
    x: {degisken: yagis, urun: GPM}
    y: {degisken: ndvi, urun: MOD13C2}
    mevsim: ilkbahar
    beklenen: "+"
    kademe: 1
"""


@pytest.mark.parametrize("ek, mesaj", [
    ("    harita: false\n    beklenen_degil: 1\n", None),                      # bilinmeyen alan zararsız
    ("    aylar: [4, 5]\n", "aylar"),
    ("    kar_maskesi_esik: 10\n", "kar_maskesi_esik"),
    ("    etiket_notlari: {belki: x}\n", "etiket_notlari"),
    ("    gecikme_ay: -1\n", "negatif"),
])
def test_dogrulama(tmp_path, ek, mesaj):
    yol = _yaml_yaz(tmp_path, TEMEL + ek)
    if mesaj is None:
        assert ciftleri_yukle(yol)[0].no == 7
    else:
        with pytest.raises(ValueError, match=mesaj):
            ciftleri_yukle(yol)


def test_dogrulama_eksik_alan_ve_cift_no(tmp_path):
    with pytest.raises(ValueError, match="'mevsim' alanı eksik"):
        ciftleri_yukle(_yaml_yaz(tmp_path, TEMEL.replace("    mevsim: ilkbahar\n", "")))
    with pytest.raises(ValueError, match="benzersiz"):
        ciftleri_yukle(_yaml_yaz(tmp_path, TEMEL + TEMEL))
    with pytest.raises(ValueError, match="harita: false"):
        ciftleri_yukle(_yaml_yaz(tmp_path, TEMEL.replace('"+"', '"0"')))
    c = ciftleri_yukle(_yaml_yaz(tmp_path, TEMEL.replace('"+"', '"0"') + "    harita: false\n"))[0]
    assert c.beklenen == 0 and c.beklenen_yon == "0"


def test_tirnaksiz_no_anahtari(tmp_path):
    """YAML 1.1'de `no:` boolean False okunur; yükleyici bunu çift numarası sayar."""
    yol = _yaml_yaz(tmp_path, TEMEL)
    import yaml
    assert False in yaml.safe_load(yol.read_text(encoding="utf-8"))["ciftler"][0]
    assert ciftleri_yukle(yol)[0].no == 7


# ------------------------------------------------------------------ regresyon
@pytest.fixture(scope="module")
def veri():
    return ornek_veri(seed=1)


def test_regresyon_tablo_birebir(veri, tmp_path):
    """ciftler.csv (sentetik, 542 satır): YAML'a taşımadan önceki çıktıyla bayt bayt aynı."""
    yol = csv_yaz(ciftler_tablosu(veri), tmp_path / "ciftler.csv")
    assert yol.read_bytes() == (ORNEK / "l4_regresyon__YER_TUTUCU.csv").read_bytes()


def test_regresyon_haritalar(veri):
    """6 harita: değişken toplamları (tolerans 1e-9), etiket/anlamlı sayıları ve attrs aynı."""
    ref = json.loads((ORNEK / "l4_regresyon_haritalar__YER_TUTUCU.json").read_text(encoding="utf-8"))
    goruldu = set()
    for c in CIFTLER:
        if not c.harita:
            continue
        for ad, ds in cift_haritasi(c, veri[f"{c.d1}__{c.u1}"], veri[f"{c.d2}__{c.u2}"]):
            r = ref[ad]
            goruldu.add(ad)
            for k in ("r", "etkin_n", "p", "p_fdr"):
                assert float(np.nansum(ds[k].values.astype("float64"))) == pytest.approx(r[k], rel=1e-9, abs=1e-9)
            for k in ("anlamli", "etiket"):
                assert int(ds[k].values.astype("int64").sum()) == r[k]
            assert int(np.isfinite(ds["r"].values).sum()) == r["gecerli_hucre"]
            assert {k: str(v) for k, v in ds.attrs.items()} == r["attrs"]
    assert goruldu == set(ref)


# ------------------------------------------------------------------ yeni çift
YENI = """
  - no: 7
    ad: İlkbahar yağışı ~ bitki örtüsü (deneme)
    x: {degisken: yagis, urun: GPM}
    y: {degisken: ndvi, urun: MOD13C2}
    mevsim: ilkbahar
    gecikme_ay: 1
    beklenen: "+"
    kademe: 1
    harita: true
    fiziksel_gerekce: Yağışlı ilkbaharlarda bitki örtüsünün daha yeşil olması beklenir.
    not: Deneme çifti.
"""


def test_yeni_cift_eklenince_run_isler(veri, tmp_path):
    """ciftler.yaml'a bir madde eklemek yeter: physics.run onu da tabloya ve haritaya yazar."""
    ham = (Path(run.AYAR_DOSYASI)).read_text(encoding="utf-8")
    yol = tmp_path / "ciftler.yaml"
    yol.write_text(ham.rstrip() + "\n" + YENI, encoding="utf-8")
    ciftler = ciftleri_yukle(yol)
    assert [c.no for c in ciftler] == [1, 2, 3, 4, 5, 6, 7]
    yeni = ciftler[-1]
    assert yeni.seri == "ilkbahar_MAM" and yeni.gecikmeler == (1,)
    assert "yagis__GPM" in run.gereken_girdiler(ciftler) and "ndvi__MOD13C2" in run.gereken_girdiler(ciftler)

    # yalnız yeni çiftin girdileri olan bir paket: komut satırından --ciftler ile
    kup = tmp_path / "paket" / "L1_kup"
    kup.mkdir(parents=True)
    for ad in ("yagis__GPM", "ndvi__MOD13C2"):
        d = veri[ad].copy()
        d.attrs = {"urun_surumu": "v0.1", "lisans": "CC BY 4.0", "doi": "10.5067/TEST", "kademe": 1}
        d.rename(ad.split("__")[0]).to_dataset().to_netcdf(kup / f"{ad}.nc")
    run.main(["--paket", str(tmp_path / "paket"), "--iller-yok", "--ciftler", str(yol)])
    l4 = tmp_path / "paket" / "L4_iliski"
    df = pd.read_csv(l4 / "ciftler.csv", encoding="utf-8-sig")
    assert set(df["cift_no"]) == {7}                     # girdisi olan tek çift
    assert (df["seri"] == "ilkbahar_MAM").all() and (df["gecikme_ay"] == 1).all()
    assert len(df) == 8 and df["r"].notna().all()        # 7 bölge + Türkiye
    assert df["not"].str.startswith("Deneme çifti.").all()
    with xr.open_dataset(l4 / "iliski__yagis__ndvi.nc") as ds:
        assert ds.attrs["cift_no"] == 7 and ds.attrs["seri"] == "ilkbahar_MAM"


def test_varsayilan_ayar_okunur():
    a = ayar_oku()
    assert a["urun_onceligi"]["yagis"][0] == "GPM" and a["urun_onceligi"]["sicaklik_2m"][0] == "MERRA2"
