"""L4'ün 6 değişken çifti ve her çiftin serilerinin hazırlanması (docs/sozlesmeler.md 2.3).

Sade anlatım: her çift için iki değişkenin hangi seriyle (kış, yaz, mevsim, aylık) karşılaştırılacağı,
fiziğin hangi yönü beklediği ve çifte özel kurallar (kar maskesi, GRACE boşluğu, gecikme) burada.
``cift_serileri`` iki aylık girdiyi alır ve ``iliski.iliski_1d``'nin istediği hizalı serileri verir.
Hücre küpü (time, lat, lon) de tek seri (time) de olur.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import xarray as xr

from physics import seriler as S


@dataclass(frozen=True)
class Cift:
    no: int
    d1: str
    u1: str
    d2: str
    u2: str
    seri: str            # sözleşmedeki `seri` değeri
    beklenen: int        # +1 aynı yönde, −1 zıt yönde
    kademe: int
    gecikmeler: tuple = (0,)
    harita: bool = True  # hücre haritası üretilir mi (çift 4: hayır)
    not_: str = ""

    @property
    def kod(self) -> str:
        """Sözleşmedeki `cift` değeri: ``<d1>__<u1>~<d2>__<u2>``."""
        return f"{self.d1}__{self.u1}~{self.d2}__{self.u2}"

    def harita_dosyasi(self, gecikme: int = 0) -> str:
        """``iliski__<d1>__<d2>[__gecikmeN].nc``"""
        ek = f"__gecikme{gecikme}" if len(self.gecikmeler) > 1 else ""
        return f"iliski__{self.d1}__{self.d2}{ek}.nc"


CIFTLER = (
    Cift(1, "sicaklik_2m", "MERRA2", "kar_ortusu", "MOD10CM", "kis_DJF", -1, 1,
         not_="Yalnız kış ortalaması kar örtüsü ≥ %10 olan hücreler."),
    Cift(2, "yagis", "GPM", "toprak_nemi", "GLDAS", "mevsim_anomali", +1, 1),
    Cift(3, "toprak_nemi", "GLDAS", "ndvi", "MOD13C2", "aylik_anomali_nis_eyl", +1, 1,
         gecikmeler=(1, 2), not_="NDVI, toprak neminden 1 ya da 2 ay sonra."),
    Cift(4, "yagis", "GPM", "toplam_su_depolama", "GRACE", "yillik", +1, 1, harita=False,
         not_=("Yalnız 7 bölge + Türkiye (8 satır), il satırı ve harita yok: GRACE uydusunun "
               "gerçek çözünürlüğü yaklaşık 300 km, çoğu il tek bir GRACE hücresinden küçük. "
               "En az 9 ayı dolu olmayan yıllar (GRACE ile GRACE-FO arasındaki boşluk) atılır.")),
    Cift(5, "sicaklik_2m", "MERRA2", "buharlasma", "GLDAS", "yaz_JJA", +1, 2,
         not_="Yaz sıcaklığı ile buharlaşma; yönü yerin kuraklığına bağlıdır."),
    Cift(6, "sicaklik_2m", "MERRA2", "yuzey_sicakligi_gunduz", "MOD11C3", "aylik_anomali", +1, 2,
         not_="Kalite kontrolü: aynı olgunun iki ölçümü, güçlü pozitif beklenir."),
)
CIFT = {c.no: c for c in CIFTLER}

# GRACE yıllık ortalaması için en az ay sayısı. GRACE'te büyük boşluk (2017–2018) dışında da
# dağınık eksik aylar var; 12 ay şartı birçok yılı gereksiz yere atar. Büyük boşluk yılları
# (≤ 8 ay) yine atılır.
GRACE_MIN_AY = 9
KAR_ESIGI = 10.0  # %


def _ondalik_yil(zaman) -> np.ndarray:
    t = pd.DatetimeIndex(zaman)
    return (t.year + (t.month - 1) / 12.0).to_numpy(float)


def _hizala(x: xr.DataArray, y: xr.DataArray, boyut: str):
    x, y = xr.align(x, y, join="inner")
    if x.sizes.get(boyut, 0) == 0:
        raise ValueError("iki değişkenin ortak dönemi yok")
    for b in ("lat", "lon"):
        if b in x.dims and x.sizes[b] == 0:
            raise ValueError(f"iki değişkenin '{b}' koordinatları uyuşmuyor (aynı ızgara olmalı)")
    return x, y


def _donem(t: np.ndarray, x: xr.DataArray, y: xr.DataArray, boyut: str) -> str:
    """İki serinin birlikte geçerli olduğu ilk ve son zaman adımı (ör. ``2002-2025``)."""
    ortak = (x.notnull() & y.notnull())
    diger = [d for d in ortak.dims if d != boyut]
    if diger:
        ortak = ortak.any(diger)
    ok = ortak.values
    if not ok.any():
        return ""
    a, b = t[ok][0], t[ok][-1]
    if boyut == "yil":
        return f"{int(a)}-{int(b)}"
    if boyut == "t":  # mevsim anomalisi: ondalık yıl
        return f"{int(np.floor(a))}-{int(np.floor(b))}"
    return f"{pd.Timestamp(a):%Y-%m}…{pd.Timestamp(b):%Y-%m}"


def cift_serileri(cift: Cift | int, a: xr.DataArray, b: xr.DataArray) -> list[dict]:
    """Bir çiftin iki aylık girdisinden hizalı seriler.

    Parametreler
    ----------
    cift : ``Cift`` ya da çift numarası (1–6).
    a, b : aylık DataArray'ler — sırasıyla ``cift.d1`` ve ``cift.d2`` (time[, lat, lon]).

    Döndürür: her gecikme için bir sözlük
    ``{"gecikme", "x", "y", "t", "boyut", "donem"}``. ``x``, ``y`` aynı boyutlu DataArray'ler;
    zaman boyutu ``boyut`` adıyla (``yil``, ``t`` ya da ``time``) ilk sırada. ``t``: trend
    çıkarmak için sayısal zaman (yıl). Çift 1'de kar maskesi dışındaki hücreler NaN'dır.
    """
    c = CIFT[cift] if isinstance(cift, int) else cift
    s = c.seri
    sonuc = []

    if s in ("kis_DJF", "yaz_JJA", "yillik"):
        mevsim = {"kis_DJF": "kis", "yaz_JJA": "yaz", "yillik": "yillik"}[s]
        min_b = GRACE_MIN_AY if c.d2 == "toplam_su_depolama" else None
        x = S.mevsim_serisi(a, mevsim, toplam=S.toplam_mi(c.d1))
        y = S.mevsim_serisi(b, mevsim, toplam=S.toplam_mi(c.d2), min_ay=min_b)
        x, y = _hizala(x, y, "yil")
        if c.no == 1 and "lat" in y.dims:
            m = S.kar_maskesi(y, KAR_ESIGI)
            x, y = x.where(m), y.where(m)
        t = x["yil"].values.astype(float)
        sonuc.append({"gecikme": 0, "x": x, "y": y, "t": t, "boyut": "yil"})

    elif s == "mevsim_anomali":
        x = S.mevsim_anomali(a, toplam=S.toplam_mi(c.d1))
        y = S.mevsim_anomali(b, toplam=S.toplam_mi(c.d2))
        x, y = _hizala(x, y, "t")
        sonuc.append({"gecikme": 0, "x": x, "y": y, "t": x["t"].values.astype(float), "boyut": "t"})

    elif s in ("aylik_anomali", "aylik_anomali_nis_eyl"):
        xa, ya = _hizala(S.aylik_anomali(a), S.aylik_anomali(b), "time")
        if s == "aylik_anomali":
            sonuc.append({"gecikme": 0, "x": xa, "y": ya, "t": _ondalik_yil(xa["time"].values),
                          "boyut": "time"})
        else:
            for g in c.gecikmeler:
                x, y = S.gecikmeli(xa, ya, g)
                sonuc.append({"gecikme": g, "x": x, "y": y, "t": _ondalik_yil(x["time"].values),
                              "boyut": "time"})
    else:
        raise ValueError(f"bilinmeyen seri: {s}")

    for r in sonuc:
        r["x"] = r["x"].transpose(r["boyut"], ...)
        r["y"] = r["y"].transpose(r["boyut"], ...)
        r["donem"] = _donem(r["t"] if r["boyut"] != "time" else r["x"]["time"].values,
                            r["x"], r["y"], r["boyut"])
    return sonuc
