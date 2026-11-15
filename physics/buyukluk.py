"""Büyüklük testleri: fizik "ne kadar" olması gerektiğini söylediğinde gözlenen büyüklüğü beklenen bantla karşılaştırır.

    python -m physics.buyukluk --surum v0.1                 # üç test
    python -m physics.buyukluk --surum v0.1 --test cc       # yalnız Clausius-Clapeyron
    python -m physics.buyukluk --surum v0.1 --test butce    # yalnız su bütçesi kapanışı
    python -m physics.buyukluk --surum v0.1 --test kar_cizgisi

Çıktı (yalnız yeni dosyalar; L1–L4 ve karne dosyalarına dokunulmaz):
    <paket>/L4_iliski/buyukluk/<test>__il.csv      (su bütçesinde il yok: GRACE il ölçeğine uygun değil)
    <paket>/L4_iliski/buyukluk/<test>__bolge.csv   (7 bölge + Türkiye satırı)
    <paket>/L4_iliski/buyukluk/ozet.csv            (bölge ve Türkiye satırları, üç test)
    <paket>/L4_iliski/buyukluk/KURAL.txt           (etiket ve güven kuralı, kaynaklar)

Eski yol haritası kodu yeni yapıya bağlandı:
- ``physics.shift.snowline_series`` → kar çizgisi rakımı (her yıl, rakım dilimlerinde medyan kar örtüsünün
  %50'yi aşağıdan yukarı kestiği yükselti),
- ``physics.tests_physical`` içindeki Clausius-Clapeyron ve su bütçesi fikirleri burada yeniden yazıldı
  (blok bootstrap güven aralığı, sabit literatür bandı, yeni etiket kuralı). Eski modüller değişmedi.

Bütün eşikler sonuçlar görülmeden sabitlendi (``KURAL_SURUMU``). Etiketler bir büyüklük tutarlılığı
özetidir; nedensellik göstermez ve hiçbir şeyi kanıtlamaz.
"""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from physics import seriler as S
from physics.iliski import etkin_n, gecikme1, trend_cikar
from stats.karne import GECTI, KALDI, UYG, blok_uzunlugu, tohum

KURAL_SURUMU = "buyukluk-v1 (2026-11-15)"
TEKRAR = 999
TOHUM = 2026
GENIS_KAT = 3.0          # GA genişliği > GENIS_KAT × bant genişliği → "belirsiz"
KIRPMA_YIL = 3           # dönem duyarlılığı: ilk / son 3 yıl çıkarılır
GA_MIN_GECERLI = 0.9     # bootstrap tekrarlarının en az %90'ı sonlu değilse GA hesaplanamadı

TUTARLI = "beklenen büyüklükle tutarlı"
KUCUK = "beklenenden küçük"
BUYUK = "beklenenden büyük"
BELIRSIZ = "belirsiz"
HESAPLANAMADI = "hesaplanamadı"
ETIKETLER = (TUTARLI, KUCUK, BUYUK, BELIRSIZ, HESAPLANAMADI)
YUKSEK, ORTA, DUSUK, YOK = "YÜKSEK", "ORTA", "DÜŞÜK", "YOK"

TESTLER = ("cc", "butce", "kar_cizgisi")

# ---------------------------------------------------------------- fiziksel beklentiler (literatür)
L_V = 2.5e6       # J/kg, buharlaşma gizli ısısı
R_V = 461.5       # J/(kg K), su buharı gaz sabiti


def cc_orani(t_c: float) -> float:
    """Clausius-Clapeyron: doymuş buhar basıncının sıcaklıkla göreli artışı, %/K = 100 · L / (R_v T²)."""
    return 100.0 * L_V / (R_V * (t_c + 273.15) ** 2)


# Bant: denklemin 30 °C ve 0 °C'deki değeri (Türkiye'de yakın yüzey aylık sıcaklıklarının çoğu bu aralıkta).
CC_BANT = (round(cc_orani(30.0), 1), round(cc_orani(0.0), 1))          # (5,9, 7,3) %/K
CC_BEKLENEN = round(cc_orani(15.0), 1)                                  # 6,6 %/K (Türkiye yıllık ortalamasına yakın)
CC_KAYNAK = ("Clausius-Clapeyron, L/(R_v T²), L = 2,5e6 J/kg, R_v = 461,5 J/(kg K); bağıl nem sabitse özgül nem ve "
             "su buharı kolonu ~%7/K artar (Held ve Soden 2006, J. Climate 19:5686). Bant: denklemin 30 °C ve 0 °C "
             "değerleri.")
CC_KARA_YORUMU = ("Karada nem kısıtlı: bağıl nemin azaldığı dönemlerde artış %7/K'nin altında kalabilir (Simmons vd. "
                  "2010, JGR 115:D01110; Byrne ve O'Gorman 2018, PNAS 115:4863). Etiket değiştirilmedi.")

LAPSE = 6.5                 # °C/km, ICAO standart atmosfer
LAPSE_BANT = (5.5, 7.5)     # °C/km
LAPSE_KAYNAK = ("Beklenen kayma = ısınma hızı / dikey sıcaklık azalma oranı. 6,5 °C/km ICAO standart atmosferi "
                "(Doc 7488); bant ±1 °C/km: dağlarda yüzey azalma oranı mevsime ve yere göre değişir, kışın daha "
                "düşük olabilir (Rolland 2003, J. Climate 16:1032).")
KAR_YORUMU = ("Olası açıklamalar (hangisinin geçerli olduğu belirlenmedi): kar örtüsü yalnız sıcaklığa değil yağışa da "
              "bağlıdır; yüzey azalma oranı kışın 6,5 °C/km'den düşük olabilir; 0,25° hücre rakımı yamaçları yumuşatır.")
KAR_DILIM = 200.0          # m, rakım dilimi (0,25° hücrelerde 100 m dilim çok seyrek kalır)
KAR_ESIK = 50.0            # %, kar çizgisi eşiği
KAR_MIN_HUCRE = 3          # dilim başına en az hücre
KAR_MIN_DILIM = 4          # yeterli yükselti aralığı: en az 4 dolu dilim (≥ 800 m)
KAR_MIN_YIL = 10           # kar çizgisi en az 10 yılda (ve yılların en az yarısında) tanımlı olmalı
KAR_MEVSIMLERI = ("kis", "ilkbahar")

BUTCE_ORAN = 0.10           # bant yarı genişliği = ortalama yıllık yağışın %10'u
BUTCE_KAYNAK = ("Kütle korunumu: dS/dt = P − ET − R, fark ≈ 0. Bant 0 ± ortalama yıllık P'nin %10'u (trendde: "
                "%10'u / 10 yıl). Proje seçimidir; büyüklük mertebesi, yağış ve buharlaşma ürünlerinin bölgesel "
                "belirsizliğinin yaklaşık %10 mertebesinde verildiği çalışmalara dayanır (Sheffield vd. 2009, GRL "
                "36:L07403; Rodell vd. 2015, J. Climate 28:8289); kesin değer bu çalışmalardan alınmadı.")
