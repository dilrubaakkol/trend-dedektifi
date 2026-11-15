"""Arayüzün görsel teması: renk belirteçleri, yazı tipleri ve Streamlit üzerine giydirilen CSS.

Tasarım dili: NASA görev kontrol ekranı. Koyu uzay zemini, arkada soluk dönen Dünya, koyu cam paneller,
ince çizgiler, tek vurgu rengi (mavi) ve marka çizgisi (NASA kırmızısına yakın turuncu-kırmızı).
Parıltı, emoji ve her yerde yuvarlak hap yok. Renk veriye ve duruma ayrılır; metin metin renginde yazılır.
"""

import streamlit as st

# ---------------------------------------------------------------- belirteçler (grafikler de kullanır)
BG = "#04070f"          # uzay zemini
SURFACE = "#0b1222"     # panel / grafik zemini
SURFACE_2 = "#101a2e"   # panel başlığı, tablo başlığı
LINE = "#1d2a42"        # ince çizgi
LINE_2 = "#2c3d5c"      # belirgin çizgi
INK = "#e8edf7"         # ana metin
INK_2 = "#b3bed3"       # ikincil metin
MUTED = "#7d89a3"       # soluk metin
BRAND = "#5b9dff"       # etkileşim (seçili sekme, birincil düğme, bağlantı)
BRAND_SOFT = "rgba(91,157,255,.14)"
MISSION = "#fc3d21"     # marka çizgisi (yalnız çerçevede, veride kullanılmaz)

# Veri renkleri: ayrışan ölçek iki kutup + koyu gri orta (dataviz kuralı, koyu yüzey için adımlandı).
UP = "#e5544b"          # artış
DOWN = "#4c8fe0"        # azalış
NEUTRAL = "#2a3346"     # anlamsız / değişim yok
EMPTY = "#121927"       # hesaplanamadı

# Durum renkleri (yalnız etiket + noktayla birlikte).
GOOD = "#2fb565"
WARN = "#e0a127"
SERIOUS = "#e07a3a"
CRIT = "#e5544b"

# Geriye dönük adlar.
EMBER, ICE, OK, BAD, INFO, PANEL, NAVY = SERIOUS, DOWN, GOOD, CRIT, MUTED, SURFACE, "#050912"

# Streamlit'in kendi teması (seçim kutuları, onay kutusu, sekmeler) bununla aynı olur.
STREAMLIT_THEME = {"theme.base": "dark", "theme.primaryColor": BRAND, "theme.backgroundColor": BG,
                   "theme.secondaryBackgroundColor": SURFACE_2, "theme.textColor": INK, "theme.font": "sans-serif"}

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {{
  --bg:{BG}; --surface:{SURFACE}; --surface2:{SURFACE_2}; --line:{LINE}; --line2:{LINE_2};
  --ink:{INK}; --ink2:{INK_2}; --muted:{MUTED}; --brand:{BRAND}; --brand-soft:{BRAND_SOFT}; --mission:{MISSION};
  --up:{UP}; --down:{DOWN}; --neutral:{NEUTRAL}; --empty:{EMPTY};
  --good:{GOOD}; --warn:{WARN}; --serious:{SERIOUS}; --crit:{CRIT};
  --glass:rgba(9,15,29,.80); --radius:6px;
  --display:'Space Grotesk', 'Inter', system-ui, sans-serif;
}}
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
  background:var(--bg) !important; color:var(--ink); font-family:Inter, system-ui, sans-serif;
}}
header[data-testid="stHeader"], #MainMenu, footer, [data-testid="stToolbar"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ display:none !important; }}
.block-container, [data-testid="stMainBlockContainer"] {{ padding:0 !important; max-width:none !important; }}
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {{ gap:0 !important; }}
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:has(style) {{
  display:none; }}
