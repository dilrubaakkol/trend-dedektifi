"""Kişi 5 için YER TUTUCU ``ciftler.csv`` örneği (sentetik veri; gerçek sonuç DEĞİLDİR).

    python -m physics.ornek_l4      # → physics/ornekler/ciftler__YER_TUTUCU.csv

Sütunlar ve biçim gerçek dosyayla aynıdır (docs/sozlesmeler.md 2.3); sayılar uydurmadır.
Sentetik desen: her yerde beklenen yönde ilişki, Konya ilinde ters yönde. 6 çiftin hepsi var.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from physics.ciftler import CIFTLER
from physics.tablo import bolge_maskeleri, ciftler_tablosu, csv_yaz

YOL = Path(__file__).resolve().parent / "ornekler" / "ciftler__YER_TUTUCU.csv"
LAT = 35.625 + 0.25 * np.arange(28)
LON = 25.625 + 0.25 * np.arange(78)
ZAMAN = pd.date_range("2001-01", "2025-12", freq="MS")


def ornek_tablo(seed: int = 0) -> pd.DataFrame:
    m = bolge_maskeleri(LAT, LON)
    kara = m["turkiye"]
    rng = np.random.default_rng(seed)
    sekil = (len(ZAMAN), len(LAT), len(LON))
    ay = ZAMAN.month.to_numpy()
    dongu = np.sin(2 * np.pi * (ay - 4) / 12)[:, None, None]
    ortak = rng.standard_normal(sekil)
    isaret = np.where(m["il:konya"], -1.0, 1.0)[None]

    def kup(v, ad):
        k = {"urun_surumu": "YER TUTUCU", "veri_seti_doi": "(yayında doldurulacak)",
             "lisans": "CC BY 4.0", "doi": f"YER TUTUCU ({ad})"}
        return xr.DataArray(np.where(kara[None], v, np.nan),
                            coords={"time": ZAMAN, "lat": LAT, "lon": LON},
                            dims=("time", "lat", "lon"), attrs=k)

    def bagli(isaretli=True, olcek=1.0, kayma=0.0):
        g = rng.standard_normal(sekil)
        s = isaret if isaretli else 1.0
        return kayma + olcek * (s * 0.6 * ortak + 0.8 * g)

    veri = {
        "sicaklik_2m__MERRA2": kup(10 + 12 * dongu + 2 * ortak, "MERRA2"),
        "kar_ortusu__MOD10CM": kup(np.clip(40 - 30 * dongu - 8 * isaret * ortak, 0, 100)
                                   * (LON > 36)[None, None, :], "MOD10CM"),
        "yagis__GPM": kup(np.clip(40 - 25 * dongu + 10 * ortak, 0, None), "GPM"),
        "toprak_nemi__GLDAS": kup(25 - 5 * dongu + bagli(olcek=3), "GLDAS"),
        "ndvi__MOD13C2": kup(0.4 + 0.2 * dongu + 0.05 * np.roll(ortak, 1, 0) * isaret
                             + 0.04 * rng.standard_normal(sekil), "MOD13C2"),
        "toplam_su_depolama__GRACE": kup(bagli(olcek=5), "GRACE"),
        "buharlasma__GLDAS": kup(np.clip(50 + 30 * dongu + bagli(olcek=8), 0, None), "GLDAS"),
        "yuzey_sicakligi_gunduz__MOD11C3": kup(14 + 15 * dongu + 2.5 * bagli(), "MOD11C3"),
    }
    df = ciftler_tablosu(veri)
    assert set(df["cift_no"]) == {c.no for c in CIFTLER}
    return df


def main() -> None:
    print(csv_yaz(ornek_tablo(), YOL))


if __name__ == "__main__":
    main()
