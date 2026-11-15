"""Beklentiden sapma haritası: L4 sonuçlarının fiziksel beklentiden saptığı yerler ve "sulama izi".

    python -m physics.sapma --surum v0.1            # → <paket>/L4_iliski/sapma/
    python -m physics.sapma --surum v0.1 --goster   # ayrıca tarayıcıda açılan HTML harita

Sade anlatım:
1. **Sapma skoru.** ciftler.yaml'daki her çift için L4 etiketi okunur: ``ters_yonde`` = 1,
   ``beklenen_yonde`` / ``anlamsiz`` = 0, hesaplanamadı = NaN. Hücre ve il başına ters çift sayısı ve oranı.
2. **İklim rejimi ayrımı.** Yönü iklim rejimine bağlı çiftlerde (``rejime_bagli: true``, ör. yaz
   sıcaklığı ~ buharlaşma) su sınırlı (kurak) yerdeki ters sonuç "rejimle açıklanabilir" diye ayrı
   sayılır ve sapma skoruna katılmaz. Kuraklık göstergesi: GLDAS yıllık buharlaşma / yağış (E/P).
3. **Sulama izi.** Sulanan alanda yazın bitki, yağışın izin verdiğinden daha yeşil ve yüzey daha serin
   olur. Her kara hücresinde iklimsel (uzun dönem) yaz değerleri bütün kara hücrelerinde
   ``değer ~ log(1+yaz yağışı) + log(1+kış+ilkbahar yağışı) + rakım`` regresyonuyla açıklanır;
   artık standartlaştırılır (z):
   - ``z_yesil``: yaz NDVI artığı (yüksek = yağışın açıkladığından yeşil)
   - ``z_serin``: yaz (gündüz yüzey sıcaklığı − 2 m hava sıcaklığı) artığı, işareti ters
     (yüksek = beklenenden serin yüzey)
   ``sulama_izi`` = mevcut z'lerin ortalaması. Yöntem kördür: hiçbir yer adı, kutu ya da yere özel eşik yoktur.
   Toprak nemi bileşeni kullanılmaz: paketteki toprak nemi GLDAS model çıktısıdır ve sulamayı içermez.

Dil: sonuçlar **fiziksel beklentiden sapmadır**. İnsan müdahalesiyle (sulama, baraj, yeraltı suyu
çekimi) tutarlı olabilir ama doğrulanmamıştır; olası açıklamalar iklim rejimi, veri/ürün sorunu ve
insan müdahalesidir.
"""

from __future__ import annotations

import argparse
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from scipy import ndimage

from physics import seriler as S
from physics.ciftler import AYAR_DOSYASI, Cift, ayar_oku

KLASOR = "sapma"
UYARI = ("Doğrulanmadı; neden göstermez. Fiziksel beklentiden sapmadır; olası açıklamalar: iklim rejimi, "
         "veri/ürün sorunu, insan müdahalesi (sulama, baraj, yeraltı suyu çekimi).")
SULAMA_NOTU = ("Yaz yeşilliği/serinliği yağışın açıkladığından yüksek: insan müdahalesiyle (sulama) tutarlı "
               "olabilir, doğrulanmadı. Kıyı etkisi, orman ya da veri/ürün sorunu da olası açıklamalardır.")
MODIS_NOTU = ("MOD13C2 ve MOD11C3 ürünlerinde L2 trend uyarısı vardır; sulama izinde trend değil, "
              "2001–2025 iklimsel yaz ortalaması kullanıldı.")
TOPRAK_NEMI_NOTU = ("Toprak nemi bileşeni kullanılmadı: paketteki toprak nemi GLDAS-2.1 Noah model çıktısıdır "
                    "ve sulamayı simüle etmez.")
GIRDILER = {"ndvi": ("ndvi", "MOD13C2"), "lst": ("yuzey_sicakligi_gunduz", "MOD11C3"),
            "t2m": ("sicaklik_2m", "MERRA2"), "yagis": ("yagis", "GPM"), "rakim": ("rakim", "SRTM")}
ETIKET = {"beklenen_yonde": 0.0, "anlamsiz": 0.0, "ters_yonde": 1.0}
KUME_YUZDELIK = 90      # sulama_izi'nin kara hücrelerindeki 90. yüzdeliği üstü kümelenir
KUME_SAYISI = 10
SULAMA_IZI_ESIK = 1.0   # il notu: il ortalaması ≥ 1 standart sapma


# ---------------------------------------------------------------- 1) sapma skoru
def etiket_birlestir(kodlar: list[np.ndarray]) -> np.ndarray:
    """Gecikmelere ait ters dizilerini (1 ters, 0 uyumlu, NaN yok) birleştirir: herhangi biri 1 ise 1,
    değerlendirilebilen varsa 0, hiçbiri yoksa NaN. (Beklenen yön önceliği ``hucre_etiketleri``'nde.)"""
    if len(kodlar) == 1:
        return kodlar[0]
    st = np.stack(kodlar)
    ters = np.nanmax(np.where(np.isnan(st), -np.inf, st), axis=0)
    return np.where(np.isfinite(ters), ters, np.nan)


