"""Sapma haritası v3: bitki takvimiyle sulama izi (v1 ve v2 dosyalarına dokunmaz).

    python -m physics.sapma_v3 --surum v0.1          # → <paket>/L4_iliski/sapma/…_v3_*.nc, kümeler
                                                     #   doğrulama katmanı varsa → <paket>/dogrulama/sapma_v3_*.csv

Sade anlatım:
- Türkiye'de yağmurla yetişen ekin (buğday, arpa) nisan–mayısta yeşerir, haziranda hasat edilir, temmuzda
  tarla kahverengidir. Sulanan ekin (pamuk, mısır, şeker pancarı) ise temmuz–ağustosta en yeşil hâlindedir.
- Yazı kurak geçen bir yer temmuz–ağustosta ilkbahardan yeşilse, yağmur bunu açıklayamaz. Bu "fiziksel
  beklentiden sapma" sulamayla tutarlı olabilir (doğrulanmadı; neden göstermez).
- Yazı yağışlı ya da yüksek yerlerde (Karadeniz ormanı, yaylalar) bitki doğal olarak yazın yeşildir; bu
  yüzden v3 skoru yalnız "kurak yaz" hücrelerinde hesaplanır. Kural fizikseldir, yer adı ya da kutu yoktur.

Bileşenler (her biri kurak yaz hücreleri arasında standartlaştırılır, z):
- ``z_takvim``  : iklimsel NDVI(Tem–Ağu) − NDVI(Nis–May). Yüksek = yazın ilkbahardan yeşil.
- ``z_kopukluk``: −r(yıllık yaz NDVI, aynı yılın Eki–Haz yağışı). Yağmurla yetişen bitkide yağışlı yıl yeşil
  yıldır (r > 0); sulanan bitki yağıştan kopuktur (r ≈ 0). Yüksek = yağıştan kopuk.

Yapılandırmalar (sonuçlar ve doğrulama katmanı görülmeden sabitlendi; ``KURAL_METNI``):
- ``v3_ana``         : z_takvim, kurak yaz hücreleri. **Ana yapılandırma.**
- ``v3_kopukluk``    : (z_takvim + z_kopukluk) / 2, kurak yaz hücreleri.
- ``v3_maskesiz``    : z_takvim, bütün kara hücreleri (kurak yaz koşulunun katkısını görmek için).
- duyarlılık (yalnız rapor): yaz yağışı eşiği 40 / 60 / 120 mm.

Keşif notu (dürüstlük için): kurak yaz eşikleri (80 mm, 1500 m) 0,25° L1 NDVI ve GPM yağışına bakılarak
seçildi (keşif sırasında 40 mm Konya ve Adana ovalarını dışarıda bırakıyordu). Doğrulama katmanlarına
(GFSAD1KCM, LGRIP30) eşik seçiminde hiç bakılmadı; bağımsız sınav onlardır.
"""

from __future__ import annotations

import argparse
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

KURAL_SURUMU = "sapma-v3 (2026-11-15)"
YAZ_AYLARI = (7, 8)               # Temmuz–Ağustos: sulanan yaz ekininin tepe dönemi
ILKBAHAR_AYLARI = (4, 5)          # Nisan–Mayıs: yağmurla yetişen kışlık tahılın tepe dönemi
SU_YILI_AYLARI = (10, 11, 12, 1, 2, 3, 4, 5, 6)   # Eki–Haz yağışı (yaz NDVI'sını besleyen yağış)
SU_YILI_MIN_AY = 9                # su yılının 9 ayı da dolu olmalı
KOPUKLUK_MIN_YIL = 10             # korelasyon için en az 10 yıl
YAZ_YAGIS_ESIK = 80.0             # mm, iklimsel Haz–Tem–Ağu toplamı < eşik → kurak yaz
RAKIM_ESIK = 1500.0               # m, rakım < eşik (yüksek yaylalarda yaz yeşilliği doğaldır)
DUYARLILIK_YAGIS = (40.0, 60.0, 120.0)
KUME_YUZDELIK = 90
YAPILANDIRMALAR = ("v3_ana", "v3_kopukluk", "v3_maskesiz")
DOSYALAR = {"025": "sapma_haritasi_v3_025.nc", "005": "sapma_haritasi_v3_005.nc"}
KUMELER = "sulama_izi_kumeleri_v3.csv"
DOGRULAMA_DOSYALARI = {   # <paket>/dogrulama/ altında; yalnız skor hesaplandıktan SONRA okunur
    "GFSAD1KCM": {"025": "sulanan_oran__GFSAD1KCM.nc", "005": "sulanan_oran__GFSAD1KCM__005.nc"},
    "LGRIP30": {"025": "sulanan_oran__LGRIP30.nc", "005": "sulanan_oran__LGRIP30__005.nc"},
}

