"""L2: hücre bazında trend katmanı (Kişi 2).

    python -m stats.l2 --surum v0.1
    python -m stats.l2 --surum v0.1 --dosyalar sicaklik_2m__MERRA2,yagis__GPM   # yalnız bunlar
    python -m stats.l2 --surum v0.1 --yalniz-isaretler   # anlamli'yı yeniden türet, uyarılar, kaynak uyumu, OZET
                                                         # (eğim/GA/p değişmez)

Girdi : outputs/trend-dedektifi-turkiye-<surum>/L1_kup/ (ICINDEKILER.csv'deki dosyalar, rakım hariç)
Çıktı : outputs/trend-dedektifi-turkiye-<surum>/L2_trend/
        <degisken>__<urun>__trend.nc     boyutlar (mevsim, lat, lon)
        <degisken>__kaynak_uyumu.nc      yagis, sicaklik_2m; boyutlar (mevsim, lat, lon)
        OZET.csv                         dosya × mevsim özeti

Şema: docs/sozlesmeler.md bölüm 2.1. Yöntem: stats/trend_tests.py, seriler: stats/preprocessing.py.
"""

from __future__ import annotations

import argparse
import csv
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from stats.preprocessing import (EKSIK_ORAN_ESIK, MEVSIMLER, SURUM, TOPLANANLAR, donem_serisi, eksik_esigi,
                                 paket_koku)
from stats.trend_tests import _trend_np, anlamli_kural, bh_fdr

ALFA_FDR = 0.10
MIN_YIL = 12
L2_DEGISKENLERI = ("sen_egimi", "ga_alt", "ga_ust", "p_mk", "etkin_n", "gereken_yil")
KAYNAK_UYUMU = {"yagis": ["GPM", "GLDAS", "MERRA2"], "sicaklik_2m": ["MERRA2", "GLDAS"]}
OZET_COLS = ["dosya", "mevsim", "kara_hucre", "anlamli_artan_yuzde", "anlamli_azalan_yuzde",
             "medyan_egim", "egim_birimi", "trend_uyarisi", "mk_yedek_hucre"]

# Trend güvenilirliği uyarıları (değerler silinmez; yalnız attr ve OZET'e yazılır).
# Anahtar: (degisken, dosya kodu); değer: [(mevsim ya da None = tüm mevsimler, metin)].
# Metindeki {kara_hucre}, o mevsimde trendi hesaplanan kara hücresi sayısıyla doldurulur.
_GLDAS_UYARI = ("GLDAS-2.1 zorlama verisi homojen olmayabilir; trend için MERRA2/GPM tercih edin "
                "(MERRA2'den %50 hızlı ısınma, yağışta 2,5 kat negatif eğim)")
_MODIS_LST_UYARI = ("Terra sensör kayması olasılığı doğrulanmadı; gündüz-gece farkını yorumlamadan önce "
                    "kontrol edin")
_KIS_SEYREK = "kar/bulut nedeniyle kış serisi seyrek ({kara_hucre} hücre)"
TREND_UYARILARI = {
    **{(v, "GLDAS"): [(None, _GLDAS_UYARI)] for v in ("sicaklik_2m", "yagis", "taban_akisi", "yuzey_akisi")},
    **{(v, "MOD11C3"): [(None, _MODIS_LST_UYARI)] for v in ("yuzey_sicakligi_gunduz", "yuzey_sicakligi_gece")},
    **{(v, "MOD13C2"): [("kis", _KIS_SEYREK)] for v in ("ndvi", "evi")},
}
SERI_TANIMI = {"yillik": "Ocak–Aralık", "kis": "Aralık(Y−1)–Şubat(Y)", "ilkbahar": "Mart–Mayıs",
               "yaz": "Haziran–Ağustos", "sonbahar": "Eylül–Kasım"}
