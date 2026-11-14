"""L3: il ve bölge özetleri (Kişi 2).

    python -m stats.l3 --surum v0.1
    python -m stats.l3 --surum v0.1 --dosyalar sicaklik_2m__MERRA2,yagis__GPM

Girdi : L1_kup/ (ICINDEKILER.csv, rakım hariç) ve L2_trend/<degisken>__<urun>__trend.nc
Çıktı : outputs/trend-dedektifi-turkiye-<surum>/L3_ozet/
        <degisken>__<urun>__il.csv, <degisken>__<urun>__bolge.csv
        <degisken>__kaynak_uyumu__il.csv, <degisken>__kaynak_uyumu__bolge.csv   (yagis, sicaklik_2m)
        ICINDEKILER.csv

Her dosya × il (81) / bölge (7) × mevsim (5) için iki tür sonuç:
A) Alan ortalaması serisinin trendi:
   - Bölge hücreleri ``data.regions.subset`` ile seçilir (hücre merkezi kuralı; merkezi düşmeyen küçük
     bölgede değen hücreler). Alan ortalaması ``area_mean`` ile alınır (cos(enlem) ağırlıklı, NaN
     hücreler atlanır).
   - Sonra ``donem_serisi`` → ``trend_analizi``. ``gereken_yil``, ``trend_analizi`` içinde
     ``weatherhead_gereken_yil`` ile aynı formülden gelir.
   - BH-FDR (α = 0,10) her dosya × mevsim × düzey içinde uygulanır: iller ayrı, bölgeler ayrı.
     Türkiye satırı (``duzey = "ulke"``) tek başına ayrı bir düzeydir, yani FDR'ye girmez (p_fdr = p_mk).
   - anlamli = 1 ⇔ p_fdr ≤ 0,10 ve GA sıfırı dışlıyor (``trend_tests.anlamli_kural``).
B) L2 hücre özeti: bölgedeki L2 hücrelerinin anlamlı oranları ve medyan eğimi.

Şema: docs/sozlesmeler.md bölüm 2.2.
"""

from __future__ import annotations

import argparse
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from stats.l2 import (ALFA_FDR, KAYNAK_UYUMU, MIN_YIL, _veri_donemi, egim_birimi, icindekiler, kara_maskesi,
                      mevsim_uyarisi, trend_uyarisi)
from stats.preprocessing import MEVSIMLER, SURUM, TOPLANANLAR, donem_serisi, eksik_esigi, paket_koku
from stats.trend_tests import anlamli_kural, bh_fdr, trend_analizi

AZ_HUCRE = 3
DOSYA_DUZEYLERI = {"il": ["il"], "bolge": ["bolge", "ulke"]}  # Türkiye satırı bölge CSV'sinde
ORTAK_ALANLAR = ("kademe", "dogrulanmadi", "urun_surumu", "veri_seti_doi", "lisans", "doi")
L3_COLS = [
    "bolge_kodu", "bolge_anahtari", "bolge_adi", "duzey", "ust_bolge", "mevsim", "hucre_sayisi",
    "sen_egimi", "ga_alt", "ga_ust", "p_mk", "p_fdr", "anlamli", "etkin_n", "gereken_yil", "mk_yedek",
    "anlamli_hucre_orani", "anlamli_artan_orani", "anlamli_azalan_orani", "medyan_hucre_egimi",
    "birim", "egim_birimi", "donem_baslangic", "donem_bitis", "trend_uyarisi", "not",
    *ORTAK_ALANLAR,
]
TREND_ALANLARI = ("sen_egimi", "ga_alt", "ga_ust", "p_mk", "etkin_n", "gereken_yil", "mk_yedek")


# ---------------------------------------------------------------- bölgeler ve maskeler

