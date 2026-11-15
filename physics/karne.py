"""İlişki karnesi: L4 (ciftler.csv) ve tek çift komutu satırları için sağlamlık kontrolleri.

Kontroller (kural metni: ``stats.karne.KURAL_METNI``):
  a) alternatif ürün kombinasyonları (ör. yağış GPM/GLDAS/MERRA2): kaç kombinasyon aynı etiketi veriyor
  b) karıştırma testi: trendi giderilmiş y serisi dairesel blok permütasyonuyla karıştırılır → p_perm
  c) trendden arındırma: trendsiz r ile ham r aynı işaretli ve |r| ≥ |ham r| / 2 (sahte korelasyon kontrolü)
  d) gecikme duyarlılığı: gecikme ±1 ayda r'nin işareti korunuyor mu
  e) eşik: α = 0,05'te de aynı etiket mi
  f) uyarılar: ürün uyarıları, rejime bağlı çift, az hücre
Seriler ``physics.tablo.cift_tablosu`` ile aynı yoldan kurulur (bölge maskesi, alan ortalaması,
``cift_serileri``). Karne bir sağlamlık ve tutarlılık özetidir; nedensellik göstermez.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from physics import seriler as S
from physics.ciftler import CIFTLER, Cift, cift_serileri
from physics.iliski import ALFA, etiket, trend_cikar
from physics.tablo import bolge_listesi, bolge_maskeleri, cift_tablosu, ham_iliski
from stats.karne import (ALFA_SIKI, ESIK_PERM, GECTI, KALDI, KURAL_SURUMU, TEKRAR, TOHUM, UYG, blok_uzunlugu,
                         dairesel_blok_indeksleri, guven_seviyesi, perm_p, tohum)

AZ_HUCRE = 3
ILISKI_ADLARI = {"a": "kaynak uyumu", "b": "karıştırma testi", "c": "trendden arındırma",
                 "d": "gecikme duyarlılığı", "e": "α = 0,05"}
SUTUNLAR = ["cift_no", "cift", "seri", "gecikme_ay", "beklenen_yon", "bolge_turu", "bolge_kodu", "bolge_adi",
            "hucre_sayisi", "n", "r", "r_ham", "p", "p_fdr", "anlamli", "etiket", "a_kaynak_uyumu", "a_sayi",
            "b_karistirma", "b_p_perm", "b_blok", "c_trend", "c_sayi", "d_gecikme", "d_sayi", "e_esik", "e_sayi",
            "f_uyarilar", "f_kritik", "guven", "gerekce", "kural_surumu"]


def bolge_serileri(c: Cift, a: xr.DataArray, b: xr.DataArray, iller: bool = True,
                   bolgeler: list[str] | None = None) -> dict[tuple[str, int], tuple]:
    """``{(bolge_kodu, gecikme): (x, y, t)}`` — ``cift_tablosu`` ile aynı bölge serileri."""
    iller = iller and c.harita
    a, b = xr.align(a, b, join="inner")
    maskeler = bolge_maskeleri(a["lat"].values, b["lon"].values, iller)
    gecerli = (a.notnull().any("time") & b.notnull().any("time")).values
    if c.kar_tarafi:
        kar = S.mevsim_serisi(b if c.kar_tarafi == "y" else a, "kis", toplam=False)
        gecerli &= S.kar_maskesi(kar, c.kar_maskesi_esik).values
    secili = bolge_listesi(iller)
    if bolgeler is not None:
        secili = [bl for bl in secili if bl["anahtar"] in set(bolgeler)]
    out = {}
    for bl in secili:
        m = maskeler[bl["anahtar"]] & gecerli
        if not m.any():
            continue
        mk = xr.DataArray(m, coords={"lat": a["lat"], "lon": a["lon"]}, dims=("lat", "lon"))
        xa, ya = S.alan_ortalamasi(a, mk), S.alan_ortalamasi(b, mk)
        xa.attrs, ya.attrs = a.attrs, b.attrs
        for s in cift_serileri(c, xa, ya):
            out[(bl["bolge_kodu"], int(s["gecikme"]))] = (s["x"].values, s["y"].values, s["t"])
    return out


def karistirma_iliski(x, y, t, n_etkin: float, anahtar: str, tekrar: int = TEKRAR,
                      temel: int = TOHUM) -> dict:
    """b) Trendi giderilmiş y'yi dairesel blok permütasyonuyla karıştırır; |r_perm| ≥ |r| oranı."""
    x, y, t = (np.asarray(v, float) for v in (x, y, t))
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(t)
    n = int(ok.sum())
    if n < 8:
        return {"durum": UYG, "p_perm": np.nan, "blok": np.nan}
    xd = trend_cikar(np.where(ok, x, np.nan), t)[ok]
    yd = trend_cikar(np.where(ok, y, np.nan), t)[ok]
    xd, yd = xd - xd.mean(), yd - yd.mean()
    olcek = np.sqrt((xd * xd).sum() * (yd * yd).sum())
    if olcek == 0:
        return {"durum": UYG, "p_perm": np.nan, "blok": np.nan}
    blok = blok_uzunlugu(n, n_etkin)
    idx = dairesel_blok_indeksleri(n, blok, tekrar, np.random.default_rng(tohum(anahtar, temel)))
    r = float(xd @ yd / olcek)
    p = perm_p(r, (yd[idx] @ xd) / olcek)
    return {"durum": GECTI if p < ESIK_PERM else KALDI, "p_perm": p, "blok": blok}


