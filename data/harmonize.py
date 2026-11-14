"""Ham Türkiye kesitlerini (cache/raw/<urun>/) sözleşmeye uygun NetCDF'e çevirir.

Adımlar (değişken başına):
  1. Ürünün tüm kesitlerini aç ve zamanda birleştir.
  2. Bayrak değerleri / geçerli aralık dışı → NaN, kalite maskesi (ör. MOD13C2 pixel reliability).
  3. Günlük → aylık ortalama; düzensiz aylık (GRACE) → ayın 1'i; zaman damgası ayın 1'i 00:00.
  4. Birim dönüşümü (UNIT_CONVERSIONS; ay uzunluğuna bağlı olanlar dahil).
  5. Izgara: 0,25° analiz ızgarası (ince üründe alan-örtüşmeli ortalama, kaba üründe bilineer
     interpolasyon) + katalogda grids: ["005"] olan ince ürünlerde 0,05°.
  6. domain'e göre maske (land = Türkiye kara sınırı, ocean = kutudaki deniz).
  7. Zorunlu attrs, cache/processed/turkiye/<degisken>__<urun>[__005].nc
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from data.catalog import load_catalog, variables
from data.fetch import raw_dir, safe_name
from data.grid import GRID_RES, finalize, grid_coords, processed_path, write_netcdf

MIN_VALID_FRAC = 0.5   # ince→kaba ortalamada hedef hücrenin en az bu kadarı geçerli olmalı
MIN_DAYS = 5           # günlük → aylık ortalamada gereken en az geçerli gün


# ---------------------------------------------------------------- birim dönüşümleri

def days_in_month(time) -> xr.DataArray:
    """Her zaman adımı için ayın gün sayısı (DataArray, time boyutlu)."""
    t = pd.DatetimeIndex(time.values)
    return xr.DataArray(t.days_in_month.values.astype("float64"), coords={"time": time}, dims="time")


def _k_to_c(da, v):
    return da - 273.15


def _pa_to_hpa(da, v):
    return da / 100.0


def _kg_m2_s_to_mm_ay(da, v):
    # 1 kg m-2 = 1 mm su; aylık ortalama oran × ayın saniyesi
    return da * 86400.0 * days_in_month(da["time"])


def _acc3h_to_mm_ay(da, v):
    # GLDAS aylık _acc: 3 saatlik birikimin ortalaması → × 8 (3 saat/gün) × gün
    return da * 8.0 * days_in_month(da["time"])


def _mm_saat_to_mm_ay(da, v):
    return da * 24.0 * days_in_month(da["time"])


def _kesir_to_yuzde(da, v):
    return da * 100.0


def _olcek(da, v):
    return da * float(v.get("olcek", 1.0)) + float(v.get("ofset", 0.0))


def _molek_to_1e15(da, v):
    return da / 1e15


UNIT_CONVERSIONS = {
    "yok": lambda da, v: da,
    "K_to_C": _k_to_c,
    "Pa_to_hPa": _pa_to_hpa,
    "kg_m2_s_to_mm_ay": _kg_m2_s_to_mm_ay,
    "acc3h_to_mm_ay": _acc3h_to_mm_ay,
    "mm_saat_to_mm_ay": _mm_saat_to_mm_ay,
    "kesir_to_yuzde": _kesir_to_yuzde,
    "olcek": _olcek,
    "molek_to_1e15": _molek_to_1e15,
}


def convert_units(da: xr.DataArray, v: dict) -> xr.DataArray:
    """Katalog kaydındaki ``donusum`` adına göre birim dönüşümü uygular."""
    name = v.get("donusum", "yok")
    if name not in UNIT_CONVERSIONS:
        raise KeyError(f"Bilinmeyen dönüşüm: {name}")
    return UNIT_CONVERSIONS[name](da, v)


# ---------------------------------------------------------------- değer temizliği

def apply_flags(da: xr.DataArray, v: dict, quality: xr.DataArray | None = None) -> xr.DataArray:
    """Bayrak değerleri, geçerli aralık dışı ve kalite maskesi → NaN (ham değerler üzerinde)."""
    da = da.astype("float64")
    for f in v.get("bayraklar", []) or []:
        da = da.where(~np.isclose(da, float(f), rtol=1e-6, atol=0))
    if v.get("gecerli_aralik"):
        lo, hi = v["gecerli_aralik"]
        da = da.where((da >= lo) & (da <= hi))
    if quality is not None and v.get("kalite"):
        da = da.where(quality.isin(v["kalite"]["izinli"]))
    return da


# ---------------------------------------------------------------- zaman

def to_month_start(da: xr.DataArray, zaman: str) -> tuple[xr.DataArray, str | None]:
    """Zamanı ayın 1'ine damgalar; günlükte aylık ortalama alır. (da, işlem notu) döndürür."""
    if "time" not in da.dims:
        return da, None
    if zaman == "gunluk":
        count = da.notnull().resample(time="MS").sum()
        out = da.resample(time="MS").mean().where(count >= MIN_DAYS)
        return out, f"günlük → aylık ortalama (en az {MIN_DAYS} geçerli gün)"
    t = pd.DatetimeIndex(da["time"].values).to_period("M").to_timestamp()
    da = da.assign_coords(time=t)
    note = None
    if pd.Index(t).has_duplicates:
        da = da.groupby("time").mean()
        note = "aynı aya düşen çözümler ortalandı"
    if zaman == "aylik_duzensiz":
        note = "; ".join(x for x in ["düzensiz aylık çözümler ayın 1'ine damgalandı", note] if x)
    return da.sortby("time"), note


