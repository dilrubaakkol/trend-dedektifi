"""L4 değişken çiftleri ve her çiftin serilerinin hazırlanması (docs/sozlesmeler.md 2.3).

Sade anlatım: çiftlerin tanımı ``physics/ciftler.yaml`` dosyasındadır (hangi iki değişken, hangi
mevsim, hangi gecikme, fiziğin beklediği yön, çifte özel notlar). Bu modül o dosyayı okuyup ``Cift``
nesnelerine çevirir; ``cift_serileri`` iki aylık girdiden ``iliski.iliski_1d``'nin istediği hizalı
serileri verir. Hücre küpü (time, lat, lon) de tek seri (time) de olur.
Kişi 3'ün L4 yöntemi; çift tanımları koddan ayar dosyasına taşındı (genel ilişki motoru).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import yaml

from physics import seriler as S

AYAR_DOSYASI = Path(__file__).with_name("ciftler.yaml")
MEVSIMLER = ("yillik", "kis", "ilkbahar", "yaz", "sonbahar")   # yılda bir değer
TUM_MEVSIMLER = MEVSIMLER + ("mevsimlik", "aylik")
# sözleşmedeki `seri` değeri (ciftler.csv ve .nc attrs)
SERI_ADI = {"kis": "kis_DJF", "ilkbahar": "ilkbahar_MAM", "yaz": "yaz_JJA", "sonbahar": "sonbahar_SON",
            "yillik": "yillik", "mevsimlik": "mevsim_anomali", "aylik": "aylik_anomali"}
NIS_EYL = (4, 5, 6, 7, 8, 9)
BEKLENEN = {"+": 1, "-": -1, "−": -1, "0": 0, 1: 1, -1: -1, 0: 0}
ETIKET_ADLARI = ("beklenen_yonde", "ters_yonde", "anlamsiz")

# GRACE yıllık ortalaması için en az ay sayısı. GRACE'te büyük boşluk (2017–2018) dışında da
# dağınık eksik aylar var; 12 ay şartı birçok yılı gereksiz yere atar. Büyük boşluk yılları
# (≤ 8 ay) yine atılır. Değişkene bağlı kuraldır (çifte değil).
GRACE_MIN_AY = 9
GRACE = "toplam_su_depolama"
KAR = "kar_ortusu"
KAR_ESIGI = 10.0  # %, ciftler.yaml'da kar_maskesi_esik verilmezse ve tek çift komutunda


@dataclass(frozen=True)
class Cift:
    no: int
    d1: str
    u1: str
    d2: str
    u2: str
    seri: str            # sözleşmedeki `seri` değeri
    beklenen: int        # +1 aynı yönde, −1 zıt yönde, 0 beklenti yok
    kademe: int
    gecikmeler: tuple = (0,)
    harita: bool = True  # hücre haritası üretilir mi (çift 4: hayır)
    not_: str = ""
    ad: str = ""
    not_ulke: str = ""                  # Türkiye dışı paketlerde not_ yerine (il/bölge yok)
    mevsim: str = ""
    aylar: tuple | None = None          # yalnız aylik: y'nin kullanılan ayları
    fiziksel_gerekce: str = ""
    kar_maskesi_esik: float | None = None
    etiket_notlari: dict = field(default_factory=dict, hash=False, compare=False)
    kalite_kontrolu: bool = False
    rejime_bagli: bool = False          # sapma haritası: kurak yerdeki ters sonuç rejimle açıklanır
    rejim_gerekcesi: str = ""

    @property
    def kod(self) -> str:
        """Sözleşmedeki `cift` değeri: ``<d1>__<u1>~<d2>__<u2>``."""
        return f"{self.d1}__{self.u1}~{self.d2}__{self.u2}"

    @property
    def beklenen_yon(self) -> str:
        """``+`` / ``-`` / ``0`` (ciftler.csv `beklenen_yon`)."""
        return {1: "+", -1: "-"}.get(self.beklenen, "0")

    @property
    def kar_tarafi(self) -> str | None:
        """Kar maskesi hangi girdiden hesaplanır: ``"x"``, ``"y"`` ya da maske yoksa None."""
        if self.kar_maskesi_esik is None:
            return None
        return "y" if self.d2 == KAR else "x"

    def harita_dosyasi(self, gecikme: int = 0) -> str:
        """``iliski__<d1>__<d2>[__gecikmeN].nc``"""
        ek = f"__gecikme{gecikme}" if len(self.gecikmeler) > 1 else ""
        return f"iliski__{self.d1}__{self.d2}{ek}.nc"


def seri_adi(mevsim: str, aylar=None) -> str:
    """Sözleşmedeki `seri` adı: ``kis`` → ``kis_DJF``; aylık + Nisan–Eylül → ``aylik_anomali_nis_eyl``."""
    if mevsim not in SERI_ADI:
        raise ValueError(f"bilinmeyen mevsim: {mevsim!r}; seçenekler: {', '.join(TUM_MEVSIMLER)}")
    s = SERI_ADI[mevsim]
    if mevsim == "aylik" and aylar:
        aylar = tuple(int(a) for a in aylar)
        if aylar != tuple(range(1, 13)):
            s += "_nis_eyl" if aylar == NIS_EYL else "_" + "-".join(map(str, aylar))
    return s


def beklenen_kodu(deger) -> int:
    """``"+"`` / ``"-"`` / ``"−"`` / ``"0"`` (ya da 1, −1, 0) → +1 / −1 / 0."""
    k = deger.strip() if isinstance(deger, str) else deger
    if k not in BEKLENEN:
        raise ValueError(f"beklenen yön '+', '-' ya da '0' olmalı (verilen: {deger!r})")
    return BEKLENEN[k]


def _cift_kur(d: dict) -> Cift:
    """ciftler.yaml'daki bir maddeden ``Cift``; eksik ya da tutarsız alanda anlaşılır ValueError."""
    d = dict(d)
    if "no" not in d and False in d:   # YAML 1.1: tırnaksız `no:` anahtarı boolean False okunur
        d["no"] = d.pop(False)
    no = d.get("no")
    yer = f"ciftler.yaml, çift {no}"
    for alan in ("no", "x", "y", "mevsim", "beklenen", "kademe"):
        if alan not in d:
            raise ValueError(f"{yer}: '{alan}' alanı eksik")
    for taraf in ("x", "y"):
        if not isinstance(d[taraf], dict) or not {"degisken", "urun"} <= set(d[taraf]):
            raise ValueError(f"{yer}: '{taraf}' alanı {{degisken, urun}} olmalı")
    mevsim = str(d["mevsim"])
    if mevsim not in TUM_MEVSIMLER:
        raise ValueError(f"{yer}: bilinmeyen mevsim {mevsim!r}; seçenekler: {', '.join(TUM_MEVSIMLER)}")
    aylar = tuple(int(a) for a in d["aylar"]) if d.get("aylar") else None
    if aylar and mevsim != "aylik":
        raise ValueError(f"{yer}: 'aylar' yalnız mevsim: aylik ile kullanılır")
    g = d.get("gecikme_ay", 0)
    gecikmeler = tuple(int(x) for x in (g if isinstance(g, (list, tuple)) else [g]))
    if any(x < 0 for x in gecikmeler):
        raise ValueError(f"{yer}: gecikme_ay negatif olamaz")
    if mevsim == "mevsimlik" and gecikmeler != (0,):
        raise ValueError(f"{yer}: mevsimlik seride gecikme desteklenmez")
    beklenen = beklenen_kodu(d["beklenen"])
    harita = bool(d.get("harita", True))
    if beklenen == 0 and harita:
        raise ValueError(f"{yer}: beklenen '0' olan çiftte harita: false olmalı (etiket haritası yön ister)")
    esik = d.get("kar_maskesi_esik")
    x, y = d["x"], d["y"]
    if esik is not None and KAR not in (x["degisken"], y["degisken"]):
        raise ValueError(f"{yer}: kar_maskesi_esik için x ya da y '{KAR}' olmalı")
    rejime_bagli = bool(d.get("rejime_bagli", False))
    if rejime_bagli and not str(d.get("rejim_gerekcesi") or "").strip():
        raise ValueError(f"{yer}: rejime_bagli: true iken rejim_gerekcesi yazılmalı")
    notlar = dict(d.get("etiket_notlari") or {})
    if set(notlar) - set(ETIKET_ADLARI):
        raise ValueError(f"{yer}: etiket_notlari anahtarları {ETIKET_ADLARI} olmalı")
    return Cift(no=int(no), d1=str(x["degisken"]), u1=str(x["urun"]), d2=str(y["degisken"]),
                u2=str(y["urun"]), seri=seri_adi(mevsim, aylar), beklenen=beklenen,
                kademe=int(d["kademe"]), gecikmeler=gecikmeler, harita=harita,
                not_=str(d.get("not") or ""), not_ulke=str(d.get("not_ulke") or ""), ad=str(d.get("ad") or ""), mevsim=mevsim, aylar=aylar,
                fiziksel_gerekce=str(d.get("fiziksel_gerekce") or ""),
                kar_maskesi_esik=None if esik is None else float(esik), etiket_notlari=notlar,
                kalite_kontrolu=bool(d.get("kalite_kontrolu", False)), rejime_bagli=rejime_bagli,
                rejim_gerekcesi=str(d.get("rejim_gerekcesi") or "").strip())


