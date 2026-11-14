"""Arazi katmanları: MODIS MCD12C1 tarım oranı (sabit L1 katmanı) ve GFSAD1KCM sulanan oran (yalnız doğrulama).

    python -m data.arazi --surum v0.1            # ikisi de (ham dosyalar cache/raw altında olmalı)
    python -m data.arazi --surum v0.1 --indir    # önce eksik ham dosyaları earthaccess ile indir (netrc)

1. ``tarim_orani`` (MCD12C1 v061, 0,05° CMG, IGBP "Land_Cover_Type_1_Percent"):
   tarim_orani = (%sınıf 12 "Croplands" + ½ · %sınıf 14 "Cropland/Natural Vegetation Mosaic") / 100,
   son 5 yılın (varsayılan 2021–2025) ortalaması. Sabit (zamansız) katman, kademe 2 (doğrulanmadı).
   Çıktı: cache/processed/turkiye/tarim_orani__MCD12C1.nc (0,25°) ve __005.nc (0,05°), ayrıca L1 paketine
   YENİ dosya L1_kup/tarim_orani__MCD12C1.nc (var olan dosyanın üzerine yazılmaz).
2. ``sulanan_oran`` (GFSAD1KCM v001, 2010, ~1 km): sulanan tarım sınıfları (1 "Irrigation major",
   2 "Irrigation minor") piksel oranı; payda kara pikselleri (1–5 tarım, 9 "Non-Cropland"; 0 = veri yok).
   Sınıf tablosu: GFSAD1K User Guide v1, bölüm 2.2.4 (lpdaac.usgs.gov/documents/172). YALNIZ DOĞRULAMA: <paket>/dogrulama/ altına yazılır; sulama izi
   hesabına girmez.

MCD12C1 granüllerinde Cloud OPeNDAP yoktur; tam HDF4 dosyaları (yaklaşık 1,2 GB/yıl) indirilir ve
Türkiye kesiti ``data.fetch`` yardımcılarıyla okunur. Şifre koda yazılmaz: ``earthaccess.login(strategy="netrc")``.
"""

from __future__ import annotations

import argparse
import time
from datetime import date
from pathlib import Path

import numpy as np
import xarray as xr

from data.grid import GRID_RES, RAW_DIR, TURKIYE_BBOX, check_contract, grid_coords, processed_path, write_netcdf

MCD12C1 = {"short_name": "MCD12C1", "version": "061", "doi": "10.5067/MODIS/MCD12C1.061", "daac": "LP DAAC"}
GFSAD = {"short_name": "GFSAD1KCM", "version": "001", "doi": "10.5067/MEASURES/GFSAD/GFSAD1KCM.001",
         "daac": "LP DAAC"}
SDS_YUZDE = "Land_Cover_Type_1_Percent"
TARIM_SINIFI, MOZAIK_SINIFI = 12, 14          # IGBP: 12 Croplands, 14 Cropland/Natural Vegetation Mosaic
MOZAIK_AGIRLIK = 0.5
YIL_SAYISI = 5
SULANAN_SINIFLAR = (1, 2)                     # GFSAD1KCM: 1 Irrigation major, 2 Irrigation minor
KARA_SINIFLARI = (1, 2, 3, 4, 5, 9)           # 1–5 tarım, 9 tarım dışı kara; 0 = veri yok (payda dışı)
MIN_PIKSEL = 10                               # 0,05° hücrede en az geçerli piksel (≈ 31 piksele düşer)


