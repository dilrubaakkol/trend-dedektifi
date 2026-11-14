"""Trend Dedektifi — web arayüzü (Kişi 5).

Çalıştırma (repo kökünden):  streamlit run app/streamlit_app.py

Akış: açılış (dönen Dünya) → nasıl çalışır → soru + bölge → soruşturma planı →
araştırma modu (harita, fiziksel test, kanıt tablosu, açıklama) / keşif modu.
Arayüz sayı üretmez; tüm değerler results.json'dan okunur. Yer tutucu ve sentetik içerik ekranda işaretlidir.
"""

from __future__ import annotations

import html
import json
import subprocess
import sys
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
for p in (str(APP_DIR), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from charts import interval_chart, noise_experiment, synthetic_trend_map  # noqa: E402
from data.regions import REGIONS  # noqa: E402
from formatting import fmt, fmt_p  # noqa: E402
from hero import build_config, render_hero  # noqa: E402
from results_io import (  # noqa: E402
    by_type, ci_of, is_placeholder, label_of, load_card, load_results, period_label,
)
from theme import anchor, inject_theme, section  # noqa: E402

st.set_page_config(page_title="Trend Dedektifi", page_icon="🛰️", layout="wide", initial_sidebar_state="collapsed")
inject_theme()

# Değişken adlarının ekrandaki karşılıkları (sözleşmedeki adlarla birebir).
VAR_NAMES = {
    "kar_ortusu": "Kar örtüsü", "kar_su_esdegeri": "Kar su eşdeğeri", "sicaklik_2m": "2 m sıcaklık",
    "ozgul_nem_2m": "Özgül nem", "yagis": "Yağış", "buharlasma": "Buharlaşma", "yuzey_akisi": "Yüzey akışı",
    "toprak_nemi": "Toprak nemi", "ndvi": "Bitki örtüsü (NDVI)", "su_buhari_kolon": "Su buharı",
    "toplam_su_depolama": "Toplam su depolaması", "rakim": "Rakım",
}
SEASONS = {"ocak_mart": "Ocak–Mart", "mart": "Mart", "yillik": "yıllık"}
PRODUCTS = [
    ("MOD10CM", "MODIS/Terra kar örtüsü, aylık 0,05°", "NSIDC"),
    ("GLDAS_NOAH025_M", "GLDAS Noah kara yüzeyi modeli, aylık 0,25°", "GES DISC"),
    ("M2TMNXSLV", "MERRA-2 tek seviye tanı alanları, aylık", "GES DISC"),
    ("GPM_3IMERGM", "GPM IMERG yağış, aylık 0,1°", "GES DISC"),
    ("AIRS3STM", "AIRS yüzey ve atmosfer, aylık 1°", "GES DISC"),
    ("MOD13C2", "MODIS bitki örtüsü indisi, aylık 0,05°", "LP DAAC"),
    ("GRACE/GRACE-FO Mascon", "JPL toplam su depolaması, aylık", "PO.DAAC"),
]


def var_name(key: str | None) -> str:
    """Değişken anahtarını ekrandaki ada çevirir."""
    return VAR_NAMES.get(key or "", key or "—")


def git_commit() -> str | None:
    """run_manifest için çalışan kodun commit kimliği."""
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=5).strip()
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- durum
region_keys = list(REGIONS)
if "region" not in st.session_state:
    st.session_state.region = region_keys[0]
region_key = st.session_state.region
region = REGIONS[region_key]

results, source_path = load_results(region_key)
has_results = results.get("region", {}).get("name") == region_key
placeholder = is_placeholder(results) if has_results else True
card = load_card(results.get("card_id")) if has_results else None
bbox = tuple(results.get("region", {}).get("bbox") or region["bbox"]) if has_results else region["bbox"]
period = period_label(results) if has_results else "2001–2025"

# ---------------------------------------------------------------- hero
with st.container(key="hero"):
    render_hero(build_config(results.get("card_id") if has_results else None, bbox, period, placeholder))