YONTEM_ATTRS = {
    "mk_yontemi": "Hamed-Rao 1998 (otokorelasyon düzeltmeli Mann-Kendall)",
    "egim_yontemi": "Sen (Theil-Sen) eğimi, birim/10 yıl",
    "ga_yontemi": ("%95 Sen aralığı × √(n/n_etkin) × t0.975(n_etkin−2)/t0.975(n−2); "
                   "n_etkin = n(1−r1)/(1+r1), r1 = r1_ham + (1+4·r1_ham)/n, r1 ≤ 0,95"),
    "fdr_yontemi": "Benjamini-Hochberg, her mevsim için Türkiye kara hücreleri üzerinden",
    "alfa_fdr": ALFA_FDR,
    "gereken_yil_yontemi": "Weatherhead vd. 1998; yılda bir değerli seride σ_N × √12",
    "eksik_veri_kurali": f"yıl/mevsimde eksik ay oranı > {EKSIK_ORAN_ESIK} ise NaN; en az {MIN_YIL} geçerli yıl",
    "anlamlilik_kurali": f"anlamli = 1 ⇔ p_fdr ≤ {ALFA_FDR} ve %95 genişletilmiş GA sıfırı dışlıyor",
}
ANLAMLI_ADI = f"p_fdr ≤ {ALFA_FDR} ve GA sıfırı dışlıyor"


def _eksik_kurali(urun: str | None) -> str:
    """``eksik_veri_kurali`` attr metni (ürüne göre eşik)."""
    y, m = eksik_esigi(urun, "yillik"), eksik_esigi(urun, "kis")
    return (f"eksik ay oranı yıllıkta > {y:.2f}, mevsimde > {m:.2f} ise NaN; en az {MIN_YIL} geçerli yıl"
            + (" (ürüne özel eşik; bkz. stats/preprocessing.py)" if (y, m) != (EKSIK_ORAN_ESIK,) * 2 else ""))


def _hucre(y, x, min_yil=MIN_YIL):
    """Tek hücre: (sen_egimi, ga_alt, ga_ust, p_mk, etkin_n, gereken_yil, mk_yedek); yetersizse NaN."""
    r = _trend_np(x, y, min_yil=min_yil, kontrol=False)
    if r["durum"] == "yetersiz_veri":
        return (np.nan,) * 6 + (0.0,)
    return (r["egim_10yil"], r["ci_alt"], r["ci_ust"], r["p_mk"], r["n_etkin"], r["gereken_yil"],
            float(r.get("mk_yedek", False)))


def hucre_trendleri(seri: xr.DataArray, min_yil: int = MIN_YIL) -> xr.Dataset:
    """(yil, lat, lon) seriden hücre başına trend alanları (xr.apply_ufunc, vectorize=True)."""
    outs = xr.apply_ufunc(
        _hucre, seri, seri["yil"].astype(float),
        input_core_dims=[["yil"], ["yil"]], output_core_dims=[[]] * 7,
        vectorize=True, kwargs={"min_yil": min_yil}, output_dtypes=[float] * 7,
    )
    ds = xr.Dataset({ad: o.astype("float32") for ad, o in zip(L2_DEGISKENLERI, outs)})
    ds["mk_yedek"] = outs[6].astype("int8")  # 1 = Hamed-Rao tanımsız, düzeltmesiz MK kullanıldı
    return ds


def fdr_katmani(p: np.ndarray, maske: np.ndarray, ga_alt: np.ndarray, ga_ust: np.ndarray,
                alfa: float = ALFA_FDR):
    """Maskeli hücrelerde BH-FDR ve anlamlılık kuralı (``trend_tests.anlamli_kural``).

    Döndürür (p_fdr, anlamli int8: 1/0, maske dışı ya da p NaN → −1).
    """
    pm = np.where(maske, p, np.nan)
    q, _ = bh_fdr(pm, alfa)
    return q.astype("float32"), anlamli_kural(q, ga_alt, ga_ust, alfa)


def kara_maskesi(da: xr.DataArray) -> np.ndarray:
    """Türkiye kara hücreleri (hücre merkezi kuralı; data.regions.domain_mask)."""
    from data.regions import domain_mask
    return domain_mask("land", da["lat"].values, da["lon"].values)


def egim_birimi(birim: str, degisken: str) -> tuple[str, dict]:
    """Eğim birimi ve mevsim başına seri birimi. Toplanan değişkende seri = dönem toplamıdır."""
    if degisken in TOPLANANLAR and birim.endswith("/ay"):
        kok = birim[: -len("/ay")]
        seri = {m: f"{kok}/{'yıl' if m == 'yillik' else 'mevsim'}" for m in MEVSIMLER}
        return f"{kok}/dönem / 10 yıl", seri
    return f"{birim} / 10 yıl", {m: birim for m in MEVSIMLER}