def full_monthly(da: xr.DataArray, start: str, end: str) -> xr.DataArray:
    """[start, end] aralığında aralıksız aylık eksene oturtur (eksik aylar NaN)."""
    t = pd.date_range(start, end, freq="MS")
    return da.reindex(time=t)


# ---------------------------------------------------------------- ızgara

def _edges(centers: np.ndarray) -> np.ndarray:
    res = float(np.median(np.diff(centers)))
    return np.concatenate([centers - res / 2, [centers[-1] + res / 2]])


def overlap_weights(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """1B alan örtüşme matrisi W[i, j] = hedef i ile kaynak j hücresinin örtüşme oranı (hedef boyuna göre)."""
    se, de = _edges(src), _edges(dst)
    lo = np.maximum(de[:-1, None], se[None, :-1])
    hi = np.minimum(de[1:, None], se[None, 1:])
    ov = np.clip(hi - lo, 0, None)
    return ov / (de[1:] - de[:-1])[:, None]


def regrid_conservative(da: xr.DataArray, lat_t, lon_t, min_frac=MIN_VALID_FRAC) -> xr.DataArray:
    """İnce → kaba alan-örtüşmeli ortalama (ayrılabilir 1B ağırlıklar, NaN farkında).

    Hedef hücrenin en az ``min_frac`` kadarı geçerli kaynak veriyle örtülü değilse NaN.
    """
    wl = overlap_weights(da["lat"].values, lat_t)
    wo = overlap_weights(da["lon"].values, lon_t)
    x = da.values
    valid = np.isfinite(x)
    xf = np.where(valid, x, 0.0)
    num = np.einsum("ij,...jk,lk->...il", wl, xf, wo, optimize=True)
    den = np.einsum("ij,...jk,lk->...il", wl, valid.astype("float64"), wo, optimize=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(den >= min_frac, num / den, np.nan)
    dims = da.dims
    coords = {d: da[d] for d in dims if d not in ("lat", "lon")}
    coords.update(lat=lat_t, lon=lon_t)
    return xr.DataArray(out, dims=dims, coords=coords, name=da.name)


def regrid(da: xr.DataArray, grid: str) -> tuple[xr.DataArray, str]:
    """Hedef ızgaraya taşır; (veri, işlem notu) döndürür."""
    lat_t, lon_t = grid_coords(grid)
    tres = GRID_RES[grid]
    sres = max(float(np.median(np.diff(da["lat"].values))), float(np.median(np.diff(da["lon"].values))))
    if sres <= tres * 1.01:
        out = regrid_conservative(da, lat_t, lon_t)
        same = np.isclose(sres, tres, rtol=0.01)
        note = (f"{sres:g}° → {tres:g}° " +
                ("hizalı kopyalama" if same else f"alan-örtüşmeli blok ortalama (geçerli oran ≥ {MIN_VALID_FRAC:.0%})"))
    else:
        out = da.interp(lat=lat_t, lon=lon_t, method="linear")
        note = f"{sres:g}° → {tres:g}° bilineer interpolasyon"
    return out, note


# ---------------------------------------------------------------- ana akış

def open_raw(key: str, names: list[str]) -> xr.Dataset:
    """Bir ürünün tüm ham kesitlerini birleştirir (yalnız istenen değişkenler)."""
    files = sorted(raw_dir(key).glob("*.nc"))
    if not files:
        raise FileNotFoundError(f"{raw_dir(key)} içinde kesit yok. Önce: python -m data.fetch --urun {key}")
    parts = []
    for f in files:
        with xr.open_dataset(f) as ds:
            parts.append(ds[[safe_name(n) for n in names]].load())
    if "time" in parts[0].dims:
        # Farklı erişim kiplerinden gelen kesitlerde koordinatlar float32/float64 yuvarlamasıyla
        # 1e-5 düzeyinde farklı olabilir: hepsini ilk dosyanın ızgarasına oturt.
        ref = parts[0]
        for i, part in enumerate(parts[1:], start=1):
            if not (np.array_equal(part["lat"].values, ref["lat"].values)
                    and np.array_equal(part["lon"].values, ref["lon"].values)):
                parts[i] = part.reindex(lat=ref["lat"], lon=ref["lon"], method="nearest", tolerance=1e-4)
        ds = xr.concat(parts, dim="time", join="exact").sortby("time")
    else:
        ds = xr.combine_by_coords(parts, combine_attrs="drop_conflicts")
    ds.attrs["_download_date"] = datetime.fromtimestamp(
        max(f.stat().st_mtime for f in files), tz=timezone.utc).date().isoformat()
    ds.attrs["_n_files"] = len(files)
    return ds


def harmonize_variable(v: dict, grids=None, raw: xr.Dataset | None = None) -> list[Path]:
    """Tek bir katalog kaydını (değişken × ürün) işleyip dosyalarını yazar."""
    p = v["urun_bilgi"]
    cat = load_catalog()
    names = [v["dosya_degiskeni"]] + ([v["kalite"]["degisken"]] if v.get("kalite") else [])
    ds = raw if raw is not None else open_raw(v["urun"], names)
    da = ds[safe_name(v["dosya_degiskeni"])]
    q = ds[safe_name(v["kalite"]["degisken"])] if v.get("kalite") else None
    steps = [f"earthaccess ile Türkiye kesiti ({p['erisim']})"]

    da = apply_flags(da, v, q)
    if v.get("bayraklar") or v.get("gecerli_aralik"):
        steps.append("bayrak/geçerli aralık dışı → NaN")
    if q is not None:
        steps.append(f"kalite maskesi: {v['kalite']['degisken']} ∈ {v['kalite']['izinli']}")

    da, note = to_month_start(da, p["zaman"])
    if note:
        steps.append(note)
    static = "time" not in da.dims
    valid_start = None
    if not static:
        start = max(pd.Period(cat["donem"][0]), pd.Period(p["valid_start"]))
        first_valid = da["time"].values[np.where(da.notnull().any(("lat", "lon")).values)[0]]
        if first_valid.size:
            start = max(start, pd.Period(pd.Timestamp(first_valid[0]), "M"))
        da = full_monthly(da, str(start), cat["donem"][1])
        valid_start = str(start)
        steps.append(f"aylık eksen {valid_start} … {cat['donem'][1]}, eksik aylar NaN")

    da = convert_units(da, v)
    if v.get("donusum", "yok") != "yok":
        steps.append(f"birim: {v['birim_orijinal']} → {v['birim']} ({v['donusum']})")

    from data.regions import domain_mask
    paths = []
    for g in grids or v.get("grids", ["025"]):
        out, note = regrid(da, g)
        gsteps = steps + [note]
        m = domain_mask(v["domain"], out["lat"].values, out["lon"].values)
        if m is not None:
            out = out.where(xr.DataArray(m, coords={"lat": out["lat"], "lon": out["lon"]},
                                         dims=("lat", "lon")))
            gsteps.append(f"{v['domain']} maskesi (hücre merkezi)")
        out.name = v["ad"]
        attrs = dict(
            units=v["birim"], long_name=v["long_name"], source_product=p["short_name"],
            source_version=str(p["version"]), doi=p.get("doi") or "yok (CMR kaydında DOI yok)",
            daac=p["daac"], download_date=ds.attrs.get("_download_date", ""),
            processing="; ".join(gsteps), grid=g, domain=v["domain"],
            valid_start=valid_start or "sabit", source_variable=v["dosya_degiskeni"],
            source_units=v["birim_orijinal"], kategori=v["kategori"], urun_anahtari=v["urun"],
        )
        if v.get("dogrulanmadi") or p.get("dogrulanmadi"):
            attrs["dogrulanmadi"] = "evet — katalog kaydının bir kısmı doğrulanmadı"
        if v.get("bilinen_sorunlar"):  # katalogdaki bilinen veri sorunu notu dosyaya taşınır
            attrs["bilinen_sorunlar"] = v["bilinen_sorunlar"]
        path = write_netcdf(finalize(out, attrs), processed_path(v["ad"], p["dosya_kodu"], g))
        paths.append(path)
    return paths


def harmonize(names=None, categories=None, products=None, include_secondary=True) -> dict:
    """Seçili katalog kayıtlarını işler. Döndürür: {(ad, urun): [yollar] ya da hata metni}."""
    sel = variables(names, categories, include_secondary=include_secondary)
    if products:
        sel = [v for v in sel if v["urun"] in products]
    res = {}
    by_product: dict[str, list] = {}
    for v in sel:
        by_product.setdefault(v["urun"], []).append(v)
    for key, vs in by_product.items():
        try:
            names_all = []
            for v in vs:
                names_all += [v["dosya_degiskeni"]] + ([v["kalite"]["degisken"]] if v.get("kalite") else [])
            raw = open_raw(key, list(dict.fromkeys(names_all)))
        except Exception as ex:
            for v in vs:
                res[(v["ad"], key)] = f"{type(ex).__name__}: {ex}"
            continue
        for v in vs:
            try:
                res[(v["ad"], key)] = harmonize_variable(v, raw=raw)
                print(f"  {v['ad']:24s} {key:12s} → {', '.join(p.name for p in res[(v['ad'], key)])}")
            except Exception as ex:
                res[(v["ad"], key)] = f"{type(ex).__name__}: {ex}"
                print(f"  {v['ad']:24s} {key:12s} HATA: {res[(v['ad'], key)]}")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ham kesitleri sözleşmeye uygun NetCDF'e çevir.")
    ap.add_argument("--vars", default="all")
    ap.add_argument("--urun", default=None, help="yalnız bu ürünler (virgülle)")
    a = ap.parse_args(argv)
    names = None if a.vars == "all" else a.vars.split(",")
    harmonize(names, products=a.urun.split(",") if a.urun else None)


if __name__ == "__main__":
    main()
