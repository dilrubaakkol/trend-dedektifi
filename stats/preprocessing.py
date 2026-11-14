"""L1 aylık küplerinden yıllık ve mevsimlik seriler (Kişi 2).

Girdi: L1 yayın paketi ``outputs/trend-dedektifi-turkiye-<surum>/L1_kup/<degisken>__<urun>.nc``
(``python -m data.export``). Çıktı: ``yil`` boyutlu seriler; ``stats.trend_tests`` bunları kullanır.

Mevsimler: yillik (Oca–Ara), kis (Ara–Şub; Aralık bir sonraki kış yılına sayılır), ilkbahar (Mar–May),
yaz (Haz–Ağu), sonbahar (Eyl–Kas).

**Eksik veri kuralı** (``donem_serisi``):
- Bir yıl ya da mevsim için eksik ay oranı ``EKSIK_ORAN_ESIK`` (0,20) **üstündeyse** değer NaN olur.
  Ay hem NaN ise hem de zaman ekseninde hiç yoksa eksik sayılır.
  - Yıllık seride en çok 2 ay eksik olabilir (2/12 = 0,17); 3 ay eksikse (0,25) yıl düşer.
  - 3 aylık mevsimde tek bir eksik ay (1/3 = 0,33) bile mevsimi düşürür.
  - Örnekler: GPM 2025-09'da bittiği için 2025 yılı (3 ay eksik) ve 2025 sonbaharı düşer. GRACE
    2002-04'te başladığı için 2002 yılı düşer; GRACE/GRACE-FO arasındaki boşluk yılları da düşer.
    İlk kış (2001: Aralık 2000 yok) düşer.
- **Ürüne göre eşik** (``EKSIK_ESIK_URUN``, ``eksik_esigi``): GRACE/GRACE-FO için yıllıkta en az 6
  geçerli ay (eksik oran ≤ 0,50), mevsimde en az 2/3 ay (eksik oran ≤ 1/3). Gerekçe:
  - GRACE'in son yıllarında (yaklaşık 2011–2017) uydu bataryası yönetimi yüzünden birkaç ayda bir
    ay eksiktir.
  - 2017-07 … 2018-05 arasında GRACE → GRACE-FO geçiş boşluğu vardır.
  - Varsayılan 0,20 eşiğiyle 2011 ve 2013–2018 yılları düşüyor, yıllık seri 16 yıla iniyordu.
  - Ayrıca GRACE ayrık "ay ortası" çözümlerdir ve su depolama yavaş değişir. Bu yüzden 6 aylık
    ortalama yıllık düzeyi temsil eder.
- Ortalama alınan değişkenlerde eksik aylar atlanarak ortalama alınır.
- Toplanan değişkenlerde (``TOPLANANLAR``: yağış, buharlaşma, akışlar) toplam,
  "geçerli ayların ortalaması × dönemdeki ay sayısı" olur. Böylece bir ayı eksik yıl sistematik
  olarak küçük çıkmaz.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

REPO_ROOT = Path(__file__).resolve().parent.parent
SURUM = "v0.1"

# Toplanarak hesaplanacak değişkenler
TOPLANANLAR = {
    "yagis",
    "buharlasma",
    "yuzey_akisi",
    "taban_akisi"
}

MEVSIMLER = {
    "yillik": list(range(1, 13)),
    "kis": [12, 1, 2],
    "ilkbahar": [3, 4, 5],
    "yaz": [6, 7, 8],
    "sonbahar": [9, 10, 11]
}

EKSIK_ORAN_ESIK = 0.20

# Ürüne göre eksik ay eşiği (dosya kodu → {"yillik": eşik, "mevsim": eşik}); gerekçe modül açıklamasında
EKSIK_ESIK_URUN = {"GRACE": {"yillik": 0.50, "mevsim": 1 / 3}}


def eksik_esigi(urun: str | None, mevsim: str) -> float:
    """Ürün ve mevsim için izin verilen en büyük eksik ay oranı (varsayılan ``EKSIK_ORAN_ESIK``)."""
    e = EKSIK_ESIK_URUN.get(urun or "")
    if not e:
        return EKSIK_ORAN_ESIK
    return e["yillik"] if mevsim == "yillik" else e["mevsim"]


def paket_koku(surum: str = SURUM, kok: Path | None = None) -> Path:
    """Yayın paketinin kökü: outputs/trend-dedektifi-turkiye-<surum>/ (kok verilirse onun altı)."""
    return Path(kok or REPO_ROOT / "outputs") / f"trend-dedektifi-turkiye-{surum}"


def l1_oku(degisken: str, urun: str, surum: str = SURUM, kok: Path | None = None) -> xr.DataArray:
    """L1 küpünü (time, lat, lon) okur; dosya attrs'ı DataArray attrs'ına kopyalanır."""
    yol = paket_koku(surum, kok) / "L1_kup" / f"{degisken}__{urun}.nc"
    if not yol.exists():
        raise FileNotFoundError(f"{yol} yok. Önce: python -m data.export --surum {surum}")
    with xr.open_dataset(yol) as ds:
        ds = ds.load()
    da = ds[degisken]
    da.attrs = {**ds.attrs, **da.attrs, "kaynak_dosya": yol.name}
    return da


def donem_serisi(da, aylar, toplama=False, kis=False, eksik_esik=EKSIK_ORAN_ESIK):
    """Aylık seriden yıllık/mevsimlik seri: ilk boyut ``yil``, diğer boyutlar korunur (ör. lat, lon).

    Eksik veri kuralı: modül açıklaması.
    """

    # İstenen ayları seç
    secilen = da.where(
        da.time.dt.month.isin(aylar),
        drop=True
    )

    # Aralık sonraki kış yılına aittir
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

    # Her yıl/piksel için geçerli ay sayısı (zaman ekseninde olmayan ay da eksik sayılır)
    sayi = gruplar.count(dim="time")
    ortalama = gruplar.mean(dim="time", skipna=True)

    # Yağış gibi değişkenlerde toplam = geçerli ayların ortalaması × ay sayısı
    sonuc = ortalama * len(aylar) if toplama else ortalama

    # Eksik ay oranı eşik üstündeyse o dönem eksik sayılır
    sonuc = sonuc.where((len(aylar) - sayi) / len(aylar) <= eksik_esik + 1e-9)

    # Veri aralığındaki yıllar (kışta Aralık 2000 olmadığı için ilk kış verinin ilk yılı + 1)
    ilk_yil = int(da.time.dt.year.min()) + (1 if kis else 0)
    son_yil = int(da.time.dt.year.max())

    return sonuc.sel(
        yil=slice(ilk_yil, son_yil)
    ).transpose("yil", ...)  # ızgarada (yil, lat, lon); bölge serisinde (yil, bolge)


def l2_uret(da, degisken, urun=None):
    """Aylık klimatoloji, aylık anomali ve 5 dönem serisi (``MEVSIMLER``) üretir.

    urun: dosya kodu (ör. "GRACE"); eksik ay eşiği ``eksik_esigi(urun, mevsim)`` ile seçilir.
    """

    toplama = degisken in TOPLANANLAR

    # 1. Aylık klimatoloji
    klimatoloji = da.groupby(
        "time.month"
    ).mean(dim="time", skipna=True)

    # 2. Aylık anomali
    anomali = (
        da.groupby("time.month") - klimatoloji
    )

    # 3. Yıllık ve mevsimlik seriler
    seriler = xr.Dataset({
        ad: donem_serisi(
            da,
            aylar,
            toplama=toplama,
            kis=(ad == "kis"),
            eksik_esik=eksik_esigi(urun, ad)
        )
        for ad, aylar in MEVSIMLER.items()
    })

    seriler.attrs["degisken"] = degisken
    seriler.attrs["toplama_yontemi"] = (
        "toplam (geçerli ay ortalaması × ay sayısı)" if toplama else "ortalama"
    )
    seriler.attrs["eksik_veri_kurali"] = (f"eksik ay oranı > {eksik_esigi(urun, 'yillik'):.2f} (yıllık) / "
                                          f"{eksik_esigi(urun, 'kis'):.2f} (mevsim) ise NaN")
    for k in ("kaynak_dosya", "source_product", "urun_surumu", "kademe"):
        if k in da.attrs:
            seriler.attrs[k] = da.attrs[k]

    return klimatoloji, anomali, seriler


# İlk deneme: L1 paketindeki kar örtüsü
if __name__ == "__main__":

    kar = l1_oku("kar_ortusu", "MOD10CM")

    cikti = REPO_ROOT / "cache" / "urun" / "L2_anomali"
    cikti.mkdir(parents=True, exist_ok=True)

    klimatoloji, anomali, seriler = l2_uret(kar, "kar_ortusu")

    klimatoloji.to_netcdf(cikti / "kar_ortusu__MOD10CM__klimatoloji.nc")
    anomali.to_netcdf(cikti / "kar_ortusu__MOD10CM__anomali.nc")
    seriler.to_netcdf(cikti / "kar_ortusu__MOD10CM__mevsim.nc")

    print("L2 VERİ HAZIRLAMA TAMAMLANDI")
    print("Klimatoloji:", dict(klimatoloji.sizes))
    print("Anomali:", dict(anomali.sizes))
    print("Mevsimler:", list(seriler.data_vars))
    print("Geçerli yıl (yıllık, ilk hücre ortalaması):",
          int(np.isfinite(seriler["yillik"]).any(dim=("lat", "lon")).sum()))