# ---------------------------------------------------------------- indirme
def indir(yillar: tuple[int, int] | None = None) -> dict:
    """Eksik ham dosyaları cache/raw altına indirir. Döndürür: {"mcd12c1": [yol], "gfsad": [yol], "sure", "gb"}."""
    import earthaccess
    t0 = time.time()
    if not earthaccess.login(strategy="netrc"):
        raise RuntimeError("Earthdata girişi başarısız (netrc)")
    out = {}
    for anahtar, urun, zaman in (("gfsad", GFSAD, None), ("mcd12c1", MCD12C1, yillar)):
        kw = {"temporal": (f"{zaman[0]}-01-01", f"{zaman[1]}-12-31")} if zaman else {}
        g = earthaccess.search_data(short_name=urun["short_name"], version=urun["version"], **kw)
        if not g:
            raise LookupError(f"CMR'de granül yok: {urun['short_name']} {urun['version']}")
        hedef = RAW_DIR / urun["short_name"]
        hedef.mkdir(parents=True, exist_ok=True)
        out[anahtar] = [Path(p) for p in earthaccess.download(g, local_path=str(hedef), threads=3)]
    out["sure"] = time.time() - t0
    out["gb"] = sum(p.stat().st_size for v in ("mcd12c1", "gfsad") for p in out[v]) / 1e9
    return out


def ham_dosyalar(urun: str, desen: str) -> list[Path]:
    return sorted((RAW_DIR / urun).glob(desen))


# ---------------------------------------------------------------- MCD12C1 → tarım oranı
def mcd12c1_kesit(yol: Path, siniflar=(TARIM_SINIFI, MOZAIK_SINIFI), bbox=TURKIYE_BBOX, pay: float = 0.25) -> xr.Dataset:
    """Bir MCD12C1 HDF4 dosyasından Türkiye kesitinde istenen IGBP sınıflarının yüzde katmanları."""
    from pyhdf.SD import SD, SDC
    from data.fetch import _gctp_geo_axes, _index_window
    h = SD(str(yol), SDC.READ)
    try:
        sm = h.attributes().get("StructMetadata.0", "")
        sds = h.select(SDS_YUZDE)
        ny, nx, nk = sds.info()[2]
        lat_all, lon_all = _gctp_geo_axes(sm, ny, nx)
        w, s, e, n = bbox
        ri, ci = _index_window(lat_all, s - pay, n + pay), _index_window(lon_all, w - pay, e + pay)
        out = {}
        for k in siniflar:
            arr = np.asarray(sds[ri.start:ri.stop, ci.start:ci.stop, k:k + 1])[..., 0].astype("float32")
            arr[(arr < 0) | (arr > 100)] = np.nan            # 255 vb. dolgu
            out[f"yuzde_{k}"] = xr.DataArray(arr, dims=("lat", "lon"),
                                             coords={"lat": lat_all[ri], "lon": lon_all[ci]})
        sds.endaccess()
    finally:
        h.end()
    return xr.Dataset(out).sortby("lat").sortby("lon")


def tarim_orani_hesapla(kesitler: list[xr.Dataset]) -> xr.DataArray:
    """Yıllık kesitlerden (yüzde_12 + ½ · yüzde_14) / 100 ortalaması (0–1)."""
    yillik = [(k[f"yuzde_{TARIM_SINIFI}"] + MOZAIK_AGIRLIK * k[f"yuzde_{MOZAIK_SINIFI}"]) / 100.0 for k in kesitler]
    return xr.concat(yillik, dim="yil").mean("yil", skipna=True).clip(0, 1).rename("tarim_orani")


def _ortak_attrs(urun: dict, kaynak_degisken: str, birim: str, ad: str, isleme: str, grid: str) -> dict:
    return {"units": birim, "long_name": ad, "source_product": urun["short_name"],
            "source_version": urun["version"], "doi": urun["doi"], "daac": urun["daac"],
            "download_date": date.today().isoformat(), "processing": isleme, "grid": grid, "domain": "land",
            "valid_start": "sabit", "source_variable": kaynak_degisken, "kategori": "sabit"}


def izgaraya(da: xr.DataArray, grid: str) -> tuple[xr.DataArray, str]:
    """Hedef ızgaraya (``data.harmonize.regrid``: 0,05° hizalı kopya, 0,25° alan-örtüşmeli ortalama) ve kara maskesi."""
    from data.harmonize import regrid
    from data.regions import domain_mask
    out, not_ = regrid(da, grid)
    m = domain_mask("land", out["lat"].values, out["lon"].values)
    if m is not None:
        out = out.where(m)
    return out.astype("float32"), not_ + "; land maskesi (hücre merkezi)"


