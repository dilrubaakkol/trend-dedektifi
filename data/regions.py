"""Hazır analiz bölgeleri. bbox = (batı, güney, doğu, kuzey), derece.

Sınırlar yaklaşık demo kutularıdır; ekip gerektiğinde günceller.
"""

REGIONS = {
    "dogu_anadolu": {
        "label": "Doğu Anadolu (Erzurum–Kars–Van)",
        "bbox": (38.0, 37.5, 44.0, 41.5),
    },
    "konya": {
        "label": "Konya Kapalı Havzası",
        "bbox": (31.5, 36.8, 34.5, 39.2),
    },
}


def get_bbox(region: str) -> tuple[float, float, float, float]:
    return REGIONS[region]["bbox"]