def bolge_listesi() -> list[dict]:
    """81 il, 7 bölge ve Türkiye: {duzey, anahtar, ad, kod, ust, sorgu}. İl kodu iki haneli plakadır.

    Türkiye satırı ``duzey = "ulke"``dir (tüm kara hücreleri) ve bölge CSV'sine yazılır.
    """
    from data.regions import _iller, bolge_of_il, list_regions  # yalnız okuma; data/ değişmez
    lr, il = list_regions(), _iller()
    out = [{"duzey": "il", "anahtar": k, "ad": ad, "kod": f"{int(il[k]['plaka']):02d}",
            "ust": bolge_of_il(k), "sorgu": f"il:{k}"} for k, ad in lr["il"]]
    out += [{"duzey": "bolge", "anahtar": k, "ad": ad, "kod": k, "ust": "", "sorgu": f"bolge:{k}"}
            for k, ad in lr["bolge"]]
    out.append({"duzey": "ulke", "anahtar": "turkiye", "ad": "Türkiye", "kod": "turkiye", "ust": "",
                "sorgu": "turkiye"})
    return out


def bolge_maskeleri(lat, lon, bolgeler: list[dict]) -> dict[str, tuple[xr.DataArray, str]]:
    """Her bölge için ızgarada (lat, lon) bool maske ve seçim yöntemi (``data.regions.subset``)."""
    from data.regions import subset
    sablon = xr.DataArray(np.ones((len(lat), len(lon)), "float32"), coords={"lat": lat, "lon": lon},
                          dims=("lat", "lon"), attrs={"domain": "land"})
    out = {}
    for b in bolgeler:
        kes = subset(sablon, b["sorgu"])
        m = kes.notnull().reindex_like(sablon, fill_value=False).astype(bool)
        out[b["anahtar"]] = (m, kes.attrs.get("region_method", ""))
    return out


def bolge_serileri(da: xr.DataArray, maskeler: dict) -> xr.DataArray:
    """(time, lat, lon) küpten (time, bolge) alan ortalaması serileri (``data.regions.area_mean``)."""
    from data.regions import area_mean
    seriler = [area_mean(da.where(m)).expand_dims(bolge=[k]) for k, (m, _) in maskeler.items()]
    return xr.concat(seriler, dim="bolge").transpose("time", "bolge")


# ---------------------------------------------------------------- A) alan ortalaması trendi

def bolge_trendleri(da: xr.DataArray, degisken: str, bolgeler: list[dict], maskeler: dict,
                    alfa: float = ALFA_FDR, min_yil: int = MIN_YIL,
                    mevsimler: dict = MEVSIMLER, urun: str | None = None) -> pd.DataFrame:
    """Her bölge × mevsim için alan ortalaması serisinin trendi; FDR düzey × mevsim içinde.

    anlamli, ``anlamli_kural`` ile belirlenir. urun (dosya kodu) eksik ay eşiğini seçer.
    """
    seri_hepsi = bolge_serileri(da, maskeler)
    toplama = degisken in TOPLANANLAR
    satirlar = []
    for mevsim, aylar in mevsimler.items():
        seri = donem_serisi(seri_hepsi, aylar, toplama=toplama, kis=(mevsim == "kis"),
                            eksik_esik=eksik_esigi(urun, mevsim))
        for b in bolgeler:
            s = seri.sel(bolge=b["anahtar"])
            r = trend_analizi(s, min_yil=min_yil, kontrol=False)
            gecerli = s["yil"].values[np.isfinite(s.values)]
            satir = {"bolge_anahtari": b["anahtar"], "duzey": b["duzey"], "mevsim": mevsim,
                     "donem_baslangic": int(gecerli.min()) if gecerli.size else np.nan,
                     "donem_bitis": int(gecerli.max()) if gecerli.size else np.nan}
            if r["durum"] == "yetersiz_veri":
                satir.update({k: np.nan for k in TREND_ALANLARI})
            else:
                satir.update(sen_egimi=r["egim_10yil"], ga_alt=r["ci_alt"], ga_ust=r["ci_ust"],
                             p_mk=r["p_mk"], etkin_n=r["n_etkin"], gereken_yil=r["gereken_yil"],
                             mk_yedek=int(bool(r.get("mk_yedek", False))))
            satirlar.append(satir)
    df = pd.DataFrame(satirlar)
    df["p_fdr"], df["anlamli"] = np.nan, -1
    for (_, _), grup in df.groupby(["duzey", "mevsim"]):
        q, _ = bh_fdr(grup["p_mk"].to_numpy(float), alfa)
        df.loc[grup.index, "p_fdr"] = q
        df.loc[grup.index, "anlamli"] = anlamli_kural(q, grup["ga_alt"].to_numpy(float),
                                                      grup["ga_ust"].to_numpy(float), alfa)
    df["anlamli"] = df["anlamli"].astype(int)
    return df