def ayar_oku(yol: str | Path = AYAR_DOSYASI) -> dict:
    """ciftler.yaml'ı okur: ``{"ciftler": tuple[Cift], "urun_onceligi": {...}, "rejim": {...}}``."""
    ham = yaml.safe_load(Path(yol).read_text(encoding="utf-8")) or {}
    ciftler = tuple(_cift_kur(d) for d in ham.get("ciftler") or [])
    if not ciftler:
        raise ValueError(f"{yol}: hiç çift tanımlı değil")
    nolar = [c.no for c in ciftler]
    if len(set(nolar)) != len(nolar):
        raise ValueError(f"{yol}: çift numaraları benzersiz olmalı ({nolar})")
    oncelik = {str(k): [str(u) for u in v] for k, v in (ham.get("urun_onceligi") or {}).items()}
    rejim = dict(ham.get("rejim") or {})
    if rejim and not 0 < float(rejim.get("su_sinirli_esik", 0)) < 10:
        raise ValueError(f"{yol}: rejim.su_sinirli_esik pozitif bir sayı olmalı")
    return {"ciftler": ciftler, "urun_onceligi": oncelik, "rejim": rejim}


def ciftleri_yukle(yol: str | Path = AYAR_DOSYASI) -> tuple[Cift, ...]:
    """ciftler.yaml'daki çiftler (numara sırasıyla dosyadaki sırada)."""
    return ayar_oku(yol)["ciftler"]


