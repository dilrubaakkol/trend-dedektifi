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


def _l3(pkg, deg, urun, il_rows, bolge_rows, birim, kademe=1):
    d = pkg / "L3_ozet"
    d.mkdir(parents=True, exist_ok=True)
    for kind, rows in (("il", il_rows), ("bolge", bolge_rows)):
        recs = []
        for kod, ad, sen, lo, hi, p, q, anl, oran, n in rows:
            recs.append({"bolge_kodu": kod, "bolge_adi": ad, "hucre_sayisi": n, "sen_egimi": sen,
                         "ga_alt": lo, "ga_ust": hi, "p_mk": p, "p_fdr": q, "anlamli": anl,
                         "etkin_n": 21.0, "gereken_yil": 31.0, "anlamli_hucre_orani": oran,
                         "birim": birim, "kademe": kademe,
                         "dogrulanmadi": "evet" if kademe == 2 else "", **META})
        pd.DataFrame(recs).to_csv(d / f"{deg}__{urun}__{kind}.csv", index=False, encoding="utf-8-sig")


@pytest.fixture(scope="module")
def pkg(tmp_path_factory):
    """Konya + İç Anadolu için yer tutucu L3/L4. Konya'nın buharlaşma il özeti yok (bölgeye düşmeli),
    L4 yalnız bölge düzeyinde (ilden bölgeye düşmeli)."""
    p = tmp_path_factory.mktemp("paket") / "trend-dedektifi-turkiye-v0.1"
    il = lambda *v: [("42", "Konya", *v)]
    bolge = lambda *v: [("ic_anadolu", "İç Anadolu Bölgesi", *v)]
    _l3(p, "toprak_nemi", "GLDAS", il(-1.84, -2.6, -1.1, 0.002, 0.03, 1, 0.62, 40),
        bolge(-1.2, -1.9, -0.5, 0.01, 0.06, 1, 0.48, 330), "kg/m²")
    _l3(p, "yagis", "GPM", il(-0.9, -2.4, 0.6, 0.31, 0.52, 0, 0.05, 40),
        bolge(-0.4, -1.5, 0.7, 0.45, 0.6, 0, 0.03, 330), "mm/ay")
    _l3(p, "yagis", "GLDAS", il(-1.1, -2.7, 0.5, 0.22, 0.44, 0, 0.08, 40),
        bolge(-0.6, -1.7, 0.5, 0.3, 0.5, 0, 0.04, 330), "mm/ay")
    _l3(p, "sicaklik_2m", "MERRA2", il(0.48, 0.31, 0.65, 0.0004, 0.002, 1, 0.97, 20),
        bolge(0.45, 0.3, 0.6, 0.0006, 0.003, 1, 0.95, 160), "°C")
    _l3(p, "buharlasma", "GLDAS", [], bolge(0.7, 0.2, 1.2, 0.02, 0.08, 1, 0.4, 330), "mm/ay", kademe=2)
    (p / "L4_iliski").mkdir()
    pd.DataFrame([
        {"cift": "sicaklik_2m__MERRA2~toprak_nemi__GLDAS", "bolge": "ic_anadolu", "r": -0.41,
         "etkin_n": 19.3, "p": 0.008, "etiket": "beklenen_yonde"},
        {"cift": "yagis__GPM~toprak_nemi__GLDAS", "bolge": "ic_anadolu", "r": 0.57,
         "etkin_n": 22.1, "p": 0.0005, "etiket": "beklenen_yonde"},
        {"cift": "ndvi__MOD13C2~yagis__GPM", "bolge": "ic_anadolu", "r": 0.3, "etkin_n": 20.0,
         "p": 0.1, "etiket": "anlamsiz"},
    ]).to_csv(p / "L4_iliski" / "ciftler.csv", index=False, encoding="utf-8-sig")
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
    rel = [a for a in r["analyses"] if a["type"] == "iliski"]
    assert {a["pair"] for a in rel} == {"sicaklik_2m__MERRA2~toprak_nemi__GLDAS",
                                        "yagis__GPM~toprak_nemi__GLDAS"}   # ndvi çifti planda yok
    assert any("ic_anadolu" in w for w in r["warnings"])                  # L4 bölgeye düştü


def test_collect_evidence_without_package(konya_plan, tmp_path):
    r = collect_evidence(konya_plan, tmp_path / "yok")
    assert r["analyses"] == [] and r["warnings"]


# --------------------------------------------------------------------------- doğrulayıcı
def test_verify_turkish_numbers(konya_plan, pkg):
    r = collect_evidence(konya_plan, pkg)
    good = ("Konya'da toprak nemi 2001–2025 döneminde on yılda −1,84 kg/m² azalmıştır (%95 GA −2,6 … −1,1; "
            "q = 0,03) [ref:trend__toprak_nemi__GLDAS]. Toprak nemi ile sıcaklık arasında r = −0,41 "
            "[ref:iliski__sicaklik_2m__MERRA2__toprak_nemi__GLDAS].")
    assert verify_text(good, r).ok
    bad = verify_text("Toprak nemi on yılda −2,5 kg/m² azalmıştır [ref:trend__toprak_nemi__GLDAS].", r)
    assert not bad.ok and bad.unverified_numbers == ["−2,5"]


def test_verify_old_contract_still_works():
    t = "Kar örtüsü on yılda -2.1 % azalıyor, hücrelerin %41'inde anlamlı [ref:trend_kar_ortusu_MOD10CM]."
    assert verify_text(t, EXAMPLE).ok


def test_verify_rejects_unknown_ref_and_uncited():
    r = verify_text("Kar azalıyor [ref:yok_boyle]. Değişim -2.1 %.", EXAMPLE)
    assert r.unknown_refs == ["yok_boyle"] and r.uncited_sentences and not r.ok


def test_template_is_always_verified(kb, konya_plan, pkg):
    r = collect_evidence(konya_plan, pkg)
    text = template_explanation(konya_plan, r, kb)
    assert verify_text(text, r).ok and "−1,84" in text and "kg/m²/10 yıl" in text


# --------------------------------------------------------------------------- uçtan uca (akademisyen)
def test_answer_academic(kb, regions, pkg):
    out = answer("Konya'da kuraklık artıyor mu?", None, kb, None, regions, package=pkg)
    assert out["verified"] and out["explainer"] == "sablon"
    assert "Hamed ve Rao, 1998" in out["methods"] and "ürüne göre 20–330 hücre" in out["methods"]
    assert any("10.5067/SXAVCZFAQLNO" in c for c in out["data_citations"])
    assert any("Benjamini" in r for r in out["method_references"])
    assert "L3_ozet/toprak_nemi__GLDAS__il.csv" in out["files"]
    assert any("Kademe 2" in w for w in out["academic_warnings"])


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
