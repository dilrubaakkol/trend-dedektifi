"""L4 için zaman serileri: mevsim, yıllık, mevsim anomalisi, aylık anomali (KISI3_PLAN.md, Faz 2).

Sade anlatım: aylık veriden her çiftin istediği seriyi üretir.
- Kış Y = Aralık (Y−1) + Ocak + Şubat (Y). Mart dahil değil (ekip kararı, 2026-11-14).
- İlkbahar = Mar–May, yaz = Haz–Ağu, sonbahar = Eyl–Kas, yıllık = Oca–Ara.
- Birikimli değişkenlerde (yağış, buharlaşma, akış) mevsim **toplamı**, ötekilerde **ortalaması** alınır.
- Mevsimin bir ayı eksikse o mevsim NaN olur (``min_ay`` ile gevşetilebilir; yalnız GRACE için).

Bütün fonksiyonlar ``time`` boyutlu her DataArray ile çalışır: tek seri (time) ya da küp
(time, lat, lon). Girdi aylık, damga ayın 1'i (docs/sozlesmeler.md, bölüm 1).

Not: ``physics/_gecici_trend.winter_mean`` eski Aralık–Mart tanımıyla rafa kalkan modüller için
duruyor; L4 bu dosyayı kullanır.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

MEVSIM_AYLARI = {
    "kis": (12, 1, 2),
    "ilkbahar": (3, 4, 5),
    "yaz": (6, 7, 8),
    "sonbahar": (9, 10, 11),
    "yillik": tuple(range(1, 13)),
}
# mevsim anomalisi dizilirken her mevsimin yıl içindeki yeri (zaman ekseni için)
MEVSIM_KONUMU = {"kis": 0.0, "ilkbahar": 0.25, "yaz": 0.5, "sonbahar": 0.75}
BIRIKIMLI = frozenset({"yagis", "buharlasma", "yuzey_akisi", "taban_akisi"})


def toplam_mi(degisken: str) -> bool:
    """Değişken birikimli mi (mevsim toplamı alınır) yoksa durum mu (ortalama alınır)?"""
    return degisken in BIRIKIMLI


def _aylik_kontrol(da: xr.DataArray) -> None:
    if "time" not in da.dims:
        raise ValueError("girdinin 'time' boyutu olmalı")
    t = pd.DatetimeIndex(da["time"].values)
    if len(t) > 1 and not (t.day == 1).all():
        raise ValueError("zaman damgası ayın 1'i olmalı (aylık veri)")


def mevsim_serisi(da: xr.DataArray, mevsim: str, toplam: bool = False,
                  min_ay: int | None = None) -> xr.DataArray:
    """Aylık veriden mevsim (ya da yıllık) serisi; yeni boyut ``yil``.

    Parametreler
    ----------
    da : DataArray (time, …) — aylık.
    mevsim : ``kis`` | ``ilkbahar`` | ``yaz`` | ``sonbahar`` | ``yillik``.
    toplam : True ise ayların toplamı (birikimli değişkenler), değilse ortalaması.
    min_ay : geçerli sayılmak için gereken en az ay (varsayılan: mevsimin tüm ayları).
        Toplamda eksik ay toplamı küçülteceği için ``toplam=True`` iken her zaman tüm aylar istenir.

    Kış Y'nin Aralık'ı Y−1 yılından gelir; bu yüzden ilk yılın kışı (Aralık yoksa) NaN olur.
    """
    if mevsim not in MEVSIM_AYLARI:
        raise ValueError(f"bilinmeyen mevsim: {mevsim}")
    _aylik_kontrol(da)
    aylar = MEVSIM_AYLARI[mevsim]
    gereken = len(aylar) if (min_ay is None or toplam) else int(min_ay)

    ay = da["time"].dt.month
    sec = da.where(ay.isin(aylar), drop=True)
    yil = sec["time"].dt.year + ((sec["time"].dt.month == 12) & (mevsim == "kis"))
    yil = yil.rename("yil")

    sayi = sec.notnull().groupby(yil).sum("time")
    deger = sec.groupby(yil).sum("time", skipna=True) if toplam else sec.groupby(yil).mean("time", skipna=True)
    out = deger.where(sayi >= gereken)
    out.attrs = dict(da.attrs)
    out.attrs["seri"] = f"{mevsim}_{'toplam' if toplam else 'ortalama'}"
    return out


def mevsim_anomali(da: xr.DataArray, toplam: bool = False) -> xr.DataArray:
    """Dört mevsim art arda dizilir, her mevsimden kendi uzun dönem ortalaması çıkarılır.

    Yeni boyut ``t`` (ondalık yıl: kış Y = Y,00; ilkbahar = Y,25; yaz = Y,50; sonbahar = Y,75)
    ve yardımcı koordinat ``mevsim``.
    """
    parcalar = []
    for m, konum in MEVSIM_KONUMU.items():
        s = mevsim_serisi(da, m, toplam=toplam)
        s = s - s.mean("yil", skipna=True)
        s = s.assign_coords(t=("yil", s["yil"].values + konum),
                            mevsim=("yil", [m] * s.sizes["yil"]))
        parcalar.append(s.swap_dims(yil="t").drop_vars("yil"))
    out = xr.concat(parcalar, dim="t").sortby("t")
    out.attrs = dict(da.attrs)
    out.attrs["seri"] = "mevsim_anomali"
    return out


def aylik_anomali(da: xr.DataArray) -> xr.DataArray:
    """Her aydan o ayın uzun dönem ortalaması (12 aylık klimatoloji) çıkarılır."""
    _aylik_kontrol(da)
    klim = da.groupby("time.month").mean("time", skipna=True)
    out = (da.groupby("time.month") - klim).drop_vars("month", errors="ignore")
    out.attrs = dict(da.attrs)
    out.attrs["seri"] = "aylik_anomali"
    return out


def gecikmeli(x: xr.DataArray, y: xr.DataArray, gecikme: int,
              aylar: tuple[int, ...] = (4, 5, 6, 7, 8, 9)) -> tuple[xr.DataArray, xr.DataArray]:
    """y'nin ``aylar`` içindeki her ayını x'in ``gecikme`` ay önceki değeriyle eşler.

    Ör. gecikme 1: Mayıs NDVI ↔ Nisan toprak nemi. Seçilmeyen aylar NaN kalır (silinmez); böylece
    otokorelasyon yalnız gerçekten ardışık aylardan hesaplanır.
    İki girdi de aynı, kesintisiz aylık zaman eksenine hizalanmış olmalı.
    """
    x, y = xr.align(x, y, join="inner")
    t = pd.DatetimeIndex(x["time"].values)
    if len(t) > 1:
        beklenen = pd.date_range(t[0], t[-1], freq="MS")
        if len(beklenen) != len(t):
            raise ValueError("gecikme için zaman ekseni kesintisiz aylık olmalı")
    xg = x.shift(time=gecikme)
    secili = y["time"].dt.month.isin(aylar)
    return xg.where(secili), y.where(secili)


def kar_maskesi(kar_kis: xr.DataArray, esik: float = 10.0) -> xr.DataArray:
    """Çift 1 kapsamı: kış ortalaması kar örtüsü ≥ ``esik`` (%) olan hücreler (lat, lon)."""
    return kar_kis.mean("yil", skipna=True) >= esik


def alan_ortalamasi(da: xr.DataArray, mask: xr.DataArray | None = None) -> xr.DataArray:
    """cos(enlem) ağırlıklı alan ortalaması; NaN hücreler atlanır, ``mask`` False olanlar dışarıda."""
    if mask is not None:
        da = da.where(mask.broadcast_like(da.isel(time=0, drop=True) if "time" in da.dims else da))
    w = np.cos(np.deg2rad(da["lat"]))
    return da.weighted(w.fillna(0)).mean(("lat", "lon"), skipna=True).where(
        da.notnull().any(("lat", "lon")))
