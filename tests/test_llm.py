"""LLM katmanı testleri (Kişi 4). Gerçek LLM ve veri gerekmez: sahte istemci ve docs/sozlesmeler.md
bölüm 2 biçiminde üretilen SAHTE bir analiz paketi kullanılır. Paketteki tüm sayılar YER TUTUCUDUR."""
import json
from pathlib import Path

import pandas as pd
import pytest

from llm import (KnowledgeBase, answer, collect_evidence, format_tr, plan_question,
                 template_explanation, verify_text)
from llm.format_tr import parse_tr

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = json.loads((ROOT / "examples" / "results_example.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase.load()


@pytest.fixture(scope="module")
def regions(kb):
    return {k for _, k, _ in kb._il_names()} | set(kb.places["bolgeler"])


class FakeClient:
    """Sırayla verilen cevapları döndüren sahte LLM."""
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), 0

    def complete(self, system, user):
        self.calls += 1
        r = self.replies[min(self.calls, len(self.replies)) - 1]
        if isinstance(r, Exception):
            raise r
        return r


# --------------------------------------------------------------------------- sahte paket
META = {"donem": "2001-01 … 2025-12", "seri": "yillik_ortalama", "urun_surumu": "v0.1",
        "veri_seti_doi": "(yayında doldurulacak)", "lisans": "CC BY 4.0"}


def _l3(pkg, deg, urun, il_rows, bolge_rows, birim, kademe=1, kis=None, uyari=""):
    """docs/sozlesmeler.md 2.2 biçiminde L3 il/bölge CSV'leri. Her bölge için 5 mevsim satırı yazılır:
    yıllık satır verilen değerlerle, kış satırı `kis` ile (verilmezse), öteki mevsimler BİLEREK 99 —
    adaptör yanlış mevsimi seçerse testler yakalar."""
    d = pkg / "L3_ozet"
    d.mkdir(parents=True, exist_ok=True)
    eb = f"{birim} / 10 yıl"
    for kind, rows in (("il", il_rows), ("bolge", bolge_rows)):
        recs = []
        for kod, anahtar, ad, duzey, ust, sen, lo, hi, p, q, anl, oran, n in rows:
            for mevsim in ("yillik", "kis", "ilkbahar", "yaz", "sonbahar"):
                if mevsim == "yillik":
                    v = (sen, lo, hi, p, q, anl, oran)
                elif mevsim == "kis" and kis is not None:
                    v = kis
                else:
                    v = (99.0, 98.0, 100.0, 0.5, 0.5, 0, 0.0)
                recs.append({"bolge_kodu": kod, "bolge_anahtari": anahtar, "bolge_adi": ad, "duzey": duzey,
                             "ust_bolge": ust, "mevsim": mevsim, "hucre_sayisi": n, "sen_egimi": v[0],
                             "ga_alt": v[1], "ga_ust": v[2], "p_mk": v[3], "p_fdr": v[4], "anlamli": v[5],
                             "etkin_n": 21.0, "gereken_yil": 31.0, "mk_yedek": 0, "anlamli_hucre_orani": v[6],
                             "anlamli_artan_orani": 0.0, "anlamli_azalan_orani": v[6],
                             "medyan_hucre_egimi": v[0], "birim": birim, "egim_birimi": eb,
                             "donem_baslangic": 2001, "donem_bitis": 2025, "trend_uyarisi": uyari, "not": "",
                             "kademe": kademe, "dogrulanmadi": "evet" if kademe == 2 else "",
                             "urun_surumu": "v0.1", "veri_seti_doi": "(yayında doldurulacak)",
                             "lisans": "CC BY 4.0", "doi": ""})
        pd.DataFrame(recs).to_csv(d / f"{deg}__{urun}__{kind}.csv", index=False, encoding="utf-8-sig")


def _karne_ve_buyukluk(p):
    """Bulgu karnesi (2.4) ve büyüklük testleri (2.5) — YER TUTUCU değerler. Sütun listeleri doğrudan
    stats.karne / physics.karne / physics.buyukluk'tan alınır: onlar değişirse bu testler de haber verir."""
    from stats.karne import TREND_SUTUNLARI
    from physics.karne import SUTUNLAR as ILISKI_SUTUNLARI
    from physics.buyukluk import SUTUNLAR as BUYUKLUK_SUTUNLARI

    def satir(cols, **kw):
        return {c: kw.get(c, "") for c in cols}

    (p / "karne").mkdir()
    ortak = dict(a_kaynak_uyumu="uygulanamaz", a_sayi="tek kaynak", b_karistirma="geçti", b_p_perm=0.004,
                 b_blok=2, c_donem="geçti", c_sayi="−1,7 / −1,9", d_esik="geçti", d_sayi="q = 0,03",
                 e_yeterlilik="geçti", e_sayi="31 ≤ 25 değil", f_uyarilar="", f_kritik="",
                 kural_surumu="karne-v1")
    pd.DataFrame([
        satir(TREND_SUTUNLARI, degisken="toprak_nemi", urun="GLDAS", bolge_kodu="42", bolge_adi="Konya",
              duzey="il", mevsim="yillik", sen_egimi=-1.84, egim_birimi="kg/m² / 10 yıl", anlamli=1,
              guven="ORTA", gerekce="tek kaynak (ikinci bağımsız ürün yok)", **ortak),
        satir(TREND_SUTUNLARI, degisken="toprak_nemi", urun="GLDAS", bolge_kodu="42", bolge_adi="Konya",
              duzey="il", mevsim="kis", sen_egimi=99.0, anlamli=0, guven="YOK", gerekce="sonuç anlamlı değil",
              **ortak),
        satir(TREND_SUTUNLARI, degisken="sicaklik_2m", urun="MERRA2", bolge_kodu="42", bolge_adi="Konya",
              duzey="il", mevsim="yillik", sen_egimi=0.48, anlamli=1, guven="YÜKSEK",
              gerekce="2/2 kaynak uyumlu, karıştırma testi geçti", **{**ortak, "a_kaynak_uyumu": "geçti",
                                                                     "a_sayi": "2/2"}),
    ]).to_csv(p / "karne" / "trend_karne_il.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([
        satir(TREND_SUTUNLARI, degisken="buharlasma", urun="GLDAS", bolge_kodu="ic_anadolu",
              bolge_adi="İç Anadolu Bölgesi", duzey="bolge", mevsim="yillik", sen_egimi=0.7, anlamli=1,
              guven="DÜŞÜK", gerekce="dönem kırpmada işaret değişti",
              **{**ortak, "c_donem": "kaldı", "f_kritik": "Kademe 2 (doğrulanmadı)"}),
    ]).to_csv(p / "karne" / "trend_karne_bolge.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([
        satir(ILISKI_SUTUNLARI, cift="yagis__GPM~toprak_nemi__GLDAS", gecikme_ay=0, bolge_turu="il",
              bolge_kodu="42", bolge_adi="Konya", r=0.57, etiket="beklenen_yonde", guven="YÜKSEK",
              gerekce="5 kontrolün 5'i geçti", a_kaynak_uyumu="geçti", a_sayi="2/3 kombinasyon",
              b_karistirma="geçti", b_p_perm=0.002, c_trend="geçti", d_gecikme="uygulanamaz", e_esik="geçti",
              kural_surumu="karne-v1"),
        satir(ILISKI_SUTUNLARI, cift="toprak_nemi__GLDAS~ndvi__MOD13C2", gecikme_ay=2, bolge_turu="il",
              bolge_kodu="42", bolge_adi="Konya", r=0.21, etiket="anlamsiz", guven="YOK",
              gerekce="ilişki anlamlı değil", kural_surumu="karne-v1"),
    ]).to_csv(p / "karne" / "iliski_karne.csv", index=False, encoding="utf-8-sig")

    b = p / "L4_iliski" / "buyukluk"
    b.mkdir()
    bk = dict(a_kaynak_uyumu="geçti", a_sayi="GLDAS ile aynı etiket", b_donem="geçti", c_ga_genisligi="kaldı",
              c_sayi="1,8", guven="ORTA", gerekce="GA bant genişliğinin 1,8 katı", kural_surumu="buyukluk-v1",
              urun_surumu="v0.1", veri_seti_doi="(yayında doldurulacak)", lisans="CC BY 4.0")
    pd.DataFrame([   # su bütçesinin il dosyası yok (sözleşme 2.5): il sorusunda bölgeye düşülmeli
        satir(BUYUKLUK_SUTUNLARI, test="butce", yol="trend", degisken="su_butcesi", urun="GRACE~GPM",
              bolge_turu="bolge", bolge_kodu="ic_anadolu", bolge_adi="İç Anadolu Bölgesi", donem="2003–2024",
              n=22, gozlenen=-31.0, ga_alt=-55.0, ga_ust=-8.0, birim="(mm/yıl) / 10 yıl", beklenen=0.0,
              beklenen_alt=-36.0, beklenen_ust=36.0, beklenen_kaynak="proje seçimi (KURAL.txt)",
              etiket="beklenen büyüklükle tutarlı", yorum="", **bk),
    ]).to_csv(b / "butce__bolge.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([
        satir(BUYUKLUK_SUTUNLARI, test="kar_cizgisi", yol=m, degisken="kar_ortusu", urun="MOD10CM~sicaklik_2m:MERRA2",
              bolge_turu="il", bolge_kodu="25", bolge_adi="Erzurum", donem="2002–2025", n=23, gozlenen=g,
              ga_alt=g - 20, ga_ust=g + 25, birim="m / 10 yıl", beklenen=74.0, beklenen_alt=64.0,
              beklenen_ust=87.0, beklenen_kaynak="6,5 °C/km (bant 5,5–7,5)", etiket="beklenen büyüklükle tutarlı",
              **bk) for m, g in (("kis", 61.0), ("ilkbahar", 110.0))
    ]).to_csv(b / "kar_cizgisi__il.csv", index=False, encoding="utf-8-sig")


