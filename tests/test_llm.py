"""LLM katmanı testleri (Kişi 4). Gerçek LLM ve veri gerekmez: sahte istemci ve
examples/results_example.json (YER TUTUCU sayılar) kullanılır."""
import json
from pathlib import Path

import pytest

from llm import KnowledgeBase, answer, plan_question, template_explanation, verify_text

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = json.loads((ROOT / "examples" / "results_example.json").read_text(encoding="utf-8"))
ALL_REGIONS = {"turkiye", "marmara", "ege", "akdeniz", "ic_anadolu", "karadeniz",
               "dogu_anadolu", "guneydogu_anadolu", "konya"}


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase.load()


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


# ------------------------------------------------------------------ bilgi tabanı
def test_kb_cards_use_contract_variables(kb):
    """Kartlardaki her değişken, sözleşmedeki değişken listesinde olmalı."""
    for c in kb.cards.values():
        for item in c.get("belirti", []) + c.get("supheliler", []):
            assert item["degisken"] in kb.variables, (c["id"], item["degisken"])


@pytest.mark.parametrize("q,region", [
    ("Konya'da kuraklık artıyor mu?", "konya"),
    ("Erzurum'da kar azalıyor mu?", "dogu_anadolu"),
    ("İzmir'de yağış nasıl değişti?", "ege"),
    ("Kahramanmaraş'ta sıcaklık", "akdeniz"),
    ("ISPARTA'DA SICAKLIK", "akdeniz"),
    ("Karadeniz'de hava nemli mi?", "karadeniz"),
    ("Toprak kurumuş mu, Ege'de?", "ege"),       # "kurumuş" içindeki "muş" ≠ Muş
])
def test_resolve_place(kb, q, region):
    assert kb.resolve_place(q, ALL_REGIONS)["region"] == region


def test_konya_without_special_region_falls_back_to_bolge(kb):
    assert kb.resolve_place("Konya'da kuraklık", {"ic_anadolu"})["region"] == "ic_anadolu"


# ------------------------------------------------------------------ planlayıcı (yedek)
@pytest.mark.parametrize("q,card", [
    ("Konya'da kuraklık artıyor mu?", "kuraklik"),
    ("Doğu Anadolu'da kar nasıl değişiyor ve bu ısınmayla tutarlı mı?", "kar_isinma"),
    ("Karadeniz'de hava daha nemli mi oluyor?", "nem_artisi"),
    ("Ankara'da sıcaklık nasıl değişti?", "isinma"),
])
def test_keyword_plan(kb, q, card):
    p = plan_question(q, kb, None, ALL_REGIONS)
    assert p["ok"] and p["card_id"] == card and p["method"] == "anahtar_kelime"
    assert p["gerekce"]


def test_variable_only_question(kb):
    p = plan_question("İzmir'de yağış nasıl değişti?", kb, None, ALL_REGIONS)
    assert p["kind"] == "degisken" and p["belirti"][0]["degisken"] == "yagis"


def test_unsupported_and_missing_region(kb):
    assert not plan_question("Mars'ta hayat var mı?", kb, None, ALL_REGIONS)["ok"]
    assert plan_question("Kuraklık artıyor mu?", kb, None, ALL_REGIONS)["needs_region"]
    assert plan_question("İzmir'de kuraklık", kb, None, {"konya"})["region_missing"]


# ------------------------------------------------------------------ planlayıcı (LLM)
def test_llm_plan_valid(kb):
    c = FakeClient('```json\n{"card_id": "kuraklik", "degisken": null, "yer": "Konya", '
                   '"gerekce": "Toprak nemi kuraklığın göstergesi."}\n```')
    p = plan_question("Konya tarımı tehlikede mi?", kb, c, ALL_REGIONS)
    assert p["method"] == "llm" and p["card_id"] == "kuraklik" and p["region"] == "konya"


def test_llm_plan_invented_id_falls_back(kb):
    c = FakeClient('{"card_id": "uydurma_kart", "degisken": "uydurma", "yer": null}')
    p = plan_question("Konya'da kuraklık artıyor mu?", kb, c, ALL_REGIONS)
    assert p["method"] == "anahtar_kelime" and p["card_id"] == "kuraklik" and p["warnings"]


def test_llm_plan_crash_falls_back(kb):
    p = plan_question("Konya'da kuraklık?", kb, FakeClient(TimeoutError()), ALL_REGIONS)
    assert p["ok"] and p["method"] == "anahtar_kelime"


# ------------------------------------------------------------------ doğrulayıcı
def test_verify_accepts_numbers_from_results():
    t = ("Kar örtüsü on yılda -2.1 % azalıyor (%95 aralık -3.0 ile -1.2), hücrelerin %41'inde anlamlı "
         "[ref:trend_kar_ortusu_MOD10CM]. 2001-2025 döneminde kar çizgisi 40 ile 95 m kaydı [ref:sinir_rakim_kar].")
    assert verify_text(t, EXAMPLE).ok


def test_verify_rejects_invented_number():
    r = verify_text("Kar örtüsü on yılda 7.5 % azalıyor [ref:trend_kar_ortusu_MOD10CM].", EXAMPLE)
    assert not r.ok and r.unverified_numbers == ["7.5"]


def test_verify_rejects_unknown_ref_and_uncited():
    r = verify_text("Kar azalıyor [ref:yok_boyle]. Değişim -2.1 %.", EXAMPLE)
    assert r.unknown_refs == ["yok_boyle"] and r.uncited_sentences and not r.ok


def test_template_is_always_verified(kb):
    p = plan_question("Doğu Anadolu'da kar azalıyor mu?", kb, None, ALL_REGIONS)
    assert verify_text(template_explanation(p, EXAMPLE, kb), EXAMPLE).ok


# ------------------------------------------------------------------ uçtan uca
def run(plan):
    return EXAMPLE


def test_answer_retries_after_hallucination(kb):
    bad = "Kar on yılda 9.9 % azalıyor [ref:trend_kar_ortusu_MOD10CM]."
    good = "Kar on yılda -2.1 % azalıyor [ref:trend_kar_ortusu_MOD10CM]."
    c = FakeClient('{"card_id": "kar_isinma", "yer": "Erzurum"}', bad, good)
    out = answer("Erzurum'da kar azalıyor mu?", run, kb, c, ALL_REGIONS)
    assert out["verified"] and out["explainer"] == "llm" and out["attempts"] == 2
    assert out["evidence"][0]["id"] == "trend_kar_ortusu_MOD10CM"


def test_answer_falls_back_to_template(kb):
    c = FakeClient('{"card_id": "kar_isinma", "yer": "Erzurum"}', "Kar 123 kat azaldı.")
    out = answer("Erzurum'da kar azalıyor mu?", run, kb, c, ALL_REGIONS)
    assert out["verified"] and out["explainer"] == "sablon" and out["warnings"]


def test_answer_without_llm_and_asks_region(kb):
    assert answer("Erzurum'da kar azalıyor mu?", run, kb, None, ALL_REGIONS)["explainer"] == "sablon"
    out = answer("Kar azalıyor mu?", run, kb, None, ALL_REGIONS)
    assert out["results"] is None and out["message"]
