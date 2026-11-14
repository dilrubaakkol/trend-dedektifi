"""Açılış ekranı: dönen Dünya, yörüngedeki uydular ve veri setinin başlığı (hero.html + three.js)."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

HERO_HTML = Path(__file__).with_name("hero.html")

HEADLINE_HTML = 'NASA verisi, <span class="ice">Türkiye</span><br>için analize <span class="ember">hazır.</span>'
PILL_HTML = "NASA UYDU VE MODEL VERİSİ · <em>ATIF YAPILABİLİR</em> TREND VERİ SETİ"
LEAD = (
    "Sıcaklık, yağış, kar, toprak nemi, bitki örtüsü ve yer altı suyu: 25 yıllık NASA verisi Türkiye'ye "
    "kesildi, aynı ızgaraya getirildi, trendi ölçüldü ve tesadüfler ayıklandı. "
    "Merak eden okur, araştıran indirir ve makalesinde atıf yapar."
)


def build_config(bbox, period_label: str, version: str, placeholder: bool, logged_in: bool = False,
                 mode: str = "hero") -> dict:
    """hero.html'e aktarılacak yapılandırmayı hazırlar (yalnızca metin, düğmeler ve kutu sınırları).

    `mode="bg"`: giriş ekranının arka planı; orta başlık ve düğmeler gizlenir, yalnız Dünya ve köşe bilgileri kalır.
    """
    w, s, e, n = bbox
    first = ({"label": "Haritaya git  →", "target": "panel", "primary": True} if logged_in
             else {"label": "Başla  →", "target": "giris", "primary": True})
    return {
        "case_label": f"VERİ SETİ · {version.upper()} ÖN SÜRÜM",
        "headline_html": HEADLINE_HTML,
        "pill_html": PILL_HTML,
        "lead": LEAD,
        "bbox": [w, s, e, n],
        "target": {"lat": (s + n) / 2, "lon": (w + e) / 2},
        "period_label": period_label,
        "is_placeholder": placeholder,
        "status_label": "YER TUTUCU VERİ" if placeholder else "YAYINDA",
        "buttons": [first, {"label": "Nasıl çalışır?", "target": "proje"}],
        "mode": mode,
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