def trend_kontrolu(r: float, r_ham: float) -> dict:
    """c) Trendsiz r ham r ile aynı işaretli ve |r| ≥ |ham r| / 2 mi."""
    if not (np.isfinite(r) and np.isfinite(r_ham)):
        return {"durum": UYG, "sayi": ""}
    ok = np.sign(r) == np.sign(r_ham) and abs(r) >= abs(r_ham) / 2
    return {"durum": GECTI if ok else KALDI, "sayi": f"ham r {r_ham:+.2f} → trendsiz r {r:+.2f}"}


def _l1(paket: Path, d: str, u: str) -> xr.DataArray:
    from physics.tek_cift import _l1_ac
    return _l1_ac(paket, d, u)


def _urunler(paket: Path | None, degisken: str, ana: str) -> list[str]:
    if paket is None:
        return [ana]
    from physics.tek_cift import l1_secenekleri
    return l1_secenekleri(paket).get(degisken, [ana])


def _anahtar(df: pd.DataFrame) -> pd.Series:
    return df["bolge_kodu"].astype(str) + "|" + df["gecikme_ay"].astype(int).astype(str)


def _uyarilar(c: Cift, a: xr.DataArray, b: xr.DataArray) -> tuple[list[str], list[str]]:
    uy, kr = [], []
    for da, d, u in ((a, c.d1, c.u1), (b, c.d2, c.u2)):
        for k in ("bilinen_sorunlar", "trend_uyarisi"):
            if da.attrs.get(k):
                uy.append(f"{d} ({u}) {k}: {da.attrs[k]}")
                kr.append(f"{d} {k}")
        if str(da.attrs.get("dogrulanmadi", "")).lower() == "evet":
            uy.append(f"{d} ({u}) Kademe 2: bağımsız doğrulaması yapılmadı")
            kr.append(f"{d} Kademe 2")
    if c.rejime_bagli:
        uy.append("rejime bağlı çift: beklenen yön iklim rejimine bağlı (ciftler.yaml)")
        kr.append("rejime bağlı çift")
    return uy, kr


