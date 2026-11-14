"""L4 hücre haritaları: her 0,25° hücrede ilişki, FDR ve etiket (KISI3_PLAN.md, Faz 3).

Sade anlatım: Faz 1'deki hesabın (trend çıkar → korelasyon → etkin n → p → etiket) haritanın her
hücresinde aynı anda yapılır. Sonra binlerce hücre birden test edildiği için şans eseri "anlamlı"
çıkanlar Benjamini-Hochberg ile ayıklanır (α_FDR = 0,10, yalnız geçerli kara hücreleri üzerinden).

Çıktı biçimi: docs/sozlesmeler.md 2.3, ``L4_iliski/iliski__<d1>__<d2>.nc``.
Sonuçlar ``iliski.iliski_1d`` ile hücre hücre aynıdır (testte doğrulanır).
"""

from __future__ import annotations

import warnings

import numpy as np
import xarray as xr
from scipy import stats

from physics.ciftler import CIFT, Cift, cift_serileri
from physics.iliski import ALFA_FDR, bh_fdr

ETIKET_KODU = {"beklenen_yonde": 1, "ters_yonde": -1, "anlamsiz": 0}
ETIKET_YOK = -99


def _trend_cikar(v: np.ndarray, t: np.ndarray, ok: np.ndarray) -> np.ndarray:
    """(zaman, hücre) dizisinde her hücreden, yalnız ``ok`` adımlarıyla EKK doğrusunu çıkarır."""
    k = ok.sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        tt = np.where(ok, t[:, None], 0.0)
        vv = np.where(ok, v, 0.0)
        tm = tt.sum(0) / k
        vm = vv.sum(0) / k
        dt = np.where(ok, t[:, None] - tm, 0.0)
        egim = (dt * np.where(ok, v - vm, 0.0)).sum(0) / (dt * dt).sum(0)
        return np.where(ok, v - vm - egim * dt, np.nan)


def _gecikme1(d: np.ndarray, kucuk_orneklem_duzeltmesi: bool) -> np.ndarray:
    """(zaman, hücre) artıklarının gecikme-1 otokorelasyonu (``iliski.gecikme1`` ile aynı tanım)."""
    n = np.isfinite(d).sum(0)
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # deniz hücreleri: boş dilim
        m = np.nanmean(d, 0)
        z = d - m
        pay = np.nansum(z[1:] * z[:-1], 0)       # yalnız iki ucu da geçerli çiftler
        payda = np.nansum(z * z, 0)
        r1 = np.where(payda > 0, pay / payda, 0.0)
        if kucuk_orneklem_duzeltmesi:
            r1 = r1 + (1 + 4 * r1) / n
    return np.clip(r1, -0.99, 0.99)


