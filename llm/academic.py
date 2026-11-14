"""Akademisyen çıktıları: yöntem paragrafı, veri atfı, yöntem kaynakçası, dosya listesi, uyarılar.

Bunlar BİLEREK LLM'e yazdırılmaz: makaleye girecek metinde yöntem adı, DOI ya da sürüm hatası
kabul edilemez. Hepsi kanıtlardaki alanlardan (L3/L4 CSV + data/catalog.yaml) şablonla üretilir.
Yöntem tanımları docs/sozlesmeler.md bölüm 2'dendir; sözleşme değişirse burası da güncellenir.
"""
from __future__ import annotations

from .explain import seri_adi
from .format_tr import format_tr

METHOD_REFS = {
    "sen": "Sen, P. K. (1968). Estimates of the regression coefficient based on Kendall's tau. "
           "Journal of the American Statistical Association, 63(324), 1379–1389.",
    "hamed_rao": "Hamed, K. H., & Rao, A. R. (1998). A modified Mann-Kendall trend test for "
                 "autocorrelated data. Journal of Hydrology, 204(1–4), 182–196.",
    "bh": "Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate: a practical and "
          "powerful approach to multiple testing. Journal of the Royal Statistical Society B, 57(1), 289–300.",
    "weatherhead": "Weatherhead, E. C., et al. (1998). Factors affecting the detection of trends: "
                   "Statistical considerations and applications to environmental data. "
                   "Journal of Geophysical Research, 103(D14), 17149–17161.",
    "bretherton": "Bretherton, C. S., et al. (1999). The effective number of spatial degrees of freedom "
                  "of a time-varying field. Journal of Climate, 12(7), 1990–2009.",
}


def _trends(results):
    return [a for a in results.get("analyses", []) if a.get("type") == "trend"]


def _relations(results):
    return [a for a in results.get("analyses", []) if a.get("type") == "iliski"]


def methods_paragraph(results: dict, kb) -> str:
    """Makalenin "Veri ve yöntem" bölümüne uyarlanabilecek paragraf."""
    trends = _trends(results)
    if not trends:
        return ""
    names = sorted({f"{kb.variables.get(t['variable'], {}).get('baslik', t['variable'])} ({t['product']})"
                    for t in trends})
    cells = [t["hucre_sayisi"] for t in trends if t.get("hucre_sayisi") is not None]
    donem = sorted({str(t.get("donem")) for t in trends if t.get("donem")})
    seri = sorted({seri_adi(t.get("seri")) for t in trends if t.get("seri")})
    region = results.get("region", {}).get("name") or trends[0].get("region_name")

    cell_txt = ""
    if cells:
        lo, hi = int(min(cells)), int(max(cells))
        cell_txt = f" ({lo} hücre)" if lo == hi else f" (ürüne göre {lo}–{hi} hücre)"
    p = [
        f"{', '.join(names)} için {' / '.join(donem) or 'analiz dönemi'} aylık NASA ürünleri 0,25° ortak "
        f"ızgaraya getirilmiş; hücre merkezi {region} sınırı içinde kalan hücrelerin{cell_txt} alan "
        "ortalaması alınmıştır.",
        f"Trendler {', '.join(seri) or 'belirtilen'} serisinden Theil-Sen eğimiyle (Sen, 1968) kestirilmiş; "
        "anlamlılık otokorelasyon düzeltmeli Mann-Kendall testiyle (Hamed ve Rao, 1998) sınanmış ve çoklu "
        "test için Benjamini-Hochberg yanlış keşif oranı düzeltmesi (Benjamini ve Hochberg, 1995; "
        "α_FDR = 0,10) uygulanmıştır.",
        "Eğimin %95 güven aralığı etkin örneklem büyüklüğüne göre genişletilmiş, gözlenen eğimi ayırt etmek "
        "için gereken süre Weatherhead vd. (1998) ile hesaplanmıştır.",
    ]
    level = (results.get("region") or {}).get("level")
    fallback = sorted({f"{kb.variables.get(t['variable'], {}).get('baslik', t['variable'])} → {t.get('region_name')}"
                       for t in trends if t.get("region_level") != level})
    if fallback:
        p.append("İl özeti bulunmayan değişkenlerde bağlı olunan bölgenin ortalaması kullanılmıştır ("
                 + "; ".join(fallback) + ").")
    if _relations(results):
        p.append("Değişkenler arası ilişki, trendi giderilmiş seriler arasındaki Pearson korelasyonu ve "
                 "Bretherton vd. (1999) etkin örneklem büyüklüğüyle değerlendirilmiştir; bu sonuçlar "
                 "nedensellik değil istatistiksel ilişki gösterir.")
    return " ".join(p)


