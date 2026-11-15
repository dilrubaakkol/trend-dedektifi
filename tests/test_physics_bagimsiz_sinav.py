"""physics.bagimsiz_sinav testleri: ön kayıt bütünlüğü ve önceden yazılmış ölçüt (sentetik tablo, internetsiz)."""

import pandas as pd

from physics import bagimsiz_sinav as B


def test_on_kayit_degismedi():
    """Ön kayıt dosyası sonuçlar görüldükten sonra değiştirilirse bu test kırılır."""
    assert B.ozet() == B.ON_KAYIT_SHA256


def test_on_kayit_okunur_no_anahtari():
    c = B.oku()
    assert len(c) == 15 and {x["sinif"] for x in c} == {"kontrol", "fizik"}
    assert all(isinstance(x["no"], str) and x["beklenen"] in "+-" for x in c)
    assert sum(x["sinif"] == "kontrol" for x in c) == 5


def _tablo(kontrol, fizik, kontrol_bolge="beklenen_yonde"):
    s = []
    for i, e in enumerate(kontrol):
        s += [{"no": f"K{i}", "sinif": "kontrol", "bolge_turu": "turkiye", "etiket": e, "hata": ""},
              {"no": f"K{i}", "sinif": "kontrol", "bolge_turu": "bolge", "etiket": kontrol_bolge, "hata": ""}]
    for i, e in enumerate(fizik):
        s.append({"no": f"F{i}", "sinif": "fizik", "bolge_turu": "turkiye", "etiket": e, "hata": ""})
    return pd.DataFrame(s)


def test_olcut_gecer_ve_kalir():
    bek, ans, ters = "beklenen_yonde", "anlamsiz", "ters_yonde"
    d = B.degerlendir(_tablo([bek] * 5, [bek] * 7 + [ans] * 2 + [ters]))
    assert d["kontrol_gecti"] and d["fizik_gecti"] and d["fizik_ters"] == 1
    assert not B.degerlendir(_tablo([bek] * 5, [bek] * 8 + [ters] * 2))["fizik_gecti"]      # 2 ters
    assert not B.degerlendir(_tablo([bek] * 5, [bek] * 5 + [ans] * 5))["fizik_gecti"]       # %50 < %60
    assert not B.degerlendir(_tablo([bek] * 4 + [ans], [bek] * 10))["kontrol_gecti"]
    assert not B.degerlendir(_tablo([bek] * 5, [bek] * 10, kontrol_bolge=ters))["kontrol_gecti"]  # bölgede ters


def test_hatali_cift_basarisiz_sayilir():
    df = _tablo(["beklenen_yonde"] * 5, ["beklenen_yonde"] * 9)
    df = pd.concat([df, pd.DataFrame([{"no": "F9", "sinif": "fizik", "bolge_turu": None, "etiket": None,
                                       "hata": "KeyError: x"}])], ignore_index=True)
    d = B.degerlendir(df)
    assert d["hatali_cift"] == 1 and d["fizik_beklenen_orani"] == 0.9
