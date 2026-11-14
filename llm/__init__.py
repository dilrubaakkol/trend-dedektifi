"""LLM katmanı (Kişi 4): soru -> plan, sonuç -> açıklama, sayı doğrulayıcı.

Arayüzün (Kişi 5) kullanacağı ana fonksiyonlar:
    from llm import KnowledgeBase, answer, plan_question, evidence_table
"""
from .answer import answer
from .explain import evidence_table, template_explanation
from .kb import KnowledgeBase
from .plan import plan_question
from .verify import verify_text

__all__ = ["KnowledgeBase", "answer", "plan_question", "evidence_table", "template_explanation", "verify_text"]
