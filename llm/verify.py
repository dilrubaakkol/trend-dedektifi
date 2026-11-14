"""Halüsinasyon koruması. Açıklama metni şu üç kuralı sağlamalı:
  1. Metindeki her sayı, sonuç dosyasındaki (results.json) bir sayıya eşit olmalı
     (gösterilen basamağa yuvarlanmış, mutlak değer ya da yüzde hali kabul edilir).
  2. Her [ref:id] bağlantısı sonuçlarda gerçekten olan bir analize işaret etmeli.
  3. Sayı içeren her cümle en az bir [ref:id] taşımalı (izlenebilirlik = açıklanabilirlik).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

REF = re.compile(r"\[ref:([^\]\s]+)\]")
NUM = re.compile(r"(?<![\w.])[-−+]?\d+(?:[.,]\d+)?")
# Yıl ve sabitler dışındaki serbest sayılar: on yıl, %95 güven, olağan anlamlılık eşikleri.
DEFAULT_ALLOWED = {10.0, 95.0, 100.0, 0.05, 0.01, 0.001}


@dataclass
class VerifyResult:
    ok: bool
    unverified_numbers: list[str] = field(default_factory=list)
    unknown_refs: list[str] = field(default_factory=list)
    uncited_sentences: list[str] = field(default_factory=list)

    def feedback(self) -> str:
        """LLM'e yeniden üretirken verilecek düzeltme talimatı."""
        parts = []
        if self.unverified_numbers:
            parts.append("Şu sayılar analiz sonuçlarında yok, kaldır ya da sonuçtaki değeri kullan: "
                         + ", ".join(self.unverified_numbers))
        if self.unknown_refs:
            parts.append("Şu kanıt kimlikleri yok, yalnızca verilen id'leri kullan: " + ", ".join(self.unknown_refs))
        if self.uncited_sentences:
            parts.append("Sayı içeren her cümlenin sonuna ilgili [ref:id] ekle. Eksik olanlar: "
                         + " | ".join(s[:60] for s in self.uncited_sentences))
        return "\n".join(parts)


def _numbers_in(obj) -> list[float]:
    """Sonuç nesnesindeki tüm sonlu sayılar (iç içe dict/list)."""
    if isinstance(obj, bool) or obj is None:
        return []
    if isinstance(obj, (int, float)):
        return [float(obj)] if math.isfinite(obj) else []
    if isinstance(obj, dict):
        return [x for k, v in obj.items() if not str(k).startswith("_") for x in _numbers_in(v)]
    if isinstance(obj, (list, tuple)):
        return [x for v in obj for x in _numbers_in(v)]
    return []


def _years(results: dict) -> set[float]:
    try:
        y0, y1 = (int(str(p)[:4]) for p in results.get("period", []))
        return {float(y) for y in range(y0, y1 + 1)}
    except (ValueError, TypeError):
        return set()


def verify_text(text: str, results: dict, extra_allowed: set[float] | None = None) -> VerifyResult:
    """Açıklama metnini sonuçlara karşı denetler."""
    ids = {a.get("id") for a in results.get("analyses", [])}
    unknown = sorted({r for r in REF.findall(text) if r not in ids})

    ref_numbers = _numbers_in(results.get("analyses", []))
    candidates = set()
    for r in ref_numbers:
        candidates.update({abs(r), abs(r) * 100})
    allowed = DEFAULT_ALLOWED | _years(results) | (extra_allowed or set())

    bad = []
    plain = REF.sub(" ", text)
    for tok in NUM.findall(plain):
        t = tok.replace("−", "-").replace(",", ".")
        x = abs(float(t))
        if x in allowed:
            continue
        decimals = len(t.split(".")[1]) if "." in t else 0
        tol = 0.5 * 10 ** (-decimals) + 1e-9
        if not any(abs(x - c) <= tol for c in candidates):
            bad.append(tok)

    # Cümle bölme: nokta + boşluk; hemen ardından gelen [ref:..] önceki cümleye aittir.
    sentences = re.split(r"(?<=[.!?])\s+(?!\[ref:)|\n+", text)
    uncited = [s.strip() for s in sentences
               if NUM.search(REF.sub(" ", s)) and not REF.search(s)
               and any(not abs(float(n.replace("−", "-").replace(",", "."))) in allowed
                       for n in NUM.findall(REF.sub(" ", s)))]

    return VerifyResult(ok=not (bad or unknown or uncited), unverified_numbers=bad,
                        unknown_refs=unknown, uncited_sentences=uncited)