def l2_dosya(da: xr.DataArray, degisken: str, maske: np.ndarray | None = None,
             mevsimler: dict = MEVSIMLER, alfa: float = ALFA_FDR, min_yil: int = MIN_YIL,
             urun: str | None = None) -> xr.Dataset:
    """Bir L1 küpünden L2 Dataset'i (mevsim, lat, lon). attrs: L1 attrs + yöntem alanları.

    urun: dosya kodu (ör. "GRACE"); verilmezse ``kaynak_dosya`` attr'ından okunur. Eksik ay eşiğini seçer.
    """
    maske = kara_maskesi(da) if maske is None else np.asarray(maske, bool)
    if urun is None and "__" in str(da.attrs.get("kaynak_dosya", "")):
        urun = str(da.attrs["kaynak_dosya"]).rsplit(".", 1)[0].split("__")[1]
    toplama = degisken in TOPLANANLAR
    parcalar = []
    for ad, aylar in mevsimler.items():
        seri = donem_serisi(da, aylar, toplama=toplama, kis=(ad == "kis"), eksik_esik=eksik_esigi(urun, ad))
        ds = hucre_trendleri(seri, min_yil)
        yedek = int((ds["mk_yedek"].values == 1).sum())
        ds = ds.drop_vars("mk_yedek")
        p_fdr, anlamli = fdr_katmani(ds["p_mk"].values, maske, ds["ga_alt"].values, ds["ga_ust"].values, alfa)
        ds["p_fdr"] = (("lat", "lon"), p_fdr)
        ds["anlamli"] = (("lat", "lon"), anlamli)
        gecerli_yil = seri["yil"].values[np.isfinite(seri.where(maske)).any(dim=("lat", "lon")).values]
        ds.attrs["_donem"] = f"{gecerli_yil.min()}–{gecerli_yil.max()}" if gecerli_yil.size else "yok"
        ds.attrs["_yedek"] = yedek
        parcalar.append(ds.expand_dims(mevsim=[ad]))
    out = xr.concat(parcalar, dim="mevsim").transpose("mevsim", "lat", "lon")
    out["anlamli"] = out["anlamli"].astype("int8")

    birim = str(da.attrs.get("units", ""))
    eb, seri_birimi = egim_birimi(birim, degisken)
    for v in ("sen_egimi", "ga_alt", "ga_ust"):
        out[v].attrs["units"] = eb
    out["sen_egimi"].attrs["long_name"] = "Sen eğimi"
    out["ga_alt"].attrs["long_name"] = "Eğimin %95 genişletilmiş güven aralığı, alt"
    out["ga_ust"].attrs["long_name"] = "Eğimin %95 genişletilmiş güven aralığı, üst"
    out["p_mk"].attrs.update(units="1", long_name="Hamed-Rao Mann-Kendall p")
    out["p_fdr"].attrs.update(units="1", long_name="Benjamini-Hochberg q değeri")
    out["anlamli"].attrs.update(long_name=ANLAMLI_ADI, flag_values="-1 0 1",
                                flag_meanings="maske_disi_ya_da_hesaplanamadi anlamli_degil anlamli")
    out["etkin_n"].attrs.update(units="yıl", long_name="Etkin örneklem büyüklüğü")
    out["gereken_yil"].attrs.update(units="yıl", long_name="Weatherhead gereken yıl sayısı")

    attrs = {k: v for k, v in da.attrs.items() if k not in ("units", "long_name", "kaynak_dosya")}
    attrs.update(YONTEM_ATTRS)
    attrs.update(
        alfa_fdr=alfa,
        katman="L2",
        degisken=degisken,
        kaynak_dosya=da.attrs.get("kaynak_dosya", ""),
        birim=birim,
        egim_birimi=eb,
        seri_birimi="; ".join(f"{m}: {b}" for m, b in seri_birimi.items()),
        seri_tanimi="; ".join(f"{m}: {SERI_TANIMI.get(m, '')}" for m in mevsimler),
        donem="; ".join(f"{m}: {p.attrs['_donem']}" for m, p in zip(mevsimler, parcalar)),
        min_yil=min_yil,
        eksik_veri_kurali=_eksik_kurali(urun),
        mk_yedek_hucre="; ".join(f"{m}: {p.attrs['_yedek']}" for m, p in zip(mevsimler, parcalar)),
        olusturma_tarihi=date.today().isoformat(),
    )
    out.attrs = attrs
    for k in ("lat", "lon"):
        out[k].attrs = dict(da[k].attrs)
    out["mevsim"].attrs["long_name"] = "dönem (yillik, kis, ilkbahar, yaz, sonbahar)"
    return out


