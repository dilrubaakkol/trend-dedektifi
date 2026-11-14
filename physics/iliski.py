"""L4: iki değişkenin yıldan yıla birlikte değişip değişmediği (KISI3_PLAN.md, Faz 1).

Sade anlatım: iki serinin (ör. kış sıcaklığı ve kış kar örtüsü) önce uzun dönemli eğilimleri
(trend) çıkarılır; geriye "bu yıl normalden sıcak / az karlı" gibi yıldan yıla oynamalar kalır.
Bu oynamaların birlikte hareket edip etmediği Pearson korelasyonu (r) ile ölçülür. Seriler
kendi içinde "hafızalı" olduğundan (sıcak yılı sıcak yıl izler) bağımsız gözlem sayısı yıl
sayısından azdır; anlamlılık bu "etkin örneklem" ile hesaplanır (Bretherton vd. 1999).

Etiketler (docs/sozlesmeler.md 2.3): ``beklenen_yonde`` · ``ters_yonde`` · ``anlamsiz``.
Hiçbiri nedensellik anlamına gelmez.
"""

from __future__ import annotations

import numpy as np
from scipy import stats

ALFA = 0.05          # bölge ve Türkiye satırları
ALFA_FDR = 0.10      # haritalar ve il satırları (Benjamini-Hochberg)
ETIKETLER = ("beklenen_yonde", "ters_yonde", "anlamsiz")


def trend_cikar(y, t=None) -> np.ndarray:
    """Seriden en küçük kareler doğrusunu çıkarır (NaN'lar NaN kalır)."""
    y = np.asarray(y, float)
    t = np.arange(len(y), dtype=float) if t is None else np.asarray(t, float)
    ok = np.isfinite(y) & np.isfinite(t)
    out = np.full_like(y, np.nan)
    if ok.sum() < 3:
        return out
    b = np.polyfit(t[ok], y[ok], 1)
    out[ok] = y[ok] - np.polyval(b, t[ok])
    return out


def gecikme1(z, kucuk_orneklem_duzeltmesi: bool = True) -> float:
    """Gecikme-1 otokorelasyonu (ardışık NaN'sız çiftlerden).

    Kısa serilerde (ör. 24 kış) bu tahmin gerçek değerden düşük çıkar; bu da etkin örneklemi
    şişirip sahte "anlamlı" sonuç üretir. Düzeltme: r₁ + (1 + 4 r₁) / n (Kendall 1954'ün
    AR(1) yanlılık yaklaşımı). Sonuç [−0,99, 0,99] aralığına kırpılır.
    """
    z = np.asarray(z, float)
    ok = np.isfinite(z)
    n = int(ok.sum())
    if n < 4:
        return float("nan")
    m = z[ok].mean()
    d = np.where(ok, z - m, np.nan)
    cift = np.isfinite(d[1:]) & np.isfinite(d[:-1])
    pay = np.sum((d[1:] * d[:-1])[cift])
    payda = np.nansum(d * d)
    r1 = 0.0 if payda == 0 else float(pay / payda)
    if kucuk_orneklem_duzeltmesi:
        r1 = r1 + (1 + 4 * r1) / n
    return float(np.clip(r1, -0.99, 0.99))


def etkin_n(n: int, r1_1: float, r1_2: float) -> float:
    """Bretherton vd. (1999): n (1 − r₁r₂) / (1 + r₁r₂); n'yi aşamaz, en az 3."""
    if not (np.isfinite(r1_1) and np.isfinite(r1_2)):
        return float("nan")
    rr = r1_1 * r1_2
    return float(np.clip(n * (1 - rr) / (1 + rr), 3.0, n))


def p_degeri(r: float, n_etkin: float) -> float:
    """İki yönlü p: t = r √((n_etkin − 2)/(1 − r²)), serbestlik n_etkin − 2."""
    if not (np.isfinite(r) and np.isfinite(n_etkin)) or n_etkin <= 2:
        return float("nan")
    r = float(np.clip(r, -0.999999, 0.999999))
    t = r * np.sqrt((n_etkin - 2) / (1 - r * r))
    return float(2 * stats.t.sf(abs(t), n_etkin - 2))


