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
    "politis": "Politis, D. N., & Romano, J. P. (1992). A circular block-resampling procedure for stationary "
               "data. In R. LePage & L. Billard (Eds.), Exploring the Limits of Bootstrap (pp. 263–270). Wiley.",
    "held_soden": "Held, I. M., & Soden, B. J. (2006). Robust responses of the hydrological cycle to global "
                  "warming. Journal of Climate, 19(21), 5686–5699.",
    "bretherton": "Bretherton, C. S., et al. (1999). The effective number of spatial degrees of freedom "
                  "of a time-varying field. Journal of Climate, 12(7), 1990–2009.",
}


def _trends(results):
    return [a for a in results.get("analyses", []) if a.get("type") == "trend"]


def _relations(results):
    return [a for a in results.get("analyses", []) if a.get("type") == "iliski"]


def methods_paragraph(results: dict, kb) -> str:
    """Makalenin "Veri ve yöntem" bölümüne uyarlanabilecek paragraf (sözleşme 2.1–2.3 tanımları)."""
    trends = _trends(results)
    if not trends:
        return ""
    title = lambda v: kb.variables.get(v, {}).get("baslik", v)
    names = sorted({f"{title(t['variable'])} ({t['product']})" for t in trends})
    cells = [t["hucre_sayisi"] for t in trends if t.get("hucre_sayisi") is not None]
    donem = sorted({str(t["donem"]) for t in trends if t.get("donem")})
    mevsim = trends[0].get("mevsim") or "yillik"
    region = results.get("region", {}).get("name") or trends[0].get("region_name")

    from .explain import MEVSIM_ADI
    cell_txt = ""
    if cells:
        lo, hi = int(min(cells)), int(max(cells))
        cell_txt = f" ({lo} hücre)" if lo == hi else f" (ürüne göre {lo}–{hi} hücre)"
    seri = ("her yıl için yıllık değer" if mevsim == "yillik"
            else f"her yıl için {MEVSIM_ADI.get(mevsim, mevsim)} değeri")
    p = [
        f"{', '.join(names)} için aylık NASA ürünleri 0,25° ortak ızgaraya getirilmiş; hücre merkezi "
        f"{region} sınırı içinde kalan hücrelerin{cell_txt} cos(enlem) ağırlıklı alan ortalaması alınmıştır.",
        f"Bu ortalamadan {seri} üretilmiş (ortalama alınan değişkenlerde dönem ortalaması, yağış ve "
        "buharlaşma gibi birikimli değişkenlerde dönem toplamı); eksik ay oranı %20'yi aşan yıllar dışarıda "
        "bırakılmış"
        + (" (GRACE için yıllıkta en az 6 geçerli ay)" if any(t["product"] == "GRACE" for t in trends) else "")
        + " ve en az 12 geçerli yılı olan serilerde trend hesaplanmıştır"
        + (f" (analiz dönemi {', '.join(donem)})." if donem else "."),
        "Trend Theil-Sen eğimiyle (Sen, 1968) kestirilmiş, anlamlılık otokorelasyon düzeltmeli Mann-Kendall "
        "testiyle (Hamed ve Rao, 1998) sınanmıştır. Çoklu test için Benjamini-Hochberg yanlış keşif oranı "
        "düzeltmesi (Benjamini ve Hochberg, 1995) aynı düzeydeki (81 il ya da 7 bölge) satırlar içinde "
        "uygulanmıştır; Türkiye geneli tek satır olduğundan düzeltme gerektirmez.",
        "Eğimin %95 güven aralığı, artıkların gecikme-1 otokorelasyonundan hesaplanan etkin örneklem "
        "büyüklüğü ve t dağılımıyla genişletilmiştir. Bir trend, q ≤ 0,10 ve güven aralığı sıfırı dışladığında "
        "anlamlı kabul edilmiştir. Gözlenen eğimi ayırt etmek için gereken süre Weatherhead vd. (1998) "
        "ile hesaplanmıştır.",
    ]
    level = (results.get("region") or {}).get("level")
    fallback = sorted({f"{title(t['variable'])} → {t.get('region_name')}"
                       for t in trends if t.get("region_level") != level})
    if fallback:
        p.append("Seçilen düzeyde özeti bulunmayan değişkenlerde daha geniş bölgenin ortalaması kullanılmıştır ("
                 + "; ".join(fallback) + ").")
    if any(a.get("type") == "kaynak_uyumu" for a in results.get("analyses", [])):
        p.append("Birden çok ürünü olan değişkenlerde ürünler ortak döneme kırpılarak yeniden test edilmiş ve "
                 "aynı yönde anlamlı trend veren ürün sayısı (k/m) raporlanmıştır.")
    rel = _relations(results)
    if rel:
        rseri = sorted({seri_adi(a["seri"]) for a in rel if a.get("seri")})
        lags = sorted({a["gecikme_ay"] for a in rel if a.get("gecikme_ay")})
        txt = ("Değişkenler arası ilişki, doğrusal trendi giderilmiş seriler"
               + (f" ({', '.join(rseri)})" if rseri else "")
               + " arasındaki Pearson korelasyonuyla"
               + (f" ({' ve '.join(str(g) for g in lags)} ay gecikme dahil)" if lags else "")
               + " değerlendirilmiş; etkin örneklem büyüklüğü Bretherton vd. (1999) ile hesaplanmış ve "
               "anlamlılık etkin n − 2 serbestlik dereceli t testiyle sınanmıştır.")
        levels = {a.get("region_level") for a in rel}
        if "il" in levels:
            txt += (" İl satırlarında aynı çiftin 81 il p değerleri üzerinden Benjamini-Hochberg düzeltmesi "
                    "(α_FDR = 0,10) uygulanmıştır.")
        if levels & {"bolge", "turkiye"}:
            txt += " Bölge ve Türkiye satırlarında anlamlılık eşiği p < 0,05'tir (az sayıda test)."
        p.append(txt + " Bu sonuçlar nedensellik değil istatistiksel ilişki gösterir.")
    karne = _of(results, "karne")
    if karne:
        surum = sorted({str(a.get("kural_surumu")) for a in karne if a.get("kural_surumu")})
        p.append("Her sonuç için sonuçlar görülmeden sabitlenmiş bir bulgu karnesi"
                 + (f" ({', '.join(surum)})" if surum else "") + " hesaplanmıştır: ürünler arası uyum, "
                 "dairesel blok permütasyonuyla karıştırma testi (499 tekrar), ilk ve son üç yılın çıkarıldığı dönem "
                 "kırpması, α = 0,05 sıkı eşik ve veri yeterliliği (trendlerde) ya da trendden arındırma ve ±1 ay "
                 "gecikme (ilişkilerde). Güven seviyesi (YÜKSEK, ORTA, DÜŞÜK, YOK) bu kontrollerden kurala göre "
                 "atanır; karne bir sağlamlık özetidir, doğruluk ya da nedensellik göstermez.")
    buy = _of(results, "buyukluk")
    if buy:
        tests = sorted({a["test"] for a in buy})
        t_txt = {"cc": "Clausius-Clapeyron nem–sıcaklık oranı (beklenen bant 5,9–7,3 %/K; Held ve Soden, 2006)",
                 "butce": "su bütçesi kapanışı (GRACE depo değişimi ile yağış − buharlaşma − akış farkı; bant, "
                          "ortalama yıllık yağışın ±%10'u)",
                 "kar_cizgisi": "kar çizgisi kayması (sıcaklık trendinin 5,5–7,5 °C/km sıcaklık azalma oranına "
                                "bölümüyle beklenen kayma)"}
        p.append("Yön testlerine ek olarak gözlenen büyüklük fiziğin beklediği bantla karşılaştırılmıştır: "
                 + "; ".join(t_txt[t] for t in tests if t in t_txt)
                 + ". Güven aralıkları dairesel blok bootstrap ile (Politis ve Romano, 1992; 999 tekrar) "
                 "hesaplanmış, aralık bantla kesişiyorsa sonuç beklenen büyüklükle tutarlı sayılmıştır.")
    return " ".join(p)


