"""Açılış ekranı: dönen Dünya, yörüngedeki uydular ve vaka başlığı (hero.html + three.js)."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

HERO_HTML = Path(__file__).with_name("hero.html")

# Karta göre açılış metni. Yeni kart eklenince buraya bir satır eklemek yeterli; yoksa genel metin kullanılır.
HERO_COPY = {
    "kar_isinma": {
        "case_label": "VAKA 01 · KAR ÇİZGİSİ",
        "headline_html": 'Uydular <span class="ice">karın</span><br>azaldığını gördü. <span class="ember">Neden?</span>',
    },
    "kuraklik_su_butcesi": {
        "case_label": "VAKA 02 · SU BÜTÇESİ",
        "headline_html": 'Uydular <span class="ice">suyun</span><br>çekildiğini gördü. <span class="ember">Neden?</span>',
    },
}
DEFAULT_COPY = {
    "case_label": "YENİ VAKA",
    "headline_html": 'Uydular bir <span class="ice">değişim</span><br>gördü. <span class="ember">Neden?</span>',
}
LEAD = (
    "Trend Dedektifi, NASA uydularının kaydettiği bir değişimin yalnızca ne olduğunu göstermez. "
    "O değişimin bir sebeple gerçekten tutarlı olup olmadığını fizik kurallarıyla sınar. "
    "Vatandaş, çiftçi ve bilim insanı aynı kanıta kendi sorusuyla bakar."
)


def build_config(card_id: str | None, bbox, period_label: str, placeholder: bool) -> dict:
    """hero.html'e aktarılacak yapılandırmayı hazırlar (yalnızca metin ve bölge sınırları)."""
    copy = HERO_COPY.get(card_id or "", DEFAULT_COPY)
    w, s, e, n = bbox
    return {
        **copy,
        "lead": LEAD,
        "bbox": [w, s, e, n],
        "target": {"lat": (s + n) / 2, "lon": (w + e) / 2},
        "period_label": period_label,
        "is_placeholder": placeholder,
        "status_label": "YER TUTUCU SONUÇ" if placeholder else "DOĞRULANMIŞ SONUÇ",
    }


def render_hero(config: dict, height: int = 860) -> None:
    """Hero'yu sayfaya gömer. Yükseklik CSS ile 100vh'ye çekilir; `height` yalnızca ilk çizim içindir."""
    payload = json.dumps(config, ensure_ascii=False).replace("</", "<\\/")
    html = HERO_HTML.read_text(encoding="utf-8").replace("/*__TD_CONFIG__*/{}", payload)
    # Yeni Streamlit sürümlerinde st.iframe; eski sürümlerde components.html (ikisi de JS çalıştırır).
    if hasattr(st, "iframe"):
        st.iframe(html, height=height)
    else:
        components.html(html, height=height, scrolling=False)