@pytest.fixture(scope="module")
def pkg(tmp_path_factory):
    """Konya + İç Anadolu için yer tutucu L3/L4. Konya'nın buharlaşma il özeti yok (bölgeye düşmeli),
    L4 yalnız bölge düzeyinde (ilden bölgeye düşmeli)."""
    p = tmp_path_factory.mktemp("paket") / "trend-dedektifi-turkiye-v0.1"
    il = lambda *v: [("42", "konya", "Konya", "il", "ic_anadolu", *v)]
    bolge = lambda *v: [("ic_anadolu", "ic_anadolu", "İç Anadolu Bölgesi", "bolge", "", *v),
                        ("turkiye", "turkiye", "Türkiye", "ulke", "", *v)]
    _l3(p, "toprak_nemi", "GLDAS", il(-1.84, -2.6, -1.1, 0.002, 0.03, 1, 0.62, 40),
        bolge(-1.2, -1.9, -0.5, 0.01, 0.06, 1, 0.48, 330), "kg/m²")
    _l3(p, "yagis", "GPM", il(-0.9, -2.4, 0.6, 0.31, 0.52, 0, 0.05, 40),
        bolge(-0.4, -1.5, 0.7, 0.45, 0.6, 0, 0.03, 330), "mm/yıl", kis=(-4.2, -6.0, -2.4, 0.001, 0.01, 1, 0.7))
    _l3(p, "yagis", "GLDAS", il(-1.1, -2.7, 0.5, 0.22, 0.44, 0, 0.08, 40),
        bolge(-0.6, -1.7, 0.5, 0.3, 0.5, 0, 0.04, 330), "mm/yıl",
        uyari="zorlama verisi homojen olmayabilir; trend için MERRA2/GPM tercih edilmeli")
    pd.DataFrame([   # Kişi 2'nin kaynak uyumu dosyası (ortak dönem): yıllık k/m = 0/2, kış 1/2
        {"bolge_kodu": "42", "bolge_anahtari": "konya", "bolge_adi": "Konya", "duzey": "il", "mevsim": m,
         "k": k, "m": 2, "isaret_uyumu": 1.0, "egim_GPM": -0.9, "anlamli_GPM": 0, "egim_GLDAS": -1.1,
         "anlamli_GLDAS": 0, "egim_birimi": "mm/yıl / 10 yıl", "ortak_donem": "2001-01 … 2025-09",
         "urunler": "GPM, GLDAS"} for m, k in (("yillik", 0), ("kis", 1))
    ]).to_csv(p / "L3_ozet" / "yagis__kaynak_uyumu__il.csv", index=False, encoding="utf-8-sig")
    _l3(p, "sicaklik_2m", "MERRA2", il(0.48, 0.31, 0.65, 0.0004, 0.002, 1, 0.97, 20),
        bolge(0.45, 0.3, 0.6, 0.0006, 0.003, 1, 0.95, 160), "°C")
    _l3(p, "buharlasma", "GLDAS", [], bolge(0.7, 0.2, 1.2, 0.02, 0.08, 1, 0.4, 330), "mm/yıl", kademe=2)
    (p / "L4_iliski").mkdir()
    # docs/sozlesmeler.md 2.3 sütunları. Konya (il, plaka 42): çift 2, çift 3 (gecikme 1 ve 2), çift 5.
    # Çift 4 (GRACE) il düzeyinde yok -> bölge satırına düşmeli. Çift 1 (kar) planla ilgisiz -> alınmamalı.
    def l4(no, cift, seri, gec, turu, kod, ad, r, p_, q, anl, etiket, kademe=1, not_=""):
        d1, d2 = (x.split("__")[0] for x in cift.split("~"))
        return {"cift_no": no, "cift": cift, "degisken_1": d1, "degisken_2": d2, "seri": seri,
                "gecikme_ay": gec, "beklenen_yon": "+", "bolge_turu": turu, "bolge_kodu": kod,
                "bolge_adi": ad, "hucre_sayisi": 40, "donem": "2001-01 … 2025-12", "n": 25, "r": r,
                "r1_1": 0.2, "r1_2": 0.3, "etkin_n": 19.3, "p": p_, "p_fdr": q, "anlamli": anl,
                "etiket": etiket, "not": not_, "kademe": kademe,
                "dogrulanmadi": "evet" if kademe == 2 else "", "doi_1": "", "doi_2": "", **{
                    k: META[k] for k in ("urun_surumu", "veri_seti_doi", "lisans")}}
    pd.DataFrame([
        l4(2, "yagis__GPM~toprak_nemi__GLDAS", "mevsim_anomali", 0, "il", "42", "Konya",
           0.57, 0.0005, 0.004, 1, "beklenen_yonde"),
        l4(3, "toprak_nemi__GLDAS~ndvi__MOD13C2", "aylik_anomali_nis_eyl", 1, "il", "42", "Konya",
           0.33, 0.04, 0.09, 1, "beklenen_yonde"),
        l4(3, "toprak_nemi__GLDAS~ndvi__MOD13C2", "aylik_anomali_nis_eyl", 2, "il", "42", "Konya",
           0.21, 0.2, 0.35, 0, "anlamsiz"),
        l4(5, "sicaklik_2m__MERRA2~buharlasma__GLDAS", "yaz_JJA", 0, "il", "42", "Konya",
           -0.38, 0.01, 0.06, 1, "ters_yonde", kademe=2, not_="Kurak bölgede buharlaşma su ile sınırlı."),
        l4(4, "yagis__GPM~toplam_su_depolama__GRACE", "yillik", 0, "bolge", "ic_anadolu",
           "İç Anadolu Bölgesi", 0.62, 0.003, None, 1, "beklenen_yonde"),
        l4(4, "yagis__GPM~toplam_su_depolama__GRACE", "yillik", 0, "turkiye", "turkiye", "Türkiye",
           0.5, 0.01, None, 1, "beklenen_yonde"),
        l4(2, "yagis__GPM~toprak_nemi__GLDAS", "mevsim_anomali", 0, "bolge", "ic_anadolu",
           "İç Anadolu Bölgesi", 0.49, 0.001, None, 1, "beklenen_yonde"),
        l4(1, "sicaklik_2m__MERRA2~kar_ortusu__MOD10CM", "kis_DJF", 0, "il", "42", "Konya",
           -0.3, 0.1, 0.2, 0, "anlamsiz"),
    ]).to_csv(p / "L4_iliski" / "ciftler.csv", index=False, encoding="utf-8-sig")
    _karne_ve_buyukluk(p)
    return p


