"""GEÇİCİ — stats/ hazır olunca silinecek.

Kişi 2'nin trend fonksiyonları gelene kadar Kişi 3'ün fiziksel testlerinde kullanılan
Sen eğimi + otokorelasyona göre genişletilmiş güven aralığı + Mann-Kendall.

Yöntem (KISI3_PLAN.md, Adım 2):
- Sen eğimi ve ham %95 aralık: ``scipy.stats.theilslopes``.
- Artıkların gecikme-1 otokorelasyonu r1 → n_etkin = n·(1 − r1)/(1 + r1) (r1 ≤ 0 ise n).
- Alt ve üst yarı genişlik ayrı ayrı √(n / n_etkin) ile çarpılır.
- Mann-Kendall p: ``pymannkendall.hamed_rao_modification_test``.

VARSAYIM (Kişi 2'ye bildirilecek): planın formülü tek başına kısa serilerde yetmiyor.
24 kışlık, φ=0,5 AR(1) gürültülü 10 000 seride ölçülen kapsama (hedef ≥ %90):

    planın formülü                                   %88,3   genişlik 1,00×
    + küçük örneklem düzeltmesi (r1 aşağı yanlı)     %90,2   1,12×   ← sınırda, tohuma göre kalıyor
    + düzeltme + t dağılımı (n_etkin − 2 sd)         %91,6   1,25×   ← VARSAYILAN

Ek iki adım:
1. r1_düz = r1 + (1 + 4·r1) / n  (Marriott-Pope / Kendall yaklaşımı; kısa seride r1 düşük çıkar)
2. Yarı genişlikler ayrıca t₀.₉₇₅(n_etkin − 2) / t₀.₉₇₅(n − 2) ile çarpılır
   (etkin serbestlik derecesi; Santer vd. 2008, J. Climatol.).
İkisi de parametreyle kapatılabilir; ikisi kapalıyken sonuç planın formülüdür.
"""

from __future__ import annotations

import numpy as np
import pymannkendall as mk
from scipy.stats import t as t_dagilimi
from scipy.stats import theilslopes

R1_UST_SINIR = 0.95  # r1 → 1 iken genişletme katsayısı sonsuza gider; üstten kırpılır


def lag1_autocorr(resid: np.ndarray) -> float:
    """Artıkların gecikme-1 otokorelasyonu (ortalaması çıkarılmış)."""
    r = np.asarray(resid, dtype=float)
    r = r - r.mean()
    den = np.sum(r * r)
    if den == 0:
        return 0.0
    return float(np.sum(r[1:] * r[:-1]) / den)


def trend_1d(y, x=None, alpha: float = 0.95, per: float = 10.0,
             kucuk_orneklem_duzeltmesi: bool = True, t_duzeltmesi: bool = True) -> dict:
    """Tek bir seride Sen eğimi, genişletilmiş aralık ve Mann-Kendall p değeri.

    Parametreler
    ----------
    y : dizi
        Seri (ör. kış yılı başına bir değer). NaN'lar atılır.
    x : dizi, isteğe bağlı
        Zaman (yıl). Verilmezse 0, 1, 2, ...
    alpha : float
        Güven düzeyi (0,95 = %95).
    per : float
        Eğimin çarpanı. Yıllık seride 10 → "on yıl başına".
    kucuk_orneklem_duzeltmesi : bool
        r1'e (1 + 4·r1)/n eklensin mi (modül açıklamasına bakın).
    t_duzeltmesi : bool
        Yarı genişlik t(n_etkin − 2) / t(n − 2) ile de çarpılsın mı.

    Döndürür
    -------
    dict: ``slope``, ``ci95`` (genişletilmiş), ``ci95_ham``, ``mk_p``, ``n``,
    ``n_etkin``, ``r1``, ``genisletme`` (katsayı). Eğim ve aralıklar ``per`` ile çarpılmıştır.
    En az 4 geçerli nokta yoksa değerler NaN olur.
    """
    y = np.asarray(y, dtype=float)
    x = np.arange(y.size, dtype=float) if x is None else np.asarray(x, dtype=float)
    ok = np.isfinite(y) & np.isfinite(x)
    y, x = y[ok], x[ok]
    n = int(y.size)
    nan = float("nan")
    if n < 4:
        return dict(slope=nan, ci95=[nan, nan], ci95_ham=[nan, nan], mk_p=nan,
                    n=n, n_etkin=nan, r1=nan, genisletme=nan)

    slope, intercept, lo, hi = theilslopes(y, x, alpha=alpha)
    r1 = lag1_autocorr(y - (intercept + slope * x))
    if kucuk_orneklem_duzeltmesi:
        r1 = r1 + (1.0 + 4.0 * r1) / n
    r1 = min(r1, R1_UST_SINIR)
    n_eff = n * (1.0 - r1) / (1.0 + r1) if r1 > 0 else float(n)
    k = float(np.sqrt(n / n_eff))
    if t_duzeltmesi:
        q = (1.0 + alpha) / 2.0
        k *= float(t_dagilimi.ppf(q, max(n_eff - 2.0, 1.0)) / t_dagilimi.ppf(q, n - 2))
    lo_ext = slope - (slope - lo) * k
    hi_ext = slope + (hi - slope) * k

    try:
        with np.errstate(invalid="ignore", divide="ignore"):
            mk_p = float(mk.hamed_rao_modification_test(y).p)
    except Exception:  # sabit seri vb. — pymannkendall hata verebilir
        mk_p = nan

    return dict(
        slope=float(slope * per),
        ci95=[float(lo_ext * per), float(hi_ext * per)],
        ci95_ham=[float(lo * per), float(hi * per)],
        mk_p=mk_p,
        n=n,
        n_etkin=float(n_eff),
        r1=float(r1),
        genisletme=k,
    )


