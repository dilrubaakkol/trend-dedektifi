"""Türkçe sayı biçimi: projedeki TEK biçimlendirici (arayüz `app/formatting.py` bunu kullanır).

Kurallar: ondalık virgül ("2,1"), binlik nokta ("1.234,5"), gerçek eksi işareti ("−2,1"),
aralıklar "a … b", eksik değer "—". Doğrulayıcı (`verify.py`) metindeki sayıları `parse_tr` ile okur;
böylece LLM'in ve şablonun yazdığı her sayı aynı kurallarla denetlenir.
"""
from __future__ import annotations

import math
import re

MINUS = "−"  # U+2212


def _auto_digits(x: float, sig: int = 3) -> int:
    """Anlamlı basamak sayısına göre ondalık basamak: 0.000123 -> 6, 12.3 -> 1, 1234 -> 0."""
    if x == 0 or not math.isfinite(x):
        return 0
    return max(0, sig - 1 - int(math.floor(math.log10(abs(x)))))


def _one(value, digits: int | None) -> str:
    if value is None:
        return "—"
    x = float(value)
    if not math.isfinite(x):
        return "—"
    d = _auto_digits(x) if digits is None else digits
    text = f"{abs(x):,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if digits is None and "," in text:          # otomatik modda 0,700 -> 0,7 (sahte hassasiyet yok)
        text = text.rstrip("0").rstrip(",")
    if x < 0 and float(text.replace(".", "").replace(",", ".")) != 0:
        text = MINUS + text
    return text


def format_tr(value, units: str | None = None, digits: int | None = None) -> str:
    """Sayıyı (ya da [alt, üst] aralığını) Türkçe biçimde yazar.

    digits=None: en fazla 3 anlamlı basamak, sondaki sıfırlar atılır (0,7 ; 0,000123 ; 1.234).
    >>> format_tr(-2.1, "mm", 1)
    '−2,1 mm'
    >>> format_tr(1234.5, digits=1)
    '1.234,5'
    >>> format_tr([-3.0, -1.2], digits=1)
    '−3,0 … −1,2'
    """
    if isinstance(value, (list, tuple)) and len(value) == 2:
        text = f"{_one(value[0], digits)} … {_one(value[1], digits)}"
    else:
        text = _one(value, digits)
    return f"{text} {units}" if units and text != "—" else text


def format_p(p) -> str:
    """p ya da q değeri: "p = 0,003"; çok küçükse "p < 0,001"."""
    if p is None or not math.isfinite(float(p)):
        return "p = —"
    return "p < 0,001" if p < 0.001 else "p = " + format_tr(p, digits=3)


# --------------------------------------------------------------------------- okuma
NUMBER = re.compile(r"(?<![\w.,])[-−+]?[1-9]\d{0,2}(?:\.\d{3})+(?:,\d+)?(?![\d])"   # 1.234,5
                    r"|(?<![\w.,])[-−+]?\d+(?:[.,]\d+)?(?![\d])")                 # 2,1 / 2.1 / 12


def parse_tr(token: str) -> list[tuple[float, int]]:
    """Metindeki bir sayı belirtecini okur. Dönen: [(değer, gösterilen ondalık basamak)].

    Türkçe ("1.234,5", "−2,1") ve İngilizce ondalık ("0.003") yazımları kabul edilir. "1.234" gibi
    belirsiz yazımda iki okuma da döner (1,234 ve 1234); doğrulayıcı ikisinden birini kabul eder.
    """
    t = token.replace(MINUS, "-").replace("+", "")
    if "," in t:                                   # Türkçe: nokta binlik, virgül ondalık
        whole, frac = t.replace(".", "").split(",")
        return [(float(f"{whole}.{frac}"), len(frac))]
    if re.fullmatch(r"-?[1-9]\d{0,2}(?:\.\d{3})+", t):  # belirsiz: binlik mi ondalık mı? ("0.003" değil)
        out = [(float(t.replace(".", "")), 0)]
        if t.count(".") == 1:
            out.append((float(t), len(t.split(".")[1])))
        return out
    if "." in t:
        return [(float(t), len(t.split(".")[1]))]
    return [(float(t), 0)]
