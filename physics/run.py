"""L4 ilişkiler katmanını üretir: L1 küplerini okur, ``L4_iliski/`` klasörünü yazar (Faz 5).

    python -m physics.run --surum v0.1        # gerçek veri: outputs/trend-dedektifi-turkiye-v0.1/
    python -m physics.run --paket <klasör>    # başka bir paket kökü
    python -m physics.run --sentetik          # deneme: cache/physics/L4_iliski__YER_TUTUCU/
    python -m physics.run --ciftler <yaml>    # başka bir çift ayar dosyası (varsayılan physics/ciftler.yaml)

Girdi: ``<paket>/L1_kup/<degisken>__<urun>.nc`` (Kişi 1, ``python -m data.export``).
Çıktı (docs/sozlesmeler.md 2.3):
    <paket>/L4_iliski/ciftler.csv
    <paket>/L4_iliski/iliski__<d1>__<d2>[__gecikmeN].nc

Kural: yayın paketine asla sentetik sonuç yazılmaz. ``--sentetik`` sonuçları yalnız
``cache/physics/`` altına, "YER TUTUCU" işaretiyle gider.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import xarray as xr

from physics.ciftler import AYAR_DOSYASI, CIFTLER, Cift, ciftleri_yukle
from physics.harita import cift_haritasi, etiket_ozeti
from physics.tablo import _ortak_alanlar, ciftler_tablosu, csv_yaz


def gereken_girdiler(ciftler: tuple[Cift, ...] = CIFTLER) -> list[str]:
    """Çiftlerin ihtiyaç duyduğu L1 dosyaları: ``["<degisken>__<urun>", …]``."""
    return sorted({f"{c.d1}__{c.u1}" for c in ciftler} | {f"{c.d2}__{c.u2}" for c in ciftler})


GEREKEN = gereken_girdiler()
YER_TUTUCU_NOTU = "Bu dosyadaki sayılar YER TUTUCUDUR (sentetik veri), gerçek sonuç değildir."


def sentetik_mi(da: xr.DataArray) -> bool:
    """Girdi sentetik mi? (Kişi 1 kuralı: ürün kodu SENTETIK ya da ``yer_tutucu`` attr'ı.)"""
    a = da.attrs
    return ("SENTETIK" in str(a.get("source_product", "")).upper()
            or "SENTETIK" in str(a.get("file", "")).upper()
            or bool(a.get("yer_tutucu")) or "YER TUTUCU" in str(a.get("urun_surumu", "")))


def l1_oku(paket: Path, gereken: list[str] | None = None) -> dict[str, xr.DataArray]:
    """``<paket>/L1_kup/`` içinden çiftlerin girdilerini okur; bulunamayanlar atlanır (uyarıyla)."""
    kup = Path(paket) / "L1_kup"
    veri, eksik = {}, []
    for ad in (GEREKEN if gereken is None else gereken):
        f = kup / f"{ad}.nc"
        if not f.exists():
            eksik.append(ad)
            continue
        with xr.open_dataset(f) as ds:
            degisken = ad.split("__")[0]
            da = ds[degisken] if degisken in ds else ds[list(ds.data_vars)[0]]
            da = da.load()
            da.attrs = {**ds.attrs, **da.attrs}
        veri[ad] = da
    if eksik:
        print(f"UYARI: L1 dosyası yok, ilgili çiftler atlanacak: {', '.join(eksik)}")
    return veri


def _nc_attrs(ds: xr.Dataset, ortak: dict, sentetik: bool) -> xr.Dataset:
    ds.attrs.update({k: v for k, v in ortak.items() if v != ""})
    ds.attrs["dogrulanmadi"] = ortak["dogrulanmadi"] or "hayır"
    ds.attrs["uretim"] = "python -m physics.run (Kişi 3, L4)"
    if sentetik:
        ds.attrs["yer_tutucu"] = YER_TUTUCU_NOTU
    return ds


def l4_yaz(veri: dict[str, xr.DataArray], hedef: Path, iller: bool = True,
           ciftler: tuple[Cift, ...] | None = None) -> dict:
    """Haritaları ve ``ciftler.csv``'yi ``hedef`` klasörüne yazar; özet döndürür.

    ciftler : işlenecek çiftler (varsayılan ``physics/ciftler.yaml``).
    """
    ciftler = CIFTLER if ciftler is None else ciftler
    hedef = Path(hedef)
    hedef.mkdir(parents=True, exist_ok=True)
    sentetik = any(sentetik_mi(v) for v in veri.values())
    ozet = {"dosyalar": [], "etiketler": {}, "sentetik": sentetik}

    for c in ciftler:
        k1, k2 = f"{c.d1}__{c.u1}", f"{c.d2}__{c.u2}"
        if not (c.harita and k1 in veri and k2 in veri):
            continue
        ortak = _ortak_alanlar(c, veri[k1], veri[k2])
        for ad, ds in cift_haritasi(c, veri[k1], veri[k2]):
            _nc_attrs(ds, ortak, sentetik)
            kod = {v: {"_FillValue": np.float32(np.nan)} for v in ("r", "etkin_n", "p", "p_fdr")}
            kod.update({v: {"_FillValue": None} for v in ("anlamli", "etiket")})
            ds.to_netcdf(hedef / ad, encoding=kod)
            ozet["dosyalar"].append(hedef / ad)
            ozet["etiketler"][ad] = etiket_ozeti(ds)

    df = ciftler_tablosu(veri, iller=iller, ciftler=ciftler)
    if sentetik:
        df["not"] = (YER_TUTUCU_NOTU + " " + df["not"].fillna("")).str.strip()
    ozet["dosyalar"].append(csv_yaz(df, hedef / "ciftler.csv"))
    ozet["tablo"] = df
    return ozet


def _yazdir(ozet: dict) -> None:
    print("SENTETİK VERİ (YER TUTUCU)" if ozet["sentetik"] else "GERÇEK VERİ")
    for ad, e in ozet["etiketler"].items():
        print(f"  {ad:58s} beklenen {e['beklenen_yonde']:4d} · ters {e['ters_yonde']:4d} · "
              f"anlamsız {e['anlamsiz']:4d} · hesaplanamadı {e['hesaplanamadi']:4d}")
    df = ozet["tablo"]
    say = df.groupby(["cift_no", "gecikme_ay"])["etiket"].value_counts().unstack(fill_value=0)
    print("  ciftler.csv:", len(df), "satır")
    print(say.to_string())
    ters = df[df["etiket"] == "ters_yonde"]
    if len(ters):
        print("  ters_yonde satırları (incelenmeli):")
        for _, r in ters.iterrows():
            print(f"    çift {r['cift_no']} · {r['bolge_adi']} · r = {r['r']:.2f}")
    for f in ozet["dosyalar"]:
        print(" ", f)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--surum", default="v0.1")
    ap.add_argument("--paket", type=Path, default=None,
                    help="paket kökü (varsayılan outputs/trend-dedektifi-turkiye-<surum>)")
    ap.add_argument("--sentetik", action="store_true",
                    help="sentetik deneme verisi; çıktı yalnız cache/physics/ altına")
    ap.add_argument("--iller-yok", action="store_true", help="il satırlarını atla (hızlı deneme)")
    ap.add_argument("--ciftler", type=Path, default=AYAR_DOSYASI,
                    help="çift ayar dosyası (varsayılan physics/ciftler.yaml)")
    a = ap.parse_args(argv)
    ciftler = ciftleri_yukle(a.ciftler)

    from data.export import OUTPUTS_DIR
    from data.grid import CACHE_DIR

    if a.sentetik:
        from physics.ornek_l4 import ornek_veri
        veri = ornek_veri()
        hedef = Path(CACHE_DIR) / "physics" / "L4_iliski__YER_TUTUCU"
    else:
        paket = a.paket or OUTPUTS_DIR / f"trend-dedektifi-turkiye-{a.surum}"
        if not (paket / "L1_kup").exists():
            raise SystemExit(f"L1 paketi yok: {paket / 'L1_kup'}. Önce Kişi 1'in "
                             f"'python -m data.export --surum {a.surum}' komutu çalışmalı.")
        veri = l1_oku(paket, gereken_girdiler(ciftler))
        if not veri:
            raise SystemExit("L1_kup içinde çiftlerin hiçbir girdisi yok.")
        if any(sentetik_mi(v) for v in veri.values()):
            raise SystemExit("L1_kup içinde sentetik dosya var; yayın paketine yazılmadı.")
        hedef = paket / "L4_iliski"
    _yazdir(l4_yaz(veri, hedef, iller=not a.iller_yok, ciftler=ciftler))


if __name__ == "__main__":
    main()