# ---------------------------------------------------------------- B) L2 hücre özeti

def l2_hucre_ozeti(l2: xr.Dataset | None, bolgeler: list[dict], maskeler: dict,
                   mevsimler: dict = MEVSIMLER) -> pd.DataFrame:
    """Bölgedeki L2 hücreleri: anlamlı / artan / azalan oranı (trendi hesaplanan hücrelere göre), medyan eğim."""
    satirlar = []
    for mevsim in mevsimler:
        for b in bolgeler:
            m, _ = maskeler[b["anahtar"]]
            satir = {"bolge_anahtari": b["anahtar"], "mevsim": mevsim, "hucre_sayisi": int(m.sum())}
            if l2 is not None and mevsim in l2["mevsim"].values:
                s = l2.sel(mevsim=mevsim)
                anl, egim = s["anlamli"].values[m.values], s["sen_egimi"].values[m.values]
                n = int((anl >= 0).sum())
                satir.update(
                    anlamli_hucre_orani=float((anl == 1).sum()) / n if n else np.nan,
                    anlamli_artan_orani=float(((anl == 1) & (egim > 0)).sum()) / n if n else np.nan,
                    anlamli_azalan_orani=float(((anl == 1) & (egim < 0)).sum()) / n if n else np.nan,
                    medyan_hucre_egimi=float(np.nanmedian(egim[anl >= 0])) if n else np.nan,
                )
            satirlar.append(satir)
    return pd.DataFrame(satirlar)


# ---------------------------------------------------------------- bir dosya

def l3_dosya(da: xr.DataArray, degisken: str, urun: str, bolgeler: list[dict], maskeler: dict,
             l2: xr.Dataset | None = None, alfa: float = ALFA_FDR, min_yil: int = MIN_YIL,
             mevsimler: dict = MEVSIMLER) -> pd.DataFrame:
    """Bir L1 dosyası için tüm il ve bölge satırları (L3_COLS sırasıyla)."""
    a = bolge_trendleri(da, degisken, bolgeler, maskeler, alfa, min_yil, mevsimler, urun=urun)
    b = l2_hucre_ozeti(l2, bolgeler, maskeler, mevsimler)
    df = a.merge(b, on=["bolge_anahtari", "mevsim"], how="left")
    bilgi = {x["anahtar"]: x for x in bolgeler}
    df["bolge_kodu"] = df["bolge_anahtari"].map(lambda k: bilgi[k]["kod"])
    df["bolge_adi"] = df["bolge_anahtari"].map(lambda k: bilgi[k]["ad"])
    df["ust_bolge"] = df["bolge_anahtari"].map(lambda k: bilgi[k]["ust"])
    eb, seri_birimi = egim_birimi(str(da.attrs.get("units", "")), degisken)
    df["birim"] = df["mevsim"].map(seri_birimi)
    df["egim_birimi"] = eb
    if l2 is not None:
        uyari = l2.attrs.get("trend_uyarisi", "")
    else:  # L2 yoksa uyarı kataloğundan (mevsimlik hücre sayısı olmadan)
        uyari = trend_uyarisi(degisken, urun, xr.Dataset(coords={"mevsim": []}), np.zeros((0,), bool))
    df["trend_uyarisi"] = df["mevsim"].map(lambda m: mevsim_uyarisi(uyari, m))
    yontem = {k: v[1] for k, v in maskeler.items()}

    def _not(r):
        notlar = []
        if r["hucre_sayisi"] < AZ_HUCRE:
            notlar.append("az hücre")
        if yontem.get(r["bolge_anahtari"], "").startswith("değen"):
            notlar.append("merkezi düşen hücre yok; değen hücreler")
        return "; ".join(notlar)

    df["not"] = df.apply(_not, axis=1)
    for k in ORTAK_ALANLAR:
        v = da.attrs.get(k, "")
        df[k] = v.item() if isinstance(v, np.generic) else v
    for c in L3_COLS:
        if c not in df:
            df[c] = np.nan
    sira = {x["anahtar"]: i for i, x in enumerate(bolgeler)}
    msira = {m: i for i, m in enumerate(mevsimler)}
    df = df.assign(_b=df["bolge_anahtari"].map(sira), _m=df["mevsim"].map(msira))
    return df.sort_values(["_b", "_m"])[L3_COLS].reset_index(drop=True)