with st.container(key="content"):
    # ------------------------------------------------------------ nasıl çalışır
    anchor("proje")
    section(
        "PROJE NE YAPIYOR",
        "Bir trendi görmek kolay. <span style='color:var(--ember)'>Sebebini sınamak</span> zor.",
        "Trend Dedektifi bir soruyu soruşturma planına çevirir, NASA verisini çeker, istatistik ve fizik testlerini "
        "koşar, sonunda her sayısı analiz çıktısına bağlı bir kanıt tablosu verir.",
    )
    steps = [
        ("01", "Soruyu sor", "“Doğu Anadolu'da kar neden azalıyor?” Araç soruyu bilgi tabanındaki süreç kartlarıyla eşleştirir."),
        ("02", "Şüphelileri seç", "Belirti ve şüpheli değişkenler, her birinin neden seçildiği açıklamasıyla birlikte gelir."),
        ("03", "Veriyi sına", "MODIS, GPM, MERRA-2, GLDAS ve GRACE; düzeltilmiş Mann-Kendall, Sen eğimi, FDR ve fiziksel tahmin."),
        ("04", "Kanıtı göster", "Uyumlu, çelişkili ya da yetersiz. Metindeki her sayı kodla doldurulur ve doğrulanır."),
    ]
    cols = st.columns(4)
    for col, (num, title, body) in zip(cols, steps):
        col.markdown(f'<div class="td-card"><div class="td-step">ADIM {num}</div><h4>{title}</h4><p>{body}</p></div>',
                     unsafe_allow_html=True)

    # ------------------------------------------------------------ soru
    anchor("sorusturma")
    section("SORUŞTURMA", "Sorunu yaz, bölgeni seç.")
    q_col, r_col = st.columns([3, 1.3])
    default_q = results.get("question", "") if has_results else ""
    question = q_col.text_area("Soru", value=default_q, height=110,
                               placeholder="Örn. Doğu Anadolu'da kar nasıl değişiyor ve bu ısınmayla tutarlı mı?")
    chosen = r_col.selectbox("Bölge", region_keys, index=region_keys.index(region_key),
                             format_func=lambda k: REGIONS[k]["label"])
    r_col.markdown(f'<div class="td-kpi-note" style="font-family:JetBrains Mono,monospace;font-size:12px">'
                   f'{html.escape(str(REGIONS[chosen]["bbox"]))}</div>', unsafe_allow_html=True)
    if r_col.button("Soruştur  →", type="primary", use_container_width=True):
        if chosen != region_key:
            st.session_state.region = chosen
            st.rerun()
        st.toast("Demo modunda canlı indirme yapılmaz; bu bölge için önceden hesaplanmış sonuç gösteriliyor.")

    if not has_results:
        st.markdown(f'<div class="td-banner"><b>Bu bölge için henüz sonuç yok.</b> '
                    f'<code>cache/results/</code> altına <code>region.name = "{region_key}"</code> olan bir '
                    f'results.json gelince burada görünecek.</div>', unsafe_allow_html=True)
        st.stop()

    if placeholder:
        st.markdown('<div class="td-banner"><b>YER TUTUCU SONUÇ.</b> Aşağıdaki sayılar '
                    f'<code>{html.escape(source_path.relative_to(ROOT).as_posix())}</code> dosyasından geliyor ve gerçek '
                    'analiz sonucu değil. Gerçek <code>results.json</code> gelince ekran kendiliğinden güncellenir.</div>',
                    unsafe_allow_html=True)

    # ------------------------------------------------------------ plan
    if card:
        section("SORUŞTURMA PLANI", html.escape(card.get("baslik", "")), html.escape(card.get("sade_tanim", "")))
        belirti = card.get("belirti", [])
        supheliler = card.get("supheliler", [])
        cols = st.columns(max(1, len(belirti) + len(supheliler)))
        i = 0
        for b in belirti:
            cols[i].markdown(
                f'<div class="td-card" style="border-color:rgba(255,138,61,.45)"><div class="td-step">BELİRTİ</div>'
                f'<h4>{var_name(b.get("degisken"))}</h4><p>Beklenen yön: {html.escape(str(b.get("beklenen_yon", "—")))}</p>'
                f'<span class="td-tag">{html.escape(str(b.get("urun", "")))}</span></div>', unsafe_allow_html=True)
            i += 1
        for s in supheliler:
            tags = "".join(f'<span class="td-tag">{html.escape(u)}</span>' for u in s.get("urunler", []))
            cols[i].markdown(
                f'<div class="td-card"><div class="td-step" style="color:var(--ice)">ŞÜPHELİ · NEDEN BU?</div>'
                f'<h4>{var_name(s.get("degisken"))}</h4><p>{html.escape(s.get("neden", ""))}</p>{tags}</div>',
                unsafe_allow_html=True)
            i += 1
        alts = card.get("alternatifler") or []
        if alts:
            st.markdown('<p class="td-sub" style="margin-top:18px">Şunu da sorgulayın: '
                        + " · ".join(html.escape(a) for a in alts) + "</p>", unsafe_allow_html=True)

    # ------------------------------------------------------------ modlar
    st.markdown('<div style="height:40px"></div>', unsafe_allow_html=True)
    tab_research, tab_explore = st.tabs(["Araştırma modu", "Keşif modu · Bu trend gerçek mi?"])

    with tab_research:
        trends = by_type(results, "trend")
        shifts = [a for a in results.get("analyses", [])
                  if a.get("observed_shift_m_per_decade") and a.get("predicted_shift_m_per_decade")]
        boundaries = by_type(results, "boundary")

        # KPI şeridi: ana belirtinin trendi
        if trends:
            t0 = trends[0]
            ci = ci_of(t0)
            k = st.columns(4)
            kpis = [
                ("Sen eğimi / 10 yıl", fmt(t0.get("sen_slope_per_decade")), t0.get("units", ""),
                 f"{var_name(t0.get('variable'))} · {t0.get('product', '')}"),
                ("%95 güven aralığı", f"{fmt(ci[0])} … {fmt(ci[1])}" if ci else "—", "", "otokorelasyon için genişletilmiş"),
                ("Mann-Kendall", fmt_p(t0.get("mk_p")), "", "Hamed-Rao düzeltmeli"),
                ("FDR'yi geçen alan", fmt((t0.get("fdr_fraction_significant") or 0) * 100, digits=0), "%",
                 "α_FDR = 0,10 (Wilks, 2016)"),
            ]
            for col, (lab, val, unit, note) in zip(k, kpis):
                col.markdown(f'<div class="td-card"><div class="td-kpi-label">{lab}</div>'
                             f'<div class="td-kpi">{val}<small>{html.escape(unit)}</small></div>'
                             f'<div class="td-kpi-note">{html.escape(note)}</div></div>', unsafe_allow_html=True)

        # Harita
        section("TREND HARİTASI", "Değişim nerede, ne kadar güçlü?",
                "Her piksel için Sen eğimi; noktalı pikseller yanlış keşif oranı (FDR) düzeltmesinden sonra da anlamlı kalanlar.")
        st.markdown('<span class="td-synth">SENTETİK YER TUTUCU</span> '
                    '<span style="color:var(--muted);font-size:14px">Piksel haritası için sonuç sözleşmesinde henüz '
                    "bir dosya biçimi yok; gerçek harita Kişi 2'nin çıktısı tanımlanınca bağlanacak.</span>",
                    unsafe_allow_html=True)
        st.plotly_chart(synthetic_trend_map(bbox), use_container_width=True, config={"displayModeBar": False})

        # Fiziksel test
        if shifts or boundaries:
            section("FİZİKSEL TEST", "Isınma bu hızı açıklıyor mu?",
                    "Isınma sorumluysa kar çizgisi, sıcaklık trendinin sıcaklığın rakımla değişimine oranı hızında yükselmeli. "
                    "Gözlenen aralık tahminle örtüşüyorsa kanıt uyumludur.")
        for a in shifts:
            anchor(f"chart-{a['id']}")
            lab, cls = label_of(a)
            st.markdown(f'<span class="td-badge {cls}">{lab}</span>', unsafe_allow_html=True)
            st.plotly_chart(interval_chart(a["observed_shift_m_per_decade"], a["predicted_shift_m_per_decade"]),
                            use_container_width=True, config={"displayModeBar": False})

        # Kanıt tablosu
        section("KANIT TABLOSU", "Her satır bir analiz, her sayı bir dosyaya bağlı.")
        rows = []
        for a in results.get("analyses", []):
            lab, cls = label_of(a)
            name, value, sig = a.get("id"), "—", "—"
            if a.get("type") == "trend":
                ci = ci_of(a)
                name = f"{var_name(a.get('variable'))} trendi · {a.get('product', '')}"
                value = f"{fmt(a.get('sen_slope_per_decade'), a.get('units'))} / 10 yıl"
                if ci:
                    value += f'<br><span class="muted">%95: {fmt(ci[0])} … {fmt(ci[1])}</span>'
                sig = f"MK {fmt_p(a.get('mk_p'))}<br><span class='muted'>t-testi {fmt_p(a.get('ttest_p'))}</span>"
            elif a.get("observed_shift_m_per_decade"):
                axis = {"rakim": "rakım", "enlem": "enlem", "boylam": "boylam"}.get(a.get("axis"), a.get("axis") or "rakım")
                name = f"Sınır kayması · {axis} ekseni"
                o, p = a["observed_shift_m_per_decade"], a["predicted_shift_m_per_decade"]
                value = (f"gözlenen {fmt(o, digits=0)} m/10 yıl<br>"
                         f"<span class='muted'>tahmin {fmt(p, digits=0)} m/10 yıl</span>")
                sig = "aralık örtüşmesi"
            elif a.get("type") == "boundary":
                name = f"İşaret değiştiren sınır · {a.get('axis', '')}"
                value = f"{fmt(a.get('boundary_m'), 'm', digits=0)}"
                if a.get("boundary_ci95_m"):
                    value += f"<br><span class='muted'>%95: {fmt(a['boundary_ci95_m'], digits=0)} m</span>"
            rows.append(
                f'<tr id="ref-{html.escape(a.get("id", ""))}"><td><b>{html.escape(str(name))}</b><br>'
                f'<span class="muted">{html.escape(a.get("id", ""))}</span></td>'
                f'<td class="num">{value}</td><td class="num">{sig}</td>'
                f'<td><span class="td-badge {cls}">{lab}</span></td></tr>')
        st.markdown('<div class="td-table-wrap"><table class="td-table"><thead><tr><th>Analiz</th><th>Değer</th>'
                    '<th>Anlamlılık</th><th>Etiket</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>",
                    unsafe_allow_html=True)

        # Açıklama (şablon metin; LLM bağlanınca Kişi 4'ün doğrulanmış metni gelecek)
        section("AÇIKLAMA", "Sade dille sonuç",
                "LLM sayı yazmaz; yer tutucu yazar, sayıları kod doldurur ve doğrular. LLM modülü bağlanana kadar "
                "aşağıda kural tabanlı şablon metin gösteriliyor.")
        sentences = []
        reg_label = REGIONS[region_key]["label"].split(" (")[0]
        for a in trends:
            ci = ci_of(a)
            season = SEASONS.get(a.get("mevsim", card.get("mevsim") if card else ""), "")
            s = (f"{reg_label} bölgesinde {season + ' ' if season else ''}{var_name(a.get('variable')).lower()}, "
                 f"{period} döneminde on yılda {fmt(a.get('sen_slope_per_decade'), a.get('units'))} değişti")
            if ci:
                s += f" (%95 aralık {fmt(ci[0])} … {fmt(ci[1])})"
            sentences.append((s + ".", a["id"]))
        for a in shifts:
            lab, _ = label_of(a)
            o, p = a["observed_shift_m_per_decade"], a["predicted_shift_m_per_decade"]
            overlap = max(o[0], p[0]) < min(o[1], p[1])
            s = (f"Kar çizgisinin gözlenen yükselme hızı ({fmt(o, digits=0)} m/10 yıl) ısınmadan beklenen hızla "
                 f"({fmt(p, digits=0)} m/10 yıl) {'örtüşüyor' if overlap else 'örtüşmüyor'}; bu ısınmayla "
                 f"{lab.lower()} kanıttır, tek başına neden kanıtı değildir.")
            sentences.append((s, a["id"]))
        text = " ".join(f'{html.escape(s)}<a class="td-ref" href="#ref-{html.escape(i)}">ref</a>' for s, i in sentences)
        st.markdown(f'<div class="td-explain">{text}</div>', unsafe_allow_html=True)

        # Yeniden üretilebilirlik
        manifest = {
            "run_id": results.get("run_id"), "card_id": results.get("card_id"), "question": question,
            "region": {"name": region_key, "bbox": list(bbox)}, "period": results.get("period"),
            "analyses": [a.get("id") for a in results.get("analyses", [])],
            "results_file": source_path.relative_to(ROOT).as_posix(), "placeholder": placeholder,
            "git_commit": git_commit(),
        }
        st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)
        st.download_button("run_manifest.json indir", json.dumps(manifest, ensure_ascii=False, indent=2),
                           file_name="run_manifest.json", mime="application/json")

    with tab_explore:
        section("KEŞİF MODU", "Bu trend gerçek mi, tesadüf mü?",
                "Aşağıdaki 20 seri tamamen rastgele gürültü; hiçbirinde gerçek trend yok. Yine de bazıları sıradan "
                "t-testinde “anlamlı” görünür. Haritada binlerce piksel varken bu tesadüfler çoğalır; "
                "FDR düzeltmesi tam olarak bunları ayıklar.")
        if "noise_seed" not in st.session_state:
            st.session_state.noise_seed = 2026
        if st.button("Yeni rastgele seriler üret"):
            st.session_state.noise_seed += 1
        fig, hits = noise_experiment(seed=st.session_state.noise_seed)
        st.markdown(f'<div class="td-card" style="margin-bottom:16px"><div class="td-kpi-label">Trendsiz 20 seriden</div>'
                    f'<div class="td-kpi" style="color:var(--ember)">{hits}<small>tanesi p &lt; 0,05 ile “anlamlı” göründü</small></div>'
                    f'<div class="td-kpi-note">Beklenen yaklaşık 1 (yüzde 5). Turuncu çizgiler tesadüfi “trendler”.</div></div>',
                    unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ------------------------------------------------------------ alt bilgi
    items = "".join(f"<li><code>{p}</code> · {d} · {src}</li>" for p, d, src in PRODUCTS)
    st.markdown(f'<div class="td-foot"><b style="color:var(--ink)">Kullanılan NASA verileri</b><ul>{items}</ul>'
                'Trend Dedektifi · NASA Space Apps Challenge 2026 · açık kaynak. '
                "Bu araç NASA tarafından yapılmamıştır; NASA'nın açık verilerini kullanır.</div>",
                unsafe_allow_html=True)
