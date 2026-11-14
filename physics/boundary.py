# YOL HARİTASI (2026-11-14): v0.1 kapsamında kullanılmıyor (bkz. physics/KISI3_PLAN.md, bölüm 2).
# Kod ve testleri ileride kullanılmak üzere duruyor; silmeyin.
"""İşaret değiştiren sınır: bir eksen (rakım, enlem, boylam) boyunca trendin yön değiştirdiği yer.

Sade anlatım: pikseller eksen boyunca dilimlere ayrılır (ör. 100 m'lik rakım basamakları), her
dilimde trendin medyanı alınır, bu eğri yumuşatılır ve sıfırı kestiği nokta "sınır" olur
(ör. "2650 m altında kar azalıyor, üstünde artıyor"). Belirsizlik, 0,5°'lik blokları yerine
koyarak yeniden örnekleyen blok bootstrap ile bulunur.

Fonksiyonlar hiçbir bölgeyi koda gömmez: bölge, ``mask`` (ya da önceden ``data.subset`` ile
kesilmiş veri) olarak verilir. Türkiye geneli ve 7 bölge için aynı fonksiyon çağrılır.

Algoritma: KISI3_PLAN.md, Adım 3. Çıktı tipi ``boundary`` (Kişi 5 arayüzü bu tipi okur); kayma ayrı ``boundary_shift`` kaydıdır.
"""

from __future__ import annotations

import numpy as np
import xarray as xr
from statsmodels.nonparametric.smoothers_lowess import lowess

EKSENLER = ("rakim", "enlem", "boylam")


def _eksen_degerleri(trend: xr.DataArray, axis: str, rakim: xr.DataArray | None) -> np.ndarray:
    """Trend ızgarasındaki her hücre için eksen değeri (2B dizi)."""
    if axis == "rakim":
        if rakim is None:
            raise ValueError("axis='rakim' için rakim DataArray'i gerekli")
        if not (np.array_equal(rakim.lat.values, trend.lat.values)
                and np.array_equal(rakim.lon.values, trend.lon.values)):
            raise ValueError("rakim ve trend aynı ızgarada olmalı (lat/lon farklı)")
        return rakim.values.astype(float)
    LON, LAT = np.meshgrid(trend.lon.values, trend.lat.values)
    if axis == "enlem":
        return LAT
    if axis == "boylam":
        return LON
    raise ValueError(f"Bilinmeyen eksen: {axis}. Seçenekler: {EKSENLER}")


def _varsayilan_dilim(axis: str, res: float) -> float:
    """Plan: rakım 0,05°'de 100 m, 0,25°'de 200 m; enlem/boylam 0,25°."""
    if axis == "rakim":
        return 100.0 if res <= 0.06 else 200.0
    return 0.25


def _dilim_medyanlari(b: np.ndarray, v: np.ndarray, n_bin: int, min_pixels: int):
    """Dilim indeksi b ve değer v için (medyanlar, sayılar); az pikselli dilim NaN."""
    order = np.lexsort((v, b))
    bs, vs = b[order], v[order]
    counts = np.bincount(bs, minlength=n_bin)
    start = np.concatenate(([0], np.cumsum(counts)[:-1]))
    med = np.full(n_bin, np.nan)
    ok = counts >= min_pixels
    lo = start[ok] + (counts[ok] - 1) // 2
    hi = start[ok] + counts[ok] // 2
    med[ok] = 0.5 * (vs[lo] + vs[hi])
    return med, counts


def _kesisimler(x: np.ndarray, y: np.ndarray) -> list[float]:
    """y eğrisinin sıfırı kestiği x değerleri (doğrusal ara değer)."""
    out = []
    for i in range(len(x) - 1):
        y0, y1 = y[i], y[i + 1]
        if y0 == 0:
            out.append(float(x[i]))
        elif y0 * y1 < 0:
            out.append(float(x[i] - y0 * (x[i + 1] - x[i]) / (y1 - y0)))
    if len(y) and y[-1] == 0:
        out.append(float(x[-1]))
    return sorted(set(out))