def yaz_nc(ds: xr.Dataset, path: Path) -> Path:
    """L2 NetCDF yazar (float32 sıkıştırılmış, NaN dolgu; int alanlar dolgusuz)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    enc = {}
    for v in ds.data_vars:
        if np.issubdtype(ds[v].dtype, np.integer):
            enc[v] = {"zlib": True, "complevel": 4, "_FillValue": None}
        else:
            enc[v] = {"zlib": True, "complevel": 4, "_FillValue": np.float32(np.nan), "dtype": "float32"}
    clean = {k: (v.item() if isinstance(v, np.generic) else v) for k, v in ds.attrs.items()}
    ds = ds.copy()
    ds.attrs = {k: v for k, v in clean.items() if v is not None}
    tmp = path.with_suffix(".nc.tmp")
    ds.to_netcdf(tmp, encoding=enc, engine="netcdf4")
    tmp.replace(path)
    return path


def _kara_hucre(ds: xr.Dataset, mevsim: str, maske: np.ndarray) -> int:
    """Mevsimde trendi hesaplanan (p_mk sonlu) kara hücresi sayısı."""
    return int((maske & np.isfinite(ds["p_mk"].sel(mevsim=mevsim).values)).sum())


def trend_uyarisi(degisken: str, urun: str, ds: xr.Dataset, maske: np.ndarray) -> str:
    """Dosyanın ``trend_uyarisi`` attr metni ("" = uyarı yok).

    Biçim: uyarılar " | " ile ayrılır. Tüm mevsimler için geçerli uyarı düz metin, yalnız bir
    mevsime ait uyarı "[mevsim] metin" biçimindedir.
    """
    parcalar = []
    for mevsim, metin in TREND_UYARILARI.get((degisken, urun), []):
        if mevsim is None:
            parcalar.append(metin)
        elif mevsim in ds["mevsim"].values:
            parcalar.append(f"[{mevsim}] " + metin.format(kara_hucre=_kara_hucre(ds, mevsim, maske)))
    return " | ".join(parcalar)


def mevsim_uyarisi(attr: str, mevsim: str) -> str:
    """``trend_uyarisi`` attr'ından bir mevsime düşen uyarılar (tüm-mevsim uyarıları dahil)."""
    out = []
    for u in filter(None, (x.strip() for x in (attr or "").split(" | "))):
        if u.startswith("["):
            m, _, metin = u[1:].partition("] ")
            if m == mevsim:
                out.append(metin)
        else:
            out.append(u)
    return " | ".join(out)


def yedek_sayilari(attr: str) -> dict:
    """``mk_yedek_hucre`` attr'ı ("yillik: 1; kis: 0; …") → {mevsim: sayı}."""
    out = {}
    for parca in filter(None, (x.strip() for x in (attr or "").split(";"))):
        m, _, n = parca.partition(":")
        out[m.strip()] = int(n)
    return out


def ozet_satirlari(ds: xr.Dataset, dosya: str, maske: np.ndarray) -> list[dict]:
    """OZET.csv satırları: kara hücre, anlamlı artan/azalan yüzdesi, medyan eğim, uyarı, MK yedeği."""
    yedek = yedek_sayilari(ds.attrs.get("mk_yedek_hucre", ""))
    rows = []
    for m in ds["mevsim"].values:
        s = ds.sel(mevsim=m)
        egim, anl = s["sen_egimi"].values, s["anlamli"].values
        hesap = maske & np.isfinite(s["p_mk"].values)
        n = int(hesap.sum())
        rows.append({
            "dosya": dosya, "mevsim": str(m), "kara_hucre": n,
            "anlamli_artan_yuzde": round(100 * float(((anl == 1) & (egim > 0)).sum()) / n, 1) if n else "",
            "anlamli_azalan_yuzde": round(100 * float(((anl == 1) & (egim < 0)).sum()) / n, 1) if n else "",
            "medyan_egim": round(float(np.nanmedian(egim[hesap])), 4) if n else "",
            "egim_birimi": ds["sen_egimi"].attrs.get("units", ""),
            "trend_uyarisi": mevsim_uyarisi(ds.attrs.get("trend_uyarisi", ""), str(m)),
            "mk_yedek_hucre": yedek.get(str(m), ""),
        })
    return rows


