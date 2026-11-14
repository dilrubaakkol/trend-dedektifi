"""L4 tablosu: 81 il, 7 bölge ve Türkiye için 6 çiftin ilişkisi (KISI3_PLAN.md, Faz 4).

Sade anlatım: her bölgenin hücrelerinin alan ağırlıklı (cos enlem) ortalamasıyla bölgenin aylık
serisi çıkarılır, sonra Faz 1–2'deki hesap bu seriye uygulanır. Bir satır = bir çift × bir bölge
(× bir gecikme). İl satırlarında 81 il birden test edildiği için FDR (α = 0,10), bölge ve Türkiye
satırlarında p < 0,05 kullanılır.

Çıktı: ``L4_iliski/ciftler.csv`` (docs/sozlesmeler.md 2.3).
Bölge sınırları Kişi 1'in ``data.regions.subset`` fonksiyonundan gelir (hücre merkezi kuralı;
Kişi 2'nin L3 il tablosuyla aynı hücreler).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from physics import seriler as S
from physics.ciftler import CIFT, CIFTLER, Cift, cift_serileri
from physics.iliski import ALFA, ALFA_FDR, bh_fdr, etiket, etkin_n, gecikme1, iliski_1d, p_degeri

SUTUNLAR = [
    "cift_no", "cift", "degisken_1", "degisken_2", "seri", "gecikme_ay", "beklenen_yon",
    "bolge_turu", "bolge_kodu", "bolge_adi", "hucre_sayisi", "donem", "n",
    "r", "r1_1", "r1_2", "etkin_n", "p", "p_fdr", "anlamli", "etiket", "not",
    "urun_surumu", "veri_seti_doi", "lisans", "kademe", "dogrulanmadi", "doi_1", "doi_2",
]

# ek_sutunlar=True ile eklenen tanı sütunları (physics.iliski; ciftler.csv'ye yazılmaz)
EK_SUTUNLAR = ["r_ham", "p_ham", "egim_x_10yil", "egim_y_10yil"]

NOT_TERS = "İncelenmeli: veri sorunu ya da insan etkisi (sulama, baraj vb.) olabilir."
NOT_KALITE = "Kalite kontrolü beklenen güçlü ilişkiyi vermedi: veri sorunu olabilir."
# Çifte özel etiket notları (ör. çift 5'in su/enerji sınırı açıklaması) ciftler.yaml'dadır.


def bolge_listesi(iller: bool = True) -> list[dict]:
    """``[{bolge_turu, bolge_kodu, bolge_adi, anahtar}]``: 81 il (plakaya göre), 7 bölge, Türkiye."""
    from data.regions import _iller, list_regions  # Kişi 1
    out = []
    if iller:
        il = sorted(_iller().items(), key=lambda kv: int(kv[1]["plaka"]))
        out += [{"bolge_turu": "il", "bolge_kodu": f"{int(v['plaka']):02d}", "bolge_adi": v["ad"],
                 "anahtar": f"il:{k}"} for k, v in il]
    out += [{"bolge_turu": "bolge", "bolge_kodu": k, "bolge_adi": ad, "anahtar": f"bolge:{k}"}
            for k, ad in list_regions()["bolge"]]
    out.append({"bolge_turu": "turkiye", "bolge_kodu": "turkiye", "bolge_adi": "Türkiye",
                "anahtar": "turkiye"})
    return out


@lru_cache(maxsize=8)
def _maskeler(lat_t: tuple, lon_t: tuple, iller: bool) -> dict[str, np.ndarray]:
    """Her bölge için tam ızgarada boolean maske (``data.regions.subset`` ile)."""
    from data.regions import subset
    lat, lon = np.array(lat_t), np.array(lon_t)
    sablon = xr.DataArray(np.ones((lat.size, lon.size)), coords={"lat": lat, "lon": lon},
                          dims=("lat", "lon"), attrs={"domain": "land"})
    out = {}
    for b in bolge_listesi(iller):
        kes = subset(sablon, b["anahtar"])
        out[b["anahtar"]] = kes.notnull().reindex_like(sablon, fill_value=False).values
    return out


def bolge_maskeleri(lat, lon, iller: bool = True) -> dict[str, np.ndarray]:
    """``{anahtar: (lat, lon) boolean}`` — önbellekli."""
    r = lambda v: tuple(np.round(np.asarray(v, float), 6))  # noqa: E731
    return _maskeler(r(lat), r(lon), iller)


def _ortak_alanlar(c: Cift, a: xr.DataArray, b: xr.DataArray) -> dict:
    """Ortak alanlar (sözleşme 2, "ortak kurallar") — girdilerin L1 attrs'ından."""
    def al(ad):
        return a.attrs.get(ad) or b.attrs.get(ad) or ""
    kademe = max(c.kademe, int(a.attrs.get("kademe", 0) or 0), int(b.attrs.get("kademe", 0) or 0))
    dogr = kademe >= 2 or "evet" in (a.attrs.get("dogrulanmadi"), b.attrs.get("dogrulanmadi"))
    return {"urun_surumu": al("urun_surumu"), "veri_seti_doi": al("veri_seti_doi"),
            "lisans": al("lisans"), "kademe": kademe, "dogrulanmadi": "evet" if dogr else "",
            "doi_1": a.attrs.get("doi", ""), "doi_2": b.attrs.get("doi", "")}