def etiket(r: float, anlamli: bool, beklenen: int) -> str | None:
    """Etiket: anlamlı değilse ``anlamsiz``; anlamlıysa işaret beklenenle aynı mı?"""
    if not np.isfinite(r):
        return None
    if not anlamli:
        return "anlamsiz"
    return "beklenen_yonde" if np.sign(r) == np.sign(beklenen) else "ters_yonde"


def bh_fdr(p) -> np.ndarray:
    """Benjamini-Hochberg düzeltilmiş p (q değerleri). NaN'lar NaN kalır, hesaba girmez."""
    p = np.asarray(p, float)
    q = np.full_like(p, np.nan)
    ok = np.isfinite(p)
    m = int(ok.sum())
    if m == 0:
        return q
    ps = p[ok]
    sira = np.argsort(ps)
    ham = ps[sira] * m / np.arange(1, m + 1)
    ham = np.minimum.accumulate(ham[::-1])[::-1]
    qq = np.empty(m)
    qq[sira] = np.minimum(ham, 1.0)
    q[ok] = qq
    return q


def iliski_1d(x, y, beklenen: int, t=None, alfa: float = ALFA, min_n: int = 8,
              kucuk_orneklem_duzeltmesi: bool = True) -> dict:
    """İki serinin trendi çıkarılmış korelasyonu, etkin n, p ve etiket.

    Parametreler
    ----------
    x, y : aynı uzunlukta diziler (aynı zaman adımları). NaN olan adımlar iki seriden de atılır.
    beklenen : +1 (aynı yönde) ya da −1 (zıt yönde) — fiziğin beklediği işaret.
    t : zaman (trend çıkarmak için), verilmezse 0, 1, 2, …
    alfa : anlamlılık eşiği (``p < alfa``). FDR'li kullanımda etiket sonradan yeniden verilir.
    min_n : ortak değer sayısı bundan azsa hesap yapılmaz.

    Döndürür: ``{r, r1_1, r1_2, n, etkin_n, p, anlamli, etiket}``.
    """
    if beklenen not in (1, -1):
        raise ValueError("beklenen +1 ya da -1 olmalı")
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if x.shape != y.shape:
        raise ValueError("x ve y aynı uzunlukta olmalı")
    t = np.arange(len(x), dtype=float) if t is None else np.asarray(t, float)
    ok = np.isfinite(x) & np.isfinite(y)
    n = int(ok.sum())
    bos = {"r": float("nan"), "r1_1": float("nan"), "r1_2": float("nan"), "n": n,
           "etkin_n": float("nan"), "p": float("nan"), "anlamli": False, "etiket": None}
    if n < min_n:
        return bos
    # ortak adımlar dışındakiler NaN yapılır; ardışıklık (gecikme-1) korunur
    xa = trend_cikar(np.where(ok, x, np.nan), t)
    ya = trend_cikar(np.where(ok, y, np.nan), t)
    # sabit (ya da tamamen doğrusal) seri: trend çıkınca geriye yalnız yuvarlama artığı kalır
    for ham, art in ((x[ok], xa), (y[ok], ya)):
        if np.nanstd(art) <= 1e-9 * (1.0 + np.abs(ham).max()):
            return bos
    r = float(np.corrcoef(xa[ok], ya[ok])[0, 1])
    a = gecikme1(xa, kucuk_orneklem_duzeltmesi)
    b = gecikme1(ya, kucuk_orneklem_duzeltmesi)
    ne = etkin_n(n, a, b)
    p = p_degeri(r, ne)
    anlamli = bool(np.isfinite(p) and p < alfa)
    return {"r": r, "r1_1": a, "r1_2": b, "n": n, "etkin_n": ne, "p": p,
            "anlamli": anlamli, "etiket": etiket(r, anlamli, beklenen)}
