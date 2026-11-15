"""Tek komutla veri üretimi ve okuma.

Üretim:
    python -m data.build --vars all
    python -m data.build --vars sicaklik_2m,yagis,no2 --categories hava_kalitesi
    python -m data.build --vars all --skip-fetch      # yalnız harmonize (ham kesitler varsa)
    python -m data.build --ozet                        # yalnız mevcut dosyaların özeti

Okuma (diğer modüller için):
    from data import load
    da = load("sicaklik_2m", region="Erzurum")                 # ana ürün, 0,25°
    da = load("kar_ortusu", region="dogu_anadolu", grid="005")
    da = load("sicaklik_2m", region=(39, 39, 41, 40), product="GLDAS")
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from data.catalog import variable, variables
from data.grid import TURKIYE_DIR, processed_path


def resolve_path(degisken: str, grid: str = "025", product: str | None = None,
                 sentetik: str | bool = "otomatik") -> Path:
    """Değişken için okunacak dosyayı bulur.

    product: katalog ürün anahtarı ("GLDAS"), dosya kodu ("MERRA2") ya da "SENTETIK".
    sentetik: "otomatik" → gerçek dosya yoksa sentetiğe düş (uyarı verir); True → hep sentetik;
              False → yalnız gerçek veri.
    """
    if sentetik is True or (product or "").upper() == "SENTETIK":
        p = processed_path(degisken, "SENTETIK", grid)
        if not p.exists():
            raise FileNotFoundError(f"{p} yok. Önce: python -m data.synthetic")
        return p
    tried = []
    try:
        v = variable(degisken, product)
        p = processed_path(degisken, v["urun_bilgi"]["dosya_kodu"], grid)
        if p.exists():
            return p
        tried.append(p)
        if product is None:  # ana ürün yoksa aynı değişkenin diğer ürünlerine bak
            for alt in variables([degisken]):
                q = processed_path(degisken, alt["urun_bilgi"]["dosya_kodu"], grid)
                if q.exists():
                    warnings.warn(f"{degisken}: ana ürün dosyası yok, {alt['urun']} kullanılıyor.")
                    return q
    except KeyError:
        if product is not None:
            raise
    if sentetik == "otomatik":
        p = processed_path(degisken, "SENTETIK", grid)
        if p.exists():
            warnings.warn(f"{degisken}: gerçek veri yok → SENTETİK dosya kullanılıyor (yer tutucu!).")
            return p
    raise FileNotFoundError(f"{degisken} ({grid}) için dosya yok: {[str(t) for t in tried]}. "
                            "Önce: python -m data.build --vars " + degisken)


def load(degisken: str, region="turkiye", grid: str = "025", product: str | None = None,
         sentetik: str | bool = "otomatik", all_touched: bool = False, ulke: str | None = None) -> xr.DataArray:
    """İşlenmiş ülke küpünü (varsayılan Türkiye) açar ve bölgeye keser.

    Döndürür: xr.DataArray (time, lat, lon) — rakım için (lat, lon). attrs: dosyanın tüm attrs'ı
    + region, region_label, region_kind, region_cells, region_method.
    region: il / bölge / "turkiye" / ülke anahtarı ("yunanistan") / deniz adı, bbox, GeoJSON ya da None
    (None → kesmeden tüm kutu). ``ulke``: cache/processed/<ulke>/ (ör. load("ndvi", "yunanistan",
    ulke="yunanistan")).
    """
    from data.regions import subset
    from data.ulkeler import ulke_baglami
    with ulke_baglami(ulke):
        path = resolve_path(degisken, grid, product, sentetik)
        with xr.open_dataset(path) as ds:
            ds = ds.load()
        if region is not None:
            ds = subset(ds, region, all_touched=all_touched)
    da = ds[degisken]
    da.attrs = {**ds.attrs, **da.attrs, "file": path.name}
    return da


def summarize(folder: Path | None = None) -> pd.DataFrame:
    """İşlenmiş dosyaların özeti: değişken, ürün, ızgara, boyut, dönem, NaN oranı, MB.

    ``folder`` verilmezse aktif ülkenin klasörü (varsayılan cache/processed/turkiye/).
    """
    from data.grid import ulke_dir
    folder = Path(folder) if folder is not None else ulke_dir()
    rows = []
    for f in sorted(folder.glob("*.nc")):
        with xr.open_dataset(f) as ds:
            name = list(ds.data_vars)[0]
            da = ds[name]
            per = (f"{pd.Timestamp(da.time.values[0]):%Y-%m} … {pd.Timestamp(da.time.values[-1]):%Y-%m}"
                   if "time" in da.dims else "sabit")
            # NaN oranı yalnız domain içindeki hücreler üzerinden (maske dışı hücreler hep NaN)
            ever = da.notnull().any("time") if "time" in da.dims else da.notnull()
            n_inside = max(int(ever.sum()) * da.sizes.get("time", 1), 1)
            nan = 1.0 - float(da.notnull().sum()) / n_inside
            rows.append(dict(dosya=f.name, degisken=name, urun=ds.attrs.get("source_product"),
                             grid=ds.attrs.get("grid"), boyut="×".join(str(s) for s in da.shape),
                             donem=per, valid_start=ds.attrs.get("valid_start"),
                             hucre=int(ever.sum()), nan_orani=round(nan, 3),
                             mb=round(f.stat().st_size / 1e6, 1)))
    return pd.DataFrame(rows)


def build(names=None, categories=None, skip_fetch=False, onay=False, include_secondary=True,
          ulke: str | None = None) -> dict:
    """Seçili değişkenler için fetch → harmonize çalıştırır; sonuç sözlüğü döndürür.

    ``ulke``: data/ulkeler.yaml anahtarı (varsayılan turkiye). Ham kesitler cache/raw/<ulke>/<urun>/
    (Türkiye: cache/raw/<urun>/), işlenmiş dosyalar cache/processed/<ulke>/.
    """
    from data.ulkeler import ulke_baglami
    with ulke_baglami(ulke):
        return _build(names, categories, skip_fetch, onay, include_secondary)


def _build(names, categories, skip_fetch, onay, include_secondary) -> dict:
    from data.fetch import fetch_product
    from data.harmonize import harmonize
    sel = variables(names, categories, include_secondary=include_secondary)
    keys = list(dict.fromkeys(v["urun"] for v in sel))
    fetch_reps = {}
    if not skip_fetch:
        for k in keys:
            try:
                fetch_reps[k] = fetch_product(k, onay=onay)
            except RuntimeError as ex:  # giriş hatası → dur
                print(f"DURDU: {ex}")
                raise
            except Exception as ex:
                fetch_reps[k] = {"urun": k, "durum": f"HATA {type(ex).__name__}: {ex}"}
                print(f"[{k}] HATA: {ex} — sonraki ürüne geçiliyor")
    names_sel = list(dict.fromkeys(v["ad"] for v in sel))
    if fetch_reps:
        products = [k for k in keys if "ertelendi" not in str(fetch_reps.get(k, {}).get("durum", ""))]
    else:  # --skip-fetch: ertelenmiş ürünleri (tek-ay denemesi olsa bile) atla, --onay ile dahil et
        from data.catalog import product
        products = [k for k in keys if onay or product(k).get("durum", "aktif") != "ertelendi"]
    res = harmonize(names_sel, products=products, include_secondary=include_secondary)
    return {"fetch": fetch_reps, "harmonize": res}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Trend Dedektifi veri üretimi (fetch + harmonize).")
    ap.add_argument("--vars", default=None, help="'all' ya da virgülle değişken adları")
    ap.add_argument("--categories", default=None, help="virgülle kategoriler (ör. hava_kalitesi)")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--onay", action="store_true", help="büyük/ertelenmiş ürünleri de indir")
    ap.add_argument("--sadece-ana", action="store_true", help="yalnız ana ürünler")
    ap.add_argument("--ozet", action="store_true", help="yalnız mevcut dosyaların özetini yaz")
    ap.add_argument("--ulke", default=None, help="data/ulkeler.yaml anahtarı (varsayılan turkiye)")
    a = ap.parse_args(argv)
    from data.ulkeler import aktif, ulke_baglami
    if not a.ozet:
        names = None if a.vars in (None, "all") else a.vars.split(",")
        cats = a.categories.split(",") if a.categories else None
        if a.vars is None and cats is None:
            ap.error("--vars ya da --categories gerekli")
        out = build(names, cats, a.skip_fetch, a.onay, not a.sadece_ana, ulke=a.ulke)
        errs = {k: v for k, v in out["harmonize"].items() if isinstance(v, str)}
        if errs:
            print("\nİşlenemeyenler:")
            for (ad, urun), msg in errs.items():
                print(f"  {ad} ({urun}): {msg[:200]}")
    with ulke_baglami(a.ulke):
        df = summarize()
        klasor = aktif()
    with pd.option_context("display.width", 200, "display.max_rows", 200, "display.max_colwidth", 40):
        print(f"\nÜRETİLEN DOSYALAR (cache/processed/{klasor}/)")
        print(df.to_string(index=False) if len(df) else "  (yok)")


if __name__ == "__main__":
    main()