def ham_iliski(x, y, t) -> dict:
    """Trendi ÇIKARILMADAN korelasyon (ortak trend tuzağını göstermek için) ve iki serinin eğimi.

    Aynı ortak adımlar ve aynı etkin n yöntemi (Bretherton) kullanılır; tek fark trend çıkarılmaz.
    Döndürür: ``{r_ham, p_ham, egim_x_10yil, egim_y_10yil}`` (eğim: birim / 10 yıl, EKK).
    """
    x, y, t = (np.asarray(v, float) for v in (x, y, t))
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(t)
    bos = {k: float("nan") for k in EK_SUTUNLAR}
    if ok.sum() < 8 or np.nanstd(x[ok]) == 0 or np.nanstd(y[ok]) == 0:
        return bos
    r = float(np.corrcoef(x[ok], y[ok])[0, 1])
    xa, ya = np.where(ok, x, np.nan), np.where(ok, y, np.nan)
    ne = etkin_n(int(ok.sum()), gecikme1(xa), gecikme1(ya))
    return {"r_ham": r, "p_ham": p_degeri(r, ne),
            "egim_x_10yil": float(np.polyfit(t[ok], x[ok], 1)[0] * 10),
            "egim_y_10yil": float(np.polyfit(t[ok], y[ok], 1)[0] * 10)}


def _not(c: Cift, et: str | None) -> str:
    """Satır notu: çiftin notu + etikete özel not (ciftler.yaml) ya da genel "incelenmeli" notu."""
    parca = [c.not_] if c.not_ else []
    if et in c.etiket_notlari:                    # ör. çift 5: yön kuraklığa bağlı (fiziksel)
        parca.append(c.etiket_notlari[et])
    elif et == "ters_yonde":
        parca.append(NOT_TERS)
    if c.kalite_kontrolu and et in ("ters_yonde", "anlamsiz"):
        parca.append(NOT_KALITE)
    return " ".join(parca)


