"""Fiziksel testler: hipotezden türetilen tahmini gözlemle karşılaştırıp etiket verir.

Sade anlatım: "Isınma sorumluysa ne görmeliydik?" sorusunu sayıya döker ve gözlenenle
karşılaştırır. Örnek: hava 10 yılda 0,4 °C ısındıysa ve yükseldikçe km başına 6 °C soğuyorsa,
kar çizgisi 10 yılda ~67 m yükselmeliydi.

İçerik
- ``label()``          : tüm testlerin ortak etiket kuralı (uyumlu / celiskili / yetersiz)
- ``climate_velocity()``: iklim hızı → beklenen kar çizgisi kayması (Adım 5)
- ``water_budget()``, ``clausius_clapeyron()``: Adım 7'de eklenecek.

VARSAYIMLAR (sonuç notuna da yazılır)
- Model sıcaklıkları modelin yumuşatılmış rakımına göredir; dT/dz için SRTM 0,25° ortalaması
  kullanılır.
- dT/dz regresyonunun aralığı sıradan EKK aralığıdır; komşu hücrelerin bağımlılığı yüzünden
  gerçekte daha geniş olabilir. Tahmin aralığına hâkim olan dT/dt belirsizliğidir.
"""

from __future__ import annotations

import numpy as np
import xarray as xr

from physics._gecici_trend import trend_1d

ETIKETLER = ("uyumlu", "celiskili", "yetersiz")
Z_95 = 1.959964


# --------------------------------------------------------------------------- etiket kuralı
def _aralik_gecerli(a) -> bool:
    return a is not None and len(a) == 2 and all(np.isfinite(a))


def label(gozlenen_ci, tahmin_ci, anlamli: bool = True, n: int | None = None,
          n_min: int = 10, max_genislik: float | None = None) -> dict:
    """Ortak etiket kuralı (KISI3_PLAN.md, Adım 5) — öncelik sırasıyla:

    1. ``yetersiz``: gözlenen trend anlamlı değil, veri kısa (n < n_min), aralık eksik ya da
       gözlenen aralık ``max_genislik``'ten geniş.
    2. ``celiskili``: işaret ters (gözlenen aralığın tamamı tahminin ters işaretinde) ya da
       gözlenen aralık tahmin aralığıyla hiç örtüşmüyor.
    3. ``uyumlu``: aralıklar örtüşüyor.

    Döndürür: ``{"label": ..., "label_reason": ...}``.
    """
    if not (_aralik_gecerli(gozlenen_ci) and _aralik_gecerli(tahmin_ci)):
        return {"label": "yetersiz", "label_reason": "aralık hesaplanamadı"}
    g_lo, g_hi = sorted(map(float, gozlenen_ci))
    t_lo, t_hi = sorted(map(float, tahmin_ci))
    if n is not None and n < n_min:
        return {"label": "yetersiz", "label_reason": f"veri kısa (n={n} < {n_min})"}
    if not anlamli:
        return {"label": "yetersiz", "label_reason": "gözlenen trend istatistiksel olarak anlamlı değil"}
    if max_genislik is not None and (g_hi - g_lo) > max_genislik:
        return {"label": "yetersiz",
                "label_reason": f"gözlenen aralık çok geniş ({g_hi - g_lo:.3g} > {max_genislik:.3g})"}
    t_isaret = np.sign(t_lo) if np.sign(t_lo) == np.sign(t_hi) else 0.0
    if t_isaret != 0 and ((t_isaret > 0 and g_hi < 0) or (t_isaret < 0 and g_lo > 0)):
        return {"label": "celiskili", "label_reason": "gözlenen değişim beklenenin ters yönünde"}
    if g_hi < t_lo or g_lo > t_hi:
        return {"label": "celiskili", "label_reason": "gözlenen aralık tahmin aralığıyla örtüşmüyor"}
    return {"label": "uyumlu", "label_reason": "gözlenen ve tahmin aralıkları örtüşüyor"}


# --------------------------------------------------------------------------- yardımcılar
def _alan_ortalamasi(da: xr.DataArray) -> xr.DataArray:
    """cos(enlem) ağırlıklı alan ortalaması (NaN hücreler atlanır)."""
    w = np.cos(np.deg2rad(da.lat))
    return da.weighted(w.fillna(0)).mean(("lat", "lon"))


def _bolune_cek(merkez, lo, hi, n, rng):
    """Asimetrik %95 aralıktan iki yarım normal ile örnek çeker."""
    s_lo, s_hi = (merkez - lo) / Z_95, (hi - merkez) / Z_95
    z = rng.standard_normal(n)
    return merkez + np.where(z < 0, z * s_lo, z * s_hi)