CIFTLER = ciftleri_yukle()
CIFT = {c.no: c for c in CIFTLER}


def _ondalik_yil(zaman) -> np.ndarray:
    t = pd.DatetimeIndex(zaman)
    return (t.year + (t.month - 1) / 12.0).to_numpy(float)


def _hizala(x: xr.DataArray, y: xr.DataArray, boyut: str):
    x, y = xr.align(x, y, join="inner")
    if x.sizes.get(boyut, 0) == 0:
        raise ValueError("iki değişkenin ortak dönemi yok")
    for b in ("lat", "lon"):
        if b in x.dims and x.sizes[b] == 0:
            raise ValueError(f"iki değişkenin '{b}' koordinatları uyuşmuyor (aynı ızgara olmalı)")
    return x, y


def _donem(t: np.ndarray, x: xr.DataArray, y: xr.DataArray, boyut: str) -> str:
    """İki serinin birlikte geçerli olduğu ilk ve son zaman adımı (ör. ``2002-2025``)."""
    ortak = (x.notnull() & y.notnull())
    diger = [d for d in ortak.dims if d != boyut]
    if diger:
        ortak = ortak.any(diger)
    ok = ortak.values
    if not ok.any():
        return ""
    a, b = t[ok][0], t[ok][-1]
    if boyut == "yil":
        return f"{int(a)}-{int(b)}"
    if boyut == "t":  # mevsim anomalisi: ondalık yıl
        return f"{int(np.floor(a))}-{int(np.floor(b))}"
    return f"{pd.Timestamp(a):%Y-%m}…{pd.Timestamp(b):%Y-%m}"


def _aylik_kaydir(a: xr.DataArray, b: xr.DataArray, gecikme: int) -> xr.DataArray:
    """x'i ``gecikme`` ay ileri kaydırır (x, y'den önce gelir); zaman ekseni kesintisiz olmalı."""
    a, _ = xr.align(a, b, join="inner")
    t = pd.DatetimeIndex(a["time"].values)
    if len(t) > 1 and len(pd.date_range(t[0], t[-1], freq="MS")) != len(t):
        raise ValueError("gecikme için zaman ekseni kesintisiz aylık olmalı")
    return a.shift(time=gecikme)


