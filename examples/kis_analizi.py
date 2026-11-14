
import xarray as xr
import numpy as np

# 1. Kar örtüsü verisini aç
ds = xr.open_dataset(
    "ornek_veriler/kar_ortusu__ORNEK.nc"
)

kar = ds["kar_ortusu"]

# 2. Sadece kış aylarını seç
aylar = kar.time.dt.month

kis_aylari = kar.where(
    aylar.isin([12, 1, 2, 3]),
    drop=True
)

# 3. Aralık ayını sonraki kış yılına ata
yillar = kis_aylari.time.dt.year
aylar = kis_aylari.time.dt.month

kis_yillari = xr.where(
    aylar == 12,
    yillar + 1,
    yillar
)

kis_aylari = kis_aylari.assign_coords(
    kis_yili=("time", kis_yillari.values)
)

# 4. Her kış için geçerli ay sayısını hesapla
gecerli_ay = kis_aylari.groupby(
    "kis_yili"
).count(dim="time")

# 5. Her kışın ortalamasını hesapla
kis_ortalama = kis_aylari.groupby(
    "kis_yili"
).mean(dim="time", skipna=True)

# En az 3 geçerli ay bulunsun
kis_ortalama = kis_ortalama.where(
    gecerli_ay >= 3
)

# 6. Yalnızca tam takvimli kışları al
kis_ortalama = kis_ortalama.sel(
    kis_yili=slice(2002, 2025)
)

# 7. Sonuçları yazdır
print("KIS VERISI BOYUTLARI:")
print(dict(kis_ortalama.sizes))

print("\nILK KIS YILI:")
print(int(kis_ortalama.kis_yili.min()))

print("\nSON KIS YILI:")
print(int(kis_ortalama.kis_yili.max()))

print("\nTOPLAM KIS YILI:")
print(kis_ortalama.sizes["kis_yili"])

print("\nEKSIK VERI SAYISI:")
print(int(kis_ortalama.isnull().sum()))

import pymannkendall as mk
from scipy.stats import theilslopes

# Bölgenin kış ortalama kar örtüsü
seri = kis_ortalama.mean(
    dim=["lat", "lon"],
    skipna=True
)

yillar = seri["kis_yili"].values
degerler = seri.values

# Eksik değerleri çıkar
gecerli = np.isfinite(degerler)
yillar = yillar[gecerli]
degerler = degerler[gecerli]

# Mann-Kendall testi
mk_sonuc = mk.hamed_rao_modification_test(
    degerler
)

# Sen eğimi ve güven aralığı
sen_sonuc = theilslopes(
    degerler,
    yillar,
    alpha=0.95
)

print("\n===== TREND TESTI =====")
print("Kis sayisi:", len(degerler))
print("Trend:", mk_sonuc.trend)
print("P degeri:", round(mk_sonuc.p, 5))

print(
    "Sen egimi (yuzde puan/10 yil):",
    round(sen_sonuc.slope * 10, 3)
)

print(
    "Guven araligi:",
    round(sen_sonuc.low_slope * 10, 3),
    round(sen_sonuc.high_slope * 10, 3)
)

# Rakim verisini oku
ds_rakim = xr.open_dataset(
    "ornek_veriler/rakim__ORNEK.nc"
)

rakim = ds_rakim["rakim"]

# Iki rakim grubu
gruplar = {
    "1800 METRE ALTI": rakim < 1800,
    "1800 METRE VE USTU": rakim >= 1800
}

for grup_adi, maske in gruplar.items():

    # Sadece ilgili rakimdaki hucreleri sec
    grup_verisi = kis_ortalama.where(maske)

    # Her kis icin bolge ortalamasini hesapla
    grup_serisi = grup_verisi.mean(
        dim=["lat", "lon"],
        skipna=True
    )

    yillar = grup_serisi.kis_yili.values
    degerler = grup_serisi.values

    # Eksik degerleri temizle
    gecerli = np.isfinite(degerler)
    yillar = yillar[gecerli]
    degerler = degerler[gecerli]

    print("\n======", grup_adi, "======")
    print("Kis sayisi:", len(degerler))

    if len(degerler) < 10:
        print("Yetersiz veri")
        continue

    # Mann-Kendall testi
    mk_sonuc = mk.hamed_rao_modification_test(
        degerler
    )

    # Sen egimi
    sen = theilslopes(
        degerler,
        yillar,
        alpha=0.95
    )

    print("Trend:", mk_sonuc.trend)
    print("P degeri:", f"{mk_sonuc.p:.3e}")
    print(
        "Sen egimi (% puan/10 yil):",
        round(sen.slope * 10, 3)
    )
    print(
        "%95 guven araligi:",
        round(sen.low_slope * 10, 3),
        round(sen.high_slope * 10, 3)
    )

ds_rakim.close()

from pathlib import Path

# 384 piksel icin bos sonuc haritasi
egimler = np.full(
    (kis_ortalama.sizes["lat"],
     kis_ortalama.sizes["lon"]),
    np.nan
)

yillar = kis_ortalama.kis_yili.values

