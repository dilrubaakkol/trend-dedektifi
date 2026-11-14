"""Arayüz grafikleri (plotly). Sayılar ya results.json'dan gelir ya da açıkça "sentetik" diye işaretlenir."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy import stats

from formatting import fmt
from theme import EMBER, ICE, INK, LINE, MUTED, OK, WARN

FONT = dict(family="Inter, system-ui, sans-serif", color=INK, size=13)
MONO = "JetBrains Mono, monospace"

# Kar azalımı turuncu, artışı buz mavisi; sıfır koyu lacivert.
DIVERGING = [[0.0, "#ff7a2f"], [0.25, "#b8461f"], [0.5, "#0b1430"], [0.75, "#2a6fb0"], [1.0, "#7fd6ff"]]


def _base(fig: go.Figure, height: int = 420) -> go.Figure:
    """Tüm grafikler için ortak koyu tema."""
    fig.update_layout(
        height=height, font=FONT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        separators=",.",  # Türkçe: ondalık virgül, binlik nokta
        margin=dict(l=60, r=24, t=30, b=50),
        hoverlabel=dict(bgcolor="#0e1733", bordercolor=LINE, font=dict(family=MONO, color=INK)),
        legend=dict(orientation="h", y=-0.18, x=0, font=dict(color=MUTED)),
    )
    fig.update_xaxes(gridcolor="rgba(140,170,230,0.08)", zeroline=False, linecolor=LINE, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor="rgba(140,170,230,0.08)", zeroline=False, linecolor=LINE, tickfont=dict(color=MUTED))
    return fig


def synthetic_trend_map(bbox: tuple[float, float, float, float], seed: int = 7) -> go.Figure:
    """SENTETİK YER TUTUCU trend haritası.

    Gerçek harita Kişi 2'nin piksel bazlı Sen eğimi + FDR çıktısından gelecek. Bu fonksiyon yalnızca
    ekran akışını göstermek için yüksek yerlerde daha güçlü azalım içeren yapay bir alan üretir.
    """
    w, s, e, n = bbox
    lons = np.arange(w + 0.125, e, 0.25)
    lats = np.arange(s + 0.125, n, 0.25)
    lon2, lat2 = np.meshgrid(lons, lats)
    rng = np.random.default_rng(seed)
    # Yapay "yükseklik" alanı: birkaç dağ tepesi (konumlar yalnızca görsel amaçlıdır).
    peaks = [(39.70, 44.30, 0.55), (39.85, 41.30, 0.60), (38.92, 42.82, 0.45), (40.6, 42.4, 0.7), (38.5, 43.6, 0.6)]
    relief = sum(np.exp(-(((lat2 - a) / sd) ** 2 + ((lon2 - b) / sd) ** 2)) for a, b, sd in peaks)
    slope = -0.3 - 3.2 * relief + rng.normal(0, 0.55, lat2.shape)
    sig = np.abs(slope) > 1.4

    fig = go.Figure()
    fig.add_trace(go.Heatmap(
        x=lons, y=lats, z=slope, colorscale=DIVERGING, zmid=0, zmin=-4, zmax=4,
        colorbar=dict(title=dict(text="örnek eğim", font=dict(color=MUTED, size=12)), tickfont=dict(color=MUTED),
                      outlinewidth=0, thickness=12, len=0.85),
        hovertemplate="%{y:.2f}°K %{x:.2f}°D<br>SENTETİK: %{z:.1f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=lon2[sig], y=lat2[sig], mode="markers", name="FDR'yi geçen piksel (örnek)",
        marker=dict(size=3.5, color="rgba(234,240,255,0.85)"), hoverinfo="skip",
    ))
    fig.add_annotation(
        text="SENTETİK YER TUTUCU · gerçek veri değil", x=0.01, y=0.98, xref="paper", yref="paper",
        showarrow=False, xanchor="left", font=dict(family=MONO, size=11, color="#1a1405"),
        bgcolor=WARN, borderpad=4,
    )
    _base(fig, 460)
    fig.update_xaxes(title="Boylam (°D)", constrain="domain")
    fig.update_yaxes(title="Enlem (°K)")
    return fig


def interval_chart(observed: list[float], predicted: list[float], units: str = "m/10 yıl") -> go.Figure:
    """Gözlenen kayma aralığı ile fiziksel tahmin aralığını yan yana çizer; örtüşen kısmı vurgular."""
    rows = [("Fiziksel tahmin", predicted, ICE), ("Gözlenen kayma", observed, EMBER)]
    fig = go.Figure()
    lo_ov, hi_ov = max(observed[0], predicted[0]), min(observed[1], predicted[1])
    if lo_ov < hi_ov:
        fig.add_vrect(x0=lo_ov, x1=hi_ov, fillcolor="rgba(61,220,151,0.10)", line_width=0,
                      annotation_text="örtüşme", annotation_position="top left",
                      annotation_font=dict(color=OK, family=MONO, size=11))
    for name, (lo, hi), color in rows:
        fig.add_trace(go.Scatter(
            x=[lo, hi], y=[name, name], mode="lines+markers", name=name,
            line=dict(color=color, width=14), marker=dict(size=18, color=color, line=dict(color="#03050f", width=3)),
            hovertemplate=f"{name}: {fmt(lo, digits=0)} … {fmt(hi, digits=0)} {units}<extra></extra>",
        ))
        fig.add_annotation(x=hi, y=name, text=f"{fmt(lo, digits=0)} … {fmt(hi, digits=0)}", showarrow=False,
                           xanchor="left", xshift=16, font=dict(family=MONO, color=color, size=13))
    _base(fig, 260)
    span = max(observed[1], predicted[1]) - min(observed[0], predicted[0])
    fig.update_xaxes(title=f"Kar çizgisinin yükselme hızı ({units})",
                     range=[min(observed[0], predicted[0]) - 0.15 * span, max(observed[1], predicted[1]) + 0.35 * span])
    fig.update_yaxes(showgrid=False)
    fig.update_layout(showlegend=False, margin=dict(l=130, r=24, t=48, b=56))
    return fig


def noise_experiment(n_series: int = 20, years: int = 25, seed: int | None = None, alpha: float = 0.05):
    """Keşif modu deneyi: trendsiz beyaz gürültüden `n_series` seri üretir ve sıradan t-testiyle sınar.

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
            line=dict(color=EMBER if significant else "rgba(140,170,230,0.45)", width=2.4 if significant else 1.2),
            hovertemplate=f"Seri {i + 1} · p = {fmt(res.pvalue, digits=3)}<extra></extra>",
        ))
        if significant:
            fig.add_trace(go.Scatter(
                x=x + 2001, y=res.intercept + res.slope * x + offset, mode="lines", showlegend=False,
                line=dict(color=EMBER, width=1.5, dash="dot"), hoverinfo="skip",
            ))
    _base(fig, 520)
    fig.update_yaxes(showticklabels=False, showgrid=False, title="20 rastgele seri (trendsiz)")
    fig.update_xaxes(title="Yıl")
    return fig, hits


