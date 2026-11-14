"""Sınır kayması: kar çizgisinin yıllar içinde kaç metre yükseldiği (KISI3_PLAN.md, Adım 6).

Sade anlatım: her kış, bölgedeki pikseller 100 m'lik rakım basamaklarına ayrılır ve her
basamağın tipik (medyan) kar örtüsü bulunur. Kar örtüsünün %50'yi geçtiği yükseklik o kışın
"kar çizgisi"dir. 24 kışlık kar çizgisi serisinin eğimi = gözlenen kayma (m/10 yıl).
Bu, Adım 5'teki "ısınma olsaydı ne kadar kaymalıydı" tahminiyle karşılaştırılıp etiketlenir.

Çıktı tipi ``boundary_shift`` (Kişi 4 ve 5 bu tipi ve alanları okuyor):
``observed_shift_m_per_decade``, ``predicted_shift_m_per_decade``, ``label``.

VARSAYIM: Kış kar örtüsü girdisi (kis, lat, lon) boyutlu, % biriminde (``winter_mean`` ya da
Kişi 2'nin ``winter_series`` çıktısı). Kış Y = Aralık Y−1 + Ocak–Mart Y.
"""

from __future__ import annotations

import numpy as np
import xarray as xr
from scipy.stats import linregress

from physics._gecici_trend import trend_1d
from physics.tests_physical import label

ALFA = 0.05
KAYAN_PENCERE = 15  # yıl; YALNIZCA görsel (p değerleri geçersiz)


def _ust_gecis(x: np.ndarray, y: np.ndarray, esik: float) -> float:
    """Rakım arttıkça y'nin eşiği ilk kez aşağıdan yukarı geçtiği x (doğrusal ara değer)."""
    for i in range(len(x) - 1):
        if y[i] < esik <= y[i + 1]:
            return float(x[i] + (esik - y[i]) * (x[i + 1] - x[i]) / (y[i + 1] - y[i]))
    return float("nan")