# --------------------------------------------------------------------------- Türkçe sayı
@pytest.mark.parametrize("args,expected", [
    ((-2.1, "mm", 1), "−2,1 mm"), ((1234.5, None, 1), "1.234,5"), ((0.000123,), "0,000123"),
    (([-3.0, -1.2], None, 1), "−3,0 … −1,2"), ((None,), "—"), ((-0.0001, None, 1), "0,0"),
])
def test_format_tr(args, expected):
    assert format_tr(*args) == expected


@pytest.mark.parametrize("tok,values", [
    ("−2,1", [-2.1]), ("1.234,5", [1234.5]), ("0.003", [0.003]), ("1.234", [1234.0, 1.234]), ("12", [12.0]),
])
def test_parse_tr(tok, values):
    assert [v for v, _ in parse_tr(tok)] == values


# --------------------------------------------------------------------------- bilgi tabanı
def test_kb_cards_use_known_variables(kb):
    for c in kb.cards.values():
        for item in c.get("belirti", []) + c.get("supheliler", []):
            assert item["degisken"] in kb.variables, (c["id"], item["degisken"])


def test_variable_cards_cover_catalog(kb):
    """data/catalog.yaml'daki her değişkenin kartı olmalı (docs/eksik_degiskenler.md)."""
    import yaml
    cat = yaml.safe_load((ROOT / "data" / "catalog.yaml").read_text(encoding="utf-8"))
    missing = {v["ad"] for v in cat["degiskenler"]} - set(kb.variables)
    assert not missing, missing


