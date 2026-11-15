"""Sınır dosyalarını BİR KEZ üretir: data/boundaries/{iller,kara,denizler}.geojson

Kaynak: Natural Earth 10m (kamu malı), sabit commit'ten indirilir. Ayrıntı: data/boundaries/README.md
Sonuç dosyaları repoya girer; bu betiği yalnızca sınırları yenilemek gerekirse çalıştırın:

    python -m data.make_boundaries                    # Türkiye (iller, kara, denizler)
    python -m data.make_boundaries --ulke yunanistan  # başka ülke: boundaries/<ulke>/{kara,kutu_kara}.geojson
"""

from __future__ import annotations

import json
import tempfile
import urllib.request
from pathlib import Path

import shapely
from shapely.geometry import box, mapping, shape
from shapely.geometry.base import BaseGeometry

from data.grid import TURKIYE_BBOX

NE_COMMIT = "ca96624a56bd078437bca8184e78163e5039ad19"
NE_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
          f"{NE_COMMIT}/geojson/{{name}}.geojson")
OUT_DIR = Path(__file__).resolve().parent / "boundaries"

# Natural Earth deniz adı → bizim anahtarımız
SEAS = {
    "Black Sea": "deniz_karadeniz",
    "Sea of Marmara": "deniz_marmara", "Bosporus": "deniz_marmara", "Dardanelles": "deniz_marmara",
    "Aegean Sea": "deniz_ege", "Sea of Crete": "deniz_ege",
    "Mediterranean Sea": "deniz_akdeniz",
}
SEA_LABELS = {"deniz_karadeniz": "Karadeniz (deniz)", "deniz_marmara": "Marmara Denizi",
              "deniz_ege": "Ege Denizi", "deniz_akdeniz": "Akdeniz (deniz)"}

TOL = 0.005  # sadeleştirme toleransı, derece (~500 m); 0,05° ızgaradan 10 kat ince


def _round(obj, nd=4):
    """GeoJSON koordinatlarını nd ondalığa yuvarlar (dosya boyutu için)."""
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, (list, tuple)):
        return [_round(o, nd) for o in obj]
    if isinstance(obj, dict):
        return {k: _round(v, nd) for k, v in obj.items()}
    return obj


