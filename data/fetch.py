"""NASA verisini earthaccess ile çeker ve Türkiye kesitini cache/raw/<urun>/ altına yazar.

Akış (ürün başına):
  1. earthaccess.login(strategy="netrc") — şifre/token asla istenmez ya da yazdırılmaz.
  2. search_data(short_name, version, Türkiye bbox, dönem).
  3. Boyut tahmini; çok büyükse (ya da günlük ürünse) --onay olmadan durur ve sorar.
  4. TEK AY indirilir/okunur ve doğrulanır (değişkenler var mı, değerler boş mu).
  5. Kalan aylar paralel işlenir. Var olan kesit dosyası tekrar indirilmez.
  6. Hata veren dosyalar atlanır, sonda listelenir (cache/raw/<urun>/_rapor.json).

Ham kesit dosyası: cache/raw/<urun>/<granül>.nc — orijinal değişken adları (güvenli adla),
ORİJİNAL birim ve ham değerler (ölçek/bayrak uygulanmamış), lat artan, lon -180..180,
TURKIYE_BBOX + 1° pay. Birim dönüşümü, bayraklar ve ızgara: data/harmonize.py.

Kullanım:
    python -m data.fetch --urun GLDAS --test          # yalnız tek ay
    python -m data.fetch --urun GLDAS,MERRA2_SLV      # tüm dönem
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from data.catalog import load_catalog, product, variables
from data.grid import RAW_DIR, ulke_kutusu
from data.ulkeler import aktif, ulke_yazimi, varsayilan_mi

MARGIN = 1.0              # kesit payı, derece (kaba ürünlerin kenar interpolasyonu için)
SIZE_LIMIT_GB = 30.0      # bunun üstünde --onay gerekir
WORKERS = 6
RETRIES = 2


# ---------------------------------------------------------------- yardımcılar

def safe_name(name: str) -> str:
    """HDF değişken adını NetCDF için güvenli ada çevirir ("CMG 0.05 Deg Monthly NDVI" → "CMG_0_05_Deg_Monthly_NDVI")."""
    return re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")


def product_vars(key: str) -> list[str]:
    """Bir üründen okunacak dosya değişkenleri (katalogdaki tüm değişkenler + kalite değişkenleri)."""
    out = []
    for v in load_catalog()["degiskenler"]:
        if v["urun"] != key:
            continue
        out.append(v["dosya_degiskeni"])
        if v.get("kalite"):
            out.append(v["kalite"]["degisken"])
    return list(dict.fromkeys(out))


def granule_begin(g) -> pd.Timestamp:
    """Granülün başlangıç zamanı (UMM TemporalExtent)."""
    te = g["umm"].get("TemporalExtent", {})
    rng = te.get("RangeDateTime") or {}
    s = rng.get("BeginningDateTime") or te.get("SingleDateTime")
    return pd.Timestamp(s).tz_localize(None) if s else pd.NaT


def granule_name(g) -> str:
    return g["umm"].get("GranuleUR", "granul").split(":")[-1]


def raw_dir(key: str) -> Path:
    """Ham kesit klasörü: Türkiye ``cache/raw/<urun>/`` (eskisi gibi), diğer ülkeler ``cache/raw/<ulke>/<urun>/``."""
    return RAW_DIR / key if varsayilan_mi() else RAW_DIR / aktif() / key


def _bbox_margin():
    """Aktif ülkenin işleme kutusu + ``MARGIN`` pay (Türkiye: TURKIYE_BBOX + 1°)."""
    w, s, e, n = ulke_kutusu()
    return w - MARGIN, s - MARGIN, e + MARGIN, n + MARGIN


def _normalize_geo(ds: xr.Dataset) -> xr.Dataset:
    """Koordinat adlarını lat/lon yapar, lon'u -180..180'e çevirir, lat'ı artan sıralar, bbox'a keser."""
    ren = {}
    for c in list(ds.coords) + list(ds.dims):
        lc = str(c).lower()
        if lc in ("latitude", "lat", "ydim") and c != "lat":
            ren[c] = "lat"
        elif lc in ("longitude", "lon", "xdim") and c != "lon":
            ren[c] = "lon"
    ds = ds.rename(ren)
    if float(ds["lon"].max()) > 180:
        ds = ds.assign_coords(lon=((ds["lon"] + 180) % 360) - 180)
    ds = ds.sortby("lon").sortby("lat")
    w, s, e, n = _bbox_margin()
    return ds.sel(lat=slice(s, n), lon=slice(w, e))


def _set_time(ds: xr.Dataset, when: pd.Timestamp, zaman: str) -> xr.Dataset:
    """Tek granüllük kesite zaman ekler: aylıkta ayın 1'i, günlükte gün."""
    if "time" in ds.dims:
        ds = ds.isel(time=0, drop=True)
    for c in ("time", "time_bnds"):
        if c in ds.variables:
            ds = ds.drop_vars(c)
    t = when.normalize() if zaman == "gunluk" else when.to_period("M").to_timestamp()
    return ds.expand_dims(time=[t])


