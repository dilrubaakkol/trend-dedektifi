"""data/catalog.yaml okuyucusu. Değişken ve ürün kayıtlarına tek erişim noktası."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

CATALOG_PATH = Path(__file__).resolve().parent / "catalog.yaml"


@lru_cache(maxsize=1)
def load_catalog(path: str | None = None) -> dict:
    """Kataloğu okur; her değişken kaydına ürün bilgisini ``urun_bilgi`` olarak ekler."""
    cat = yaml.safe_load(Path(path or CATALOG_PATH).read_text(encoding="utf-8"))
    for key, p in cat["urunler"].items():
        p["anahtar"] = key
    for v in cat["degiskenler"]:
        if v["urun"] not in cat["urunler"]:
            raise ValueError(f"catalog.yaml: {v['ad']} bilinmeyen ürüne bağlı: {v['urun']}")
        v["urun_bilgi"] = cat["urunler"][v["urun"]]
    return cat


def product(key: str) -> dict:
    """Ürün kaydı (anahtar: ör. "GLDAS")."""
    return load_catalog()["urunler"][key]


def variables(names=None, categories=None, include_secondary: bool = True,
              only_active: bool = False) -> list[dict]:
    """Değişken kayıtlarını filtreler.

    names: ad listesi ya da None/"all"; categories: kategori listesi; ikisi birlikte verilirse birleşim.
    """
    allv = load_catalog()["degiskenler"]
    if names in (None, "all", ["all"]) and not categories:
        sel = list(allv)
    else:
        names = set() if names in (None, "all", ["all"]) else set(names)
        categories = set(categories or [])
        sel = [v for v in allv if v["ad"] in names or v["kategori"] in categories]
        unknown = names - {v["ad"] for v in allv}
        if unknown:
            raise KeyError(f"Katalogda olmayan değişken(ler): {sorted(unknown)}")
    if not include_secondary:
        sel = [v for v in sel if v.get("ana")]
    if only_active:
        sel = [v for v in sel if v["urun_bilgi"].get("durum", "aktif") == "aktif"]
    return sel


def variable(name: str, product_key: str | None = None) -> dict:
    """Bir değişkenin kaydı. product_key verilmezse ana ürün; ürün anahtarı ya da dosya_kodu olabilir."""
    cands = [v for v in load_catalog()["degiskenler"] if v["ad"] == name]
    if not cands:
        raise KeyError(f"Katalogda yok: {name}")
    if product_key is None:
        main = [v for v in cands if v.get("ana")]
        return (main or cands)[0]
    for v in cands:
        if product_key in (v["urun"], v["urun_bilgi"]["dosya_kodu"], v["urun_bilgi"]["short_name"]):
            return v
    raise KeyError(f"{name} için ürün yok: {product_key}. Seçenekler: {[v['urun'] for v in cands]}")


def unverified() -> list[str]:
    """katalog_dogrulanmadi: true olan ürün ve değişkenlerin listesi (rapor için)."""
    cat = load_catalog()
    out = [f"ürün {k}: {p.get('not', '')}" for k, p in cat["urunler"].items() if p.get("katalog_dogrulanmadi")]
    out += [f"değişken {v['ad']} ({v['urun']}): {v['dosya_degiskeni']}"
            for v in cat["degiskenler"] if v.get("katalog_dogrulanmadi")]
    return out
