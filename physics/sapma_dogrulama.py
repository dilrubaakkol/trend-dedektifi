"""Sapma haritası v2 için bağımsız doğrulama (yalnız rapor; sulama izi hesabına hiçbir şey vermez).

Hedef: GFSAD1KCM (2010) sulanan oran ≥ 0,2 olan kara hücreleri (sabit eşik; ``data.arazi``).
Ölçütler: ROC AUC (Mann-Whitney, eşitlikler ortalama sıra), precision@%5 (en yüksek skorlu %5 kara
hücresinde hedef oranı) ve rastgele beklenti (hedef oranı; AUC için 0,5).
Maskeli ya da skoru olmayan hücre en düşük skoru alır (maske tahminin bir parçasıdır); hedefi bilinmeyen
hücre değerlendirmeye girmez. Dört yapılandırma: v1 (0,25° maskesiz) · maske (0,25°) · 0,05° (maskesiz) ·
maske + 0,05°. Ayrıca yalnız rapor için maske eşiği 0,2 ve 0,5 duyarlılığı.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from scipy.stats import rankdata

HEDEF_ESIK = 0.2
UST_ORAN = 0.05
DOSYA = {"025": "sulanan_oran__GFSAD1KCM.nc", "005": "sulanan_oran__GFSAD1KCM__005.nc"}


def auc(skor: np.ndarray, hedef: np.ndarray) -> float:
    """ROC AUC: rastgele bir hedef hücrenin rastgele bir hedef dışı hücreden yüksek skor alma olasılığı."""
    s = np.where(np.isfinite(skor), skor, -np.inf).astype(float)
    h = np.asarray(hedef, bool)
    n1, n0 = int(h.sum()), int((~h).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = rankdata(s)                                    # −inf (skorsuz) en düşük sıra; eşitlikler ortalama
    return float((r[h].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def precision_ust(skor: np.ndarray, hedef: np.ndarray, oran: float = UST_ORAN) -> float:
    """En yüksek skorlu ``oran`` kadar hücrede hedef oranı (skoru olmayanlar sona; kararlı sıralama)."""
    s = np.where(np.isfinite(skor), skor, -np.inf)
    k = max(1, int(np.ceil(oran * s.size)))
    sira = np.argsort(-s, kind="stable")[:k]
    return float(np.asarray(hedef, bool)[sira].mean())


def degerlendir(skor: np.ndarray, sulanan: np.ndarray, kara: np.ndarray, esik: float = HEDEF_ESIK) -> dict:
    """Kara ve hedefi bilinen hücrelerde AUC, precision@%5, taban oran."""
    ok = np.asarray(kara, bool) & np.isfinite(sulanan)
    h = sulanan[ok] >= esik
    s = np.asarray(skor, float)[ok]
    return {"hucre": int(ok.sum()), "hedef_hucre": int(h.sum()), "taban_oran": float(h.mean()),
            "skorlu_hucre": int(np.isfinite(s).sum()), "auc": auc(s, h), "precision_ust5": precision_ust(s, h)}


def hedef_oku(paket: Path, grid: str, lat, lon) -> np.ndarray:
    """Doğrulama katmanını (lat, lon) hücrelerine hizalar (aynı merkezler, tolerans 1e-4°)."""
    with xr.open_dataset(Path(paket) / "dogrulama" / DOSYA[grid]) as ds:
        da = ds["sulanan_oran"].load()
    return da.sel(lat=xr.DataArray(lat, dims="lat"), lon=xr.DataArray(lon, dims="lon"), method="nearest",
                  tolerance=1e-4).values.astype(float)


def _komsu_ort(x: np.ndarray, iy: int, ix: int, r: int = 1) -> float:
    p = x[max(0, iy - r):iy + r + 1, max(0, ix - r):ix + r + 1]
    return float(np.nanmean(p)) if np.isfinite(p).any() else float("nan")


def dogrula(paket: Path, v2: dict | None = None) -> dict:
    """Dört yapılandırma + maske duyarlılığı + küme tablosu; <paket>/dogrulama/ altına yazar."""
    from physics.sapma import sulama_izi_v2, tarim_maskesi
    paket = Path(paket)
    satir = []
    hedefler = {}
    for grid, ad_maskesiz, ad_maskeli in (("025", "v1 (0,25°, maskesiz)", "maske (0,25°)"),
                                          ("005", "0,05° (maskesiz)", "maske + 0,05°")):
        ham = sulama_izi_v2(paket, grid, maske=False)
        hedef = hedef_oku(paket, grid, ham["lat"], ham["lon"])
        hedefler[grid] = (ham, hedef)
        for ad, esik, tur in ((ad_maskesiz, None, "ana"), (ad_maskeli, 0.3, "ana"),
                              (f"maske {0.2:g} ({grid})", 0.2, "duyarlılık"),
                              (f"maske {0.5:g} ({grid})", 0.5, "duyarlılık")):
            skor = ham["sulama"]["sulama_izi"] if esik is None else \
                tarim_maskesi(ham["sulama"], ham["tarim"], esik)["sulama_izi"]
            satir.append({"yapilandirma": ad, "tur": tur, "izgara": grid, "tarim_esigi": esik,
                          **degerlendir(skor, hedef, ham["kara"])})
    tab = pd.DataFrame(satir)
    tab["rastgele_auc"] = 0.5
    tab["kaldirac_ust5"] = tab["precision_ust5"] / tab["taban_oran"]

    # v2 kümeleri (maske + 0,05°): tepe hücrenin ve 3×3 komşuluğun sulanan oranı
    km = v2["kumeler"].copy() if v2 is not None else None
    if km is not None and len(km):
        ham, hedef = hedefler["005"]
        lat, lon = ham["lat"], ham["lon"]
        iy = [int(np.argmin(np.abs(lat - a))) for a in km["tepe_lat"]]
        ix = [int(np.argmin(np.abs(lon - o))) for o in km["tepe_lon"]]
        km["sulanan_oran_tepe"] = [hedef[a, b] for a, b in zip(iy, ix)]
        km["sulanan_oran_3x3"] = [_komsu_ort(hedef, a, b) for a, b in zip(iy, ix)]
        km["hedef_tepe"] = km["sulanan_oran_tepe"] >= HEDEF_ESIK
    hedef_dir = paket / "dogrulama"
    yollar = [hedef_dir / "sapma_v2_dogrulama.csv"]
    tab.to_csv(yollar[0], index=False, encoding="utf-8-sig", float_format="%.4g")
    if km is not None:
        yollar.append(hedef_dir / "kume_dogrulama_v2.csv")
        km.to_csv(yollar[1], index=False, encoding="utf-8-sig", float_format="%.4g")
    return {"tablo": tab, "kumeler": km, "yollar": yollar}