def _strip_codec_attrs(da: xr.DataArray) -> xr.DataArray:
    """Ölçek/dolgu attrs'ını 'hdf_' önekine taşır (xarray yeniden okurken uygulamasın diye)."""
    attrs = {}
    for k, v in da.attrs.items():
        if k in ("scale_factor", "add_offset", "_FillValue", "missing_value", "valid_range",
                 "valid_min", "valid_max", "MissingValue", "ScaleFactor", "Offset"):
            attrs[f"hdf_{k}"] = np.asarray(v).tolist()
        elif isinstance(v, (str, int, float, np.number)):
            attrs[k] = v if not isinstance(v, np.number) else v.item()
        elif isinstance(v, bytes):
            attrs[k] = v.decode("utf-8", "ignore")
    da.attrs = attrs
    da.encoding = {}
    return da


# ---------------------------------------------------------------- okuyucular

def read_netcdf(src, p: dict, names: list[str], when, group=None) -> xr.Dataset:
    """NetCDF4/HDF5 (MERRA-2, GLDAS, GPM, GRACE, MODIS-Aqua L3m) → Türkiye kesiti (dolgu → NaN, paketli değerler ölçekli)."""
    ds = xr.open_dataset(src, engine="h5netcdf", group=group, mask_and_scale=True,
                         decode_times=bool(p.get("tek_dosya")), decode_timedelta=False)
    missing = [n for n in names if n not in ds.data_vars]
    if missing:
        raise KeyError(f"dosyada yok: {missing}; mevcut: {list(ds.data_vars)[:40]}")
    ds = ds[names]
    for n in names:
        if ds[n].dims[-2:] == ("lon", "lat"):  # IMERG: (time, lon, lat)
            ds[n] = ds[n].transpose(*ds[n].dims[:-2], "lat", "lon")
    ds = _normalize_geo(ds).load()
    if not p.get("tek_dosya"):
        ds = _set_time(ds, when, p["zaman"])
    for n in names:  # dolgu/ölçek xarray tarafından uygulandı (mask_and_scale=True)
        ds[n] = _strip_codec_attrs(ds[n])
    return ds.rename({n: safe_name(n) for n in names})


