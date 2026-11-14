"""Trend Dedektifi veri modülü (Kişi 1).

Diğer modüller için iki giriş noktası:
    from data import load, subset
    da = load("sicaklik_2m", region="Erzurum")     # işlenmiş küpü aç + bölgeye kes
    sub = subset(ds, "Doğu Anadolu")                # elindeki xarray'i bölgeye kes
"""


def load(*args, **kwargs):
    """data.build.load kısayolu (ağır içe aktarmalar ilk çağrıda yapılır)."""
    from data.build import load as _load
    return _load(*args, **kwargs)


def subset(*args, **kwargs):
    """data.regions.subset kısayolu."""
    from data.regions import subset as _subset
    return _subset(*args, **kwargs)
