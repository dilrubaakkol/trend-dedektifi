"""Arayüzdeki sayı biçimlendirme köprüsü.

Rehber kuralı: tüm sayı biçimlendirmesi Kişi 4'ün `llm/format_tr.py` içindeki tek bir `format_tr()`
fonksiyonundadır. O modül hazır olduğunda burası doğrudan onu kullanır. Hazır olana kadar aşağıdaki
GEÇİCİ sürüm çalışır; aynı kuralları (ondalık virgül, gerçek eksi işareti, birim) uygular.
"""

from __future__ import annotations

try:  # Kişi 4'ün biçimlendiricisi varsa tek kaynak odur.
    from llm.format_tr import format_tr as _format_tr  # type: ignore
    USING_SHARED_FORMATTER = True
except Exception:  # noqa: BLE001 - modül henüz yok
    _format_tr = None
    USING_SHARED_FORMATTER = False


def _fallback(value, units: str | None = None, digits: int = 1) -> str:
    """Geçici biçimlendirici: 1234.5 → "1.234,5", -2.1 → "−2,1"."""
    if value is None:
        return "—"
    if isinstance(value, (list, tuple)) and len(value) == 2:
        lo, hi = (_fallback(v, None, digits) for v in value)
        text = f"{lo} … {hi}"
    else:
        num = float(value)
        text = f"{abs(num):,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if num < 0:
            text = "−" + text
    return f"{text} {units}" if units else text


def fmt(value, units: str | None = None, digits: int = 1) -> str:
    """Arayüzün kullandığı tek biçimlendirme girişi."""
    if _format_tr is not None:
        try:
            return _format_tr(value, units=units, digits=digits)
        except TypeError:
            return _format_tr(value)
    return _fallback(value, units, digits)


def fmt_p(p) -> str:
    """p değerini kısa biçimde yazar (ör. "p = 0,003", çok küçükse "p < 0,001")."""
    if p is None:
        return "—"
    if p < 0.001:
        return "p < " + fmt(0.001, digits=3)
    return "p = " + fmt(p, digits=3)