def _gctp_geo_axes(struct_meta: str, ny: int, nx: int):
    """HDF-EOS GCTP_GEO ızgarası için hücre merkezi lat/lon dizileri (DMS paketli köşelerden)."""
    def dms(v):  # DDDMMMSSS.SS → derece
        v = float(v)
        sign = -1 if v < 0 else 1
        v = abs(v)
        d = int(v // 1_000_000)
        m = int((v - d * 1_000_000) // 1000)
        s = v - d * 1_000_000 - m * 1000
        return sign * (d + m / 60 + s / 3600)
    ul = re.search(r"UpperLeftPointMtrs=\(([-\d.]+),([-\d.]+)\)", struct_meta)
    lr = re.search(r"LowerRightMtrs=\(([-\d.]+),([-\d.]+)\)", struct_meta)
    x0, y0, x1, y1 = dms(ul.group(1)), dms(ul.group(2)), dms(lr.group(1)), dms(lr.group(2))
    dx, dy = (x1 - x0) / nx, (y1 - y0) / ny
    lon = x0 + dx * (np.arange(nx) + 0.5)
    lat = y0 + dy * (np.arange(ny) + 0.5)
    return np.round(lat, 6), np.round(lon, 6)


def _index_window(axis: np.ndarray, lo: float, hi: float) -> slice:
    idx = np.where((axis >= lo) & (axis <= hi))[0]
    return slice(int(idx.min()), int(idx.max()) + 1)


def read_hdf4_cmg(path, p: dict, names: list[str], when) -> xr.Dataset:
    """MODIS CMG HDF4 (MOD10CM, MOD13C2, MOD11C3) → Türkiye kesiti, ham DN değerleri."""
    from pyhdf.SD import SD, SDC
    h = SD(str(path), SDC.READ)
    try:
        sm = h.attributes().get("StructMetadata.0", "")
        out = {}
        lat = lon = None
        for n in names:
            sds = h.select(n)
            ny, nx = sds.info()[2]
            if lat is None:
                lat_all, lon_all = _gctp_geo_axes(sm, ny, nx)
                w, s, e, nn = _bbox_margin()
                ri, ci = _index_window(lat_all, s, nn), _index_window(lon_all, w, e)
                lat, lon = lat_all[ri], lon_all[ci]
            arr = np.asarray(sds[ri.start:ri.stop, ci.start:ci.stop])
            da = xr.DataArray(arr, dims=("lat", "lon"), coords={"lat": lat, "lon": lon},
                              attrs=sds.attributes())
            out[safe_name(n)] = _strip_codec_attrs(da)
            sds.endaccess()
    finally:
        h.end()
    ds = xr.Dataset(out).sortby("lat")
    return _set_time(ds, when, p["zaman"])


def read_hdfeos5_grid(src, p: dict, names: list[str], when) -> xr.Dataset:
    """OMI L3 HDF-EOS5 ızgaraları (OMNO2d, OMTO3e, OMSO2e) → Türkiye kesiti."""
    import h5py
    with h5py.File(src, "r") as h:
        sm = h["HDFEOS INFORMATION/StructMetadata.0"][()].decode("utf-8", "ignore")
        grp = h[p["grid_yolu"]]
        out = {}
        for n in names:
            d = grp[n]
            ny, nx = d.shape[-2:]
            lat_all, lon_all = _gctp_geo_axes(sm, ny, nx)
            w, s, e, nn = _bbox_margin()
            ri, ci = _index_window(lat_all, s, nn), _index_window(lon_all, w, e)
            arr = d[..., ri, ci].astype("float32")
            fill = d.attrs.get("_FillValue", d.attrs.get("MissingValue"))
            if fill is not None:
                arr[arr == np.asarray(fill).ravel()[0]] = np.nan
            da = xr.DataArray(arr, dims=("lat", "lon"),
                              coords={"lat": lat_all[ri], "lon": lon_all[ci]},
                              attrs={k: d.attrs[k] for k in d.attrs})
            out[safe_name(n)] = _strip_codec_attrs(da)
    return _set_time(xr.Dataset(out).sortby("lat"), when, "gunluk")


def read_srtm_dem(path, p: dict, names: list[str], when) -> xr.Dataset:
    """SRTMGL30 karosu (.zip içinde .dem + .hdr, big-endian int16) → Türkiye kesiti."""
    path = Path(path)
    with zipfile.ZipFile(path) as z:
        dem_name = next(n for n in z.namelist() if n.lower().endswith(".dem"))
        hdr_names = [n for n in z.namelist() if n.lower().endswith(".hdr")]
        hdr = (dict(line.split()[:2] for line in z.read(hdr_names[0]).decode().splitlines()
                    if line.strip()) if hdr_names else {})
        raw = z.read(dem_name)
    if not hdr:
        # SRTMGL30 zip'inde .hdr yok: GTOPO30 karo kuralı — ad eXXXnYY / wXXXsYY = sol üst köşe,
        # 30 yay saniyesi, 4800 sütun (40°), satır sayısı dosya boyutundan, big-endian int16.
        m = re.search(r"([ew])(\d{3})([ns])(\d{2})", dem_name.lower())
        x0 = int(m.group(2)) * (1 if m.group(1) == "e" else -1)
        y0 = int(m.group(4)) * (1 if m.group(3) == "n" else -1)
        step = 1 / 120
        hdr = {"NCOLS": 4800, "NROWS": len(raw) // 2 // 4800, "XDIM": step, "YDIM": step,
               "ULXMAP": x0 + step / 2, "ULYMAP": y0 - step / 2, "BYTEORDER": "M"}
    nrows, ncols = int(hdr["NROWS"]), int(hdr["NCOLS"])
    dt = ">i2" if str(hdr.get("BYTEORDER", "M")).upper() == "M" else "<i2"
    arr = np.frombuffer(raw, dtype=dt).reshape(nrows, ncols)
    land = arr[arr != -9999]
    if land.size and not (-500 <= np.median(land) <= 6000 and land.max() <= 9000):
        raise ValueError("SRTM değerleri makul değil (bayt sırası/geometri hatalı olabilir)")
    xdim, ydim = float(hdr["XDIM"]), float(hdr["YDIM"])
    lon_all = np.round(float(hdr["ULXMAP"]) + xdim * np.arange(ncols), 7)  # ULXMAP = ilk hücre merkezi
    lat_all = np.round(float(hdr["ULYMAP"]) - ydim * np.arange(nrows), 7)
    w, s, e, n = ulke_kutusu()
    ri = np.where((lat_all >= s) & (lat_all <= n))[0]
    ci = np.where((lon_all >= w) & (lon_all <= e))[0]
    if ri.size == 0 or ci.size == 0:
        raise ValueError(f"karo {aktif()} kutusuyla kesişmiyor")
    sub = arr[ri.min():ri.max() + 1, ci.min():ci.max() + 1].astype("int16")
    da = xr.DataArray(sub, dims=("lat", "lon"),
                      coords={"lat": lat_all[ri.min():ri.max() + 1],
                              "lon": lon_all[ci.min():ci.max() + 1]},
                      attrs={"units": "m", "hdf_nodata": -9999})
    return xr.Dataset({"elevation": da}).sortby("lat")


READERS = {"netcdf": read_netcdf, "hdf5_grid": read_netcdf, "hdf4_cmg": read_hdf4_cmg,
           "hdfeos5_grid": read_hdfeos5_grid, "srtm_dem": read_srtm_dem}


# ---------------------------------------------------------------- Cloud OPeNDAP (sunucuda kesme)

_DAP4_NS = "{http://xml.opendap.org/ns/DAP/4.0#}"
_DAP4_TYPES = ("Float32", "Float64", "Int8", "UInt8", "Int16", "UInt16", "Int32", "UInt32",
               "Int64", "UInt64", "Byte")
_tls = threading.local()
_plan_lock = threading.Lock()
# netCDF4/HDF5 C kütüphaneleri iş parçacığı güvenli değil: yerel dosya okuma/yazma bu kilitle sıralanır
# (ağ istekleri paralel kalır). Kilitsiz çalıştırmada süreç izsiz çöküyordu.
IO_LOCK = threading.RLock()
_PLANS: dict[str, dict] = {}


def _session():
    """İş parçacığı başına Earthdata yetkili requests oturumu (netrc girişinden)."""
    if not hasattr(_tls, "s"):
        import earthaccess
        _tls.s = earthaccess.get_requests_https_session()
    return _tls.s


def opendap_url(g) -> str:
    """Granülün Cloud OPeNDAP adresi (UMM RelatedUrls, Subtype 'OPENDAP DATA')."""
    for u in g["umm"].get("RelatedUrls", []):
        if str(u.get("Subtype", "")).upper() == "OPENDAP DATA":
            return u["URL"]
    raise LookupError("granülde OPeNDAP adresi yok")


def _parse_dmr(xml_text: str) -> dict:
    """DAP4 DMR → {fqn: {"name", "dims": [dim fqn], "type"}} ve boyut uzunlukları."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_text)
    out, sizes = {}, {}

    def walk(node, prefix):
        for ch in node:
            tag = ch.tag.replace(_DAP4_NS, "")
            if tag == "Dimension":
                sizes[f"{prefix}/{ch.get('name')}"] = int(ch.get("size"))
            elif tag == "Group":
                walk(ch, f"{prefix}/{ch.get('name')}")
            elif tag in _DAP4_TYPES:
                dims = [d.get("name") for d in ch if d.tag.replace(_DAP4_NS, "") == "Dim"]
                out[f"{prefix}/{ch.get('name')}"] = {"name": ch.get("name"), "dims": dims, "type": tag}
    walk(root, "")
    return {"vars": out, "sizes": sizes}


def _axis_of(dim: str) -> str:
    d = dim.lower().split("/")[-1]
    if d.startswith(("lat", "ydim")) or d == "y":
        return "lat"
    if d.startswith(("lon", "xdim")) or d == "x":
        return "lon"
    if "time" in d:
        return "time"
    return d


def _dap_get(url: str, ce: str, dest: Path) -> Path:
    """DAP4 isteğini netCDF4 olarak indirir."""
    from urllib.parse import quote
    full = f"{url}.dap.nc4?dap4.ce={quote(ce, safe='/_')}"
    r = _session().get(full, timeout=600, stream=True)
    if r.status_code != 200:
        raise RuntimeError(f"OPeNDAP HTTP {r.status_code}: {r.text[:200]}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as fh:
        for chunk in r.iter_content(1 << 20):
            fh.write(chunk)
    return dest


def _read_nc_var(path: Path, basename: str, decode: bool) -> np.ndarray:
    """netCDF4 dosyasında (gruplar dahil) adı basename olan değişkeni okur."""
    import netCDF4
    with netCDF4.Dataset(path) as nc:
        stack = [nc]
        while stack:
            grp = stack.pop()
            if basename in grp.variables:
                v = grp.variables[basename]
                v.set_auto_maskandscale(decode)
                arr = v[...]
                if np.ma.isMaskedArray(arr):
                    arr = arr.astype("float64").filled(np.nan) if decode else arr.data
                return np.asarray(arr)
            stack.extend(grp.groups.values())
    raise KeyError(f"yanıtta değişken yok: {basename}")


def _opendap_plan(key: str, url: str, names: list[str], tmp: Path) -> dict:
    """Ürün için (bir kez) DMR'yi okuyup değişken yollarını ve Türkiye indeks aralığını belirler."""
    plan_key = f"{aktif()}:{key}"          # indeks aralığı ülkeye özgü: başka ülkenin planı kullanılmasın
    with _plan_lock:
        if plan_key in _PLANS:
            return _PLANS[plan_key]
        r = _session().get(url + ".dmr.xml", timeout=120)
        r.raise_for_status()
        dmr = _parse_dmr(r.text)
        by_name = {}
        for fqn, info in dmr["vars"].items():
            by_name.setdefault(info["name"], fqn)
        vars_ = {}
        for n in names:
            fqn = by_name.get(safe_name(n)) or by_name.get(n)
            if fqn is None:
                raise KeyError(f"OPeNDAP'ta değişken yok: {n}; mevcut: {sorted(by_name)[:40]}")
            vars_[n] = fqn
        dims = dmr["vars"][vars_[names[0]]]["dims"]
        lat_dim = next(d for d in dims if _axis_of(d) == "lat")
        lon_dim = next(d for d in dims if _axis_of(d) == "lon")
        # koordinat değerleri: 1B koordinat değişkeni ya da 2B Latitude/Longitude'dan bir kesit
        if lat_dim in dmr["vars"] and lon_dim in dmr["vars"]:
            ce = f"{lat_dim};{lon_dim}"
            lat_name, lon_name, two_d = lat_dim.split("/")[-1], lon_dim.split("/")[-1], False
        else:
            lat2 = by_name.get("Latitude") or by_name.get("lat")
            lon2 = by_name.get("Longitude") or by_name.get("lon")
            two_d = len(dmr["vars"][lat2]["dims"]) == 2
            if two_d:
                ny, nx = dmr["sizes"].get(lat_dim), dmr["sizes"].get(lon_dim)
                ce = f"{lat2}[0:1:{ny - 1}][0];{lon2}[0][0:1:{nx - 1}]"
            else:
                ce = f"{lat2};{lon2}"
            lat_name, lon_name = lat2.split("/")[-1], lon2.split("/")[-1]
        cpath = _dap_get(url, ce, tmp / f"_{key}_koordinat.nc4")
        with IO_LOCK:
            lat_all = _read_nc_var(cpath, lat_name, True).ravel().astype("float64")
            lon_all = _read_nc_var(cpath, lon_name, True).ravel().astype("float64")
        cpath.unlink(missing_ok=True)
        lon_all = np.where(lon_all > 180, lon_all - 360, lon_all)
        w, s, e, n_ = _bbox_margin()
        ri = _index_window(lat_all, s, n_)
        ci = _index_window(lon_all, w, e)
        plan = {"vars": vars_, "dmr": dmr, "lat_dim": lat_dim, "lon_dim": lon_dim, "ri": ri, "ci": ci,
                "lat": np.round(lat_all[ri], 6), "lon": np.round(lon_all[ci], 6), "two_d": two_d}
        _PLANS[plan_key] = plan
        return plan


def read_opendap(g, p: dict, names: list[str], when, tmp: Path) -> xr.Dataset:
    """Cloud OPeNDAP ile sunucuda Türkiye kesiti alır. HDF4 ürünlerde ham DN korunur."""
    url = opendap_url(g)
    plan = _opendap_plan(p["anahtar"], url, names, tmp)
    decode = not str(p["okuyucu"]).startswith("hdf4")
    parts = []
    for n in names:
        fqn = plan["vars"][n]
        idx = []
        for d in plan["dmr"]["vars"][fqn]["dims"]:
            ax = _axis_of(d)
            sl = plan["ri"] if ax == "lat" else plan["ci"] if ax == "lon" else None
            if sl is None:
                size = plan["dmr"]["sizes"].get(d, 1)
                idx.append(f"[0:1:{size - 1}]")
            else:
                idx.append(f"[{sl.start}:1:{sl.stop - 1}]")
        parts.append(fqn + "".join(idx))
    dest = tmp / f"{Path(granule_name(g)).stem}.dap.nc4"
    _dap_get(url, ";".join(parts), dest)
    out = {}
    with IO_LOCK:
        return _dap_to_dataset(dest, plan, names, decode, when, p)


def _dap_to_dataset(dest, plan, names, decode, when, p) -> xr.Dataset:
    """İndirilen DAP4 yanıtını (lat, lon) kesit Dataset'ine çevirir (IO_LOCK altında çağrılır)."""
    out = {}
    try:
        for n in names:
            fqn = plan["vars"][n]
            arr = _read_nc_var(dest, fqn.split("/")[-1], decode)
            axes = [_axis_of(d) for d in plan["dmr"]["vars"][fqn]["dims"]]
            # zaman ve diğer tekil boyutları at, (lat, lon) sırasına getir
            keep = [i for i, a in enumerate(axes) if a in ("lat", "lon")]
            for i in sorted((i for i, a in enumerate(axes) if a not in ("lat", "lon")), reverse=True):
                if arr.shape[i] != 1:
                    raise ValueError(f"{n}: beklenmeyen boyut {axes[i]}={arr.shape[i]}")
                arr = np.take(arr, 0, axis=i)
            sub_axes = [axes[i] for i in keep]
            if sub_axes == ["lon", "lat"]:
                arr = arr.T
            if not decode:  # ham DN: tamsayı tipini koru (bayrak/ölçek harmonize'da)
                arr = np.asarray(arr)
            out[safe_name(n)] = xr.DataArray(arr, dims=("lat", "lon"),
                                             coords={"lat": plan["lat"], "lon": plan["lon"]})
    finally:
        dest.unlink(missing_ok=True)
    ds = xr.Dataset(out).sortby("lat").sortby("lon")
    return _set_time(ds, when, p["zaman"])


# ---------------------------------------------------------------- tek granül

def _process_one(g, p: dict, names: list[str], out: Path, tmp: Path) -> Path:
    """Bir granülü okuyup Türkiye kesitini out'a yazar. Var olan dosyayı yeniden işlemez."""
    if out.exists():
        return out
    import earthaccess
    reader = READERS.get(p["okuyucu"])
    if reader is None and p["erisim"] != "opendap":
        raise NotImplementedError(f"okuyucu yok: {p['okuyucu']}")
    when = granule_begin(g)
    if p["erisim"] == "opendap":
        ds = read_opendap(g, p, names, when, tmp)
    elif p["erisim"] == "stream":
        f = earthaccess.open([g], show_progress=False)[0]
        kw = {"group": p["grup"]} if p.get("grup") else {}
        with IO_LOCK:
            ds = reader(f, p, names, when, **kw)
    else:
        tmp.mkdir(parents=True, exist_ok=True)
        files = earthaccess.download([g], str(tmp), show_progress=False)
        files = [Path(x) for x in files if not str(x).endswith((".xml", ".jpg", ".png", ".cmr.xml"))]
        if not files:
            raise RuntimeError("indirme dosya döndürmedi")
        src = files[0]
        try:
            with IO_LOCK:
                ds = reader(src, p, names, when)
        finally:
            if p.get("keep_raw", False):
                keep = raw_dir(p["anahtar"]) / "orijinal"
                keep.mkdir(parents=True, exist_ok=True)
                for x in files:
                    if Path(x).exists():
                        shutil.move(str(x), keep / Path(x).name)
            else:
                for x in files:
                    Path(x).unlink(missing_ok=True)
    if any(int(ds.sizes.get(d, 0)) == 0 for d in ("lat", "lon")):
        raise ValueError(f"{ulke_yazimi()} kesiti boş")
    ds.attrs.update(source_granule=granule_name(g), source_product=p["short_name"],
                    source_version=str(p["version"]))
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out.with_suffix(f".{threading.get_ident()}.tmp")
    with IO_LOCK:
        ds.to_netcdf(tmp_out, engine="netcdf4")
    tmp_out.replace(out)
    return out


def _validate(path: Path, names: list[str]) -> str:
    """Tek-ay deneme dosyasını açar; sorun yoksa kısa özet döndürür, varsa hata fırlatır."""
    with IO_LOCK, xr.open_dataset(path) as ds:
        parts = []
        for n in names:
            v = ds[safe_name(n)]
            vals = v.values.astype("float64")
            fin = np.isfinite(vals)
            if not fin.any():
                raise ValueError(f"{n}: tüm değerler boş")
            parts.append(f"{n} [{np.nanmin(vals):.4g} … {np.nanmax(vals):.4g}] {v.attrs.get('units', '?')}")
        return f"{dict(ds.sizes)}; " + "; ".join(parts)


# ---------------------------------------------------------------- ürün

def search(key: str, start: str | None = None, end: str | None = None) -> list:
    """Ürünün Türkiye kutusu ve dönem için granüllerini bulur (aylık ürünlerde ay başına bir)."""
    import earthaccess
    p, cat = product(key), load_catalog()
    s = max(pd.Period(start or cat["donem"][0]), pd.Period(p["valid_start"]))
    e = pd.Period(end or cat["donem"][1])
    # Türkiye'de ulke_kutusu() = catalog.yaml bbox = TURKIYE_BBOX (testle sınanır)
    kw = dict(short_name=p["short_name"], version=str(p["version"]), bounding_box=tuple(ulke_kutusu()))
    if p["zaman"] not in ("sabit",) and not p.get("tek_dosya"):
        kw["temporal"] = (s.start_time.strftime("%Y-%m-%d"), e.end_time.strftime("%Y-%m-%d"))
    gs = earthaccess.search_data(**kw)
    if p.get("granul_deseni"):
        gs = [g for g in gs if p["granul_deseni"] in granule_name(g)]
    if p["zaman"] == "aylik":  # ay başına tek granül; dönem dışını at
        seen, keep = set(), []
        for g in sorted(gs, key=granule_begin):
            m = granule_begin(g).to_period("M")
            if s <= m <= e and m not in seen:
                seen.add(m)
                keep.append(g)
        gs = keep
    return gs


def login():
    """Earthdata girişi (yalnızca netrc). Başarısızsa RuntimeError."""
    import earthaccess
    auth = earthaccess.login(strategy="netrc")
    if not getattr(auth, "authenticated", False):
        raise RuntimeError("Earthdata girişi başarısız (_netrc). Durduruldu.")
    return auth


def fetch_product(key: str, start=None, end=None, test_only=False, onay=False,
                  workers=WORKERS) -> dict:
    """Bir ürünü çeker. Döndürür: {"urun", "granul", "tamam", "atlanan", "hatalar", "durum", ...}."""
    p = product(key)
    names = product_vars(key)
    rep = {"urun": key, "short_name": p["short_name"], "granul": 0, "tamam": 0, "atlanan": 0,
           "hatalar": [], "durum": ""}
    if p.get("durum") == "ertelendi" and not onay:
        rep["durum"] = f"ertelendi: {p.get('not', '')}"
        print(f"[{key}] {rep['durum']}")
        return rep
    login()
    gs = search(key, start, end)
    rep["granul"] = len(gs)
    if not gs:
        rep["durum"] = "granül bulunamadı"
        print(f"[{key}] {rep['durum']}")
        return rep
    total_mb = sum(float(g.size or 0) for g in gs)
    rep["toplam_mb"] = round(total_mb, 1)
    print(f"[{key}] {len(gs)} granül, kaynak toplamı ~{total_mb / 1024:.1f} GB "
          f"({p['erisim']}: {'tam indirme' if p['erisim'] == 'download' else f'yalnız {ulke_yazimi()} kesiti aktarılır'})")
    big = (p["erisim"] == "download" and total_mb / 1024 > SIZE_LIMIT_GB) or p["zaman"] == "gunluk"
    if big and not onay and not test_only:
        rep["durum"] = (f"onay gerekli: ~{total_mb / 1024:.0f} GB / {len(gs)} dosya. "
                        "Tek ay denendi; tüm dönem için --onay ile çalıştırın.")
        test_only = True

    d = raw_dir(key)
    tmp = d / "_indirilen"
    outs = {granule_name(g): d / (Path(granule_name(g)).stem + ".nc") for g in gs}

    # 1) tek ay denemesi
    g0 = gs[len(gs) // 2] if len(gs) > 2 else gs[0]
    t0 = time.time()
    try:
        path0 = _process_one(g0, p, names, outs[granule_name(g0)], tmp)
        summary = _validate(path0, names)
        print(f"[{key}] tek ay denemesi TAMAM ({granule_begin(g0):%Y-%m}, {time.time() - t0:.1f} s): {summary}")
    except Exception as ex:
        rep["durum"] = f"tek ay denemesi başarısız: {type(ex).__name__}: {ex}"
        print(f"[{key}] {rep['durum']}")
        _save_report(d, rep)
        return rep
    if test_only:
        rep["tamam"] = 1
        rep["durum"] = rep["durum"] or "yalnız tek ay denendi"
        _save_report(d, rep)
        return rep

    # 2) tüm dönem
    todo = [g for g in gs if not outs[granule_name(g)].exists()]
    rep["atlanan"] = len(gs) - len(todo)
    print(f"[{key}] {rep['atlanan']} dosya önbellekte, {len(todo)} işlenecek")
    n_done, t_start = 0, time.time()

    def work(g):
        last = None
        for attempt in range(RETRIES + 1):
            try:
                return _process_one(g, p, names, outs[granule_name(g)], tmp / str(attempt))
            except Exception as ex:  # ağ hatası vb.: yeniden dene
                last = ex
                time.sleep(2 * (attempt + 1))
        raise last

    nw = min(workers, 3) if p["erisim"] == "download" else workers
    with ThreadPoolExecutor(max_workers=nw) as ex:
        futs = {ex.submit(work, g): g for g in todo}
        for fut in as_completed(futs):
            g = futs[fut]
            n_done += 1
            try:
                fut.result()
                rep["tamam"] += 1
                mark = "ok"
            except Exception as e:
                rep["hatalar"].append({"granul": granule_name(g), "hata": f"{type(e).__name__}: {e}"[:300]})
                mark = "HATA"
            if n_done % 10 == 0 or n_done == len(todo) or mark == "HATA":
                el = time.time() - t_start
                eta = el / n_done * (len(todo) - n_done)
                print(f"[{key}] {n_done}/{len(todo)} {granule_begin(g):%Y-%m-%d} {mark} "
                      f"(geçen {el / 60:.1f} dk, kalan ~{eta / 60:.1f} dk)", flush=True)
    shutil.rmtree(tmp, ignore_errors=True)
    rep["tamam"] += rep["atlanan"]
    rep["durum"] = "tamam" if not rep["hatalar"] else f"{len(rep['hatalar'])} dosya hatalı"
    _save_report(d, rep)
    if rep["hatalar"]:
        print(f"[{key}] Hatalı dosyalar:")
        for h in rep["hatalar"]:
            print(f"   - {h['granul']}: {h['hata']}")
    return rep


def _save_report(d: Path, rep: dict) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "_rapor.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")


def products_for(var_names=None, categories=None, include_secondary=True) -> list[str]:
    """Seçili değişkenlerin ihtiyaç duyduğu ürün anahtarları (katalog sırasıyla)."""
    vs = variables(var_names, categories, include_secondary=include_secondary)
    return list(dict.fromkeys(v["urun"] for v in vs))


def main(argv=None):
    ap = argparse.ArgumentParser(description="NASA verisini seçili ülke için çek (earthaccess; varsayılan Türkiye).")
    ap.add_argument("--ulke", default=None, help="data/ulkeler.yaml anahtarı (varsayılan turkiye)")
    ap.add_argument("--urun", help="virgülle ürün anahtarları (catalog.yaml 'urunler')")
    ap.add_argument("--vars", help="ya da değişken adları (virgülle)")
    ap.add_argument("--baslangic", default=None)
    ap.add_argument("--bitis", default=None)
    ap.add_argument("--test", action="store_true", help="yalnız tek ay")
    ap.add_argument("--onay", action="store_true", help="büyük/ertelenmiş ürünleri de indir")
    ap.add_argument("--workers", type=int, default=WORKERS)
    a = ap.parse_args(argv)
    from data.ulkeler import ulke_baglami
    keys = a.urun.split(",") if a.urun else products_for(a.vars.split(",") if a.vars else None)
    with ulke_baglami(a.ulke):
        reps = [fetch_product(k, a.baslangic, a.bitis, a.test, a.onay, a.workers) for k in keys]
    print("\nÖZET")
    for r in reps:
        print(f"  {r['urun']:14s} {r['tamam']}/{r['granul']}  {r['durum']}")


if __name__ == "__main__":
    main()
