
import numpy as np
import xarray as xr
from pathlib import Path


# Toplanarak hesaplanacak degiskenler
TOPLANANLAR = {
    "yagis",
    "buharlasma",
    "yuzey_akisi",
    "taban_akisi"
}


def donem_serisi(da, aylar, toplama=False, kis=False):

    # Istenen aylari sec
    secilen = da.where(
        da.time.dt.month.isin(aylar),
        drop=True
    )

    # Aralik sonraki kis yilina aittir
    if kis:
        yillar = xr.where(
            secilen.time.dt.month == 12,
            secilen.time.dt.year + 1,
            secilen.time.dt.year
        )
    else:
        yillar = secilen.time.dt.year

    secilen = secilen.assign_coords(
        yil=("time", yillar.values)
    )

    gruplar = secilen.groupby("yil")

    # Her yil/piksel icin gecerli ay sayisi
    sayi = gruplar.count(dim="time")

    # Yagis gibi degiskenlerde toplam
    if toplama:
        sonuc = gruplar.sum(
            dim="time", skipna=True
        )
    else:
        sonuc = gruplar.mean(
            dim="time", skipna=True
        )

    # Bir ay eksikse o donem eksik sayilir
    sonuc = sonuc.where(sayi == len(aylar))

    # Aralik 2000 olmadigi icin ilk tam kis 2002
    ilk_yil = 2002 if kis else 2001

    return sonuc.sel(
        yil=slice(ilk_yil, 2025)
    ).transpose("yil", "lat", "lon")


def l2_uret(da, degisken):

    toplama = degisken in TOPLANANLAR

    # 1. Aylik klimatoloji
    klimatoloji = da.groupby(
        "time.month"
    ).mean(dim="time", skipna=True)

    # 2. Aylik anomali
    anomali = (
        da.groupby("time.month") - klimatoloji
    )

    # 3. Yillik ve mevsimlik seriler
    mevsimler = {
        "yillik": list(range(1, 13)),
        "kis": [12, 1, 2],
        "ilkbahar": [3, 4, 5],
        "yaz": [6, 7, 8],
        "sonbahar": [9, 10, 11]
    }

    seriler = xr.Dataset({
        ad: donem_serisi(
            da,
            aylar,
            toplama=toplama,
            kis=(ad == "kis")
        )
        for ad, aylar in mevsimler.items()
    })

    seriler.attrs["degisken"] = degisken
    seriler.attrs["veri_turu"] = "sentetik_ornek"
    seriler.attrs["toplama_yontemi"] = (
        "toplam" if toplama else "ortalama"
    )

    return klimatoloji, anomali, seriler


# Ilk testimizi mevcut kar verisiyle yapalim
if __name__ == "__main__":

    dosya = (
        "ornek_veriler/kar_ortusu__ORNEK.nc"
    )

    cikti = Path("cache/urun/L2_anomali")
    cikti.mkdir(parents=True, exist_ok=True)

    with xr.open_dataset(dosya) as ds:

        kar = ds["kar_ortusu"]

        klimatoloji, anomali, seriler = l2_uret(
            kar, "kar_ortusu"
        )

        klimatoloji.to_netcdf(
            cikti / "kar_ortusu__ORNEK__klimatoloji.nc"
        )

        anomali.to_netcdf(
            cikti / "kar_ortusu__ORNEK__anomali.nc"
        )

        seriler.to_netcdf(
            cikti / "kar_ortusu__ORNEK__mevsim.nc"
        )

        print("L2 VERI HAZIRLAMA TAMAMLANDI")
        print("Klimatoloji:", dict(klimatoloji.sizes))
        print("Anomali:", dict(anomali.sizes))
        print("Mevsimler:", list(seriler.data_vars))
        print("Ilk tam kis:", 2002)
        print("Dosyalar kaydedildi!")