def test_il_keys_match_data_regions(kb):
    pytest.importorskip("shapely")
    from data.regions import list_regions
    assert {k for _, k, _ in kb._il_names()} == {k for k, _ in list_regions()["il"]}


@pytest.mark.parametrize("q,region,level", [
    ("Konya'da kuraklık artıyor mu?", "konya", "il"),
    ("Erzurum'da kar azalıyor mu?", "erzurum", "il"),
    ("İzmir'de yağış nasıl değişti?", "izmir", "il"),
    ("Maraş'ta sıcaklık", "kahramanmaras", "il"),
    ("ISPARTA'DA SICAKLIK", "isparta", "il"),
    ("Karadeniz'de hava nemli mi?", "karadeniz", "bolge"),
    ("Toprak kurumuş mu, Ege'de?", "ege", "bolge"),       # "kurumuş" içindeki "muş" ≠ Muş
    ("Türkiye genelinde NDVI", "turkiye", "turkiye"),
])
def test_resolve_place(kb, regions, q, region, level):
    r = kb.resolve_place(q, regions)
    assert (r["region"], r["level"]) == (region, level) and not r["missing"]


# --------------------------------------------------------------------------- planlayıcı
@pytest.mark.parametrize("q,card", [
    ("Konya'da kuraklık artıyor mu?", "kuraklik"),
    ("Doğu Anadolu'da kar nasıl değişiyor ve bu ısınmayla tutarlı mı?", "kar_isinma"),
    ("Karadeniz'de hava daha nemli mi oluyor?", "nem_artisi"),
    ("Ankara'da sıcaklık nasıl değişti?", "isinma"),
    ("İstanbul'da hava kirliliği artıyor mu?", "hava_kalitesi"),
])
def test_keyword_plan(kb, regions, q, card):
    p = plan_question(q, kb, None, regions)
    assert p["ok"] and p["card_id"] == card and p["method"] == "anahtar_kelime" and p["gerekce"]


def test_variable_only_question(kb, regions):
    p = plan_question("İzmir'de yağış nasıl değişti?", kb, None, regions)
    assert p["kind"] == "degisken" and p["belirti"][0]["degisken"] == "yagis"


def test_unsupported_and_missing_region(kb, regions):
    assert not plan_question("Mars'ta hayat var mı?", kb, None, regions)["ok"]
    assert plan_question("Kuraklık artıyor mu?", kb, None, regions)["needs_region"]
    assert plan_question("İzmir'de kuraklık", kb, None, {"konya"})["region_missing"]


def test_llm_plan_district_to_il(kb, regions):
    c = FakeClient('```json\n{"card_id": "kuraklik", "degisken": null, "yer": "Konya", '
                   '"gerekce": "Toprak nemi kuraklığın göstergesidir."}\n```')
    p = plan_question("Karapınar'da toprak kuruyor mu?", kb, c, regions)
    assert p["method"] == "llm" and (p["region"], p["region_level"], p["region_bolge"]) == \
        ("konya", "il", "ic_anadolu")


def test_llm_plan_invented_id_falls_back(kb, regions):
    p = plan_question("Konya'da kuraklık artıyor mu?", kb,
                      FakeClient('{"card_id": "uydurma", "degisken": "uydurma"}'), regions)
    assert p["method"] == "anahtar_kelime" and p["card_id"] == "kuraklik" and p["warnings"]


def test_llm_plan_crash_falls_back(kb, regions):
    p = plan_question("Konya'da kuraklık?", kb, FakeClient(TimeoutError()), regions)
    assert p["ok"] and p["method"] == "anahtar_kelime"


# --------------------------------------------------------------------------- kanıt adaptörü (L3/L4)
@pytest.fixture
def konya_plan(kb, regions):
    return plan_question("Konya'da kuraklık artıyor mu?", kb, None, regions)


def test_collect_evidence(konya_plan, pkg):
    r = collect_evidence(konya_plan, pkg)
    ids = {a["id"]: a for a in r["analyses"]}
    t = ids["trend__toprak_nemi__GLDAS"]
    assert (t["sen_egimi"], t["label"], t["region_level"]) == (-1.84, "anlamli_azalis", "il")
    assert t["provenance"]["doi"] == "10.5067/SXAVCZFAQLNO"            # katalogdan
    assert ids["trend__buharlasma__GLDAS"]["region_level"] == "bolge"   # il özeti yok -> bölge
    assert ids["trend__buharlasma__GLDAS"]["dogrulanmadi"] is True
    u = ids["uyum__yagis"]
    assert (u["k"], u["m"], u["label"]) == (0, 2, "uyumsuz")
    rel = {a["id"]: a for a in r["analyses"] if a["type"] == "iliski"}
    assert set(rel) == {
        "iliski__yagis__GPM__toprak_nemi__GLDAS",
        "iliski__toprak_nemi__GLDAS__ndvi__MOD13C2__g1",      # gecikme kimliğe girer, çakışmaz
        "iliski__toprak_nemi__GLDAS__ndvi__MOD13C2__g2",
        "iliski__sicaklik_2m__MERRA2__buharlasma__GLDAS",       # iki değişken de planda
    }                                           # kar ve GRACE çiftleri bu planla ilgisiz -> yok
    assert rel["iliski__yagis__GPM__toprak_nemi__GLDAS"]["region_level"] == "il"   # il varken bölge değil