def lapse_rate(t_ort: xr.DataArray, rakim: xr.DataArray, mask: xr.DataArray | None = None) -> dict:
    """Bölge içinde ``T ~ rakım + enlem + boylam`` EKK regresyonunun rakım katsayısı.

    Döndürür: ``{"dTdz_C_per_km", "ci95", "n_cells", "r2"}``. 6,5 °C/km varsayılmaz, ölçülür.
    """
    import statsmodels.api as sm
    if not (np.array_equal(rakim.lat.values, t_ort.lat.values)
            and np.array_equal(rakim.lon.values, t_ort.lon.values)):
        raise ValueError("sıcaklık ve rakım aynı ızgarada olmalı (0,25°)")
    t_ort = t_ort.transpose("lat", "lon")
    rakim = rakim.transpose("lat", "lon")
    LON, LAT = np.meshgrid(t_ort.lon.values, t_ort.lat.values)
    y, z = t_ort.values, rakim.values
    ok = np.isfinite(y) & np.isfinite(z)
    if mask is not None:
        ok &= np.asarray(mask.broadcast_like(t_ort).transpose("lat", "lon").values, bool)
    nan = float("nan")
    if ok.sum() < 10:
        return {"dTdz_C_per_km": nan, "ci95": [nan, nan], "n_cells": int(ok.sum()), "r2": nan}
    X = sm.add_constant(np.c_[z[ok] / 1000.0, LAT[ok], LON[ok]])
    fit = sm.OLS(y[ok], X).fit()
    lo, hi = fit.conf_int(0.05)[1]
    return {"dTdz_C_per_km": float(fit.params[1]), "ci95": [float(lo), float(hi)],
            "n_cells": int(ok.sum()), "r2": float(fit.rsquared)}


# --------------------------------------------------------------------------- iklim hızı
def climate_velocity(sicaklik_kis: xr.DataArray, rakim: xr.DataArray,
                     mask: xr.DataArray | None = None, region: str = "bolge",
                     urun: str = "MERRA2", gozlenen: dict | None = None,
                     n_mc: int = 1000, seed: int = 0) -> dict:
    """Isınma sorumluysa kar çizgisinin beklenen yükselme hızı (m/10 yıl) ve isteğe bağlı etiket.

    tahmin = dT/dt ÷ |dT/dz|

    Parametreler
    ----------
    sicaklik_kis : DataArray (kis, lat, lon), °C — kış ortalaması sıcaklık
        (``_gecici_trend.winter_mean`` ya da Kişi 2'nin ``winter_series`` çıktısı), 0,25°.
    rakim : DataArray (lat, lon), m — aynı 0,25° ızgarada.
    mask : boolean DataArray, isteğe bağlı — bölge.
    urun : sıcaklık ürünü kodu (MERRA2 ana, GLDAS ikincil); ``id``'ye girer.
    gozlenen : isteğe bağlı gözlenen kayma (Adım 6): ``{"ci95": [lo, hi], "anlamli": bool,
        "n": int}``. Verilirse ``observed_shift_m_per_decade`` ve ``label`` eklenir.
    n_mc : Monte Carlo çekiliş sayısı (plan: 1000).

    Döndürür
    -------
    dict, ``type: "climate_velocity"`` — ``predicted_shift_m_per_decade`` (%95), bileşenler,
    varsayım notu; ``gozlenen`` verilirse ``label`` ve ``label_reason``.
    """
    s = sicaklik_kis.transpose("kis", "lat", "lon")
    if mask is not None:
        s = s.where(mask.broadcast_like(s.isel(kis=0)))
    seri = _alan_ortalamasi(s)
    tr = trend_1d(seri.values, seri["kis"].values)  # °C / 10 yıl
    lr = lapse_rate(s.mean("kis"), rakim, mask)

    sonuc = {
        "id": f"iklim_hizi_kar_cizgisi_{urun}_{region}",
        "type": "climate_velocity",
        "region": region,
        "axis": "rakim",
        "product": urun,
        "dTdt_C_per_decade": round(tr["slope"], 4) if np.isfinite(tr["slope"]) else None,
        "dTdt_ci95": [round(v, 4) for v in tr["ci95"]],
        "dTdt_mk_p": tr["mk_p"],
        "dTdz_C_per_km": round(lr["dTdz_C_per_km"], 3) if np.isfinite(lr["dTdz_C_per_km"]) else None,
        "dTdz_ci95": [round(v, 3) for v in lr["ci95"]],
        "dTdz_n_cells": lr["n_cells"],
        "n_kis": tr["n"],
        "predicted_shift_m_per_decade": None,
        "note": ("dT/dz SRTM 0,25° ortalama rakımıyla ölçüldü (model kendi yumuşatılmış rakımını "
                 "kullanır); dT/dz aralığı komşu hücre bağımlılığını içermez."),
    }

    gecerli = (np.isfinite(tr["slope"]) and _aralik_gecerli(tr["ci95"])
               and np.isfinite(lr["dTdz_C_per_km"]) and _aralik_gecerli(lr["ci95"]))
    if gecerli and lr["ci95"][1] >= 0:
        sonuc["note"] += " UYARI: sıcaklık rakımla azalmıyor (dT/dz ≥ 0 olabilir); tahmin anlamsız."
        gecerli = False

    if gecerli:
        rng = np.random.default_rng(seed)
        dtdt = _bolune_cek(tr["slope"], *tr["ci95"], n_mc, rng)                 # °C/10 yıl
        dtdz = _bolune_cek(lr["dTdz_C_per_km"], *lr["ci95"], n_mc, rng)        # °C/km
        dtdz = np.minimum(dtdz, -1e-3)                                          # işaret koruması
        v = dtdt / np.abs(dtdz) * 1000.0                                        # m/10 yıl
        lo, med, hi = np.percentile(v, [2.5, 50, 97.5])
        sonuc["predicted_shift_m_per_decade"] = [round(float(lo), 1), round(float(hi), 1)]
        sonuc["predicted_median_m_per_decade"] = round(float(med), 1)

    if gozlenen is not None:
        sonuc["observed_shift_m_per_decade"] = gozlenen.get("ci95")
        sonuc.update(label(gozlenen.get("ci95"), sonuc["predicted_shift_m_per_decade"],
                           anlamli=gozlenen.get("anlamli", True), n=gozlenen.get("n")))
    return sonuc