def _veri_donemi(da: xr.DataArray, maske: np.ndarray) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Maske içinde en az bir geçerli hücresi olan ilk ve son ay."""
    ok = da.where(maske).notnull().any(dim=("lat", "lon")).values
    t = pd.DatetimeIndex(da["time"].values[ok])
    return t[0], t[-1]


def kaynak_uyumu(dalar: dict[str, xr.DataArray], degisken: str, maske: np.ndarray,
                 hazir: dict | None = None, alfa: float = ALFA_FDR, min_yil: int = MIN_YIL,
                 mevsimler: dict = MEVSIMLER) -> xr.Dataset:
    """Ürünler arası kaynak uyumu (mevsim, lat, lon).

    Ortak dönem = her ürünün veri döneminin kesişimi; her ürün bu döneme kırpılıp L2 yeniden
    hesaplanır (dönemi zaten ortak dönemle aynı olan ürün için ``hazir`` içindeki sonuç kullanılır).
    m = hücrede trendi hesaplanabilen ürün sayısı; k = anlamlı (p_fdr ≤ alfa) ve aynı yönde olan
    en büyük ürün grubu. Maske dışı hücrede k = m = −1.
    """
    hazir = hazir or {}
    donemler = {u: _veri_donemi(da, maske) for u, da in dalar.items()}
    bas = max(d[0] for d in donemler.values())
    son = min(d[1] for d in donemler.values())
    sonuclar = {}
    for u, da in dalar.items():
        if u in hazir and donemler[u] == (bas, son):  # kırpmak sonucu değiştirmez
            sonuclar[u] = hazir[u]
        else:
            kesit = da.sel(time=slice(bas, son))
            kesit.attrs = da.attrs
            sonuclar[u] = l2_dosya(kesit, degisken, maske, mevsimler, alfa, min_yil, urun=u)
    anl = np.stack([sonuclar[u]["anlamli"].values for u in dalar])          # (ürün, mevsim, lat, lon)
    egim = np.stack([sonuclar[u]["sen_egimi"].values for u in dalar])
    m = (anl >= 0).sum(axis=0)
    k = np.maximum(((anl == 1) & (egim > 0)).sum(axis=0), ((anl == 1) & (egim < 0)).sum(axis=0))
    # İşaret uyumu: anlamlılığa bakmadan aynı işaretli en büyük grup / m
    gecerli = anl >= 0
    ayni = np.maximum((gecerli & (egim > 0)).sum(axis=0), (gecerli & (egim < 0)).sum(axis=0))
    disarida = ~np.broadcast_to(maske, m.shape)
    with np.errstate(invalid="ignore", divide="ignore"):
        isaret = np.where(disarida | (m == 0), np.nan, ayni / np.maximum(m, 1)).astype("float32")
    m = np.where(disarida, -1, m).astype("int16")
    k = np.where(disarida, -1, k).astype("int16")
    ref = next(iter(sonuclar.values()))
    ds = xr.Dataset({"k": (("mevsim", "lat", "lon"), k), "m": (("mevsim", "lat", "lon"), m),
                     "isaret_uyumu": (("mevsim", "lat", "lon"), isaret)},
                    coords={"mevsim": ref["mevsim"], "lat": ref["lat"], "lon": ref["lon"]})
    ds["k"].attrs["long_name"] = "anlamlı ve aynı yönde trend veren en büyük ürün grubu"
    ds["m"].attrs["long_name"] = "trendi hesaplanabilen ürün sayısı"
    ds["isaret_uyumu"].attrs.update(units="1", long_name=(
        "anlamlılığa bakmadan aynı işaretli en büyük ürün grubu / m; maske dışı ya da m = 0 ise NaN"))
    ilk = next(iter(dalar.values())).attrs
    ds.attrs = {
        "katman": "L2", "degisken": degisken, "urunler": ", ".join(dalar),
        "ortak_donem": f"{bas:%Y-%m} … {son:%Y-%m}", "alfa_fdr": alfa,
        "tanim": ("k/m: m ürünün k tanesi aynı yönde anlamlı trend veriyor; maske dışı −1. "
                  "isaret_uyumu: anlamlılığa bakmadan aynı işaretli en büyük grup / m"),
        "urun_surumu": ilk.get("urun_surumu", ""), "veri_seti_doi": ilk.get("veri_seti_doi", ""),
        "lisans": ilk.get("lisans", ""), "olusturma_tarihi": date.today().isoformat(),
        "kaynak_doi": "; ".join(f"{u}: {da.attrs.get('doi', '')}" for u, da in dalar.items()),
    }
    return ds


def icindekiler(kok: Path) -> pd.DataFrame:
    """L1_kup/ICINDEKILER.csv; rakım (kademe 0 / sabit) hariç."""
    df = pd.read_csv(kok / "L1_kup" / "ICINDEKILER.csv", encoding="utf-8-sig", dtype={"kademe": str})
    return df[(df["donem"] != "sabit") & (df["kademe"] != "0")].reset_index(drop=True)


def uret(surum: str = SURUM, kok: Path | None = None, dosyalar: list[str] | None = None,
         alfa: float = ALFA_FDR, min_yil: int = MIN_YIL) -> Path:
    """L2 katmanını üretir; L2_trend klasörünün yolunu döndürür."""
    paket = paket_koku(surum, kok)
    out_dir = paket / "L2_trend"
    out_dir.mkdir(parents=True, exist_ok=True)
    tablo = icindekiler(paket)
    if dosyalar:
        tablo = tablo[tablo["dosya"].str.replace(".nc", "", regex=False).isin(dosyalar)]
    ozet, hazir, dalar_hepsi, maske = [], {}, {}, None
    t0 = time.time()
    for _, r in tablo.iterrows():
        t1 = time.time()
        stem = r["dosya"][:-3]
        degisken, urun = stem.split("__")
        with xr.open_dataset(paket / "L1_kup" / r["dosya"]) as ds:
            ds = ds.load()
        da = ds[degisken]
        da.attrs = {**ds.attrs, **da.attrs, "kaynak_dosya": r["dosya"]}
        if maske is None:
            maske = kara_maskesi(da)
        res = l2_dosya(da, degisken, maske, alfa=alfa, min_yil=min_yil, urun=urun)
        _uyari_ekle(res, degisken, urun, maske)
        yaz_nc(res, out_dir / f"{stem}__trend.nc")
        ozet += ozet_satirlari(res, r["dosya"], maske)
        hazir[(degisken, urun)] = res
        dalar_hepsi[(degisken, urun)] = da
        print(f"  {stem}__trend.nc  ({time.time() - t1:.0f} sn)")
    if dosyalar:
        # Yalnız bazı dosyalar yeniden hesaplandı: OZET ve kaynak uyumu tüm dosyalardan yenilenir
        print(f"L2: {len(tablo)} dosya yeniden hesaplandı ({time.time() - t0:.0f} sn); OZET ve kaynak uyumu "
              "tüm dosyalar için yenileniyor")
        return isaretle(surum, kok, alfa, min_yil)
    _kaynak_ve_ozet(out_dir, hazir, dalar_hepsi, maske, ozet, alfa, min_yil)
    print(f"L2 tamam: {len(tablo)} dosya, {time.time() - t0:.0f} sn → {out_dir}")
    return out_dir


def anlamli_yeniden(res: xr.Dataset, alfa: float = ALFA_FDR) -> xr.Dataset:
    """Var olan L2 Dataset'inde ``anlamli``'yı p_fdr ve GA'dan yeniden türetir (yerinde ve döndürür).

    Eğim, GA, p ve p_fdr değişmez; yalnız ``anlamli`` ve kuralı anlatan attrs güncellenir.
    """
    res["anlamli"] = (res["anlamli"].dims,
                      anlamli_kural(res["p_fdr"].values, res["ga_alt"].values, res["ga_ust"].values, alfa))
    res["anlamli"].attrs.update(long_name=ANLAMLI_ADI, flag_values="-1 0 1",
                                flag_meanings="maske_disi_ya_da_hesaplanamadi anlamli_degil anlamli")
    res.attrs["anlamlilik_kurali"] = YONTEM_ATTRS["anlamlilik_kurali"]
    return res


def _uyari_ekle(res: xr.Dataset, degisken: str, urun: str, maske: np.ndarray) -> None:
    """``trend_uyarisi`` attr'ını ekler ya da (uyarı yoksa) kaldırır (yerinde)."""
    metin = trend_uyarisi(degisken, urun, res, maske)
    if metin:
        res.attrs["trend_uyarisi"] = metin
    else:
        res.attrs.pop("trend_uyarisi", None)