def method_references(results: dict) -> list[str]:
    refs = ["sen", "hamed_rao", "bh", "weatherhead"] if _trends(results) else []
    if _relations(results):
        refs.append("bretherton")
    return [METHOD_REFS[r] for r in refs]


def data_citations(results: dict) -> list[str]:
    """Kullanılan her NASA ürünü için atıf satırı + proje veri paketi."""
    seen, out = set(), []
    for t in _trends(results):
        pv = t.get("provenance") or {}
        key = pv.get("short_name") or t["product"]
        if key in seen:
            continue
        seen.add(key)
        parts = [key]
        if pv.get("version"):
            parts.append(f"sürüm {pv['version']}")
        if pv.get("daac"):
            parts.append(f"NASA {pv['daac']}")
        line = ", ".join(parts)
        doi = pv.get("doi") or t.get("doi")
        if doi:
            line += f". https://doi.org/{doi}"
        out.append(line)
    pkg = [t for t in _trends(results) if t.get("urun_surumu")]
    if pkg:
        t = pkg[0]
        line = f"Trend Dedektifi Türkiye veri paketi, {t['urun_surumu']}"
        if t.get("lisans"):
            line += f", {t['lisans']}"
        doi = t.get("veri_seti_doi")
        if doi and "doldurulacak" not in str(doi):
            line += f". https://doi.org/{doi}"
        out.append(line + ".")
    return out


def files_used(results: dict) -> list[str]:
    """Analizde okunan paket dosyaları (paket köküne göreli)."""
    return sorted({a["file"] for a in results.get("analyses", []) if a.get("file")})


def academic_warnings(results: dict, kb) -> list[str]:
    """Hakem sorusu olabilecek noktalar. Sayılar kanıtlardan aynen kopyalanır."""
    title = lambda v: kb.variables.get(v, {}).get("baslik", v)
    w = []
    trends = _trends(results)
    unver = sorted({f"{title(t['variable'])} ({t['product']})" for t in trends if t.get("dogrulanmadi")})
    if unver:
        w.append("Kademe 2 (doğrulanmamış) girdi: " + ", ".join(unver) +
                 ". Bu sonuçlar bağımsız veriyle karşılaştırılmadan yayımlanmamalı.")
    long_ = []
    for t in trends:
        gy, n_years = t.get("gereken_yil"), _period_years(t.get("donem"))
        if gy is not None and n_years and gy > n_years:
            long_.append(f"{title(t['variable'])} ({t['product']}): ≈{format_tr(gy, digits=0)} yıl "
                         f"[ref:{t['id']}]")
    if long_:
        w.append(f"Gözlenen eğimi ayırt etmek için gereken süre mevcut seriden ({n_years} yıl) uzun — "
                 + "; ".join(long_) + ". Eğim büyüklüğü dikkatle yorumlanmalı.")
    for t in trends:
        if t.get("hucre_sayisi") is not None and t["hucre_sayisi"] < 4:
            w.append(f"{title(t['variable'])} ({t['product']}): bölge ortalaması yalnız "
                     f"{format_tr(t['hucre_sayisi'], digits=0)} hücreye dayanıyor [ref:{t['id']}].")
    for a in results.get("analyses", []):
        if a.get("type") == "kaynak_uyumu" and a["label"] != "uyumlu":
            w.append(f"{title(a['variable'])}: ürünler aynı yönde anlamlı değil ({a['k']}/{a['m']}) "
                     f"[ref:{a['id']}].")
    for v in sorted({t["variable"] for t in trends}):
        note = kb.variables.get(v, {}).get("dikkat")
        if note:
            w.append(f"{title(v)}: {note}")
    return w + list(results.get("warnings", []))


def _period_years(donem) -> int | None:
    """"2001-01 … 2025-12" -> 25."""
    import re
    ys = [int(y) for y in re.findall(r"(?<!\d)(\d{4})-\d{2}", str(donem or ""))]
    return ys[-1] - ys[0] + 1 if len(ys) >= 2 else None
