"""Trend motoru (Kişi 2): Sen eğimi, Hamed-Rao Mann-Kendall, genişletilmiş güven aralığı,
Weatherhead "gereken yıl" ve Benjamini-Hochberg FDR.

Girdi serileri yıllık ya da mevsimlik seridir: yılda bir değer, boyut adı ``yil``
(``stats.preprocessing.donem_serisi`` çıktısı). Eğimler "birim / 10 yıl" olarak döner.

Yöntem özeti (ayrıntı: docs/sozlesmeler.md bölüm 2.1):
- Sen eğimi ve ham %95 aralık: ``scipy.stats.theilslopes``.
- Artıkların (seri − Sen doğrusu) gecikme-1 otokorelasyonu r1, yalnız ardışık yıllardan.
- Küçük örneklem düzeltmesi: r1_düz = r1 + (1 + 4·r1)/n (Marriott-Pope / Kendall; kısa seride r1
  aşağı yanlıdır), üstten 0,95'te kırpılır.
- n_etkin = n·(1 − r1_düz)/(1 + r1_düz) (r1_düz ≤ 0 ise n; alttan 3).
- Aralığın iki yarısı ayrı ayrı √(n/n_etkin) · t₀.₉₇₅(n_etkin − 2)/t₀.₉₇₅(n − 2) ile genişletilir
  (etkin serbestlik derecesi; Santer vd. 2008).
- p: ``pymannkendall.hamed_rao_modification_test`` (otokorelasyona göre düzeltilmiş MK). Düzeltme
  varyansı negatif çıkarsa (güçlü negatif otokorelasyon; p NaN) düzeltmesiz MK kullanılır,
  ``mk_yedek = True``.
"""

from __future__ import annotations

import numpy as np
import pymannkendall as mk
from scipy.stats import t as t_dagilimi
from scipy.stats import theilslopes

R1_UST_SINIR = 0.95   # r1 → 1 iken genişletme sonsuza gider; üstten kırpılır
WEATHERHEAD_SABIT = 3.3  # %90 olasılıkla |ω0/σ_ω| > 2 (Weatherhead vd. 1998, denklem 3)


def _r1_ardisik(x: np.ndarray, artiklar: np.ndarray) -> float:
    """Artıkların gecikme-1 korelasyonu; yalnız ardışık yıl çiftlerinden (boşluk atlanmaz)."""
    ardisik = np.isclose(np.diff(x), 1)
    onceki, sonraki = artiklar[:-1][ardisik], artiklar[1:][ardisik]
    if len(onceki) >= 3 and np.std(onceki) > 0 and np.std(sonraki) > 0:
        r1 = float(np.corrcoef(onceki, sonraki)[0, 1])
        return r1 if np.isfinite(r1) else 0.0
    return 0.0


def _weatherhead(omega0: float, sigma_n: float, phi: float, ornek_per_yil: int = 1) -> float:
    """Weatherhead (1998) n* (yıl); ayrıntı ``weatherhead_gereken_yil`` docstring'inde."""
    if not (np.isfinite(omega0) and np.isfinite(sigma_n)) or omega0 == 0 or sigma_n <= 0:
        return float("nan")
    phi = float(np.clip(phi if np.isfinite(phi) else 0.0, -R1_UST_SINIR, R1_UST_SINIR))
    sigma_aylik_esdeger = sigma_n * np.sqrt(12.0 / ornek_per_yil)
    return float((WEATHERHEAD_SABIT * sigma_aylik_esdeger / abs(omega0)
                  * np.sqrt((1 + phi) / (1 - phi))) ** (2.0 / 3.0))


