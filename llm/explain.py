"""Kanıtlar -> açıklama metni + kanıt tablosu.

İki kitle: "akademisyen" (varsayılan; kısa, teknik bulgular paragrafı) ve "genel" (sade dil).
LLM yalnızca anlatır: sayıları kanıtlardan kopyalar, her sayılı cümleye [ref:id] ekler.
LLM yoksa ya da doğrulamayı geçemezse `template_explanation` aynı kanıtlardan güvenli metin üretir.
Tüm sayılar `format_tr` ile Türkçe biçimde yazılır (arayüzle aynı).
"""
from __future__ import annotations

import json
import re

from .format_tr import format_p, format_tr
from .kb import KnowledgeBase

LABELS = {
    # L3 trend (işaret + anlamlılık bayrağından)
    "anlamli_artis": "FDR sonrası anlamlı artış",
    "anlamli_azalis": "FDR sonrası anlamlı azalış",
    "anlamsiz": "FDR sonrası anlamlı değil",
    "yetersiz": "hesaplanamadı / veri yetersiz",
    # L4 ilişki
    "beklenen_yonde": "ilişki anlamlı ve beklenen yönde",
    "ters_yonde": "ilişki anlamlı ama beklenenin tersi yönde",
    "hesaplanamadi": "ilişki hesaplanamadı",
    # kaynak uyumu
    "uyumlu": "tüm ürünler aynı yönde anlamlı",
    "kismen": "ürünlerin bir kısmı aynı yönde anlamlı",
    "uyumsuz": "ürünler arasında anlamlı ortak yön yok",
    # eski results.json (geriye uyum)
    "celiskili": "beklenenle çelişiyor",
}

EXPLAIN_SYSTEM = {
    "akademisyen": """Sen yer bilimleri alanında çalışan bir araştırmacıya yardım eden bir veri analistisin.
Aşağıdaki analiz kanıtlarından, bir makalenin "Bulgular" bölümüne uyarlanabilecek akademik Türkçe bir
paragraf yaz. KURALLAR (çiğnersen cevabın reddedilir):
1. Sayıları YALNIZCA kanıtlardan kopyala; yeni sayı (fark, oran, ortalama, yüzde) türetme, hesap yapma.
   Türkçe sayı biçimi kullan: ondalık virgül (−2,1), en fazla 3 anlamlı basamak.
2. Sayı içeren her cümlenin sonuna kaynağı olan kanıtı [ref:<id>] biçiminde ekle (noktadan önce).
3. Etiketlerin anlamını değiştirme. "anlamsiz" bir trendi artış/azalış diye sunma.
4. Nedensellik dili kullanma ("neden oldu", "yol açtı" yok); "ilişkili", "eşzamanlı", "tutarlı" kullan.
5. Doğrulanmamış (dogrulanmadi=true) ürünleri ve ürünler arası uyumsuzluğu açıkça belirt.
6. 120–200 kelime; madde işareti yok, tek paragraf. Yöntem ve kaynakça YAZMA (ayrıca ekleniyor).""",
    "genel": """Sen bir NASA veri dedektifisin. Lise öğrencisinin anlayacağı sade bir Türkçeyle aşağıdaki
analiz kanıtlarını açıkla. KURALLAR: sayıları yalnızca kanıtlardan kopyala (Türkçe biçim: −2,1), yeni sayı
türetme; sayı içeren her cümlenin sonuna [ref:<id>] ekle; ilişkinin kesin neden olmadığını söyle;
**Ne değişti?**, **Nerede?**, **Neden olabilir?**, **Ne kadar güvenebiliriz?** başlıklarıyla 120–200 kelime.""",
}


SERI = {"yillik_ortalama": "yıllık ortalama", "yillik": "yıllık", "aylik_anomali": "aylık anomali",
        "aylik_anomali_nis_eyl": "aylık anomali (Nisan–Eylül)", "mevsim_anomali": "mevsimlik anomali",
        "kis_DJF": "kış (DJF)", "ilkbahar_MAM": "ilkbahar (MAM)", "yaz_JJA": "yaz (JJA)",
        "sonbahar_SON": "sonbahar (SON)"}


def seri_adi(code) -> str:
    """Seri kodunun okunur hali: "yillik_ortalama" -> "yıllık ortalama"."""
    return SERI.get(str(code), str(code).replace("_", " "))


def _title(kb: KnowledgeBase, name: str | None) -> str:
    return kb.variables.get(name, {}).get("baslik", name or "?")


_PER_DECADE = re.compile(r"/\s*(10|on)\s*y[ıi]l|/\s*decade", re.I)


def _slope_units(a: dict) -> str:
    """Eğim birimi. L3 `birim` sütunu temel birimdir ("mm"); "/10 yıl" burada eklenir. Sütun zaten
    "mm/10 yıl" yazılmışsa tekrar eklenmez (sözleşme bunu açıkça yazmıyor; iki durum da güvenli)."""
    u = str(a.get("birim") or a.get("units") or "").strip()
    if _PER_DECADE.search(u):
        return u
    return f"{u}/10 yıl" if u not in ("1", "") else "/10 yıl"