def iliski_harita(x: xr.DataArray, y: xr.DataArray, t, beklenen: int,
                  alfa_fdr: float = ALFA_FDR, min_n: int = 8,
                  kucuk_orneklem_duzeltmesi: bool = True) -> xr.Dataset:
    """Her hücrede trendi çıkarılmış korelasyon, etkin n, p, FDR ve etiket.

    Parametreler
    ----------
    x, y : DataArray (zaman, lat, lon); ilk boyut zaman (``ciftler.cift_serileri`` çıktısı).
    t : sayısal zaman (yıl), uzunluğu ilk boyutla aynı.
    beklenen : +1 ya da −1.
    alfa_fdr : BH eşiği; ``anlamli = p_fdr ≤ alfa_fdr``.

    Döndürür: Dataset (lat, lon) — ``r``, ``etkin_n``, ``p``, ``p_fdr`` (float32),
    ``anlamli`` (int8: 1/0/−1), ``etiket`` (int8: 1 beklenen_yonde, −1 ters_yonde, 0 anlamsiz,
    −99 maskeli ya da hesaplanamadı).
    """
    if beklenen not in (1, -1):
        raise ValueError("beklenen +1 ya da -1 olmalı")
    zb = x.dims[0]
    x, y = xr.align(x, y, join="exact")
    x = x.transpose(zb, "lat", "lon")
    y = y.transpose(zb, "lat", "lon")
    nt, ny, nx = x.shape
    t = np.asarray(t, float)
    if t.shape != (nt,):
        raise ValueError("t uzunluğu zaman boyutuyla aynı olmalı")

    X = x.values.reshape(nt, -1).astype(float)
    Y = y.values.reshape(nt, -1).astype(float)
    ok = np.isfinite(X) & np.isfinite(Y)
    n = ok.sum(0)

    xa = _trend_cikar(X, t, ok)
    ya = _trend_cikar(Y, t, ok)
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # deniz hücreleri: boş dilim
        sx = np.sqrt(np.nansum(xa * xa, 0))
        sy = np.sqrt(np.nansum(ya * ya, 0))
        r = np.nansum(xa * ya, 0) / (sx * sy)
        # sabit seri: trend çıkınca yalnız yuvarlama artığı kalır (iliski_1d ile aynı ölçüt)
        olc_x = 1e-9 * (1.0 + np.nanmax(np.where(ok, np.abs(X), np.nan), 0)) * np.sqrt(n)
        olc_y = 1e-9 * (1.0 + np.nanmax(np.where(ok, np.abs(Y), np.nan), 0)) * np.sqrt(n)
    gecerli = (n >= min_n) & (sx > olc_x) & (sy > olc_y)

    a = _gecikme1(xa, kucuk_orneklem_duzeltmesi)
    b = _gecikme1(ya, kucuk_orneklem_duzeltmesi)
    rr = a * b
    with np.errstate(invalid="ignore", divide="ignore"):
        ne = np.clip(n * (1 - rr) / (1 + rr), 3.0, np.maximum(n, 3))
        rc = np.clip(r, -0.999999, 0.999999)
        tstat = rc * np.sqrt((ne - 2) / (1 - rc * rc))
        p = 2 * stats.t.sf(np.abs(tstat), ne - 2)
    r = np.where(gecerli, r, np.nan)
    ne = np.where(gecerli, ne, np.nan)
    p = np.where(gecerli, p, np.nan)
    q = bh_fdr(p)

    anlamli = np.where(np.isfinite(q), (q <= alfa_fdr).astype(np.int8), -1).astype(np.int8)
    etiket = np.full(r.shape, ETIKET_YOK, np.int8)
    etiket[anlamli == 0] = ETIKET_KODU["anlamsiz"]
    ayni = np.sign(r) == np.sign(beklenen)
    etiket[(anlamli == 1) & ayni] = ETIKET_KODU["beklenen_yonde"]
    etiket[(anlamli == 1) & ~ayni] = ETIKET_KODU["ters_yonde"]

    sekil = (ny, nx)
    k = {"coords": {"lat": x["lat"].values, "lon": x["lon"].values}, "dims": ("lat", "lon")}
    ds = xr.Dataset({
        "r": xr.DataArray(r.reshape(sekil).astype(np.float32), **k,
                          attrs={"long_name": "trendi giderilmiş seriler arasındaki Pearson korelasyonu"}),
        "etkin_n": xr.DataArray(ne.reshape(sekil).astype(np.float32), **k,
                                attrs={"long_name": "etkin örneklem (Bretherton vd. 1999)"}),
        "p": xr.DataArray(p.reshape(sekil).astype(np.float32), **k,
                          attrs={"long_name": "iki yönlü p (t testi, etkin_n − 2 serbestlik)"}),
        "p_fdr": xr.DataArray(q.reshape(sekil).astype(np.float32), **k,
                              attrs={"long_name": "Benjamini-Hochberg düzeltilmiş p"}),
        "anlamli": xr.DataArray(anlamli.reshape(sekil), **k,
                                attrs={"long_name": "1 = p_fdr <= alfa_fdr, 0 = değil, -1 = maskeli"}),
        "etiket": xr.DataArray(etiket.reshape(sekil), **k, attrs={
            "long_name": "fizik kontrolü etiketi",
            "flag_values": np.array([1, -1, 0, ETIKET_YOK], np.int8),
            "flag_meanings": "beklenen_yonde ters_yonde anlamsiz maskeli_ya_da_hesaplanamadi"}),
    })
    ds.attrs.update({"alfa_fdr": alfa_fdr, "beklenen_yon": "+" if beklenen > 0 else "-",
                     "fdr_hucre_sayisi": int(np.isfinite(p).sum())})
    return ds


def cift_haritasi(cift: Cift | int, a: xr.DataArray, b: xr.DataArray,
                  alfa_fdr: float = ALFA_FDR) -> list[tuple[str, xr.Dataset]]:
    """Bir çiftin aylık küplerinden harita(lar): ``[(dosya_adi, Dataset), ...]``.

    a, b : (time, lat, lon) aylık L1 küpleri — sırasıyla ``cift.d1`` ve ``cift.d2``.
    Çift 4 (GRACE) için harita üretilmez (ValueError).
    """
    c = CIFT[cift] if isinstance(cift, int) else cift
    if not c.harita:
        raise ValueError(f"çift {c.no} için hücre haritası üretilmez (yalnız bölge ölçeği)")
    out = []
    for s in cift_serileri(c, a, b):
        ds = iliski_harita(s["x"], s["y"], s["t"], c.beklenen, alfa_fdr=alfa_fdr)
        ds.attrs.update({"cift": c.kod, "cift_no": c.no, "seri": c.seri,
                         "gecikme_ay": s["gecikme"], "donem": s["donem"], "kademe": c.kademe})
        if c.not_:
            ds.attrs["not"] = c.not_
        out.append((c.harita_dosyasi(s["gecikme"]), ds))
    return out


def etiket_ozeti(ds: xr.Dataset) -> dict:
    """Haritadaki etiketlerin hücre sayıları (site ve kontrol için)."""
    e = ds["etiket"].values
    return {ad: int((e == kod).sum()) for ad, kod in ETIKET_KODU.items()} | {
        "hesaplanamadi": int((e == ETIKET_YOK).sum())}