# ------------------------------------------------------------------ veri seti sayfaları
# Belgedeki kural: anlamlı artış kırmızı, anlamlı azalış mavi, anlamsız gri.
TREND_SCALE = [[0.0, "#1f6fe0"], [0.3, "#5cc8ff"], [0.5, "#e6ecff"], [0.7, "#ff9a7a"], [1.0, "#e8364b"]]
GREY = "#2b3552"


def _geo(fig: go.Figure, height: int = 520) -> go.Figure:
    """İl haritaları için ortak coğrafya ayarı (taban harita yok, yalnız il sınırları)."""
    _base(fig, height)
    # Yayın kutusu (25,5–45,0 D, 35,5–42,5 K); fitbounds bu boyda haritayı küçük bırakıyor.
    fig.update_geos(visible=False, bgcolor="rgba(0,0,0,0)", projection_type="mercator",
                    lonaxis_range=[25.6, 44.9], lataxis_range=[35.7, 42.3], center=dict(lon=35.25, lat=39.0))
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), geo=dict(bgcolor="rgba(0,0,0,0)"))
    return fig


def province_trend_map(df, geojson: dict, units: str, highlight: str | None = None) -> go.Figure:
    """İl trend haritası. `df`: il, plaka, egim_10yil, ci_alt, ci_ust, p_mk, anlamli_fdr sütunları."""
    fig = go.Figure()
    hover = [f"<b>{r.il}</b><br>{fmt(r.egim_10yil, digits=2)} {units}<br>"
             f"%95: {fmt(r.ci_alt, digits=2)} … {fmt(r.ci_ust, digits=2)}<br>"
             f"p = {fmt(r.p_mk, digits=3)} · {'FDR sonrası anlamlı' if r.anlamli_fdr else 'anlamlı değil'}"
             for r in df.itertuples()]
    fig.add_trace(go.Choropleth(
        geojson=geojson, featureidkey="properties.plaka", locations=df["plaka"], z=[0] * len(df),
        colorscale=[[0, GREY], [1, GREY]], showscale=False, text=hover, hovertemplate="%{text}<extra></extra>",
        marker=dict(line=dict(color="rgba(3,5,15,.9)", width=0.6)),
    ))
    sig = df[df["anlamli_fdr"] == 1]
    if len(sig):
        lim = float(np.nanpercentile(np.abs(sig["egim_10yil"]), 95)) or 1.0
        fig.add_trace(go.Choropleth(
            geojson=geojson, featureidkey="properties.plaka", locations=sig["plaka"], z=sig["egim_10yil"],
            zmin=-lim, zmax=lim, colorscale=TREND_SCALE,
            text=[h for h, s in zip(hover, df["anlamli_fdr"]) if s == 1], hovertemplate="%{text}<extra></extra>",
            marker=dict(line=dict(color="rgba(3,5,15,.9)", width=0.6)),
            colorbar=dict(title=dict(text=units, font=dict(color=MUTED, size=12)), tickfont=dict(color=MUTED),
                          outlinewidth=0, thickness=12, len=0.7, x=1.0),
        ))
    if highlight is not None:
        h = df[df["il"] == highlight]
        fig.add_trace(go.Choropleth(
            geojson=geojson, featureidkey="properties.plaka", locations=h["plaka"], z=[1] * len(h),
            colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False, hoverinfo="skip",
            marker=dict(line=dict(color=EMBER, width=2.6)),
        ))
    return _geo(fig)