BUTCE_YORUMU = ("Olası açıklamalar (hangisinin geçerli olduğu belirlenmedi): ölçülmeyen yeraltı suyu çekimi ya da "
                "sulama (GLDAS-2.1 Noah bunları modellemez), ürün yanlılığı (yağış, buharlaşma, akış), GRACE "
                "çözünürlüğü (JPL mascon ~3°, ~300 km; Watkins vd. 2015, JGR 120:2648) ve sızıntı.")
BUTCE_IL_NOTU = "Su bütçesi il düzeyinde hesaplanmadı: GRACE'in etkin çözünürlüğü (~300 km) il ölçeğine uygun değil."
BOOTSTRAP_KAYNAK = ("Dairesel blok bootstrap (Politis ve Romano 1992); blok = ceil(n / etkin n), etkin n Bretherton vd. "
                    "(1999) gecikme-1 otokorelasyonundan.")

KURAL_METNI = f"""BÜYÜKLÜK TESTİ KURALI ({KURAL_SURUMU}; sonuçlar görülmeden sabitlendi)

Gözlenen büyüklük: nokta tahmini + %95 güven aralığı (GA). GA: {BOOTSTRAP_KAYNAK}
  {TEKRAR} tekrar, satıra özgü sabit tohum (crc32(anahtar) ^ {TOHUM}); GA = 2,5 ve 97,5 yüzdelikleri.
  Tekrarların %{GA_MIN_GECERLI * 100:.0f}'ından azı sonluysa GA hesaplanamadı.
Beklenen: fiziksel nokta değer + belirsizlik bandı [alt, üst] (kaynak her satırda).
Etiket (öncelik sırasıyla):
  {HESAPLANAMADI}: GA ya da bant hesaplanamadı (veri yetersiz).
  {BELIRSIZ}: GA genişliği > {GENIS_KAT:g} × bant genişliği.
  {TUTARLI}: GA bantla kesişiyor.
  {KUCUK}: GA tamamen bandın altında.   {BUYUK}: GA tamamen bandın üstünde.
Karne kontrolleri (geçti / kaldı / uygulanamaz; "uygulanamaz" geçti sayılmaz):
  a kaynak uyumu: alternatif ürünle (yağış GPM/MERRA2, sıcaklık MERRA2/GLDAS) aynı etiket
  b dönem duyarlılığı: ilk {KIRPMA_YIL} ve son {KIRPMA_YIL} yıl ayrı ayrı çıkarılınca aynı etiket
  c GA genişliği: GA genişliği ≤ bant genişliği (GA en az bant kadar dar)
  f uyarılar: Kademe 2 (doğrulanmadı), trend_uyarisi, bilinen_sorunlar KRİTİK
Güven:
  YOK    : etiket "{BELIRSIZ}" ya da "{HESAPLANAMADI}" (büyüklük iddiası yok).
  DÜŞÜK  : b geçmedi (etiket döneme duyarlı).
  YÜKSEK : a, b, c geçti; kritik uyarı yok.
  ORTA   : b geçti ama YÜKSEK'in başka bir şartı sağlanmadı (tek kaynak, a ya da c kaldı, kritik uyarı).
Bu bir büyüklük tutarlılığı özetidir; doğruluk ya da nedensellik göstermez.
"""

SUTUNLAR = [
    "test", "yol", "degisken", "urun", "bolge_turu", "bolge_kodu", "bolge_adi", "hucre_sayisi", "donem", "n",
    "gozlenen", "ga_alt", "ga_ust", "birim", "beklenen", "beklenen_alt", "beklenen_ust", "beklenen_kaynak",
    "etiket", "etiket_gerekce", "yorum", "blok", "tekrar",
    "a_kaynak_uyumu", "a_sayi", "b_donem", "b_sayi", "c_ga_genisligi", "c_sayi", "uyarilar", "kritik",
    "guven", "gerekce", "ek", "kural_surumu", "urun_surumu", "veri_seti_doi", "lisans",
]


# ---------------------------------------------------------------- bootstrap ve kestiriciler
def blok_bootstrap_indeksleri(n: int, blok: int, tekrar: int, rng: np.random.Generator) -> np.ndarray:
    """(tekrar, n) indeks: seri halka sayılır, rastgele başlangıçlı ``blok`` uzunluğunda parçalar YERİNE KOYARAK
    seçilip art arda eklenir ve n'de kesilir (dairesel blok bootstrap). Blok içi ardışıklık korunur."""
    blok = int(max(1, min(blok, n)))
    nb = math.ceil(n / blok)
    bas = rng.integers(0, n, size=(tekrar, nb))
    idx = (bas[:, :, None] + np.arange(blok)[None, None, :]) % n
    return idx.reshape(tekrar, nb * blok)[:, :n]


def etkin_n_tek(z) -> float:
    """Tek seri için etkin n = n (1 − r₁) / (1 + r₁) (r₁ ≤ 0 ise n)."""
    z = np.asarray(z, float)
    n = int(np.isfinite(z).sum())
    r1 = gecikme1(z)
    if not np.isfinite(r1) or r1 <= 0:
        return float(n)
    return float(max(3.0, n * (1 - r1) / (1 + r1)))