UYARI = ("Doğrulanmadı; neden göstermez. Fiziksel beklentiden sapmadır: kurak yazda ilkbahardan yeşil kalan bitki "
         "sulamayla tutarlı olabilir; olası diğer açıklamalar kıyı nemi, yaz yağışı alan dağ eteği, sulak alan ve "
         "veri/ürün sorunudur.")

KURAL_METNI = f"""SAPMA HARİTASI v3 KURALI ({KURAL_SURUMU}; doğrulama katmanları görülmeden sabitlendi)

Kurak yaz hücresi: iklimsel Haz–Tem–Ağu yağışı (GPM) < {YAZ_YAGIS_ESIK:g} mm VE rakım (SRTM) < {RAKIM_ESIK:g} m.
z_takvim  = iklimsel NDVI(Tem–Ağu) − NDVI(Nis–May), kurak yaz hücreleri arasında z.
z_kopukluk = −r(yıllık Tem–Ağu NDVI, Eki–Haz yağışı), en az {KOPUKLUK_MIN_YIL} yıl; kurak yaz hücreleri arasında z.
Yapılandırmalar: v3_ana = z_takvim (kurak yaz) · v3_kopukluk = (z_takvim + z_kopukluk)/2 (kurak yaz) ·
  v3_maskesiz = z_takvim (bütün kara, kara hücreleri arasında z).
Kurak yaz dışındaki hücre skorsuzdur (değerlendirmede en düşük skoru alır; v2 ile aynı kural).
Duyarlılık (yalnız rapor): yaz yağışı eşiği {", ".join(f"{v:g}" for v in DUYARLILIK_YAGIS)} mm.
Doğrulama: physics.sapma_dogrulama ölçütleri (ROC AUC, precision@%5, hedef = sulanan oran ≥ 0,2), varsa
  GFSAD1KCM (2010) ve LGRIP30 (2015). Tanı (ana ölçüt değil): yalnız kurak yaz hücreleri içinde AUC.
Keşif notu: eşikler L1 NDVI ve yağışa bakılarak seçildi; doğrulama katmanlarına bakılmadı.
"""


