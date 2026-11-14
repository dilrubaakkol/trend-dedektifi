"""Ayna bölgeler: aynı süreç, farklı yerlerde zıt yönlü trend.

Sade anlatım: anlamlı trendi olan pikseller "artan" ve "azalan" diye ayrılır, yan yana
duranlar gruplanır (küme). Sonra "artan ve azalan kümeleri en çok ne ayırıyor: rakım mı,
enlem mi, boylam mı?" sorulur. En çok ayıran özellik, sınır aramasında (Adım 3) kullanılacak
önerilen eksendir. Böylece eksen önceden varsayılmaz, veriden çıkar.

Algoritma: KISI3_PLAN.md, Adım 4. Çıktı tipi ``mirror`` (öneri; Kişi 4 ve 5 onaylayacak).

VARSAYIM: Anlamlılık maskesi (FDR'yi geçen pikseller) Kişi 2'den boolean DataArray olarak
gelir. Gelene kadar testlerde sentetik bir eşik kullanılır.
"""

from __future__ import annotations

import numpy as np
import xarray as xr
from scipy import ndimage

OZELLIKLER = ("rakim", "enlem", "boylam")
_ALAN = {"rakim": "mean_rakim_m", "enlem": "mean_lat", "boylam": "mean_lon"}
KARISIKLIK_R = 0.6     # iki eksen arasındaki |korelasyon| bu değeri geçerse ...
KARISIKLIK_ORAN = 2.0  # ... ve ayırma güçleri oranı bundan küçükse "alternatif eksen" yazılır


def _kumeler(isaretli: np.ndarray, min_boyut: int, kosegen: bool):
    """Boolean dizide bitişik piksel kümeleri; min_boyut'tan küçükler atılır."""
    yapi = np.ones((3, 3), bool) if kosegen else None
    etiket, n = ndimage.label(isaretli, structure=yapi)
    if n == 0:
        return etiket, []
    boyut = np.bincount(etiket.ravel())[1:]
    tut = [i + 1 for i in range(n) if boyut[i] >= min_boyut]
    return etiket, tut


def _standart_fark(a: np.ndarray, b: np.ndarray) -> float:
    """İki grup arasındaki standartlaştırılmış fark |ort_a − ort_b| / birleşik std (Cohen d)."""
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if a.size < 2 or b.size < 2:
        return float("nan")
    s = np.sqrt(((a.size - 1) * a.var(ddof=1) + (b.size - 1) * b.var(ddof=1))
                / (a.size + b.size - 2))
    return float(abs(a.mean() - b.mean()) / s) if s > 0 else float("inf")