# --------------------------------------------------------------------------- kanıt tablosu
def evidence_table(results: dict, kb: KnowledgeBase) -> list[dict]:
    """Arayüz için kanıt satırları (id'ler açıklamadaki [ref:id] ile eşleşir). Değerler ham sayıdır;
    arayüz bunları format_tr ile gösterir."""
    rows = []
    for a in results.get("analyses", []):
        t = a.get("type")
        row = {"id": a.get("id"), "analiz": t, "etiket": a.get("label"),
               "etiket_sade": LABELS.get(a.get("label"), ""), "dogrulanmadi": a.get("dogrulanmadi", False)}
        if t == "trend":
            row.update(degisken=_title(kb, a.get("variable")), urun=a.get("product"),
                       deger=a.get("sen_egimi", a.get("sen_slope_per_decade")), birim=_slope_units(a),
                       aralik_95=[a.get("ga_alt"), a.get("ga_ust")] if a.get("ga_alt") is not None else a.get("ci95"),
                       p=a.get("p_mk", a.get("mk_p")), q=a.get("p_fdr"), gereken_yil=a.get("gereken_yil"),
                       bolge=a.get("region_name"), kademe=a.get("kademe"))
        elif t == "iliski":
            row.update(degisken=" ~ ".join(_title(kb, v) for v in a["variables"]), urun=" ~ ".join(a["products"]),
                       deger=a.get("r"), birim="r", p=a.get("p"), q=a.get("p_fdr"),
                       gecikme_ay=a.get("gecikme_ay"), seri=a.get("seri"),
                       bolge=a.get("bolge_adi") or a.get("region_key"), kademe=a.get("kademe"))
        elif t == "kaynak_uyumu":
            row.update(degisken=_title(kb, a.get("variable")), urun=", ".join(a["urunler"]),
                       deger=f"{a['k']}/{a['m']}", birim="ürün aynı yönde")
        elif t == "boundary_shift":
            row.update(degisken=a.get("axis"), deger=a.get("observed_shift_m_per_decade"), birim="m/10 yıl")
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- şablon
def _sentence(a: dict, kb: KnowledgeBase) -> str | None:
    """Tek kanıt için güvenli cümle (sayılar kanıttan kopyalanır, Türkçe biçimde)."""
    rid, lab = a.get("id"), LABELS.get(a.get("label"), a.get("label") or "")
    t = a.get("type")
    if t == "trend" and a.get("sen_egimi") is not None:
        s = (f"{_title(kb, a['variable'])} ({a['product']}"
             + (f", {seri_adi(a['seri'])}" if a.get("seri") else "") + f"): Sen eğimi "
             + format_tr(a["sen_egimi"], _slope_units(a)))
        if a.get("ga_alt") is not None and a.get("ga_ust") is not None:
            s += f" (%95 GA {format_tr([a['ga_alt'], a['ga_ust']])})"
        stats = []
        if a.get("p_mk") is not None:
            stats.append("Mann-Kendall " + format_p(a["p_mk"]))
        if a.get("p_fdr") is not None:
            stats.append("FDR " + format_p(a["p_fdr"]).replace("p ", "q ", 1))
        if stats:
            s += "; " + ", ".join(stats)
        if a.get("anlamli_hucre_orani") is not None:
            s += f"; anlamlı hücre oranı %{format_tr(a['anlamli_hucre_orani'] * 100, digits=0)}"
        if a.get("dogrulanmadi"):
            s += "; doğrulanmamış (Kademe 2) ürün"
        return s + f" [ref:{rid}]. Sonuç: {lab}."
    if t == "trend" and a.get("sen_slope_per_decade") is not None:   # eski results.json
        s = (f"{_title(kb, a.get('variable'))} ({a.get('product', '?')}): on yılda "
             + format_tr(a["sen_slope_per_decade"], a.get("units")))
        if a.get("ci95"):
            s += f" (%95 GA {format_tr(a['ci95'])})"
        if a.get("mk_p") is not None:
            s += "; Mann-Kendall " + format_p(a["mk_p"])
        return s + f" [ref:{rid}]. Sonuç: {lab}."
    if t == "kaynak_uyumu":
        return (f"{_title(kb, a['variable'])}: {', '.join(a['urunler'])} ürünlerinden {a['k']}/{a['m']} "
                f"tanesi aynı yönde anlamlı ({a['kapsam']}) [ref:{rid}]. Sonuç: {lab}.")
    if t == "iliski" and a.get("r") is not None:
        if a.get("label") == "anlamsiz":       # bölge/Türkiye satırlarında FDR yok; genel ifade kullan
            lab = "ilişki anlamlı değil"
        v1, v2 = (_title(kb, v) for v in a["variables"])
        ctx = [seri_adi(a["seri"])] if a.get("seri") else []
        if a.get("gecikme_ay"):
            ctx.append(f"{v2} {a['gecikme_ay']} ay gecikmeli")
        if a.get("bolge_adi"):
            ctx.append(str(a["bolge_adi"]))
        # İl satırında anlamlılık FDR (q), bölge/Türkiye satırında p ile verilir (sözleşme 2.3).
        if a.get("region_level") == "il" and a.get("p_fdr") is not None:
            sig = "FDR " + format_p(a["p_fdr"]).replace("p ", "q ", 1)
        else:
            sig = format_p(a["p"]) if a.get("p") is not None else "p = —"
        s = (f"{v1} ile {v2} arasında trendi giderilmiş seriler üzerinden r = {format_tr(a['r'])}"
             + (f" ({', '.join(ctx)})" if ctx else "")
             + f"; {sig}, etkin n = {format_tr(a.get('etkin_n'), digits=0)}")
        if a.get("dogrulanmadi"):
            s += "; doğrulanmamış (Kademe 2) girdi"
        s += f" [ref:{rid}]. Sonuç: {lab}; bu bir ilişkidir, nedensellik göstermez."
        if a.get("label") == "ters_yonde" and a.get("not"):
            s += f" Not: {a['not']}"
        return s
    if t == "boundary_shift" and a.get("observed_shift_m_per_decade"):
        o, p = a["observed_shift_m_per_decade"], a.get("predicted_shift_m_per_decade")
        s = f"{a.get('axis', 'eksen')} boyunca gözlenen sınır kayması {format_tr(o, 'm/10 yıl', 0)}"
        if p:
            s += f", beklenen {format_tr(p, 'm/10 yıl', 0)}"
        return s + f" [ref:{rid}]. Sonuç: {lab}."
    if a.get("label"):
        return f"{t or 'analiz'}: {lab} [ref:{rid}]."
    return None


