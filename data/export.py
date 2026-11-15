"""Yayın paketi: işlenmiş 0,25° gerçek veri küplerini yayın kutusuna kırpıp tek klasöre yazar.

    python -m data.export --surum v0.1                      # Türkiye (varsayılan)
    python -m data.export --ulke yunanistan --surum v0.1

Çıktı:
    outputs/trend-dedektifi-<ulke>-<surum>/L1_kup/<degisken>__<urun>.nc
    outputs/trend-dedektifi-<ulke>-<surum>/L1_kup/ICINDEKILER.csv

Kurallar:
- Yalnız 0,25° (``__005`` dosyaları girmez) ve yalnız gerçek veri (SENTETIK girmez).
- Kaynak ``cache/processed/<ulke>/``; yayın kutusu ``data/ulkeler.yaml`` (``yayin_kutusu``). Türkiye:
  ``YAYIN_BBOX`` (25,5–45,0 D, 35,5–42,5 K), 0,25°'de 28 enlem × 78 boylam hücre. Hücre kenarlarının kutu
  sınırına tam oturduğu denetlenir.
- Türkiye dışındaki ülkelerde ``ulke``, ``ulke_adi``, ``ulke_iso3`` attr'ları yazılır ve ulkeler.yaml'daki
  ``ek_uyarilar`` ``bilinen_sorunlar``'a eklenir. Türkiye dosyalarının biçimi değişmez (attr yoksa Türkiye).
- Kademe 1 = ekip belgesindeki çekirdek dosyalar (``KADEME_1``); diğerleri Kademe 2 ve
  ``dogrulanmadi="evet"`` attr'ı taşır. Sabit alanlar (rakım) kademesizdir: ``kademe=0``.
- ``kademe`` her dosyada int32'dir: 1, 2 ya da 0 (kademesiz).
- ``L1_kup/`` içinde başka modülün ayrıca yazdığı sabit katmanlar (ör. ``data.arazi`` →
  ``tarim_orani__MCD12C1.nc``) korunur ve ICINDEKILER.csv'ye kendi ``kademe`` attr'larıyla eklenir.
- Katalog kaydının doğrulanmadığını gösteren ayrı bayrak ``katalog_dogrulanmadi``'dır (harmonize
  yazar); yayın paketindeki ``dogrulanmadi`` yalnız Kademe 2 anlamına gelir.
- Mevcut ``doi`` attr'ı NASA kaynak ürününün DOI'si olarak kalır; yayın DOI'si ``veri_seti_doi``.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from data.catalog import variables
from data.grid import GRID_RES, REPO_ROOT, TURKIYE_DIR, check_contract, ulke_dir, write_netcdf
from data import ulkeler as U

# (batı, güney, doğu, kuzey), derece — yayın kutusu
YAYIN_BBOX: tuple[float, float, float, float] = (25.5, 35.5, 45.0, 42.5)
YAYIN_SHAPE = (28, 78)  # (lat, lon) 0,25°'de

# Kademe 1 değişken × dosya kodu çiftleri (ekip belgesi); geri kalan gerçek dosyalar Kademe 2
KADEME_1 = {
    ("sicaklik_2m", "MERRA2"), ("sicaklik_2m", "GLDAS"),
    ("yagis", "GPM"), ("yagis", "GLDAS"), ("yagis", "MERRA2"),
    ("toprak_nemi", "GLDAS"), ("kar_ortusu", "MOD10CM"), ("kar_su_esdegeri", "GLDAS"),
    ("ndvi", "MOD13C2"), ("toplam_su_depolama", "GRACE"),
}
# Kademesiz (sabit alanlar): kademe attr'ı 0, dogrulanmadi yok
KADEME_DISI = {"rakim"}
KADEMESIZ = 0

LISANS = "CC BY 4.0"
VERI_SETI_DOI = "(yayında doldurulacak)"
OUTPUTS_DIR = REPO_ROOT / "outputs"
ICINDEKILER_COLS = ["dosya", "degisken", "birim", "kaynak", "kaynak_doi", "donem", "kademe"]


def kademe(degisken: str, urun: str) -> int:
    """Değişken × dosya kodu için yayın kademesi: 1, 2 (doğrulanmadı) ya da 0 (kademesiz, sabit alan)."""
    if degisken in KADEME_DISI:
        return KADEMESIZ
    return 1 if (degisken, urun) in KADEME_1 else 2


def is_synthetic(ds: xr.Dataset) -> bool:
    """Dosya sentetik mi? (ürün kodu SENTETIK ya da synthetic_truth / yer_tutucu attrs'ı)."""
    return (str(ds.attrs.get("source_product", "")).upper() == "SENTETIK"
            or "synthetic_truth" in ds.attrs or "yer_tutucu" in ds.attrs)


def crop_to_bbox(ds: xr.Dataset, bbox=YAYIN_BBOX, res: float = GRID_RES["025"],
                 shape=YAYIN_SHAPE) -> xr.Dataset:
    """Hücre merkezi kutu içinde kalan hücreleri seçer ve kenarların ızgaraya oturduğunu doğrular.

    Hata verir: ızgara aralığı ``res`` değilse, kesit ``shape`` boyutunda değilse ya da ilk/son
    hücrenin kenarı kutu sınırıyla çakışmıyorsa.
    """
    west, south, east, north = bbox
    lat, lon = ds["lat"].values, ds["lon"].values
    for name, c in (("lat", lat), ("lon", lon)):
        if c.size < 2 or not np.allclose(np.diff(c), res, atol=1e-6):
            raise ValueError(f"{name} ızgara aralığı {res}° değil")
    out = ds.isel(lat=np.where((lat > south) & (lat < north))[0],
                  lon=np.where((lon > west) & (lon < east))[0])
    got = (out.sizes["lat"], out.sizes["lon"])
    if shape is not None and got != tuple(shape):
        raise ValueError(f"kesit boyutu {got}, beklenen {tuple(shape)}")
    half = res / 2
    edges = {"batı": (out["lon"].values[0] - half, west), "doğu": (out["lon"].values[-1] + half, east),
             "güney": (out["lat"].values[0] - half, south), "kuzey": (out["lat"].values[-1] + half, north)}
    bad = {k: v for k, v in edges.items() if not np.isclose(v[0], v[1], atol=1e-6)}
    if bad:
        raise ValueError(f"kutu kenarı ızgaraya oturmuyor: {bad}")
    return out


def data_period(ds: xr.Dataset) -> str:
    """Kesitte en az bir geçerli hücresi olan ilk ve son ay ("YYYY-MM … YYYY-MM"); sabit alanda "sabit"."""
    if "time" not in ds.dims:
        return "sabit"
    da = next(iter(ds.data_vars.values()))
    ok = da.notnull().any(dim=[d for d in da.dims if d != "time"]).values
    if not ok.any():
        return "veri yok"
    t = pd.DatetimeIndex(ds["time"].values[ok])
    return f"{t[0]:%Y-%m} … {t[-1]:%Y-%m}"


def yayin_sekli(bbox, res: float = GRID_RES["025"]) -> tuple[int, int]:
    """Yayın kutusunun (lat, lon) hücre sayısı (Türkiye: 28 × 78)."""
    w, s, e, n = bbox
    return int(round((n - s) / res)), int(round((e - w) / res))


def release_attrs(ds: xr.Dataset, degisken: str, urun: str, surum: str, bbox=YAYIN_BBOX,
                  ulke: str | None = None) -> dict:
    """Mevcut attrs'a yayın alanlarını ekler (doi = NASA kaynak DOI'si olarak kalır).

    Türkiye dışındaki ülkede ülke attr'ları ve ülkeye özgü ``ek_uyarilar`` (``bilinen_sorunlar``) eklenir.
    """
    k = kademe(degisken, urun)
    a = dict(ds.attrs)
    # Eski harmonize çıktısında katalog bayrağı "dogrulanmadi" adıyla yazılmış olabilir: yeni ada taşı
    if "dogrulanmadi" in a:
        a.setdefault("katalog_dogrulanmadi", a.pop("dogrulanmadi"))
    w, s, e, n = bbox
    a["processing"] = (f"{a.get('processing', '')}; yayın kutusuna kırpıldı "
                       f"(batı {w}, güney {s}, doğu {e}, kuzey {n})").lstrip("; ")
    a.update(urun_surumu=surum, veri_seti_doi=VERI_SETI_DOI, kademe=np.int32(k), lisans=LISANS,
             yayin_kutusu=f"{w}, {s}, {e}, {n}")
    if k == 2:
        a["dogrulanmadi"] = "evet"
    if not U.varsayilan_mi(ulke):                 # Türkiye dosyaları eskisiyle bayt bayt aynı kalsın
        u = U.ulke(ulke)
        a.update(ulke=u["anahtar"], ulke_adi=u["ad"], ulke_iso3=u["iso3"])
        ek = u["ek_uyarilar"].get(f"{degisken}__{urun}")
        if ek:
            a["bilinen_sorunlar"] = "; ".join(x for x in (a.get("bilinen_sorunlar"), ek) if x)
    return a


def candidates(src_dir: Path = TURKIYE_DIR) -> list[tuple[str, str, Path]]:
    """Katalogdaki her değişken × ürün için var olan 0,25° gerçek dosyalar: (degisken, urun, yol)."""
    seen, out = set(), []
    for v in variables():
        key = (v["ad"], v["urun_bilgi"]["dosya_kodu"])
        p = Path(src_dir) / f"{key[0]}__{key[1]}.nc"
        if key not in seen and p.exists():
            seen.add(key)
            out.append((*key, p))
    return out


def icindekiler_satiri(ds: xr.Dataset, dosya: str, degisken: str, kademe_: int) -> dict:
    """ICINDEKILER.csv için bir satır (yayın attr'ları yazılmış Dataset'ten)."""
    return {"dosya": dosya, "degisken": degisken, "birim": ds.attrs.get("units", ""),
            "kaynak": f"{ds.attrs['source_product']} {ds.attrs['source_version']}",
            "kaynak_doi": ds.attrs.get("doi", ""), "donem": data_period(ds), "kademe": int(kademe_)}


def sabit_katmanlar(out_dir: Path, yazilan: set[str]) -> list[dict]:
    """L1_kup/ içinde export'un yazmadığı, ayrıca üretilmiş sabit (zamansız) katmanların satırları.

    Örnek: ``data.arazi`` ile yazılan ``tarim_orani__MCD12C1.nc``. Dosyaya dokunulmaz; yalnız okunur.
    Kademe dosyanın ``kademe`` attr'ından gelir (yoksa katman atlanır ve uyarı basılır). Zamanlı ya da
    sentetik dosyalar listeye alınmaz (zamanlı L1 dosyalarının tek kaynağı export'tur).
    """
    rows = []
    for p in sorted(Path(out_dir).glob("*.nc")):
        if p.name in yazilan or "__005" in p.stem or p.stem.count("__") != 1:
            continue
        with xr.open_dataset(p) as ds:
            if "time" in ds.dims or is_synthetic(ds):
                continue
            if "kademe" not in ds.attrs:
                print(f"  ICINDEKILER'e alınmadı (kademe attr'ı yok): {p.name}")
                continue
            degisken = p.stem.split("__")[0]
            rows.append(icindekiler_satiri(ds, p.name, degisken, ds.attrs["kademe"]))
        print(f"  listelendi (sabit katman): {p.name} (kademe {rows[-1]['kademe']})")
    return rows


def paket_adi(surum: str, ulke: str | None = None) -> str:
    """``trend-dedektifi-<ulke>-<surum>`` (Türkiye: trend-dedektifi-turkiye-v0.1)."""
    return f"trend-dedektifi-{U.ulke(ulke)['anahtar']}-{surum}"


def export(surum: str, src_dir: Path | None = None, out_root: Path = OUTPUTS_DIR,
           bbox=None, ulke: str | None = None) -> Path:
    """Yayın paketini yazar; L1_kup klasörünün yolunu döndürür.

    ``ulke`` verilmezse aktif ülke (varsayılan Türkiye); ``src_dir`` verilmezse ``cache/processed/<ulke>/``,
    ``bbox`` verilmezse ulkeler.yaml ``yayin_kutusu``.
    """
    with U.ulke_baglami(ulke):
        return _export(surum, src_dir, out_root, bbox)


def _export(surum, src_dir, out_root, bbox) -> Path:
    src_dir = Path(src_dir) if src_dir is not None else ulke_dir()
    bbox = tuple(bbox) if bbox is not None else U.yayin_kutusu()
    sekil = yayin_sekli(bbox)
    out_dir = Path(out_root) / paket_adi(surum) / "L1_kup"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for degisken, urun, path in candidates(src_dir):
        with xr.open_dataset(path) as ds:
            ds = ds.load()
        if is_synthetic(ds):
            print(f"  atlandı (sentetik): {path.name}")
            continue
        cut = crop_to_bbox(ds, bbox, shape=sekil)
        cut.attrs = release_attrs(ds, degisken, urun, surum, bbox)
        problems = check_contract(cut, static="time" not in cut.dims)
        if problems:
            raise ValueError(f"{path.name} sözleşmeye uymuyor: {problems}")
        write_netcdf(cut, out_dir / path.name)
        rows.append(icindekiler_satiri(cut, path.name, degisken, kademe(degisken, urun)))
        print(f"  yazıldı: {path.name} (kademe {rows[-1]['kademe']}, {rows[-1]['donem']})")
    rows += sabit_katmanlar(out_dir, {r["dosya"] for r in rows})
    rows.sort(key=lambda r: (r["kademe"] or 9, r["dosya"]))  # 1, 2, sonra kademesiz (0)
    with open(out_dir / "ICINDEKILER.csv", "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=ICINDEKILER_COLS)
        wr.writeheader()
        wr.writerows(rows)
    return out_dir


def main(argv=None):
    ap = argparse.ArgumentParser(description="Yayın paketi (L1 küpleri) üretir.")
    ap.add_argument("--surum", required=True, help="ör. v0.1")
    ap.add_argument("--ulke", default=None, help="data/ulkeler.yaml anahtarı (varsayılan turkiye)")
    ap.add_argument("--kaynak", default=None, help="işlenmiş dosyaların klasörü (varsayılan cache/processed/<ulke>/)")
    ap.add_argument("--cikti", default=str(OUTPUTS_DIR), help="çıktı kök klasörü")
    a = ap.parse_args(argv)
    out = export(a.surum, Path(a.kaynak) if a.kaynak else None, Path(a.cikti), ulke=a.ulke)
    print(f"Yayın paketi: {out}")


if __name__ == "__main__":
    main()