def relation_map(df, geojson: dict, region_of: dict | None = None) -> go.Figure:
    """Fizik kontrolü haritası: beklenen yönde yeşil, ters yönde turuncu, anlamsız gri, hesaplanamadı koyu.

    `df`: ciftler.csv satırları. İl düzeyinde `plaka` sütunu gerekir. Bölge düzeyinde `region_of`
    ({plaka: bölge_kodu}) verilir; her il, bağlı olduğu bölgenin etiketiyle boyanır.
    """
    colors = {"beklenen_yonde": OK, "ters_yonde": EMBER, "anlamsiz": GREY, "": "#141b33"}
    if region_of is not None:  # bölge satırlarını illere yay
        by_code = {str(r["bolge_kodu"]): r for r in df.to_dict("records")}
        rows = [(plaka, by_code[code]) for plaka, code in region_of.items() if code in by_code]
    else:
        rows = [(int(r["plaka"]), r) for r in df.to_dict("records") if pd.notna(r["plaka"])]
    fig = go.Figure()
    for lab, color in colors.items():
        sel = [(pl, r) for pl, r in rows if (r["etiket"] or "") == lab]
        if not sel:
            continue
        text = []
        for _, r in sel:
            if pd.isna(r["r"]):
                text.append(f"<b>{r['bolge_adi']}</b><br>{r['not'] or 'hesaplanamadı'}")
            else:
                text.append(f"<b>{r['bolge_adi']}</b><br>r = {fmt(r['r'], digits=2)} · p = {fmt(r['p'], digits=3)}"
                            f"<br>etkin n = {fmt(r['etkin_n'])}")
        fig.add_trace(go.Choropleth(
            geojson=geojson, featureidkey="properties.plaka", locations=[pl for pl, _ in sel], z=[1] * len(sel),
            colorscale=[[0, color], [1, color]], showscale=False, text=text,
            hovertemplate="%{text}<extra></extra>", marker=dict(line=dict(color="rgba(3,5,15,.9)", width=0.6)),
        ))
    return _geo(fig, 480)


def source_comparison(rows, units: str) -> go.Figure:
    """Aynı değişkenin farklı NASA ürünlerinden trendleri: nokta = Sen eğimi, çizgi = %95 aralık."""
    fig = go.Figure()
    palette = [EMBER, ICE, OK, WARN]
    for i, r in enumerate(rows.itertuples()):
        c = palette[i % len(palette)]
        fig.add_trace(go.Scatter(
            x=[r.ci_alt, r.ci_ust], y=[r.urun, r.urun], mode="lines", line=dict(color=c, width=10),
            opacity=0.45, hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(
            x=[r.egim_10yil], y=[r.urun], mode="markers", showlegend=False,
            marker=dict(size=16, color=c, line=dict(color="#03050f", width=3)),
            hovertemplate=(f"{r.urun}<br>{fmt(r.egim_10yil, digits=2)} {units}<br>"
                           f"%95: {fmt(r.ci_alt, digits=2)} … {fmt(r.ci_ust, digits=2)}<br>"
                           f"p = {fmt(r.p_mk, digits=3)}<extra></extra>")))
    fig.add_vline(x=0, line=dict(color=MUTED, width=1, dash="dot"))
    _base(fig, 120 + 70 * len(rows))
    fig.update_xaxes(title=f"Trend ({units})")
    fig.update_yaxes(showgrid=False, autorange="reversed")
    fig.update_layout(margin=dict(l=210, r=24, t=20, b=56))
    return fig
