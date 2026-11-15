"""Motorun bağımsız fizik sınavı: ön kayıtlı, geliştirmede kullanılmamış çiftlerde beklenen yön tutuyor mu?

    python -m physics.bagimsiz_sinav --surum v0.1     # → <paket>/L4_iliski/sinav/bagimsiz_sinav.csv

Çiftler ve başarı ölçütü ``physics/sinav/bagimsiz_ciftler.yaml`` içinde, motor çalıştırılmadan önce yazıldı.
Dosyanın SHA-256 özeti çıktıya yazılır. Yöntem ``physics.tek_cift.hesapla`` ile aynıdır (L4 yöntemi).
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd
import yaml

ON_KAYIT = Path(__file__).resolve().parent / "sinav" / "bagimsiz_ciftler.yaml"
ON_KAYIT_SHA256 = "18ad7722b6d2ebe398d251063ab5f2336864e603205eae788b803fb6b7d2651b"
FIZIK_MIN_BEKLENEN = 0.60
FIZIK_MAX_TERS = 1


def ozet(yol: Path = ON_KAYIT) -> str:
    """Ön kayıt dosyasının SHA-256 özeti (satır sonu farkı sayılmaz)."""
    return hashlib.sha256(Path(yol).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def oku(yol: Path = ON_KAYIT) -> list[dict]:
    """Çift listesi. YAML 1.1'de ``no`` anahtarı False okunur; ön kayıt değişmesin diye burada düzeltilir."""
    ciftler = yaml.safe_load(Path(yol).read_text(encoding="utf-8"))["ciftler"]
    return [{("no" if k is False else k): v for k, v in c.items()} for c in ciftler]


def calistir(paket: Path | None = None, surum: str = "v0.1", yol: Path = ON_KAYIT) -> pd.DataFrame:
    """Her çift için 7 bölge + Türkiye satırları; çalışmayan çift ``hata`` sütunuyla tek satır."""
    from physics.tek_cift import hesapla
    parca = []
    for c in oku(yol):
        ortak = {"no": c["no"], "sinif": c["sinif"], "x": "__".join(c["x"]), "y": "__".join(c["y"]),
                 "mevsim": c["mevsim"], "beklenen": c["beklenen"], "gerekce": c["gerekce"]}
        try:
            r = hesapla(c["x"][0], c["y"][0], "tum_bolgeler", c["mevsim"], urun_x=c["x"][1], urun_y=c["y"][1],
                        beklenen=c["beklenen"], surum=surum, paket=paket)
        except Exception as e:  # noqa: BLE001 — sınavda çalışmayan çift de bir sonuçtur
            parca.append(pd.DataFrame([{**ortak, "hata": f"{type(e).__name__}: {e}"}]))
            continue
        t = r["tablo"][["bolge_turu", "bolge_adi", "donem", "n", "r", "r_ham", "p", "etiket"]].copy()
        for k, v in reversed(list(ortak.items())):
            t.insert(0, k, v)
        t["hata"] = ""
        parca.append(t)
    return pd.concat(parca, ignore_index=True)


def degerlendir(df: pd.DataFrame) -> dict:
    """Önceden yazılmış ölçüt (YAML başlığı). Türkiye satırları üzerinden."""
    tr = df[(df["bolge_turu"] == "turkiye") | (df["hata"] != "")]
    k, f = tr[tr["sinif"] == "kontrol"], tr[tr["sinif"] == "fizik"]
    k_tum = df[df["sinif"] == "kontrol"]
    olcut1 = bool((k["etiket"] == "beklenen_yonde").all() and not (k_tum["etiket"] == "ters_yonde").any())
    f_bek = float((f["etiket"] == "beklenen_yonde").mean()) if len(f) else float("nan")
    f_ters = int((f["etiket"] == "ters_yonde").sum())
    olcut2 = bool(f_ters <= FIZIK_MAX_TERS and f_bek >= FIZIK_MIN_BEKLENEN)
    return {"kontrol_gecti": olcut1, "kontrol_turkiye": k["etiket"].fillna("hata").value_counts().to_dict(),
            "fizik_gecti": olcut2, "fizik_beklenen_orani": f_bek, "fizik_ters": f_ters,
            "fizik_turkiye": f["etiket"].fillna("hata").value_counts().to_dict(),
            "hatali_cift": int((tr["hata"] != "").sum())}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m physics.bagimsiz_sinav", description=__doc__.splitlines()[0])
    ap.add_argument("--surum", default="v0.1")
    ap.add_argument("--paket", type=Path, default=None)
    a = ap.parse_args(argv)
    sha = ozet()
    if sha != ON_KAYIT_SHA256:
        raise SystemExit(f"ÖN KAYIT DEĞİŞMİŞ: {sha} ≠ {ON_KAYIT_SHA256}. Sınav geçersiz.")
    from physics.tek_cift import paket_koku
    paket = paket_koku(a.surum, a.paket)
    df = calistir(paket, a.surum)
    d = degerlendir(df)
    hedef = paket / "L4_iliski" / "sinav"
    hedef.mkdir(parents=True, exist_ok=True)
    df.to_csv(hedef / "bagimsiz_sinav.csv", index=False, encoding="utf-8-sig", float_format="%.4g")
    tr = df[(df["bolge_turu"] == "turkiye") | (df["hata"] != "")]
    print(f"BAĞIMSIZ FİZİK SINAVI · ön kayıt SHA-256 {sha[:12]}… (doğrulandı)")
    for _, s in tr.iterrows():
        sonuc = s["hata"] or f"r = {s['r']:+.2f} (ham {s['r_ham']:+.2f}), p = {s['p']:.3g} → {s['etiket']}"
        print(f"  {s['no']:4s} {s['sinif']:8s} {s['x']:32s} ~ {s['y']:34s} {s['mevsim']:9s} "
              f"bekl. {s['beklenen']}  {sonuc}")
    print(f"Ölçüt 1 (kontrol): {'GEÇTİ' if d['kontrol_gecti'] else 'KALDI'} {d['kontrol_turkiye']}")
    print(f"Ölçüt 2 (fizik)  : {'GEÇTİ' if d['fizik_gecti'] else 'KALDI'} beklenen oranı "
          f"{d['fizik_beklenen_orani']:.0%}, ters {d['fizik_ters']} {d['fizik_turkiye']}")
    print(" ", hedef / "bagimsiz_sinav.csv")


if __name__ == "__main__":
    main()
