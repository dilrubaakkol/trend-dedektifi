"""Arayüzün görsel teması: renk belirteçleri, yazı tipleri ve Streamlit üzerine giydirilen CSS."""

import streamlit as st

# Renk belirteçleri — grafikler de aynı değerleri kullanır.
BG = "#03050f"
PANEL = "#0a1126"
PANEL_2 = "#0e1733"
LINE = "rgba(140,170,230,0.18)"
INK = "#eaf0ff"
MUTED = "#8796bd"
ICE = "#5cc8ff"
EMBER = "#ff8a3d"
OK = "#3ddc97"
BAD = "#ff5d6c"
WARN = "#f5c451"
INFO = "#8a93a8"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Exo+2:wght@600;700;800;900&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;600&display=swap');

:root {{
  --bg:{BG}; --panel:{PANEL}; --panel2:{PANEL_2}; --line:{LINE}; --ink:{INK}; --muted:{MUTED};
  --ice:{ICE}; --ember:{EMBER}; --ok:{OK}; --bad:{BAD}; --warn:{WARN}; --info:{INFO};
}}
html, body, .stApp, [data-testid="stAppViewContainer"] {{
  background: var(--bg) !important; color: var(--ink);
  font-family: Inter, system-ui, sans-serif;
}}
.stApp {{
  background:
    radial-gradient(1200px 600px at 85% 40%, rgba(40,70,160,.12), transparent 70%),
    radial-gradient(900px 500px at 10% 80%, rgba(255,138,61,.05), transparent 70%),
    var(--bg) !important;
}}
header[data-testid="stHeader"], #MainMenu, footer, [data-testid="stToolbar"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ display:none !important; }}
.block-container, [data-testid="stMainBlockContainer"] {{
  padding: 0 !important; max-width: none !important;
}}

/* Hero tam ekran */
.st-key-hero iframe {{ width:100% !important; height:100vh !important; min-height:640px; border:0; display:block; }}
.st-key-hero {{ gap:0 !important; }}

/* İçerik sütunu */
.st-key-content {{ max-width:1180px; margin:0 auto; padding:24px 24px 96px; }}
@media (max-width:640px) {{ .st-key-content {{ padding:16px 16px 64px; }} }}

h1, h2, h3, h4 {{ font-family:'Exo 2', sans-serif !important; color:var(--ink) !important; letter-spacing:-.005em; }}
p, li, label, span {{ color: inherit; }}
a {{ color: var(--ice) !important; }}

.td-eyebrow {{ font-family:'JetBrains Mono', monospace; font-size:12px; letter-spacing:.22em;
  text-transform:uppercase; color:var(--muted); margin:72px 0 6px; }}
.td-eyebrow b {{ color:var(--ember); font-weight:600; }}
.td-h2 {{ font-family:'Exo 2', sans-serif; font-weight:800; font-size:clamp(28px,3.2vw,42px);
  line-height:1.1; margin:0 0 14px; color:var(--ink); }}