def _kaynak_ve_ozet(out_dir: Path, hazir: dict, dalar_hepsi: dict, maske: np.ndarray, ozet: list,
                    alfa: float, min_yil: int) -> None:
    """Kaynak uyumu dosyalarını ve OZET.csv'yi yazar."""
    for degisken, urunler in KAYNAK_UYUMU.items():
        dalar = {u: dalar_hepsi[(degisken, u)] for u in urunler if (degisken, u) in dalar_hepsi}
        if len(dalar) < 2:
            continue
        t1 = time.time()
        ku = kaynak_uyumu(dalar, degisken, maske, {u: hazir[(degisken, u)] for u in dalar}, alfa, min_yil)
        yaz_nc(ku, out_dir / f"{degisken}__kaynak_uyumu.nc")
        print(f"  {degisken}__kaynak_uyumu.nc  ({ku.attrs['urunler']}; {ku.attrs['ortak_donem']}; "
              f"{time.time() - t1:.0f} sn)")
    with open(out_dir / "OZET.csv", "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=OZET_COLS)
        wr.writeheader()
        wr.writerows(ozet)


def isaretle(surum: str = SURUM, kok: Path | None = None, alfa: float = ALFA_FDR,
             min_yil: int = MIN_YIL) -> Path:
    """Var olan L2 dosyalarını trendleri yeniden hesaplamadan günceller.

    Trend dosyalarında ``anlamli`` p_fdr ve GA'dan yeniden türetilir (``anlamli_kural``) ve
    ``trend_uyarisi`` attr'ı güncellenir; eğim, GA, p ve p_fdr değişmez. Kaynak uyumu (L1'den, ortak
    dönemde) ve OZET.csv yeniden yazılır. Sonuç, tam ``uret`` çalıştırmasıyla aynıdır.
    """
    paket = paket_koku(surum, kok)
    out_dir = paket / "L2_trend"
    ozet, hazir, dalar_hepsi, maske = [], {}, {}, None
    for _, r in icindekiler(paket).iterrows():
        stem = r["dosya"][:-3]
        degisken, urun = stem.split("__")
        yol = out_dir / f"{stem}__trend.nc"
        if not yol.exists():
            continue
        with xr.open_dataset(yol) as ds:
            res = ds.load()
        if maske is None:
            maske = kara_maskesi(res)
        anlamli_yeniden(res, alfa)
        _uyari_ekle(res, degisken, urun, maske)
        yaz_nc(res, yol)
        ozet += ozet_satirlari(res, r["dosya"], maske)
        hazir[(degisken, urun)] = res
        if urun in KAYNAK_UYUMU.get(degisken, []):
            with xr.open_dataset(paket / "L1_kup" / r["dosya"]) as l1:
                l1 = l1.load()
            da = l1[degisken]
            da.attrs = {**l1.attrs, **da.attrs, "kaynak_dosya": r["dosya"]}
            dalar_hepsi[(degisken, urun)] = da
        print(f"  işaretlendi: {yol.name}" + ("  [uyarı var]" if "trend_uyarisi" in res.attrs else ""))
    _kaynak_ve_ozet(out_dir, hazir, dalar_hepsi, maske, ozet, alfa, min_yil)
    return out_dir


def main(argv=None):
    ap = argparse.ArgumentParser(description="L2 hücre bazında trend katmanı.")
    ap.add_argument("--surum", default=SURUM)
    ap.add_argument("--kok", default=None, help="outputs kök klasörü (varsayılan: repo/outputs)")
    ap.add_argument("--dosyalar", default=None, help="virgülle: sicaklik_2m__MERRA2,yagis__GPM")
    ap.add_argument("--min-yil", type=int, default=MIN_YIL)
    ap.add_argument("--yalniz-isaretler", action="store_true",
                    help="trendleri yeniden hesaplamadan uyarıları, kaynak uyumunu ve OZET'i güncelle")
    a = ap.parse_args(argv)
    if a.yalniz_isaretler:
        isaretle(a.surum, Path(a.kok) if a.kok else None, min_yil=a.min_yil)
        return
    uret(a.surum, Path(a.kok) if a.kok else None,
         a.dosyalar.split(",") if a.dosyalar else None, min_yil=a.min_yil)


if __name__ == "__main__":
    main()
