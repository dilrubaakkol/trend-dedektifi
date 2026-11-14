"""Orkestratör: soru -> plan -> kanıtlar (L3/L4) -> açıklama -> doğrulama (gerekirse yeniden üret) -> yedek.

Varsayılan kanıt kaynağı analiz paketidir (`llm/evidence.py`, docs/sozlesmeler.md bölüm 2). Test ya da
eski akış için `run_analysis(plan) -> {"analyses": [...], ...}` dışarıdan verilebilir.
"""
from __future__ import annotations

from typing import Callable

from . import academic
from .client import get_client
from .evidence import collect_evidence
from .explain import evidence_table, llm_explanation, template_explanation
from .kb import KnowledgeBase
from .plan import plan_question
from .verify import verify_text

MAX_RETRIES = 2


def available_regions() -> set[str] | None:
    """Veri tarafında tanımlı bölge anahtarları: turkiye, 7 bölge, 81 il (data/regions.py).
    Okunamazsa None döner ve bölge kontrolü yapılmaz."""
    try:
        from data.regions import list_regions
        r = list_regions()
        return {k for group in ("turkiye", "bolge", "il") for k, _ in r.get(group, [])}
    except Exception:
        return None


def answer(question: str, run_analysis: Callable[[dict], dict] | None = None,
           kb: KnowledgeBase | None = None, client="auto",
           regions: set[str] | None = None, kitle: str = "akademisyen", package=None) -> dict:
    """Kullanıcı sorusunu uçtan uca cevaplar.

    Dönen sözlük (arayüz bunu gösterir):
      plan, results, explanation, verified, explainer ("llm" | "sablon"), attempts,
      evidence (kanıt tablosu), warnings, message (kullanıcıya sorulacak bir şey varsa)
      akademisyen için ayrıca: methods, data_citations, method_references, files, academic_warnings
    """
    kb = kb or KnowledgeBase.load()
    warnings: list[str] = []
    if client == "auto":
        try:
            client = get_client()
        except Exception as e:
            client = None
            warnings.append(f"LLM ayarı okunamadı, şablon kullanılacak: {e}")
    if regions is None:
        regions = available_regions()

    plan = plan_question(question, kb, client, regions)
    warnings += plan.get("warnings", [])
    out = {"plan": plan, "results": None, "explanation": None, "verified": False, "explainer": None,
           "attempts": 0, "evidence": [], "warnings": warnings, "kitle": kitle}
    if not plan["ok"] or plan.get("needs_region") or plan.get("region_missing"):
        out["message"] = plan.get("message")
        return out

    results = run_analysis(plan) if run_analysis else collect_evidence(plan, package)
    out["results"], out["evidence"] = results, evidence_table(results, kb)
    if kitle == "akademisyen":
        out.update(methods=academic.methods_paragraph(results, kb),
                   data_citations=academic.data_citations(results),
                   method_references=academic.method_references(results),
                   files=academic.files_used(results),
                   academic_warnings=academic.academic_warnings(results, kb))
    if not results.get("analyses"):
        out.update(explanation=template_explanation(plan, results, kb, kitle), verified=True,
                   explainer="sablon", message="Bu bölge ve değişkenler için analiz sonucu bulunamadı.")
        return out

    feedback = None
    if client is not None:
        for attempt in range(1, MAX_RETRIES + 2):
            out["attempts"] = attempt
            try:
                text = llm_explanation(question, plan, results, kb, client, feedback, kitle)
            except Exception as e:
                warnings.append(f"LLM açıklayıcı çalışmadı ({type(e).__name__}); şablona geçildi.")
                break
            check = verify_text(text, results, ignore_phrases=kb.number_phrases())
            if check.ok:
                out.update(explanation=text, verified=True, explainer="llm")
                return out
            feedback = check.feedback()
        else:
            warnings.append("LLM açıklaması doğrulamayı geçemedi; şablon açıklama gösteriliyor.")

    text = template_explanation(plan, results, kb, kitle)
    check = verify_text(text, results, ignore_phrases=kb.number_phrases())
    out.update(explanation=text, verified=check.ok, explainer="sablon")
    if not check.ok:
        warnings.append("Şablon açıklama bile doğrulanamadı: " + check.feedback())
    return out