.td-sub {{ color:#b9c5e4; font-size:17px; line-height:1.65; max-width:760px; margin:0 0 26px; }}

.td-card {{ background:linear-gradient(180deg, rgba(16,26,58,.75), rgba(8,13,32,.75));
  border:1px solid var(--line); border-radius:18px; padding:22px 22px 20px; height:100%;
  backdrop-filter: blur(6px); }}
.td-card h4 {{ margin:6px 0 8px; font-size:19px; }}
.td-card p {{ margin:0; color:#aebbdc; font-size:15px; line-height:1.6; }}
.td-step {{ font-family:'JetBrains Mono', monospace; color:var(--ember); font-size:12px; letter-spacing:.18em; }}
.td-tag {{ display:inline-block; font-family:'JetBrains Mono', monospace; font-size:11px; letter-spacing:.12em;
  padding:3px 9px; border-radius:999px; border:1px solid var(--line); color:var(--muted); margin:8px 6px 0 0; }}

.td-kpi {{ font-family:'Exo 2', sans-serif; font-weight:800; font-size:40px; line-height:1; color:var(--ink); }}
.td-kpi small {{ font-size:15px; color:var(--muted); font-weight:600; margin-left:6px; }}
.td-kpi-label {{ font-family:'JetBrains Mono', monospace; font-size:11px; letter-spacing:.16em;
  text-transform:uppercase; color:var(--muted); margin-bottom:10px; }}
.td-kpi-note {{ color:#aebbdc; font-size:14px; margin-top:8px; }}

.td-banner {{ border:1px solid rgba(245,196,81,.35); background:rgba(245,196,81,.07); color:#f3dc9c;
  border-radius:14px; padding:12px 16px; font-size:14px; margin:18px 0 0; }}
.td-banner b {{ color:var(--warn); }}
.td-synth {{ display:inline-block; font-family:'JetBrains Mono', monospace; font-size:11px; letter-spacing:.14em;
  color:#1a1405; background:var(--warn); border-radius:6px; padding:3px 8px; margin-bottom:8px; }}

/* Kanıt tablosu */
.td-table {{ width:100%; border-collapse:separate; border-spacing:0; font-size:15px;
  border:1px solid var(--line); border-radius:16px; overflow:hidden; }}
.td-table th {{ text-align:left; font-family:'JetBrains Mono', monospace; font-size:11px; letter-spacing:.14em;
  text-transform:uppercase; color:var(--muted); font-weight:600; padding:14px 16px; background:rgba(14,23,51,.9);
  border-bottom:1px solid var(--line); }}
.td-table td {{ padding:16px; border-bottom:1px solid var(--line); vertical-align:top; color:#dbe4fb;
  background:rgba(8,13,32,.6); }}
.td-table tr:last-child td {{ border-bottom:0; }}
.td-table td.num {{ font-family:'JetBrains Mono', monospace; font-size:14px; white-space:nowrap; }}
.td-table .muted {{ color:var(--muted); font-size:13px; }}
.td-badge {{ display:inline-block; padding:5px 12px; border-radius:999px; font-weight:600; font-size:13px; white-space:nowrap; }}
.td-badge.ok {{ color:var(--ok); background:rgba(61,220,151,.12); border:1px solid rgba(61,220,151,.4); }}
.td-badge.bad {{ color:var(--bad); background:rgba(255,93,108,.12); border:1px solid rgba(255,93,108,.4); }}
.td-badge.warn {{ color:var(--warn); background:rgba(245,196,81,.12); border:1px solid rgba(245,196,81,.4); }}
.td-badge.info {{ color:var(--info); background:rgba(138,147,168,.12); border:1px solid rgba(138,147,168,.4); }}
.td-table-wrap {{ overflow-x:auto; }}

.td-explain {{ font-size:18px; line-height:1.8; color:#dbe4fb; border-left:3px solid var(--ice);
  padding:6px 0 6px 20px; }}
.td-ref {{ font-family:'JetBrains Mono', monospace; font-size:11px; color:var(--ice) !important; text-decoration:none;
  border:1px solid rgba(92,200,255,.35); border-radius:6px; padding:1px 6px; margin-left:4px; vertical-align:2px; }}
.td-ref:hover {{ background:rgba(92,200,255,.12); }}

/* Streamlit bileşenleri */
[data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input {{
  background:var(--panel) !important; color:var(--ink) !important; border:1px solid var(--line) !important;
  border-radius:14px !important; font-size:17px !important; }}
[data-baseweb="select"] > div {{ background:var(--panel) !important; border:1px solid var(--line) !important;
  border-radius:14px !important; color:var(--ink) !important; }}
[data-testid="stWidgetLabel"] p {{ color:var(--muted) !important; font-family:'JetBrains Mono', monospace;
  font-size:12px !important; letter-spacing:.14em; text-transform:uppercase; }}
.stButton > button, .stDownloadButton > button {{
  font-family:'Exo 2', sans-serif; font-weight:700; letter-spacing:.03em; border-radius:999px;
  padding:10px 26px; border:1px solid var(--line); background:var(--panel2); color:var(--ink); }}
.stButton > button[kind="primary"] {{ background:var(--ember); color:#1a0d05; border-color:transparent;
  box-shadow:0 8px 30px rgba(255,138,61,.3); }}
.stButton > button:hover {{ border-color:var(--ice); color:var(--ink); }}
.stButton > button[kind="primary"]:hover {{ background:#ff9a55; color:#1a0d05; }}
[data-testid="stTabs"] button p {{ font-family:'Exo 2', sans-serif; font-weight:700; font-size:16px; }}
[data-baseweb="tab-highlight"] {{ background:var(--ember) !important; }}
[data-testid="stExpander"] {{ border:1px solid var(--line) !important; border-radius:14px !important; background:rgba(8,13,32,.6); }}
[data-testid="stPlotlyChart"] {{ border:1px solid var(--line); border-radius:18px; overflow:hidden;
  background:rgba(8,13,32,.6); }}
.td-foot {{ margin-top:90px; padding-top:22px; border-top:1px solid var(--line); color:var(--muted); font-size:13px; line-height:1.8; }}
.td-foot code {{ color:#c6d2ee; background:transparent; }}
</style>
"""


def inject_theme() -> None:
    """Tema CSS'ini sayfaya ekler."""
    st.markdown(CSS, unsafe_allow_html=True)


def anchor(anchor_id: str) -> None:
    """Hero düğmelerinin ve [ref] bağlantılarının kaydırdığı görünmez çapa."""
    st.markdown(f'<div id="{anchor_id}" style="position:relative;top:-24px"></div>', unsafe_allow_html=True)


def section(eyebrow: str, title: str, sub: str | None = None) -> None:
    """Bölüm başlığı: küçük üst etiket, büyük başlık, isteğe bağlı açıklama."""
    html = f'<div class="td-eyebrow">{eyebrow}</div><div class="td-h2">{title}</div>'
    if sub:
        html += f'<p class="td-sub">{sub}</p>'
    st.markdown(html, unsafe_allow_html=True)
