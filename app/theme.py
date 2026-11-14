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
.st-key-content {{ max-width:1180px; margin:0 auto; padding:28px 24px 96px; }}
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
/* Giriş paneli */
.td-role {{ position:relative; background:linear-gradient(180deg, rgba(16,26,58,.8), rgba(8,13,32,.8));
  border:1px solid var(--line); border-radius:22px; padding:26px 26px 22px; height:100%; overflow:hidden;
  transition:border-color .25s ease, box-shadow .25s ease; }}
.td-role::after {{ content:""; position:absolute; right:-60px; top:-60px; width:180px; height:180px; border-radius:50%;
  background:radial-gradient(circle, rgba(92,200,255,.16), transparent 70%); pointer-events:none; }}
.td-role.ember::after {{ background:radial-gradient(circle, rgba(255,138,61,.18), transparent 70%); }}
.td-role.on {{ border-color:var(--ice); box-shadow:0 0 0 1px var(--ice), 0 18px 60px rgba(92,200,255,.12); }}
.td-role.ember.on {{ border-color:var(--ember); box-shadow:0 0 0 1px var(--ember), 0 18px 60px rgba(255,138,61,.14); }}
.td-role .ico {{ font-size:40px; color:var(--ice); }}
.td-role.ember .ico {{ color:var(--ember); }}
.td-role h3 {{ margin:8px 0 2px; font-size:30px; }}
.td-role .who {{ color:var(--muted); font-size:14px; margin-bottom:14px; }}
.td-role ul {{ margin:0; padding-left:18px; color:#c6d2ee; font-size:15px; line-height:1.75; }}
.td-note {{ color:var(--muted); font-size:13px; line-height:1.6; margin-top:10px; }}
.td-note b {{ color:#c6d2ee; }}

.td-userbar {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; padding:10px 16px; min-height:44px; color:#c6d2ee;
  border:1px solid var(--line); border-radius:16px; background:rgba(8,13,32,.7); }}
.td-avatar {{ width:40px; height:40px; border-radius:50%; display:grid; place-items:center; font-family:'Exo 2';
  font-weight:800; color:#1a0d05; background:var(--ember); flex:none; }}
.td-avatar.ice {{ background:var(--ice); color:#04121c; }}
.td-userbar .nm {{ font-weight:600; color:var(--ink); }}
.td-userbar .meta {{ color:var(--muted); font-size:13px; }}

.td-lock {{ text-align:center; padding:44px 24px; border:1px dashed rgba(255,138,61,.45); border-radius:22px;
  background:rgba(255,138,61,.04); }}
.td-lock .big {{ font-size:34px; color:var(--ember); }}
.td-lock h3 {{ margin:8px 0 6px; }}
.td-lock p {{ color:#b9c5e4; max-width:560px; margin:0 auto; }}

.td-stats {{ display:flex; flex-wrap:wrap; gap:0; border:1px solid var(--line); border-radius:18px; overflow:hidden;
  margin-top:26px; background:rgba(8,13,32,.6); }}
.td-stats > div {{ flex:1 1 150px; padding:18px 20px; border-right:1px solid var(--line); }}
.td-stats > div:last-child {{ border-right:0; }}
.td-stats b {{ display:block; font-family:'Exo 2'; font-size:30px; font-weight:800; color:var(--ink); line-height:1.1; }}
.td-stats span {{ font-family:'JetBrains Mono', monospace; font-size:11px; letter-spacing:.14em; color:var(--muted);
  text-transform:uppercase; }}

.td-sentence {{ padding:16px 18px; border:1px solid var(--line); border-radius:14px; background:rgba(8,13,32,.6);
  margin-bottom:10px; color:#dbe4fb; line-height:1.65; font-size:16px; }}
.td-sentence .v {{ font-family:'Exo 2'; font-weight:700; color:var(--ink); }}
.td-sentence .up {{ color:var(--bad); font-weight:600; }}
.td-sentence .down {{ color:var(--ice); font-weight:600; }}
.td-legend {{ display:flex; gap:18px; flex-wrap:wrap; font-size:13px; color:var(--muted); margin:6px 0 10px; }}
.td-legend i {{ display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:6px; vertical-align:-1px; }}

span[data-baseweb="tag"] {{ background:rgba(255,138,61,.16) !important; color:var(--ember) !important;
  border:1px solid rgba(255,138,61,.45); }}
span[data-baseweb="tag"] span, span[data-baseweb="tag"] svg {{ color:var(--ember) !important; }}
[data-testid="stBaseButton-segmented_controlActive"] *, [data-testid="stBaseButton-pillsActive"] * {{
  color:var(--ember) !important; }}
[data-testid="stBaseButton-segmented_controlActive"], [data-testid="stBaseButton-pillsActive"],
button[kind="segmented_controlActive"], button[kind="pillsActive"] {{ color:var(--ember) !important;
  font-weight:700 !important;
  border-color:var(--ember) !important; background:rgba(255,138,61,.12) !important; }}
[data-testid="stBaseButton-segmented_control"], [data-testid="stBaseButton-pills"],
button[kind="segmented_control"], button[kind="pills"] {{ background:rgba(8,13,32,.7) !important; color:#c6d2ee !important;
  border-color:var(--line) !important; }}
[data-testid="stSegmentedControl"] button, [data-testid="stButtonGroup"] button {{
  font-family:'Exo 2', sans-serif; font-weight:700; }}
[data-testid="stCode"] pre, [data-testid="stCodeBlock"] pre {{ background:var(--panel) !important; border:1px solid var(--line);
  border-radius:12px; }}
[data-testid="stDataFrame"] {{ border:1px solid var(--line); border-radius:14px; overflow:hidden; }}
/* Büyük cevap cümlesi */
.td-answer {{ font-family:'Exo 2', sans-serif; font-weight:800; font-size:clamp(26px,3vw,40px); line-height:1.18;
  color:var(--ink); margin:26px 0 10px; letter-spacing:-.005em; max-width:1000px; }}
.td-answer .up, .td-answer-sub .up {{ color:#ff6b6b; }}
.td-answer .down, .td-answer-sub .down {{ color:var(--ice); }}
.td-answer .ok {{ color:var(--ok); }} .td-answer .ember {{ color:var(--ember); }}
.td-answer-sub {{ color:#b9c5e4; font-size:17px; line-height:1.6; max-width:860px; margin-bottom:18px; }}
.td-mini-h {{ font-family:'JetBrains Mono', monospace; font-size:12px; letter-spacing:.18em; text-transform:uppercase;
  color:var(--muted); margin:26px 0 10px; }}

/* Kutucuklar */
.td-grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(230px, 1fr)); gap:14px; margin:8px 0 10px; }}
.td-tile {{ background:linear-gradient(180deg, rgba(16,26,58,.85), rgba(8,13,32,.85)); border:1px solid var(--line);
  border-radius:18px; padding:20px; height:100%; }}
.td-tile.dim {{ opacity:.72; }}
.td-tile .t-ico {{ font-size:28px; margin-bottom:6px; }}
.td-tile .t-name {{ font-family:'Exo 2'; font-weight:700; font-size:19px; color:var(--ink); margin-bottom:6px; }}
.td-tile .t-val {{ font-family:'Exo 2'; font-weight:800; font-size:32px; line-height:1.1; margin-bottom:10px; }}
.td-tile .t-val small {{ font-size:14px; color:var(--muted); font-weight:600; }}
.td-tile .t-val.up {{ color:#ff6b6b; }} .td-tile .t-val.down {{ color:var(--ice); }}
.td-tile .t-note {{ color:#aebbdc; font-size:13px; margin-top:8px; line-height:1.55; }}

/* Nasıl çalışır akışı */
.td-flow-row {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:18px; position:relative; }}
@media (max-width:820px) {{ .td-flow-row {{ grid-template-columns:1fr; }} }}
.td-flow {{ position:relative; padding:28px 26px; border:1px solid var(--line); border-radius:22px;
  background:linear-gradient(180deg, rgba(16,26,58,.8), rgba(8,13,32,.8)); }}
.td-flow .f-ico {{ font-size:44px; line-height:1; }}
.td-flow .f-n {{ position:absolute; right:24px; top:22px; font-family:'JetBrains Mono'; color:var(--ember);
  font-size:13px; letter-spacing:.2em; }}
.td-flow h4 {{ font-size:24px !important; margin:16px 0 8px; }}
.td-flow p {{ color:#b9c5e4; font-size:16px; line-height:1.6; margin:0; }}

.td-callout {{ border-left:3px solid var(--ember); background:rgba(255,138,61,.06); padding:14px 18px;
  border-radius:0 14px 14px 0; color:#e3d6cc; margin-top:14px; line-height:1.6; }}
.td-callout.warn {{ border-left-color:var(--warn); background:rgba(255,200,87,.07); margin-bottom:10px; }}
.td-callout.warn .td-li {{ font-size:14px; color:#d8cfb6; }}
.td-chip {{ display:inline-block; font-family:'JetBrains Mono', monospace; font-size:11px; letter-spacing:.12em;
  padding:5px 10px; border-radius:999px; margin-left:auto; }}
.td-chip.warn {{ color:var(--warn); border:1px solid rgba(245,196,81,.45); background:rgba(245,196,81,.08); cursor:help; }}
.td-step-h {{ font-family:'Exo 2'; font-weight:700; font-size:20px; color:var(--ink); margin:22px 0 10px; }}
.td-step-h b {{ display:inline-grid; place-items:center; width:30px; height:30px; border-radius:50%; background:var(--ember);
  color:#1a0d05; font-size:15px; margin-right:10px; }}
.td-step-h span {{ color:var(--muted); font-size:14px; font-weight:500; }}
.td-scroll {{ max-height:420px; overflow:auto; }}
.td-table.td-dense td, .td-table.td-dense th {{ padding:8px 12px; font-size:13px; }}

/* Streamlit bileşenlerini temaya uydur */
[data-baseweb="select"] > div, [data-baseweb="select"] div[class*="ValueContainer"],
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="input"] input {{
  background-color:var(--panel) !important; color:var(--ink) !important; }}
[data-baseweb="popover"] ul, [data-baseweb="popover"] [role="listbox"], [data-baseweb="menu"] {{
  background:var(--panel2) !important; }}
[data-baseweb="popover"] li {{ color:var(--ink) !important; }}
[data-baseweb="popover"] li:hover, [data-baseweb="popover"] li[aria-selected="true"] {{ background:rgba(92,200,255,.12) !important; }}
[data-testid="stPills"] button, [data-testid="stButtonGroup"] button {{ border-radius:999px !important; padding:6px 16px !important;
  font-size:15px !important; }}
[data-testid="stExpander"] summary p {{ font-family:'Exo 2'; font-weight:700; font-size:16px; color:var(--ink); }}
[data-testid="stTabs"] [data-baseweb="tab-list"] {{ background:transparent; }}
[data-testid="stCaptionContainer"] p {{ color:var(--muted) !important; }}
.td-chip {{ border:1px solid var(--line); color:var(--muted); }}
.td-chip.ok {{ color:var(--ok); border-color:rgba(61,220,151,.4); background:rgba(61,220,151,.07); margin-left:8px; }}
.td-chip.warn + .td-chip {{ margin-left:8px; }}
.td-paper {{ border:1px solid var(--line); border-radius:18px; padding:18px 20px; margin-bottom:12px;
  background:linear-gradient(180deg, rgba(16,26,58,.75), rgba(8,13,32,.75)); }}
.td-paper .p-top {{ display:flex; gap:8px; align-items:center; }}
.td-paper .p-year {{ margin-left:auto; font-family:'JetBrains Mono'; color:var(--muted); font-size:13px; }}
.td-paper h4 {{ margin:10px 0 6px; font-size:19px !important; }}
.td-paper .p-meta {{ color:#aebbdc; font-size:14px; line-height:1.6; }}
.td-paper p {{ color:#c6d2ee; font-size:15px; margin:8px 0 4px; line-height:1.6; }}
/* Giriş ekranı: Dünya sabit arka planda, sayfa kaymaz */
.st-key-herobg {{ position:fixed !important; inset:0; z-index:0; }}
.st-key-herobg iframe {{ width:100vw !important; height:100vh !important; border:0; display:block; }}
.st-key-login {{ position:relative; z-index:2; min-height:calc(100vh - 24px); max-width:1240px; margin:0 auto;
  padding:12px 40px; justify-content:center; }}
.st-key-logincard [data-testid="stCheckbox"] p {{ text-transform:none !important; font-family:Inter, sans-serif !important;
  letter-spacing:0 !important; font-size:13px !important; color:#aebbdc !important; }}
@media (max-width:900px) {{ .st-key-login {{ padding:24px 16px; }} }}
.st-key-logincard {{ background:rgba(6,10,28,.74); backdrop-filter:blur(16px); -webkit-backdrop-filter:blur(16px);
  border:1px solid rgba(140,170,230,.24); border-radius:26px; padding:26px 28px 18px !important;
  box-shadow:0 30px 90px rgba(0,0,0,.55), inset 0 1px 0 rgba(255,255,255,.04); max-width:470px; margin-left:auto; }}
.st-key-logincard [data-testid="stWidgetLabel"] p {{ font-size:11px !important; }}
.st-key-logincard [data-testid="stTextInput"] input {{ font-size:16px !important; padding:12px 14px !important; }}
.st-key-logincard [data-testid="stButtonGroup"] {{ width:100%; }}
.st-key-logincard [data-testid="stButtonGroup"] button {{ flex:1; padding:10px 0 !important; }}
.td-card-h {{ font-family:'Exo 2'; font-weight:800; font-size:28px; color:var(--ink); margin:14px 0 2px; }}
.td-card-s {{ color:#aebbdc; font-size:15px; margin-bottom:14px; line-height:1.55; }}
.td-or {{ display:flex; align-items:center; gap:12px; color:var(--muted); font-size:12px; margin:6px 0 10px; }}
.td-or::before, .td-or::after {{ content:""; flex:1; height:1px; background:var(--line); }}
.td-demo-code {{ font-size:13px; color:var(--warn); border:1px dashed rgba(245,196,81,.5); border-radius:12px;
  padding:10px 12px; margin-bottom:12px; background:rgba(245,196,81,.06); }}
.td-demo-code b {{ font-family:'JetBrains Mono'; font-size:18px; letter-spacing:.25em; color:var(--ink); }}
button[data-testid="stBaseButton-tertiary"] p {{ color:var(--ice) !important; font-size:14px !important; }}
button[data-testid="stBaseButton-tertiary"]:hover p {{ text-decoration:underline; }}
.td-login-brand {{ font-family:'Exo 2'; font-weight:800; letter-spacing:.22em; font-size:15px; color:var(--ink); }}
.td-login-h {{ font-family:'Exo 2'; font-weight:900; font-size:clamp(38px,4.6vw,66px); line-height:1.04;
  color:var(--ink); margin:18px 0 18px; text-shadow:0 4px 40px rgba(0,0,0,.7); }}
.td-login-p {{ color:#c6d2ee; font-size:18px; line-height:1.65; max-width:520px; text-shadow:0 2px 18px rgba(0,0,0,.9); }}
.td-login-feats {{ display:flex; gap:12px; flex-wrap:wrap; margin-top:26px; }}
.td-login-feats > div {{ padding:12px 16px; border:1px solid var(--line); border-radius:16px;
  background:rgba(6,10,28,.55); backdrop-filter:blur(8px); }}
.td-login-feats b {{ display:block; color:var(--ink); font-family:'Exo 2'; font-size:16px; }}
.td-login-feats span {{ color:var(--muted); font-size:12px; }}
.td-login-ph {{ display:inline-block; margin-top:18px; font-family:'JetBrains Mono'; font-size:11px; letter-spacing:.12em;
  color:var(--warn); border:1px solid rgba(245,196,81,.4); border-radius:999px; padding:5px 12px; background:rgba(245,196,81,.06); }}

/* Giriş sonrası üst çubuk */
.td-topbar {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding:12px 18px; border:1px solid var(--line);
  border-radius:18px; background:rgba(8,13,32,.75); }}
.td-topbar .brand {{ font-family:'Exo 2'; font-weight:800; letter-spacing:.18em; font-size:14px; color:var(--ink);
  margin-right:6px; }}
.td-topbar .who {{ margin-left:auto; color:#c6d2ee; }}
.td-topbar .who .meta {{ color:var(--muted); font-size:13px; margin-left:8px; }}
.td-li {{ padding-left:18px; position:relative; margin:6px 0; }}
.td-li::before {{ content:'•'; position:absolute; left:2px; color:var(--ember); }}
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
