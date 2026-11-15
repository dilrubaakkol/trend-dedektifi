"""Bulgu karnesi: her trend (L3) ve ilişki (L4) sonucunun yanına şeffaf bir güven karnesi.

    python -m stats.karne --surum v0.1                  # trend + ilişki → <paket>/karne/
    python -m stats.karne --surum v0.1 --yalniz trend   # yalnız trend karnesi

Karne mevcut L2/L3/L4 dosyalarını değiştirmez; ayrı dosyalara yazılır. Her kontrol ayrı sütundur
(``geçti`` / ``kaldı`` / ``uygulanamaz`` + sayı). Güven seviyesi önceden sabit bir kuralla verilir
(``KURAL_METNI``; docs/sozlesmeler.md "Bulgu karnesi"). Karne bir sağlamlık ve tutarlılık özetidir;
bir sonucun doğruluğunu ya da nedenselliğini kanıtlamaz.

Trend kontrolleri (L3 il/bölge/Türkiye × mevsim serileri):
  a) kaynak uyumu   b) dairesel blok permütasyonu (p_perm < 0,10)   c) ilk/son 3 yıl çıkarılınca
  d) α = 0,05'te de anlamlı mı   e) Weatherhead gereken yıl ≤ mevcut yıl   f) uyarılar
İlişki kontrolleri (physics/karne.py): a) alternatif ürünler b) permütasyon c) trendden arındırma
  d) gecikme ±1 ay e) α = 0,05 f) uyarılar.
"""

from __future__ import annotations

import argparse
import math
import time
import zlib
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

GECTI, KALDI, UYG = "geçti", "kaldı", "uygulanamaz"
YUKSEK, ORTA, DUSUK, YOK = "YÜKSEK", "ORTA", "DÜŞÜK", "YOK"
TEKRAR = 499
TOHUM = 2026
ESIK_PERM = 0.10
ALFA_SIKI = 0.05
KIRPMA_YIL = 3
KURAL_SURUMU = "karne-v1 (2026-11-15)"
KURAL_METNI = f"""BULGU KARNESİ GÜVEN KURALI ({KURAL_SURUMU}; sonuçlar görülmeden sabitlendi)

Kontroller her sonuç için ayrı sütundur: geçti / kaldı / uygulanamaz. "uygulanamaz" geçti sayılmaz.
Trend:  a kaynak uyumu (bu ürün dahil en az 2 ürün anlamlı ve aynı yönde; tek ürün → uygulanamaz)
        b karıştırma testi: dairesel blok permütasyonu, blok = ceil(n / etkin_n), {TEKRAR} tekrar, sabit tohum;
          p_perm = (1 + #{{|Sen eğimi_perm| ≥ |Sen eğimi|}}) / ({TEKRAR} + 1); p_perm < {ESIK_PERM:g} → geçti
        c dönem duyarlılığı: ilk {KIRPMA_YIL} ve son {KIRPMA_YIL} geçerli yıl ayrı ayrı çıkarılınca işaret korunuyor ve
          anlamlılık sürüyor (alt dönemde FDR uygulanamaz: p_mk ≤ 0,10 ve %95 GA sıfırı dışlar)
        d eşik duyarlılığı: α = {ALFA_SIKI:g}'te de anlamlı (p_fdr ≤ {ALFA_SIKI:g} ve GA sıfırı dışlar)
        e veri yeterliliği: Weatherhead gereken_yil ≤ geçerli yıl sayısı
        f uyarılar: trend_uyarisi, bilinen_sorunlar, Kademe 2 (doğrulanmadı) KRİTİK; mk_yedek yalnız listelenir
İlişki: a alternatif ürün kombinasyonları (en az 2 kombinasyon aynı etiket; alternatif yok → uygulanamaz)
        b karıştırma testi: trendi giderilmiş y serisi dairesel blok permütasyonuyla karıştırılır (aynı kurallar)
        c trendden arındırma: trendsiz r ile ham r aynı işaretli ve |r| ≥ |ham r| / 2
        d gecikme duyarlılığı: gecikme ±1 ayda r'nin işareti korunuyor (negatif gecikme ve mevsimlik seri → uygulanamaz)
        e eşik: α = {ALFA_SIKI:g}'te de aynı etiket (il: p_fdr ≤ {ALFA_SIKI:g}; bölge/Türkiye zaten p < 0,05)
        f uyarılar: ürün uyarıları (bilinen_sorunlar, trend_uyarisi, Kademe 2), rejime bağlı çift, az hücre (< 3) KRİTİK

Güven:
  YOK    : sonuç anlamlı değil (trend/ilişki iddiası yok). Trendde e kaldıysa "veri henüz yetmiyor" yazılır.
  DÜŞÜK  : anlamlı ama b ya da c geçmedi.
  YÜKSEK : anlamlı; a, b, c, d, e geçti; kritik uyarı yok.
  ORTA   : anlamlı; b ve c geçti ama YÜKSEK'in başka bir şartı sağlanmadı (ör. tek kaynak, d/e kaldı, uyarı).
Karne bir sağlamlık ve tutarlılık özetidir; doğruluk ya da nedensellik göstermez.
"""