def _trend_np(x: np.ndarray, y: np.ndarray, min_yil: int = 12, kontrol: bool = True,
              kucuk_orneklem_duzeltmesi: bool = True, t_duzeltmesi: bool = True) -> dict:
    """``trend_analizi``'nin numpy çekirdeği (x: yıl, y: değer). Hücre bazında L2 bunu kullanır."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    gecerli = np.isfinite(x) & np.isfinite(y)
    x, y = x[gecerli], y[gecerli]
    n = len(y)

    if n < min_yil:
        return {"durum": "yetersiz_veri", "n": n}

    # Sabit seride trend yok
    if np.allclose(y, y[0]):
        return {"durum": "sabit_seri", "n": n, "egim_10yil": 0.0, "ci_alt": 0.0, "ci_ust": 0.0,
                "n_etkin": float(n), "p_mk": 1.0, "gereken_yil": float("nan")}

    # 1. Ana Mann-Kendall testi (Hamed-Rao düzeltmeli)
    with np.errstate(invalid="ignore", divide="ignore"):
        ana = mk.hamed_rao_modification_test(y)
        # Güçlü negatif otokorelasyonda Hamed-Rao varyans düzeltmesi negatif olabilir (var_s ≤ 0 → p NaN).
        # O zaman düzeltmesiz MK kullanılır (negatif otokorelasyonda o daha temkinlidir) ve işaretlenir.
        mk_yedek = not np.isfinite(ana.p)
        if mk_yedek:
            ana = mk.original_test(y)
        # 2. Kontrol Mann-Kendall testi (L2'de hız için kapatılabilir)
        kontrol_test = mk.trend_free_pre_whitening_modification_test(y) if kontrol else None

    # 3. Sen eğimi ve ilk güven aralığı
    sen = theilslopes(y, x, alpha=0.95)

    # 4. Otokorelasyon: Sen trendini çıkar, ardışık yılları karşılaştır
    artiklar = y - (sen.intercept + sen.slope * x)
    r1_ham = _r1_ardisik(x, artiklar)
    r1 = r1_ham + (1.0 + 4.0 * r1_ham) / n if kucuk_orneklem_duzeltmesi else r1_ham
    r1 = min(r1, R1_UST_SINIR)

    # Negatif otokorelasyonda n_etkin = n; çok küçük etkin örneklemi sınırla
    n_etkin = float(n) if r1 <= 0 else n * (1 - r1) / (1 + r1)
    n_etkin = max(3.0, n_etkin)

    # 5. Güven aralığını genişlet: √(n/n_etkin), ayrıca etkin serbestlik derecesiyle t oranı
    carpan = np.sqrt(n / n_etkin)
    if t_duzeltmesi:
        carpan *= float(t_dagilimi.ppf(0.975, max(n_etkin - 2.0, 1.0)) / t_dagilimi.ppf(0.975, n - 2))
    ci_alt = sen.slope - (sen.slope - sen.low_slope) * carpan
    ci_ust = sen.slope + (sen.high_slope - sen.slope) * carpan

    sonuc = {
        "durum": "ok",
        "n": n,
        "trend": ana.trend,
        "egim_10yil": float(sen.slope * 10),
        "ci_alt": float(ci_alt * 10),
        "ci_ust": float(ci_ust * 10),
        "n_etkin": float(n_etkin),
        "r1": float(r1),
        "r1_ham": float(r1_ham),
        "genisletme": float(carpan),
        "p_mk": float(ana.p),
        "mk_yedek": bool(mk_yedek),
        "gereken_yil": _weatherhead(sen.slope, float(np.std(artiklar, ddof=1)), r1_ham),
    }
    if kontrol_test is not None:
        # Testler farklı karar veriyor mu?
        sonuc["p_mk_kontrol"] = float(kontrol_test.p)
        sonuc["belirsiz"] = bool((ana.p < 0.05) != (kontrol_test.p < 0.05)
                                 or ana.trend != kontrol_test.trend)
    return sonuc


def trend_analizi(seri, min_yil=12, kontrol: bool = True, kucuk_orneklem_duzeltmesi: bool = True,
                  t_duzeltmesi: bool = True):
    """
    Yıllık veya mevsimlik serinin trendini hesaplar.

    Girdi:
        seri: ``yil`` boyutlu xarray.DataArray (NaN'lar atılır)
        min_yil: en az geçerli yıl sayısı; altında ``durum = "yetersiz_veri"``
        kontrol: True ise TFPW Mann-Kendall kontrol testi ve ``belirsiz`` bayrağı da hesaplanır
        kucuk_orneklem_duzeltmesi: r1 + (1 + 4·r1)/n düzeltmesi (modül açıklaması)
        t_duzeltmesi: GA yarı genişliği t(n_etkin − 2)/t(n − 2) ile de çarpılır

    Çıktı (sözlük):
        durum ("ok" | "yetersiz_veri" | "sabit_seri"), n, trend, egim_10yil, ci_alt, ci_ust
        (birim/10 yıl, genişletilmiş %95), n_etkin, r1 (düzeltilmiş), r1_ham, genisletme (çarpan),
        p_mk (Hamed-Rao; düzeltme tanımsızsa düzeltmesiz MK ve mk_yedek = True), gereken_yil
        (Weatherhead), [p_mk_kontrol, belirsiz].
    """
    return _trend_np(seri["yil"].values, seri.values, min_yil=min_yil, kontrol=kontrol,
                     kucuk_orneklem_duzeltmesi=kucuk_orneklem_duzeltmesi, t_duzeltmesi=t_duzeltmesi)


def weatherhead_gereken_yil(seri, ornek_per_yil: int = 1) -> float:
    """Gözlenen eğimi ayırt etmek için gereken yıl sayısı (Weatherhead vd. 1998, J. Geophys. Res.).

        n* = [ 3,3 · σ_N / |ω0| · √((1 + φ) / (1 − φ)) ]^(2/3)

    - ω0: yıllık Sen eğimi (birim/yıl).
    - σ_N: artıkların (seri − Sen doğrusu) standart sapması.
    - φ: artıkların gecikme-1 otokorelasyonu (ardışık yıllardan, ham; ±0,95'te kırpılır).
    - 3,3: %90 olasılıkla |ω0/σ_ω| > 2 koşulu.

    **√12 faktörü:** Weatherhead formülü **aylık** seri için türetilmiştir: σ_N aylık gürültüdür ve
    n yıl × 12 nokta vardır. Eşit aralıklı m noktada OLS eğim varyansı ≈ 12·σ²/(Δ²·m³)'tür:
    - aylık seride (m = 12n, Δ = 1/12 yıl) bu σ²_aylık / n³'e eşittir;
    - yıllık seride (m = n, Δ = 1) 12·σ²_yıllık / n³'e eşittir.
    Yani yılda bir değerli seride formül, σ_N yerine **√12 · σ_N** koyarak kullanılır. Genel olarak
    çarpan √(12 / ornek_per_yil)'dir (aylık seride 1). Mevsimlik seriler de yılda bir değer
    olduğundan √12 alır. φ ise serinin kendi (yıllık) gecikme-1 otokorelasyonudur.

    Eğim 0 ya da seri yetersizse NaN döner.
    """
    x = np.asarray(seri["yil"].values, dtype=float)
    y = np.asarray(seri.values, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(y) < 4 or np.allclose(y, y[0]):
        return float("nan")
    sen = theilslopes(y, x)
    artiklar = y - (sen.intercept + sen.slope * x)
    return _weatherhead(sen.slope, float(np.std(artiklar, ddof=1)), _r1_ardisik(x, artiklar),
                        ornek_per_yil)


def anlamli_kural(p_fdr, ga_alt, ga_ust, alfa: float = 0.10):
    """Projenin tek anlamlılık kuralı (L2 hücreleri, L3 il/bölge ve kaynak uyumu ``k`` bunu kullanır).

    anlamli = 1  ⇔  p_fdr ≤ alfa  VE  %95 genişletilmiş GA sıfırı dışlıyor (ga_alt > 0 ya da ga_ust < 0)
    anlamli = 0  ⇔  p_fdr hesaplanmış ama koşullardan biri sağlanmıyor
    anlamli = −1 ⇔  p_fdr NaN (maske dışı ya da trend hesaplanamadı)

    Gerekçe: MK testi ile genişletilmiş Sen GA'sı farklı yöntemlerdir. Yalnız p_fdr'ye bakmak, GA'sı
    sıfırı kapsayan trendleri "anlamlı" gösteriyordu. İkisinin birlikte sağlanması temkinli taraftır.
    Girdi diziler (aynı şekil) ya da sayılar; çıktı int8 dizi.
    """
    q = np.asarray(p_fdr, dtype=float)
    alt = np.asarray(ga_alt, dtype=float)
    ust = np.asarray(ga_ust, dtype=float)
    with np.errstate(invalid="ignore"):
        evet = (q <= alfa) & ((alt > 0) | (ust < 0))
    return np.where(np.isfinite(q), evet.astype("int8"), np.int8(-1)).astype("int8")


def bh_fdr(p, alfa: float = 0.10):
    """Benjamini-Hochberg FDR (vektörel; NaN'lar atlanır ve NaN kalır).

    Girdi: herhangi bir şekilde p değerleri dizisi.
    Döndürür: (q, anlamli)
        q: BH ile düzeltilmiş p değerleri (aynı şekil; m = NaN olmayan p sayısı),
           q_(i) = min_{j ≥ i} p_(j)·m/j, 1'de kırpılır
        anlamli: bool dizi, q ≤ alfa (NaN girişler False)
    q ≤ alfa, klasik BH "reddet" kararıyla birebir aynıdır.
    """
    p = np.asarray(p, dtype=float)
    q = np.full(p.shape, np.nan)
    ok = np.isfinite(p)
    m = int(ok.sum())
    if m:
        ps = p[ok]
        o = np.argsort(ps)
        oran = ps[o] * m / np.arange(1, m + 1)
        qs = np.minimum.accumulate(oran[::-1])[::-1]
        qo = np.empty(m)
        qo[o] = np.minimum(qs, 1.0)
        q[ok] = qo
    return q, np.where(ok, q <= alfa, False)
