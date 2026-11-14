"""Giovanni alan ortalaması CSV'sini bizim dosyamızla karşılaştırır.

Giovanni'de (https://giovanni.gsfc.nasa.gov) "Time Series, Area-Averaged" çıktısını CSV olarak indirin.
Bu betik CSV'deki bölge kutusunu (ya da --region ile verilen bölgeyi) bizim işlenmiş dosyamızdan
keser, cos(enlem) ağırlıklı alan ortalamasını alır ve aylık seriler arasında korelasyon, ortalama
fark ve RMSE yazdırır.

    python -m data.check_giovanni giovanni.csv --degisken yagis --giovanni-donusum mm_saat_to_mm_ay
    python -m data.check_giovanni g.csv --degisken sicaklik_2m --giovanni-donusum K_to_C --region Erzurum

Not: Bizim kara değişkenlerimiz Türkiye kara sınırıyla maskelidir; Giovanni kutudaki tüm hücreleri
(deniz ve komşu ülkeler dahil) ortalar. Kıyıya ya da sınıra yakın kutularda küçük farklar beklenir.
"""

from __future__ import annotations

import argparse
import io
import re
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr


def read_giovanni_csv(path) -> tuple[pd.Series, dict]:
    """Giovanni CSV → (aylık seri, meta). Seri indeksi ayın 1'i; dolgu değeri NaN olur."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    meta, start = {}, None
    for i, line in enumerate(lines):
        if re.match(r"^\s*time\s*,", line, flags=re.I):
            start = i
            break
        if ":" in line and "," in line:
            k, _, v = line.partition(",")
            meta[k.strip().rstrip(":")] = v.strip().strip('"')
    if start is None:
        raise ValueError("CSV'de 'time,...' başlık satırı bulunamadı")
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
    tcol, vcol = df.columns[0], df.columns[1]
    s = pd.Series(pd.to_numeric(df[vcol], errors="coerce").values,
                  index=pd.to_datetime(df[tcol]).dt.to_period("M").dt.to_timestamp(), name=vcol)
    fill = next((v for k, v in meta.items() if k.lower().startswith("fill value")), None)
    if fill is not None:
        try:
            s = s.where(~np.isclose(s, float(fill)))
        except ValueError:
            pass
    bbox = None
    bb = meta.get("Bounding Box")
    if bb:
        nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", bb)]
        if len(nums) == 4:
            bbox = tuple(nums)  # Giovanni sırası: batı, güney, doğu, kuzey
    meta["bbox"] = bbox
    return s.groupby(level=0).mean(), meta


def compare(ours: pd.Series, theirs: pd.Series) -> dict:
    """Ortak aylarda korelasyon, ortalama fark (biz − Giovanni), RMSE ve N."""
    j = pd.concat([ours.rename("biz"), theirs.rename("giovanni")], axis=1).dropna()
    if len(j) < 3:
        return {"n": len(j), "korelasyon": np.nan, "ortalama_fark": np.nan, "rmse": np.nan}
    d = j["biz"] - j["giovanni"]
    return {"n": int(len(j)), "korelasyon": float(j["biz"].corr(j["giovanni"])),
            "ortalama_fark": float(d.mean()), "rmse": float(np.sqrt((d ** 2).mean())),
            "biz_ort": float(j["biz"].mean()), "giovanni_ort": float(j["giovanni"].mean()),
            "baslangic": f"{j.index[0]:%Y-%m}", "bitis": f"{j.index[-1]:%Y-%m}"}


def giovanni_convert(s: pd.Series, donusum: str | None) -> pd.Series:
    """Giovanni serisini bizim birimimize çevirir (harmonize.UNIT_CONVERSIONS adlarıyla)."""
    if not donusum or donusum == "yok":
        return s
    from data.harmonize import convert_units
    da = xr.DataArray(s.values, coords={"time": s.index}, dims="time")
    return pd.Series(convert_units(da, {"donusum": donusum}).values, index=s.index)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Giovanni alan ortalaması ile karşılaştırma.")
    ap.add_argument("csv")
    ap.add_argument("--degisken", required=True)
    ap.add_argument("--urun", default=None, help="ürün anahtarı/dosya kodu (varsayılan: ana ürün)")
    ap.add_argument("--region", default=None, help="varsayılan: CSV'deki Bounding Box")
    ap.add_argument("--giovanni-donusum", default=None,
                    help="Giovanni birimini bizimkine çevir: mm_saat_to_mm_ay, K_to_C, kg_m2_s_to_mm_ay ...")
    a = ap.parse_args(argv)

    from data.build import load
    from data.regions import area_mean
    theirs, meta = read_giovanni_csv(a.csv)
    theirs = giovanni_convert(theirs, a.giovanni_donusum)
    region = a.region or meta["bbox"]
    if region is None:
        ap.error("CSV'de Bounding Box yok; --region verin")
    da = load(a.degisken, region=region, product=a.urun, sentetik=False)
    ours = area_mean(da).to_series()
    ours.index = pd.DatetimeIndex(ours.index)
    r = compare(ours, theirs)
    print(f"Değişken: {a.degisken} ({da.attrs.get('file')}), bölge: {da.attrs.get('region_label')}, "
          f"hücre: {da.attrs.get('region_cells')}")
    print(f"Giovanni: {meta.get('Title', theirs.name)[:120]}")
    if r["n"] < 3:
        print(f"Ortak ay sayısı yetersiz: {r['n']}")
        return
    print(f"Ortak dönem {r['baslangic']} … {r['bitis']} (N = {r['n']} ay)")
    print(f"  korelasyon        : {r['korelasyon']:.3f}")
    print(f"  ortalama fark     : {r['ortalama_fark']:+.3f} {da.attrs.get('units', '')} (biz − Giovanni)")
    print(f"  RMSE              : {r['rmse']:.3f}")
    print(f"  ortalamalar       : biz {r['biz_ort']:.3f}, Giovanni {r['giovanni_ort']:.3f}")


if __name__ == "__main__":
    main()