def test_relation_falls_back_per_pair(kb, regions, pkg):
    """Yağış~GRACE yalnız bölge/Türkiye düzeyinde var: Konya sorusunda İç Anadolu satırı kullanılır,
    aynı sorudaki yağış~toprak nemi ise il satırından gelir."""
    plan = plan_question("Konya'da yeraltı suyu azalıyor mu?", kb, None, regions)
    assert plan["card_id"] == "su_kaynaklari"
    rel = {a["id"]: a for a in collect_evidence(plan, pkg)["analyses"] if a["type"] == "iliski"}
    grace = rel["iliski__yagis__GPM__toplam_su_depolama__GRACE"]
    assert (grace["region_level"], grace["region_key"]) == ("bolge", "ic_anadolu")
    assert rel["iliski__yagis__GPM__toprak_nemi__GLDAS"]["region_level"] == "il"


def test_relation_sentence_uses_q_for_il_and_p_for_bolge(kb, konya_plan, pkg):
    r = collect_evidence(konya_plan, pkg)
    text = template_explanation(konya_plan, r, kb)
    assert "1 ay gecikmeli" in text and "FDR q = 0,004" in text
    assert "Kurak bölgede" in text                                   # ters_yonde notu
    assert "2 ay gecikmeli" in text and "Sonuç: ilişki anlamlı değil" in text
    assert verify_text(text, r).ok


@pytest.mark.parametrize("q,mevsim", [
    ("Konya'da kuraklık artıyor mu?", "yillik"), ("Konya'da kışın kuraklık artıyor mu?", "kis"),
    ("Konya'da yaz kuraklığı", "yaz"), ("Konya'da sonbahar yağışı", "sonbahar"),
    ("Erzurum'da kar azalıyor mu?", "kis"),            # kar kartının varsayılanı
    ("Erzurum'da ilkbaharda kar azalıyor mu?", "ilkbahar"),
])
def test_plan_mevsim(kb, regions, q, mevsim):
    assert plan_question(q, kb, None, regions)["mevsim"] == mevsim


def test_season_row_is_selected(kb, regions, pkg):
    """Kış sorusunda kış satırı; hiçbir kanıtta 99 (yanlış mevsim nöbetçisi) olmamalı."""
    plan = plan_question("Konya'da kışın kuraklık artıyor mu?", kb, None, regions)
    r = collect_evidence(plan, pkg)
    gpm = next(a for a in r["analyses"] if a["id"] == "trend__yagis__GPM__kis")
    assert (gpm["sen_egimi"], gpm["mevsim"], gpm["label"]) == (-4.2, "kis", "anlamli_azalis")
    uyum = next(a for a in r["analyses"] if a["type"] == "kaynak_uyumu")
    assert (uyum["id"], uyum["k"], uyum["m"]) == ("uyum__yagis__kis", 1, 2)
    yillik = collect_evidence(plan_question("Konya'da kuraklık artıyor mu?", kb, None, regions), pkg)
    assert all(a.get("sen_egimi") != 99.0 for a in yillik["analyses"])


def test_card_default_season_falls_back_to_yearly(kb, regions, tmp_path):
    """Kar kartının varsayılanı kış; paket yalnız yıllık satır içeriyorsa yıllığa düşülür ve söylenir.
    Kullanıcı kışı AÇIKÇA sorduysa düşülmez."""
    p = tmp_path / "trend-dedektifi-turkiye-v0.1"
    _l3(p, "kar_ortusu", "MOD10CM", [("25", "erzurum", "Erzurum", "il", "dogu_anadolu",
                                      -2.1, -3.0, -1.2, 0.001, 0.02, 1, 0.41, 30)], [], "%")
    f = p / "L3_ozet" / "kar_ortusu__MOD10CM__il.csv"
    df = pd.read_csv(f, encoding="utf-8-sig", dtype={"bolge_kodu": str})
    df[df["mevsim"] == "yillik"].to_csv(f, index=False, encoding="utf-8-sig")
    r = collect_evidence(plan_question("Erzurum'da kar azalıyor mu?", kb, None, regions), p)
    t = next(a for a in r["analyses"] if a["type"] == "trend")
    assert (t["id"], t["mevsim"]) == ("trend__kar_ortusu__MOD10CM", "yillik")
    assert any("yıllık sonuç kullanıldı" in w for w in r["warnings"])
    r = collect_evidence(plan_question("Erzurum'da kışın kar azalıyor mu?", kb, None, regions), p)
    assert not [a for a in r["analyses"] if a["type"] == "trend"]
    assert any("istenen mevsim" in w for w in r["warnings"])


def test_agreement_from_l3_file_and_trend_warning(kb, regions, pkg):
    out = answer("Konya'da kuraklık artıyor mu?", None, kb, None, regions, package=pkg)
    uyum = next(a for a in out["results"]["analyses"] if a["type"] == "kaynak_uyumu")
    assert uyum["ortak_donem"] == "2001-01 … 2025-09" and uyum["isaret_uyumu"] == 1.0
    assert "yagis__kaynak_uyumu__il.csv" in " ".join(out["files"])
    assert any("MERRA2/GPM tercih" in w for w in out["academic_warnings"])        # trend_uyarisi
    assert "MERRA2/GPM tercih" not in out["explanation"]                           # bulgulara girmez
    assert out["verified"]