def cift_karnesi(c: Cift, a: xr.DataArray, b: xr.DataArray, ana: pd.DataFrame, paket: Path | None = None,
                 iller: bool = True, bolgeler: list[str] | None = None, fdr: bool = True,
                 tekrar: int = TEKRAR, temel: int = TOHUM) -> pd.DataFrame:
    """Bir çiftin ``ana`` satırları (ciftler.csv sütunları) için karne.

    ``paket`` verilirse alternatif ürünler ``<paket>/L1_kup`` içinden okunur (a kontrolü).
    ``iller``, ``bolgeler``, ``fdr``: ana satırların üretildiği kapsam (cift_tablosu ile aynı).
    """
    ana = ana.copy()
    ana["gecikme_ay"] = ana["gecikme_ay"].astype(int)
    seriler = bolge_serileri(c, a, b, iller, bolgeler)
    kw = {"iller": iller, "bolgeler": bolgeler, "fdr": fdr}

    # a) alternatif ürünler (aynı gecikmeler, aynı kapsam)
    alt = []
    for u1 in _urunler(paket, c.d1, c.u1):
        for u2 in _urunler(paket, c.d2, c.u2):
            if (u1, u2) == (c.u1, c.u2):
                continue
            cc = replace(c, u1=u1, u2=u2)
            t = cift_tablosu(cc, _l1(paket, c.d1, u1), _l1(paket, c.d2, u2), **kw)
            alt.append((f"{u1}~{u2}", dict(zip(_anahtar(t), t["etiket"].fillna("")))))
    # d) gecikme ±1
    gec = {}
    if c.mevsim != "mevsimlik":
        lazim = sorted({g + d for g in ana["gecikme_ay"].unique() for d in (-1, 1) if g + d >= 0}
                       - set(c.gecikmeler))
        for g in lazim:
            t = cift_tablosu(replace(c, gecikmeler=(g,)), a, b, **kw)
            gec[g] = dict(zip(t["bolge_kodu"].astype(str), t["r"]))
        for g in c.gecikmeler:
            gec.setdefault(g, dict(zip(ana.loc[ana["gecikme_ay"] == g, "bolge_kodu"].astype(str),
                                       ana.loc[ana["gecikme_ay"] == g, "r"])))
    uy, kr = _uyarilar(c, a, b)

    satirlar = []
    for _, r in ana.iterrows():
        kod, g = str(r["bolge_kodu"]), int(r["gecikme_ay"])
        anahtar = f"{kod}|{g}"
        rr = float(r["r"]) if pd.notna(r["r"]) else np.nan
        et = r["etiket"] if isinstance(r["etiket"], str) else ""
        anl = r.get("anlamli") == 1
        x, y, t = seriler.get((kod, g), (None, None, None))
        ham = ham_iliski(x, y, t) if x is not None else {"r_ham": np.nan}
        b_ = (karistirma_iliski(x, y, t, float(r["etkin_n"]) if pd.notna(r.get("etkin_n")) else np.nan,
                                f"{c.kod}|{anahtar}", tekrar, temel)
              if x is not None else {"durum": UYG, "p_perm": np.nan, "blok": np.nan})
        c_ = trend_kontrolu(rr, ham["r_ham"])
        # a
        if alt and np.isfinite(rr):
            ayni = 1 + sum(1 for _, d in alt if d.get(anahtar, "") == et)
            m = 1 + sum(1 for _, d in alt if d.get(anahtar, "") != "")
            a_s = f"{ayni}/{m} kombinasyon aynı etiket ({', '.join(k for k, _ in alt)} denendi)"
            if anl:
                a_d = GECTI if ayni >= 2 else KALDI
            else:                                     # anlamsız sonucun uyumu sınanmaz (güven zaten YOK)
                a_d, a_s = UYG, f"sonuç anlamlı değil; {a_s}"
        else:
            a_d, a_s = UYG, ("alternatif ürün yok" if not alt else "r hesaplanamadı")
        # d
        komsu = [(g + d, gec.get(g + d, {}).get(kod, np.nan)) for d in (-1, 1) if g + d >= 0 and (g + d) in gec]
        komsu = [(gg, v) for gg, v in komsu if np.isfinite(v)]
        if not komsu or not np.isfinite(rr):
            d_d, d_s = UYG, ("mevsimlik seride gecikme yok" if c.mevsim == "mevsimlik" else "")
        else:
            d_d = GECTI if all(np.sign(v) == np.sign(rr) for _, v in komsu) else KALDI
            d_s = "; ".join(f"gecikme {gg}: r {v:+.2f}" for gg, v in komsu)
        # e
        if np.isfinite(rr):
            il = r["bolge_turu"] == "il" and fdr and pd.notna(r.get("p_fdr"))
            p05 = (float(r["p_fdr"]) <= ALFA_SIKI) if il else (float(r["p"]) < min(ALFA, ALFA_SIKI))
            et05 = etiket(rr, bool(p05), c.beklenen) or ""
            e_d = GECTI if (et05 == et and bool(p05) == anl) else KALDI
            e_s = f"α = 0,05 etiketi: {et05 or ('anlamlı' if p05 else 'anlamsız')}"
        else:
            e_d, e_s = UYG, ""
        uy_r, kr_r = list(uy), list(kr)
        if pd.notna(r.get("hucre_sayisi")) and int(r["hucre_sayisi"]) < AZ_HUCRE:
            uy_r.append(f"az hücre ({int(r['hucre_sayisi'])})")
            kr_r.append("az hücre")
        kontrol = {"a": a_d, "b": b_["durum"], "c": c_["durum"], "d": d_d, "e": e_d}
        gv, gr = guven_seviyesi(anl, kontrol, kr_r, adlar=ILISKI_ADLARI)
        satirlar.append({
            "cift_no": c.no, "cift": c.kod, "seri": c.seri, "gecikme_ay": g, "beklenen_yon": c.beklenen_yon,
            "bolge_turu": r["bolge_turu"], "bolge_kodu": kod, "bolge_adi": r["bolge_adi"],
            "hucre_sayisi": r.get("hucre_sayisi"), "n": r.get("n"), "r": rr, "r_ham": ham["r_ham"],
            "p": r.get("p"), "p_fdr": r.get("p_fdr"), "anlamli": r.get("anlamli"), "etiket": et,
            "a_kaynak_uyumu": a_d, "a_sayi": a_s, "b_karistirma": b_["durum"], "b_p_perm": b_["p_perm"],
            "b_blok": b_["blok"], "c_trend": c_["durum"], "c_sayi": c_["sayi"], "d_gecikme": d_d, "d_sayi": d_s,
            "e_esik": e_d, "e_sayi": e_s, "f_uyarilar": "; ".join(uy_r), "f_kritik": "evet" if kr_r else "hayır",
            "guven": gv, "gerekce": gr, "kural_surumu": KURAL_SURUMU})
    return pd.DataFrame(satirlar, columns=SUTUNLAR)


def l4_karnesi(paket: Path, tekrar: int = TEKRAR, temel: int = TOHUM,
               ciftler: tuple[Cift, ...] = CIFTLER) -> pd.DataFrame:
    """``<paket>/L4_iliski/ciftler.csv`` satırlarının hepsi için karne."""
    paket = Path(paket)
    ref = pd.read_csv(paket / "L4_iliski" / "ciftler.csv", dtype={"bolge_kodu": str}, encoding="utf-8-sig")
    parca = []
    for c in ciftler:
        ana = ref[ref["cift_no"] == c.no]
        f1, f2 = (paket / "L1_kup" / f"{d}__{u}.nc" for d, u in ((c.d1, c.u1), (c.d2, c.u2)))
        if ana.empty or not (f1.exists() and f2.exists()):
            continue
        iller = bool((ana["bolge_turu"] == "il").any())      # ana satırlarla aynı kapsam
        parca.append(cift_karnesi(c, _l1(paket, c.d1, c.u1), _l1(paket, c.d2, c.u2), ana, paket,
                                  iller=iller, tekrar=tekrar, temel=temel))
        print(f"  ilişki karnesi çift {c.no}: {len(ana)} satır")
    return pd.concat(parca, ignore_index=True)