def snowline_series(kar_kis: xr.DataArray, rakim: xr.DataArray,
                    mask: xr.DataArray | None = None, dilim: float = 100.0,
                    esik: float = 50.0, min_pixels: int = 30) -> dict:
    """Her kış için kar çizgisi rakımı (m).

    Parametreler
    ----------
    kar_kis : DataArray (kis, lat, lon), % — kış ortalaması kar örtüsü.
    rakim : DataArray (lat, lon), m — aynı ızgarada (0,05°).
    mask : boolean DataArray, isteğe bağlı — bölge.
    dilim : rakım basamağı (m). esik : kar çizgisi eşiği (%). min_pixels : basamak başına en az piksel.

    Döndürür: ``{"kis": [...], "rakim_m": [...] (NaN = o kış %50 kesilmedi), "n_gecerli"}``.
    """
    kar = kar_kis.transpose("kis", "lat", "lon")
    rakim = rakim.transpose("lat", "lon")
    if not (np.array_equal(rakim.lat.values, kar.lat.values)
            and np.array_equal(rakim.lon.values, kar.lon.values)):
        raise ValueError("kar örtüsü ve rakım aynı ızgarada olmalı (lat/lon farklı)")
    z = rakim.values.astype(float)
    ok = np.isfinite(z)
    if mask is not None:
        ok &= np.asarray(mask.broadcast_like(rakim).transpose("lat", "lon").values, bool)
    zz = z[ok]
    kislar = [int(k) for k in kar["kis"].values]
    if zz.size == 0:
        return {"kis": kislar, "rakim_m": [float("nan")] * len(kislar), "n_gecerli": 0}

    z0 = np.floor(zz.min() / dilim) * dilim
    b = ((zz - z0) // dilim).astype(int)
    n_bin = int(b.max()) + 1
    merkez = z0 + dilim * (np.arange(n_bin) + 0.5)

    cizgi = []
    for i in range(len(kislar)):
        v = kar.values[i][ok]
        g = np.isfinite(v)
        med = np.full(n_bin, np.nan)
        for j in range(n_bin):
            sec = g & (b == j)
            if sec.sum() >= min_pixels:
                med[j] = np.median(v[sec])
        d = np.isfinite(med)
        cizgi.append(_ust_gecis(merkez[d], med[d], esik) if d.sum() >= 2 else float("nan"))
    return {"kis": kislar, "rakim_m": cizgi, "n_gecerli": int(np.sum(np.isfinite(cizgi)))}


def observed_shift(seri: dict) -> dict:
    """Kar çizgisi serisinin Sen eğimi (m/10 yıl), genişletilmiş aralık, MK ve t-testi p."""
    x = np.asarray(seri["kis"], float)
    y = np.asarray(seri["rakim_m"], float)
    tr = trend_1d(y, x)
    ok = np.isfinite(y)
    ttest_p = float(linregress(x[ok], y[ok]).pvalue) if ok.sum() >= 4 else float("nan")

    kayan = []
    if ok.sum() >= KAYAN_PENCERE:
        for s in range(len(x) - KAYAN_PENCERE + 1):
            w = slice(s, s + KAYAN_PENCERE)
            if np.isfinite(y[w]).sum() >= KAYAN_PENCERE - 2:
                t = trend_1d(y[w], x[w])
                kayan.append({"orta_kis": int(x[s + KAYAN_PENCERE // 2]),
                              "slope_m_per_decade": round(t["slope"], 1)})
    return {"slope": tr["slope"], "ci95": tr["ci95"], "mk_p": tr["mk_p"],
            "ttest_p": ttest_p, "n": tr["n"], "kayan_pencere": kayan}


def boundary_shift(kar_kis: xr.DataArray, rakim: xr.DataArray,
                   tahminler: list[dict] | None = None, mask: xr.DataArray | None = None,
                   region: str = "bolge", variable: str = "kar_ortusu", **kw) -> dict:
    """Gözlenen kar çizgisi kayması + iklim hızı tahmini + etiket → ``boundary_shift`` kaydı.

    tahminler : ``tests_physical.climate_velocity`` çıktıları; ilki ana ürün (MERRA-2),
        etiketi o belirler; diğerleri (GLDAS) ``predicted_secondary`` olarak yazılır.
    ``kw`` → ``snowline_series`` (dilim, esik, min_pixels).
    """
    seri = snowline_series(kar_kis, rakim, mask=mask, **kw)
    n_kis = len(seri["kis"])
    sonuc = {
        "id": f"kayma_rakim_{variable}_{region}",
        "type": "boundary_shift",
        "region": region,
        "variable": variable,
        "axis": "rakim",
        "observed_shift_m_per_decade": None,
        "predicted_shift_m_per_decade": None,
        "status": "ok",
        "snowline": {"kis": seri["kis"],
                     "rakim_m": [None if not np.isfinite(v) else round(v, 1)
                                 for v in seri["rakim_m"]]},
        "n_kis_gecerli": seri["n_gecerli"],
    }
    if seri["n_gecerli"] <= n_kis / 2:
        sonuc["status"] = "undefined"
        sonuc.update(label(None, None))
        sonuc["label_reason"] = (f"kar çizgisi tanımsız: {n_kis} kışın yalnız "
                                 f"{seri['n_gecerli']}'inde kar örtüsü %50'yi geçti")
        return sonuc

    g = observed_shift(seri)
    anlamli = bool(np.isfinite(g["mk_p"]) and g["mk_p"] < ALFA)
    sonuc.update({
        "observed_shift_m_per_decade": [round(v, 1) for v in g["ci95"]],
        "observed_slope_m_per_decade": round(g["slope"], 1),
        "mk_p": g["mk_p"],
        "ttest_p": g["ttest_p"],
        "rolling_15y": {"note": "yalnızca görsel; p değerleri geçersiz",
                        "seri": g["kayan_pencere"]},
    })

    if tahminler:
        ana = tahminler[0]
        sonuc["predicted_shift_m_per_decade"] = ana.get("predicted_shift_m_per_decade")
        sonuc["predicted_product"] = ana.get("product")
        sonuc["predicted_ref"] = ana.get("id")
        if len(tahminler) > 1:
            sonuc["predicted_secondary"] = [
                {"product": t.get("product"), "ref": t.get("id"),
                 "predicted_shift_m_per_decade": t.get("predicted_shift_m_per_decade")}
                for t in tahminler[1:]]
        sonuc.update(label(sonuc["observed_shift_m_per_decade"],
                           sonuc["predicted_shift_m_per_decade"], anlamli=anlamli, n=g["n"]))
    return sonuc