def TEST_BOLGELER():
    """Küçük sentetik ızgara için üç bölge (gerçek anahtarlarla)."""
    from shapely.geometry import box
    g = box(32.0, 38.0, 33.5, 39.0)
    return [{"duzey": "il", "anahtar": "konya", "ad": "Konya", "kod": "42", "ust": "ic_anadolu", "sorgu": g},
            {"duzey": "bolge", "anahtar": "ic_anadolu", "ad": "İç Anadolu", "kod": "ic_anadolu", "ust": "",
             "sorgu": g},
            {"duzey": "ulke", "anahtar": "turkiye", "ad": "Türkiye", "kod": "turkiye", "ust": "", "sorgu": g}]


def _stats_package(tmp_path):
    """stats.l2 + stats.l3 ile gerçek biçimli bir paket (sentetik yağış küpleri, YER TUTUCU)."""
    np = pytest.importorskip("numpy")
    xr = pytest.importorskip("xarray")
    pytest.importorskip("shapely")
    from shapely.geometry import box
    from stats import l2 as st_l2, l3 as st_l3

    lat, lon = 38.125 + 0.25 * np.arange(4), 32.125 + 0.25 * np.arange(6)
    l1 = tmp_path / "outputs" / "trend-dedektifi-turkiye-v0.1" / "L1_kup"
    l1.mkdir(parents=True)
    rows = []
    for i, urun in enumerate(["GPM", "GLDAS"]):
        t = pd.date_range("2001-01", "2025-12", freq="MS")
        x = np.asarray((t.year - 2001) + (t.month - 0.5) / 12)
        v = 40 - 2.0 * x[:, None, None] + np.random.default_rng(i).normal(0, 1, (len(t), 4, 6))
        da = xr.DataArray(v.astype("float32"), coords={"time": t, "lat": lat, "lon": lon},
                          dims=("time", "lat", "lon"), name="yagis",
                          attrs={"units": "mm/ay", "kademe": np.int32(1), "lisans": "CC BY 4.0", "doi": "x",
                                 "urun_surumu": "v0.1", "veri_seti_doi": "(yayında doldurulacak)", "domain": "land"})
        da.to_dataset().assign_attrs(da.attrs).to_netcdf(l1 / f"yagis__{urun}.nc")
        rows.append({"dosya": f"yagis__{urun}.nc", "degisken": "yagis", "birim": "mm/ay", "kaynak": urun,
                     "kaynak_doi": "x", "donem": "2001-01 … 2025-12", "kademe": 1})
    pd.DataFrame(rows).to_csv(l1 / "ICINDEKILER.csv", index=False, encoding="utf-8-sig")
    bolgeler = TEST_BOLGELER()
    st_l2.uret("v0.1", kok=tmp_path / "outputs")
    st_l3.uret("v0.1", kok=tmp_path / "outputs", bolgeler=bolgeler)
    return tmp_path / "outputs" / "trend-dedektifi-turkiye-v0.1"



def test_real_l3_from_stats_pipeline(kb, regions, tmp_path):
    """Kişi 2'nin kendi kodu (stats.l2 + stats.l3) ile üretilen L3 paketini adaptör doğru okumalı.
    Küp ve bölgeler sentetik (YER TUTUCU); bölge anahtarları gerçek (konya / ic_anadolu / turkiye)."""
    pytest.importorskip("shapely")
    pkg = _stats_package(tmp_path)

    plan = plan_question("Konya'da yağış nasıl değişti?", kb, None, regions)
    r = collect_evidence(plan, pkg)
    gpm = next(a for a in r["analyses"] if a["id"] == "trend__yagis__GPM")
    il = pd.read_csv(pkg / "L3_ozet" / "yagis__GPM__il.csv", dtype={"bolge_kodu": str}, encoding="utf-8-sig")
    beklenen = il[(il["bolge_anahtari"] == "konya") & (il["mevsim"] == "yillik")].iloc[0]
    assert gpm["sen_egimi"] == pytest.approx(beklenen["sen_egimi"]) and gpm["region_level"] == "il"
    assert gpm["egim_birimi"] == beklenen["egim_birimi"] and gpm["label"] == "anlamli_azalis"
    assert gpm["donem"] == f"{int(beklenen['donem_baslangic'])}–{int(beklenen['donem_bitis'])}"
    uyum = next(a for a in r["analyses"] if a["type"] == "kaynak_uyumu")
    assert (uyum["k"], uyum["m"]) == (2, 2) and uyum["file"] == "L3_ozet/yagis__kaynak_uyumu__il.csv"
    out = answer("Konya'da yağış nasıl değişti?", None, kb, None, regions, package=pkg)
    assert out["verified"], out["warnings"]
    tr = collect_evidence(plan_question("Türkiye genelinde yağış nasıl değişti?", kb, None, regions), pkg)
    assert next(a for a in tr["analyses"] if a["type"] == "trend")["region_level"] == "turkiye"


@pytest.mark.parametrize("q,odak", [
    ("Konya'daki ısınma ne kadar güvenilir?", "guven"), ("Bu sonuçtan ne kadar emin olabiliriz?", "guven"),
    ("Karadeniz'de nem ne kadar artmalı, beklenen büyüklükte mi?", "buyukluk"),
    ("Konya'da kuraklık artıyor mu?", None),
])
def test_plan_odak(kb, regions, q, odak):
    assert plan_question(q, kb, None, regions).get("odak") == odak