# Her pikseli ayri analiz et
for i in range(kis_ortalama.sizes["lat"]):
    for j in range(kis_ortalama.sizes["lon"]):

        seri = kis_ortalama[:, i, j].values

        # Eksik verileri filtrele
        gecerli = np.isfinite(seri)

        # En az 15 kis verisi olmali
        if gecerli.sum() < 15:
            continue

        # Sen egimini hesapla
        sonuc = theilslopes(
            seri[gecerli],
            yillar[gecerli]
        )

        egimler[i, j] = sonuc.slope * 10

# Haritayi xarray formatina cevir
egim_haritasi = xr.DataArray(
    egimler,
    coords={
        "lat": kis_ortalama.lat,
        "lon": kis_ortalama.lon
    },
    dims=["lat", "lon"],
    name="sen_egimi"
)

egim_haritasi.attrs["units"] = (
    "percentage_points_per_decade"
)

# Sonucu NetCDF olarak kaydet
Path("outputs").mkdir(exist_ok=True)

egim_haritasi.to_netcdf(
    "outputs/piksel_egimleri.nc"
)

print("\n===== PIKSEL ANALIZI =====")
print("Toplam piksel:", egimler.size)
print(
    "Analiz edilen piksel:",
    np.isfinite(egimler).sum()
)
print(
    "Azalis gosteren:",
    np.sum(egimler < 0)
)
print(
    "Artis gosteren:",
    np.sum(egimler > 0)
)
print("Harita kaydedildi!")

ds.close()

# ===== PIKSEL BAZLI MANN-KENDALL =====

p_degerleri = np.full(
    egimler.shape,
    np.nan
)

for i in range(kis_ortalama.sizes["lat"]):
    for j in range(kis_ortalama.sizes["lon"]):

        seri = kis_ortalama[:, i, j].values

        # Eksik verileri temizle
        gecerli = np.isfinite(seri)
        temiz_seri = seri[gecerli]

        if len(temiz_seri) < 15:
            continue

        # Sabit serilerde trend yok
        if np.all(temiz_seri == temiz_seri[0]):
            p_degerleri[i, j] = 1.0
            continue

        try:
            sonuc = mk.hamed_rao_modification_test(
                temiz_seri
            )

            if np.isfinite(sonuc.p):
                p_degerleri[i, j] = sonuc.p

        except (ValueError, ZeroDivisionError):
            continue

# Sonuclari xarray formatina cevir
p_haritasi = xr.DataArray(
    p_degerleri,
    coords={
        "lat": kis_ortalama.lat,
        "lon": kis_ortalama.lon
    },
    dims=["lat", "lon"],
    name="p_value"
)

# NetCDF dosyasina kaydet
p_haritasi.to_netcdf(
    "outputs/piksel_p_degerleri.nc"
)

print("\n===== MANN-KENDALL PIKSEL TESTI =====")

print("Toplam piksel:", p_degerleri.size)

print(
    "Gecerli p degeri:",
    np.isfinite(p_degerleri).sum()
)

print(
    "Ham p < 0.05:",
    np.sum(p_degerleri < 0.05)
)

print(
    "Ham p >= 0.05:",
    np.sum(p_degerleri >= 0.05)
)

print("P degeri haritasi kaydedildi!")

from statsmodels.stats.multitest import multipletests

# ===== FDR DUZELTMESI =====

# Gecerli p degerlerini bul
gecerli = np.isfinite(p_degerleri)

# Bos sonuc haritalari
fdr_anlamli = np.zeros(
    p_degerleri.shape,
    dtype=bool
)

duzeltilmis_p = np.full(
    p_degerleri.shape,
    np.nan
)

# Benjamini-Hochberg FDR
reddet, p_duzeltilmis, _, _ = multipletests(
    p_degerleri[gecerli],
    alpha=0.10,
    method="fdr_bh"
)

# Sonuclari haritaya yerlestir
fdr_anlamli[gecerli] = reddet
duzeltilmis_p[gecerli] = p_duzeltilmis

# NetCDF dosyasi olustur
fdr_ds = xr.Dataset(
    {
        "fdr_anlamli": (
            ("lat", "lon"),
            fdr_anlamli
        ),
        "p_duzeltilmis": (
            ("lat", "lon"),
            duzeltilmis_p
        ),
        "sen_egimi": (
            ("lat", "lon"),
            egimler
        )
    },
    coords={
        "lat": kis_ortalama.lat,
        "lon": kis_ortalama.lon
    }
)

fdr_ds.attrs["alpha_fdr"] = 0.10
fdr_ds.attrs["veri_turu"] = "sentetik"

fdr_ds.to_netcdf(
    "outputs/piksel_fdr.nc"
)

# Sonuclari yazdir
print("\n===== FDR SONUCLARI =====")

print("Test edilen piksel:", gecerli.sum())

print("FDR anlamli piksel:", fdr_anlamli.sum())

print(
    "Anlamli azalis:",
    np.sum(fdr_anlamli & (egimler < 0))
)

print(
    "Anlamli artis:",
    np.sum(fdr_anlamli & (egimler > 0))
)

print("FDR haritasi kaydedildi!")