def _hucre_etiketi(etiket_int8: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """L4 harita etiketi (1/−1/0/−99) → (ters: 1/0/NaN, beklenen: bool)."""
    e = np.asarray(etiket_int8)
    ters = np.where(e == -1, 1.0, np.where(np.isin(e, (0, 1)), 0.0, np.nan))
    return ters, e == 1


def hucre_etiketleri(l4: Path, ciftler: tuple[Cift, ...]) -> dict[int, np.ndarray]:
    """``{cift_no: (lat, lon) dizisi}`` — 1 ters, 0 uyumlu, NaN hesaplanamadı. Haritasız çift atlanır.

    Birden çok gecikmeli çiftte: bir gecikmede beklenen yön varsa 0; yoksa herhangi birinde ters ise 1.
    """
    out = {}
    for c in ciftler:
        if not c.harita:
            continue
        tersler, beklenenler = [], []
        for g in c.gecikmeler:
            f = Path(l4) / c.harita_dosyasi(g)
            if not f.exists():
                continue
            with xr.open_dataset(f) as ds:
                t, b = _hucre_etiketi(ds["etiket"].values)
            tersler.append(t)
            beklenenler.append(b)
        if tersler:
            t = etiket_birlestir(tersler)
            out[c.no] = np.where(np.any(beklenenler, axis=0), 0.0, t)
    return out


def il_etiketleri(ciftler_csv: Path, ciftler: tuple[Cift, ...]) -> pd.DataFrame:
    """İl × çift tablosu (satır: bolge_kodu, sütun: cift_no): 1 ters, 0 uyumlu, NaN hesaplanamadı."""
    df = pd.read_csv(ciftler_csv, dtype={"bolge_kodu": str}, encoding="utf-8-sig")
    df = df[df["bolge_turu"] == "il"]
    out = {}
    for c in ciftler:
        d = df[df["cift_no"] == c.no]
        if d.empty:
            continue
        e = d["etiket"].map(ETIKET)
        bek = (d["etiket"] == "beklenen_yonde").groupby(d["bolge_kodu"]).any()
        ters = e.groupby(d["bolge_kodu"]).max()           # NaN'lar atlanır; hepsi NaN ise NaN
        out[c.no] = ters.where(~bek, 0.0)
    return pd.DataFrame(out)


def sapma_skoru(etiketler: dict[int, np.ndarray], rejime_bagli: set[int],
                su_sinirli: np.ndarray) -> dict[str, np.ndarray]:
    """Ters çift sayısı ve oranı; rejime bağlı çiftin su sınırlı yerdeki tersi ayrı sayılır.

    Parametreler
    ----------
    etiketler : ``{cift_no: dizi}`` — 1 ters, 0 uyumlu, NaN hesaplanamadı (hepsi aynı şekil).
    rejime_bagli : ciftler.yaml'da ``rejime_bagli: true`` olan çift numaraları.
    su_sinirli : bool dizi (kurak yer); çıktıların şekli bundan alınır (etiket yoksa her şey NaN).

    Döndürür: ``sapma_sayisi``, ``degerlendirilen``, ``sapma_orani``, ``rejimle_aciklanan``,
    ``sapma_sayisi_ham`` (rejim ayrımı öncesi), ``ters_bit`` (bit i−1 = çift i ters ve sapma sayıldı),
    ``rejim_bit`` (bit i−1 = çift i ters ama rejimle açıklandı).
    """
    sekil = np.shape(su_sinirli)
    say = np.zeros(sekil)
    ham = np.zeros(sekil)
    rejim = np.zeros(sekil)
    deg = np.zeros(sekil)
    ters_bit = np.zeros(sekil, np.int32)
    rejim_bit = np.zeros(sekil, np.int32)
    kurak = np.asarray(su_sinirli, bool)
    for no, e in etiketler.items():
        e = np.asarray(e, float)
        ok = np.isfinite(e)
        ters = ok & (e == 1)
        aciklanan = ters & kurak if no in rejime_bagli else np.zeros(sekil, bool)
        sapma = ters & ~aciklanan
        deg += ok
        ham += ters
        say += sapma
        rejim += aciklanan
        ters_bit |= np.where(sapma, 1 << (no - 1), 0).astype(np.int32)
        rejim_bit |= np.where(aciklanan, 1 << (no - 1), 0).astype(np.int32)
    with np.errstate(invalid="ignore", divide="ignore"):
        oran = np.where(deg > 0, say / deg, np.nan)
    bos = deg == 0
    return {"sapma_sayisi": np.where(bos, np.nan, say), "degerlendirilen": deg,
            "sapma_orani": oran, "rejimle_aciklanan": np.where(bos, np.nan, rejim),
            "sapma_sayisi_ham": np.where(bos, np.nan, ham), "ters_bit": ters_bit, "rejim_bit": rejim_bit}


def bit_listesi(bit: int) -> str:
    """Bit maskesi → ``"3,5"`` (çift numaraları)."""
    bit = int(bit)
    return ",".join(str(i + 1) for i in range(31) if bit >> i & 1)


# ---------------------------------------------------------------- 2) iklim rejimi
def iklim_ortalamasi(da: xr.DataArray, mevsim: str, toplam: bool) -> xr.DataArray:
    """Mevsim (ya da yıllık) serisinin uzun dönem ortalaması (lat, lon)."""
    return S.mevsim_serisi(da, mevsim, toplam=toplam).mean("yil", skipna=True)


def kuraklik_gostergesi(yagis: xr.DataArray, buharlasma: xr.DataArray) -> xr.DataArray:
    """Uzun dönem yıllık buharlaşma / yağış (E/P). Yüksek = yağışın çoğu buharlaşıyor (su sınırlı)."""
    p = iklim_ortalamasi(yagis, "yillik", toplam=True)
    e = iklim_ortalamasi(buharlasma, "yillik", toplam=True)
    return (e / p.where(p > 0)).rename("kuraklik_gostergesi")


# ---------------------------------------------------------------- 3) sulama izi
def artik_z(y: np.ndarray, X: list[np.ndarray], maske: np.ndarray) -> np.ndarray:
    """``y ~ 1 + X`` EKK regresyonu (yalnız ``maske`` ve tüm değişkenleri sonlu hücrelerde);
    standartlaştırılmış artık (artık / artıkların standart sapması). Diğer hücreler NaN."""
    y = np.asarray(y, float)
    ok = np.asarray(maske, bool) & np.isfinite(y)
    for x in X:
        ok &= np.isfinite(x)
    out = np.full(y.shape, np.nan)
    if ok.sum() < len(X) + 3:
        return out
    A = np.column_stack([np.ones(ok.sum())] + [np.asarray(x, float)[ok] for x in X])
    b, *_ = np.linalg.lstsq(A, y[ok], rcond=None)
    art = y[ok] - A @ b
    sd = art.std(ddof=len(X) + 1)
    out[ok] = art / sd if sd > 0 else 0.0
    return out


def sulama_izi(ndvi: xr.DataArray | None, lst: xr.DataArray | None, t2m: xr.DataArray | None,
               yagis: xr.DataArray, rakim: xr.DataArray, kara: np.ndarray) -> dict[str, np.ndarray]:
    """Bileşen z'leri ve ortalamaları.

    Girdiler aylık küpler (time, lat, lon); ``rakim`` (lat, lon); ``kara`` (lat, lon) bool.
    Eksik girdinin bileşeni atlanır. Döndürür: ``z_yesil``, ``z_serin``, ``sulama_izi``, ``n_bilesen``.
    """
    p_yaz = iklim_ortalamasi(yagis, "yaz", toplam=True).values
    p_kis = iklim_ortalamasi(yagis, "kis", toplam=True).values
    p_ilk = iklim_ortalamasi(yagis, "ilkbahar", toplam=True).values
    X = [np.log1p(np.clip(p_yaz, 0, None)), np.log1p(np.clip(p_kis + p_ilk, 0, None)),
         np.asarray(rakim.values, float) / 1000.0]
    sekil = p_yaz.shape
    z = {}
    if ndvi is not None:
        z["z_yesil"] = artik_z(iklim_ortalamasi(ndvi, "yaz", toplam=False).values, X, kara)
    else:
        z["z_yesil"] = np.full(sekil, np.nan)
    if lst is not None and t2m is not None:
        fark = (iklim_ortalamasi(lst, "yaz", toplam=False) - iklim_ortalamasi(t2m, "yaz", toplam=False)).values
        z["z_serin"] = -artik_z(fark, X, kara)
    else:
        z["z_serin"] = np.full(sekil, np.nan)
    st = np.stack([z["z_yesil"], z["z_serin"]])
    n = np.isfinite(st).sum(0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)       # bileşensiz hücre: boş dilim
        ort = np.where(n > 0, np.nanmean(st, 0), np.nan)
    return {**z, "sulama_izi": ort, "n_bilesen": n.astype(np.int8)}


# ---------------------------------------------------------------- kümeler
def kumeler(skor: np.ndarray, lat, lon, il_maskeleri: dict[str, np.ndarray], il_adlari: dict[str, str],
            yuzdelik: float = KUME_YUZDELIK, n: int = KUME_SAYISI) -> pd.DataFrame:
    """Yüksek skorlu komşu hücreleri (8 komşuluk) birleştirir; en yüksek tepe değerli ``n`` küme.

    Eşik: kara hücrelerindeki skorun ``yuzdelik``. yüzdeliği (veriden; yere özel değil).
    Sütunlar: kume, hucre_sayisi, tepe_sulama_izi, ortalama_sulama_izi, tepe_lat, tepe_lon,
    merkez_lat, merkez_lon (skor ağırlıklı), il (tepe hücrenin ili), iller (kümenin dokunduğu iller).
    """
    lat, lon = np.asarray(lat), np.asarray(lon)
    s = np.asarray(skor, float)
    if not np.isfinite(s).any():
        return pd.DataFrame()
    esik = np.nanpercentile(s, yuzdelik)
    etk, say = ndimage.label(np.isfinite(s) & (s >= esik), structure=np.ones((3, 3)))
    il_of = np.full(s.shape, "", object)
    for k, m in il_maskeleri.items():
        il_of[m & (il_of == "")] = il_adlari[k]
    satir = []
    for i in range(1, say + 1):
        m = etk == i
        v = np.where(m, s, np.nan)
        iy, ix = np.unravel_index(np.nanargmax(v), s.shape)
        yy, xx = np.nonzero(m)
        w = s[m] - esik + 1e-9
        iller = sorted({il_of[a, b] for a, b in zip(yy, xx) if il_of[a, b]})
        tepe_il = il_of[iy, ix] or _en_yakin_il(iy, ix, il_of)
        satir.append({"hucre_sayisi": int(m.sum()), "tepe_sulama_izi": float(s[iy, ix]),
                      "ortalama_sulama_izi": float(np.nanmean(v)), "tepe_lat": float(lat[iy]),
                      "tepe_lon": float(lon[ix]), "merkez_lat": float(np.average(lat[yy], weights=w)),
                      "merkez_lon": float(np.average(lon[xx], weights=w)), "il": tepe_il,
                      "iller": ", ".join(iller) or tepe_il})
    df = pd.DataFrame(satir).sort_values(["tepe_sulama_izi", "hucre_sayisi"], ascending=False).head(n)
    df.insert(0, "kume", range(1, len(df) + 1))
    df["esik"] = esik
    return df.reset_index(drop=True)


def _en_yakin_il(iy: int, ix: int, il_of: np.ndarray) -> str:
    yy, xx = np.nonzero(il_of != "")
    if not len(yy):
        return ""
    k = np.argmin((yy - iy) ** 2 + (xx - ix) ** 2)
    return il_of[yy[k], xx[k]]


# ---------------------------------------------------------------- il tablosu
def _alan_ort(v: np.ndarray, m: np.ndarray, lat) -> float:
    w = np.cos(np.deg2rad(np.asarray(lat)))[:, None] * np.ones_like(v)
    ok = m & np.isfinite(v)
    return float(np.average(v[ok], weights=w[ok])) if ok.any() else float("nan")


def il_notu(sapma: float, ters: str, rejim: str, iz: float) -> str:
    """İl satırı için dil kuralına uygun kısa not."""
    parca = []
    if np.isfinite(sapma) and sapma > 0:
        parca.append(f"Fiziksel beklentiden sapma: çift {ters} ters yönde. Olası açıklamalar: iklim rejimi, "
                     "veri/ürün sorunu, insan müdahalesi (sulama, baraj, yeraltı suyu çekimi); doğrulanmadı.")
    if rejim:
        parca.append(f"Çift {rejim} ters yönde ama su sınırlı iklimde bu beklenen işarettir (rejimle açıklanabilir).")
    if np.isfinite(iz) and iz >= SULAMA_IZI_ESIK:
        parca.append(SULAMA_NOTU)
    return " ".join(parca)


def il_tablosu(il_et: pd.DataFrame, rejime_bagli: set[int], il_kurak: pd.Series, il_ep: pd.Series,
               sulama: dict[str, np.ndarray], il_maskeleri: dict[str, np.ndarray], iller: list[dict],
               lat) -> pd.DataFrame:
    """81 il: sapma skoru (L4 il satırlarından), rejim, il ortalaması sulama izi ve bileşenleri."""
    kodlar = [b["bolge_kodu"] for b in iller]
    et = il_et.reindex(kodlar)
    sk = sapma_skoru({no: et[no].to_numpy(float) for no in et.columns}, rejime_bagli,
                     il_kurak.reindex(kodlar).fillna(False).to_numpy(bool))
    satir = []
    for i, b in enumerate(iller):
        m = il_maskeleri[b["anahtar"]]
        zy, zs = _alan_ort(sulama["z_yesil"], m, lat), _alan_ort(sulama["z_serin"], m, lat)
        iz = _alan_ort(sulama["sulama_izi"], m, lat)
        bil = {"yesillik (z_yesil)": zy, "serinlik (z_serin)": zs}
        bil = {k: v for k, v in bil.items() if np.isfinite(v)}
        ters, rej = bit_listesi(sk["ters_bit"][i]), bit_listesi(sk["rejim_bit"][i])
        satir.append({
            "bolge_kodu": b["bolge_kodu"], "il": b["bolge_adi"],
            "sapma_sayisi": sk["sapma_sayisi"][i], "degerlendirilen_cift": int(sk["degerlendirilen"][i]),
            "sapma_orani": sk["sapma_orani"][i], "ters_ciftler": ters,
            "rejimle_aciklanan": sk["rejimle_aciklanan"][i], "rejimle_aciklanan_ciftler": rej,
            "sapma_sayisi_rejim_oncesi": sk["sapma_sayisi_ham"][i],
            "kuraklik_gostergesi": il_ep.get(b["bolge_kodu"], np.nan),
            "su_sinirli": bool(il_kurak.get(b["bolge_kodu"], False)),
            "sulama_izi": iz, "z_yesil": zy, "z_serin": zs,
            "sulama_izi_hucre_en_yuksek": float(np.nanmax(np.where(m, sulama["sulama_izi"], np.nan)))
            if np.isfinite(np.where(m, sulama["sulama_izi"], np.nan)).any() else np.nan,
            "en_yuksek_bilesen": max(bil, key=bil.get) if bil else "",
            "not": il_notu(sk["sapma_sayisi"][i], ters, rej, iz)})
    return pd.DataFrame(satir)


# ---------------------------------------------------------------- akış
def _oku(kup: Path, degisken: str, urun: str) -> xr.DataArray | None:
    f = Path(kup) / f"{degisken}__{urun}.nc"
    if not f.exists():
        return None
    with xr.open_dataset(f) as ds:
        da = (ds[degisken] if degisken in ds else ds[list(ds.data_vars)[0]]).load()
        da.attrs = {**ds.attrs, **da.attrs}
    return da


def uret(paket: Path, ayar: Path = AYAR_DOSYASI) -> dict:
    """Paketten sapma haritası, il tablosu ve kümeleri üretir (yazmaz). Eksik L4 → ValueError."""
    from physics.tablo import bolge_listesi, bolge_maskeleri
    paket = Path(paket)
    l4, kup = paket / "L4_iliski", paket / "L1_kup"
    if not (l4 / "ciftler.csv").exists():
        raise ValueError(f"L4 çıktısı yok: {l4 / 'ciftler.csv'}. Önce: python -m physics.run --paket {paket}")
    a = ayar_oku(ayar)
    ciftler, rejim = a["ciftler"], a["rejim"]
    if not rejim:
        raise ValueError(f"{ayar}: 'rejim' bölümü yok (kuraklık göstergesi ayarı)")
    rejime_bagli = {c.no for c in ciftler if c.rejime_bagli}

    g = {k: _oku(kup, *v) for k, v in GIRDILER.items()}
    if g["yagis"] is None or g["rakim"] is None:
        raise ValueError("sulama izi için yagis__GPM ve rakim__SRTM gerekli")
    p_r = _oku(kup, rejim["yagis"]["degisken"], rejim["yagis"]["urun"])
    e_r = _oku(kup, rejim["buharlasma"]["degisken"], rejim["buharlasma"]["urun"])
    if p_r is None or e_r is None:
        raise ValueError("kuraklık göstergesi için GLDAS yağış ve buharlaşma gerekli")
    sablon = g["yagis"].isel(time=0, drop=True)
    lat, lon = sablon["lat"].values, sablon["lon"].values
    iller = [b for b in bolge_listesi(iller=True) if b["bolge_turu"] == "il"]
    maskeler = bolge_maskeleri(lat, lon, True)
    il_m = {b["anahtar"]: maskeler[b["anahtar"]] for b in iller}
    kara = maskeler["turkiye"]

    ep = kuraklik_gostergesi(p_r, e_r)
    esik = float(rejim["su_sinirli_esik"])
    kurak = (ep >= esik).values
    hucre = sapma_skoru(hucre_etiketleri(l4, ciftler), rejime_bagli, kurak)
    sul = sulama_izi(g["ndvi"], g["lst"], g["t2m"], g["yagis"], g["rakim"], kara)

    # il düzeyi: E/P, il alanında GLDAS yıllık E ve P'nin ayrı ayrı alan ortalamasının oranı
    p_yil = iklim_ortalamasi(p_r, "yillik", True).values
    e_yil = iklim_ortalamasi(e_r, "yillik", True).values
    il_ep = pd.Series({b["bolge_kodu"]: _alan_ort(e_yil, il_m[b["anahtar"]], lat)
                       / _alan_ort(p_yil, il_m[b["anahtar"]], lat) for b in iller})
    il_tab = il_tablosu(il_etiketleri(l4 / "ciftler.csv", ciftler), rejime_bagli, il_ep >= esik, il_ep,
                        sul, il_m, iller, lat)
    kume = kumeler(sul["sulama_izi"], lat, lon, il_m, {b["anahtar"]: b["bolge_adi"] for b in iller})
    ortak = {k: g["yagis"].attrs.get(k, "") for k in ("urun_surumu", "veri_seti_doi", "lisans")}
    return {"hucre": hucre, "sulama": sul, "kuraklik": ep.values, "su_sinirli": kurak, "esik": esik,
            "lat": lat, "lon": lon, "kara": kara, "iller": il_tab, "kumeler": kume, "ortak": ortak,
            "ciftler": ciftler, "rejime_bagli": sorted(rejime_bagli)}


def haritayi_kur(s: dict) -> xr.Dataset:
    """``sapma_haritasi.nc`` içeriği (lat, lon)."""
    k = {"coords": {"lat": s["lat"], "lon": s["lon"]}, "dims": ("lat", "lon")}
    kara = s["kara"]

    def f32(v, ad, birim="1"):
        return xr.DataArray(np.where(kara, v, np.nan).astype(np.float32), **k,
                            attrs={"long_name": ad, "units": birim})

    h, sl = s["hucre"], s["sulama"]
    haritali = [c for c in s["ciftler"] if c.harita]
    bitler = np.array([1 << (c.no - 1) for c in haritali], np.int32)
    bit_ad = " ".join(f"cift_{c.no}" for c in haritali)
    ds = xr.Dataset({
        "sapma_sayisi": f32(h["sapma_sayisi"], "ters yönde çıkan ve rejimle açıklanmayan çift sayısı"),
        "degerlendirilen": f32(np.where(h["degerlendirilen"] > 0, h["degerlendirilen"], np.nan),
                               "etiketi olan (değerlendirilebilen) çift sayısı"),
        "sapma_orani": f32(h["sapma_orani"], "sapma_sayisi / degerlendirilen"),
        "rejimle_aciklanan": f32(h["rejimle_aciklanan"], "rejime bağlı çiftin su sınırlı yerdeki ters sonucu (sayı)"),
        "sapma_sayisi_rejim_oncesi": f32(h["sapma_sayisi_ham"], "rejim ayrımı yapılmadan ters çift sayısı"),
        "ters_ciftler": xr.DataArray(np.where(kara, h["ters_bit"], 0).astype(np.int32), **k, attrs={
            "long_name": "sapma sayılan ters çiftler (bit maskesi)", "flag_masks": bitler,
            "flag_meanings": bit_ad}),
        "rejimle_aciklanan_ciftler": xr.DataArray(np.where(kara, h["rejim_bit"], 0).astype(np.int32), **k, attrs={
            "long_name": "rejimle açıklanan ters çiftler (bit maskesi)", "flag_masks": bitler,
            "flag_meanings": bit_ad}),
        "kuraklik_gostergesi": f32(s["kuraklik"], "GLDAS uzun dönem yıllık buharlaşma / yağış (E/P)"),
        "su_sinirli": xr.DataArray(np.where(kara, s["su_sinirli"], 0).astype(np.int8), **k,
                                   attrs={"long_name": f"1 = E/P ≥ {s['esik']:g} (su sınırlı)"}),
        "sulama_izi": f32(sl["sulama_izi"], "sulama izi: z_yesil ve z_serin ortalaması"),
        "z_yesil": f32(sl["z_yesil"], "yaz NDVI'sının yağış ve rakıma göre beklenenden yüksekliği (z)"),
        "z_serin": f32(sl["z_serin"], "yaz (LST gündüz − T2M) farkının beklenenden düşüklüğü (z, işareti ters)"),
        "n_bilesen": xr.DataArray(np.where(kara, sl["n_bilesen"], 0).astype(np.int8), **k,
                                  attrs={"long_name": "sulama_izi'ne giren bileşen sayısı"}),
    })
    ds.attrs.update({k2: v for k2, v in s["ortak"].items() if v})
    ds.attrs.update({
        "baslik": "Beklentiden sapma haritası (Trend Dedektifi, physics.sapma)",
        "yontem": ("Sapma: ciftler.yaml çiftlerinin L4 hücre etiketlerinden ters_yonde sayısı; rejime_bagli "
                   f"çiftlerde (çift {', '.join(map(str, s['rejime_bagli'])) or '-'}) E/P ≥ {s['esik']:g} olan "
                   "hücredeki ters sonuç rejimle açıklanan sayılır. Sulama izi: iklimsel yaz NDVI ve "
                   "(LST gündüz − T2M) değerlerinin log(1+yaz yağışı), log(1+kış+ilkbahar yağışı) ve rakım "
                   "üzerine EKK regresyon artıkları (z), ortalaması. Haritasız çift (GRACE) hücrede yok."),
        "uyari": UYARI, "not": f"{MODIS_NOTU} {TOPRAK_NEMI_NOTU}",
        "girdiler": "L4_iliski/iliski__*.nc, L1_kup: ndvi__MOD13C2, yuzey_sicakligi_gunduz__MOD11C3, "
                    "sicaklik_2m__MERRA2, yagis__GPM, rakim__SRTM, yagis__GLDAS, buharlasma__GLDAS",
        "uretim": "python -m physics.sapma",
    })
    return ds


def yaz(s: dict, hedef: Path) -> list[Path]:
    """``sapma_haritasi.nc``, ``sapma_iller.csv``, ``sulama_izi_kumeleri.csv`` yazar."""
    hedef = Path(hedef)
    hedef.mkdir(parents=True, exist_ok=True)
    nc = hedef / "sapma_haritasi.nc"
    haritayi_kur(s).to_netcdf(nc)
    il = s["iller"].copy()
    for k2, v in s["ortak"].items():
        il[k2] = v
    il["uyari"] = UYARI
    yollar = [nc]
    for df, ad in ((il, "sapma_iller.csv"), (s["kumeler"], "sulama_izi_kumeleri.csv")):
        out = df.copy()
        for c in ("sapma_sayisi", "rejimle_aciklanan", "sapma_sayisi_rejim_oncesi"):
            if c in out:
                out[c] = out[c].astype("Int64")
        p = hedef / ad
        out.to_csv(p, index=False, encoding="utf-8-sig", na_rep="", float_format="%.4g")
        yollar.append(p)
    return yollar


def html_harita(s: dict, yol: Path) -> Path:
    """Sunum için tek sayfalık HTML: sulama izi ve sapma oranı, il sınırları ve küme numaraları."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from data.regions import _read_geojson
    fig = make_subplots(rows=1, cols=2, horizontal_spacing=0.06,
                        subplot_titles=("Sulama izi (z): yağışın açıkladığından yeşil/serin yaz",
                                        "Sapma oranı: ters yönde çıkan çiftler (rejimle açıklananlar hariç)"))
    k = s["kara"]
    fig.add_trace(go.Heatmap(z=np.where(k, s["sulama"]["sulama_izi"], np.nan), x=s["lon"], y=s["lat"],
                             colorscale="RdBu_r", zmid=0, zmin=-3, zmax=3, colorbar=dict(x=0.46, title="z")),
                  1, 1)
    fig.add_trace(go.Heatmap(z=np.where(k, s["hucre"]["sapma_orani"], np.nan), x=s["lon"], y=s["lat"],
                             colorscale="Oranges", zmin=0, zmax=1, colorbar=dict(x=1.0, title="oran")), 1, 2)
    xs, ys = [], []
    for ft in _read_geojson("iller.geojson")["features"]:
        geo = ft["geometry"]
        pol = geo["coordinates"] if geo["type"] == "MultiPolygon" else [geo["coordinates"]]
        for p in pol:
            halka = np.asarray(p[0])
            xs += list(halka[:, 0]) + [None]
            ys += list(halka[:, 1]) + [None]
    for col in (1, 2):
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="rgba(40,40,40,.55)", width=0.6),
                                 hoverinfo="skip", showlegend=False), 1, col)
    km = s["kumeler"]
    if len(km):
        fig.add_trace(go.Scatter(x=km["tepe_lon"], y=km["tepe_lat"], mode="markers+text", text=km["kume"].astype(str),
                                 textposition="top center", marker=dict(size=9, color="black", symbol="circle-open"),
                                 hovertext=[f"Küme {r.kume}: {r.il} · tepe z {r.tepe_sulama_izi:.2f} · {r.hucre_sayisi} hücre"
                                            for r in km.itertuples()], hoverinfo="text", showlegend=False), 1, 1)
    fig.update_xaxes(range=[s["lon"].min() - 0.2, s["lon"].max() + 0.2], showgrid=False)
    fig.update_yaxes(range=[s["lat"].min() - 0.2, s["lat"].max() + 0.2], showgrid=False, scaleanchor="x")
    fig.update_yaxes(scaleanchor="x2", row=1, col=2)
    fig.update_layout(height=520, margin=dict(l=20, r=20, t=60, b=70), plot_bgcolor="white",
                      title="Beklentiden sapma haritası (Trend Dedektifi v0.1)",
                      annotations=list(fig.layout.annotations) + [dict(
                          text=UYARI, showarrow=False, xref="paper", yref="paper", x=0, y=-0.14,
                          xanchor="left", font=dict(size=11))])
    fig.write_html(yol, include_plotlyjs=True)
    return yol


def ozet_yazdir(s: dict, yollar: list[Path], sure: float) -> None:
    il = s["iller"]
    h = s["hucre"]
    kara = s["kara"]
    oncesi = int((il["sapma_sayisi_rejim_oncesi"] > 0).sum())
    sonrasi = int((il["sapma_sayisi"] > 0).sum())
    gecen = int(((il["sapma_sayisi_rejim_oncesi"] > 0) & (il["sapma_sayisi"] == 0)).sum())
    print("BEKLENTİDEN SAPMA HARİTASI (doğrulanmadı; neden göstermez)")
    print(f"  su sınırlı (E/P ≥ {s['esik']:g}) kara hücresi: {int((s['su_sinirli'] & kara).sum())} / {int(kara.sum())}")
    hc_on = int(((h["sapma_sayisi_ham"] > 0) & kara).sum())
    hc_son = int(((h["sapma_sayisi"] > 0) & kara).sum())
    print(f"  sapmalı hücre: rejim ayrımı öncesi {hc_on} → sonrası {hc_son}")
    print(f"  sapmalı il: rejim ayrımı öncesi {oncesi} → sonrası {sonrasi} "
          f"({gecen} il yalnız 'rejimle açıklanan' oldu)")
    print("  en yüksek sulama izi kümeleri (kör yöntem; tepe z, hücre sayısı, il):")
    for r in s["kumeler"].itertuples():
        print(f"    {r.kume:2d}. {r.il:15s} z={r.tepe_sulama_izi:4.2f} ort={r.ortalama_sulama_izi:4.2f} "
              f"{r.hucre_sayisi:3d} hücre · tepe {r.tepe_lat:.2f}K {r.tepe_lon:.2f}D · iller: {r.iller}")
    print(f"  ⚠ {UYARI}")
    print(f"  ⚠ {MODIS_NOTU}")
    print(f"  ⚠ {TOPRAK_NEMI_NOTU}")
    for p in yollar:
        print(" ", p)
    print(f"  süre: {sure:.1f} sn")


# ---------------------------------------------------------------- v2: tarım maskesi + 0,05° (2026-11-15)
# Önceden tanımlı iki değişiklik (v1 sonuçlarına bakarak ayarlanmadı): (1) tarım maskesi, (2) 0,05° çözünürlük.
# Bileşenler ve regresyon biçimi v1 ile aynıdır; maske regresyondan SONRA uygulanır (regresyon v1'deki gibi
# bütün kara hücrelerinde kurulur). Doğrulama katmanı (GFSAD sulanan oran) bu bölümde hiç okunmaz.
TARIM_ESIK = 0.3            # sabit; 0,2 ve 0,5 yalnız raporda duyarlılık (physics.sapma_dogrulama)
V2_DOSYALARI = {"025": "sapma_haritasi_v2_025.nc", "005": "sapma_haritasi_v2_005.nc"}
V2_KUMELER = "sulama_izi_kumeleri_v2.csv"
V2_NOTU = ("v2: tarım maskesi (MCD12C1 tarim_orani < {esik:g} → NaN, 'tarım dışı') ve {grid} çözünürlük. "
           "Bileşenler ve regresyon biçimi v1 ile aynı; maske regresyondan sonra uygulanır.")
NN_NOTU = ("0,05°: NDVI (MOD13C2) ve LST (MOD11C3) 0,05° CMG dosyalarından, rakım SRTM 0,05° ortalamasından, "
           "tarım oranı MCD12C1 0,05°'den; yağış (GPM) ve T2M (MERRA-2) 0,25° L1'den en yakın komşu ile aktarıldı.")


def tarim_maskesi(sulama: dict[str, np.ndarray], tarim: np.ndarray, esik: float = TARIM_ESIK) -> dict:
    """``tarim_orani < esik`` (ya da tarım oranı bilinmeyen) hücrelerde sulama izi ve bileşenleri NaN.

    Döndürür: aynı anahtarlar + ``tarim_disi`` (bool). Maske dışında değerler değişmez.
    """
    m = np.asarray(tarim, float) >= esik                 # NaN → False (tarım dışı sayılır)
    out = {k: np.where(m, np.asarray(sulama[k], float), np.nan) for k in ("z_yesil", "z_serin", "sulama_izi")}
    out["n_bilesen"] = np.where(m, sulama["n_bilesen"], 0).astype(np.int8)
    out["tarim_disi"] = ~m
    return out


def _cache_oku(degisken: str, urun: str, grid: str) -> xr.DataArray | None:
    from data.grid import processed_path
    p = processed_path(degisken, urun, grid)
    return _oku(p.parent, f"{degisken}", f"{urun}__{grid}") if grid != "025" else _oku(p.parent, degisken, urun)


def _hizala(da: xr.DataArray, lat, lon, en_yakin: bool) -> xr.DataArray:
    """``da``yı (lat, lon) hücre merkezlerine taşır: en yakın komşu ya da aynı koordinatların seçimi."""
    if en_yakin:
        out = da.sel(lat=xr.DataArray(lat, dims="lat"), lon=xr.DataArray(lon, dims="lon"), method="nearest")
    else:
        out = da.sel(lat=xr.DataArray(lat, dims="lat"), lon=xr.DataArray(lon, dims="lon"), method="nearest",
                     tolerance=1e-4)
    return out.assign_coords(lat=lat, lon=lon)


def sulama_izi_v2(paket: Path, grid: str = "025", maske: bool = True, esik: float = TARIM_ESIK) -> dict:
    """v2 sulama izi. ``grid``: "025" (L1 paketi) ya da "005" (0,05° CMG dosyaları, cache/processed).

    ``maske=False`` ile v1 yöntemi aynı ızgarada çalışır (0,25°'de sonuç v1 ile birebir aynıdır).
    Döndürür: {"grid", "lat", "lon", "kara", "il_maskeleri", "il_adlari", "sulama", "tarim", "esik", "maske"}.
    """
    from physics.tablo import bolge_listesi, bolge_maskeleri
    paket = Path(paket)
    kup = paket / "L1_kup"
    yagis, t2m = _oku(kup, *GIRDILER["yagis"]), _oku(kup, *GIRDILER["t2m"])
    if yagis is None or t2m is None:
        raise ValueError("v2 için L1 yagis__GPM ve sicaklik_2m__MERRA2 gerekli")
    if grid == "025":
        ndvi, lst, rakim = (_oku(kup, *GIRDILER[k]) for k in ("ndvi", "lst", "rakim"))
        tarim = _oku(kup, "tarim_orani", "MCD12C1")
        lat, lon = yagis["lat"].values, yagis["lon"].values
    elif grid == "005":
        ndvi = _cache_oku("ndvi", "MOD13C2", "005")
        lst = _cache_oku("yuzey_sicakligi_gunduz", "MOD11C3", "005")
        rakim = _cache_oku("rakim", "SRTM", "005")
        tarim = _cache_oku("tarim_orani", "MCD12C1", "005")
        if ndvi is None or rakim is None:
            raise ValueError("0,05° için cache/processed/turkiye/ndvi__MOD13C2__005.nc ve rakim__SRTM__005.nc gerekli")
        # yayın kutusu (L1 ile aynı alan): hücre merkezi L1 kutusunun içinde kalan 0,05° hücreler
        la, lo = yagis["lat"].values, yagis["lon"].values
        s_, n_, w_, e_ = la.min() - 0.125, la.max() + 0.125, lo.min() - 0.125, lo.max() + 0.125
        lat = ndvi["lat"].values[(ndvi["lat"].values > s_) & (ndvi["lat"].values < n_)]
        lon = ndvi["lon"].values[(ndvi["lon"].values > w_) & (ndvi["lon"].values < e_)]
        ndvi = _hizala(ndvi, lat, lon, False)
        lst = _hizala(lst, lat, lon, False) if lst is not None else None
        rakim = _hizala(rakim, lat, lon, False)
        yagis, t2m = _hizala(yagis, lat, lon, True), _hizala(t2m, lat, lon, True)
        if tarim is not None:
            tarim = _hizala(tarim, lat, lon, False)
    else:
        raise ValueError(f"bilinmeyen ızgara: {grid}")
    if maske and tarim is None:
        raise ValueError("tarım maskesi için tarim_orani__MCD12C1 gerekli; önce: python -m data.arazi --surum v0.1")
    iller = [b for b in bolge_listesi(iller=True) if b["bolge_turu"] == "il"]
    maskeler = bolge_maskeleri(lat, lon, True)
    kara = maskeler["turkiye"]
    sul = sulama_izi(ndvi, lst, t2m, yagis, rakim, kara)
    tarim_v = np.asarray(tarim.values, float) if tarim is not None else np.full(kara.shape, np.nan)
    if maske:
        sul = tarim_maskesi(sul, tarim_v, esik)
    return {"grid": grid, "lat": lat, "lon": lon, "kara": kara,
            "il_maskeleri": {b["anahtar"]: maskeler[b["anahtar"]] for b in iller},
            "il_adlari": {b["anahtar"]: b["bolge_adi"] for b in iller}, "sulama": sul, "tarim": tarim_v,
            "esik": esik, "maske": maske}


def v2_harita(v: dict, ortak: dict) -> xr.Dataset:
    """``sapma_haritasi_v2_<grid>.nc`` içeriği (yalnız sulama izi; sapma skoru v1 dosyasında, değişmedi)."""
    k = {"coords": {"lat": v["lat"], "lon": v["lon"]}, "dims": ("lat", "lon")}
    kara, s = v["kara"], v["sulama"]

    def f32(x, ad):
        return xr.DataArray(np.where(kara, x, np.nan).astype(np.float32), **k, attrs={"long_name": ad, "units": "1"})
    cozunurluk = "0,25°" if v["grid"] == "025" else "0,05°"
    ds = xr.Dataset({
        "sulama_izi": f32(s["sulama_izi"], "sulama izi v2: z_yesil ve z_serin ortalaması (tarım dışı NaN)"),
        "z_yesil": f32(s["z_yesil"], "yaz NDVI'sının yağış ve rakıma göre beklenenden yüksekliği (z)"),
        "z_serin": f32(s["z_serin"], "yaz (LST gündüz − T2M) farkının beklenenden düşüklüğü (z, işareti ters)"),
        "n_bilesen": xr.DataArray(np.where(kara, s["n_bilesen"], 0).astype(np.int8), **k,
                                  attrs={"long_name": "sulama_izi'ne giren bileşen sayısı"}),
        "tarim_orani": f32(v["tarim"], "MCD12C1 tarım oranı (IGBP 12 + ½·14), 5 yıl ortalaması"),
        "tarim_disi": xr.DataArray(np.where(kara, s.get("tarim_disi", np.zeros(kara.shape, bool)), 0).astype(np.int8),
                                   **k, attrs={"long_name": f"1 = tarim_orani < {v['esik']:g} (maskelendi)"}),
    })
    ds.attrs.update({k2: x for k2, x in ortak.items() if x})
    ds.attrs.update({
        "baslik": f"Beklentiden sapma haritası v2, sulama izi ({cozunurluk})",
        "yontem": V2_NOTU.format(esik=v["esik"], grid=cozunurluk) + (f" {NN_NOTU}" if v["grid"] == "005" else ""),
        "uyari": UYARI, "not": f"{MODIS_NOTU} {TOPRAK_NEMI_NOTU} Sapma skoru değişmedi: sapma_haritasi.nc (v1).",
        "surum": "v2", "tarim_esigi": v["esik"], "uretim": "python -m physics.sapma --v2",
    })
    return ds


def v2_uret_yaz(paket: Path) -> dict:
    """v2'yi iki ızgarada üretir; L4_iliski/sapma/ altına YENİ v2 dosyalarını yazar (v1 dosyalarına dokunmaz)."""
    paket = Path(paket)
    hedef = paket / "L4_iliski" / KLASOR
    hedef.mkdir(parents=True, exist_ok=True)
    yagis = _oku(paket / "L1_kup", *GIRDILER["yagis"])
    ortak = {k: yagis.attrs.get(k, "") for k in ("urun_surumu", "veri_seti_doi", "lisans")}
    sonuc, yollar = {}, []
    for grid in ("025", "005"):
        v = sulama_izi_v2(paket, grid, maske=True)
        p = hedef / V2_DOSYALARI[grid]
        v2_harita(v, ortak).to_netcdf(p)
        yollar.append(p)
        sonuc[grid] = v
    v = sonuc["005"]
    km = kumeler(v["sulama"]["sulama_izi"], v["lat"], v["lon"], v["il_maskeleri"], v["il_adlari"])
    p = hedef / V2_KUMELER
    km.to_csv(p, index=False, encoding="utf-8-sig", float_format="%.4g")
    yollar.append(p)
    return {"v2": sonuc, "kumeler": km, "yollar": yollar}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m physics.sapma", description=__doc__.splitlines()[0])
    ap.add_argument("--surum", default="v0.1")
    ap.add_argument("--paket", type=Path, default=None)
    ap.add_argument("--ciftler", type=Path, default=AYAR_DOSYASI)
    ap.add_argument("--goster", action="store_true", help="HTML harita yaz ve tarayıcıda aç")
    ap.add_argument("--v2", action="store_true",
                    help="v2: tarım maskesi + 0,05° (yalnız v2 dosyaları yazılır; v1 dosyalarına dokunulmaz)")
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    if a.paket is None:
        from data.export import OUTPUTS_DIR
        a.paket = OUTPUTS_DIR / f"trend-dedektifi-turkiye-{a.surum}"
    if a.v2:
        try:
            r = v2_uret_yaz(a.paket)
        except ValueError as e:
            raise SystemExit(f"HATA: {e}") from None
        print("BEKLENTİDEN SAPMA HARİTASI v2 · sulama izi (doğrulanmadı; neden göstermez)")
        for g, v in r["v2"].items():
            kara = v["kara"]
            print(f"  {g}: kara {int(kara.sum())} hücre, tarım dışı (maskeli) {int((v['sulama']['tarim_disi'] & kara).sum())}, "
                  f"değerli {int((np.isfinite(v['sulama']['sulama_izi']) & kara).sum())}")
        for x in r["kumeler"].itertuples():
            print(f"    {x.kume:2d}. {x.il:15s} z={x.tepe_sulama_izi:4.2f} {x.hucre_sayisi:3d} hücre · "
                  f"tepe {x.tepe_lat:.3f}K {x.tepe_lon:.3f}D")
        print(f"  ⚠ {UYARI}")
        dg = Path(a.paket) / "dogrulama" / "sulanan_oran__GFSAD1KCM.nc"
        if dg.exists():                      # bağımsız doğrulama: sulama izi hesaplandıktan SONRA
            from physics.sapma_dogrulama import dogrula
            d = dogrula(a.paket, r)
            r["yollar"] += d["yollar"]
            print(d["tablo"].to_string(index=False))
        for p in r["yollar"]:
            print(" ", p)
        print(f"  süre: {time.perf_counter() - t0:.1f} sn")
        return
    try:
        s = uret(a.paket, a.ciftler)
    except ValueError as e:
        raise SystemExit(f"HATA: {e}") from None
    hedef = Path(a.paket) / "L4_iliski" / KLASOR
    yollar = yaz(s, hedef)
    if a.goster:
        h = html_harita(s, hedef / "sapma_haritasi.html")
        yollar.append(h)
        import webbrowser
        webbrowser.open(h.resolve().as_uri())
    ozet_yazdir(s, yollar, time.perf_counter() - t0)


if __name__ == "__main__":
    main()
