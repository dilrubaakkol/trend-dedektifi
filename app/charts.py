"""Arayüz grafikleri (plotly). Sayılar analiz paketinden gelir; sentetik olanlar açıkça işaretlenir.

Renk kuralı (dataviz): artış/azalış ayrışan ölçek (kırmızı ↔ mavi, ortası gri); anlamsız sonuç gri;
durumlar (beklenen yönde / ters yönde) yalnız lejant metniyle birlikte. Metin her zaman metin renginde.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy import stats

from formatting import fmt
from theme import BG, DOWN, EMPTY, GOOD, INK, INK_2, LINE, LINE_2, MUTED, NEUTRAL, SERIOUS, SURFACE_2, UP

FONT = dict(family="Inter, system-ui, sans-serif", color=INK_2, size=13)
MONO = "IBM Plex Mono, monospace"
GRID = "#152035"
CLEAR = "rgba(0,0,0,0)"   # zemin panelden gelir (koyu cam)

# Ayrışan ölçek: mavi kutup → gri orta → kırmızı kutup (eşit adım).
TREND_SCALE = [[0.0, DOWN], [0.25, "#2f5a8f"], [0.5, NEUTRAL], [0.75, "#8f3a35"], [1.0, UP]]
GREY = NEUTRAL
BORDER = BG          # il sınırı: zemin rengi (yüzey boşluğu etkisi)


def _base(fig: go.Figure, height: int = 420) -> go.Figure:
    """Tüm grafikler için ortak açık tema."""
    fig.update_layout(
        height=height, font=FONT, paper_bgcolor=CLEAR, plot_bgcolor=CLEAR,
        separators=",.",  # Türkçe: ondalık virgül, binlik nokta
        margin=dict(l=60, r=24, t=24, b=50),
        hoverlabel=dict(bgcolor=SURFACE_2, bordercolor=LINE_2, font=dict(family=FONT["family"], color=INK, size=13)),
        legend=dict(orientation="h", y=-0.18, x=0, font=dict(color=INK_2)),
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=LINE, tickfont=dict(color=MUTED), title_font=dict(color=INK_2))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=LINE, tickfont=dict(color=MUTED), title_font=dict(color=INK_2))
    return fig


def noise_experiment(n_series: int = 20, years: int = 25, seed: int | None = None, alpha: float = 0.05):
    """Tesadüf deneyi: trendsiz beyaz gürültüden `n_series` seri üretir ve sıradan t-testiyle sınar.

    Bu gerçek bir hesaptır (yer tutucu değil): trend olmadığı halde yaklaşık %5'i "anlamlı" görünür.
    Dönüş: (figür, anlamlı görünen seri sayısı).
    """
    rng = np.random.default_rng(seed)
    x = np.arange(years)
    fig = go.Figure()
    hits = 0
    for i in range(n_series):
        y = rng.normal(0, 1, years)
        res = stats.linregress(x, y)
        significant = res.pvalue < alpha
        hits += int(significant)
        offset = i * 3.2
        fig.add_trace(go.Scatter(
            x=x + 2001, y=y + offset, mode="lines", showlegend=False,
            line=dict(color=UP if significant else "#3a4865", width=2 if significant else 1.2),
            hovertemplate=f"Seri {i + 1} · p = {fmt(res.pvalue, digits=3)}<extra></extra>",
        ))
        if significant:
            fig.add_trace(go.Scatter(
                x=x + 2001, y=res.intercept + res.slope * x + offset, mode="lines", showlegend=False,
                line=dict(color=UP, width=1.5, dash="dot"), hoverinfo="skip",
            ))
    _base(fig, 500)
    fig.update_yaxes(showticklabels=False, showgrid=False, title="20 rastgele seri (hiçbirinde trend yok)")
    fig.update_xaxes(title="Yıl", showgrid=False)
    return fig, hits


# ------------------------------------------------------------------ haritalar
def _geo(fig: go.Figure, height: int = 520) -> go.Figure:
    """İl haritaları için ortak coğrafya ayarı (taban harita yok, yalnız il sınırları)."""
    _base(fig, height)
    fig.update_geos(visible=False, bgcolor=CLEAR, projection_type="mercator",
                    lonaxis_range=[25.6, 44.9], lataxis_range=[35.7, 42.3], center=dict(lon=35.25, lat=39.0))
    fig.update_layout(margin=dict(l=0, r=0, t=6, b=0), geo=dict(bgcolor=CLEAR))
    return fig


def province_trend_map(df, geojson: dict, units: str, highlight: str | None = None,
                       confidence: dict | None = None) -> go.Figure:
    """İl trend haritası: anlamlı iller ayrışan ölçekte, anlamsızlar gri, hesaplanamayanlar açık gri.

    `df`: il, plaka, egim_10yil, ci_alt, ci_ust, p_mk, anlamli_fdr (+ isteğe bağlı anlamli) sütunları.
    `confidence`: {plaka: güven seviyesi} (bulgu karnesi); varsa üzerine gelince gösterilir.
    """
    confidence = confidence or {}
    fig = go.Figure()

    def hover(r) -> str:
        if pd.isna(r.egim_10yil):
            return f"<b>{r.il}</b><br>hesaplanamadı"
        state = "anlamlı (FDR sonrası)" if r.anlamli_fdr else "anlamlı değil"
        g = confidence.get(int(r.plaka))
        return (f"<b>{r.il}</b><br>{fmt(r.egim_10yil, digits=2)} {units}<br>"
                f"%95 aralık: {fmt(r.ci_alt, digits=2)} … {fmt(r.ci_ust, digits=2)}<br>"
                f"p = {fmt(r.p_mk, digits=3)} · {state}" + (f"<br>güven: {g}" if g else ""))

    texts = [hover(r) for r in df.itertuples()]
    fig.add_trace(go.Choropleth(
        geojson=geojson, featureidkey="properties.plaka", locations=df["plaka"],
        z=[0 if pd.notna(v) else 1 for v in df["egim_10yil"]], zmin=0, zmax=1,
        colorscale=[[0, GREY], [1, EMPTY]], showscale=False, text=texts, hovertemplate="%{text}<extra></extra>",
        marker=dict(line=dict(color=BORDER, width=1)),
    ))
    mask = (df["anlamli_fdr"] == 1).to_numpy()
    sig = df[mask]
    if len(sig):
        lim = float(np.nanpercentile(np.abs(sig["egim_10yil"]), 95)) or 1.0
        fig.add_trace(go.Choropleth(
            geojson=geojson, featureidkey="properties.plaka", locations=sig["plaka"], z=sig["egim_10yil"],
            zmin=-lim, zmax=lim, colorscale=TREND_SCALE,
            text=[t for t, m in zip(texts, mask) if m], hovertemplate="%{text}<extra></extra>",
            marker=dict(line=dict(color=BORDER, width=1)),
            colorbar=dict(title=dict(text=units, font=dict(color=INK_2, size=12), side="right"),
                          tickfont=dict(color=MUTED, family=MONO, size=11), outlinewidth=0, thickness=10, len=0.6,
                          x=0.99, separatethousands=False),
        ))
    if highlight is not None:
        h = df[df["il"] == highlight]
        fig.add_trace(go.Choropleth(
            geojson=geojson, featureidkey="properties.plaka", locations=h["plaka"], z=[1] * len(h),
            colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False, hoverinfo="skip",
            marker=dict(line=dict(color=INK, width=2.2)),
        ))
    return _geo(fig)


RELATION_COLORS = {"beklenen_yonde": GOOD, "ters_yonde": SERIOUS, "anlamsiz": GREY, "": EMPTY}


def relation_map(df, geojson: dict, region_of: dict | None = None, confidence: dict | None = None) -> go.Figure:
    """Fizik kontrolü haritası: beklenen yönde yeşil, ters yönde turuncu, anlamsız gri, hesaplanamadı açık.

    `df`: ciftler.csv satırları. İl düzeyinde `plaka` sütunu gerekir. Bölge düzeyinde `region_of`
    ({plaka: bölge_kodu}) verilir; her il, bağlı olduğu bölgenin etiketiyle boyanır.
    `confidence`: {bolge_kodu: güven seviyesi} (bulgu karnesi).
    """
    confidence = confidence or {}
    if region_of is not None:  # bölge satırlarını illere yay
        by_code = {str(r["bolge_kodu"]): r for r in df.to_dict("records")}
        rows = [(plaka, by_code[code]) for plaka, code in region_of.items() if code in by_code]
    else:
        rows = [(int(r["plaka"]), r) for r in df.to_dict("records") if pd.notna(r["plaka"])]
    names = {"beklenen_yonde": "beklenen yönde", "ters_yonde": "ters yönde", "anlamsiz": "net ilişki yok"}
    fig = go.Figure()
    for lab, color in RELATION_COLORS.items():
        sel = [(pl, r) for pl, r in rows if (r["etiket"] or "") == lab]
        if not sel:
            continue
        text = []
        for _, r in sel:
            g = confidence.get(str(r["bolge_kodu"]))
            if pd.isna(r["r"]):
                text.append(f"<b>{r['bolge_adi']}</b><br>{r['not'] or 'hesaplanamadı'}")
            else:
                text.append(f"<b>{r['bolge_adi']}</b><br>{names.get(lab, '')}<br>r = {fmt(r['r'], digits=2)} · "
                            f"p = {fmt(r['p'], digits=3)}<br>etkin n = {fmt(r['etkin_n'])}"
                            + (f"<br>güven: {g}" if g else ""))
        fig.add_trace(go.Choropleth(
            geojson=geojson, featureidkey="properties.plaka", locations=[pl for pl, _ in sel], z=[1] * len(sel),
            colorscale=[[0, color], [1, color]], showscale=False, text=text,
            hovertemplate="%{text}<extra></extra>", marker=dict(line=dict(color=BORDER, width=1)),
        ))
    return _geo(fig, 480)


def value_map(df, geojson: dict, value_col: str, title: str, hover_cols: list[tuple[str, str]] | None = None,
              symmetric: bool = True) -> go.Figure:
    """Tek bir sayısal sütunun il haritası (ilişki laboratuvarı: r). Boş değerler açık gri."""
    hover_cols = hover_cols or []
    fig = go.Figure()
    texts = []
    for r in df.to_dict("records"):
        extra = "".join(f"<br>{lab}: {fmt(r[c], digits=2) if isinstance(r[c], float) else r[c]}"
                        for c, lab in hover_cols if c in r and pd.notna(r[c]) and r[c] != "")
        texts.append(f"<b>{r['bolge_adi']}</b><br>{title}: {fmt(r[value_col], digits=2)}{extra}")
    ok = df[value_col].notna().to_numpy()
    fig.add_trace(go.Choropleth(
        geojson=geojson, featureidkey="properties.plaka", locations=df["plaka"], z=[1] * len(df),
        colorscale=[[0, EMPTY], [1, EMPTY]], showscale=False, text=texts, hovertemplate="%{text}<extra></extra>",
        marker=dict(line=dict(color=BORDER, width=1))))
    if ok.any():
        lim = 1.0 if symmetric else float(np.nanmax(np.abs(df[value_col])))
        fig.add_trace(go.Choropleth(
            geojson=geojson, featureidkey="properties.plaka", locations=df.loc[ok, "plaka"], z=df.loc[ok, value_col],
            zmin=-lim, zmax=lim, colorscale=TREND_SCALE, text=[t for t, m in zip(texts, ok) if m],
            hovertemplate="%{text}<extra></extra>", marker=dict(line=dict(color=BORDER, width=1)),
            colorbar=dict(title=dict(text=title, font=dict(color=INK_2, size=12), side="right"),
                          tickfont=dict(color=MUTED, family=MONO, size=11), outlinewidth=0, thickness=10, len=0.6)))
    return _geo(fig, 480)


# ------------------------------------------------------------------ aralık grafikleri
def source_comparison(rows, units: str) -> go.Figure:
    """Aynı değişkenin farklı NASA ürünlerinden trendleri: nokta = Sen eğimi, çizgi = %95 aralık."""
    fig = go.Figure()
    for r in rows.itertuples():
        fig.add_trace(go.Scatter(
            x=[r.ci_alt, r.ci_ust], y=[r.urun, r.urun], mode="lines", line=dict(color=LINE_2, width=6),
            hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(
            x=[r.egim_10yil], y=[r.urun], mode="markers", showlegend=False,
            marker=dict(size=11, color=INK, line=dict(color=BG, width=2)),
            hovertemplate=(f"{r.urun}<br>{fmt(r.egim_10yil, digits=2)} {units}<br>"
                           f"%95: {fmt(r.ci_alt, digits=2)} … {fmt(r.ci_ust, digits=2)}<br>"
                           f"p = {fmt(r.p_mk, digits=3)}<extra></extra>")))
    fig.add_vline(x=0, line=dict(color=MUTED, width=1, dash="dot"))
    _base(fig, 110 + 56 * len(rows))
    fig.update_xaxes(title=f"Trend ({units})")
    fig.update_yaxes(showgrid=False, autorange="reversed")
    fig.update_layout(margin=dict(l=110, r=24, t=16, b=52))
    return fig


def magnitude_chart(df: pd.DataFrame, units: str, label_col: str = "bolge_adi") -> go.Figure:
    """Büyüklük testi: her bölge için gözlenen değer (nokta) ve %95 GA (çizgi); gri bant = fiziğin beklediği aralık.

    `df` sütunları: gozlenen, ga_alt, ga_ust, beklenen_alt, beklenen_ust, beklenen, etiket, guven ve `label_col`.
    Türkiye satırı en üstte, koyu yazılır.
    """
    d = df.copy()
    d["_tr"] = d[label_col].eq("Türkiye")
    d = d.sort_values(["_tr", label_col], ascending=[False, True]).reset_index(drop=True)
    labels = [f"<b>{v}</b>" if t else v for v, t in zip(d[label_col], d["_tr"])]
    fig = go.Figure()
    lo, hi = d["beklenen_alt"].dropna(), d["beklenen_ust"].dropna()
    # Bant: bütün satırlarda aynıysa tek dikdörtgen, değilse satır satır.
    if len(lo) and lo.nunique() == 1 and hi.nunique() == 1:
        fig.add_vrect(x0=float(lo.iloc[0]), x1=float(hi.iloc[0]), fillcolor="#1a2742", line_width=0, layer="below")
        if d["beklenen"].notna().any():
            fig.add_vline(x=float(d["beklenen"].dropna().iloc[0]), line=dict(color=LINE_2, width=1, dash="dot"))
    else:
        for i, r in d.iterrows():
            if pd.notna(r["beklenen_alt"]) and pd.notna(r["beklenen_ust"]):
                fig.add_shape(type="rect", x0=r["beklenen_alt"], x1=r["beklenen_ust"], y0=i - 0.32, y1=i + 0.32,
                              fillcolor="#1a2742", line_width=0, layer="below")
    colors = {"beklenen büyüklükle tutarlı": GOOD, "beklenenden küçük": SERIOUS, "beklenenden büyük": SERIOUS}
    for i, r in d.iterrows():
        c = colors.get(r["etiket"], MUTED)
        if pd.notna(r["ga_alt"]) and pd.notna(r["ga_ust"]):
            fig.add_trace(go.Scatter(x=[r["ga_alt"], r["ga_ust"]], y=[i, i], mode="lines",
                                     line=dict(color=c, width=2), hoverinfo="skip", showlegend=False))
        if pd.notna(r["gozlenen"]):
            fig.add_trace(go.Scatter(
                x=[r["gozlenen"]], y=[i], mode="markers", showlegend=False,
                marker=dict(size=10, color=c, line=dict(color=BG, width=2)),
                hovertemplate=(f"<b>{r[label_col]}</b><br>gözlenen {fmt(r['gozlenen'], digits=2)} {units}<br>"
                               f"%95: {fmt(r['ga_alt'], digits=2)} … {fmt(r['ga_ust'], digits=2)}<br>"
                               f"beklenen: {fmt(r['beklenen_alt'], digits=2)} … {fmt(r['beklenen_ust'], digits=2)}<br>"
                               f"{r['etiket']} · güven {r.get('guven') or '—'}<extra></extra>")))
    _base(fig, 90 + 40 * len(d))
    fig.update_yaxes(tickvals=list(range(len(d))), ticktext=labels, autorange="reversed", showgrid=False,
                     tickfont=dict(color=INK_2, size=12.5))
    fig.update_xaxes(title=units, zeroline=True, zerolinecolor=LINE_2)
    fig.update_layout(margin=dict(l=170, r=24, t=12, b=52))
    return fig