def tarim_orani_uret(dosyalar: list[Path], surum: str = "v0.1", paket: Path | None = None) -> dict:
    """tarim_orani 0,05° ve 0,25° cache dosyalarını ve L1 paketindeki yeni dosyayı yazar."""
    from data.export import OUTPUTS_DIR, crop_to_bbox, release_attrs
    if len(dosyalar) < YIL_SAYISI:
        raise ValueError(f"MCD12C1: {YIL_SAYISI} yıl gerekli, {len(dosyalar)} dosya var")
    dosyalar = sorted(dosyalar)[-YIL_SAYISI:]
    yillar = [p.name.split(".")[1][1:5] for p in dosyalar]
    to = tarim_orani_hesapla([mcd12c1_kesit(p) for p in dosyalar])
    yazilan = {}
    for grid in ("005", "025"):
        da, not_ = izgaraya(to, grid)
        isleme = (f"MCD12C1 {SDS_YUZDE}: (%{TARIM_SINIFI} + {MOZAIK_AGIRLIK:g}·%{MOZAIK_SINIFI}) / 100, "
                  f"{yillar[0]}–{yillar[-1]} ortalaması ({len(yillar)} yıl); {not_}")
        da.attrs = _ortak_attrs(MCD12C1, SDS_YUZDE, "1", "Tarım alanı oranı (IGBP 12 + ½·14)", isleme, grid)
        da.attrs["donem"] = f"{yillar[0]}–{yillar[-1]} ortalaması"
        ds = da.to_dataset(name="tarim_orani")
        ds.attrs = dict(da.attrs)
        sorun = check_contract(ds, static=True)
        if sorun:
            raise ValueError(f"tarim_orani {grid} sözleşmeye uymuyor: {sorun}")
        yazilan[grid] = write_netcdf(ds, processed_path("tarim_orani", "MCD12C1", grid))
        if grid == "025":
            paket = Path(paket) if paket else OUTPUTS_DIR / f"trend-dedektifi-turkiye-{surum}"
            hedef = paket / "L1_kup" / "tarim_orani__MCD12C1.nc"
            if hedef.exists():                    # hesaplamadan önce de bak: boşuna çalışma
                raise FileExistsError(f"{hedef} zaten var; mevcut L1 dosyasının üzerine yazılmaz")
            kes = crop_to_bbox(ds)
            kes.attrs = release_attrs(ds, "tarim_orani", "MCD12C1", surum)
            sorun = check_contract(kes, static=True)
            if sorun:
                raise ValueError(f"L1 tarim_orani sözleşmeye uymuyor: {sorun}")
            yazilan["L1"] = yeni_dosya_yaz(kes, hedef)
    yazilan["yillar"] = yillar
    return yazilan


def yeni_dosya_yaz(ds: xr.Dataset, hedef: Path) -> Path:
    """Yalnız YENİ dosya yazar; hedef varsa FileExistsError (yayın paketindeki dosyalar değişmesin)."""
    hedef = Path(hedef)
    if hedef.exists():
        raise FileExistsError(f"{hedef} zaten var; mevcut dosyanın üzerine yazılmaz")
    return write_netcdf(ds, hedef)


# ---------------------------------------------------------------- GFSAD → sulanan oran (doğrulama)
def gfsad_oran(tif: Path, grid: str, bbox=TURKIYE_BBOX) -> xr.DataArray:
    """1 km sınıf haritasından hücre başına sulanan piksel oranı (payda: kara sınıfları 1–5 ve 9)."""
    import rasterio
    from rasterio.windows import from_bounds
    lat_t, lon_t = grid_coords(grid, bbox)
    res = GRID_RES[grid]
    w, s, e, n = bbox
    with rasterio.open(tif) as src:
        win = from_bounds(w, s, e, n, src.transform).round_offsets().round_lengths()
        a = src.read(1, window=win)
        tr = src.window_transform(win)
    rows, cols = np.indices(a.shape)
    lon_p = tr.c + (cols + 0.5) * tr.a
    lat_p = tr.f + (rows + 0.5) * tr.e
    iy = np.floor((lat_p - s) / res).astype(int)
    ix = np.floor((lon_p - w) / res).astype(int)
    ok = (iy >= 0) & (iy < lat_t.size) & (ix >= 0) & (ix < lon_t.size)
    kara = np.isin(a, KARA_SINIFLARI) & ok
    sul = np.isin(a, SULANAN_SINIFLAR) & ok
    k = iy * lon_t.size + ix
    n_kara = np.bincount(k[kara], minlength=lat_t.size * lon_t.size).reshape(lat_t.size, lon_t.size)
    n_sul = np.bincount(k[sul], minlength=lat_t.size * lon_t.size).reshape(lat_t.size, lon_t.size)
    beklenen = (res / abs(tr.a)) ** 2
    with np.errstate(invalid="ignore", divide="ignore"):
        oran = np.where(n_kara >= max(MIN_PIKSEL, 0.3 * beklenen), n_sul / n_kara, np.nan)
    return xr.DataArray(oran.astype("float32"), coords={"lat": lat_t, "lon": lon_t}, dims=("lat", "lon"),
                        name="sulanan_oran")