h1, h2, h3, h4 {{ font-family:var(--display) !important; color:var(--ink) !important; letter-spacing:-.01em; }}
a {{ color:var(--brand) !important; text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
.num, .mono {{ font-family:'IBM Plex Mono', monospace; font-feature-settings:"tnum"; }}
code {{ color:var(--ink2) !important; background:var(--surface2) !important; }}

/* ------------------------------------------------ arka plan: soluk dönen Dünya */
.st-key-appbg {{ position:fixed !important; inset:0; z-index:0; pointer-events:none; opacity:.55; }}
.st-key-appbg iframe {{ width:100vw !important; height:100vh !important; border:0; display:block; pointer-events:none; }}
.st-key-appbg::after {{ content:""; position:absolute; inset:0; pointer-events:none;
  background:linear-gradient(180deg, rgba(4,7,15,.35) 0%, rgba(4,7,15,.82) 38%, rgba(4,7,15,.94) 100%); }}
.st-key-masthead, .st-key-navbar, .st-key-content {{ position:relative; z-index:2; }}

/* ------------------------------------------------ üst çubuk */
.st-key-masthead {{ background:rgba(5,9,18,.92); border-top:3px solid var(--mission);
  padding:10px max(24px, calc((100vw - 1200px) / 2)) !important; backdrop-filter:blur(10px); }}
.st-key-masthead [data-testid="stHorizontalBlock"] {{ align-items:center; }}
.td-mast {{ display:flex; align-items:center; gap:14px; flex-wrap:wrap; }}
.td-mark {{ width:34px; height:34px; flex:none; }}
.td-mast .wm {{ font-family:var(--display); color:#fff; font-weight:700; font-size:19px; letter-spacing:.01em; line-height:1.1; }}
.td-mast .wm small {{ display:block; font-family:'IBM Plex Mono', monospace; font-weight:400; font-size:10.5px;
  letter-spacing:.14em; color:var(--muted); text-transform:uppercase; margin-top:3px; }}
.td-mast .who {{ margin-left:auto; color:var(--ink2); font-size:13px; text-align:right; line-height:1.35; }}
.td-mast .who b {{ color:#fff; font-weight:600; }}
.td-mast .who span {{ display:block; color:var(--muted); font-size:12px; }}
.td-mast .tag {{ font-family:'IBM Plex Mono', monospace; font-size:10.5px; letter-spacing:.1em; padding:3px 8px;
  border-radius:3px; border:1px solid var(--line2); color:var(--ink2); }}
.td-mast .tag.live::before {{ content:""; display:inline-block; width:6px; height:6px; border-radius:50%;
  background:var(--good); margin-right:6px; vertical-align:1px; }}
.td-mast .tag.warn {{ border-color:rgba(224,161,39,.5); color:var(--warn); }}
.st-key-masthead .stButton > button {{ background:transparent !important; color:var(--ink2) !important;
  border:1px solid var(--line2) !important; padding:4px 14px !important; font-size:13px !important; min-height:0 !important; }}
.st-key-masthead .stButton > button:hover {{ border-color:var(--ink2) !important; color:#fff !important; }}

.st-key-navbar {{ background:rgba(7,12,24,.9); border-bottom:1px solid var(--line); backdrop-filter:blur(10px);
  padding:0 max(24px, calc((100vw - 1200px) / 2)) !important; }}
.st-key-navbar [data-testid="stButtonGroup"] {{ gap:0 !important; flex-wrap:wrap; }}
.st-key-navbar button[data-variant="segmented_control"] {{ background:transparent !important; border:0 !important;
  border-radius:0 !important; box-shadow:none !important; border-bottom:2px solid transparent !important;
  padding:13px 14px 11px !important; }}
.st-key-navbar button[data-variant="segmented_control"] * {{ font-size:14px !important; font-weight:500 !important;
  color:var(--ink2) !important; }}
.st-key-navbar button[data-variant="segmented_control"]:hover * {{ color:#fff !important; }}
.st-key-navbar button[data-variant="segmented_control"][aria-checked="true"] {{ background:transparent !important;
  border-bottom:2px solid var(--brand) !important; }}
.st-key-navbar button[data-variant="segmented_control"][aria-checked="true"] * {{ color:#fff !important;
  font-weight:600 !important; }}

.st-key-content {{ max-width:1200px; margin:0 auto; padding:30px 24px 80px; }}
@media (max-width:640px) {{ .st-key-content {{ padding:18px 16px 56px; }}
  .st-key-masthead, .st-key-navbar {{ padding-left:16px !important; padding-right:16px !important; }} }}

/* ------------------------------------------------ sayfa başlığı */
.td-kicker {{ font-family:'IBM Plex Mono', monospace; font-size:11.5px; letter-spacing:.14em; text-transform:uppercase;
  color:var(--brand); margin:2px 0 10px; }}
.td-kicker .pill {{ letter-spacing:.08em; color:var(--warn); border:1px solid rgba(224,161,39,.45); border-radius:3px;
  padding:1px 6px; margin-left:10px; }}
.td-answer {{ font-family:var(--display); font-weight:600; font-size:clamp(26px, 2.8vw, 36px); line-height:1.2;
  color:#fff; margin:0 0 10px; letter-spacing:-.015em; max-width:980px; }}
.td-answer .num {{ font-family:var(--display); font-weight:700; }}
.td-answer .up, .td-answer .down, .td-answer .ok, .td-answer .ember {{ color:#fff; }}
.td-answer-sub {{ color:var(--ink2); font-size:16px; line-height:1.65; max-width:860px; margin-bottom:22px; }}
.td-answer-sub b {{ color:#fff; font-weight:600; }}
.td-mini-h {{ font-family:var(--display); font-size:16px; font-weight:600; color:#fff; margin:30px 0 12px; }}
.td-mini-h small {{ font-family:Inter; font-weight:400; color:var(--muted); font-size:13px; margin-left:8px; }}
.td-section {{ border-top:1px solid var(--line); margin:40px 0 0; padding-top:26px; }}
.td-section h3 {{ font-size:21px !important; font-weight:600 !important; margin:0 0 6px !important; }}
.td-section p.lead {{ color:var(--ink2); margin:0 0 14px; max-width:820px; line-height:1.65; }}
.td-note {{ color:var(--muted); font-size:13px; line-height:1.6; margin-top:8px; }}
.td-note b {{ color:var(--ink2); }}

/* ------------------------------------------------ yön işareti */
.td-dir {{ display:inline-block; width:0; height:0; margin:0 7px 4px 2px; vertical-align:middle;
  border-left:7px solid transparent; border-right:7px solid transparent; }}
.td-dir.up {{ border-bottom:10px solid var(--up); }}
.td-dir.down {{ border-top:10px solid var(--down); }}
.td-dir.flat {{ width:12px; height:3px; border:0; background:var(--muted); margin-bottom:6px; }}

/* ------------------------------------------------ paneller */
.td-card, .td-tile, .td-stats, .td-table-wrap, .td-explain, .td-paper, .td-lock,
[data-testid="stPlotlyChart"], [data-testid="stExpander"] {{ background:var(--glass) !important;
  backdrop-filter:blur(8px); -webkit-backdrop-filter:blur(8px); }}
.td-card {{ border:1px solid var(--line); border-radius:var(--radius); padding:18px 20px; }}
.td-grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(240px, 1fr)); gap:12px; margin:6px 0 12px; }}
.td-tile {{ border:1px solid var(--line); border-radius:var(--radius); padding:16px 18px; display:flex;
  flex-direction:column; gap:6px; position:relative; }}
.td-tile::before {{ content:""; position:absolute; left:0; top:14px; bottom:14px; width:2px; background:var(--line2); }}
.td-tile.dim {{ opacity:.82; }}
.td-tile .t-name {{ font-family:var(--display); font-weight:600; font-size:15.5px; color:#fff; }}
.td-tile .t-sub {{ font-family:'IBM Plex Mono', monospace; font-size:11px; letter-spacing:.08em; color:var(--muted); }}
.td-tile .t-val {{ font-family:var(--display); font-weight:600; font-size:26px; color:#fff; line-height:1.2; }}
.td-tile .t-val small {{ font-family:Inter; font-size:13px; color:var(--muted); font-weight:400; margin-left:5px; }}
.td-tile .t-note {{ color:var(--muted); font-size:12.5px; line-height:1.55; }}
.td-tile .t-badges {{ display:flex; gap:6px; flex-wrap:wrap; margin-top:2px; }}

.td-stats {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); border:1px solid var(--line);
  border-radius:var(--radius); margin:6px 0 18px; }}
.td-stats > div {{ padding:16px 20px; border-right:1px solid var(--line); }}
.td-stats > div:last-child {{ border-right:0; }}
.td-stats b {{ display:block; font-family:var(--display); font-weight:600; font-size:28px; color:#fff; line-height:1.15; }}
.td-stats span {{ font-family:'IBM Plex Mono', monospace; font-size:11px; letter-spacing:.08em; text-transform:uppercase;
  color:var(--muted); }}

/* ------------------------------------------------ rozetler (durum: nokta + metin) */
.td-badge {{ display:inline-flex; align-items:center; gap:6px; padding:2px 8px; border-radius:3px; font-size:12px;
  font-weight:500; white-space:nowrap; border:1px solid var(--line2); background:rgba(255,255,255,.03); color:var(--ink2); }}
.td-badge::before {{ content:""; width:6px; height:6px; border-radius:50%; background:var(--muted); flex:none; }}
.td-badge.ok {{ border-color:rgba(47,181,101,.45); color:#8fe0b0; }}
.td-badge.ok::before {{ background:var(--good); }}
.td-badge.warn {{ border-color:rgba(224,161,39,.45); color:#f0cd85; }}
.td-badge.warn::before {{ background:var(--warn); }}
.td-badge.bad {{ border-color:rgba(224,122,58,.5); color:#f3b08a; }}
.td-badge.bad::before {{ background:var(--serious); }}
.td-badge.crit {{ border-color:rgba(229,84,75,.5); color:#f4a29c; }}
.td-badge.crit::before {{ background:var(--crit); }}

/* ------------------------------------------------ tablolar */
.td-table-wrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:var(--radius); }}
.td-table {{ width:100%; border-collapse:collapse; font-size:14px; border:0 !important; margin:0 !important; }}
.td-table th, .td-table td {{ border-left:0 !important; border-right:0 !important; border-top:0 !important; }}
.td-table th {{ text-align:left; font-family:'IBM Plex Mono', monospace; font-size:11px; letter-spacing:.04em;
  font-weight:500; color:var(--muted); padding:10px 14px; background:var(--surface2);
  border-bottom:1px solid var(--line) !important; white-space:nowrap; }}
.td-table td {{ padding:11px 14px; border-bottom:1px solid var(--line) !important; vertical-align:top; color:var(--ink);
  background:transparent; }}
.td-table tr:last-child td {{ border-bottom:0 !important; }}
.td-table tr:hover td {{ background:rgba(91,157,255,.05); }}
.td-table td.num {{ font-family:'IBM Plex Mono', monospace; font-size:13px; white-space:nowrap; }}
.td-table .muted {{ color:var(--muted); font-size:12.5px; }}
.td-table.td-dense td, .td-table.td-dense th {{ padding:6px 10px; font-size:12.5px; }}
.td-scroll {{ max-height:440px; overflow:auto; }}

/* ------------------------------------------------ uyarı ve bilgi kutuları */
.td-callout {{ border:1px solid var(--line); border-left:2px solid var(--brand); background:var(--glass);
  padding:12px 16px; border-radius:0 var(--radius) var(--radius) 0; color:var(--ink2); margin:12px 0; line-height:1.6;
  font-size:14.5px; }}
.td-callout b {{ color:#fff; }}
.td-callout.warn {{ border-left-color:var(--warn); }}
.td-callout.bad {{ border-left-color:var(--serious); }}
.td-li {{ padding-left:16px; position:relative; margin:4px 0; }}
.td-li::before {{ content:""; position:absolute; left:3px; top:.72em; width:5px; height:5px; background:var(--muted); }}

.td-explain {{ font-size:16.5px; line-height:1.75; color:var(--ink); border:1px solid var(--line);
  border-radius:var(--radius); padding:18px 22px; }}
.td-ref {{ font-family:'IBM Plex Mono', monospace; font-size:11px; color:var(--brand) !important;
  border:1px solid rgba(91,157,255,.4); border-radius:3px; padding:0 5px; margin-left:3px; vertical-align:2px; }}

.td-legend {{ display:flex; gap:20px; flex-wrap:wrap; font-size:12.5px; color:var(--ink2); margin:10px 2px 4px; }}
.td-legend i {{ display:inline-block; width:12px; height:12px; border-radius:2px; margin-right:6px; vertical-align:-1px; }}
.td-legend .bar {{ display:inline-block; width:120px; height:8px; border-radius:2px; vertical-align:0; margin:0 8px;
  background:linear-gradient(90deg, {DOWN}, #2f5a8f 35%, {NEUTRAL} 50%, #8f3a35 65%, {UP}); }}

/* ------------------------------------------------ Streamlit bileşenleri */
[data-testid="stWidgetLabel"] p {{ color:var(--ink2) !important; font-size:13px !important; font-weight:500 !important; }}
[data-baseweb="select"] > div, [data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"] {{
  background:var(--surface) !important; border-color:var(--line2) !important; border-radius:var(--radius) !important; }}
[data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input {{
  background:var(--surface) !important; color:var(--ink) !important; font-size:15px !important; }}
[data-baseweb="popover"] ul, [data-baseweb="popover"] [role="listbox"], [data-baseweb="menu"] {{ background:var(--surface2) !important; }}
[data-baseweb="popover"] li:hover, [data-baseweb="popover"] li[aria-selected="true"] {{ background:var(--brand-soft) !important; }}
span[data-baseweb="tag"] {{ background:var(--brand-soft) !important; border:1px solid rgba(91,157,255,.4); }}
span[data-baseweb="tag"] span, span[data-baseweb="tag"] svg {{ color:#cfe0ff !important; }}

.stButton > button, .stDownloadButton > button {{ border-radius:var(--radius); font-weight:500; font-size:14px;
  padding:8px 18px; border:1px solid var(--line2); background:var(--glass); color:var(--ink); box-shadow:none; }}
.stButton > button:hover, .stDownloadButton > button:hover {{ border-color:var(--brand); color:#fff; }}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{ background:var(--brand); color:#04101f;
  border-color:var(--brand); font-weight:600; }}
.stButton > button[kind="primary"] *, .stDownloadButton > button[kind="primary"] * {{ color:#04101f !important; }}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover {{ background:#7cb2ff; }}
button[data-testid="stBaseButton-tertiary"] p {{ color:var(--brand) !important; font-size:13.5px !important; }}
button[data-testid="stBaseButton-tertiary"]:hover p {{ text-decoration:underline; }}

/* Seçim düğmeleri (pills / segmented) */
[data-testid="stButtonGroup"] button {{ border-radius:var(--radius) !important; padding:5px 13px !important; }}
button[data-variant="pills"], button[data-variant="segmented_control"] {{ background:var(--glass) !important;
  border:1px solid var(--line2) !important; box-shadow:none !important; }}
button[data-variant="pills"] *, button[data-variant="segmented_control"] * {{ color:var(--ink2) !important;
  font-size:13.5px !important; font-weight:500 !important; }}
button[data-variant="pills"]:hover, button[data-variant="segmented_control"]:hover {{ border-color:var(--brand) !important; }}
button[data-variant="pills"][aria-checked="true"], button[data-variant="segmented_control"][aria-checked="true"] {{
  background:var(--brand-soft) !important; border-color:var(--brand) !important; position:relative; z-index:1; }}
button[data-variant][aria-checked="true"] * {{ color:#fff !important; font-weight:600 !important; }}

[data-testid="stExpander"], [data-testid="stExpander"] details {{ border-color:var(--line) !important;
  border-radius:var(--radius) !important; }}
[data-testid="stExpander"] summary p {{ font-weight:500; font-size:14.5px; color:var(--ink) !important; }}
[data-testid="stExpander"] summary:hover p {{ color:var(--brand) !important; }}
[data-testid="stTabs"] button p {{ font-weight:500; font-size:14px; }}
[data-baseweb="tab-highlight"] {{ background:var(--brand) !important; }}
[data-baseweb="tab-border"] {{ background:var(--line) !important; }}
[data-testid="stPlotlyChart"] {{ border:1px solid var(--line); border-radius:var(--radius); overflow:hidden; }}
[data-testid="stCode"] pre, [data-testid="stCodeBlock"] pre {{ background:var(--surface) !important;
  border:1px solid var(--line); border-radius:var(--radius); }}
[data-testid="stCaptionContainer"] p {{ color:var(--muted) !important; }}
[data-testid="stCheckbox"] p {{ color:var(--ink2) !important; font-size:14px !important; font-family:Inter !important;
  letter-spacing:0 !important; text-transform:none !important; }}

/* ------------------------------------------------ yayınlar, adımlar */
.td-paper {{ border:1px solid var(--line); border-radius:var(--radius); padding:16px 18px; margin-bottom:10px; }}
.td-paper .p-top {{ display:flex; gap:8px; align-items:center; }}
.td-paper .p-year {{ margin-left:auto; font-family:'IBM Plex Mono', monospace; color:var(--muted); font-size:12.5px; }}
.td-paper h4 {{ margin:8px 0 4px; font-size:16.5px !important; font-weight:600 !important; }}
.td-paper .p-meta {{ color:var(--ink2); font-size:13.5px; line-height:1.6; }}
.td-paper p {{ color:var(--ink2); font-size:14px; margin:6px 0 4px; line-height:1.6; }}
.td-tag {{ display:inline-block; font-size:12px; padding:1px 8px; border-radius:3px; border:1px solid var(--line2);
  color:var(--ink2); margin:6px 6px 0 0; }}
.td-step-h {{ font-family:var(--display); font-weight:600; font-size:16px; color:#fff; margin:24px 0 10px; }}
.td-step-h b {{ display:inline-grid; place-items:center; width:22px; height:22px; border:1px solid var(--brand);
  color:var(--brand); font-family:'IBM Plex Mono', monospace; font-size:11.5px; margin-right:10px; vertical-align:1px; }}
.td-step-h span {{ font-family:Inter; color:var(--muted); font-size:13px; font-weight:400; }}
.td-lock {{ text-align:center; padding:36px 24px; border:1px dashed var(--line2); border-radius:var(--radius); }}
.td-lock h3 {{ margin:0 0 6px; font-size:18px !important; }}
.td-lock p {{ color:var(--ink2); max-width:560px; margin:0 auto; }}

.td-foot {{ margin-top:64px; padding-top:18px; border-top:1px solid var(--line); color:var(--muted); font-size:12.5px;
  line-height:1.8; }}
.td-foot b {{ color:var(--ink2); }}

/* ------------------------------------------------ giriş ekranı */
.st-key-herobg {{ position:fixed !important; inset:0; z-index:0; }}
.st-key-herobg iframe {{ width:100vw !important; height:100vh !important; border:0; display:block; }}
.st-key-login {{ position:relative; z-index:2; min-height:calc(100vh - 24px); max-width:1200px; margin:0 auto;
  padding:12px 40px; justify-content:center; }}
@media (max-width:900px) {{ .st-key-login {{ padding:24px 16px; }} }}
.st-key-logincard {{ background:rgba(8,13,26,.86); backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px);
  border:1px solid var(--line2); border-top:3px solid var(--mission); border-radius:var(--radius);
  padding:26px 28px 18px !important; box-shadow:0 30px 80px rgba(0,0,0,.55); max-width:440px; margin-left:auto; }}
.st-key-logincard [data-testid="stButtonGroup"] {{ width:100%; }}
.st-key-logincard [data-testid="stButtonGroup"] button {{ flex:1; padding:8px 0 !important; }}
.td-card-h {{ font-family:var(--display); font-weight:600; font-size:23px; color:#fff; margin:16px 0 2px; }}
.td-card-s {{ color:var(--ink2); font-size:14px; margin-bottom:12px; line-height:1.55; }}
.td-or {{ display:flex; align-items:center; gap:12px; color:var(--muted); font-size:12px; margin:6px 0 10px; }}
.td-or::before, .td-or::after {{ content:""; flex:1; height:1px; background:var(--line); }}
.td-demo-code {{ font-size:13px; color:#f0cd85; border:1px solid rgba(224,161,39,.45); border-radius:var(--radius);
  padding:10px 12px; margin-bottom:12px; }}
.td-demo-code b {{ font-family:'IBM Plex Mono'; font-size:17px; letter-spacing:.2em; color:#fff; }}
.td-login-brand {{ display:flex; align-items:center; gap:12px; font-family:'IBM Plex Mono', monospace; color:var(--ink2);
  font-size:11.5px; letter-spacing:.14em; text-transform:uppercase; }}
.td-login-h {{ font-family:var(--display); font-weight:700; font-size:clamp(36px, 4.2vw, 56px); line-height:1.06;
  color:#fff; margin:18px 0 16px; letter-spacing:-.02em; }}
.td-login-h em {{ font-style:normal; color:var(--brand); }}
.td-login-p {{ color:var(--ink2); font-size:17px; line-height:1.65; max-width:520px; }}
.td-login-facts {{ display:flex; gap:30px; flex-wrap:wrap; margin-top:28px; border-top:1px solid var(--line2);
  padding-top:18px; max-width:560px; }}
.td-login-facts b {{ display:block; color:#fff; font-family:var(--display); font-weight:600; font-size:24px; }}
.td-login-facts span {{ font-family:'IBM Plex Mono', monospace; color:var(--muted); font-size:10.5px; letter-spacing:.1em;
  text-transform:uppercase; }}
.td-login-ph {{ display:inline-block; margin-top:18px; font-family:'IBM Plex Mono'; font-size:11px; letter-spacing:.1em;
  color:var(--warn); border:1px solid rgba(224,161,39,.45); border-radius:3px; padding:3px 8px; }}
</style>
"""

# Özgün amblem (NASA logosu değildir): yörünge elipsi, uydu noktası, Türkiye'yi simgeleyen yay.
MARK_SVG = ('<svg class="td-mark" viewBox="0 0 40 40" aria-hidden="true">'
            '<circle cx="20" cy="20" r="18.5" fill="#0b1a3a" stroke="#2c3d5c"/>'
            '<ellipse cx="20" cy="20" rx="17" ry="7" fill="none" stroke="#5b9dff" stroke-width="1.4" '
            'transform="rotate(-22 20 20)"/>'
            '<path d="M9 25 Q20 17 31 23" fill="none" stroke="#fc3d21" stroke-width="2" stroke-linecap="round"/>'
            '<circle cx="33.2" cy="13.6" r="2.2" fill="#fff"/></svg>')


def inject_theme() -> None:
    """Tema CSS'ini sayfaya ekler."""
    st.markdown(CSS, unsafe_allow_html=True)


def apply_streamlit_theme() -> None:
    """Streamlit'in kendi temasını (seçim kutuları, sekmeler) bu temayla eşler; kök config dosyası gerekmez."""
    for opt, val in STREAMLIT_THEME.items():
        try:
            st._config.set_option(opt, val)
        except Exception:  # noqa: BLE001 — sürüm farkı: tema CSS ile yine uygulanır
            pass


def anchor(anchor_id: str) -> None:
    """[ref] bağlantılarının kaydırdığı görünmez çapa."""
    st.markdown(f'<div id="{anchor_id}" style="position:relative;top:-24px"></div>', unsafe_allow_html=True)


def section(eyebrow: str, title: str, sub: str | None = None) -> None:
    """Bölüm başlığı: üst çizgi, başlık ve isteğe bağlı açıklama (`eyebrow` geriye dönük, kullanılmaz)."""
    html = f'<div class="td-section"><h3>{title}</h3>'
    if sub:
        html += f'<p class="lead">{sub}</p>'
    st.markdown(html + "</div>", unsafe_allow_html=True)