# ---------------------------------------------------------------- kaynak uyumu

def kaynak_uyumu_l3(dalar: dict[str, xr.DataArray], degisken: str, bolgeler: list[dict], maskeler: dict,
                    kara: np.ndarray, alfa: float = ALFA_FDR, min_yil: int = MIN_YIL,
                    mevsimler: dict = MEVSIMLER) -> pd.DataFrame:
    """İl/bölge düzeyinde kaynak uyumu (L2 ile aynı tanım, alan ortalaması serileri üzerinden).

    Ortak dönem = ürünlerin Türkiye kara hücrelerindeki veri dönemlerinin kesişimi. Her ürün bu
    döneme kırpılır, bölge trendi ve FDR yeniden hesaplanır.
    - m: trendi hesaplanabilen ürün sayısı.
    - k: anlamlı ve aynı yönde en büyük grup.
    - isaret_uyumu: anlamlılığa bakmadan aynı işaretli en büyük grup / m.
    """
    donemler = {u: _veri_donemi(da, kara) for u, da in dalar.items()}
    bas, son = max(d[0] for d in donemler.values()), min(d[1] for d in donemler.values())
    tablolar = {}
    for u, da in dalar.items():
        kesit = da.sel(time=slice(bas, son))
        tablolar[u] = bolge_trendleri(kesit, degisken, bolgeler, maskeler, alfa, min_yil, mevsimler, urun=u) \
            .set_index(["bolge_anahtari", "mevsim"])
    ref = next(iter(tablolar.values()))
    out = ref[["duzey"]].copy()
    egim = pd.concat({u: t["sen_egimi"] for u, t in tablolar.items()}, axis=1)
    anl = pd.concat({u: t["anlamli"] for u, t in tablolar.items()}, axis=1)
    gecerli = anl >= 0
    out["m"] = gecerli.sum(axis=1)
    out["k"] = np.maximum(((anl == 1) & (egim > 0)).sum(axis=1), ((anl == 1) & (egim < 0)).sum(axis=1))
    ayni = np.maximum((gecerli & (egim > 0)).sum(axis=1), (gecerli & (egim < 0)).sum(axis=1))
    out["isaret_uyumu"] = np.where(out["m"] > 0, ayni / out["m"].clip(lower=1), np.nan)
    for u in dalar:
        out[f"egim_{u}"] = egim[u]
        out[f"anlamli_{u}"] = anl[u]
    out = out.reset_index()
    bilgi = {x["anahtar"]: x for x in bolgeler}
    out.insert(0, "bolge_kodu", out["bolge_anahtari"].map(lambda k: bilgi[k]["kod"]))
    out.insert(2, "bolge_adi", out["bolge_anahtari"].map(lambda k: bilgi[k]["ad"]))
    out["egim_birimi"] = egim_birimi(str(next(iter(dalar.values())).attrs.get("units", "")), degisken)[0]
    out["ortak_donem"] = f"{bas:%Y-%m} … {son:%Y-%m}"
    out["urunler"] = ", ".join(dalar)
    cols = ["bolge_kodu", "bolge_anahtari", "bolge_adi", "duzey", "mevsim", "k", "m", "isaret_uyumu",
            *[c for u in dalar for c in (f"egim_{u}", f"anlamli_{u}")], "egim_birimi", "ortak_donem", "urunler"]
    return out[cols]


# ---------------------------------------------------------------- üretim

def _csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig", float_format="%.6g")