def cift_tablosu(cift: Cift | int, a: xr.DataArray, b: xr.DataArray,
                 iller: bool = True, bolgeler: list[str] | None = None,
                 fdr: bool = True, ek_sutunlar: bool = False) -> pd.DataFrame:
    """Bir çiftin il, bölge ve Türkiye satırları.

    a, b : (time, lat, lon) aylık L1 küpleri (aynı ızgara) — sırasıyla ``cift.d1``, ``cift.d2``.
    iller : False ise il satırları atlanır. Haritasız çiftte (GRACE) il satırı hiç üretilmez.
    bolgeler : yalnız bu anahtarlar (``il:konya``, ``bolge:…``, ``turkiye``); None = hepsi.
    fdr : il satırlarında BH-FDR (α = 0,10). Tek il seçildiğinde (physics.iliski) False verilir;
        o zaman il satırı da bölge satırları gibi ``p < 0,05`` ile değerlendirilir.
    ek_sutunlar : True ise sona ``EK_SUTUNLAR`` (ham r, ham p, iki serinin eğimi) eklenir.
    """
    c = CIFT[cift] if isinstance(cift, int) else cift
    iller = iller and c.harita
    a, b = xr.align(a, b, join="inner")
    lat, lon = a["lat"].values, b["lon"].values
    maskeler = bolge_maskeleri(lat, lon, iller)

    # iki değişkenin de verisi olan hücreler; çift 1'de ayrıca kar kapsamı (kış ort. ≥ %10)
    gecerli = (a.notnull().any("time") & b.notnull().any("time")).values
    if c.kar_tarafi:
        kar_kis = S.mevsim_serisi(b if c.kar_tarafi == "y" else a, "kis", toplam=False)
        gecerli &= S.kar_maskesi(kar_kis, c.kar_maskesi_esik).values
    ortak = _ortak_alanlar(c, a, b)

    secili = bolge_listesi(iller)
    if bolgeler is not None:
        secili = [bl for bl in secili if bl["anahtar"] in set(bolgeler)]
    satirlar = []
    for bl in secili:
        m = maskeler[bl["anahtar"]] & gecerli
        temel = {"cift_no": c.no, "cift": c.kod, "degisken_1": c.d1, "degisken_2": c.d2,
                 "seri": c.seri, "beklenen_yon": c.beklenen_yon,
                 "bolge_turu": bl["bolge_turu"], "bolge_kodu": bl["bolge_kodu"],
                 "bolge_adi": bl["bolge_adi"], "hucre_sayisi": int(m.sum()), **ortak}
        if not m.any():
            for g in c.gecikmeler:
                bos = "kapsamda hücre yok" + (f" (kış kar örtüsü < %{c.kar_maskesi_esik:g})"
                                              if c.kar_tarafi else "")
                satirlar.append(temel | {"gecikme_ay": g, "n": 0, "not": bos})
            continue
        mk = xr.DataArray(m, coords={"lat": a["lat"], "lon": a["lon"]}, dims=("lat", "lon"))
        xa, ya = S.alan_ortalamasi(a, mk), S.alan_ortalamasi(b, mk)
        xa.attrs, ya.attrs = a.attrs, b.attrs
        for s in cift_serileri(c, xa, ya):
            # r ve p beklenen yönden bağımsızdır; etiket aşağıda c.beklenen ile verilir (0 = beklenti yok)
            r = iliski_1d(s["x"].values, s["y"].values, c.beklenen or 1, t=s["t"])
            satir = temel | {
                "gecikme_ay": s["gecikme"], "donem": s["donem"], "n": r["n"], "r": r["r"],
                "r1_1": r["r1_1"], "r1_2": r["r1_2"], "etkin_n": r["etkin_n"], "p": r["p"]}
            if ek_sutunlar:
                satir |= ham_iliski(s["x"].values, s["y"].values, s["t"])
            satirlar.append(satir)

    df = pd.DataFrame(satirlar)
    for k in ("r", "r1_1", "r1_2", "etkin_n", "p", "donem"):
        if k not in df:
            df[k] = np.nan
    df["p_fdr"] = np.nan

    # anlamlılık: il satırlarında FDR (aynı çift ve gecikme içinde), ötekilerde p < 0,05
    for g in df["gecikme_ay"].unique():
        il = (df["bolge_turu"] == "il") & (df["gecikme_ay"] == g)
        if il.any() and fdr:
            df.loc[il, "p_fdr"] = bh_fdr(df.loc[il, "p"].to_numpy(float))
    il = (df["bolge_turu"] == "il") & fdr
    anl = np.where(il, df["p_fdr"] <= ALFA_FDR, df["p"] < ALFA)
    df["anlamli"] = np.where(df["p"].notna(), anl.astype(int), np.nan)
    df["etiket"] = [etiket(r, bool(an), c.beklenen) if np.isfinite(r) else ""
                    for r, an in zip(df["r"].astype(float), df["anlamli"].fillna(0))]
    df["etiket"] = df["etiket"].fillna("")
    if "not" not in df:
        df["not"] = ""
    df["not"] = [n if isinstance(n, str) and n else _not(c, e or None)
                 for n, e in zip(df["not"], df["etiket"])]
    return df.reindex(columns=SUTUNLAR + (EK_SUTUNLAR if ek_sutunlar else []))


def ciftler_tablosu(veri: dict[str, xr.DataArray], iller: bool = True,
                    ciftler: tuple[Cift, ...] | None = None) -> pd.DataFrame:
    """Bütün çiftler (varsayılan: ciftler.yaml). ``veri``: ``{"<degisken>__<urun>": aylık küp}``;
    eksik girdili çift atlanır."""
    parca = []
    for c in (CIFTLER if ciftler is None else ciftler):
        k1, k2 = f"{c.d1}__{c.u1}", f"{c.d2}__{c.u2}"
        if k1 in veri and k2 in veri:
            parca.append(cift_tablosu(c, veri[k1], veri[k2], iller=iller))
    if not parca:
        raise ValueError("hiçbir çiftin iki girdisi birden yok")
    return pd.concat(parca, ignore_index=True)


def csv_yaz(df: pd.DataFrame, yol: str | Path) -> Path:
    """UTF-8 (BOM'lu, Excel Türkçe karakterleri doğru açsın), ondalık nokta, boş değer boş hücre."""
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    for k in ("anlamli", "n", "hucre_sayisi", "kademe", "cift_no", "gecikme_ay"):
        out[k] = out[k].astype("Int64")
    out.to_csv(yol, index=False, encoding="utf-8-sig", na_rep="", float_format="%.6g")
    return yol
