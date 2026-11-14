"""Soru -> plan. LLM yalnızca KATALOGDAN SEÇİM yapar (kart/değişken kimliği + yer adı);
kimlikler kodda doğrulanır, yer adı deterministik olarak bölgeye çevrilir. LLM yoksa veya
hatalı cevap verirse anahtar kelime eşleştirmesi devreye girer.
"""
from __future__ import annotations

import json
import re

from .kb import KnowledgeBase

PLAN_SYSTEM = """Sen bir NASA yer bilimi veri asistanısın. Kullanıcının Türkiye hakkındaki sorusunu,
aşağıdaki katalogdan BİR süreç kartına ya da (uygun kart yoksa) BİR değişkene eşle ve soruda geçen
yer adını aynen çıkar. Katalogda olmayan kimlik UYDURMA. Yalnızca şu JSON'u döndür:
{"card_id": "<katalogdaki kart kimliği ya da null>",
 "degisken": "<kart null ise katalogdaki değişken kimliği ya da null>",
 "yer": "<soruda geçen il/bölge adı ya da null>",
 "gerekce": "<neden bu kartı/değişkeni seçtiğini lise öğrencisine anlatan tek cümle>"}
"""


def _parse_json(text: str) -> dict:
    """LLM cevabındaki ilk JSON nesnesini ayıklar (```json bloklarına dayanıklı)."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("LLM cevabında JSON yok")
    return json.loads(m.group(0))


def _ask_llm(question: str, kb: KnowledgeBase, client) -> dict:
    raw = client.complete(PLAN_SYSTEM, kb.catalog_for_prompt() + f"\n\nSORU: {question}")
    d = _parse_json(raw)
    card = d.get("card_id") if d.get("card_id") in kb.cards else None
    var = d.get("degisken") if d.get("degisken") in kb.variables else None
    if card is None and var is None:
        raise ValueError("LLM katalogda olmayan ya da boş bir seçim döndürdü")
    return {"card_id": card, "degisken": var, "yer": d.get("yer"),
            "gerekce": str(d.get("gerekce") or "")}


def plan_question(question: str, kb: KnowledgeBase, client=None,
                  available_regions: set[str] | None = None) -> dict:
    """Kullanıcı sorusunu analiz planına çevirir.

    Dönen plan (arayüz ve analiz modülleri bunu kullanır):
      ok, kind ("surec" | "degisken"), card_id, card_title, sade_tanim,
      belirti, supheliler, fiziksel_test, alternatifler,
      region, region_name, place_matched, needs_region, region_missing,
      method ("llm" | "anahtar_kelime"), gerekce, warnings, message
    """
    warnings: list[str] = []
    choice, method = None, "anahtar_kelime"
    if client is not None:
        try:
            choice, method = _ask_llm(question, kb, client), "llm"
        except Exception as e:  # LLM çökse de demo durmasın
            warnings.append(f"LLM planlayıcı kullanılamadı, anahtar kelimeye geçildi ({type(e).__name__}).")
    if choice is None:
        card = kb.match_card(question)
        choice = {"card_id": card, "degisken": None if card else kb.match_variable(question),
                  "yer": None, "gerekce": ""}

    plan: dict = {"ok": True, "question": question, "method": method,
                  "gerekce": choice["gerekce"], "warnings": warnings}

    if choice["card_id"]:
        c = kb.cards[choice["card_id"]]
        plan.update(kind="surec", card_id=c["id"], card_title=c["baslik"], sade_tanim=c.get("sade_tanim"),
                    belirti=c.get("belirti", []), supheliler=c.get("supheliler", []),
                    fiziksel_test=c.get("fiziksel_test"), alternatifler=c.get("alternatifler", []))
        if not plan["gerekce"]:
            plan["gerekce"] = (f"Soru \"{c['baslik']}\" konusuyla eşleşti; bu konuda "
                               f"{', '.join(kb.variables[b['degisken']]['baslik'] for b in c['belirti'])} "
                               "belirti olarak incelenir.")
    elif choice["degisken"]:
        v = kb.variables[choice["degisken"]]
        plan.update(kind="degisken", card_id=None, card_title=v["baslik"], sade_tanim=v["sade_tanim"],
                    belirti=[{"degisken": v["ad"], "urun": v["ana_urun"], "beklenen_yon": "belirsiz"}],
                    supheliler=[], fiziksel_test=None, alternatifler=[])
        if not plan["gerekce"]:
            plan["gerekce"] = f"Soru doğrudan \"{v['baslik']}\" değişkeniyle ilgili."
    else:
        topics = sorted({c.get("konu", c["baslik"]) for c in kb.cards.values()})
        plan.update(ok=False, message="Bu soruyu henüz desteklenen bir konuyla eşleştiremedim. "
                                      "Şu konularda soru sorabilirsin: " + ", ".join(topics) + ".")
        return plan

    place = kb.resolve_place(choice["yer"], available_regions) if choice["yer"] else None
    if not place or place["region"] is None:
        place = kb.resolve_place(question, available_regions)
    plan.update(region=place["region"], place_matched=place["matched"],
                region_name=kb.region_name(place["region"]) if place["region"] else None,
                needs_region=place["region"] is None, region_missing=place["missing"])
    if plan["needs_region"]:
        plan["message"] = "Hangi il ya da bölgeyi incelemek istersin?"
    elif plan["region_missing"]:
        plan["message"] = (f"{plan['region_name']} için veri henüz hazırlanmadı. "
                           "Mevcut bölgelerden birini seç.")
    return plan
