"""Tek çift ilişki komutu: istenen iki değişkenin bir bölgede birlikte değişip değişmediği.

    python -m physics.iliski --x sicaklik_2m --y kar_ortusu --bolge Erzurum --mevsim kis --beklenen -
    python -m physics.iliski --x yagis --y ndvi --bolge tum_iller --mevsim ilkbahar --gecikme 1 --beklenen + --kaydet
    python -m physics.iliski --x no2 --y ruzgar_hizi --bolge Ankara --mevsim kis --json

Yöntem L4 ile aynıdır (Kişi 3; ``physics.tablo.cift_tablosu``): bölgenin cos(enlem) ağırlıklı alan
ortalaması → mevsim döngüsü dışarıda kalan seri (yılda bir mevsim değeri ya da aylık anomali) →
iki seriden de doğrusal trend çıkarılır → Pearson r → Bretherton etkin n ile p → etiket.
``tum_iller`` seçilince 81 il üzerinde BH-FDR (α = 0,10); tek bölge/il için p < 0,05.
Ayrıca trend çıkarılmadan hesaplanan "ham r" yanında verilir: ikisi arasındaki büyük fark, iki
serinin aynı dönemde trendli olmasından doğan sahte korelasyonun işaretidir.

Sonuç bir **ilişkidir**; nedensellik iddiası taşımaz. Yalnız yerel L1 paketi okunur (indirme yok).
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from physics.ciftler import (AYAR_DOSYASI, GRACE, KAR, TUM_MEVSIMLER, Cift, ayar_oku,
                             beklenen_kodu, seri_adi)
from physics.iliski import ALFA, ALFA_FDR
from physics.tablo import EK_SUTUNLAR, SUTUNLAR, bolge_listesi, cift_tablosu, csv_yaz

OZEL = ("turkiye", "tum_iller", "tum_bolgeler")
BUYUK_FARK = 0.3     # |ham r − trendsiz r| bundan büyükse ortak trend uyarısı
UYARI_ATTRS = ("bilinen_sorunlar", "trend_uyarisi")


class SecimHatasi(ValueError):
    """Bilinmeyen değişken / ürün / bölge: mesaj mevcut seçenekleri listeler."""


# ---------------------------------------------------------------- seçim
def paket_koku(surum: str = "v0.1", paket: Path | None = None) -> Path:
    """Analiz paketi kökü (varsayılan ``outputs/trend-dedektifi-turkiye-<surum>``)."""
    if paket is not None:
        return Path(paket)
    from data.export import OUTPUTS_DIR
    return OUTPUTS_DIR / f"trend-dedektifi-turkiye-{surum}"


def l1_secenekleri(paket: Path) -> dict[str, list[str]]:
    """``{degisken: [urun, …]}`` — ``<paket>/L1_kup/*.nc`` dosya adlarından (zamansız sabit alanlar,
    ör. rakım, hariç)."""
    from data.export import KADEME_DISI
    out: dict[str, list[str]] = {}
    for f in sorted((Path(paket) / "L1_kup").glob("*__*.nc")):
        d, u = f.stem.split("__", 1)
        if d not in KADEME_DISI:
            out.setdefault(d, []).append(u)
    return out


def _oneri(ad: str, secenekler) -> str:
    yakin = difflib.get_close_matches(ad, list(secenekler), n=3, cutoff=0.5)
    return f" Bunu mu demek istediniz: {', '.join(yakin)}?" if yakin else ""


def urun_sec(degisken: str, urun: str | None, secenekler: dict[str, list[str]],
             oncelik: dict[str, list[str]]) -> tuple[str, str]:
    """Ürünü doğrular ya da seçer. Döndürür: ``(urun, gerekce)``.

    Ürün verilmezse sıra: ciftler.yaml ``urun_onceligi`` (Kademe 1 ana ürünü önce), sonra Kademe 1
    listesindeki ürünler, sonra alfabetik.
    """
    if degisken not in secenekler:
        raise SecimHatasi(f"Bilinmeyen değişken: '{degisken}'.{_oneri(degisken, secenekler)}\n"
                          f"Mevcut değişkenler: {', '.join(sorted(secenekler))}")
    var = secenekler[degisken]
    if urun:
        if urun not in var:
            raise SecimHatasi(f"'{degisken}' için '{urun}' ürünü yok. Mevcut ürünler: {', '.join(var)}")
        return urun, "kullanıcı seçti"
    if len(var) == 1:
        return var[0], "tek ürün"
    from data.export import KADEME_1
    sira = [u for u in oncelik.get(degisken, []) if u in var]
    sira += sorted(u for u in var if (degisken, u) in KADEME_1 and u not in sira)
    sira += sorted(u for u in var if u not in sira)
    return sira[0], f"Kademe 1 öncelikli ürün (seçenekler: {', '.join(sira)})"


_TR_ALFABE = "aâbcçdefgğhıiîjklmnoöprsştuûüvyz"


def _tr_sira(ad: str) -> list[int]:
    """Türkçe alfabe sırası için anahtar (Ağrı, Aydın'dan önce; Çorum, Ç ile)."""
    s = ad.replace("I", "ı").replace("İ", "i").lower()
    return [_TR_ALFABE.index(ch) if ch in _TR_ALFABE else 100 + ord(ch) for ch in s]


def bolge_coz(ad: str) -> tuple[str, list[str], bool]:
    """Bölge girdisi → ``(etiket, [anahtar, …], fdr)``.

    ``turkiye`` · ``tum_iller`` (81 il, FDR) · ``tum_bolgeler`` (7 bölge + Türkiye) · il adı ya da
    plaka (``Elazığ``, ``elazig``, ``23``) · bölge adı (``Doğu Anadolu``, ``dogu_anadolu``).
    """
    from data.regions import normalize_name
    n = normalize_name(ad)
    liste = bolge_listesi(iller=True)
    if n == "turkiye":
        return "turkiye", ["turkiye"], False  # (anahtar, [anahtarlar], fdr)
    if n == "tum_iller":
        return "tum_iller", [b["anahtar"] for b in liste if b["bolge_turu"] == "il"], True
    if n == "tum_bolgeler":
        return "tum_bolgeler", [b["anahtar"] for b in liste if b["bolge_turu"] != "il"], False
    adlar = {}
    for b in liste:
        anahtar = b["anahtar"].split(":")[-1]
        for k in {normalize_name(b["bolge_adi"]), anahtar, normalize_name(b["bolge_adi"]).removesuffix("_bolgesi")}:
            adlar[k] = b
        if b["bolge_turu"] == "il":
            adlar[str(int(b["bolge_kodu"]))] = adlar[b["bolge_kodu"]] = b
    if n in adlar or n.removesuffix("_bolgesi") in adlar:
        b = adlar.get(n) or adlar[n.removesuffix("_bolgesi")]
        return b["anahtar"].split(":")[-1], [b["anahtar"]], False
    il_adlari = sorted((b["bolge_adi"] for b in liste if b["bolge_turu"] == "il"), key=_tr_sira)
    bolgeler = [b["bolge_adi"] for b in liste if b["bolge_turu"] == "bolge"]
    raise SecimHatasi(f"Bilinmeyen bölge: '{ad}'.{_oneri(n, adlar)}\n"
                      f"Seçenekler: {', '.join(OZEL)}; bölgeler: {', '.join(bolgeler)};\n"
                      f"iller ({len(il_adlari)}): {', '.join(il_adlari)}")


def gecici_cift(x: str, ux: str, y: str, uy: str, mevsim: str, gecikme: int,
                beklenen: int, ciftler: tuple[Cift, ...]) -> tuple[Cift, Cift | None]:
    """Komut satırı seçiminden ``Cift``. Aynı x/y/ürün/mevsim ciftler.yaml'da varsa o çiftin ayarları
    (kar maskesi, aylar, notlar, numara) devralınır; beklenen yön her zaman komuttan gelir."""
    for c in ciftler:
        if (c.d1, c.u1, c.d2, c.u2, c.mevsim) == (x, ux, y, uy, mevsim) and gecikme in c.gecikmeler:
            return replace(c, beklenen=beklenen, gecikmeler=(gecikme,)), c
    harita = GRACE not in (x, y)       # GRACE il ölçeğinde anlamlı değil (çift 4 kuralı)
    kar = 10.0 if (KAR in (x, y) and mevsim == "kis") else None
    return Cift(no=0, d1=x, u1=ux, d2=y, u2=uy, seri=seri_adi(mevsim), beklenen=beklenen, kademe=1,
                gecikmeler=(gecikme,), harita=harita, mevsim=mevsim,
                not_=("Yalnız kış ortalaması kar örtüsü ≥ %10 olan hücreler." if kar else ""),
                kar_maskesi_esik=kar), None


def _l1_ac(paket: Path, degisken: str, urun: str) -> xr.DataArray:
    with xr.open_dataset(Path(paket) / "L1_kup" / f"{degisken}__{urun}.nc") as ds:
        da = ds[degisken] if degisken in ds else ds[list(ds.data_vars)[0]]
        da = da.load()
        da.attrs = {**ds.attrs, **da.attrs}
    return da


def uyarilar(a: xr.DataArray, b: xr.DataArray, x: str, ux: str, y: str, uy: str,
             df: pd.DataFrame) -> list[str]:
    """L1 dosyalarındaki bilinen sorunlar / trend uyarıları, Kademe 2 ve ortak trend uyarısı."""
    out = []
    for da, d, u in ((a, x, ux), (b, y, uy)):
        for k in UYARI_ATTRS:
            if da.attrs.get(k):
                out.append(f"{d} ({u}) {k}: {da.attrs[k]}")
        if str(da.attrs.get("dogrulanmadi", "")).lower() == "evet":
            out.append(f"{d} ({u}): Kademe 2 ürün, bağımsız doğrulaması yapılmadı.")
    out += ortak_trend_uyarilari(df)
    return out


def ortak_trend_uyarilari(df: pd.DataFrame, esik: float = BUYUK_FARK) -> list[str]:
    """Ham r ile trendi çıkarılmış r arasındaki farkı |Δr| > ``esik`` olan satırlar için uyarı.

    |ham r| > |r|: iki serinin aynı dönemdeki trendi ilişkiyi **şişiriyor** (sahte korelasyon).
    |ham r| < |r|: zıt yönlü trendler yıldan yıla ilişkiyi **gizliyor**.
    """
    d = df[(df["r_ham"] - df["r"]).abs() > esik]
    out = []
    for tur, sec, aciklama in (
            ("şişiriyor", d["r_ham"].abs() > d["r"].abs(),
             "ham korelasyonun bir kısmı iki serinin aynı dönemde trendli olmasından geliyor (sahte korelasyon)"),
            ("gizliyor", d["r_ham"].abs() <= d["r"].abs(),
             "zıt yönlü trendler yıldan yıla birlikte değişimi örtüyor")):
        s = d[sec]
        if len(s):
            ornek = ", ".join(f"{r.bolge_adi} (ham {r.r_ham:+.2f} → trendsiz {r.r:+.2f})"
                              for r in s.head(5).itertuples())
            out.append(f"Ortak trend ilişkiyi {tur} ({len(s)} satır, |Δr| > {esik}): {aciklama}. "
                       f"Örn. {ornek}{', …' if len(s) > 5 else ''}. Yorum için trendi çıkarılmış r kullanılır.")
    return out


# ---------------------------------------------------------------- hesap
def hesapla(x: str, y: str, bolge: str, mevsim: str, urun_x: str | None = None,
            urun_y: str | None = None, gecikme: int = 0, beklenen=None, surum: str = "v0.1",
            paket: Path | None = None, ayar: Path = AYAR_DOSYASI) -> dict:
    """Seçimi doğrular, iki L1 dosyasını okur ve L4 yöntemiyle tabloyu üretir.

    Döndürür: ``{"secim": {...}, "tablo": DataFrame (SUTUNLAR + EK_SUTUNLAR + yon), "uyarilar": [...],
    "yaml_cifti": int | None, "sure_sn": float}``. Seçim hatasında ``SecimHatasi``.
    """
    t0 = time.perf_counter()
    if mevsim not in TUM_MEVSIMLER:
        raise SecimHatasi(f"Bilinmeyen mevsim: '{mevsim}'. Seçenekler: {', '.join(TUM_MEVSIMLER)}")
    if gecikme < 0:
        raise SecimHatasi("Gecikme negatif olamaz (x, y'den kaç ay önce).")
    if mevsim == "mevsimlik" and gecikme:
        raise SecimHatasi("mevsimlik seride gecikme desteklenmez; aylik ya da bir mevsim seçin.")
    bek = 0 if beklenen in (None, "") else beklenen_kodu(beklenen)
    paket = paket_koku(surum, paket)
    if not (paket / "L1_kup").exists():
        raise SecimHatasi(f"L1 paketi yok: {paket / 'L1_kup'}")
    ayarlar = ayar_oku(ayar)
    secenekler = l1_secenekleri(paket)
    ux, gx = urun_sec(x, urun_x, secenekler, ayarlar["urun_onceligi"])
    uy, gy = urun_sec(y, urun_y, secenekler, ayarlar["urun_onceligi"])
    if (x, ux) == (y, uy):
        raise SecimHatasi("x ve y aynı dosya; iki farklı değişken ya da ürün seçin.")
    bolge_ad, anahtarlar, fdr = bolge_coz(bolge)
    adlar = {b["anahtar"]: b["bolge_adi"] for b in bolge_listesi(iller=True)}
    bolge_adi = adlar[anahtarlar[0]] if len(anahtarlar) == 1 else {
        "tum_iller": "81 il", "tum_bolgeler": "7 bölge + Türkiye"}[bolge_ad]
    c, eslesen = gecici_cift(x, ux, y, uy, mevsim, gecikme, bek, ayarlar["ciftler"])
    if GRACE in (x, y) and any(k.startswith("il:") for k in anahtarlar):
        raise SecimHatasi("GRACE (toplam_su_depolama) il ölçeğinde hesaplanmaz: çözünürlüğü ~300 km. "
                          "Bir bölge, 'tum_bolgeler' ya da 'turkiye' seçin.")
    a, b = _l1_ac(paket, x, ux), _l1_ac(paket, y, uy)
    df = cift_tablosu(c, a, b, iller=True, bolgeler=anahtarlar, fdr=fdr, ek_sutunlar=True)
    df["yon"] = np.select([df["r"] > 0, df["r"] < 0], ["pozitif", "negatif"], default="")
    return {"secim": {"x": x, "urun_x": ux, "urun_x_gerekce": gx, "y": y, "urun_y": uy,
                      "urun_y_gerekce": gy, "bolge": bolge_ad, "bolge_adi": bolge_adi, "mevsim": mevsim, "seri": c.seri,
                      "gecikme_ay": gecikme, "beklenen": c.beklenen_yon if bek else "",
                      "fdr": fdr, "esik": f"p_fdr ≤ {ALFA_FDR}" if fdr else f"p < {ALFA}",
                      "paket": str(paket)},
            "tablo": df, "uyarilar": uyarilar(a, b, x, ux, y, uy, df),
            "yaml_cifti": eslesen.no if eslesen else None,
            "sure_sn": round(time.perf_counter() - t0, 2)}


# ---------------------------------------------------------------- çıktı
def _f(v, d=2) -> str:
    return "" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.{d}f}"


def _p(v) -> str:
    if v is None or not np.isfinite(v):
        return ""
    return f"{v:.3f}" if v >= 0.001 else f"{v:.1e}"


def ekran_tablosu(df: pd.DataFrame, fdr: bool, en_cok: int = 15) -> pd.DataFrame:
    """Okunur kısa tablo (Türkçe sütun adları)."""
    d = df[df["n"].fillna(0) > 0].copy()
    if fdr:
        d = d.sort_values("p")
    out = pd.DataFrame({
        "bölge": d["bolge_adi"], "dönem": d["donem"], "n": d["n"].astype("Int64"),
        "etkin n": d["etkin_n"].map(lambda v: _f(v, 1)),
        "ham r": d["r_ham"].map(_f), "r (trendsiz)": d["r"].map(_f),
        "p": d["p"].map(_p), **({"p_fdr": d["p_fdr"].map(_p)} if fdr else {}),
        "yön": d["yon"], "etiket": np.where(d["r"].isna(), "hesaplanamadı", d["etiket"].replace("", "anlamlı (beklenti yok)"))})
    return out.head(en_cok) if fdr else out


def yazdir(sonuc: dict) -> None:
    s, df = sonuc["secim"], sonuc["tablo"]
    print(f"İLİŞKİ: {s['x']} ({s['urun_x']}) ~ {s['y']} ({s['urun_y']}) · {s['bolge_adi']} · {s['mevsim']}"
          + (f" · x {s['gecikme_ay']} ay önce" if s["gecikme_ay"] else ""))
    for k in ("x", "y"):
        if s[f"urun_{k}_gerekce"] != "kullanıcı seçti":
            print(f"  ürün ({k}): {s[f'urun_{k}']} — {s[f'urun_{k}_gerekce']}")
    print(f"  seri: {s['seri']} · trend çıkarıldı · anlamlılık: {s['esik']}"
          + (" (81 il, Benjamini-Hochberg)" if s["fdr"] else "")
          + f" · beklenen yön: {s['beklenen'] or 'verilmedi (yalnız r, p ve yön)'}")
    if sonuc["yaml_cifti"]:
        print(f"  ciftler.yaml çift {sonuc['yaml_cifti']} ayarları kullanıldı (aynı yöntem, aynı kapsam).")
    hesap = df[df["n"].fillna(0) > 0]
    bos = df[df["n"].fillna(0) == 0]
    print()
    if len(hesap):
        print(ekran_tablosu(df, s["fdr"]).to_string(index=False))
    if s["fdr"] and len(hesap):
        lab = np.where(hesap["r"].isna(), "hesaplanamadı",
                       np.where(hesap["etiket"] == "", "anlamlı (beklenti yok)", hesap["etiket"]))
        say = pd.Series(lab).value_counts()
        print(f"\n  {len(hesap)} il: " + " · ".join(f"{k} {v}" for k, v in say.items())
              + (f" (ilk {min(15, len(hesap))} il p'ye göre sıralı; tamamı --kaydet ile)" if len(hesap) > 15 else ""))
    if len(bos):
        print(f"  hesaplanamadı: {', '.join(bos['bolge_adi'])} — {bos['not'].iloc[0]}")
    for u in sonuc["uyarilar"]:
        print(f"  ⚠ {u}")
    print("  Not: bu bir ilişkidir, nedensellik göstermez.")
    print(f"  süre: {sonuc['sure_sn']:.1f} sn")


def kayit_yolu(sonuc: dict) -> Path:
    """``<paket>/L4_iliski/ozel/<x>__<y>__<bolge>__<mevsim>[__gecikmeN].csv``"""
    s = sonuc["secim"]
    ek = f"__gecikme{s['gecikme_ay']}" if s["gecikme_ay"] else ""
    return Path(s["paket"]) / "L4_iliski" / "ozel" / f"{s['x']}__{s['y']}__{s['bolge']}__{s['mevsim']}{ek}.csv"


def kaydet(sonuc: dict) -> Path:
    """Sözleşme 2.3 sütunları + ``EK_SUTUNLAR`` + ``yon`` + ``uyari`` (BOM'lu UTF-8)."""
    df = sonuc["tablo"].copy()
    df["uyari"] = " | ".join(sonuc["uyarilar"])
    return csv_yaz(df[SUTUNLAR + EK_SUTUNLAR + ["yon", "uyari"]], kayit_yolu(sonuc))


def json_metni(sonuc: dict) -> str:
    satirlar = json.loads(sonuc["tablo"].to_json(orient="records", force_ascii=False))
    return json.dumps({"secim": sonuc["secim"], "yaml_cifti": sonuc["yaml_cifti"],
                       "uyarilar": sonuc["uyarilar"], "satirlar": satirlar,
                       "sure_sn": sonuc["sure_sn"]}, ensure_ascii=False, indent=1)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m physics.iliski",
                                 description="İki değişkenin bir bölgede birlikte değişimi (ilişki, nedensellik değil).")
    ap.add_argument("--x", required=True, help="birinci değişken (ör. sicaklik_2m)")
    ap.add_argument("--urun-x", default=None, help="x ürünü (verilmezse Kademe 1 öncelikli)")
    ap.add_argument("--y", required=True, help="ikinci değişken (ör. kar_ortusu)")
    ap.add_argument("--urun-y", default=None, help="y ürünü")
    ap.add_argument("--bolge", required=True,
                    help="il adı/plaka, bölge adı, 'turkiye', 'tum_iller' ya da 'tum_bolgeler'")
    ap.add_argument("--mevsim", required=True, choices=TUM_MEVSIMLER)
    ap.add_argument("--gecikme", type=int, default=0, help="x, y'den kaç ay önce (varsayılan 0)")
    ap.add_argument("--beklenen", default=None, help="beklenen yön: + / - / 0 (isteğe bağlı)")
    ap.add_argument("--kaydet", action="store_true", help="L4_iliski/ozel/ altına CSV yaz")
    ap.add_argument("--json", action="store_true", help="makine okunur JSON çıktı")
    ap.add_argument("--surum", default="v0.1")
    ap.add_argument("--paket", type=Path, default=None, help="paket kökü (varsayılan outputs/…-<surum>)")
    a = ap.parse_args(argv)
    try:
        sonuc = hesapla(a.x, a.y, a.bolge, a.mevsim, a.urun_x, a.urun_y, a.gecikme, a.beklenen,
                        a.surum, a.paket)
    except (SecimHatasi, ValueError) as e:
        print(f"HATA: {e}", file=sys.stderr)
        raise SystemExit(2) from None
    yol = kaydet(sonuc) if a.kaydet else None
    if a.json:
        print(json_metni(sonuc))
    else:
        yazdir(sonuc)
        if yol:
            print(f"  kaydedildi: {yol}")