# ---------------------------------------------------------------- ortak yardımcılar
def tohum(anahtar: str, temel: int = TOHUM) -> int:
    """Satıra özgü ama sıradan bağımsız sabit tohum (aynı satır her çalıştırmada aynı karışımı alır)."""
    return (zlib.crc32(anahtar.encode("utf-8")) ^ temel) & 0x7FFFFFFF


def blok_uzunlugu(n: int, n_etkin: float) -> int:
    """Blok uzunluğu = ceil(n / etkin_n), en az 1, en çok n // 2 (en az iki blok kalsın)."""
    if not (n_etkin and np.isfinite(n_etkin) and n_etkin > 0):
        return 1
    return int(np.clip(math.ceil(n / n_etkin), 1, max(1, n // 2)))


def dairesel_blok_indeksleri(n: int, blok: int, tekrar: int, rng: np.random.Generator) -> np.ndarray:
    """(tekrar, n) indeks dizisi: seri halka gibi düşünülür, rastgele bir noktadan ``blok`` uzunluğunda
    parçalara bölünür, parçaların sırası karıştırılır. Blok içindeki ardışıklık (otokorelasyon) korunur."""
    nb = math.ceil(n / blok)
    konum = np.arange(nb * blok)
    bas = rng.integers(0, n, size=tekrar)[:, None]
    # son blok kısa olabilir: n'yi aşan konumlar dolgu (−1) olarak işaretlenir ve sonda atılır
    tam = np.where(konum[None] < n, (bas + konum[None]) % n, -1)        # (tekrar, nb·blok)
    sira = np.argsort(rng.random((tekrar, nb)), axis=1)
    parca = np.take_along_axis(tam.reshape(tekrar, nb, blok), sira[:, :, None], axis=1).reshape(tekrar, -1)
    return parca[parca >= 0].reshape(tekrar, n)                         # her satır 0..n−1'in bir permütasyonu


def sen_egimleri(Y: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Satır başına Sen eğimi (ikili eğimlerin NaN atlayan medyanı). Y: (k, n), t: (n,)."""
    Y = np.atleast_2d(np.asarray(Y, float))
    t = np.asarray(t, float)
    i, j = np.triu_indices(len(t), 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        e = (Y[:, j] - Y[:, i]) / (t[j] - t[i])
    e[~np.isfinite(e)] = np.nan
    out = np.full(Y.shape[0], np.nan)
    ok = np.isfinite(e).any(1)
    out[ok] = np.nanmedian(e[ok], axis=1)
    return out


def perm_p(gozlenen: float, dagilim: np.ndarray) -> float:
    """İki yönlü permütasyon p'si: (1 + #{|d| ≥ |g|}) / (R + 1)."""
    d = np.asarray(dagilim, float)
    d = d[np.isfinite(d)]
    if not np.isfinite(gozlenen) or d.size == 0:
        return float("nan")
    return float((1 + np.sum(np.abs(d) >= abs(gozlenen) - 1e-12)) / (d.size + 1))


def guven_seviyesi(anlamli: bool, kontrol: dict[str, str], kritik: list[str],
                   yuksek_icin: tuple = ("a", "b", "c", "d", "e"), dusuk_icin: tuple = ("b", "c"),
                   adlar: dict[str, str] | None = None, yok_notu: str = "") -> tuple[str, str]:
    """Önceden sabit kural (``KURAL_METNI``) → (seviye, kısa gerekçe)."""
    adlar = adlar or {}
    ad = lambda k: adlar.get(k, k)  # noqa: E731
    if not anlamli:
        return YOK, "anlamlı değil" + (f"; {yok_notu}" if yok_notu else "")
    eksik = [k for k in dusuk_icin if kontrol.get(k) != GECTI]
    if eksik:
        return DUSUK, "anlamlı ama " + ", ".join(f"{ad(k)} {kontrol.get(k, UYG)}" for k in eksik)
    sorun = [f"{ad(k)} {kontrol.get(k, UYG)}" for k in yuksek_icin if kontrol.get(k) != GECTI]
    if kritik:
        sorun.append("uyarı: " + "; ".join(kritik))
    if not sorun:
        return YUKSEK, "anlamlı; bütün kontroller geçti"
    return ORTA, "anlamlı; " + ", ".join(sorun)


# ---------------------------------------------------------------- trend kontrolleri
TREND_ADLARI = {"a": "kaynak uyumu", "b": "karıştırma testi", "c": "dönem duyarlılığı",
                "d": "α = 0,05", "e": "veri yeterliliği"}


def karistirma_trend(s: xr.DataArray, n_etkin: float, anahtar: str, tekrar: int = TEKRAR,
                     temel: int = TOHUM) -> dict:
    """b) Yıl serisinin dairesel blok permütasyonu; Sen eğimi dağılımına göre p_perm."""
    y = np.asarray(s.values, float)
    ok = np.where(np.isfinite(y))[0]
    if ok.size < 8:
        return {"durum": UYG, "p_perm": np.nan, "blok": np.nan}
    y = y[ok[0]:ok[-1] + 1]
    t = np.arange(y.size, dtype=float)
    blok = blok_uzunlugu(int(np.isfinite(y).sum()), n_etkin)
    idx = dairesel_blok_indeksleri(y.size, blok, tekrar, np.random.default_rng(tohum(anahtar, temel)))
    g = sen_egimleri(y, t)[0]
    p = perm_p(g, sen_egimleri(y[idx], t))
    return {"durum": GECTI if p < ESIK_PERM else KALDI, "p_perm": p, "blok": blok}


def donem_duyarliligi(s: xr.DataArray, egim: float, min_yil: int, alfa: float = 0.10) -> dict:
    """c) İlk ve son ``KIRPMA_YIL`` geçerli yıl ayrı ayrı çıkarılınca işaret ve anlamlılık."""
    from stats.trend_tests import anlamli_kural, trend_analizi
    gec = s["yil"].values[np.isfinite(s.values)]
    if gec.size < min_yil + KIRPMA_YIL or not np.isfinite(egim) or egim == 0:
        return {"durum": UYG, "sayi": ""}
    parca, ok = [], True
    for ad, yillar in (("ilk", gec[KIRPMA_YIL:]), ("son", gec[:-KIRPMA_YIL])):
        r = trend_analizi(s.sel(yil=yillar), min_yil=min_yil, kontrol=False)
        if r["durum"] != "ok":
            return {"durum": UYG, "sayi": f"{ad}{KIRPMA_YIL} yetersiz"}
        an = int(anlamli_kural(r["p_mk"], r["ci_alt"], r["ci_ust"], alfa))
        ok &= bool(np.sign(r["egim_10yil"]) == np.sign(egim) and an == 1)
        parca.append(f"{ad}{KIRPMA_YIL} çıkınca {r['egim_10yil']:+.3g} ({'anlamlı' if an == 1 else 'anlamsız'})")
    return {"durum": GECTI if ok else KALDI, "sayi": "; ".join(parca)}


def trend_satiri_karnesi(satir: dict, s: xr.DataArray | None, kaynak: tuple[str, str], uyarilar: list[str],
                         kritik: list[str], anahtar: str, min_yil: int = 12, tekrar: int = TEKRAR,
                         temel: int = TOHUM) -> dict:
    """Bir L3 satırının karnesi. ``satir``: L3 sütunları; ``s``: aynı satırın yıl serisi."""
    from stats.trend_tests import anlamli_kural
    egim = float(satir.get("sen_egimi", np.nan))
    anl = int(satir.get("anlamli", -1)) == 1
    out = {"a_kaynak_uyumu": kaynak[0], "a_sayi": kaynak[1]}
    if s is None or not np.isfinite(egim):
        b = {"durum": UYG, "p_perm": np.nan, "blok": np.nan}
        c = {"durum": UYG, "sayi": ""}
        n_yil = 0
    else:
        b = karistirma_trend(s, float(satir.get("etkin_n", np.nan)), anahtar, tekrar, temel)
        c = donem_duyarliligi(s, egim, min_yil)
        n_yil = int(np.isfinite(s.values).sum())
    out.update(b_karistirma=b["durum"], b_p_perm=b["p_perm"], b_blok=b["blok"], c_donem=c["durum"], c_sayi=c["sayi"])
    p_fdr, ga = float(satir.get("p_fdr", np.nan)), (float(satir.get("ga_alt", np.nan)), float(satir.get("ga_ust", np.nan)))
    if np.isfinite(p_fdr):
        d = GECTI if int(anlamli_kural(p_fdr, *ga, alfa=ALFA_SIKI)) == 1 else KALDI
    else:
        d = UYG
    out.update(d_esik=d, d_sayi=f"p_fdr {p_fdr:.3g}" if np.isfinite(p_fdr) else "")
    gy = float(satir.get("gereken_yil", np.nan))
    if np.isfinite(gy) and n_yil:
        e = GECTI if gy <= n_yil else KALDI
        out.update(e_yeterlilik=e, e_sayi=f"gereken {gy:.0f} yıl, mevcut {n_yil}")
    else:
        e = UYG
        out.update(e_yeterlilik=e, e_sayi="")
    out.update(f_uyarilar="; ".join(uyarilar), f_kritik="evet" if kritik else "hayır")
    kontrol = {"a": kaynak[0], "b": b["durum"], "c": c["durum"], "d": d, "e": e}
    yok_notu = f"veri henüz yetmiyor ({out['e_sayi']})" if e == KALDI else ""
    out["guven"], out["gerekce"] = guven_seviyesi(anl, kontrol, kritik, adlar=TREND_ADLARI, yok_notu=yok_notu)
    return out


def kaynak_durumu(ku: pd.DataFrame | None, anahtar: str, mevsim: str, urun: str, egim: float,
                  anlamli: bool) -> tuple[str, str]:
    """a) L3 kaynak uyumu tablosundan: bu ürün dahil anlamlı ve aynı yönlü ürün sayısı / ürün sayısı."""
    if ku is None:
        return UYG, "tek kaynak"
    try:
        r = ku.loc[(anahtar, mevsim)]
    except KeyError:
        return UYG, "tek kaynak"
    urunler = [c[len("anlamli_"):] for c in ku.columns if c.startswith("anlamli_")]
    m = int(r["m"])
    if urun not in urunler or m < 2:
        return UYG, "tek kaynak"
    ayni = sum(1 for u in urunler if int(r[f"anlamli_{u}"]) == 1 and np.sign(r[f"egim_{u}"]) == np.sign(egim))
    sayi = f"{ayni}/{m} ürün anlamlı ve aynı yönde; işaret uyumu {float(r['isaret_uyumu']):.2f}"
    if not anlamli:                                   # anlamsız sonucun uyumu sınanmaz (güven zaten YOK)
        return UYG, f"sonuç anlamlı değil; {sayi}"
    return (GECTI if ayni >= 2 else KALDI), sayi


TREND_SUTUNLARI = ["degisken", "urun", "bolge_kodu", "bolge_adi", "duzey", "mevsim", "sen_egimi", "egim_birimi",
                   "ga_alt", "ga_ust", "p_fdr", "anlamli", "a_kaynak_uyumu", "a_sayi", "b_karistirma", "b_p_perm",
                   "b_blok", "c_donem", "c_sayi", "d_esik", "d_sayi", "e_yeterlilik", "e_sayi", "f_uyarilar",
                   "f_kritik", "guven", "gerekce", "kural_surumu"]


def trend_karnesi(paket: Path, tekrar: int = TEKRAR, temel: int = TOHUM, dosyalar: list[str] | None = None,
                  ilerleme: bool = True) -> tuple[pd.DataFrame, dict]:
    """Bütün L3 trend dosyaları için karne. Seriler L3 ile aynı fonksiyonlarla yeniden kurulur.

    Döndürür: (karne tablosu, {"l3_en_buyuk_fark": …}) — ikinci değer, yeniden kurulan serinin Sen
    eğiminin L3 dosyasındakiyle uyumunu gösterir (tekrar üretilebilirlik denetimi).
    """
    from stats.l2 import MIN_YIL
    from stats.l3 import bolge_listesi, bolge_maskeleri, bolge_serileri
    from stats.preprocessing import MEVSIMLER, TOPLANANLAR, donem_serisi, eksik_esigi
    from stats.trend_tests import trend_analizi
    paket = Path(paket)
    l3 = paket / "L3_ozet"
    ic = pd.read_csv(l3 / "ICINDEKILER.csv", encoding="utf-8-sig")
    trend = ic[ic["tur"] == "trend"]
    ku_ic = ic[ic["tur"] == "kaynak_uyumu"]
    ku = {}
    for _, r in ku_ic.iterrows():
        d = pd.read_csv(l3 / r["dosya"], encoding="utf-8-sig", dtype={"bolge_kodu": str})
        ku.setdefault(r["degisken"], []).append(d)
    ku = {k: pd.concat(v).set_index(["bolge_anahtari", "mevsim"]) for k, v in ku.items()}
    bolgeler = bolge_listesi()
    maskeler, parcalar, fark = None, [], 0.0
    for (degisken, urun), grup in trend.groupby(["degisken", "urun"], sort=False):
        if dosyalar and f"{degisken}__{urun}" not in dosyalar:
            continue
        t1 = time.time()
        with xr.open_dataset(paket / "L1_kup" / f"{degisken}__{urun}.nc") as ds:
            ds = ds.load()
        da = ds[degisken]
        bilinen = str(ds.attrs.get("bilinen_sorunlar", "") or "")
        if maskeler is None:
            maskeler = bolge_maskeleri(da["lat"].values, da["lon"].values, bolgeler)
        tum = bolge_serileri(da, maskeler)
        df = pd.concat([pd.read_csv(l3 / f, encoding="utf-8-sig", dtype={"bolge_kodu": str})
                        for f in grup["dosya"]], ignore_index=True)
        seriler = {}
        for mevsim, aylar in MEVSIMLER.items():
            seriler[mevsim] = donem_serisi(tum, aylar, toplama=degisken in TOPLANANLAR, kis=(mevsim == "kis"),
                                           eksik_esik=eksik_esigi(urun, mevsim))
        satirlar = []
        for _, r in df.iterrows():
            s = seriler[r["mevsim"]].sel(bolge=r["bolge_anahtari"])
            if np.isfinite(r["sen_egimi"]):
                yeni = trend_analizi(s, min_yil=MIN_YIL, kontrol=False)
                if yeni["durum"] == "ok":
                    fark = max(fark, abs(yeni["egim_10yil"] - r["sen_egimi"]) / max(1.0, abs(r["sen_egimi"])))
            uy, kr = [], []
            if isinstance(r.get("trend_uyarisi"), str) and r["trend_uyarisi"]:
                uy.append(r["trend_uyarisi"])
                kr.append("trend uyarısı")
            if bilinen:
                uy.append(f"bilinen sorun: {bilinen}")
                kr.append("bilinen sorun")
            if str(r.get("dogrulanmadi", "")).lower() == "evet":
                uy.append("Kademe 2: bağımsız doğrulaması yapılmadı")
                kr.append("Kademe 2")
            if r.get("mk_yedek") == 1:
                uy.append("mk_yedek: Hamed-Rao tanımsız, düzeltmesiz MK kullanıldı")
            kaynak = kaynak_durumu(ku.get(degisken), r["bolge_anahtari"], r["mevsim"], urun, r["sen_egimi"],
                                   int(r["anlamli"]) == 1)
            k = trend_satiri_karnesi(r.to_dict(), s, kaynak, uy, kr,
                                     f"{degisken}|{urun}|{r['bolge_anahtari']}|{r['mevsim']}", MIN_YIL, tekrar, temel)
            satirlar.append({"degisken": degisken, "urun": urun, "bolge_kodu": r["bolge_kodu"],
                             "bolge_adi": r["bolge_adi"], "duzey": r["duzey"], "mevsim": r["mevsim"],
                             "sen_egimi": r["sen_egimi"], "egim_birimi": r.get("egim_birimi", ""),
                             "ga_alt": r["ga_alt"], "ga_ust": r["ga_ust"], "p_fdr": r["p_fdr"],
                             "anlamli": int(r["anlamli"]), **k, "kural_surumu": KURAL_SURUMU})
        parcalar.append(pd.DataFrame(satirlar))
        if ilerleme:
            print(f"  trend karnesi {degisken}__{urun}: {len(satirlar)} satır ({time.time() - t1:.0f} sn)")
    return pd.concat(parcalar, ignore_index=True)[TREND_SUTUNLARI], {"l3_en_buyuk_fark": fark}


# ---------------------------------------------------------------- yazma ve komut
def csv_yaz(df: pd.DataFrame, yol: Path) -> Path:
    """UTF-8 BOM'lu, ondalık nokta, boş değer boş hücre."""
    yol.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(yol, index=False, encoding="utf-8-sig", na_rep="", float_format="%.4g")
    return yol


def ozet(df: pd.DataFrame, baslik: str) -> str:
    say = df["guven"].value_counts().reindex([YUKSEK, ORTA, DUSUK, YOK], fill_value=0)
    return f"  {baslik}: {len(df)} satır · " + " · ".join(f"{k} {v}" for k, v in say.items())


def uret(paket: Path, yalniz: str | None = None, tekrar: int = TEKRAR, temel: int = TOHUM) -> dict:
    """Karneleri ``<paket>/karne/`` altına yazar; özet döndürür."""
    hedef = Path(paket) / "karne"
    hedef.mkdir(parents=True, exist_ok=True)
    sonuc = {"dosyalar": [], "sure": {}}
    if yalniz in (None, "trend"):
        t0 = time.time()
        df, denet = trend_karnesi(paket, tekrar, temel)
        il = df[df["duzey"] == "il"]
        bolge = df[df["duzey"] != "il"]
        sonuc["dosyalar"] += [csv_yaz(il, hedef / "trend_karne_il.csv"),
                              csv_yaz(bolge, hedef / "trend_karne_bolge.csv")]
        sonuc.update(trend=df, denetim=denet)
        sonuc["sure"]["trend"] = time.time() - t0
    if yalniz in (None, "iliski"):
        from physics.karne import l4_karnesi
        t0 = time.time()
        df = l4_karnesi(paket, tekrar, temel)
        sonuc["dosyalar"].append(csv_yaz(df, hedef / "iliski_karne.csv"))
        sonuc["iliski"] = df
        sonuc["sure"]["iliski"] = time.time() - t0
    kural = hedef / "KURALLAR.txt"
    kural.write_text(KURAL_METNI + f"\nÜretim: python -m stats.karne · {date.today().isoformat()} · "
                     f"tekrar {tekrar} · tohum {temel}\n", encoding="utf-8")
    sonuc["dosyalar"].append(kural)
    return sonuc


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m stats.karne", description=__doc__.splitlines()[0])
    ap.add_argument("--surum", default="v0.1")
    ap.add_argument("--kok", type=Path, default=None, help="paket kökü (varsayılan outputs/…-<surum>)")
    ap.add_argument("--yalniz", choices=("trend", "iliski"), default=None)
    ap.add_argument("--tekrar", type=int, default=TEKRAR)
    ap.add_argument("--tohum", type=int, default=TOHUM)
    a = ap.parse_args(argv)
    from stats.preprocessing import paket_koku
    paket = paket_koku(a.surum, a.kok)
    t0 = time.time()
    s = uret(paket, a.yalniz, a.tekrar, a.tohum)
    print("BULGU KARNESİ (sağlamlık ve tutarlılık özeti; doğruluk ya da nedensellik göstermez)")
    if "trend" in s:
        print(ozet(s["trend"][s["trend"]["duzey"] == "il"], "trend · il"))
        print(ozet(s["trend"][s["trend"]["duzey"] != "il"], "trend · bölge + Türkiye"))
        print(f"  L3 ile tekrar üretim: Sen eğimlerinde en büyük göreli fark {s['denetim']['l3_en_buyuk_fark']:.2g}")
    if "iliski" in s:
        print(ozet(s["iliski"], "ilişki (L4)"))
    for k, v in s["sure"].items():
        print(f"  süre {k}: {v / 60:.1f} dk")
    for p in s["dosyalar"]:
        print(" ", p)
    print(f"  toplam: {(time.time() - t0) / 60:.1f} dk")


if __name__ == "__main__":
    main()