def uret(surum: str = SURUM, kok: Path | None = None, dosyalar: list[str] | None = None,
         bolgeler: list[dict] | None = None, alfa: float = ALFA_FDR, min_yil: int = MIN_YIL) -> Path:
    """L3 katmanını üretir; L3_ozet klasörünün yolunu döndürür."""
    paket = paket_koku(surum, kok)
    out_dir = paket / "L3_ozet"
    out_dir.mkdir(parents=True, exist_ok=True)
    tablo = icindekiler(paket)
    if dosyalar:
        tablo = tablo[tablo["dosya"].str.replace(".nc", "", regex=False).isin(dosyalar)]
    bolgeler = bolgeler or bolge_listesi()
    maskeler, kara, dalar_hepsi, icerik = None, None, {}, []
    t0 = time.time()
    for _, r in tablo.iterrows():
        t1 = time.time()
        stem = r["dosya"][:-3]
        degisken, urun = stem.split("__")
        with xr.open_dataset(paket / "L1_kup" / r["dosya"]) as ds:
            ds = ds.load()
        da = ds[degisken]
        da.attrs = {**ds.attrs, **da.attrs}
        if maskeler is None:
            maskeler = bolge_maskeleri(da["lat"].values, da["lon"].values, bolgeler)
            kara = kara_maskesi(da)
        l2_yol = paket / "L2_trend" / f"{stem}__trend.nc"
        l2 = None
        if l2_yol.exists():
            with xr.open_dataset(l2_yol) as x:
                l2 = x.load()
        df = l3_dosya(da, degisken, urun, bolgeler, maskeler, l2, alfa, min_yil)
        for duzey in ("il", "bolge"):
            parca = df[df["duzey"].isin(DOSYA_DUZEYLERI[duzey])]
            if parca.empty:
                continue
            ad = f"{stem}__{duzey}.csv"
            _csv(parca, out_dir / ad)
            icerik.append({"dosya": ad, "tur": "trend", "degisken": degisken, "urun": urun, "duzey": duzey,
                           "satir": len(parca), "kademe": r["kademe"],
                           "trend_uyarisi": "evet" if (parca["trend_uyarisi"] != "").any() else "",
                           "l2_ozeti": "evet" if l2 is not None else "yok (L2 dosyası bulunamadı)"})
        if urun in KAYNAK_UYUMU.get(degisken, []):
            dalar_hepsi[(degisken, urun)] = da
        print(f"  {stem}: {len(df)} satır ({time.time() - t1:.0f} sn)")
    for degisken, urunler in KAYNAK_UYUMU.items():
        dalar = {u: dalar_hepsi[(degisken, u)] for u in urunler if (degisken, u) in dalar_hepsi}
        if len(dalar) < 2:
            continue
        ku = kaynak_uyumu_l3(dalar, degisken, bolgeler, maskeler, kara, alfa, min_yil)
        for duzey in ("il", "bolge"):
            parca = ku[ku["duzey"].isin(DOSYA_DUZEYLERI[duzey])]
            if parca.empty:
                continue
            ad = f"{degisken}__kaynak_uyumu__{duzey}.csv"
            _csv(parca, out_dir / ad)
            icerik.append({"dosya": ad, "tur": "kaynak_uyumu", "degisken": degisken, "urun": ", ".join(dalar),
                           "duzey": duzey, "satir": len(parca), "kademe": "", "trend_uyarisi": "",
                           "l2_ozeti": ""})
        print(f"  {degisken} kaynak uyumu ({', '.join(dalar)}; {ku['ortak_donem'].iloc[0]})")
    ic = pd.DataFrame(icerik)
    ic["olusturma_tarihi"] = date.today().isoformat()
    _csv(ic, out_dir / "ICINDEKILER.csv")
    print(f"L3 tamam: {len(tablo)} dosya, {len(icerik)} CSV, {time.time() - t0:.0f} sn → {out_dir}")
    return out_dir


def main(argv=None):
    ap = argparse.ArgumentParser(description="L3 il ve bölge özetleri.")
    ap.add_argument("--surum", default=SURUM)
    ap.add_argument("--kok", default=None, help="outputs kök klasörü (varsayılan: repo/outputs)")
    ap.add_argument("--dosyalar", default=None, help="virgülle: sicaklik_2m__MERRA2,yagis__GPM")
    ap.add_argument("--min-yil", type=int, default=MIN_YIL)
    a = ap.parse_args(argv)
    uret(a.surum, Path(a.kok) if a.kok else None,
         a.dosyalar.split(",") if a.dosyalar else None, min_yil=a.min_yil)


if __name__ == "__main__":
    main()