# ---------------------------------------------------------------- bileşenler (saf numpy/xarray)
def aylar_ortalamasi(da: xr.DataArray, aylar: tuple[int, ...]) -> np.ndarray:
    """İklimsel ay ortalamalarının (her ayın uzun dönem ortalaması) ortalaması → (lat, lon)."""
    iklim = da.groupby("time.month").mean("time", skipna=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return iklim.sel(month=list(aylar)).mean("month", skipna=False).values.astype(float)


def yaz_yagisi(yagis: xr.DataArray) -> np.ndarray:
    """İklimsel Haz–Tem–Ağu yağış toplamı (mm): üç ayın iklimsel ortalamalarının toplamı."""
    iklim = yagis.groupby("time.month").mean("time", skipna=True)
    return iklim.sel(month=[6, 7, 8]).sum("month", skipna=False).values.astype(float)


def takvim_farki(ndvi: xr.DataArray) -> np.ndarray:
    """NDVI(Tem–Ağu) − NDVI(Nis–May), iklimsel. Yüksek = yazın ilkbahardan yeşil."""
    return aylar_ortalamasi(ndvi, YAZ_AYLARI) - aylar_ortalamasi(ndvi, ILKBAHAR_AYLARI)


def _yillik_yaz_ndvi(ndvi: xr.DataArray) -> xr.DataArray:
    """(yil, lat, lon): Tem ve Ağu ikisi de doluysa ortalaması, değilse NaN."""
    s = ndvi.where(ndvi["time"].dt.month.isin(YAZ_AYLARI))
    ort = s.groupby("time.year").mean("time", skipna=True)
    say = s.notnull().groupby("time.year").sum("time")
    return ort.where(say == len(YAZ_AYLARI))


def _su_yili_yagisi(yagis: xr.DataArray) -> xr.DataArray:
    """(yil, lat, lon): bir önceki Ekim'den bu yılın Haziran'ına toplam; 9 ayın hepsi doluysa."""
    ay = yagis["time"].dt.month
    s = yagis.where(ay.isin(SU_YILI_AYLARI))
    su_yili = xr.where(ay >= 10, yagis["time"].dt.year + 1, yagis["time"].dt.year).rename("year")
    top = s.groupby(su_yili).sum("time", skipna=True)
    say = s.notnull().groupby(su_yili).sum("time")
    return top.where(say == SU_YILI_MIN_AY)


def kopukluk(ndvi: xr.DataArray, yagis: xr.DataArray) -> np.ndarray:
    """−r(yıllık yaz NDVI, Eki–Haz yağışı) her hücrede; en az ``KOPUKLUK_MIN_YIL`` ortak yıl, yoksa NaN."""
    a, b = xr.align(_yillik_yaz_ndvi(ndvi), _su_yili_yagisi(yagis), join="inner")
    a, b = a.values.astype(float), b.values.astype(float)
    ok = np.isfinite(a) & np.isfinite(b)
    n = ok.sum(0)
    a, b = np.where(ok, a, np.nan), np.where(ok, b, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        da_, db_ = a - np.nanmean(a, 0), b - np.nanmean(b, 0)
        r = np.nansum(da_ * db_, 0) / np.sqrt(np.nansum(da_ ** 2, 0) * np.nansum(db_ ** 2, 0))
    r = np.where((n >= KOPUKLUK_MIN_YIL) & np.isfinite(r), r, np.nan)
    return -r


def kurak_yaz(p_yaz: np.ndarray, rakim: np.ndarray, kara: np.ndarray,
              yagis_esik: float = YAZ_YAGIS_ESIK, rakim_esik: float = RAKIM_ESIK) -> np.ndarray:
    """Kurak yaz hücresi: kara, iklimsel yaz yağışı < eşik ve rakım < eşik (NaN → hayır)."""
    p, z = np.asarray(p_yaz, float), np.asarray(rakim, float)
    with np.errstate(invalid="ignore"):
        return np.asarray(kara, bool) & (p < yagis_esik) & (z < rakim_esik)


def zskor(x: np.ndarray, alan: np.ndarray) -> np.ndarray:
    """``alan`` içindeki sonlu değerlere göre standart skor; alan dışı NaN."""
    x = np.asarray(x, float)
    m = np.asarray(alan, bool) & np.isfinite(x)
    out = np.full(x.shape, np.nan)
    if m.sum() < 3:
        return out
    sd = x[m].std(ddof=1)
    out[m] = (x[m] - x[m].mean()) / sd if sd > 0 else 0.0
    return out


def skorlar(takvim: np.ndarray, kopuk: np.ndarray, kurak: np.ndarray, kara: np.ndarray) -> dict[str, np.ndarray]:
    """Üç yapılandırmanın skoru (lat, lon). Kopukluk eksikse ``v3_kopukluk`` = z_takvim (tek bileşen)."""
    zt = zskor(takvim, kurak)
    zk = zskor(kopuk, kurak)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        birlesik = np.where(np.isfinite(zt), np.nanmean(np.stack([zt, zk]), 0), np.nan)
    return {"v3_ana": zt, "v3_kopukluk": birlesik, "v3_maskesiz": zskor(takvim, kara),
            "z_takvim": zt, "z_kopukluk": zk}


# ---------------------------------------------------------------- girdiler
def girdiler(paket: Path, grid: str = "025") -> dict:
    """NDVI, yağış, rakım ve bölge maskeleri. "025": L1 paketi; "005": NDVI ve rakım 0,05° cache dosyaları,
    yağış 0,25° L1'den en yakın komşu (v2 ile aynı aktarım)."""
    from physics.sapma import GIRDILER, _cache_oku, _hizala, _oku
    from physics.tablo import bolge_listesi, bolge_maskeleri
    kup = Path(paket) / "L1_kup"
    yagis = _oku(kup, *GIRDILER["yagis"])
    if yagis is None:
        raise ValueError("v3 için L1 yagis__GPM gerekli")
    if grid == "025":
        ndvi, rakim = _oku(kup, *GIRDILER["ndvi"]), _oku(kup, *GIRDILER["rakim"])
        lat, lon = yagis["lat"].values, yagis["lon"].values
    elif grid == "005":
        ndvi, rakim = _cache_oku("ndvi", "MOD13C2", "005"), _cache_oku("rakim", "SRTM", "005")
        if ndvi is None or rakim is None:
            raise ValueError("0,05° için cache/processed/turkiye/ndvi__MOD13C2__005.nc ve rakim__SRTM__005.nc gerekli")
        la, lo = yagis["lat"].values, yagis["lon"].values
        s_, n_, w_, e_ = la.min() - 0.125, la.max() + 0.125, lo.min() - 0.125, lo.max() + 0.125
        lat = ndvi["lat"].values[(ndvi["lat"].values > s_) & (ndvi["lat"].values < n_)]
        lon = ndvi["lon"].values[(ndvi["lon"].values > w_) & (ndvi["lon"].values < e_)]
        ndvi, rakim = _hizala(ndvi, lat, lon, False), _hizala(rakim, lat, lon, False)
        yagis = _hizala(yagis, lat, lon, True)
    else:
        raise ValueError(f"bilinmeyen ızgara: {grid}")
    if ndvi is None or rakim is None:
        raise ValueError("v3 için L1 ndvi__MOD13C2 ve rakim__SRTM gerekli")
    iller = [b for b in bolge_listesi(iller=True) if b["bolge_turu"] == "il"]
    mk = bolge_maskeleri(lat, lon, True)
    return {"grid": grid, "lat": lat, "lon": lon, "ndvi": ndvi, "yagis": yagis,
            "rakim": np.asarray(rakim.values, float), "kara": mk["turkiye"],
            "il_maskeleri": {b["anahtar"]: mk[b["anahtar"]] for b in iller},
            "il_adlari": {b["anahtar"]: b["bolge_adi"] for b in iller},
            "meta": {k: yagis.attrs.get(k, "") for k in ("urun_surumu", "veri_seti_doi", "lisans")}}


def hesapla(g: dict, yagis_esik: float = YAZ_YAGIS_ESIK) -> dict:
    """Bileşenler ve skorlar. Doğrulama katmanı burada hiç okunmaz."""
    p_yaz = yaz_yagisi(g["yagis"])
    tk = takvim_farki(g["ndvi"])
    kp = kopukluk(g["ndvi"], g["yagis"])
    kurak = kurak_yaz(p_yaz, g["rakim"], g["kara"], yagis_esik)
    return {"p_yaz": p_yaz, "takvim": tk, "kopukluk": kp, "kurak": kurak, "yagis_esik": yagis_esik,
            "skor": skorlar(tk, kp, kurak, g["kara"])}


# ---------------------------------------------------------------- çıktı
def harita(g: dict, h: dict) -> xr.Dataset:
    """``sapma_haritasi_v3_<grid>.nc``."""
    k = {"coords": {"lat": g["lat"], "lon": g["lon"]}, "dims": ("lat", "lon")}
    kara = g["kara"]

    def f32(x, ad, birim="1"):
        return xr.DataArray(np.where(kara, x, np.nan).astype(np.float32), **k, attrs={"long_name": ad, "units": birim})
    s = h["skor"]
    ds = xr.Dataset({
        "sulama_izi": f32(s["v3_ana"], "sulama izi v3 (ana): kurak yaz hücrelerinde z_takvim"),
        "sulama_izi_kopukluk": f32(s["v3_kopukluk"], "(z_takvim + z_kopukluk) / 2, kurak yaz hücreleri"),
        "z_takvim": f32(s["z_takvim"], "NDVI(Tem–Ağu) − NDVI(Nis–May), kurak yaz hücreleri arasında z"),
        "z_kopukluk": f32(s["z_kopukluk"], "−r(yaz NDVI, Eki–Haz yağışı), kurak yaz hücreleri arasında z"),
        "takvim_farki": f32(h["takvim"], "iklimsel NDVI(Tem–Ağu) − NDVI(Nis–May)"),
        "yaz_yagisi": f32(h["p_yaz"], "iklimsel Haz–Tem–Ağu yağış toplamı (GPM)", "mm"),
        "kurak_yaz": xr.DataArray(np.where(kara, h["kurak"], 0).astype(np.int8), **k,
                                  attrs={"long_name": f"1 = yaz yağışı < {h['yagis_esik']:g} mm ve rakım < "
                                                      f"{RAKIM_ESIK:g} m (skorun hesaplandığı hücreler)"}),
    })
    ds.attrs.update({a: v for a, v in g["meta"].items() if v})
    ds.attrs.update({"baslik": f"Beklentiden sapma haritası v3, bitki takvimi ({'0,25°' if g['grid'] == '025' else '0,05°'})",
                     "yontem": KURAL_METNI, "uyari": UYARI, "surum": "v3", "kural_surumu": KURAL_SURUMU,
                     "uretim": "python -m physics.sapma_v3"})
    return ds


def _hedef(paket: Path, ad: str, grid: str, lat, lon) -> np.ndarray | None:
    p = Path(paket) / "dogrulama" / DOGRULAMA_DOSYALARI[ad][grid]
    if not p.exists():
        return None
    from physics.sapma_dogrulama import hedef_oku
    if ad == "GFSAD1KCM":
        return hedef_oku(paket, grid, lat, lon)
    with xr.open_dataset(p) as ds:
        da = ds["sulanan_oran"].load()
    return da.sel(lat=xr.DataArray(lat, dims="lat"), lon=xr.DataArray(lon, dims="lon"), method="nearest",
                  tolerance=1e-4).values.astype(float)


def dogrula(paket: Path, sonuclar: dict[str, tuple[dict, dict]]) -> pd.DataFrame:
    """Skorlar hesaplandıktan SONRA: her referans × ızgara × yapılandırma için ölçütler (+ duyarlılık, tanı)."""
    from physics.sapma_dogrulama import degerlendir
    satir = []
    for grid, (g, h) in sonuclar.items():
        for ref in DOGRULAMA_DOSYALARI:
            hedef = _hedef(paket, ref, grid, g["lat"], g["lon"])
            if hedef is None:
                continue
            for ad in YAPILANDIRMALAR:
                satir.append({"referans": ref, "izgara": grid, "yapilandirma": ad, "tur": "ana",
                              "yaz_yagis_esigi": h["yagis_esik"] if ad != "v3_maskesiz" else np.nan,
                              **degerlendir(h["skor"][ad], hedef, g["kara"])})
            satir.append({"referans": ref, "izgara": grid, "yapilandirma": "v3_ana, yalnız kurak yaz hücreleri",
                          "tur": "tanı", "yaz_yagis_esigi": h["yagis_esik"],
                          **degerlendir(h["skor"]["v3_ana"], hedef, h["kurak"])})
            for e in DUYARLILIK_YAGIS:
                kurak = kurak_yaz(h["p_yaz"], g["rakim"], g["kara"], e)
                satir.append({"referans": ref, "izgara": grid, "yapilandirma": f"v3_ana, yaz yağışı < {e:g} mm",
                              "tur": "duyarlılık", "yaz_yagis_esigi": e,
                              **degerlendir(zskor(h["takvim"], kurak), hedef, g["kara"])})
    tab = pd.DataFrame(satir)
    if len(tab):
        tab["rastgele_auc"] = 0.5
        tab["kaldirac_ust5"] = tab["precision_ust5"] / tab["taban_oran"]
    return tab


def uret_yaz(paket: Path, izgaralar=("025", "005")) -> dict:
    """v3'ü üretir ve yazar; 0,05° girdileri yoksa o ızgara atlanır. Doğrulama katmanı varsa ölçer."""
    from physics.sapma import KLASOR, kumeler
    paket = Path(paket)
    hedef = paket / "L4_iliski" / KLASOR
    hedef.mkdir(parents=True, exist_ok=True)
    sonuclar, yollar, atlanan = {}, [], []
    for grid in izgaralar:
        try:
            g = girdiler(paket, grid)
        except ValueError as e:
            if grid == "025":
                raise
            atlanan.append(f"{grid}: {e}")
            continue
        h = hesapla(g)
        p = hedef / DOSYALAR[grid]
        harita(g, h).to_netcdf(p)
        yollar.append(p)
        sonuclar[grid] = (g, h)
    ince = "005" if "005" in sonuclar else "025"
    g, h = sonuclar[ince]
    km = kumeler(h["skor"]["v3_ana"], g["lat"], g["lon"], g["il_maskeleri"], g["il_adlari"], KUME_YUZDELIK)
    km["izgara"] = ince
    p = hedef / KUMELER
    km.to_csv(p, index=False, encoding="utf-8-sig", float_format="%.4g")
    yollar.append(p)
    (hedef / "KURAL_v3.txt").write_text(KURAL_METNI + "\n" + UYARI + "\n", encoding="utf-8")
    yollar.append(hedef / "KURAL_v3.txt")
    dg = dogrula(paket, sonuclar)
    if len(dg):
        p = paket / "dogrulama" / "sapma_v3_dogrulama.csv"
        dg.to_csv(p, index=False, encoding="utf-8-sig", float_format="%.4g")
        yollar.append(p)
    return {"sonuclar": sonuclar, "kumeler": km, "dogrulama": dg, "yollar": yollar, "atlanan": atlanan}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m physics.sapma_v3", description=__doc__.splitlines()[0])
    ap.add_argument("--surum", default="v0.1")
    ap.add_argument("--paket", type=Path, default=None)
    ap.add_argument("--yalniz-025", action="store_true", help="0,05° ızgarayı atla")
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    if a.paket is None:
        from data.export import OUTPUTS_DIR
        a.paket = OUTPUTS_DIR / f"trend-dedektifi-turkiye-{a.surum}"
    try:
        r = uret_yaz(a.paket, ("025",) if a.yalniz_025 else ("025", "005"))
    except ValueError as e:
        raise SystemExit(f"HATA: {e}") from None
    print(f"BEKLENTİDEN SAPMA HARİTASI v3 · bitki takvimi ({KURAL_SURUMU})")
    for grid, (g, h) in r["sonuclar"].items():
        print(f"  {grid}: kara {int(g['kara'].sum())} hücre, kurak yaz {int(h['kurak'].sum())}")
    for x in r["atlanan"]:
        print(f"  atlandı: {x}")
    for x in r["kumeler"].itertuples():
        print(f"    {x.kume:2d}. {x.il:15s} z={x.tepe_sulama_izi:4.2f} {x.hucre_sayisi:3d} hücre · "
              f"tepe {x.tepe_lat:.3f}K {x.tepe_lon:.3f}D")
    if len(r["dogrulama"]):
        print(r["dogrulama"][["referans", "izgara", "yapilandirma", "tur", "auc", "precision_ust5",
                              "taban_oran", "kaldirac_ust5"]].to_string(index=False))
    else:
        print("  doğrulama katmanı yok (<paket>/dogrulama/sulanan_oran__*.nc); yalnız harita üretildi")
    print(f"  ⚠ {UYARI}")
    for p in r["yollar"]:
        print(" ", p)
    print(f"  süre: {time.perf_counter() - t0:.1f} sn")


if __name__ == "__main__":
    main()
