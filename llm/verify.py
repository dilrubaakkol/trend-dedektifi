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

from .format_tr import NUMBER as NUM, parse_tr

REF = re.compile(r"\[ref:([^\]\s]+)\]")
# Yıl ve sabitler dışındaki serbest sayılar: on yıl, %95 güven, anlamlılık/FDR eşikleri.
DEFAULT_ALLOWED = {10.0, 95.0, 100.0, 0.05, 0.01, 0.001, 0.10}


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
    """Analiz dönemindeki yıllar ("2001-01 … 2025-12", ["2001-01", "2025-12"] ya da analizlerin
    "donem" alanları). Metinde bu yıllar serbestçe geçebilir."""
    texts = [str(results.get("period", ""))] + [str(a.get(k, "")) for a in results.get("analyses", [])
                                                for k in ("donem", "ortak_donem")]
    years = [int(y) for t in texts for y in re.findall(r"(?<!\d)(1[89]\d\d|20\d\d)(?!\d)", t)]
    return {float(y) for y in range(min(years), max(years) + 1)} if years else set()


def _ok_number(tok: str, candidates: set[float], allowed: set[float]) -> bool:
    """Belirteç, gösterilen basamağa yuvarlanmış haliyle bir sonuç sayısına (ya da serbest sabite) eşit mi?"""
    for x, decimals in parse_tr(tok):
        x = abs(x)
        if any(abs(x - a) < 1e-12 for a in allowed):
            return True
        tol = 0.5 * 10 ** (-decimals) + 1e-12
        if any(abs(x - c) <= tol for c in candidates):
            return True
    return False


def _strip_phrases(text: str, phrases) -> str:
    """Değişken adı ve birimleri ("Hava sıcaklığı (2 m)", "10^15 molekül/cm²") sayı içerir ama sonuç değildir;
    denetimden önce metinden çıkarılır. Uzun ifadeler önce çıkarılır."""
    # Yalnız hem harf hem rakam içeren ifadeler: birimi "1" olan değişkenler metindeki her "1"i silmesin.
    keep = {p for p in (phrases or []) if p and re.search(r"\d", p) and re.search(r"[^\W\d_]", p)}
    for ph in sorted(keep, key=len, reverse=True):
        text = text.replace(ph, " ")
    return text


def verify_text(text: str, results: dict, extra_allowed: set[float] | None = None,
                ignore_phrases=None) -> VerifyResult:
    """Açıklama metnini sonuçlara karşı denetler.

    ignore_phrases: içinde rakam olan ama sonuç olmayan ifadeler (değişken başlıkları, birimler)."""
    text = _strip_phrases(text, ignore_phrases)
    # "2025-09" gibi yıl-ay tarihlerinde ay kısmı ayrı bir sayı değildir: yalnız yıl kalsın.
    text = re.sub(r"((?:19|20)\d\d)-(?:0[1-9]|1[0-2])(?!\d)", r"\1", text)
    ids = {a.get("id") for a in results.get("analyses", [])}
    unknown = sorted({r for r in REF.findall(text) if r not in ids})

    ref_numbers = _numbers_in(results.get("analyses", []))
    # Karne/büyüklük kanıtlarının metin sütunlarındaki paket sayıları ("2/3 ürün", "Held ve Soden 2006").
    for a in results.get("analyses", []):
        for t in a.get("sayi_metinleri", []) or []:
            for tok in NUM.findall(re.sub(r"((?:19|20)\d\d)-(?:0[1-9]|1[0-2])(?!\d)", r"\1", str(t))):
                ref_numbers += [v for v, _ in parse_tr(tok)]
    candidates = set()
    for r in ref_numbers:
        candidates.update({abs(r), abs(r) * 100})
    allowed = DEFAULT_ALLOWED | _years(results) | (extra_allowed or set())

    plain = REF.sub(" ", text)
    bad = [tok for tok in NUM.findall(plain) if not _ok_number(tok, candidates, allowed)]

    # Cümle bölme: nokta + boşluk; hemen ardından gelen [ref:..] önceki cümleye aittir.
    # Yalnız serbest sabit/yıl içeren cümle (ör. "%95 güven", "2001-2025") kaynak gerektirmez.
    sentences = re.split(r"(?<=[.!?])\s+(?!\[ref:)|\n+", text)
    uncited = [s.strip() for s in sentences
               if not REF.search(s)
               and any(not _ok_number(n, set(), allowed) for n in NUM.findall(REF.sub(" ", s)))]

    return VerifyResult(ok=not (bad or unknown or uncited), unverified_numbers=bad,
                        unknown_refs=unknown, uncited_sentences=uncited)
