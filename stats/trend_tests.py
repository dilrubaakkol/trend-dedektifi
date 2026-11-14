
import numpy as np
import xarray as xr
import pymannkendall as mk
from scipy.stats import theilslopes


def trend_analizi(seri, min_yil=12):
    """
    Yillik veya mevsimlik serinin trendini hesaplar.

    Girdi:
        seri: yil boyutlu xarray.DataArray

    Cikti:
        Sen egimi, guven araligi,
        Mann-Kendall testleri ve p degerleri.
    """

    yillar = seri["yil"].values.astype(float)
    degerler = seri.values.astype(float)

    # Eksik verileri temizle
    gecerli = (
        np.isfinite(yillar)
        & np.isfinite(degerler)
    )

    x = yillar[gecerli]
    y = degerler[gecerli]

    n = len(y)

    if n < min_yil:
        return {
            "durum": "yetersiz_veri",
            "n": n
        }

    # Sabit seride trend yok
    if np.allclose(y, y[0]):
        return {
            "durum": "sabit_seri",
            "n": n,
            "egim_10yil": 0.0,
            "p_mk": 1.0
        }

    # 1. Ana Mann-Kendall testi
    ana = mk.hamed_rao_modification_test(y)

    # 2. Kontrol Mann-Kendall testi
    kontrol = (
        mk.trend_free_pre_whitening_modification_test(y)
    )

    # 3. Sen egimi ve ilk guven araligi
    sen = theilslopes(y, x, alpha=0.95)

    # 4. Otokorelasyonu hesapla
    # Sen trendini seriden cikar
    tahmin = sen.intercept + sen.slope * x
    artiklar = y - tahmin

    # Sadece ardisik yillari karsilastir
    ardisik = np.isclose(np.diff(x), 1)

    onceki = artiklar[:-1][ardisik]
    sonraki = artiklar[1:][ardisik]

    if (
        len(onceki) >= 3
        and np.std(onceki) > 0
        and np.std(sonraki) > 0
    ):
        r1 = float(np.corrcoef(
            onceki, sonraki
        )[0, 1])
    else:
        r1 = 0.0

    # Negatif otokorelasyonda n_etkin = n
    if not np.isfinite(r1) or r1 <= 0:
        n_etkin = float(n)
    else:
        n_etkin = n * (1 - r1) / (1 + r1)

    # Cok kucuk etkin orneklemi sinirla
    n_etkin = max(3.0, n_etkin)

    # Guven araligini genislet
    carpan = np.sqrt(n / n_etkin)

    ci_alt = sen.slope - (
        sen.slope - sen.low_slope
    ) * carpan

    ci_ust = sen.slope + (
        sen.high_slope - sen.slope
    ) * carpan

    # Testler farkli karar veriyor mu?
    belirsiz = (
        (ana.p < 0.05) != (kontrol.p < 0.05)
        or ana.trend != kontrol.trend
    )

    return {
        "durum": "ok",
        "n": n,
        "trend": ana.trend,
        "egim_10yil": float(sen.slope * 10),
       "ci_alt": float(ci_alt * 10),
       "ci_ust": float(ci_ust * 10),
       "n_etkin": float(n_etkin),
        "r1": float(r1),
        "p_mk": float(ana.p),
        "p_mk_kontrol": float(kontrol.p),
        "belirsiz": bool(belirsiz)
    }

