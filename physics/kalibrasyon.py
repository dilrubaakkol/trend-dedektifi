"""Motorun kalibrasyonu: cevabı bilinen yapay serilerde ne sıklıkla yanılıyor, neyi görebiliyor?

    python -m physics.kalibrasyon --surum v0.1       # → <paket>/L4_iliski/kalibrasyon/
    python -m physics.kalibrasyon --hizli            # az tekrar (deneme)

Sade anlatım:
1. **Yanlış alarm.** İki seri arasında hiç ilişki yokken motor kaç kere "anlamlı" diyor? Hedef: en çok %5
   (bölge/Türkiye eşiği p < 0,05). Seriler gerçek iklim serileri gibi "hafızalı" (AR(1)) ve trendlidir.
2. **Ters alarm.** Gerçek ilişki pozitifken motor kaç kere "ters yönde" diyor?
3. **Güç (yakalama).** Bilinen güçte (r) bir ilişki varken motor kaç kere "beklenen yönde" diyor?
4. **Ortak trend tuzağı.** İlişkisiz ama ikisi de aynı dönemde artan iki seri: trend çıkarmasaydık kaç kere
   sahte "anlamlı" derdik? (Motor trendi çıkarır.)
5. **FDR.** 81 ilin bir kısmında gerçek ilişki varken, "anlamlı" denen illerin yüzde kaçı aslında ilişkisiz?
   Hedef: ortalama en çok %10 (Benjamini-Hochberg 1995). İller birbirine benzediği için ortak bileşenli
   (bağımlı) durum da denenir.
6. **Saptanabilir en küçük r.** Gerçek her satırın etkin örneklem sayısıyla, motorun %80 olasılıkla
   yakalayabileceği en zayıf ilişki. "anlamsiz" etiketi "ilişki yok" değil, "bu uzunlukta veriyle bu
   güçten zayıf ilişki görülemez" demektir.

Yöntem ``physics.iliski.iliski_1d`` ile birebir aynıdır (L4 ve tek çift komutu bunu kullanır).
Simülasyon sentetiktir; sabit tohumla tekrar üretilebilir.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from physics.iliski import ALFA, ALFA_FDR, bh_fdr, etkin_n, gecikme1, iliski_1d, p_degeri

TOHUM = 2026
TEKRAR = 1000
GUC_HEDEF = 0.80
N_DEGERLERI = (22, 25, 300)            # 22–25: yıllık/mevsimlik seri; 300: aylık anomali (25 yıl)
PHI_DEGERLERI = (0.0, 0.3, 0.6)        # gecikme-1 otokorelasyonu ("hafıza")
R_DEGERLERI = (0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8)
TREND_SD = 1.0                         # dönem boyunca trend artışı (serinin standart sapması cinsinden)


# ---------------------------------------------------------------- yapay seri
def ar1_cift(n: int, phi: float, rho: float, rng: np.random.Generator, trend: float = TREND_SD,
             ortak_trend: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """Korelasyonu ``rho`` olan iki AR(1) seri (aynı ``phi``; durağan korelasyon = yenilik korelasyonu).

    Her seriye ``trend`` büyüklüğünde doğrusal eğilim eklenir; ``ortak_trend`` ise ikisine aynı yönde
    (ilişkisiz serilerde sahte korelasyon kaynağı), değilse rastgele işaretli.
    """
    e = rng.multivariate_normal([0, 0], [[1, rho], [rho, 1]], size=n)
    x = np.empty((n, 2))
    x[0] = e[0]
    s = np.sqrt(1 - phi ** 2)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + s * e[i]
    t = np.linspace(0, 1, n)
    isaret = np.ones(2) if ortak_trend else rng.choice([-1.0, 1.0], 2)
    x = x + trend * t[:, None] * isaret[None, :]
    return x[:, 0], x[:, 1]


# ---------------------------------------------------------------- 1–4: tek seri çifti
def deneme(n: int, phi: float, rho: float, tekrar: int, rng: np.random.Generator,
           ortak_trend: bool = False) -> dict:
    """``tekrar`` çiftte motorun etiket oranları (beklenen yön +1) ve trendsiz-ham yanlış alarm."""
    say = {"beklenen_yonde": 0, "ters_yonde": 0, "anlamsiz": 0, "hesaplanamadi": 0}
    ham_anlamli = 0
    for _ in range(tekrar):
        x, y = ar1_cift(n, phi, rho, rng, ortak_trend=ortak_trend)
        r = iliski_1d(x, y, +1)
        say[r["etiket"] or "hesaplanamadi"] += 1
        # karşılaştırma: trend ÇIKARILMADAN aynı test (motorun yapmadığı şey)
        rh = float(np.corrcoef(x, y)[0, 1])
        ph = p_degeri(rh, etkin_n(n, gecikme1(x), gecikme1(y)))
        ham_anlamli += bool(np.isfinite(ph) and ph < ALFA)
    return {"n": n, "phi": phi, "gercek_r": rho, "ortak_trend": ortak_trend, "tekrar": tekrar,
            **{f"oran_{k}": v / tekrar for k, v in say.items()},
            "oran_anlamli": (say["beklenen_yonde"] + say["ters_yonde"]) / tekrar,
            "oran_anlamli_trendsiz_olmasa": ham_anlamli / tekrar}


def tek_cift_tablosu(tekrar: int = TEKRAR, tohum: int = TOHUM) -> pd.DataFrame:
    """Bütün (n, phi, r) koşulları + ilişkisiz-ortak trend koşulu."""
    rng = np.random.default_rng(tohum)
    satir = [deneme(n, phi, r, tekrar, rng) for n in N_DEGERLERI for phi in PHI_DEGERLERI for r in R_DEGERLERI]
    satir += [deneme(n, phi, 0.0, tekrar, rng, ortak_trend=True) for n in N_DEGERLERI for phi in PHI_DEGERLERI]
    return pd.DataFrame(satir)


# ---------------------------------------------------------------- 5: 81 il ve FDR
def fdr_deneme(n: int = 25, phi: float = 0.3, iller: int = 81, gercek_pay: float = 0.3, rho: float = 0.5,
               ortak: float = 0.0, tekrar: int = 500, tohum: int = TOHUM) -> dict:
    """81 ilde ``gercek_pay`` kadarında gerçek ilişki (``rho``), kalanında yok. ``ortak``: ilişkisiz illerin
    ortak bileşen payı (0 = bağımsız, 0,5 = komşu iller gibi benzer; o illerin p değerleri birlikte küçülüp
    büyür). Gerçekleşen FDR ve yakalama oranı."""
    rng = np.random.default_rng(tohum)
    gercek = np.arange(iller) < round(gercek_pay * iller)
    fdr, guc, alarm = [], [], []
    for _ in range(tekrar):
        gx, gy = ar1_cift(n, phi, 0.0, rng, trend=0.0)          # illerin ortak (ilişkisiz) bileşeni
        p, isaret = np.empty(iller), np.empty(iller)
        for k in range(iller):
            x, y = ar1_cift(n, phi, rho if gercek[k] else 0.0, rng)
            if not gercek[k]:      # ilişkisiz iller birbirine benzer (FDR için zor durum); sinyal seyrelmez
                x, y = np.sqrt(1 - ortak) * x + np.sqrt(ortak) * gx, np.sqrt(1 - ortak) * y + np.sqrt(ortak) * gy
            r = iliski_1d(x, y, +1)
            p[k], isaret[k] = r["p"], np.sign(r["r"])
        q = bh_fdr(p)
        anl = q <= ALFA_FDR
        yanlis = anl & (~gercek | (isaret < 0))
        fdr.append(yanlis.sum() / anl.sum() if anl.any() else 0.0)
        guc.append((anl & gercek & (isaret > 0)).sum() / max(gercek.sum(), 1))
        alarm.append((anl & ~gercek).sum())
    return {"n": n, "phi": phi, "iller": iller, "gercek_pay": gercek_pay, "gercek_r": rho, "ortak_bilesen": ortak,
            "tekrar": tekrar, "gerceklesen_fdr": float(np.mean(fdr)), "hedef_fdr": ALFA_FDR,
            "yakalama_orani": float(np.mean(guc)), "il_basi_yanlis_alarm": float(np.mean(alarm))}


def fdr_tablosu(tekrar: int = 500, tohum: int = TOHUM) -> pd.DataFrame:
    kos = [(0.0, 0.0), (0.3, 0.0), (0.3, 0.5), (0.6, 0.0), (0.6, 0.5)]   # (gerçek pay, ortak bileşen)
    return pd.DataFrame([fdr_deneme(gercek_pay=g, ortak=o, tekrar=tekrar, tohum=tohum + i)
                         for i, (g, o) in enumerate(kos)])


# ---------------------------------------------------------------- 6: saptanabilir en küçük r
def saptanabilir_r(n_etkin: float, alfa: float = ALFA, guc: float = GUC_HEDEF) -> float:
    """Fisher z yaklaşımı: iki yönlü ``alfa`` testinde ``guc`` olasılıkla yakalanan en küçük |r|.
    r = tanh((z_{1−α/2} + z_{güç}) / √(n_etkin − 3)). n_etkin ≤ 3 → NaN."""
    if not np.isfinite(n_etkin) or n_etkin <= 3:
        return float("nan")
    z = stats.norm.ppf(1 - alfa / 2) + stats.norm.ppf(guc)
    return float(np.tanh(z / np.sqrt(n_etkin - 3)))


def gercek_satirlar(paket: Path) -> pd.DataFrame:
    """``ciftler.csv`` satırlarına saptanabilir en küçük r ve okuma ekler (dosyanın kendisi değişmez).

    il satırları FDR'li (α = 0,10) okunur; yaklaşık olarak bölge eşiğiyle (α = 0,05) aynı sınır verilir,
    bu yüzden il satırlarında değer alt sınırdır.
    """
    df = pd.read_csv(Path(paket) / "L4_iliski" / "ciftler.csv", encoding="utf-8-sig", dtype={"bolge_kodu": str})
    df = df[df["etkin_n"].notna()].copy()
    df["saptanabilir_r"] = [saptanabilir_r(v) for v in df["etkin_n"]]
    zayif = df["etiket"].eq("anlamsiz") & (df["r"].abs() < df["saptanabilir_r"])
    df["okuma"] = np.select(
        [df["etiket"].eq("anlamsiz") & zayif, df["etiket"].eq("anlamsiz"), df["etiket"].ne("anlamsiz")],
        ["ilişki bu veri uzunluğunda görülemeyecek kadar zayıf (yok demek değil)",
         "r sınırın üstünde ama anlamsız (etkin n küçük ya da FDR)", "anlamlı"], default="")
    return df[["cift_no", "cift", "seri", "gecikme_ay", "bolge_turu", "bolge_adi", "n", "etkin_n", "r",
               "saptanabilir_r", "p", "etiket", "okuma"]]


def guc_ozeti(df: pd.DataFrame) -> pd.DataFrame:
    """Çift × bölge türü: etkin n ve saptanabilir r medyanı, anlamsız satırların kaçı 'zayıf'."""
    g = df.groupby(["cift_no", "cift", "gecikme_ay", "bolge_turu"])
    return g.agg(satir=("r", "size"), etkin_n_medyan=("etkin_n", "median"),
                 saptanabilir_r_medyan=("saptanabilir_r", "median"),
                 anlamsiz=("etiket", lambda s: int((s == "anlamsiz").sum())),
                 anlamsiz_zayif=("okuma", lambda s: int(s.str.startswith("ilişki bu veri").sum()))).reset_index()


# ---------------------------------------------------------------- çıktı
def uret(paket: Path | None, tekrar: int = TEKRAR, fdr_tekrar: int = 500) -> dict:
    t0 = time.perf_counter()
    out = {"tek": tek_cift_tablosu(tekrar), "fdr": fdr_tablosu(fdr_tekrar),
           "sinir": pd.DataFrame([{"etkin_n": n, "saptanabilir_r_alfa005": saptanabilir_r(n),
                                   "saptanabilir_r_alfa010": saptanabilir_r(n, ALFA_FDR)}
                                  for n in (8, 10, 12, 15, 18, 20, 22, 25, 30, 50, 100, 200, 300)])}
    if paket is not None and (Path(paket) / "L4_iliski" / "ciftler.csv").exists():
        out["gercek"] = gercek_satirlar(paket)
        out["guc_ozeti"] = guc_ozeti(out["gercek"])
    out["sure_sn"] = time.perf_counter() - t0
    return out


def yaz(out: dict, hedef: Path) -> list[Path]:
    hedef.mkdir(parents=True, exist_ok=True)
    adlar = {"tek": "yanilma_oranlari.csv", "fdr": "fdr_81_il.csv", "sinir": "saptanabilir_r_tablosu.csv",
             "gercek": "ciftler_saptanabilir_r.csv", "guc_ozeti": "guc_ozeti.csv"}
    yollar = []
    for k, ad in adlar.items():
        if k in out:
            p = hedef / ad
            out[k].to_csv(p, index=False, encoding="utf-8-sig", float_format="%.4g")
            yollar.append(p)
    return yollar


def ozet_yazdir(out: dict) -> None:
    t = out["tek"]
    print("1) YANLIŞ ALARM (gerçek r = 0; hedef ≤ %5):")
    s = t[(t["gercek_r"] == 0) & ~t["ortak_trend"]]
    for _, r in s.iterrows():
        print(f"   n={r['n']:3d} hafıza φ={r['phi']:.1f}: anlamlı {r['oran_anlamli']:.1%} "
              f"(ters {r['oran_ters_yonde']:.1%})")
    print("2) ORTAK TREND TUZAĞI (ilişkisiz, ikisi de artıyor): motor / trend çıkarılmasaydı")
    s = t[t["ortak_trend"]]
    for _, r in s.iterrows():
        print(f"   n={r['n']:3d} φ={r['phi']:.1f}: {r['oran_anlamli']:.1%} / {r['oran_anlamli_trendsiz_olmasa']:.1%}")
    print("3) YAKALAMA (beklenen yönde) ve TERS ALARM, n = 25:")
    s = t[(t["n"] == 25) & ~t["ortak_trend"] & (t["gercek_r"] > 0)]
    for _, r in s.iterrows():
        print(f"   φ={r['phi']:.1f} gerçek r={r['gercek_r']:.1f}: yakaladı {r['oran_beklenen_yonde']:.0%} · "
              f"ters {r['oran_ters_yonde']:.2%}")
    print("4) 81 İL, BH-FDR (hedef ≤ %10):")
    for _, r in out["fdr"].iterrows():
        print(f"   gerçek ilişkili il payı {r['gercek_pay']:.0%}, illerin ortak bileşeni {r['ortak_bilesen']:.1f}: "
              f"FDR {r['gerceklesen_fdr']:.1%} · yakalama {r['yakalama_orani']:.0%} · "
              f"ilişkisiz illerde alarm {r['il_basi_yanlis_alarm']:.2f}/tekrar")
    print("5) SAPTANABİLİR EN KÜÇÜK r (%80 güç, α = 0,05):")
    print("   " + " · ".join(f"n_etkin {int(r['etkin_n'])}: {r['saptanabilir_r_alfa005']:.2f}"
                           for _, r in out["sinir"].iterrows()))
    if "guc_ozeti" in out:
        g = out["guc_ozeti"]
        g = g[g["bolge_turu"] != "il"].groupby(["cift_no", "gecikme_ay"]).agg(
            etkin_n=("etkin_n_medyan", "median"), sinir=("saptanabilir_r_medyan", "median"),
            anlamsiz=("anlamsiz", "sum"), zayif=("anlamsiz_zayif", "sum")).reset_index()
        print("6) GERÇEK VERİ (bölge + Türkiye satırları): çift · etkin n · saptanabilir r · anlamsız (zayıf)")
        for _, r in g.iterrows():
            gk = f" gecikme {int(r['gecikme_ay'])}" if r["gecikme_ay"] else ""
            print(f"   çift {int(r['cift_no'])}{gk}: {r['etkin_n']:.0f} · {r['sinir']:.2f} · "
                  f"{int(r['anlamsiz'])} ({int(r['zayif'])})")
    print(f"   süre {out['sure_sn']:.0f} sn")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m physics.kalibrasyon", description=__doc__.splitlines()[0])
    ap.add_argument("--surum", default="v0.1")
    ap.add_argument("--paket", type=Path, default=None)
    ap.add_argument("--hizli", action="store_true", help="az tekrar (200 / 50), yalnız deneme")
    a = ap.parse_args(argv)
    from physics.tek_cift import paket_koku
    paket = paket_koku(a.surum, a.paket)
    out = uret(paket, *((200, 50) if a.hizli else (TEKRAR, 500)))
    ozet_yazdir(out)
    for p in yaz(out, paket / "L4_iliski" / "kalibrasyon"):
        print(" ", p)


if __name__ == "__main__":
    main()