def _fc(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def _write(path: Path, fc: dict) -> None:
    path.write_text(json.dumps(_round(fc), ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    print(f"  {path.name}: {path.stat().st_size / 1024:.0f} KB")


def _download(name: str, folder: Path) -> dict:
    target = folder / f"{name}.geojson"
    print(f"  indiriliyor: {name}")
    urllib.request.urlretrieve(NE_URL.format(name=name), target)
    return json.loads(target.read_text(encoding="utf-8"))


def build(out_dir: Path = OUT_DIR) -> None:
    """Natural Earth'ten il, kara ve deniz sınırlarını indirip sadeleştirerek yazar."""
    from data.regions import il_adi, normalize_name  # döngüsel içe aktarmayı önlemek için burada

    out_dir.mkdir(parents=True, exist_ok=True)
    clip = box(*TURKIYE_BBOX).buffer(1.0)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        adm1 = _download("ne_10m_admin_1_states_provinces", tmp)
        land = _download("ne_10m_land", tmp)
        islands = _download("ne_10m_minor_islands", tmp)
        marine = _download("ne_10m_geography_marine_polys", tmp)

    # 1) İller: 81 il, ortak kenarları bozmadan sadeleştir (coverage_simplify)
    tr = [f for f in adm1["features"] if f["properties"].get("adm0_a3") == "TUR"]
    if len(tr) != 81:
        raise RuntimeError(f"81 il bekleniyordu, {len(tr)} bulundu")
    geoms = shapely.coverage_simplify([shape(f["geometry"]) for f in tr], TOL)
    feats = []
    for f, g in sorted(zip(tr, geoms), key=lambda x: x[0]["properties"]["iso_3166_2"]):
        p = f["properties"]
        ad = il_adi(p["name_tr"])  # il_adlari.yaml düzeltmeleri (ör. Elâzığ → Elazığ)
        feats.append({"type": "Feature",
                      "properties": {"plaka": int(p["iso_3166_2"].split("-")[1]), "ad": ad,
                                     "anahtar": normalize_name(ad), "iso_3166_2": p["iso_3166_2"]},
                      "geometry": mapping(shapely.make_valid(g))})
    _write(out_dir / "iller.geojson", _fc(feats))

    # 2) Kara (tüm ülkeler, deniz maskesi için): kutuya kes + sadeleştir
    polys = [shape(f["geometry"]) for f in land["features"] + islands["features"]]
    polys = [p.intersection(clip) for p in polys if p.intersects(clip)]
    land_u = shapely.make_valid(shapely.union_all(polys).simplify(TOL, preserve_topology=True))
    _write(out_dir / "kara.geojson",
           _fc([{"type": "Feature", "properties": {"ad": "kara"}, "geometry": mapping(land_u)}]))

    # 3) Denizler: Natural Earth deniz poligonları → 4 anahtar; karadan arındır
    seas: dict[str, list] = {}
    for f in marine["features"]:
        key = SEAS.get(f["properties"].get("name"))
        if key:
            seas.setdefault(key, []).append(shape(f["geometry"]).intersection(clip))
    feats = []
    for key, parts in sorted(seas.items()):
        g = shapely.union_all(parts).difference(land_u).simplify(TOL, preserve_topology=True)
        feats.append({"type": "Feature",
                      "properties": {"anahtar": key, "ad": SEA_LABELS[key]},
                      "geometry": mapping(shapely.make_valid(g))})
    _write(out_dir / "denizler.geojson", _fc(feats))


def _admin0(fc: dict, iso3: str, ne_adi: str) -> BaseGeometry:
    """Natural Earth admin-0 içinden ülke çokgeni (ADM0_A3 = iso3; ad tutarlılık için denetlenir)."""
    for f in fc["features"]:
        p = {k.upper(): v for k, v in f["properties"].items()}
        if p.get("ADM0_A3") == iso3:
            if ne_adi not in (p.get("NAME"), p.get("ADMIN"), p.get("NAME_LONG")):
                raise RuntimeError(f"{iso3}: Natural Earth adı {p.get('NAME')!r}, ulkeler.yaml'da {ne_adi!r}")
            return shapely.make_valid(shape(f["geometry"]))
    raise RuntimeError(f"Natural Earth admin-0'da {iso3} yok")


def build_ulke(anahtar: str, out_dir: Path = OUT_DIR) -> dict:
    """Türkiye dışındaki bir ülke için ``boundaries/<ulke>/kara.geojson`` (Natural Earth admin-0 ülke sınırı,
    adalar dahil) ve ``kutu_kara.geojson`` (kutudaki bütün kara; deniz maskesi için) yazar.

    Türkiye dosyalarına dokunmaz (Türkiye için ``build()``). Döndürür: {"sinir": dış kutu, "yayin_kutusu": …}.
    """
    from data.ulkeler import ulke, varsayilan_mi, yayin_kutusu_hesapla
    if varsayilan_mi(anahtar):
        raise ValueError("Türkiye sınırları build() ile üretilir; bu fonksiyon Türkiye dosyalarına dokunmaz")
    u = ulke(anahtar)
    hedef = out_dir / anahtar
    hedef.mkdir(parents=True, exist_ok=True)
    clip = box(*u["ic_kutu"]).buffer(1.0)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        adm0 = _download("ne_10m_admin_0_countries", tmp)
        land = _download("ne_10m_land", tmp)
        islands = _download("ne_10m_minor_islands", tmp)
    g = _admin0(adm0, u["iso3"], u["ne_adi"]).intersection(clip)
    g = shapely.make_valid(g.simplify(TOL, preserve_topology=True))
    _write(hedef / "kara.geojson", _fc([{"type": "Feature",
                                          "properties": {"ad": u["ad"], "iso3": u["iso3"], "kaynak":
                                                         "Natural Earth 10m admin-0 (kamu malı)"},
                                          "geometry": mapping(g)}]))
    polys = [shape(f["geometry"]) for f in land["features"] + islands["features"]]
    polys = [p.intersection(clip) for p in polys if p.intersects(clip)]
    land_u = shapely.make_valid(shapely.union_all(polys).simplify(TOL, preserve_topology=True))
    _write(hedef / "kutu_kara.geojson",
           _fc([{"type": "Feature", "properties": {"ad": "kara"}, "geometry": mapping(land_u)}]))
    sinir = tuple(round(v, 4) for v in g.bounds)
    yk = yayin_kutusu_hesapla(sinir)
    w, s, e, n = u["ic_kutu"]
    if not (yk[0] >= w and yk[1] >= s and yk[2] <= e and yk[3] <= n):
        raise RuntimeError(f"yayın kutusu {yk} işleme kutusunun {u['ic_kutu']} dışına taşıyor")
    print(f"  {u['ad']} sınırının dış kutusu: {sinir}; 0,25° hizalı yayın kutusu: {list(yk)} "
          f"(ulkeler.yaml yayin_kutusu ile aynı olmalı)")
    return {"sinir": sinir, "yayin_kutusu": yk}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Sınır dosyalarını üretir (Natural Earth, kamu malı).")
    ap.add_argument("--ulke", default=None, help="Türkiye dışında bir ülke: boundaries/<ulke>/ yazılır")
    a = ap.parse_args()
    build_ulke(a.ulke) if a.ulke else build()