def test_karne_attached_to_trends_and_relations(kb, regions, pkg):
    plan = plan_question("Konya'da kuraklık artıyor mu?", kb, None, regions)
    r = collect_evidence(plan, pkg)
    k = {a["about"]: a for a in r["analyses"] if a["type"] == "karne"}
    assert k["trend__toprak_nemi__GLDAS"]["guven"] == "ORTA"            # yıllık satır, kış değil
    assert k["trend__buharlasma__GLDAS"]["guven"] == "DÜŞÜK"            # bölgeye düşen trendin karnesi
    assert k["iliski__yagis__GPM__toprak_nemi__GLDAS"]["guven"] == "YÜKSEK"
    assert k["iliski__toprak_nemi__GLDAS__ndvi__MOD13C2__g2"]["guven"] == "YOK"   # gecikme eşleşmesi
    assert "iliski__toprak_nemi__GLDAS__ndvi__MOD13C2__g1" not in k     # karnesi yok -> eklenmez


def test_guven_question_answer(kb, regions, pkg):
    """Görev örneği: "Konya'daki ısınma ne kadar güvenilir?" -> güven özeti + karne satırı, doğrulanmış."""
    out = answer("Konya'daki ısınma ne kadar güvenilir?", None, kb, None, regions, package=pkg)
    t = out["explanation"]
    assert out["plan"]["card_id"] == "isinma" and out["plan"]["odak"] == "guven"
    assert "Güven özeti" in t and "güven YÜKSEK" in t and "p_perm = 0,004" in t
    assert "2/2 kaynak uyumlu" in t and "[ref:karne__trend__sicaklik_2m__MERRA2]" in t
    assert out["verified"], out["warnings"]
    assert any(e["id"] == "karne__trend__sicaklik_2m__MERRA2" for e in out["evidence"])
    assert "bulgu karnesi" in out["methods"] and "karne/trend_karne_il.csv" in out["files"]


def test_buyukluk_tests(kb, regions, pkg):
    # kar çizgisi: kart varsayılanı kış -> yalnız kış yolu
    r = collect_evidence(plan_question("Erzurum'da kar azalıyor mu?", kb, None, regions), pkg)
    buy = [a for a in r["analyses"] if a["type"] == "buyukluk"]
    assert [(a["test"], a["yol"], a["gozlenen"]) for a in buy] == [("kar_cizgisi", "kis", 61.0)]
    # su bütçesi: il dosyası yok -> İç Anadolu; odak büyüklük -> en üstte; doğrulanmış
    out = answer("Konya'da kuraklık beklenen büyüklükte mi, su bütçesi kapanıyor mu?", None, kb, None,
                 regions, package=pkg)
    b = next(a for a in out["results"]["analyses"] if a["type"] == "buyukluk")
    assert (b["id"], b["region_level"]) == ("buyukluk__butce__trend__su_butcesi", "bolge")
    satirlar = [l for l in out["explanation"].splitlines() if l.startswith("- ")]
    assert satirlar[0].startswith("- Su bütçesi kapanışı") and "beklenen bant −36 … 36" in satirlar[0]
    assert out["verified"], out["warnings"]
    assert any("Politis" in r for r in out["method_references"])


def test_real_trend_karne_from_stats(kb, regions, tmp_path, monkeypatch):
    """Halime'nin stats.karne'si ile üretilen gerçek trend karnesi adaptörle eşleşmeli. Karne bölge listesini
    parametre almadığı için (gerçek 81 il), küçük sentetik ızgarada test bölgeleriyle değiştirilir."""
    pytest.importorskip("shapely")
    pkg = _stats_package(tmp_path)
    from stats import karne as st_karne
    from stats import l3 as st_l3
    monkeypatch.setattr(st_l3, "bolge_listesi", TEST_BOLGELER)
    st_karne.uret(pkg, yalniz="trend", tekrar=19)
    plan = plan_question("Konya'da yağış nasıl değişti?", kb, None, regions)
    r = collect_evidence(plan, pkg)
    k = next(a for a in r["analyses"] if a["type"] == "karne" and a["about"] == "trend__yagis__GPM")
    df = pd.read_csv(pkg / "karne" / "trend_karne_il.csv", dtype={"bolge_kodu": str}, encoding="utf-8-sig")
    row = df[(df["degisken"] == "yagis") & (df["urun"] == "GPM") & (df["mevsim"] == "yillik")].iloc[0]
    assert k["guven"] == row["guven"] and k["kural_surumu"] == row["kural_surumu"]
    out = answer("Konya'da yağış ne kadar güvenilir?", None, kb, None, regions, package=pkg)
    assert out["verified"], out["warnings"]


def test_collect_evidence_without_package(konya_plan, tmp_path):
    r = collect_evidence(konya_plan, tmp_path / "yok")
    assert r["analyses"] == [] and r["warnings"]


# --------------------------------------------------------------------------- doğrulayıcı
def test_verify_turkish_numbers(konya_plan, pkg):
    r = collect_evidence(konya_plan, pkg)
    good = ("Konya'da toprak nemi 2001–2025 döneminde on yılda −1,84 kg/m² azalmıştır (%95 GA −2,6 … −1,1; "
            "q = 0,03) [ref:trend__toprak_nemi__GLDAS]. Yağış ile toprak nemi arasında r = 0,57 "
            "[ref:iliski__yagis__GPM__toprak_nemi__GLDAS].")
    assert verify_text(good, r).ok
    bad = verify_text("Toprak nemi on yılda −2,5 kg/m² azalmıştır [ref:trend__toprak_nemi__GLDAS].", r)
    assert not bad.ok and bad.unverified_numbers == ["−2,5"]


def test_verify_old_contract_still_works():
    t = "Kar örtüsü on yılda -2.1 % azalıyor, hücrelerin %41'inde anlamlı [ref:trend_kar_ortusu_MOD10CM]."
    assert verify_text(t, EXAMPLE).ok


