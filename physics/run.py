"""Kişi 3'ün tüm analizleri tek bölge için uçtan uca: veri → sınır, ayna, kayma, iklim hızı.

    python -m physics.run dogu_anadolu            # kar: sınır, ayna, kayma (ekrana özet)
    python -m physics.run --test butce            # su bütçesi (varsayılan bölge demo:konya)
    python -m physics.run --test cc               # Clausius-Clapeyron (Karadeniz + Türkiye kara)
    python -m physics.run dogu_anadolu --yaz      # gerçek veri: cache/results/fizik_<bolge>.json
                                                  # sentetik:    cache/physics/fizik_<bolge>.json

Veri Kişi 1'in ``data.load`` fonksiyonuyla okunur. Gerçek dosya yoksa ``data.load`` sentetiğe
düşer; bu durumda sonuç dosyası "YER TUTUCU" olarak işaretlenir ve arayüz bunu gösterir.

Kişi 2'nin fonksiyonları gelene kadar trend haritası ve kış ortalaması
``physics/_gecici_trend.py``'den gelir.
"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np

from physics._gecici_trend import trend_map, winter_mean
from physics.boundary import find_boundary
from physics.mirror import find_mirror_clusters
from physics.shift import boundary_shift
from physics.tests_physical import clausius_clapeyron, climate_velocity, water_budget

SICAKLIK_URUNLERI = ("MERRA2", "GLDAS")  # ilki ana ürün (etiketi o belirler)


def _yukle(degisken, region, grid, product=None, sentetik="otomatik"):
    from data import load
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        da = load(degisken, region=region, grid=grid, product=product, sentetik=sentetik)
    sent = "SENTETIK" in str(da.attrs.get("file", "")) or any("ENTET" in str(x.message) for x in w)
    return da, sent


def analyze_region(region: str = "dogu_anadolu", sentetik="otomatik", n_boot: int = 1000,
                   variable: str = "kar_ortusu") -> dict:
    """Bir bölge için Kişi 3 analizlerini çalıştırır; ``{"analyses": [...], "sentetik": bool}``."""
    kaynaklar = {}
    kar, kaynaklar["kar_ortusu"] = _yukle(variable, region, "005", sentetik=sentetik)
    z05, kaynaklar["rakim_005"] = _yukle("rakim", region, "005", sentetik=sentetik)
    z25, kaynaklar["rakim_025"] = _yukle("rakim", region, "025", sentetik=sentetik)

    kar_kis = winter_mean(kar)
    kar_kis = kar_kis.where(kar_kis["kis"] >= 2002, drop=True)  # Kararlar, madde 5
    tm = trend_map(kar_kis)

    analyses = [
        find_boundary(tm["slope"], rakim=z05, region=region, variable=variable, n_boot=n_boot),
        find_mirror_clusters(tm["slope"], tm["anlamli"], rakim=z05, region=region,
                             variable=variable),
    ]
    analyses[1]["clusters"] = analyses[1]["clusters"][:10]

    tahminler = []
    for urun in SICAKLIK_URUNLERI:
        try:
            T, kaynaklar[f"sicaklik_{urun}"] = _yukle("sicaklik_2m", region, "025", urun,
                                                       sentetik=sentetik)
        except (FileNotFoundError, KeyError, ValueError) as e:
            warnings.warn(f"sicaklik_2m {urun} okunamadı: {e}")
            continue
        T_kis = winter_mean(T)
        T_kis = T_kis.where(T_kis["kis"] >= 2002, drop=True)
        tahminler.append(climate_velocity(T_kis, z25, region=region, urun=urun))
    analyses.extend(tahminler)
    analyses.append(boundary_shift(kar_kis, z05, tahminler=tahminler, region=region,
                                   variable=variable))

    sentetik_mi = any(kaynaklar.values())
    trend_ozet = {
        "id": f"trend_haritasi_{variable}_{region}",
        "type": "trend_map_summary",
        "region": region,
        "variable": variable,
        "fdr_fraction_significant": round(float(tm["anlamli"].where(np.isfinite(tm["slope"])).mean()), 3),
        "note": "GEÇİCİ trend haritası (physics/_gecici_trend.py); Kişi 2'nin haritası gelince değişecek.",
    }
    return {"analyses": [trend_ozet] + analyses, "sentetik": sentetik_mi, "kaynaklar": kaynaklar}


def _yukle_varsa(degisken, region, grid="025", product=None, sentetik="otomatik", kaynaklar=None):
    """``_yukle`` gibi; dosya yoksa uyarıp None döndürür."""
    try:
        da, sent = _yukle(degisken, region, grid, product, sentetik=sentetik)
    except (FileNotFoundError, KeyError, ValueError) as e:
        warnings.warn(f"{degisken} {product or ''} okunamadı: {e}")
        return None
    if kaynaklar is not None:
        kaynaklar[f"{degisken}_{product or 'ana'}"] = sent
    return da


def analyze_budget(region: str = "demo:konya", sentetik="otomatik") -> dict:
    """Su bütçesi kapanışı (Adım 7a). P: GPM (ana), GLDAS, MERRA2; ET, R: GLDAS."""
    k = {}
    grace = _yukle_varsa("toplam_su_depolama", region, sentetik=sentetik, kaynaklar=k)
    yagis = {}
    for urun in (None, "GLDAS", "MERRA2"):  # None = ana ürün (GPM)
        p = _yukle_varsa("yagis", region, product=urun, sentetik=sentetik, kaynaklar=k)
        if p is not None:
            yagis[urun or "GPM"] = p
    et = _yukle_varsa("buharlasma", region, sentetik=sentetik, kaynaklar=k)
    rs = _yukle_varsa("yuzey_akisi", region, sentetik=sentetik, kaynaklar=k)
    rb = _yukle_varsa("taban_akisi", region, sentetik=sentetik, kaynaklar=k)
    if grace is None or not yagis or et is None or rs is None:
        raise FileNotFoundError("su bütçesi için GRACE, yağış, buharlaşma ve yüzey akışı gerekli")
    a = water_budget(grace, yagis, et, rs, rb, region=region.replace("demo:", ""))
    return {"analyses": [a], "sentetik": any(k.values()), "kaynaklar": k}


def analyze_cc(deniz: str = "deniz_karadeniz", kara: str = "turkiye", sentetik="otomatik") -> dict:
    """Clausius-Clapeyron (Adım 7b): deniz etiketli, kara etiketsiz; özgül nem + su buharı kolonu."""
    k, analyses = {}, []
    for nem_d in ("ozgul_nem_2m", "su_buhari_kolon"):
        for bolge, etiketli in ((deniz, True), (kara, False)):
            q = _yukle_varsa(nem_d, bolge, sentetik=sentetik, kaynaklar=k)
            t = _yukle_varsa("sicaklik_2m", bolge, product="MERRA2", sentetik=sentetik, kaynaklar=k)
            if q is None or t is None:
                continue
            analyses.append(clausius_clapeyron(q, t, region=bolge, nem_degisken=nem_d,
                                               urun="MERRA2", etiketli=etiketli))
    if not analyses:
        raise FileNotFoundError("Clausius-Clapeyron için nem ve sıcaklık dosyaları gerekli")
    return {"analyses": analyses, "sentetik": any(k.values()), "kaynaklar": k}


KART = {"kar": "kar_isinma", "butce": "su_kaynaklari", "cc": "nem_artisi"}


def results_dosyasi(region: str, sonuc: dict, card_id: str = "kar_isinma") -> dict:
    """Arayüzün okuduğu ``results.json`` biçimine sarar (docs/sozlesmeler.md, Bölüm 2)."""
    from data.regions import region_bounds
    d = {
        "run_id": f"fizik_{card_id}_{region}",
        "question": None,
        "region": {"name": region.replace("demo:", ""), "bbox": list(region_bounds(region))},
        "period": ["2001-01", "2025-12"],
        "card_id": card_id,
        "analyses": sonuc["analyses"],
    }
    if sonuc["sentetik"]:
        d["_not"] = "Bu dosyadaki sayilar YER TUTUCUDUR (sentetik veri), gercek sonuc degildir."
    return d


def _ozet(sonuc: dict) -> None:
    print("SENTETİK VERİ (yer tutucu)" if sonuc["sentetik"] else "GERÇEK VERİ")
    for a in sonuc["analyses"]:
        t = a["type"]
        if t == "boundary":
            print(f"  sınır       : {a['boundary_m']} m, %95 {a['boundary_ci95_m']} ({a['status']})")
        elif t == "mirror":
            print(f"  ayna        : eksen={a['suggested_axis']} kümeler={a['n_clusters']} "
                  f"{a.get('note', '')}")
        elif t == "climate_velocity":
            print(f"  tahmin {a['product']:6s}: {a['predicted_shift_m_per_decade']} m/10 yıl "
                  f"(dT/dt {a['dTdt_C_per_decade']} °C/10 yıl, dT/dz {a['dTdz_C_per_km']} °C/km)")
        elif t == "boundary_shift":
            print(f"  gözlenen    : {a['observed_shift_m_per_decade']} m/10 yıl "
                  f"(eğim {a.get('observed_slope_m_per_decade')}, MK p {a.get('mk_p')})")
            print(f"  ETİKET      : {a.get('label')} — {a.get('label_reason')}")
        elif t == "water_budget":
            print(f"  GRACE eğimi : {a.get('grace_slope_mm_per_year')} mm/yıl")
            print(f"  P − ET − R  : {a.get('p_et_r_by_product')} mm/yıl")
            print(f"  artık       : {a.get('residual_mm_per_year')} mm/yıl")
            print(f"  ETİKET      : {a.get('label')} — {a.get('note')}")
        elif t == "clausius_clapeyron":
            print(f"  CC {a['variable']:16s} {a['region']:16s}: {a['slope_pct_per_C']} %/°C "
                  f"→ {a.get('label', 'bilgi (etiketsiz)')}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bolge", nargs="?", default=None,
                    help="kar: dogu_anadolu, butce: demo:konya, cc: deniz_karadeniz (varsayılan)")
    ap.add_argument("--test", choices=("kar", "butce", "cc"), default="kar")
    ap.add_argument("--yaz", action="store_true", help="sonucu JSON olarak yaz (sentetikse cache/physics/)")
    ap.add_argument("--n-boot", type=int, default=1000)
    a = ap.parse_args(argv)
    varsayilan = {"kar": "dogu_anadolu", "butce": "demo:konya", "cc": "deniz_karadeniz"}
    bolge = a.bolge or varsayilan[a.test]
    try:
        if a.test == "kar":
            sonuc = analyze_region(bolge, n_boot=a.n_boot)
        elif a.test == "butce":
            sonuc = analyze_budget(bolge)
        else:
            sonuc = analyze_cc(deniz=bolge)
    except FileNotFoundError as e:
        raise SystemExit(f"Veri eksik: {e}. Kişi 1'in cache/processed/turkiye/ dosyaları gerekli "
                         f"(bkz. physics/KISI3_PLAN.md).")
    _ozet(sonuc)
    if a.yaz:
        from data.grid import CACHE_DIR
        # cache/results/ yalnız gerçek sonuçlar içindir (arayüz oradan okur; Kişi 5'in testi
        # buradaki dosyaların yer tutucu olmamasını bekler). Sentetik sonuç cache/physics/'e gider.
        klasor = "physics" if sonuc["sentetik"] else "results"
        ad = bolge.replace("demo:", "")
        yol = Path(CACHE_DIR) / klasor / f"fizik_{a.test}_{ad}.json"
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(json.dumps(results_dosyasi(bolge, sonuc, KART[a.test]), ensure_ascii=False,
                                  indent=1, default=float), encoding="utf-8")
        print(yol)


if __name__ == "__main__":
    main()
