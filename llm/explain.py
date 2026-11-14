"""Sonuç (results.json) -> sade dilde açıklama + kanıt tablosu.

LLM yalnızca anlatır: sayıları sonuçtan kopyalar, her iddiaya [ref:id] ekler. LLM yoksa ya da
doğrulamayı geçemezse `template_explanation` aynı kanıtlardan güvenli bir metin üretir.
"""
from __future__ import annotations

import json

from .kb import KnowledgeBase

LABELS = {
    "uyumlu": "beklenen yönle/hipotezle uyumlu",
    "celiskili": "beklenenle çelişiyor; başka bir etken baskın olabilir",
    "yetersiz": "veri kesin bir sonuç için yetersiz",
}

EXPLAIN_SYSTEM = """Sen bir NASA veri dedektifisin. Lise öğrencisinin anlayacağı sade bir Türkçeyle,
aşağıdaki analiz sonuçlarını açıkla. KURALLAR (çiğnersen cevabın reddedilir):
1. Sayıları YALNIZCA sonuç JSON'undan kopyala; hesap yapma, yuvarlarken en fazla 2 ondalık kullan.
   Yeni sayı (yüzde, fark, toplam) türetme.
2. Sayı içeren her cümlenin sonuna kaynağı olan analizi [ref:<id>] biçiminde ekle (noktadan önce).
3. Etiketleri (uyumlu / celiskili / yetersiz) değiştirme; ne anlama geldiklerini sade dille söyle.
4. Neden kısmında bunun bir İLİŞKİ ya da TUTARLILIK kanıtı olduğunu, kesin neden olmadığını belirt.
5. Şu dört başlıkla, toplam 120-200 kelime yaz: **Ne değişti?**, **Nerede?**, **Neden olabilir?**,
   **Ne kadar güvenebiliriz?** Sonuçta olmayan bir başlık için "Bu analizde bu bilgi yok." yaz.
6. Mann-Kendall p-değerini "bu değişimin tesadüf olma olasılığı" gibi sade bir dille anlat.
"""


def _var_title(kb: KnowledgeBase, name: str | None) -> str:
    return kb.variables.get(name, {}).get("baslik", name or "?")


def _fmt(x, d=2) -> str:
    return f"{x:.{d}f}"


def _fmt_p(p) -> str:
    return "< 0.001" if p < 0.001 else f"= {p:.3g}"


def evidence_table(results: dict, kb: KnowledgeBase) -> list[dict]:
    """Arayüz için kanıt tablosu satırları (her satırın id'si açıklamadaki [ref:id] ile eşleşir)."""
    rows = []
    for a in results.get("analyses", []):
        rows.append({
            "id": a.get("id"),
            "analiz": a.get("type"),
            "degisken": _var_title(kb, a.get("variable")) if a.get("variable") else a.get("axis", "-"),
            "urun": a.get("product", "-"),
            "deger": a.get("sen_slope_per_decade", a.get("observed_shift_m_per_decade")),
            "birim": (a.get("units", "") + "/on yıl") if "sen_slope_per_decade" in a else
                     ("m/on yıl" if "observed_shift_m_per_decade" in a else a.get("units", "")),
            "aralik_95": a.get("ci95"),
            "p": a.get("mk_p"),
            "etiket": a.get("label"),
            "etiket_sade": LABELS.get(a.get("label"), ""),
        })
    return rows


def _sentence(a: dict, kb: KnowledgeBase) -> str | None:
    """Tek bir analiz için güvenli (sonuçtan kopyalanmış sayılarla) cümle."""
    rid, label = a.get("id"), a.get("label")
    lab = LABELS.get(label, label or "")
    if a.get("type") == "trend" and a.get("sen_slope_per_decade") is not None:
        s = (f"{_var_title(kb, a.get('variable'))} ({a.get('product', '?')}) on yılda "
             f"{_fmt(a['sen_slope_per_decade'])} {a.get('units', '')} değişiyor")
        if a.get("ci95"):
            s += f" (%95 güven aralığı {_fmt(a['ci95'][0])} ile {_fmt(a['ci95'][1])})"
        if a.get("mk_p") is not None:
            s += f"; Mann-Kendall p {_fmt_p(a['mk_p'])}"
        if a.get("fdr_fraction_significant") is not None:
            s += f"; bölgedeki hücrelerin %{a['fdr_fraction_significant'] * 100:.0f}'inde anlamlı"
        return s + f" [ref:{rid}]. Sonuç: {lab}."
    if a.get("type") == "boundary_shift" and a.get("observed_shift_m_per_decade"):
        o, p = a["observed_shift_m_per_decade"], a.get("predicted_shift_m_per_decade")
        s = (f"{a.get('axis', 'eksen')} boyunca gözlenen sınır kayması on yılda "
             f"{_fmt(o[0], 0)} ile {_fmt(o[1], 0)} m")
        if p:
            s += f", ısınmadan beklenen ise {_fmt(p[0], 0)} ile {_fmt(p[1], 0)} m"
        return s + f" [ref:{rid}]. Sonuç: {lab}."
    if label:
        return f"{a.get('type', 'analiz')} sonucu: {lab} [ref:{rid}]."
    return None


def template_explanation(plan: dict, results: dict, kb: KnowledgeBase) -> str:
    """LLM'siz yedek açıklama. Yalnızca sonuçtaki sayıları kullanır, her cümle kanıta bağlıdır."""
    lines = [f"**{plan.get('card_title', 'Analiz')}** — {plan.get('region_name') or results.get('region', {}).get('name', '')}"]
    if plan.get("sade_tanim"):
        lines.append(plan["sade_tanim"])
    for a in results.get("analyses", []):
        s = _sentence(a, kb)
        if s:
            lines.append("- " + s)
    if plan.get("supheliler"):
        lines.append("Not: Şüpheli değişkenlerle görülen ilişkiler kesin neden değil, tutarlılık kanıtıdır.")
    return "\n".join(lines)


def llm_explanation(question: str, plan: dict, results: dict, kb: KnowledgeBase, client,
                    feedback: str | None = None) -> str:
    """LLM ile açıklama üretir (doğrulama answer.py'de yapılır)."""
    names = {a.get("variable") for a in results.get("analyses", [])} | \
            {b["degisken"] for b in plan.get("belirti", [])} | {s["degisken"] for s in plan.get("supheliler", [])}
    var_cards = {n: {k: kb.variables[n].get(k) for k in ("baslik", "birim", "sade_tanim", "dikkat")}
                 for n in names if n in kb.variables}
    context = {
        "soru": question,
        "bolge": plan.get("region_name"),
        "surec": {k: plan.get(k) for k in ("card_title", "sade_tanim", "supheliler", "alternatifler")},
        "degisken_kartlari": var_cards,
        "etiket_anlamlari": LABELS,
        "sonuclar": {k: v for k, v in results.items() if not str(k).startswith("_")},
    }
    user = "Analiz bağlamı ve sonuçları (JSON):\n" + json.dumps(context, ensure_ascii=False, indent=1)
    if feedback:
        user += "\n\nÖNCEKİ CEVABIN REDDEDİLDİ. Düzelt:\n" + feedback
    return client.complete(EXPLAIN_SYSTEM, user)