def find_mirror_clusters(trend: xr.DataArray, anlamli: xr.DataArray | None = None,
                         rakim: xr.DataArray | None = None, mask: xr.DataArray | None = None,
                         region: str = "bolge", variable: str = "kar_ortusu",
                         min_kume: int = 20, kosegen: bool = True) -> dict:
    """Zıt işaretli trend kümelerini bulur ve onları en iyi ayıran ekseni önerir.

    Parametreler
    ----------
    trend : DataArray (lat, lon) — piksel başına trend.
    anlamli : boolean DataArray (lat, lon) — FDR'yi geçen pikseller (Kişi 2). None → hepsi.
    rakim : DataArray (lat, lon), aynı ızgarada. None ise rakım özelliği atlanır.
    mask : boolean DataArray (lat, lon) — bölge. None → tüm ızgara.
    min_kume : en küçük küme boyutu (piksel).
    kosegen : True → çapraz komşular da bitişik sayılır (8-komşuluk).

    Döndürür
    -------
    dict, ``type: "mirror"``. ``status``: ``ok`` (iki işaret de var) / ``no_mirror``
    (yalnız bir işaret ya da hiç küme yok).
    """
    trend = trend.transpose("lat", "lon")
    rakim = rakim.transpose("lat", "lon") if rakim is not None else None
    mask = mask.broadcast_like(trend).transpose("lat", "lon") if mask is not None else None
    anlamli = (anlamli.broadcast_like(trend).transpose("lat", "lon")
               if anlamli is not None else None)
    v = trend.values.astype(float)
    gecerli = np.isfinite(v)
    if anlamli is not None:
        gecerli &= np.asarray(anlamli.values, dtype=bool)
    if mask is not None:
        gecerli &= np.asarray(mask.values, dtype=bool)

    LON, LAT = np.meshgrid(trend.lon.values, trend.lat.values)
    alanlar = {"enlem": LAT, "boylam": LON}
    if rakim is not None:
        if not (np.array_equal(rakim.lat.values, trend.lat.values)
                and np.array_equal(rakim.lon.values, trend.lon.values)):
            raise ValueError("rakim ve trend aynı ızgarada olmalı (lat/lon farklı)")
        alanlar = {"rakim": rakim.values.astype(float), **alanlar}

    kumeler, pozitif, negatif = [], np.zeros_like(gecerli), np.zeros_like(gecerli)
    kid = 0
    for isaret, secim in ((1, gecerli & (v > 0)), (-1, gecerli & (v < 0))):
        etiket, tut = _kumeler(secim, min_kume, kosegen)
        for e in tut:
            m = etiket == e
            (pozitif if isaret > 0 else negatif)[m] = True
            kid += 1
            k = {"cluster_id": kid, "sign": isaret, "n_pixels": int(m.sum()),
                 "mean_trend": round(float(v[m].mean()), 4)}
            for ad, arr in alanlar.items():
                k[_ALAN[ad]] = round(float(np.nanmean(arr[m])), 4)
            kumeler.append(k)

    kumeler.sort(key=lambda k: -k["n_pixels"])
    sonuc = {
        "id": f"ayna_{variable}_{region}",
        "type": "mirror",
        "region": region,
        "variable": variable,
        "suggested_axis": None,
        "standardized_difference": {},
        "n_clusters": {"pozitif": sum(k["sign"] > 0 for k in kumeler),
                       "negatif": sum(k["sign"] < 0 for k in kumeler)},
        "clusters": kumeler,
        "status": "no_mirror",
    }
    if not (pozitif.any() and negatif.any()):
        sonuc["note"] = ("yalnız tek yönlü trend kümeleri var" if kumeler
                         else f"{min_kume}+ pikselli anlamlı küme yok")
        return sonuc

    farklar = {ad: _standart_fark(arr[pozitif], arr[negatif]) for ad, arr in alanlar.items()}
    sonuc["standardized_difference"] = {ad: round(d, 3) for ad, d in farklar.items()}
    sonlu = {ad: d for ad, d in farklar.items() if np.isfinite(d) or d == float("inf")}
    if not sonlu:
        return sonuc
    sirali = sorted(sonlu, key=sonlu.get, reverse=True)
    sonuc["suggested_axis"] = sirali[0]
    sonuc["status"] = "ok"

    # Karışıklık kontrolü: önerilen eksen ikinci adayla sıkı ilişkiliyse ve ayırma güçleri
    # yakınsa (ör. Türkiye'de doğuya gidildikçe rakım artar), veri ikisini ayırt edemez.
    if len(sirali) > 1:
        a1, a2 = sirali[0], sirali[1]
        kume = pozitif | negatif
        x1, x2 = alanlar[a1][kume], alanlar[a2][kume]
        ok = np.isfinite(x1) & np.isfinite(x2)
        r = float(np.corrcoef(x1[ok], x2[ok])[0, 1]) if ok.sum() > 2 else 0.0
        oran = sonlu[a1] / sonlu[a2] if sonlu[a2] > 0 else float("inf")
        sonuc["axis_correlation"] = {"eksenler": [a1, a2], "r": round(r, 3)}
        if abs(r) >= KARISIKLIK_R and oran < KARISIKLIK_ORAN:
            sonuc["alternative_axis"] = a2
            sonuc["note"] = (f"{a1} ve {a2} bu bölgede birbirine bağlı (r={r:.2f}); veri ikisini "
                             f"tam ayırt edemiyor. Sınır her iki eksende de aranmalı.")
    return sonuc