def _of(results, kind):
    return [a for a in results.get("analyses", []) if a.get("type") == kind]


def method_references(results: dict) -> list[str]:
    refs = ["sen", "hamed_rao", "bh", "weatherhead"] if _trends(results) else []
    if _relations(results) or _of(results, "buyukluk"):
        refs.append("bretherton")
    if _of(results, "buyukluk"):
        refs.append("politis")
        if any(a.get("test") == "cc" for a in _of(results, "buyukluk")):
            refs.append("held_soden")
    return [METHOD_REFS[r] for r in refs]


def data_citations(results: dict) -> list[str]:
    """Kullanılan her NASA ürünü için atıf satırı (trend + ilişki kanıtları) + proje veri paketi."""
    seen, out = set(), []
    sources = [(t.get("provenance") or {}, t["product"], t.get("doi")) for t in _trends(results)]
    for a in _relations(results):
        for i, pv in enumerate(a.get("provenance") or []):
            sources.append((pv or {}, a["products"][i], a.get(f"doi_{i + 1}")))
    for pv, product, row_doi in sources:
        key = pv.get("short_name") or product
        if key in seen:
            continue
        seen.add(key)
        parts = [key]
        if pv.get("version"):
            parts.append(f"sürüm {pv['version']}")
        if pv.get("daac"):
            parts.append(f"NASA {pv['daac']}")
        line = ", ".join(parts)
        doi = pv.get("doi") or row_doi
        if doi:
            line += f". https://doi.org/{doi}"
        out.append(line)
    pkg = [t for t in _trends(results) + _relations(results) if t.get("urun_surumu")]
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
    unver = sorted({f"{title(t['variable'])} ({t['product']})" for t in trends if t.get("dogrulanmadi")}
                   | {" ~ ".join(title(v) for v in a["variables"]) for a in _relations(results)
                      if a.get("dogrulanmadi")})
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
    for t in trends:
        if t.get("trend_uyarisi"):
            w.append(f"{title(t['variable'])} ({t['product']}): {t['trend_uyarisi']}")
        if t.get("not"):
            w.append(f"{title(t['variable'])} ({t['product']}), {t.get('region_name')}: {t['not']}")
        if t.get("mk_yedek") == 1:
            w.append(f"{title(t['variable'])} ({t['product']}): Hamed-Rao düzeltmesi tanımsız çıktığı için "
                     f"düzeltmesiz Mann-Kendall kullanıldı [ref:{t['id']}].")
    for a in results.get("analyses", []):
        if a.get("type") == "kaynak_uyumu" and a["label"] != "uyumlu":
            w.append(f"{title(a['variable'])}: ürünler aynı yönde anlamlı değil ({a['k']}/{a['m']}) "
                     f"[ref:{a['id']}].")
    for v in sorted({t["variable"] for t in trends}):
        note = kb.variables.get(v, {}).get("dikkat")
        if note:
            w.append(f"{title(v)}: {note}")
    for a in _of(results, "karne"):
        if a.get("f_kritik") and str(a["f_kritik"]).strip() not in ("", "nan", "—"):
            w.append(f"Karne kritik uyarı ({a['about']}): {a['f_kritik']} [ref:{a['id']}].")
        if a.get("guven") in ("DÜŞÜK",):
            w.append(f"{a['about']}: güven DÜŞÜK — sonuç karıştırma ya da dönem kırpma testinden geçmedi "
                     f"[ref:{a['id']}].")
    for a in _of(results, "buyukluk"):
        if a.get("yorum"):
            w.append(f"{a['test']} ({a['yol']}, {a.get('bolge_adi')}): {a['yorum']} [ref:{a['id']}].")
    return w + list(results.get("warnings", []))


def _period_years(donem) -> int | None:
    """"2001-01 … 2025-12" ya da "2001–2024" -> yıl sayısı."""
    import re
    ys = [int(y) for y in re.findall(r"(?<!\d)(1[89]\d\d|20\d\d)(?!\d)", str(donem or ""))]
    return ys[-1] - ys[0] + 1 if len(ys) >= 2 else None