def template_explanation(plan: dict, results: dict, kb: KnowledgeBase, kitle: str = "akademisyen") -> str:
    """LLM'siz yedek açıklama. Yalnızca kanıtlardaki sayıları kullanır, her sayılı cümle kanıta bağlıdır."""
    region = plan.get("region_name") or (results.get("region") or {}).get("name") or ""
    lines = [f"**{plan.get('card_title', 'Analiz')}** — {region}"]
    if kitle == "genel" and plan.get("sade_tanim"):
        lines.append(plan["sade_tanim"])
    if not results.get("analyses"):
        lines.append("Bu bölge ve değişkenler için analiz paketinde sonuç bulunamadı.")
    for a in results.get("analyses", []):
        s = _sentence(a, kb)
        if s:
            lines.append("- " + s)
    if any(a.get("type") == "iliski" for a in results.get("analyses", [])) or plan.get("supheliler"):
        lines.append("Not: Değişkenler arası sonuçlar istatistiksel ilişki gösterir, nedensellik göstermez.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- LLM
def _compact(a: dict) -> dict:
    """LLM'e gidecek kanıt: dosya yolu ve künye gibi metin dışı alanlar çıkarılır, sayılar aynen kalır."""
    skip = {"file", "provenance", "veri_seti_doi", "doi", "lisans", "urun_surumu"}
    return {k: v for k, v in a.items() if k not in skip and v is not None}


def llm_explanation(question: str, plan: dict, results: dict, kb: KnowledgeBase, client,
                    feedback: str | None = None, kitle: str = "akademisyen") -> str:
    """LLM ile açıklama üretir (doğrulama answer.py'de yapılır)."""
    names = {a.get("variable") for a in results.get("analyses", [])} | \
            {b["degisken"] for b in plan.get("belirti", [])} | {s["degisken"] for s in plan.get("supheliler", [])}
    var_cards = {n: {k: kb.variables[n].get(k) for k in ("baslik", "birim", "sade_tanim", "dikkat")}
                 for n in names if n in kb.variables}
    context = {
        "soru": question,
        "bolge": plan.get("region_name"),
        "surec": {k: plan.get(k) for k in ("card_title", "supheliler", "alternatifler")},
        "degisken_kartlari": var_cards,
        "etiket_anlamlari": LABELS,
        "kanitlar": [_compact(a) for a in results.get("analyses", [])],
        "uyarilar": results.get("warnings", []),
    }
    user = "Analiz bağlamı ve kanıtlar (JSON):\n" + json.dumps(context, ensure_ascii=False, indent=1)
    if feedback:
        user += "\n\nÖNCEKİ CEVABIN REDDEDİLDİ. Düzelt:\n" + feedback
    return client.complete(EXPLAIN_SYSTEM.get(kitle, EXPLAIN_SYSTEM["akademisyen"]), user)
