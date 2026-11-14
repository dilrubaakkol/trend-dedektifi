# YOL HARİTASI (2026-11-14): v0.1 kapsamında kullanılmıyor (bkz. physics/KISI3_PLAN.md, bölüm 2).
# Kod ve testleri ileride kullanılmak üzere duruyor; silmeyin.
"""Kişi 4 ve 5 için ÖRNEK sonuç dosyası üretir (sentetik veri — YER TUTUCU).

    python -m physics.ornek          → physics/ornekler/ornek_sonuclar.json

Gerçek trend haritası (Kişi 2) gelene kadar arayüz ve LLM tarafı Kişi 3'ün çıktı biçimini
bu dosyayla görebilir. İçindeki sayılar gerçek değildir.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import xarray as xr

from physics.boundary import find_boundaries
from physics.mirror import find_mirror_clusters
from physics.synthetic import synthetic_trend_map

CIKTI = Path(__file__).resolve().parent / "ornekler" / "ornek_sonuclar.json"


def uret(grid: str = "005", n_boot: int = 1000, seed: int = 1) -> dict:
    """Türkiye geneli + 7 bölge için sınır ve ayna sonuçlarını sentetik veriyle üretir."""
    from data import subset
    from data.synthetic import synthetic_elevation

    z = subset(synthetic_elevation(grid), "turkiye")
    # Doğuda (lon > 38) sınır 1700 m, batıda 1200 m — bölgeye göre farklı sınır örneği.
    z0 = xr.where(z.lon > 38.0, 1700.0, 1200.0)
    t = synthetic_trend_map(z, z0=z0, a=-0.004, gurultu=0.5, seed=seed)
    anlamli = np.abs(t) > 0.5  # FDR maskesi yerine geçici eşik

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sinirlar = find_boundaries(t, z, n_boot=n_boot)
        aynalar = [find_mirror_clusters(subset(t, b), subset(anlamli.astype(float), b) > 0,
                                        rakim=subset(z, b), region=b)
                   for b in [r["region"] for r in sinirlar]]
    for a in aynalar:  # örnek dosya kısa kalsın: her bölgede en büyük 5 küme
        a["clusters"] = a["clusters"][:5]

    return {
        "_not": "Bu dosyadaki sayilar YER TUTUCUDUR (sentetik veri), gercek sonuc degildir.",
        "_sentetik_gercek": "sinir: dogu (lon>38) 1700 m, bati 1200 m; eksen: rakim",
        "analyses": sinirlar + aynalar,
    }


if __name__ == "__main__":
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    CIKTI.write_text(json.dumps(uret(), ensure_ascii=False, indent=1), encoding="utf-8")
    print(CIKTI)