def winter_mean(da, aylar=(12, 1, 2, 3)):
    """Aylık seriden kış ortalaması; boyut ``kis`` (kış yılı, tamsayı).

    Kış Y = Aralık (Y−1) + Ocak–Mart (Y) (KISI3_PLAN.md, madde 5). Dört aydan biri bile eksikse
    (NaN ya da zaman ekseninde yok) o kış NaN olur; böylece 2001 kışı (Aralık 2000 yok) düşer.
    GEÇİCİ: Kişi 2'nin ``winter_series`` fonksiyonu gelince silinecek.
    """
    import xarray as xr
    t = da["time"].dt
    kis = xr.where(t.month == 12, t.year + 1, t.year)
    sec = da.where(t.month.isin(aylar), drop=True)
    kis = kis.sel(time=sec.time)
    grup = sec.assign_coords(kis=("time", kis.values)).groupby("kis")
    ort = grup.mean("time", skipna=False)
    sayi = grup.count("time")
    return ort.where(sayi == len(aylar))


def trend_map(kis_kup, alpha_fdr: float = 0.10, per: float = 10.0):
    """Piksel başına Sen eğimi + Mann-Kendall p + FDR maskesi (vektörel, hızlı).

    Girdi: (kis, lat, lon). Çıktı: Dataset ``slope`` (birim/10 yıl), ``p``, ``anlamli`` (FDR,
    Benjamini-Hochberg, q = ``alpha_fdr``). Mann-Kendall burada otokorelasyon düzeltmesiz,
    bağ düzeltmesizdir (normal yaklaşım) — GEÇİCİ: Kişi 2'nin ``trend_map``/``apply_fdr``'ı
    gelince silinecek.
    """
    import xarray as xr
    from scipy.stats import norm
    k = kis_kup.transpose("kis", "lat", "lon")
    y = k.values.reshape(k.sizes["kis"], -1).astype(float)            # (T, P)
    x = k["kis"].values.astype(float)
    i, j = np.triu_indices(len(x), 1)
    dy = y[j] - y[i]                                                    # (çift, P)
    slope = np.nanmedian(dy / (x[j] - x[i])[:, None], axis=0) * per
    s = np.nansum(np.sign(dy), axis=0)
    n = np.isfinite(y).sum(axis=0).astype(float)
    var = n * (n - 1) * (2 * n + 5) / 18.0
    zst = np.where(s > 0, s - 1, np.where(s < 0, s + 1, 0.0)) / np.sqrt(np.where(var > 0, var, np.nan))
    p = 2 * norm.sf(np.abs(zst))
    p[n < 8] = np.nan
    # Benjamini-Hochberg
    anl = np.zeros_like(p, dtype=bool)
    ok = np.isfinite(p)
    if ok.any():
        ps = p[ok]
        o = np.argsort(ps)
        m = ps.size
        esik = alpha_fdr * np.arange(1, m + 1) / m
        gec = np.nonzero(ps[o] <= esik)[0]
        if gec.size:
            sinir = ps[o][gec.max()]
            anl[ok] = ps <= sinir
    shp = (k.sizes["lat"], k.sizes["lon"])
    kw = dict(coords={"lat": k.lat, "lon": k.lon}, dims=("lat", "lon"))
    return xr.Dataset({"slope": xr.DataArray(slope.reshape(shp), **kw),
                       "p": xr.DataArray(p.reshape(shp), **kw),
                       "anlamli": xr.DataArray(anl.reshape(shp), **kw)})