def cift_serileri(cift: Cift | int, a: xr.DataArray, b: xr.DataArray) -> list[dict]:
    """Bir çiftin iki aylık girdisinden hizalı seriler.

    Parametreler
    ----------
    cift : ``Cift`` ya da çift numarası (ciftler.yaml).
    a, b : aylık DataArray'ler — sırasıyla ``cift.d1`` (x) ve ``cift.d2`` (y) (time[, lat, lon]).

    Döndürür: her gecikme için bir sözlük
    ``{"gecikme", "x", "y", "t", "boyut", "donem"}``. ``x``, ``y`` aynı boyutlu DataArray'ler;
    zaman boyutu ``boyut`` adıyla (``yil``, ``t`` ya da ``time``) ilk sırada. ``t``: trend
    çıkarmak için sayısal zaman (yıl). Kar maskeli çiftte kapsam dışı hücreler NaN'dır.

    Seriler (mevsim döngüsü her durumda dışarıda kalır):
    - ``yillik``/``kis``/``ilkbahar``/``yaz``/``sonbahar``: yılda bir değer (birikimli değişkende
      toplam, ötekilerde ortalama). Gecikme > 0 ise x aylık seride önce kaydırılır.
    - ``mevsimlik``: dört mevsim art arda, her mevsimden kendi ortalaması çıkarılmış.
    - ``aylik``: 12 aylık klimatolojisi çıkarılmış aylık anomali; ``aylar`` ya da gecikme varsa
      ``seriler.gecikmeli`` ile y'nin seçili ayları x'in g ay önceki değeriyle eşlenir.
    """
    c = CIFT[cift] if isinstance(cift, int) else cift
    m = c.mevsim
    sonuc = []

    if m in MEVSIMLER:
        min_a = GRACE_MIN_AY if c.d1 == GRACE else None
        min_b = GRACE_MIN_AY if c.d2 == GRACE else None
        y = S.mevsim_serisi(b, m, toplam=S.toplam_mi(c.d2), min_ay=min_b)
        for g in c.gecikmeler:
            ag = a if g == 0 else _aylik_kaydir(a, b, g)
            x = S.mevsim_serisi(ag, m, toplam=S.toplam_mi(c.d1), min_ay=min_a)
            x, yy = _hizala(x, y, "yil")
            if c.kar_tarafi and "lat" in yy.dims:
                # kapsam: hizalanmış yıllardaki kış ortalaması kar örtüsü ≥ eşik
                if c.kar_tarafi == "y" and m == "kis":
                    kar = yy
                else:
                    kar = S.mevsim_serisi(b if c.kar_tarafi == "y" else a, "kis", toplam=False)
                    kar = kar.sel(yil=kar["yil"].isin(x["yil"]))
                maske = S.kar_maskesi(kar, c.kar_maskesi_esik)
                x, yy = x.where(maske), yy.where(maske)
            sonuc.append({"gecikme": g, "x": x, "y": yy, "t": x["yil"].values.astype(float),
                          "boyut": "yil"})

    elif m == "mevsimlik":
        x = S.mevsim_anomali(a, toplam=S.toplam_mi(c.d1))
        y = S.mevsim_anomali(b, toplam=S.toplam_mi(c.d2))
        x, y = _hizala(x, y, "t")
        sonuc.append({"gecikme": 0, "x": x, "y": y, "t": x["t"].values.astype(float), "boyut": "t"})

    elif m == "aylik":
        xa, ya = _hizala(S.aylik_anomali(a), S.aylik_anomali(b), "time")
        if c.aylar is None and c.gecikmeler == (0,):
            sonuc.append({"gecikme": 0, "x": xa, "y": ya, "t": _ondalik_yil(xa["time"].values),
                          "boyut": "time"})
        else:
            aylar = c.aylar or tuple(range(1, 13))
            for g in c.gecikmeler:
                x, y = S.gecikmeli(xa, ya, g, aylar=aylar)
                sonuc.append({"gecikme": g, "x": x, "y": y, "t": _ondalik_yil(x["time"].values),
                              "boyut": "time"})
    else:
        raise ValueError(f"bilinmeyen mevsim: {m}")

    for r in sonuc:
        r["x"] = r["x"].transpose(r["boyut"], ...)
        r["y"] = r["y"].transpose(r["boyut"], ...)
        r["donem"] = _donem(r["t"] if r["boyut"] != "time" else r["x"]["time"].values,
                            r["x"], r["y"], r["boyut"])
    return sonuc
