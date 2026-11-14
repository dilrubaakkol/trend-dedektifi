
import numpy as np
import xarray as xr
import matplotlib.pyplot as plt
from pathlib import Path

# FDR sonucunu oku
ds = xr.open_dataset(
    "outputs/piksel_fdr.nc"
)

# Sen egimleri ve FDR sonuclari
egim = ds["sen_egimi"]
anlamli = ds["fdr_anlamli"].astype(bool)

# Yalnizca anlamli trendleri goster
harita = egim.where(anlamli)

# Renk skalasini sifira gore simetrik yap
limit = float(np.nanmax(np.abs(egim.values)))

# Haritayi ciz
fig, ax = plt.subplots(figsize=(10, 6))

harita.plot.pcolormesh(
    ax=ax,
    x="lon",
    y="lat",
    cmap="RdBu",
    vmin=-limit,
    vmax=limit,
    cbar_kwargs={
        "label": "Kar ortusu degisimi (% puan / 10 yil)"
    }
)

ax.set_title(
    "Dogu Anadolu - Kar Ortusu Trendleri\n"
    "Sentetik Veri | FDR = 0.10"
)

ax.set_xlabel("Boylam")
ax.set_ylabel("Enlem")
ax.grid(alpha=0.2)

# Haritayi kaydet
Path("outputs").mkdir(exist_ok=True)

plt.savefig(
    "outputs/kar_trend_haritasi.png",
    dpi=200,
    bbox_inches="tight"
)

plt.show()

ds.close()

print("HARITA BASARIYLA OLUSTURULDU!")
