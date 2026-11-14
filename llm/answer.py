"""Orkestratör: soru -> plan -> analiz -> açıklama -> doğrulama (gerekirse yeniden üret) -> yedek.

Analizi bu modül yapmaz: `run_analysis(plan) -> results.json sözlüğü` dışarıdan verilir
(pipeline.py; Kişi 1-3'ün modülleri). Böylece LLM katmanı veri hazır olmadan da test edilir.
"""
from __future__ import annotations

from typing import Callable

from .client import get_client
from .explain import evidence_table, llm_explanation, template_explanation
from .kb import KnowledgeBase
from .plan import plan_question
from .verify import verify_text

MAX_RETRIES = 2


def _available_regions() -> set[str] | None:
    """Veri hattında tanımlı bölgeler (data/regions.py). Okunamazsa kontrol yapılmaz."""
    try:
        from data.regions import REGIONS
        return set(REGIONS)
    except Exception:
        return None


def answer(question: str, run_analysis: Callable[[dict], dict], kb: KnowledgeBase | None = None,
           client="auto", available_regions: set[str] | None = None) -> dict:
    """Kullanıcı sorusunu uçtan uca cevaplar.

    Dönen sözlük (arayüz bunu gösterir):
      plan, results, explanation, verified, explainer ("llm" | "sablon"), attempts,
      evidence (kanıt tablosu satırları), warnings, message (kullanıcıya sorulacak bir şey varsa)
    """
    kb = kb or KnowledgeBase.load()
    warnings: list[str] = []
    if client == "auto":
        try:
            client = get_client()
        except Exception as e:
            client = None
            warnings.append(f"LLM ayarı okunamadı, şablon kullanılacak: {e}")
    if available_regions is None:
        available_regions = _available_regions()

    plan = plan_question(question, kb, client, available_regions)
    warnings += plan.get("warnings", [])
    out = {"plan": plan, "results": None, "explanation": None, "verified": False,
           "explainer": None, "attempts": 0, "evidence": [], "warnings": warnings}
    if not plan["ok"] or plan.get("needs_region") or plan.get("region_missing"):
        out["message"] = plan.get("message")
        return out

    results = run_analysis(plan)
    out["results"], out["evidence"] = results, evidence_table(results, kb)

    feedback = None
    if client is not None:
        for attempt in range(1, MAX_RETRIES + 2):
            out["attempts"] = attempt
            try:
                text = llm_explanation(question, plan, results, kb, client, feedback)
            except Exception as e:
                warnings.append(f"LLM açıklayıcı çalışmadı ({type(e).__name__}); şablona geçildi.")
                break
            check = verify_text(text, results)
            if check.ok:
                out.update(explanation=text, verified=True, explainer="llm")
                return out
            feedback = check.feedback()
        else:
            warnings.append("LLM açıklaması doğrulamayı geçemedi; şablon açıklama gösteriliyor.")

    text = template_explanation(plan, results, kb)
    check = verify_text(text, results)
    out.update(explanation=text, verified=check.ok, explainer="sablon")
    if not check.ok:
        warnings.append("Şablon açıklama bile doğrulanamadı: " + check.feedback())
    return out