def _ayrisma_skoru(x: np.ndarray, med: np.ndarray, c: float) -> float:
    """Kesişim c'nin altı bir işarete, üstü ters işarete ne kadar iyi ayrılıyor (0–1)."""
    alt, ust = med[x < c], med[x > c]
    if alt.size == 0 or ust.size == 0:
        return 0.0
    s1 = (np.sum(alt > 0) + np.sum(ust < 0)) / med.size
    s2 = (np.sum(alt < 0) + np.sum(ust > 0)) / med.size
    return float(max(s1, s2))


def _sinir_bul(x: np.ndarray, med: np.ndarray, span_bins: int):
    """Geçerli dilimlerde LOWESS + kesişimler + ana sınır. (ana, kesişimler, yumuşak eğri)."""
    ok = np.isfinite(med)
    x, med = x[ok], med[ok]
    if x.size < 5:
        return None, [], x, med, np.full_like(med, np.nan)
    frac = min(1.0, span_bins / x.size)
    smooth = lowess(med, x, frac=frac, it=1, return_sorted=False)
    cs = _kesisimler(x, smooth)
    if not cs:
        return None, [], x, med, smooth
    ana = max(cs, key=lambda c: _ayrisma_skoru(x, med, c))
    return ana, cs, x, med, smooth


