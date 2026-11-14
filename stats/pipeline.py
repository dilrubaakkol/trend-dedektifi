"""Trend Dedektifi - L3: L2 mevsim serilerinden piksel bazli trend urunu.

Calistirma (proje kokunden):
    python -m stats.pipeline

Bu dosya stats/trend_tests.py dosyasini DEGISTIRMEZ.
"""
from pathlib import Path

import numpy as np
import xarray as xr
from statsmodels.stats.multitest import multipletests

from stats.trend_tests import trend_analizi


MEVSIMLER = ("yillik", "kis", "ilkbahar", "yaz", "sonbahar")
# Ilk adimda sadece "kis" test edecegiz; sonra besini acacagiz.
ILK_TEST_MEVSIMLERI = ("kis",)


def l3_uret(l2: xr.Dataset, mevsimler=ILK_TEST_MEVSIMLERI,
             min_yil: int = 12, alpha_fdr: float = 0.10) -> xr.Dataset:
    """L2 mevsim Dataset'inden L3 trend Dataset'i uret.

    Sonuc her mevsim icin (lat, lon) izgarasinda hesaplanir.
    Yalnizca gecerli p degerleri FDR'ye katilir.
    """
    mevsimler = tuple(mevsimler)
    if not mevsimler or any(m not in MEVSIMLER for m in mevsimler):
        raise ValueError("Gecersiz mevsim listesi")
    for mevsim in mevsimler:
        if mevsim not in l2.data_vars:
            raise KeyError(f"L2 dosyasinda '{mevsim}' bulunamadi")
        if set(l2[mevsim].dims) != {"yil", "lat", "lon"}:
            raise ValueError(f"'{mevsim}' boyutlari yil,lat,lon olmali")

    ilk = l2[mevsimler[0]].transpose("yil", "lat", "lon")
    lat, lon = ilk.lat.values, ilk.lon.values
    uyumsuz = [m for m in mevsimler
               if not (np.array_equal(l2[m].lat.values, lat)
                       and np.array_equal(l2[m].lon.values, lon))]
    if uyumsuz:
        raise ValueError(f"Mevsim koordinatlari ayni degil: {uyumsuz}")

    boyut = (len(mevsimler), len(lat), len(lon))
    sayisal_alanlar = (
        "egim_10yil", "ci_alt", "ci_ust", "p_mk", "p_mk_kontrol",
        "n", "n_etkin", "r1"
    )
    sonuc_dizileri = {
        ad: np.full(boyut, np.nan, dtype=np.float64)
        for ad in sayisal_alanlar
    }
    # Bunlar yeni belgede isteniyor; henuz hesaplanmadigi icin NaN.
    sonuc_dizileri["p_ttest"] = np.full(boyut, np.nan)
    sonuc_dizileri["yil_sayisi_gereken"] = np.full(boyut, np.nan)
    sonuc_dizileri["anlamli_fdr"] = np.zeros(boyut, dtype=np.int8)
    sonuc_dizileri["belirsiz"] = np.zeros(boyut, dtype=np.int8)
    sonuc_dizileri["gecerli_test"] = np.zeros(boyut, dtype=np.int8)

    for k, mevsim in enumerate(mevsimler):
        alan = l2[mevsim].transpose("yil", "lat", "lon")
        for i in range(len(lat)):
            for j in range(len(lon)):
                seri = alan.isel(lat=i, lon=j)
                # trend_analizi yetersiz veri ve sabit serileri zaten yonetir.
                deger = trend_analizi(seri, min_yil=min_yil)
                for ad in sayisal_alanlar:
                    if ad in deger and deger[ad] is not None:
                        sonuc_dizileri[ad][k, i, j] = float(deger[ad])
                if deger.get("durum") in ("ok", "sabit_seri"):
                    sonuc_dizileri["gecerli_test"][k, i, j] = 1
                    sonuc_dizileri["belirsiz"][k, i, j] = int(
                        bool(deger.get("belirsiz", False))
                    )

        p = sonuc_dizileri["p_mk"][k]
        gecerli = (sonuc_dizileri["gecerli_test"][k] == 1) & np.isfinite(p)
        if np.any(gecerli):
            red, p_duz, _, _ = multipletests(
                p[gecerli], alpha=alpha_fdr, method="fdr_bh"
            )
            sonuc_dizileri["anlamli_fdr"][k][gecerli] = red.astype(np.int8)
            if "p_duzeltilmis" not in sonuc_dizileri:
                sonuc_dizileri["p_duzeltilmis"] = np.full(boyut, np.nan)
            sonuc_dizileri["p_duzeltilmis"][k][gecerli] = p_duz

        print(f"{mevsim}: "
              f"gecerli={int(gecerli.sum())}, "
              f"FDR_anlamli={int(sonuc_dizileri['anlamli_fdr'][k].sum())}")

    if "p_duzeltilmis" not in sonuc_dizileri:
        sonuc_dizileri["p_duzeltilmis"] = np.full(boyut, np.nan)

    sonuc = xr.Dataset(
        data_vars={
            ad: (("mevsim", "lat", "lon"), deger)
            for ad, deger in sonuc_dizileri.items()
        },
        coords={"mevsim": list(mevsimler), "lat": lat, "lon": lon},
    )
    sonuc.attrs.update({
        "urun_katmani": "L3_trend",
        "yontem": "Theil-Sen; Hamed-Rao MK; Benjamini-Hochberg FDR",
        "alpha_fdr": alpha_fdr,
        "min_yil": min_yil,
        "kaynak_turu": str(l2.attrs.get("veri_turu", "belirtilmedi")),
        "dogrulama_durumu": "prototip; kapsamli bilimsel testler bekleniyor",
        "eksik_hesaplamalar": "p_ttest; yil_sayisi_gereken",
        "fdr_kapsami": "girilen L2 alaninin gecerli hucreleri",
    })
    birim = ilk.attrs.get("units", l2.attrs.get("units", "bilinmiyor"))
    sonuc["egim_10yil"].attrs["units"] = f"{birim}/10_yil"
    sonuc["p_ttest"].attrs["status"] = "not_implemented"
    sonuc["yil_sayisi_gereken"].attrs["status"] = "not_implemented"
    sonuc["anlamli_fdr"].attrs["note"] = "1=anlamli, 0=anlamli degil/yetersiz; gecerli_test alanini da kontrol edin"
    return sonuc


def main() -> None:
    giris = Path("cache/urun/L2_anomali/kar_ortusu__ORNEK__mevsim.nc")
    cikis = Path("cache/urun/L3_trend/kar_ortusu__ORNEK__trend.nc")
    if not giris.is_file():
        raise FileNotFoundError(f"L2 dosyasi yok: {giris}")

    with xr.open_dataset(giris) as l2:
        sonuc = l3_uret(l2, mevsimler=ILK_TEST_MEVSIMLERI)
    cikis.parent.mkdir(parents=True, exist_ok=True)
    sonuc.to_netcdf(cikis)
    print(f"L3 KAYDEDILDI: {cikis}")
    print("Boyutlar:", dict(sonuc.sizes))


if __name__ == "__main__":
    main()
