"""İki ülkenin L4 sonuçlarını yan yana koyar: aynı motor, aynı 6 fizik çifti, farklı ülke.

    python -m physics.ulke_karsilastirma --surum v0.1 --ulke yunanistan
    # → outputs/trend-dedektifi-<ulke>-v0.1/L4_iliski/ulke_karsilastirma.csv

Önce iki pakette de ``python -m physics.run`` çalışmış olmalı (Yunanistan: ``--ulke yunanistan``).
Türkiye satırı ``bolge_turu = turkiye``, diğer ülkenin satırı ``bolge_turu = ulke``. Yalnız okur; L4 dosyalarını
değiştirmez.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

SUTUNLAR = ["cift_no", "cift", "seri", "gecikme_ay", "beklenen_yon"]
DEGERLER = ["hucre_sayisi", "donem", "n", "r", "etkin_n", "p", "etiket"]


def ulke_satirlari(paket: Path) -> pd.DataFrame:
    """Paketin ülke düzeyi satırları (Türkiye: ``turkiye``, diğerleri: ``ulke``)."""
    df = pd.read_csv(Path(paket) / "L4_iliski" / "ciftler.csv", encoding="utf-8-sig", dtype={"bolge_kodu": str})
    return df[df["bolge_turu"].isin(["turkiye", "ulke"])][SUTUNLAR + ["bolge_adi"] + DEGERLER]


def karsilastir(paket_a: Path, paket_b: Path) -> pd.DataFrame:
    a, b = ulke_satirlari(paket_a), ulke_satirlari(paket_b)
    ad_a, ad_b = a["bolge_adi"].iloc[0], b["bolge_adi"].iloc[0]
    out = a.drop(columns="bolge_adi").merge(b.drop(columns="bolge_adi"), on=SUTUNLAR, how="outer",
                                            suffixes=(f"_{ad_a}", f"_{ad_b}"))
    out["ayni_etiket"] = out[f"etiket_{ad_a}"] == out[f"etiket_{ad_b}"]
    return out.sort_values(["cift_no", "gecikme_ay"]).reset_index(drop=True)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m physics.ulke_karsilastirma", description=__doc__.splitlines()[0])
    ap.add_argument("--surum", default="v0.1")
    ap.add_argument("--ulke", default="yunanistan")
    ap.add_argument("--paket-a", type=Path, default=None, help="varsayılan Türkiye paketi")
    ap.add_argument("--paket-b", type=Path, default=None, help="varsayılan outputs/trend-dedektifi-<ulke>-<surum>")
    a = ap.parse_args(argv)
    from data.export import OUTPUTS_DIR
    pa = a.paket_a or OUTPUTS_DIR / f"trend-dedektifi-turkiye-{a.surum}"
    pb = a.paket_b or OUTPUTS_DIR / f"trend-dedektifi-{a.ulke}-{a.surum}"
    for p in (pa, pb):
        if not (p / "L4_iliski" / "ciftler.csv").exists():
            raise SystemExit(f"{p / 'L4_iliski' / 'ciftler.csv'} yok: önce python -m physics.run --paket {p}")
    df = karsilastir(pa, pb)
    yol = pb / "L4_iliski" / "ulke_karsilastirma.csv"
    df.to_csv(yol, index=False, encoding="utf-8-sig", float_format="%.4g")
    r_sut = [c for c in df.columns if c.startswith("r_")]
    e_sut = [c for c in df.columns if c.startswith("etiket_")]
    print("AYNI MOTOR, İKİ ÜLKE (ülke düzeyi satırlar)")
    for _, s in df.iterrows():
        g = f" g{int(s['gecikme_ay'])}" if s["gecikme_ay"] else ""
        print(f"  çift {int(s['cift_no'])}{g} ({s['beklenen_yon']}) {s['cift'][:48]:48s} " + " · ".join(
            f"{c[2:]}: r {s[c]:+.2f} {s[e]}" for c, e in zip(r_sut, e_sut)))
    print(f"  aynı etiket: {int(df['ayni_etiket'].sum())}/{len(df)}")
    print(" ", yol)


if __name__ == "__main__":
    main()