def test_verify_year_month_dates():
    r = {"analyses": [{"id": "x", "k": 1, "m": 2, "ortak_donem": "2001-01 … 2025-09"}]}
    assert verify_text("Ortak dönem 2001-01 … 2025-09, 1/2 ürün [ref:x].", r).ok


def test_verify_rejects_unknown_ref_and_uncited():
    r = verify_text("Kar azalıyor [ref:yok_boyle]. Değişim -2.1 %.", EXAMPLE)
    assert r.unknown_refs == ["yok_boyle"] and r.uncited_sentences and not r.ok


def test_template_is_always_verified(kb, konya_plan, pkg):
    r = collect_evidence(konya_plan, pkg)
    text = template_explanation(konya_plan, r, kb)
    assert verify_text(text, r).ok and "−1,84" in text and "kg/m² / 10 yıl" in text


@pytest.mark.parametrize("birim,expected", [
    ("mm", "mm/10 yıl"), ("mm/10 yıl", "mm/10 yıl"), ("°C / 10 yil", "°C / 10 yil"), ("1", "/10 yıl"),
])
def test_slope_units_not_doubled(birim, expected):
    from llm.explain import _slope_units
    assert _slope_units({"birim": birim}) == expected


def test_verify_ignores_digits_in_variable_names(kb):
    r = {"analyses": [{"id": "x", "r": -0.5}]}
    t = "Hava sıcaklığı (2 m) ile NO₂ (10^15 molekül/cm²) arasında r = −0,5 [ref:x]."
    assert not verify_text(t, r).ok
    assert verify_text(t, r, ignore_phrases=kb.number_phrases()).ok


def test_real_l4_example_from_physics(kb, regions, tmp_path):
    """Kişi 3'ün örnek ciftler.csv'si (YER TUTUCU sayılar) ile adaptör ve doğrulayıcı."""
    src = ROOT / "physics" / "ornekler" / "ciftler__YER_TUTUCU.csv"
    if not src.exists():
        pytest.skip("örnek dosya yok")
    pkg = tmp_path / "trend-dedektifi-turkiye-ornek"
    (pkg / "L3_ozet").mkdir(parents=True)
    (pkg / "L4_iliski").mkdir()
    (pkg / "L4_iliski" / "ciftler.csv").write_bytes(src.read_bytes())
    for q, must in [("Erzurum'da kar azalıyor mu?", "iliski__sicaklik_2m__MERRA2__kar_ortusu__MOD10CM"),
                    ("Konya'da kuraklık artıyor mu?", "iliski__toprak_nemi__GLDAS__ndvi__MOD13C2__g2"),
                    ("Konya'da yeraltı suyu azalıyor mu?", "iliski__yagis__GPM__toplam_su_depolama__GRACE")]:
        out = answer(q, None, kb, None, regions, package=pkg)
        ids = {a["id"] for a in out["results"]["analyses"]}
        assert must in ids and out["verified"], (q, out["warnings"])


# --------------------------------------------------------------------------- uçtan uca (akademisyen)
def test_answer_academic(kb, regions, pkg):
    out = answer("Konya'da kuraklık artıyor mu?", None, kb, None, regions, package=pkg)
    assert out["verified"] and out["explainer"] == "sablon"
    assert "Hamed ve Rao, 1998" in out["methods"] and "ürüne göre 20–330 hücre" in out["methods"]
    assert any("10.5067/SXAVCZFAQLNO" in c for c in out["data_citations"])
    assert any("Benjamini" in r for r in out["method_references"])
    assert "L3_ozet/toprak_nemi__GLDAS__il.csv" in out["files"]
    assert any("Kademe 2" in w for w in out["academic_warnings"])
    assert "Benjamini-Hochberg düzeltmesi" in out["methods"] and "1 ve 2 ay gecikme" in out["methods"]
    assert "p < 0,05" not in out["methods"]        # bu soruda bölge/Türkiye ilişki satırı kullanılmadı
    assert any(c.startswith("MOD13C2") and "10.5067/MODIS/MOD13C2.061" in c for c in out["data_citations"])


def test_answer_bolge_relation_uses_p(kb, regions, pkg):
    out = answer("Konya'da yeraltı suyu azalıyor mu?", None, kb, None, regions, package=pkg)
    assert out["verified"] and "p = 0,003" in out["explanation"]       # bölge satırı: p, q değil
    assert "p < 0,05" in out["methods"] and any("GRACE" in w for w in out["academic_warnings"])


def test_answer_retries_after_hallucination(kb, regions, pkg):
    bad = "Toprak nemi on yılda −9,9 kg/m² azaldı [ref:trend__toprak_nemi__GLDAS]."
    good = "Toprak nemi on yılda −1,84 kg/m² azaldı [ref:trend__toprak_nemi__GLDAS]."
    c = FakeClient('{"card_id": "kuraklik", "yer": "Konya"}', bad, good)
    out = answer("Konya'da kuraklık artıyor mu?", None, kb, c, regions, package=pkg)
    assert out["verified"] and out["explainer"] == "llm" and out["attempts"] == 2


def test_answer_falls_back_to_template(kb, regions, pkg):
    c = FakeClient('{"card_id": "kuraklik", "yer": "Konya"}', "Toprak 123 kat kurudu.")
    out = answer("Konya'da kuraklık artıyor mu?", None, kb, c, regions, package=pkg)
    assert out["verified"] and out["explainer"] == "sablon" and out["warnings"]


def test_answer_custom_runner_and_asks_region(kb, regions):
    out = answer("Erzurum'da kar azalıyor mu?", lambda p: EXAMPLE, kb, None, regions)
    assert out["explainer"] == "sablon" and out["verified"]
    out = answer("Kar azalıyor mu?", lambda p: EXAMPLE, kb, None, regions)
    assert out["results"] is None and out["message"]