def ekk_satir(X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """Satır başına EKK eğimi (NaN çiftler atlanır). X, Y: (k, n)."""
    X, Y = np.atleast_2d(np.asarray(X, float)), np.atleast_2d(np.asarray(Y, float))
    ok = np.isfinite(X) & np.isfinite(Y)
    n = ok.sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mx = np.where(ok, X, 0).sum(1) / n
        my = np.where(ok, Y, 0).sum(1) / n
        dx = np.where(ok, X - mx[:, None], 0)
        dy = np.where(ok, Y - my[:, None], 0)
        sxx = (dx * dx).sum(1)
        out = (dx * dy).sum(1) / sxx
    out[(n < 3) | ~(sxx > 0)] = np.nan
    return out


def sen_satir(T: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """Satır başına Sen eğimi; her satırın kendi zaman ekseni var (bootstrap'te tekrarlanan zamanlar atlanır)."""
    T, Y = np.atleast_2d(np.asarray(T, float)), np.atleast_2d(np.asarray(Y, float))
    i, j = np.triu_indices(T.shape[1], 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        e = (Y[:, j] - Y[:, i]) / (T[:, j] - T[:, i])
    e[~np.isfinite(e)] = np.nan
    out = np.full(T.shape[0], np.nan)
    ok = np.isfinite(e).sum(1) >= 3
    out[ok] = np.nanmedian(e[ok], axis=1)
    return out


def guven_araligi(dagilim: np.ndarray, tekrar: int) -> tuple[float, float]:
    """Yüzdelik %95 GA; sonlu tekrar oranı ``GA_MIN_GECERLI``'den azsa (nan, nan)."""
    d = np.asarray(dagilim, float)
    d = d[np.isfinite(d)]
    if d.size < GA_MIN_GECERLI * tekrar:
        return float("nan"), float("nan")
    lo, hi = np.percentile(d, [2.5, 97.5])
    return float(lo), float(hi)


def bootstrap(fonk, diziler: list[np.ndarray], blok: int, anahtar: str, tekrar: int = TEKRAR,
              temel: int = TOHUM) -> dict:
    """``fonk`` satır başına (k, n) dizilerle çalışan kestirici. Nokta tahmini + blok bootstrap GA."""
    diziler = [np.asarray(d, float) for d in diziler]
    n = diziler[0].size
    nokta = float(fonk(*[d[None, :] for d in diziler])[0])
    idx = blok_bootstrap_indeksleri(n, blok, tekrar, np.random.default_rng(tohum(anahtar, temel)))
    lo, hi = guven_araligi(fonk(*[d[idx] for d in diziler]), tekrar)
    return {"gozlenen": nokta, "ga_alt": lo, "ga_ust": hi, "blok": int(blok), "tekrar": int(tekrar)}


def _bos(neden: str) -> dict:
    nan = float("nan")
    return {"gozlenen": nan, "ga_alt": nan, "ga_ust": nan, "blok": np.nan, "tekrar": 0, "neden": neden}


# ---------------------------------------------------------------- etiket ve güven
def etiketle(ga_alt: float, ga_ust: float, b_alt: float, b_ust: float) -> tuple[str, str]:
    """Önceden sabit etiket kuralı (``KURAL_METNI``) → (etiket, kısa gerekçe)."""
    if not all(np.isfinite(v) for v in (ga_alt, ga_ust, b_alt, b_ust)):
        return HESAPLANAMADI, "GA ya da beklenen bant hesaplanamadı"
    g_lo, g_hi = sorted((ga_alt, ga_ust))
    b_lo, b_hi = sorted((b_alt, b_ust))
    gw, bw = g_hi - g_lo, b_hi - b_lo
    if gw > GENIS_KAT * bw:
        return BELIRSIZ, f"GA genişliği {gw:.3g}, bant genişliğinin {gw / bw:.1f} katı (> {GENIS_KAT:g})"
    if g_hi < b_lo:
        return KUCUK, "GA tamamen bandın altında"
    if g_lo > b_hi:
        return BUYUK, "GA tamamen bandın üstünde"
    return TUTARLI, "GA bantla kesişiyor"


def ga_kontrolu(r: dict) -> dict:
    """c) GA genişliği ≤ bant genişliği mi."""
    vals = (r.get("ga_alt"), r.get("ga_ust"), r.get("beklenen_alt"), r.get("beklenen_ust"))
    if not all(v is not None and np.isfinite(v) for v in vals):
        return {"durum": UYG, "sayi": ""}
    gw, bw = abs(vals[1] - vals[0]), abs(vals[3] - vals[2])
    return {"durum": GECTI if gw <= bw else KALDI, "sayi": f"GA {gw:.3g} / bant {bw:.3g} = {gw / bw:.2f}"}


def etiket_uyumu(ana: str, digerleri: list[tuple[str, str]], bos_metin: str) -> dict:
    """Ana etiket diğer varyantların hepsinde aynı mı; ``hesaplanamadı`` varyant uygulanamaz sayılır."""
    if not digerleri:
        return {"durum": UYG, "sayi": bos_metin}
    sayi = "; ".join(f"{ad}: {et}" for ad, et in digerleri)
    if any(et == HESAPLANAMADI for _, et in digerleri):
        return {"durum": UYG, "sayi": sayi}
    return {"durum": GECTI if all(et == ana for _, et in digerleri) else KALDI, "sayi": sayi}


def guven_seviyesi(etiket: str, kontrol: dict[str, str], kritik: list[str]) -> tuple[str, str]:
    """Önceden sabit güven kuralı (``KURAL_METNI``) → (seviye, gerekçe)."""
    adlar = {"a": "kaynak uyumu", "b": "dönem duyarlılığı", "c": "GA genişliği"}
    if etiket in (BELIRSIZ, HESAPLANAMADI):
        return YOK, f"etiket {etiket}; büyüklük iddiası yok"
    if kontrol.get("b") != GECTI:
        return DUSUK, f"dönem duyarlılığı {kontrol.get('b', UYG)}"
    sorun = [f"{adlar[k]} {kontrol.get(k, UYG)}" for k in ("a", "c") if kontrol.get(k) != GECTI]
    if kritik:
        sorun.append("uyarı: " + "; ".join(kritik))
    if not sorun:
        return YUKSEK, "bütün kontroller geçti"
    return ORTA, "; ".join(sorun)


# ---------------------------------------------------------------- test 1: Clausius-Clapeyron (1B seriler)
def _cc_a(T, Y):
    return ekk_satir(T, Y) * 100.0


def _cc_b(t, T, Y):
    return sen_satir(t, Y) * 100.0 / sen_satir(t, T)


def cc_yillar_arasi(yil, sicaklik, nem, anahtar: str, tekrar: int = TEKRAR, temel: int = TOHUM) -> dict:
    """(a) Yıllar arası: trendi giderilmiş yıllık ln(nem) anomalisinin trendi giderilmiş sıcaklığa EKK eğimi × 100
    (%/K). GA: (T, ln q) anomali çiftlerinin blok bootstrap'ı."""
    yil, T, q = (np.asarray(v, float) for v in (yil, sicaklik, nem))
    ok = np.isfinite(yil) & np.isfinite(T) & np.isfinite(q) & (q > 0)
    if ok.sum() < 10:
        return _bos(f"geçerli yıl {int(ok.sum())} < 10")
    x = trend_cikar(np.where(ok, T, np.nan), yil)[ok]
    y = trend_cikar(np.where(ok, np.log(np.where(q > 0, q, np.nan)), np.nan), yil)[ok]
    blok = blok_uzunlugu(x.size, etkin_n(x.size, gecikme1(x), gecikme1(y)))
    return bootstrap(_cc_a, [x, y], blok, anahtar, tekrar, temel) | {"n": int(x.size)}


def cc_trend_orani(yil, sicaklik, nem, anahtar: str, tekrar: int = TEKRAR, temel: int = TOHUM) -> dict:
    """(b) Uzun dönem: Sen eğimi(ln q) × 100 / Sen eğimi(T) (%/K). GA: (yıl, T, ln q) üçlülerinin blok bootstrap'ı."""
    yil, T, q = (np.asarray(v, float) for v in (yil, sicaklik, nem))
    ok = np.isfinite(yil) & np.isfinite(T) & np.isfinite(q) & (q > 0)
    if ok.sum() < 10:
        return _bos(f"geçerli yıl {int(ok.sum())} < 10")
    t, x, y = yil[ok], T[ok], np.log(q[ok])
    blok = blok_uzunlugu(t.size, etkin_n(t.size, gecikme1(trend_cikar(x, t)), gecikme1(trend_cikar(y, t))))
    return bootstrap(_cc_b, [t, x, y], blok, anahtar, tekrar, temel) | {"n": int(t.size)}


# ---------------------------------------------------------------- test 2: su bütçesi (1B seriler)
def depolama_degisimi(s_mm: np.ndarray) -> np.ndarray:
    """dS/dt (mm/ay) merkezî fark: (S[t+1] − S[t−1]) / 2; komşulardan biri yoksa NaN (GRACE boşlukları)."""
    s = np.asarray(s_mm, float)
    out = np.full_like(s, np.nan)
    out[1:-1] = (s[2:] - s[:-2]) / 2.0
    return out


def _ortalama_yillik(R):
    return np.nanmean(np.where(np.isfinite(R), R, np.nan), axis=1) * 12.0


def butce_ortalama(artik_mm_ay, anahtar: str, tekrar: int = TEKRAR, temel: int = TOHUM) -> dict:
    """İklimsel ortalama kapanış: ortalama(dS/dt − (P − ET − R)) × 12 (mm/yıl). GA: aylık artığın blok bootstrap'ı."""
    r = np.asarray(artik_mm_ay, float)
    if np.isfinite(r).sum() < 60:
        return _bos(f"geçerli ay {int(np.isfinite(r).sum())} < 60")
    blok = blok_uzunlugu(int(np.isfinite(r).sum()), etkin_n_tek(r))
    return bootstrap(_ortalama_yillik, [r], blok, anahtar, tekrar, temel) | {"n": int(np.isfinite(r).sum())}


def _trend_10yil(t, R):
    return ekk_satir(t, R) * 12.0 * 10.0


def aylik_anomali_dizi(x: np.ndarray, ay: np.ndarray) -> np.ndarray:
    """Her aydan o ayın ortalamasını çıkarır (NaN'lar NaN kalır)."""
    x = np.asarray(x, float).copy()
    for m in range(1, 13):
        s = ay == m
        if np.isfinite(x[s]).any():
            x[s] = x[s] - np.nanmean(x[s])
    return x


def butce_trend(t_yil, ay, artik_mm_ay, anahtar: str, tekrar: int = TEKRAR, temel: int = TOHUM) -> dict:
    """Trend kapanışı: aylık artık anomalisinin EKK eğimi → (mm/yıl) / 10 yıl. trend(dS/dt) − trend(P − ET − R) ile
    aynıdır. GA: (zaman, anomali) çiftlerinin blok bootstrap'ı."""
    r = aylik_anomali_dizi(artik_mm_ay, np.asarray(ay))
    if np.isfinite(r).sum() < 60:
        return _bos(f"geçerli ay {int(np.isfinite(r).sum())} < 60")
    blok = blok_uzunlugu(int(np.isfinite(r).sum()), etkin_n_tek(trend_cikar(r, t_yil)))
    return bootstrap(_trend_10yil, [np.asarray(t_yil, float), r], blok, anahtar, tekrar, temel) | \
        {"n": int(np.isfinite(r).sum())}


# ---------------------------------------------------------------- test 3: kar çizgisi (1B seriler)
def _sen_10yil(t, Y):
    return sen_satir(t, Y) * 10.0


def egim_10yil(yil, deger, anahtar: str, tekrar: int = TEKRAR, temel: int = TOHUM, min_n: int = KAR_MIN_YIL) -> dict:
    """Yıllık serinin Sen eğimi × 10 (birim / 10 yıl). GA: (yıl, değer) çiftlerinin blok bootstrap'ı."""
    yil, z = np.asarray(yil, float), np.asarray(deger, float)
    ok = np.isfinite(yil) & np.isfinite(z)
    if ok.sum() < min_n:
        return _bos(f"geçerli yıl {int(ok.sum())} < {min_n}")
    t, y = yil[ok], z[ok]
    blok = blok_uzunlugu(t.size, etkin_n_tek(trend_cikar(y, t)))
    return bootstrap(_sen_10yil, [t, y], blok, anahtar, tekrar, temel) | {"n": int(t.size)}


def beklenen_kar_kaymasi(dT_10yil: float) -> tuple[float, float, float]:
    """Isınma hızı (°C/10 yıl) → beklenen kar çizgisi kayması (m/10 yıl): nokta (6,5 °C/km) ve bant (5,5–7,5)."""
    if not np.isfinite(dT_10yil):
        return (float("nan"),) * 3
    a, b = sorted((dT_10yil * 1000.0 / LAPSE_BANT[1], dT_10yil * 1000.0 / LAPSE_BANT[0]))
    return dT_10yil * 1000.0 / LAPSE, a, b


def kar_dilim_sayisi(rakim: np.ndarray, dilim: float = KAR_DILIM, min_hucre: int = KAR_MIN_HUCRE) -> int:
    """En az ``min_hucre`` hücresi olan rakım dilimi sayısı (``shift.snowline_series`` ile aynı dilimleme)."""
    z = np.asarray(rakim, float)
    z = z[np.isfinite(z)]
    if z.size == 0:
        return 0
    b = ((z - np.floor(z.min() / dilim) * dilim) // dilim).astype(int)
    return int((np.bincount(b) >= min_hucre).sum())


# ---------------------------------------------------------------- paket ve bölge serileri
def _l1(paket: Path, degisken: str, urun: str) -> xr.DataArray | None:
    p = Path(paket) / "L1_kup" / f"{degisken}__{urun}.nc"
    if not p.exists():
        return None
    from physics.tek_cift import _l1_ac
    return _l1_ac(paket, degisken, urun)


def _l2_uyarisi(paket: Path, degisken: str, urun: str) -> str:
    """L2 dosyasının ``trend_uyarisi`` attr'ı (yalnız okunur; yoksa "")."""
    p = Path(paket) / "L2_trend" / f"{degisken}__{urun}__trend.nc"
    if not p.exists():
        return ""
    with xr.open_dataset(p) as ds:
        return str(ds.attrs.get("trend_uyarisi", "") or "")


def urun_uyarilari(paket: Path, girdiler: list[tuple[str, str, xr.DataArray]]) -> tuple[list[str], list[str]]:
    """(uyarı metinleri, kritik kısa adlar): Kademe 2, bilinen_sorunlar (L1), trend_uyarisi (L2)."""
    uy, kr = [], []
    for d, u, da in girdiler:
        if str(da.attrs.get("dogrulanmadi", "")).lower() == "evet":
            uy.append(f"{d} ({u}) Kademe 2: bağımsız doğrulaması yapılmadı")
            kr.append(f"{d} Kademe 2")
        if da.attrs.get("bilinen_sorunlar"):
            uy.append(f"{d} ({u}) bilinen_sorunlar: {da.attrs['bilinen_sorunlar']}")
            kr.append(f"{d} bilinen_sorunlar")
        tu = _l2_uyarisi(paket, d, u)
        if tu:
            uy.append(f"{d} ({u}) trend_uyarisi: {tu}")
            kr.append(f"{d} trend_uyarisi")
    return uy, kr


def bolgeler_ve_maskeler(lat, lon, iller: bool) -> tuple[list[dict], dict[str, np.ndarray]]:
    """L4 ile aynı bölge listesi ve maskeleri (``physics.tablo``)."""
    from physics.tablo import bolge_listesi, bolge_maskeleri
    return bolge_listesi(iller), bolge_maskeleri(lat, lon, iller)


def bolge_ortalamalari(da: xr.DataArray, maskeler: list[np.ndarray]) -> np.ndarray:
    """(bölge, time) cos(enlem) ağırlıklı alan ortalamaları; NaN hücre atlanır, hiç geçerli yoksa NaN.
    ``seriler.alan_ortalamasi`` ile aynı tanım, matris çarpımıyla hızlı."""
    v = da.transpose("time", "lat", "lon").values.astype(float)
    nt = v.shape[0]
    w = np.cos(np.deg2rad(da["lat"].values))[:, None] * np.ones(da.sizes["lon"])[None, :]
    W = np.stack([np.where(m, w, 0.0).ravel() for m in maskeler])          # (b, hücre)
    X = v.reshape(nt, -1)
    gec = np.isfinite(X)
    pay = W @ np.where(gec, X, 0.0).T
    payda = W @ gec.T.astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(payda > 0, pay / payda, np.nan)


def _meta(da: xr.DataArray) -> dict:
    return {k: da.attrs.get(k, "") for k in ("urun_surumu", "veri_seti_doi", "lisans")}


def _donem(yillar) -> str:
    y = np.asarray(yillar, float)
    y = y[np.isfinite(y)]
    return f"{int(y.min())}-{int(y.max())}" if y.size else ""


def _satir(test: str, yol: str, degisken: str, urun: str, bl: dict, hucre: int, sonuc: dict, birim: str,
           beklenen: tuple[float, float, float], kaynak: str) -> dict:
    """Ortak sütunlar + etiket (karne sütunları sonra eklenir)."""
    et, ger = etiketle(sonuc["ga_alt"], sonuc["ga_ust"], beklenen[1], beklenen[2])
    if et == HESAPLANAMADI and sonuc.get("neden"):
        ger = sonuc["neden"]
    return {"test": test, "yol": yol, "degisken": degisken, "urun": urun, "bolge_turu": bl["bolge_turu"],
            "bolge_kodu": bl["bolge_kodu"], "bolge_adi": bl["bolge_adi"], "hucre_sayisi": int(hucre),
            "n": sonuc.get("n", 0), "gozlenen": sonuc["gozlenen"], "ga_alt": sonuc["ga_alt"],
            "ga_ust": sonuc["ga_ust"], "birim": birim, "beklenen": beklenen[0], "beklenen_alt": beklenen[1],
            "beklenen_ust": beklenen[2], "beklenen_kaynak": kaynak, "etiket": et, "etiket_gerekce": ger,
            "blok": sonuc["blok"], "tekrar": sonuc["tekrar"], "kural_surumu": KURAL_SURUMU}


def _karne_ekle(r: dict, alt: list[tuple[str, str]], kirpma: list[tuple[str, str]], alt_bos: str,
                uyarilar: list[str], kritik: list[str]) -> dict:
    a = etiket_uyumu(r["etiket"], alt, alt_bos)
    b = etiket_uyumu(r["etiket"], kirpma, "dönem kırpılamadı")
    c = ga_kontrolu(r)
    gv, gr = guven_seviyesi(r["etiket"], {"a": a["durum"], "b": b["durum"], "c": c["durum"]}, kritik)
    r.update({"a_kaynak_uyumu": a["durum"], "a_sayi": a["sayi"], "b_donem": b["durum"], "b_sayi": b["sayi"],
              "c_ga_genisligi": c["durum"], "c_sayi": c["sayi"], "uyarilar": "; ".join(uyarilar),
              "kritik": "evet" if kritik else "hayır", "guven": gv, "gerekce": gr})
    return r


def _kirp(yillar: np.ndarray, gecerli: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """İlk / son ``KIRPMA_YIL`` geçerli yılı dışarıda bırakan iki maske (``yillar`` aylık seride ayın yılıdır)."""
    g = np.unique(np.asarray(yillar)[np.asarray(gecerli, bool)])
    if g.size < KIRPMA_YIL * 2 + 10:
        return []
    return [(f"ilk {KIRPMA_YIL} yıl çıkınca", np.asarray(yillar) >= g[KIRPMA_YIL]),
            (f"son {KIRPMA_YIL} yıl çıkınca", np.asarray(yillar) <= g[-KIRPMA_YIL - 1])]


def _yillik(seri_bt: np.ndarray, zaman: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """(bölge, time) aylık → (bölge, yıl) yıllık ortalama; 12 ayı tam olmayan yıl NaN."""
    yil = zaman.year.to_numpy()
    yillar = np.unique(yil)
    out = np.full((seri_bt.shape[0], yillar.size), np.nan)
    for k, y in enumerate(yillar):
        s = seri_bt[:, yil == y]
        tam = np.isfinite(s).sum(1) == 12
        out[tam, k] = s[tam].mean(1)
    return yillar.astype(float), out


# ---------------------------------------------------------------- test 1: paket
CC_NEM = (("ozgul_nem_2m", "MERRA2"), ("su_buhari_kolon", "MERRA2"))
SICAKLIK = ("MERRA2", "GLDAS")       # ilki ana ürün, ikincisi kaynak uyumu


def cc_testi(paket: Path, iller: bool = True, tekrar: int = TEKRAR, temel: int = TOHUM) -> pd.DataFrame:
    """Clausius-Clapeyron, iki yol × iki nem değişkeni, il / bölge / Türkiye."""
    T = {u: _l1(paket, "sicaklik_2m", u) for u in SICAKLIK}
    if T[SICAKLIK[0]] is None:
        raise FileNotFoundError("sicaklik_2m__MERRA2.nc yok")
    ref = T[SICAKLIK[0]]
    bl, mk = bolgeler_ve_maskeler(ref["lat"].values, ref["lon"].values, iller)
    zaman = pd.DatetimeIndex(ref["time"].values)
    Ty = {u: _yillik(bolge_ortalamalari(da, [mk[b["anahtar"]] for b in bl]), zaman)
          for u, da in T.items() if da is not None}
    satirlar = []
    for nd, nu in CC_NEM:
        q = _l1(paket, nd, nu)
        if q is None:
            print(f"  CC: {nd}__{nu}.nc yok, atlandı")
            continue
        q, _ = xr.align(q, ref, join="inner")
        yillar, Q = _yillik(bolge_ortalamalari(q, [mk[b["anahtar"]] for b in bl]), pd.DatetimeIndex(q["time"].values))
        gecerli_h = q.notnull().any("time").values
        uy, kr = urun_uyarilari(paket, [(nd, nu, q), ("sicaklik_2m", SICAKLIK[0], ref)])
        for yol, fonk in (("a_yillar_arasi", cc_yillar_arasi), ("b_trend_orani", cc_trend_orani)):
            for k, b in enumerate(bl):
                ty_y, ty = Ty[SICAKLIK[0]]
                tk = np.interp(yillar, ty_y, ty[k], left=np.nan, right=np.nan)
                anahtar = f"cc|{yol}|{nd}|{b['bolge_kodu']}"
                s = fonk(yillar, tk, Q[k], anahtar, tekrar, temel)
                r = _satir("cc", yol, nd, f"{nu}~sicaklik_2m:{SICAKLIK[0]}", b,
                           int((mk[b["anahtar"]] & gecerli_h).sum()), s, "%/K", (CC_BEKLENEN, *CC_BANT), CC_KAYNAK)
                ok = np.isfinite(tk) & np.isfinite(Q[k])
                r["donem"] = _donem(yillar[ok])
                r["yorum"] = CC_KARA_YORUMU if r["etiket"] == KUCUK else ""
                alt = []
                for u in SICAKLIK[1:]:
                    if u in Ty:
                        ta = np.interp(yillar, Ty[u][0], Ty[u][1][k], left=np.nan, right=np.nan)
                        sa = fonk(yillar, ta, Q[k], anahtar + f"|{u}", tekrar, temel)
                        alt.append((f"sıcaklık {u}", etiketle(sa["ga_alt"], sa["ga_ust"], *CC_BANT)[0]))
                kirpma = []
                for ad, m in _kirp(yillar, ok):
                    sk = fonk(yillar[m], tk[m], Q[k][m], anahtar + f"|{ad}", tekrar, temel)
                    kirpma.append((ad, etiketle(sk["ga_alt"], sk["ga_ust"], *CC_BANT)[0]))
                ek_uy, ek_kr = list(uy), list(kr)
                r["ek"] = ""
                satirlar.append(_karne_ekle(r, alt, kirpma, "alternatif sıcaklık ürünü yok", ek_uy, ek_kr) | _meta(q))
        print(f"  CC {nd}: {len(bl)} bölge × 2 yol")
    return pd.DataFrame(satirlar, columns=SUTUNLAR)


# ---------------------------------------------------------------- test 2: paket
BUTCE_YAGIS = ("GPM", "MERRA2")       # ilki ana ürün, ikincisi kaynak uyumu


def _butce_terimleri(paket: Path, maskeler: list[np.ndarray]) -> dict:
    """GRACE zamanına hizalı (bölge, time) seriler, mm ve mm/ay."""
    g = _l1(paket, "toplam_su_depolama", "GRACE")
    terim = {"ET": ("buharlasma", "GLDAS"), "Rs": ("yuzey_akisi", "GLDAS"), "Rb": ("taban_akisi", "GLDAS")}
    das = {k: _l1(paket, *v) for k, v in terim.items()}
    pler = {u: _l1(paket, "yagis", u) for u in BUTCE_YAGIS}
    if g is None or any(v is None for v in das.values()) or pler[BUTCE_YAGIS[0]] is None:
        raise FileNotFoundError("su bütçesi için GRACE, yagis GPM, buharlasma, yuzey_akisi, taban_akisi gerekli")
    # GRACE'in kendi aylık ekseni (boşluklar NaN) tam aylık eksene açılır; merkezî fark ardışık ay ister
    t0, t1 = pd.Timestamp(g["time"].values[0]), pd.Timestamp(g["time"].values[-1])
    eksen = pd.date_range(t0, t1, freq="MS")
    g = g.reindex(time=eksen)
    out = {"zaman": eksen, "S": bolge_ortalamalari(g, maskeler) * 10.0,
           "girdiler": [("toplam_su_depolama", "GRACE", g)] + [(*terim[k], das[k]) for k in terim]}
    for k, da in das.items():
        out[k] = bolge_ortalamalari(da.reindex(time=eksen), maskeler)
    out["P"] = {u: bolge_ortalamalari(da.reindex(time=eksen), maskeler) for u, da in pler.items() if da is not None}
    out["P_da"] = pler
    out["gecerli_hucre"] = g.notnull().any("time").values
    return out


def butce_testi(paket: Path, tekrar: int = TEKRAR, temel: int = TOHUM) -> pd.DataFrame:
    """Su bütçesi kapanışı: iklimsel ortalama ve trend, 7 bölge + Türkiye (il yok)."""
    g0 = _l1(paket, "toplam_su_depolama", "GRACE")
    if g0 is None:
        raise FileNotFoundError("toplam_su_depolama__GRACE.nc yok")
    bl, mk = bolgeler_ve_maskeler(g0["lat"].values, g0["lon"].values, iller=False)
    B = _butce_terimleri(paket, [mk[b["anahtar"]] for b in bl])
    z = B["zaman"]
    t_yil = (z.year + (z.month - 1) / 12.0).to_numpy(float)
    ay = z.month.to_numpy()
    yil = z.year.to_numpy()
    satirlar = []
    for k, b in enumerate(bl):
        dS = depolama_degisimi(B["S"][k])
        R = B["Rs"][k] + B["Rb"][k]

        def artik(u):
            return dS - (B["P"][u][k] - B["ET"][k] - R)
        ana = BUTCE_YAGIS[0]
        r0 = artik(ana)
        ok = np.isfinite(r0)
        p_yillik = float(np.nanmean(np.where(ok, B["P"][ana][k], np.nan)) * 12.0) if ok.any() else np.nan
        yari = BUTCE_ORAN * p_yillik
        bant = (0.0, -yari, yari)
        uy, kr = urun_uyarilari(paket, B["girdiler"] + [("yagis", ana, B["P_da"][ana])])
        hucre = int((mk[b["anahtar"]] & B["gecerli_hucre"]).sum())
        ek_terim = {"dS_dt_mm_yil": np.nanmean(np.where(ok, dS, np.nan)) * 12,
                    "P_mm_yil": p_yillik, "ET_mm_yil": np.nanmean(np.where(ok, B["ET"][k], np.nan)) * 12,
                    "R_mm_yil": np.nanmean(np.where(ok, R, np.nan)) * 12}
        for yol in ("ortalama", "trend"):
            anahtar = f"butce|{yol}|{b['bolge_kodu']}"

            def hesap(rr, m=None, ek=""):
                m = np.ones_like(rr, bool) if m is None else m
                rr = np.where(m, rr, np.nan)
                if yol == "ortalama":
                    return butce_ortalama(rr, anahtar + ek, tekrar, temel)
                return butce_trend(t_yil, ay, rr, anahtar + ek, tekrar, temel)
            s = hesap(r0)
            birim = "mm/yıl" if yol == "ortalama" else "(mm/yıl)/10 yıl"
            r = _satir("butce", yol, "dS/dt − (P − ET − R)", f"GRACE; P {ana}; ET, R GLDAS", b, hucre, s, birim,
                       bant, BUTCE_KAYNAK)
            r["donem"] = _donem(yil[ok])
            r["yorum"] = BUTCE_YORUMU if r["etiket"] in (KUCUK, BUYUK) else ""
            ek = dict(ek_terim)
            if yol == "trend":
                def tr(x):
                    a = aylik_anomali_dizi(np.where(ok, x, np.nan), ay)
                    return float(ekk_satir(t_yil[None], a[None])[0] * 12 * 10)
                ek = {"dS_dt_trend": tr(dS), "P_ET_R_trend": tr(B["P"][ana][k] - B["ET"][k] - R)}
            r["ek"] = "; ".join(f"{a}={v:.4g}" for a, v in ek.items())
            alt = []
            for u in BUTCE_YAGIS[1:]:
                if u in B["P"]:
                    sa = hesap(artik(u), ek=f"|{u}")
                    alt.append((f"yağış {u}", etiketle(sa["ga_alt"], sa["ga_ust"], bant[1], bant[2])[0]))
            kirpma = []
            for ad, m in _kirp(yil.astype(float), ok):
                sk = hesap(r0, m, ek=f"|{ad}")
                kirpma.append((ad, etiketle(sk["ga_alt"], sk["ga_ust"], bant[1], bant[2])[0]))
            satirlar.append(_karne_ekle(r, alt, kirpma, "alternatif yağış ürünü yok", uy, kr) | _meta(g0))
    print(f"  su bütçesi: {len(bl)} bölge × 2 yol")
    return pd.DataFrame(satirlar, columns=SUTUNLAR)


# ---------------------------------------------------------------- test 3: paket
def kar_cizgisi_serisi(kar_m: xr.DataArray, rakim: xr.DataArray, maske: np.ndarray) -> dict:
    """Bir bölgede her yılın kar çizgisi rakımı (``physics.shift.snowline_series``) ve yeterlilik bilgisi."""
    from physics.shift import snowline_series
    mk = xr.DataArray(maske, coords={"lat": rakim["lat"], "lon": rakim["lon"]}, dims=("lat", "lon"))
    z = np.where(maske, rakim.values, np.nan)
    dilim = kar_dilim_sayisi(z)
    s = snowline_series(kar_m.rename(yil="kis"), rakim, mask=mk, dilim=KAR_DILIM, esik=KAR_ESIK,
                        min_pixels=KAR_MIN_HUCRE)
    return {"yil": np.asarray(s["kis"], float), "rakim_m": np.asarray(s["rakim_m"], float), "dilim": dilim}


def kar_testi(paket: Path, iller: bool = True, tekrar: int = TEKRAR, temel: int = TOHUM) -> pd.DataFrame:
    """Kar çizgisi kayması: kış ve ilkbahar, il / bölge / Türkiye; beklenen = sıcaklık trendi / azalma oranı."""
    kar = _l1(paket, "kar_ortusu", "MOD10CM")
    rakim = _l1(paket, "rakim", "SRTM")
    if kar is None or rakim is None:
        raise FileNotFoundError("kar_ortusu__MOD10CM.nc ve rakim__SRTM.nc gerekli")
    T = {u: _l1(paket, "sicaklik_2m", u) for u in SICAKLIK}
    bl, mk = bolgeler_ve_maskeler(kar["lat"].values, kar["lon"].values, iller)
    dolu = kar.notnull().any(("lat", "lon")).values
    bos_aylar = [str(t)[:7] for t, d in zip(kar["time"].values, dolu) if not d]
    satirlar = []
    for mevsim in KAR_MEVSIMLERI:
        km = S.mevsim_serisi(kar, mevsim, toplam=False)          # eksik ayı olan mevsim NaN (L2 kuralı)
        dusen = [int(y) for y, d in zip(km["yil"].values, km.notnull().any(("lat", "lon")).values) if not d]
        Tm = {}
        for u, da in T.items():
            if da is not None:
                tm = S.mevsim_serisi(da, mevsim, toplam=False)
                Tm[u] = (tm["yil"].values.astype(float),
                         bolge_ortalamalari(tm.rename(yil="time"), [mk[b["anahtar"]] for b in bl]))
        uy, kr = urun_uyarilari(paket, [("kar_ortusu", "MOD10CM", kar), ("sicaklik_2m", SICAKLIK[0], T[SICAKLIK[0]])])
        not_bos = (f"MOD10CM boş aylar {', '.join(bos_aylar)}; düşen {mevsim} yılları: "
                   f"{', '.join(map(str, dusen)) or 'yok'} (docs/dogrulama.md)")
        gec_h = km.notnull().any("yil").values & np.isfinite(rakim.values)
        for k, b in enumerate(bl):
            m = mk[b["anahtar"]] & gec_h
            anahtar = f"kar|{mevsim}|{b['bolge_kodu']}"
            seri = kar_cizgisi_serisi(km, rakim, m) if m.any() else {"yil": km["yil"].values.astype(float),
                                                                     "rakim_m": np.full(km.sizes["yil"], np.nan),
                                                                     "dilim": 0}
            yillar, zc = seri["yil"], seri["rakim_m"]
            ok = np.isfinite(zc)
            gerek = max(KAR_MIN_YIL, math.ceil(km.sizes["yil"] / 2))
            if seri["dilim"] < KAR_MIN_DILIM:
                s, neden = _bos(""), f"yükselti aralığı yetersiz ({seri['dilim']} dolu dilim < {KAR_MIN_DILIM})"
            elif ok.sum() < gerek:
                s, neden = _bos(""), f"kar çizgisi yalnız {int(ok.sum())} yılda tanımlı (< {gerek})"
            else:
                s, neden = egim_10yil(yillar, zc, anahtar, tekrar, temel), ""

            def bek(u, mm=None):
                if u not in Tm:
                    return (float("nan"),) * 3, {"gozlenen": float("nan"), "ga_alt": float("nan"),
                                                  "ga_ust": float("nan")}
                ty = np.interp(yillar, Tm[u][0], Tm[u][1][k], left=np.nan, right=np.nan)
                sec = ok if mm is None else (ok & mm)
                dt = egim_10yil(yillar[sec], ty[sec], anahtar + f"|T|{u}|{mm is not None}", tekrar, temel)
                return beklenen_kar_kaymasi(dt["gozlenen"]), dt
            beklenen, dT = bek(SICAKLIK[0])
            if neden:
                beklenen = (float("nan"),) * 3
            r = _satir("kar_cizgisi", mevsim, "kar_ortusu", f"MOD10CM~sicaklik_2m:{SICAKLIK[0]}", b, int(m.sum()), s,
                       "m/10 yıl", beklenen, LAPSE_KAYNAK)
            if neden:
                r["etiket_gerekce"] = neden
            r["n"] = int(ok.sum())
            r["donem"] = _donem(yillar[ok])
            r["yorum"] = KAR_YORUMU if r["etiket"] in (KUCUK, BUYUK) else ""
            r["ek"] = (f"sicaklik_trendi_C_10yil={dT['gozlenen']:.3g} [GA {dT['ga_alt']:.3g}, {dT['ga_ust']:.3g}]; "
                       f"dolu_dilim={seri['dilim']}; {not_bos}")
            alt, kirpma = [], []
            if not neden:
                for u in SICAKLIK[1:]:
                    if u in Tm:
                        ba, _ = bek(u)
                        alt.append((f"sıcaklık {u}", etiketle(s["ga_alt"], s["ga_ust"], ba[1], ba[2])[0]))
                for ad, mm in _kirp(yillar, ok):
                    sk = egim_10yil(yillar[mm], zc[mm], anahtar + f"|{ad}", tekrar, temel)
                    bk, _ = bek(SICAKLIK[0], mm)
                    kirpma.append((ad, etiketle(sk["ga_alt"], sk["ga_ust"], bk[1], bk[2])[0]))
            satirlar.append(_karne_ekle(r, alt, kirpma, "alternatif sıcaklık ürünü yok", uy, kr) | _meta(kar))
        print(f"  kar çizgisi {mevsim}: {len(bl)} bölge")
    return pd.DataFrame(satirlar, columns=SUTUNLAR)


# ---------------------------------------------------------------- yazma ve CLI
def cikti_klasoru(paket: Path) -> Path:
    return Path(paket) / "L4_iliski" / "buyukluk"


def csv_yaz(df: pd.DataFrame, yol: Path) -> Path:
    yol.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(yol, index=False, encoding="utf-8-sig", float_format="%.4g")
    return yol


def yaz(paket: Path, test: str, df: pd.DataFrame) -> list[Path]:
    """``<test>__il.csv`` (varsa) ve ``<test>__bolge.csv`` (bölge + Türkiye)."""
    d = cikti_klasoru(paket)
    yollar = []
    il = df[df["bolge_turu"] == "il"]
    if len(il):
        yollar.append(csv_yaz(il, d / f"{test}__il.csv"))
    yollar.append(csv_yaz(df[df["bolge_turu"] != "il"], d / f"{test}__bolge.csv"))
    return yollar


OZET_SUTUNLARI = ["test", "yol", "degisken", "bolge_turu", "bolge_adi", "n", "gozlenen", "ga_alt", "ga_ust", "birim",
                  "beklenen", "beklenen_alt", "beklenen_ust", "etiket", "guven", "gerekce"]


def ozet_yaz(paket: Path) -> Path:
    """Var olan ``<test>__bolge.csv`` dosyalarından özet + kural metni."""
    d = cikti_klasoru(paket)
    parca = [pd.read_csv(d / f"{t}__bolge.csv", encoding="utf-8-sig") for t in TESTLER
             if (d / f"{t}__bolge.csv").exists()]
    oz = pd.concat(parca, ignore_index=True)[OZET_SUTUNLARI] if parca else pd.DataFrame(columns=OZET_SUTUNLARI)
    (d / "KURAL.txt").write_text(KURAL_METNI + "\nKaynaklar:\n- " + "\n- ".join(
        [CC_KAYNAK, CC_KARA_YORUMU, BUTCE_KAYNAK, BUTCE_YORUMU, BUTCE_IL_NOTU, LAPSE_KAYNAK, BOOTSTRAP_KAYNAK]) + "\n",
        encoding="utf-8")
    return csv_yaz(oz, d / "ozet.csv")


def ekran_ozeti(df: pd.DataFrame) -> None:
    """Türkiye ve bölge satırlarını kısa tablo olarak basar."""
    s = df[df["bolge_turu"] != "il"]
    for _, r in s.iterrows():
        g = f"{r['gozlenen']:+.3g} [{r['ga_alt']:+.3g}, {r['ga_ust']:+.3g}]" if np.isfinite(r["gozlenen"]) else "—"
        b = f"[{r['beklenen_alt']:+.3g}, {r['beklenen_ust']:+.3g}]" if np.isfinite(r["beklenen_alt"]) else "—"
        print(f"  {r['test']:11s} {r['yol']:15s} {str(r['degisken'])[:16]:16s} {r['bolge_adi'][:18]:18s} "
              f"{g:28s} {b:20s} {r['birim']:16s} {r['etiket']:27s} {r['guven']}")


def uret(paket: Path, testler=TESTLER, iller: bool = True, tekrar: int = TEKRAR, temel: int = TOHUM) -> dict:
    """Seçili testleri çalıştırır, yazar; ``{test: DataFrame, "yollar": [...]}``."""
    paket = Path(paket)
    out, yollar = {}, []
    for t in testler:
        t0 = time.time()
        if t == "cc":
            df = cc_testi(paket, iller, tekrar, temel)
        elif t == "butce":
            df = butce_testi(paket, tekrar, temel)
        else:
            df = kar_testi(paket, iller, tekrar, temel)
        out[t] = df
        yollar += yaz(paket, t, df)
        print(f"  {t}: {len(df)} satır, {time.time() - t0:.1f} sn")
    yollar.append(ozet_yaz(paket))
    out["yollar"] = yollar
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Büyüklük testleri (Clausius-Clapeyron, su bütçesi, kar çizgisi).")
    ap.add_argument("--surum", default="v0.1")
    ap.add_argument("--paket", default=None, help="paket kökü (varsayılan outputs/trend-dedektifi-turkiye-<surum>)")
    ap.add_argument("--test", choices=TESTLER, default=None, help="yalnız bu test")
    ap.add_argument("--il-yok", action="store_true", help="il satırlarını atla (hızlı)")
    ap.add_argument("--tekrar", type=int, default=TEKRAR)
    a = ap.parse_args(argv)
    from physics.tek_cift import paket_koku
    paket = paket_koku(a.surum, Path(a.paket) if a.paket else None)
    t0 = time.time()
    sonuc = uret(paket, (a.test,) if a.test else TESTLER, not a.il_yok, a.tekrar)
    print(f"\nBüyüklük testleri ({KURAL_SURUMU}), Türkiye ve bölgeler:")
    for t in TESTLER:
        if t in sonuc:
            ekran_ozeti(sonuc[t])
    if "butce" in sonuc:
        print(f"  not: {BUTCE_IL_NOTU}")
    print("\nEtiketler bir büyüklük tutarlılığı özetidir; nedensellik göstermez.")
    for y in sonuc["yollar"]:
        print(f"  yazıldı: {y}")
    print(f"Toplam süre: {time.time() - t0:.1f} sn")


if __name__ == "__main__":
    main()
