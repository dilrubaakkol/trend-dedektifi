"""LLM katmanı (Kişi 4): soru -> plan, kanıtlar (L3/L4) -> açıklama, sayı doğrulayıcı, Türkçe sayı biçimi.

Arayüzün (Kişi 5) kullanacağı ana fonksiyonlar:
    from llm import answer, KnowledgeBase, evidence_table, format_tr
"""
from .answer import answer, available_regions
from .evidence import collect_evidence, find_package
from .explain import evidence_table, template_explanation
from .format_tr import format_p, format_tr
from .kb import KnowledgeBase
from .plan import plan_question
from .verify import verify_text

__all__ = ["KnowledgeBase", "answer", "available_regions", "collect_evidence", "find_package",
           "plan_question", "evidence_table", "template_explanation", "verify_text", "format_tr", "format_p"]