def find_boundary(trend: xr.DataArray, axis: str = "rakim", rakim: xr.DataArray | None = None,
                  mask: xr.DataArray | None = None, region: str = "bolge",
                  variable: str = "kar_ortusu", dilim: float | None = None,
                  min_pixels: int = 30, span_bins: int = 7, n_boot: int = 1000,
                  blok_derece: float = 0.5, kayip_esigi: float = 0.2,
                  seed: int = 0) -> dict:
    """Trend haritasında eksen boyunca işaret değiştiren sınırı ve %95 aralığını bulur.

    Parametreler
    ----------
    trend : DataArray (lat, lon)
        Piksel başına trend (ör. Sen eğimi, %/10 yıl). NaN'lar atılır.
    axis : "rakim" | "enlem" | "boylam"
    rakim : DataArray (lat, lon), axis="rakim" ise gerekli, trend ile aynı ızgarada.
    mask : boolean DataArray (lat, lon), isteğe bağlı. True = bölgenin içi.
    region, variable : sonuç kaydının ``id``'si ve alanları için.
    dilim : dilim genişliği; None → plandaki varsayılan.
    min_pixels : bundan az pikselli dilim atılır (plan: 30).
    span_bins : LOWESS penceresi, dilim sayısı cinsinden.
    n_boot, blok_derece : blok bootstrap ayarları (plan: 1000, 0,5°).
    kayip_esigi : bootstrap'lerin bu oranından fazlasında kesişim yoksa ``uncertain``.

    Döndürür
    -------
    dict, ``type: "boundary"``. ``status``: ``ok`` / ``uncertain`` /
    ``no_boundary``.
    """
    trend = trend.transpose("lat", "lon")
    rakim = rakim.transpose("lat", "lon") if rakim is not None else None
    mask = mask.broadcast_like(trend).transpose("lat", "lon") if mask is not None else None
    ax2d = _eksen_degerleri(trend, axis, rakim)
    v2d = trend.values.astype(float)
    gecerli = np.isfinite(v2d) & np.isfinite(ax2d)
    if mask is not None:
        gecerli &= np.asarray(mask.values, dtype=bool)

    lat = trend.lat.values
    lon = trend.lon.values
    res = float(abs(lat[1] - lat[0])) if lat.size > 1 else 0.25
    w = float(dilim) if dilim is not None else _varsayilan_dilim(axis, res)
    birim = "m" if axis == "rakim" else "deg"

    LON, LAT = np.meshgrid(lon, lat)
    v = v2d[gecerli]
    a = ax2d[gecerli]
    sonuc = {
        "id": f"sinir_{axis}_{variable}_{region}",
        "type": "boundary",
        "region": region,
        "variable": variable,
        "axis": axis,
        f"boundary_{birim}": None,
        f"boundary_ci95_{birim}": None,
        f"crossings_{birim}": [],
        "status": "no_boundary",
        "n_pixels": int(v.size),
        "bootstrap": {"n_boot": n_boot, "blok_derece": blok_derece, "kayip_orani": None},
        "curve": {f"x_{birim}": [], "median_trend": [], "smoothed": [], "n_pixels": []},
    }
    if v.size == 0:
        sonuc["note"] = "bölgede geçerli piksel yok"
        return sonuc

    a0 = np.floor(a.min() / w) * w
    b = ((a - a0) // w).astype(int)
    n_bin = int(b.max()) + 1
    merkez = a0 + w * (np.arange(n_bin) + 0.5)

    med, counts = _dilim_medyanlari(b, v, n_bin, min_pixels)
    ana, cs, x_ok, med_ok, smooth = _sinir_bul(merkez, med, span_bins)
    ok = np.isfinite(med)
    sonuc["curve"] = {
        f"x_{birim}": [round(float(t), 4) for t in x_ok],
        "median_trend": [float(t) for t in med_ok],
        "smoothed": [float(t) for t in smooth],
        "n_pixels": [int(t) for t in counts[ok]],
    }
    if ana is None:
        if x_ok.size < 5:
            sonuc["note"] = f"{min_pixels}+ pikselli dilim sayısı 5'ten az"
        return sonuc
    sonuc[f"boundary_{birim}"] = round(ana, 4)
    sonuc[f"crossings_{birim}"] = [round(c, 4) for c in cs]

    # Blok bootstrap: bloklar yerine koyarak çekilir, her seferinde sınır yeniden bulunur.
    blat = np.floor((LAT[gecerli] - lat.min()) / blok_derece).astype(int)
    blon = np.floor((LON[gecerli] - lon.min()) / blok_derece).astype(int)
    _, blok = np.unique(blat * 100000 + blon, return_inverse=True)
    order = np.argsort(blok, kind="stable")
    bsay = np.bincount(blok)
    bbas = np.concatenate(([0], np.cumsum(bsay)[:-1]))
    n_blok = bsay.size

    rng = np.random.default_rng(seed)
    boots = np.full(n_boot, np.nan)
    for k in range(n_boot):
        sec = rng.integers(0, n_blok, n_blok)
        idx = order[np.concatenate([np.arange(bbas[j], bbas[j] + bsay[j]) for j in sec])]
        mk, _ = _dilim_medyanlari(b[idx], v[idx], n_bin, min_pixels)
        bk, _, _, _, _ = _sinir_bul(merkez, mk, span_bins)
        if bk is not None:
            boots[k] = bk

    kayip = float(np.mean(np.isnan(boots)))
    sonuc["bootstrap"]["kayip_orani"] = round(kayip, 3)
    if np.sum(np.isfinite(boots)) >= 2:
        lo, hi = np.nanpercentile(boots, [2.5, 97.5])
        sonuc[f"boundary_ci95_{birim}"] = [round(float(lo), 4), round(float(hi), 4)]
    sonuc["status"] = "uncertain" if kayip > kayip_esigi else "ok"
    if len(cs) > 1:
        sonuc["note"] = f"{len(cs)} kesişim bulundu; ana sınır en iyi ayıranı"
    return sonuc


TURKIYE_BOLGELERI = ("turkiye", "marmara", "ege", "akdeniz", "ic_anadolu", "karadeniz",
                     "dogu_anadolu", "guneydogu_anadolu")


def find_boundaries(trend: xr.DataArray, rakim: xr.DataArray | None = None,
                    bolgeler=TURKIYE_BOLGELERI, axis: str = "rakim", **kw) -> list[dict]:
    """``find_boundary``'yi her bölge için ayrı çalıştırır (Türkiye geneli + 7 bölge).

    Bölge kesme işi Kişi 1'in ``data.subset`` fonksiyonuyla yapılır; bölge adları
    ``data.regions.list_regions()`` ile aynıdır. Ülke geneli sonucu yalnızca ek bilgidir
    (farklı iklim rejimleri tek eğride karışır). ``kw`` doğrudan ``find_boundary``'ye gider.
    """
    from data import subset
    sonuclar = []
    for bolge in bolgeler:
        tb = subset(trend, bolge)
        zb = subset(rakim, bolge) if rakim is not None else None
        r = find_boundary(tb, axis=axis, rakim=zb, region=bolge, **kw)
        if bolge == "turkiye":
            r["note"] = (r.get("note", "") + "; " if r.get("note") else "") + \
                "ülke geneli eğrisi yalnızca ek bilgidir"
        sonuclar.append(r)
    return sonuclar