def sulanan_oran_uret(tif: Path, surum: str = "v0.1", paket: Path | None = None) -> dict:
    """<paket>/dogrulama/sulanan_oran__GFSAD1KCM.nc (0,25°, yayın kutusu) ve __005.nc (0,05°)."""
    from data.export import OUTPUTS_DIR, YAYIN_BBOX
    from data.regions import domain_mask
    paket = Path(paket) if paket else OUTPUTS_DIR / f"trend-dedektifi-turkiye-{surum}"
    hedef = paket / "dogrulama"
    yazilan = {}
    for grid, bbox, ad in (("025", YAYIN_BBOX, "sulanan_oran__GFSAD1KCM.nc"),
                           ("005", TURKIYE_BBOX, "sulanan_oran__GFSAD1KCM__005.nc")):
        da = gfsad_oran(tif, grid, bbox)
        m = domain_mask("land", da["lat"].values, da["lon"].values)
        if m is not None:
            da = da.where(m)
        da.attrs = _ortak_attrs(GFSAD, "Crop Mask (sınıf 1–5)", "1",
                                "Sulanan tarım piksel oranı (GFSAD1KCM sınıf 1 + 2)",
                                f"1 km pikseller hücre merkezine göre {GRID_RES[grid]:g}° hücrelere sayıldı; "
                                f"oran = sınıf {SULANAN_SINIFLAR} / sınıf {KARA_SINIFLARI}; "
                                f"en az {MIN_PIKSEL} geçerli piksel; land maskesi", grid)
        da.attrs.update(donem="2010 (nominal)", kullanim="YALNIZ DOĞRULAMA; sulama izi hesabına girmez",
                        kademe=np.int32(2), dogrulanmadi="evet")
        yazilan[grid] = write_netcdf(da.to_dataset(), hedef / ad)
    return yazilan


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m data.arazi", description=__doc__.splitlines()[0])
    ap.add_argument("--surum", default="v0.1")
    ap.add_argument("--indir", action="store_true", help="eksik ham dosyaları indir (earthaccess, netrc)")
    ap.add_argument("--yillar", default="2021-2025")
    a = ap.parse_args(argv)
    if a.indir:
        y = tuple(int(x) for x in a.yillar.split("-"))
        r = indir(y)
        print(f"indirildi: {r['gb']:.2f} GB, {r['sure'] / 60:.1f} dk")
    mcd = ham_dosyalar("MCD12C1", "MCD12C1.A*.hdf")
    tif = ham_dosyalar("GFSAD1KCM", "GFSAD1KCM*.tif")
    t0 = time.time()
    y = tarim_orani_uret(mcd, a.surum)
    print(f"tarim_orani ({y['yillar'][0]}–{y['yillar'][-1]}): {y['005']}, {y['025']}, {y['L1']}")
    if tif:
        s = sulanan_oran_uret(tif[0], a.surum)
        print(f"sulanan_oran (doğrulama): {s['025']}, {s['005']}")
    else:
        print("GFSAD1KCM dosyası yok: doğrulama katmanı üretilmedi")
    print(f"süre: {time.time() - t0:.0f} sn")


if __name__ == "__main__":
    main()
