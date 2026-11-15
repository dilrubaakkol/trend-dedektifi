"""Trend Dedektifi — Türkiye iklim trendi veri seti ve ilişki motorunun arayüzü (Kişi 5).

Çalıştırma (repo kökünden):  streamlit run app/streamlit_app.py

Sayfalar: Genel bakış · İl profili · İlişkiler · İlişki laboratuvarı · Büyüklük testleri · Soru sor ·
Veri indir · (Çalışmalarım) · Yöntem. Her sayfanın başında tek cümlelik bir sonuç, altında kanıtı vardır.
Site yeni istatistik üretmez: analiz paketini (L3_ozet, L4_iliski, karne, buyukluk) okur. İlişki
laboratuvarı ekibin genel ilişki motorunu (`physics.tek_cift.hesapla`) aynı yöntemle canlı çalıştırır.
Gerçek dosyalar yoksa sentetik yer tutucu tablolar gösterilir ve her yerde işaretlenir.
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
for p in (str(APP_DIR), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import auth  # noqa: E402
import eposta  # noqa: E402
import urun_io as U  # noqa: E402
import veritabani as DB  # noqa: E402
from charts import (magnitude_chart, noise_experiment, province_trend_map, relation_map,  # noqa: E402
                    source_comparison, value_map)
from formatting import fmt, fmt_p  # noqa: E402
from hero import build_config, render_hero  # noqa: E402
from theme import MARK_SVG, apply_streamlit_theme, inject_theme  # noqa: E402

apply_streamlit_theme()  # seçim kutuları, sekmeler: koyu tema (kök config dosyası gerekmez)
st.set_page_config(page_title="Trend Dedektifi", page_icon="🛰️", layout="wide", initial_sidebar_state="collapsed")
inject_theme()

# Değişkenlerin ekrandaki adları (sözleşmedeki kodlarla birebir).
VAR_NAMES = {
    "sicaklik_2m": "Hava sıcaklığı", "yagis": "Yağış", "kar_ortusu": "Kar örtüsü", "kar_su_esdegeri": "Kar suyu",
    "toprak_nemi": "Toprak nemi", "ndvi": "Bitki örtüsü (NDVI)", "toplam_su_depolama": "Toplam su depolama",
    "buharlasma": "Buharlaşma", "yuzey_sicakligi_gunduz": "Yüzey sıcaklığı (gündüz)",
    "yuzey_sicakligi_gece": "Yüzey sıcaklığı (gece)", "aerosol_optik_derinlik": "Aerosol optik derinliği",
    "bulut_orani": "Bulut oranı", "deniz_seviyesi_basinci": "Deniz seviyesi basıncı", "evi": "Bitki örtüsü (EVI)",
    "kok_bolgesi_nemi": "Kök bölgesi nemi", "no2": "Azot dioksit (NO₂)", "ozgul_nem_2m": "Özgül nem",
    "ozon_kolon": "Ozon kolonu", "ruzgar_hizi": "Rüzgâr hızı", "ruzgar_u_10m": "Rüzgâr (doğu–batı)",
    "ruzgar_v_10m": "Rüzgâr (kuzey–güney)", "su_buhari_kolon": "Su buharı kolonu", "taban_akisi": "Taban akışı",
    "yuzey_akisi": "Yüzey akışı", "rakim": "Rakım",
}
PAIR_QUESTIONS = {
    1: "Kış ısındıkça kar örtüsü azalıyor mu?",
    2: "Yağış arttığında toprak nemi artıyor mu?",
    3: "Toprak nemi arttığında bitki örtüsü artıyor mu?",
    4: "Yağış, toplam su depolamayı artırıyor mu?",
    5: "Yaz ısındıkça buharlaşma artıyor mu?",
    6: "İki farklı sıcaklık ölçümü aynı şeyi gösteriyor mu?",
}
SEASON_TXT = {"yillik": "", "kis": "kışın ", "ilkbahar": "ilkbaharda ", "yaz": "yazın ", "sonbahar": "sonbaharda "}
PLOT_CFG = {"displayModeBar": False}


# ---------------------------------------------------------------- yardımcılar
def vname(key: str) -> str:
    """Değişkenin ekrandaki adı."""
    return VAR_NAMES.get(key) or U.variable_cards().get(key, {}).get("baslik", key)


def unit_of(birim: str) -> str:
    """'mm/10 yil' ya da 'mm/yıl' → ekranda '… / 10 yıl' önüne yazılacak birim; birimsiz NDVI için boş metin."""
    u = str(birim if pd.notna(birim) else "").replace("/10 yil", "").replace(" / 10 yıl", "").strip()
    return "" if u in ("1", "", "-", "nan") else u


def num(v: float) -> str:
    """Eğim için okunur sayı (küçük değerlerde 3 basamak)."""
    return fmt(abs(v), digits=3 if abs(v) < 0.1 else (1 if abs(v) >= 10 else 2))


def low(text: str) -> str:
    """Cümle içi küçük harf: yalnız ilk harf (Türkçe İ/I kuralıyla); kısaltmalar (NO₂, NDVI) korunur."""
    if not text:
        return text
    first = {"İ": "i", "I": "ı"}.get(text[0], text[0].lower())
    return first + text[1:]


def loc(name: str) -> str:
    """Bulunma eki, Türkçe ünlü ve ünsüz uyumuyla: Erzurum'da, İzmir'de, Muş'ta, Tokat'ta, Kars'ta."""
    s = str(name)
    vowels = [c for c in s.lower() if c in "aıoueiöü"]
    back = not vowels or vowels[-1] in "aıou"
    hard = s[-1].lower() in "fstkçşhp"
    return f"{s}'{'t' if hard else 'd'}{'a' if back else 'e'}"


def esc(v) -> str:
    """HTML için güvenli metin."""
    return html.escape(str(v if v is not None and not (isinstance(v, float) and pd.isna(v)) else ""))


def dir_mark(v: float) -> str:
    """Yön işareti: artış kırmızı ▲, azalış mavi ▼ (renk metinde değil, işarette)."""
    if v is None or pd.isna(v) or v == 0:
        return '<span class="td-dir flat"></span>'
    return f'<span class="td-dir {"up" if v > 0 else "down"}"></span>'


def badge(text: str, cls: str = "info", title: str | None = None) -> str:
    """Durum rozeti (nokta + metin)."""
    t = f' title="{esc(title)}"' if title else ""
    return f'<span class="td-badge {cls}"{t}>{esc(text)}</span>'


def guven_badge(level: str | None, reason: str | None = None) -> str:
    """Bulgu karnesi güven rozeti."""
    if not level:
        return ""
    return badge(f"güven: {level.lower()}", U.GUVEN_CLASS.get(level, "info"), reason)


def git_commit() -> str | None:
    """Paket manifestosu için çalışan kodun commit kimliği."""
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=5).strip()
    except Exception:  # noqa: BLE001
        return None


@st.cache_resource(ttl=30, show_spinner=False)
def db_ok() -> bool:
    """MS SQL veri tabanı erişilebilir mi? (30 sn önbellek)"""
    return DB.available()


@st.cache_data(ttl=300, show_spinner="Veri hazırlanıyor…")
def get_tables(use_db: bool) -> dict:
    """Trend ve ilişki tabloları (5 dk önbellek).

    Sıra: gerçek analiz paketi (L3_ozet + L4_iliski) → veri tabanındaki gerçek tablolar → yer tutucu.
    """
    files = U.load_tables()
    if not files["yer_tutucu"]:
        return {**files, "kaynak_turu": "dosya"}
    if use_db:
        try:
            t = DB.load_tables()
            if t is not None and not t["yer_tutucu"]:
                return {**t, "yer_tutucu_tablolar": [], "kaynak_turu": "mssql"}
        except Exception:  # noqa: BLE001
            pass
    return {**files, "kaynak_turu": "dosya"}


@st.cache_data(ttl=300, show_spinner=False)
def get_karne() -> dict:
    """Bulgu karnesi tabloları (yoksa None)."""
    return U.load_karne()


@st.cache_data(ttl=300, show_spinner=False)
def get_magnitude() -> dict:
    """Büyüklük testi tabloları (yoksa None)."""
    return U.load_magnitude()


def main_product(var: str) -> str:
    """Kademe 1 tablosundaki ana NASA ürünü."""
    return next((prods[0] for v, prods, _ in U.TIER1 if v == var), "")


def seasons_for(df: pd.DataFrame, var: str) -> list[str]:
    """Bu değişken için tabloda bulunan mevsimler (belgedeki sırayla)."""
    have = set(df.loc[df["degisken"] == var, "mevsim"])
    return [s for s in U.SEASONS if s in have]


def verdict(row) -> tuple[str, str]:
    """Bir trend satırı için sade hüküm ve durum sınıfı: (metin, css sınıfı)."""
    if row.get("anlamli", 0) == -1 or pd.isna(row["egim_10yil"]):
        return "Hesaplanamadı", "info"
    if row["anlamli_fdr"] == 1 and not row["belirsiz"]:
        return "Anlamlı değişim", "ok"
    if row["belirsiz"]:
        return "Testler çelişiyor", "warn"
    return "Anlamlı değil", "info"


def flag_badges(row) -> str:
    """Satırın veri uyarısı rozetleri: trend_uyarisi, doğrulanmadı (Kademe 2), az hücre."""
    out = []
    warn = str(row.get("trend_uyarisi") or "")
    if warn:
        out.append(badge("veri uyarısı", "warn", warn))
    if str(row.get("dogrulanmadi") or "").lower() == "evet":
        out.append(badge("doğrulanmadı", "warn", "Kademe 2 ürün: bağımsız doğrulaması yapılmadı"))
    if "az hücre" in str(row.get("not") or ""):
        out.append(badge("az hücre", "info", str(row["not"])))
    return " ".join(out)


def warning_callout(df: pd.DataFrame) -> None:
    """Seçili tablodaki veri uyarılarını (trend_uyarisi, doğrulanmadı) açıkça gösterir."""
    warns = sorted({w for w in df.get("trend_uyarisi", pd.Series(dtype=str)) if w})
    unver = bool((df.get("dogrulanmadi", pd.Series(dtype=str)) == "evet").any())
    if not warns and not unver:
        return
    items = "".join(f'<div class="td-li">{esc(w)}</div>' for w in warns)
    if unver:
        items += '<div class="td-li">Bu ürün Kademe 2: sonuçlar bağımsız olarak doğrulanmadı.</div>'
    st.markdown(f'<div class="td-callout warn">{badge("veri uyarısı", "warn")} <b>Yorumlamadan önce:</b>{items}</div>',
                unsafe_allow_html=True)


def header(kicker: str, big: str, small: str = "", tag: str | None = None) -> None:
    """Sayfa başlığı: küçük üst satır, tek cümlelik sonuç, kısa açıklama."""
    t = f'<span class="pill">{esc(tag)}</span>' if tag else ""
    st.markdown(f'<div class="td-kicker" lang="tr">{kicker}{t}</div><div class="td-answer">{big}</div>'
                + (f'<div class="td-answer-sub">{small}</div>' if small else ""), unsafe_allow_html=True)


def answer(big: str, small: str = "") -> None:
    """Geriye dönük: başlıksız sonuç cümlesi."""
    header("", big, small)


def subhead(text: str, note: str = "") -> None:
    """Bölüm içi küçük başlık."""
    st.markdown(f'<div class="td-mini-h">{text}' + (f"<small>{note}</small>" if note else "") + "</div>",
                unsafe_allow_html=True)


def stats_strip(items: list[tuple[str, str]]) -> None:
    """Yan yana sayı kutuları: [(değer, açıklama)]."""
    st.markdown('<div class="td-stats" lang="tr">' + "".join(f"<div><b>{v}</b><span>{lab}</span></div>" for v, lab in items)
                + "</div>", unsafe_allow_html=True)


def html_table(df: pd.DataFrame, max_rows: int = 200) -> None:
    """Temaya uygun HTML tablo (Streamlit'in hazır tablosu temayla çakıştığı için)."""
    head = "".join(f"<th>{esc(c)}</th>" for c in df.columns)
    body = []
    for _, r in df.head(max_rows).iterrows():
        cells = []
        for v in r:
            if isinstance(v, float):
                v = "" if pd.isna(v) else f"{v:.4g}"
            cells.append(f'<td class="num">{esc(v)}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(f'<div class="td-table-wrap td-scroll"><table class="td-table td-dense"><thead><tr>{head}</tr></thead>'
                f'<tbody>{"".join(body)}</tbody></table></div>', unsafe_allow_html=True)


def karne_table(row, checks: list[tuple[str, str, str]]) -> None:
    """Bir sonucun bulgu karnesi: her kontrol için soru, durum ve sayı."""
    body = []
    for col, num_col, question in checks:
        state = str(row.get(col) or "uygulanamaz")
        detail = row.get(num_col)
        detail = "" if detail is None or (isinstance(detail, float) and pd.isna(detail)) else detail
        if col.startswith("b_") and isinstance(detail, float):
            detail = f"p_perm = {fmt(detail, digits=3)}"
        body.append(f"<tr><td>{esc(question)}</td><td>{badge(state, U.KARNE_STATES.get(state, 'info'))}</td>"
                    f'<td class="muted">{esc(detail)}</td></tr>')
    crit = str(row.get("f_kritik") or "")
    warns = str(row.get("f_uyarilar") or "")
    if warns:
        body.append(f"<tr><td>Bilinen veri uyarısı var mı?</td><td>{badge('evet', 'warn' if crit == 'evet' else 'info')}"
                    f'</td><td class="muted">{esc(warns)}</td></tr>')
    st.markdown('<div class="td-table-wrap"><table class="td-table"><thead><tr><th>Kontrol</th><th>Sonuç</th>'
                "<th>Ayrıntı</th></tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"
                f'<p class="td-note">Güven: <b>{esc(row.get("guven"))}</b> · {esc(row.get("gerekce"))} · '
                f'kural {esc(row.get("kural_surumu"))}</p>', unsafe_allow_html=True)


STAT_COLS = ["degisken", "urun", "mevsim", "donem", "n_yil", "n_hucre", "egim_10yil", "ci_alt", "ci_ust", "birim",
             "p_mk", "p_mk_kontrol", "p_ttest", "belirsiz", "anlamli_fdr", "yil_sayisi_gereken", "kaynak_uyumu"]
L3_STAT_COLS = ["degisken", "urun", "mevsim", "donem_baslangic", "donem_bitis", "hucre_sayisi", "sen_egimi", "ga_alt",
                "ga_ust", "egim_birimi", "p_mk", "p_fdr", "anlamli", "etkin_n", "gereken_yil", "anlamli_hucre_orani",
                "kaynak_uyumu", "trend_uyarisi", "dogrulanmadi", "not"]


def stats_table(df: pd.DataFrame, place_col: str) -> pd.DataFrame:
    """Araştırmacı tablosu: sütun adları indirilen CSV ile aynı (gerçek veride sözleşme 2.2)."""
    if "sen_egimi" in df.columns:
        return df[[c for c in ["bolge_kodu", "bolge_adi"] + L3_STAT_COLS if c in df.columns]]
    return df[[c for c in [place_col] + STAT_COLS if c in df.columns]]


# ---------------------------------------------------------------- durum
DB_OK = db_ok()
tables = get_tables(DB_OK)
placeholder = tables["yer_tutucu"]
user = st.session_state.get("user")
geojson = U.provinces_geojson()
academic = auth.is_academic(user)
PH = "YER_TUTUCU_" if placeholder else ""
KARNE = get_karne()


def footer() -> None:
    """Alt bilgi: kullanılan NASA ürünleri ve DOI'leri."""
    items = " · ".join(f'<a href="https://doi.org/{s["doi"]}" target="_blank">{s["short_name"]}</a>' if s["doi"]
                       else s["short_name"] for s in U.nasa_sources())
    st.markdown(f'<div class="td-foot"><b>Kullanılan NASA verileri:</b> {items}<br>'
                f"Trend Dedektifi {U.VERSION} · NASA Space Apps Challenge 2026 · veri {U.LICENSE}, kod MIT · "
                "Bu araç NASA tarafından yapılmamıştır; NASA'nın açık verilerini kullanır.</div>",
                unsafe_allow_html=True)


# ================================================================ Genel bakış
def pick_variable(df: pd.DataFrame, key: str) -> str:
    """Değişken seçimi."""
    variables = [v for v, *_ in U.TIER1 if v in set(df["degisken"])]
    return st.pills("Değişken", variables, default=variables[0], format_func=vname, key=key) or variables[0]


def pick_season(df: pd.DataFrame, var: str, key: str, default: str | None = None) -> str:
    """Mevsim seçimi."""
    seasons = seasons_for(df, var)
    d = default if default in seasons else seasons[0]
    return st.segmented_control("Mevsim", seasons, default=d, format_func=U.SEASONS.get, key=f"{key}_{var}") or d


def page_kesfet() -> None:
    """Türkiye haritası: tek cümlelik sonuç, karne özeti, harita ve en çok değişen iller."""
    il_df = tables["il"]
    var = pick_variable(il_df, "k_var")
    c1, c2 = st.columns([3, 2])
    with c1:
        season = pick_season(il_df, var, "k_season", "kis")
    prod = main_product(var)
    products = list(dict.fromkeys(il_df.loc[il_df["degisken"] == var, "urun"]))
    if len(products) > 1:
        with c2:
            prod = st.segmented_control("NASA ürünü", products, default=prod, key=f"k_prod_{var}") or prod
    df = il_df[(il_df["degisken"] == var) & (il_df["mevsim"] == season) & (il_df["urun"] == prod)]
    if df.empty:
        st.info("Bu seçim için veri yok.")
        return
    unit = unit_of(df["birim"].iloc[0])
    unit10 = f"{unit} / 10 yıl" if unit else "/ 10 yıl"
    tr = tables["bolge"]
    tr = tr[(tr["bolge"] == "turkiye") & (tr["degisken"] == var) & (tr["mevsim"] == season) & (tr["urun"] == prod)]
    sig = df[df["anlamli_fdr"] == 1]
    up, down = int((sig["egim_10yil"] > 0).sum()), int((sig["egim_10yil"] < 0).sum())
    kc = U.trend_confidence(KARNE["trend_il"], var, prod, season)
    kt = U.trend_confidence(KARNE["trend_bolge"], var, prod, season)
    conf = {int(k): v for k, v in kc["guven"].items() if str(k).isdigit()} if len(kc) else {}
    high = sum(1 for p in sig["plaka"] if conf.get(int(p)) == "YÜKSEK")

    name = vname(var)
    if len(tr):
        t = tr.iloc[0]
        tconf = kt.loc["turkiye", "guven"] if len(kt) and "turkiye" in kt.index else None
        if t.get("anlamli", 1) == 1:
            verb = "arttı" if t["egim_10yil"] > 0 else "azaldı"
            big = (f"Türkiye'de {SEASON_TXT[season]}{low(name)} her 10 yılda {dir_mark(t['egim_10yil'])}"
                   f'<span class="num">{num(t["egim_10yil"])}</span> {esc(unit)} {verb}.')
        else:
            big = (f"Türkiye'de {SEASON_TXT[season]}{low(name)} için ülke genelinde anlamlı bir değişim yok "
                   f'<span style="font-weight:400;color:var(--muted);font-size:.6em">(eğim '
                   f"{fmt(t['egim_10yil'], digits=2)} {esc(unit10)})</span>.")
    else:
        big, tconf = f"Türkiye'de {SEASON_TXT[season]}{low(name)}", None
    small = (f"81 ilin <b>{up}</b> tanesinde anlamlı artış, <b>{down}</b> tanesinde anlamlı azalış var; gri illerde "
             f"değişim tesadüften ayırt edilemiyor. Dönem {esc(str(df['donem'].iloc[0]).replace('-', '–'))}, "
             f"kaynak {esc(prod)}.")
    header(f"Genel bakış · {esc(name)} · {esc(U.SEASONS[season])}", big, small)
    if tconf:
        st.markdown(guven_badge(tconf, kt.loc["turkiye", "gerekce"]) + ' <span class="td-note">Türkiye satırının '
                    "bulgu karnesi</span>", unsafe_allow_html=True)
    warning_callout(pd.concat([df, tr]))

    items = [(f"{up + down}", "ilde anlamlı değişim"), (f"{up}", "ilde artış"), (f"{down}", "ilde azalış")]
    if conf:
        items.append((f"{high}", "tanesinde yüksek güven (karne)"))
    if len(tr) and tr.iloc[0].get("kaynak_uyumu"):
        items.append((esc(tr.iloc[0]["kaynak_uyumu"]), "NASA ürünü aynı yönde"))
    stats_strip(items)

    st.plotly_chart(province_trend_map(df, geojson, unit10, confidence=conf), width="stretch", config=PLOT_CFG)
    st.markdown(f'<div class="td-legend"><span>azalış<span class="bar"></span>artış</span>'
                '<span><i style="background:#2a3346"></i>anlamlı değil</span>'
                '<span><i style="background:#121927;border:1px solid #2c3d5c"></i>hesaplanamadı</span></div>',
                unsafe_allow_html=True)

    top = sig.reindex(sig["egim_10yil"].abs().sort_values(ascending=False).index).head(4)
    if len(top):
        subhead("En çok değişen iller", "anlamlı sonuçlar arasında")
        tiles = []
        for _, r in top.iterrows():
            g = conf.get(int(r["plaka"]))
            tiles.append(f'<div class="td-tile"><div class="t-name">{esc(r["il"])}</div>'
                         f'<div class="t-val">{dir_mark(r["egim_10yil"])}{num(r["egim_10yil"])}'
                         f"<small>{esc(unit10)}</small></div>"
                         f'<div class="t-badges">{guven_badge(g)} {flag_badges(r)}</div></div>')
        st.markdown(f'<div class="td-grid">{"".join(tiles)}</div>', unsafe_allow_html=True)

    with st.expander("Bütün iller · güven aralıkları ve p değerleri"):
        view = stats_table(df.sort_values("egim_10yil"), "il")
        if len(kc):
            view = view.assign(guven=[kc["guven"].get(f"{int(p):02d}", "") for p in df.sort_values("egim_10yil")["plaka"]])
        html_table(view)
        st.download_button("Bu tabloyu CSV olarak indir", view.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"{PH}trend_iller__{var}__{prod}__{season}.csv", mime="text/csv")
    rows = tables["bolge"]
    rows = rows[(rows["bolge"] == "turkiye") & (rows["degisken"] == var) & (rows["mevsim"] == season)]
    if len(rows) > 1:
        with st.expander(f"Kaynak karşılaştırması · {len(rows)} NASA ürünü aynı şeyi söylüyor mu?"):
            st.plotly_chart(source_comparison(rows, unit10), width="stretch", config=PLOT_CFG)
            st.caption("Nokta: Sen eğimi. Çizgi: otokorelasyona göre genişletilmiş %95 aralık. Ürünler ortak girdi "
                       "paylaşabildiği için bu bağımsız doğrulama değil, tutarlılık göstergesidir.")


# ================================================================ İl profili
def page_il() -> None:
    """Bir ilin bütün değişkenleri: her biri için eğim, hüküm ve güven; seçilen sonucun karnesi."""
    il_df = tables["il"]
    names = sorted(il_df["il"].unique(), key=U.norm_name)
    c1, c2 = st.columns([1, 2])
    il = c1.selectbox("İl", names, index=names.index("Erzurum") if "Erzurum" in names else 0, key="i_il")
    with c2:
        season = st.segmented_control("Mevsim", list(U.SEASONS), default="kis", format_func=U.SEASONS.get,
                                      key="i_season") or "kis"
    sub = il_df[il_df["il"] == il]
    main = sub[[u == main_product(v) for u, v in zip(sub["urun"], sub["degisken"])]]
    cur = main[main["mevsim"] == season]
    real = cur[(cur["anlamli_fdr"] == 1) & (cur["belirsiz"] == 0)]
    season_txt = "yıl boyunca" if season == "yillik" else f"{low(U.SEASONS[season])} mevsiminde"
    header(f"İl profili · {esc(il)}", f"{esc(loc(il))} {season_txt} {len(real)} değişkende anlamlı değişim var.",
           f"{len(cur)} değişkene bakıldı. Ötekilerde değişim, eldeki yaklaşık 25 yılla henüz tesadüften ayırt "
           "edilemiyor.")
    warning_callout(cur)

    tiles = []
    for _, r in cur.iterrows():
        unit = unit_of(r["birim"])
        lab, cls = verdict(r)
        kc = U.trend_confidence(KARNE["trend_il"], r["degisken"], r["urun"], season)
        code = str(r.get("bolge_kodu") or f"{int(r['plaka']):02d}")
        g = kc.loc[code, "guven"] if len(kc) and code in kc.index else None
        note = ""
        if lab == "Anlamlı değil" and pd.notna(r.get("yil_sayisi_gereken")):
            n = r["yil_sayisi_gereken"]
            note = (f'<div class="t-note">Bu büyüklükte bir trendi ayırt etmek için '
                    f'{"100 yıldan fazla" if n >= 100 else f"yaklaşık {int(n)} yıl daha"} veri gerekir.</div>')
        val = (f'{dir_mark(r["egim_10yil"])}{num(r["egim_10yil"])}<small>{esc(unit)} / 10 yıl</small>'
               if pd.notna(r["egim_10yil"]) else "—")
        tiles.append(f'<div class="td-tile {"dim" if cls != "ok" else ""}"><div class="t-name">{esc(vname(r["degisken"]))}'
                     f'</div><div class="t-sub">{esc(r["urun"])}</div><div class="t-val">{val}</div>'
                     f'<div class="t-badges">{badge(lab, cls)} {guven_badge(g) if cls == "ok" else ""} '
                     f"{flag_badges(r)}</div>{note}</div>")
    st.markdown(f'<div class="td-grid">{"".join(tiles)}</div>', unsafe_allow_html=True)

    if KARNE["trend_il"] is not None and len(cur):
        subhead("Bu sonuca neden güvenebiliriz?", "bulgu karnesi")
        opts = list(cur["degisken"])
        v = st.selectbox("Değişken", opts, format_func=vname, key="i_karne_var")
        r = cur[cur["degisken"] == v].iloc[0]
        kc = U.trend_confidence(KARNE["trend_il"], v, r["urun"], season)
        code = str(r.get("bolge_kodu") or f"{int(r['plaka']):02d}")
        if len(kc) and code in kc.index:
            karne_table(kc.loc[code], U.TREND_CHECKS)
        else:
            st.caption("Bu satır için karne yok.")

    if academic:
        with st.expander(f"Araştırmacı ayrıntısı · {il} için tüm satırlar"):
            html_table(stats_table(sub[sub["mevsim"] == season], "il"))
            st.download_button(f"{il} · tüm mevsimler (CSV)",
                               stats_table(sub, "il").to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"{PH}trend_iller__{U.norm_name(il)}.csv", mime="text/csv")


# ================================================================ İlişkiler (6 çift)
def page_iliski() -> None:
    """Fiziğin beklediği altı ilişki: harita, sayılar ve karne (ciftler.csv, sözleşme 2.3–2.4)."""
    rel = tables["iliski"]
    pairs = [p for p in U.PAIRS if p[0] in set(rel["cift_no"])]
    no = st.selectbox("İlişki", [p[0] for p in pairs], format_func=lambda n: PAIR_QUESTIONS.get(n, str(n)),
                      key="r_pair_sel") or pairs[0][0]
    meta = next(p for p in U.PAIRS if p[0] == no)
    lags = sorted(set(rel.loc[rel["cift_no"] == no, "gecikme_ay"]))
    lag = lags[0]
    if len(lags) > 1:
        lag = st.segmented_control("Gecikme", lags, default=lags[0], format_func=lambda x: f"{x} ay sonra",
                                   key=f"r_lag_{no}") or lags[0]
    d_all = rel[(rel["cift_no"] == no) & (rel["gecikme_ay"] == lag)]
    il_rows = U.pair_rows(d_all, "il")
    level = "il" if len(il_rows) else "bolge"
    d = il_rows if level == "il" else U.pair_rows(d_all, "bolge")
    unit, unit_gen = ("il", "ilin") if level == "il" else ("bölge", "bölgenin")
    done = d[d["etiket"] != ""]
    c = done["etiket"].value_counts()
    yes, rev, none = int(c.get("beklenen_yonde", 0)), int(c.get("ters_yonde", 0)), int(c.get("anlamsiz", 0))
    skipped = len(d) - len(done)
    kp = U.pair_confidence(KARNE["iliski"], no, lag)
    conf = {str(k): v for k, v in kp["guven"].items()} if len(kp) else {}
    header(f"İlişkiler · {esc(vname(meta[1]))} ve {esc(vname(meta[2]))}",
           f"Hesaplanabilen {len(done)} {unit_gen} {yes} tanesinde ilişki fiziğin beklediği yönde.",
           f"{rev} {unit}de ters yönde, {none} {unit}de net bir ilişki yok"
           + (f"; {skipped} {unit}de hesaplanamadı (ör. kar yok)" if skipped else "")
           + f". Beklenti: “{esc(meta[6])}”. Bu bir ilişkidir; neden-sonuç iddiası taşımaz.")
    items = [(str(yes), "beklenen yönde"), (str(rev), "ters yönde"), (str(none), "net ilişki yok")]
    if conf:
        items.append((str(sum(1 for k, v in conf.items() if v == "YÜKSEK" and k in set(d["bolge_kodu"]))),
                      "yüksek güvenli (karne)"))
    stats_strip(items)
    if level == "bolge":
        st.markdown('<div class="td-callout">Bu ilişki yalnız <b>7 bölge ve Türkiye</b> düzeyinde hesaplanır: GRACE '
                    "uydusunun çözünürlüğü yüzlerce kilometre, il için fazla kaba. Haritada her il, bağlı olduğu bölgenin "
                    "sonucuyla boyanmıştır.</div>", unsafe_allow_html=True)
        region_of = {int(r.plaka): r.bolge for r in U.provinces().itertuples()}
        st.plotly_chart(relation_map(d, geojson, region_of, conf), width="stretch", config=PLOT_CFG)
    else:
        st.plotly_chart(relation_map(d, geojson, confidence=conf), width="stretch", config=PLOT_CFG)
    st.markdown('<div class="td-legend"><span><i style="background:#2fb565"></i>beklenen yönde</span>'
                '<span><i style="background:#e07a3a"></i>ters yönde · incelenmeli</span>'
                '<span><i style="background:#2a3346"></i>net ilişki yok</span>'
                + ('<span><i style="background:#121927;border:1px solid #2c3d5c"></i>hesaplanamadı</span>' if skipped
                   else "") + "</div>", unsafe_allow_html=True)
    tr = U.pair_rows(d_all, "turkiye")
    if len(tr) and pd.notna(tr["r"].iloc[0]):
        t = tr.iloc[0]
        lab, cls = U.CONTROL_LABELS.get(t["etiket"], ("—", "info"))
        subhead(f"Türkiye geneli: r = {fmt(t['r'], digits=2)}")
        st.markdown(badge(lab, cls) + " " + guven_badge(conf.get("turkiye")), unsafe_allow_html=True)
        if len(kp) and "turkiye" in kp.index:
            with st.expander("Türkiye satırının bulgu karnesi"):
                karne_table(kp.loc["turkiye"], U.PAIR_CHECKS)
    rv = d[d["etiket"] == "ters_yonde"]
    if len(rv):
        notes = {x for x in rv["not"] if x}
        st.markdown('<div class="td-callout bad"><b>Ters yönde çıkan yerler:</b> '
                    + ", ".join(esc(x) for x in rv["bolge_adi"])
                    + ". Fiziğin beklediğinin tersi bir sonuç; iklim rejimine (ör. kurak bölgede buharlaşmayı suyun "
                      "sınırlaması), veri sorununa ya da sulama, baraj gibi insan etkisine işaret edebilir."
                    + (f"<br><span style='color:var(--muted)'>Not: {esc('; '.join(sorted(notes)))}</span>"
                       if notes else "") + "</div>", unsafe_allow_html=True)
    if academic:
        with st.expander("Araştırmacı ayrıntısı · ciftler.csv satırları (il, bölge, Türkiye)"):
            cols = ["bolge_turu", "bolge_kodu", "bolge_adi", "hucre_sayisi", "donem", "n", "r", "r1_1", "r1_2",
                    "etkin_n", "p", "p_fdr", "anlamli", "etiket", "not"]
            view = d_all[cols].sort_values(["bolge_turu", "r"])
            if conf:
                view = view.assign(guven=[conf.get(str(k), "") for k in view["bolge_kodu"]])
            html_table(view, max_rows=300)


# ================================================================ İlişki laboratuvarı (genel motor)
LAB_SEASONS = {"yillik": "Yıllık", "kis": "Kış", "ilkbahar": "İlkbahar", "yaz": "Yaz", "sonbahar": "Sonbahar",
               "mevsimlik": "Dört mevsim (anomali)", "aylik": "Aylık (anomali)"}
LAB_ADV = {"yillik": "yıllık ölçekte", "kis": "kışın", "ilkbahar": "ilkbaharda", "yaz": "yazın",
           "sonbahar": "sonbaharda", "mevsimlik": "mevsimden mevsime", "aylik": "aydan aya"}
LAB_EXPECT = {"": "Beklenti yok", "+": "Aynı yönde (+)", "-": "Ters yönde (−)"}
LAB_PRESETS = [
    ("Kış sıcaklığı ve kar · Erzurum", dict(x="sicaklik_2m", y="kar_ortusu", bolge="Erzurum", mevsim="kis", bek="-")),
    ("Kış sıcaklığı ve kar · 81 il", dict(x="sicaklik_2m", y="kar_ortusu", bolge="tum_iller", mevsim="kis", bek="-")),
    ("Yaz sıcaklığı ve buharlaşma · 81 il", dict(x="sicaklik_2m", y="buharlasma", bolge="tum_iller", mevsim="yaz",
                                                  bek="+")),
    ("NO₂ ve rüzgâr · Ankara", dict(x="no2", y="ruzgar_hizi", bolge="Ankara", mevsim="kis", bek="-")),
]


@st.cache_data(ttl=3600, show_spinner=False, max_entries=64)
def lab_options() -> tuple[dict, list[tuple[str, str]]]:
    """Paketteki L1 değişken/ürün seçenekleri ve bölge listesi [(girdi, ekran adı)]."""
    from physics.tek_cift import l1_secenekleri, paket_koku
    opts = l1_secenekleri(paket_koku())
    regions = [("turkiye", "Türkiye"), ("tum_iller", "81 il (harita)"), ("tum_bolgeler", "7 bölge ve Türkiye")]
    regions += [(k, v["ad"]) for k, v in U.regions_map().items()]
    regions += [(n, n) for n in sorted(U.provinces()["il"], key=U.norm_name)]
    return opts, regions


@st.cache_data(ttl=3600, show_spinner=False, max_entries=64)
def lab_run(x: str, ux: str | None, y: str, uy: str | None, bolge: str, mevsim: str, gecikme: int,
            bek: str, karne: bool) -> dict:
    """Genel ilişki motoru (physics.tek_cift.hesapla) + isteğe bağlı bulgu karnesi. Önbellek 1 saat."""
    from physics.tek_cift import hesapla, karne_ekle
    s = hesapla(x, y, bolge, mevsim, urun_x=ux, urun_y=uy, gecikme=gecikme, beklenen=bek or None)
    if karne:
        s = karne_ekle(s)
    return {"secim": s["secim"], "tablo": s["tablo"], "uyarilar": s["uyarilar"], "yaml_cifti": s["yaml_cifti"],
            "karne": s.get("karne"), "sure_sn": s["sure_sn"] + s.get("karne_sure_sn", 0)}


def _apply_preset(p: dict) -> None:
    """Hazır örneği forma doldurur."""
    st.session_state.update({"lab_x": p["x"], "lab_y": p["y"], "lab_bolge": p["bolge"], "lab_mevsim": p["mevsim"],
                             "lab_bek": p["bek"], "lab_gec": 0})
    st.session_state["lab_go"] = True


def page_lab() -> None:
    """Herhangi iki değişken, herhangi bir yer ve mevsim: L4 yöntemiyle canlı ilişki hesabı ve karnesi."""
    header("İlişki laboratuvarı",
           "Herhangi iki NASA değişkenini, istediğin yerde ve mevsimde karşılaştır.",
           "Ekibin L4 yöntemi canlı çalışır: alan ortalaması → mevsim serisi → trendden arındırma → Pearson r → "
           "otokorelasyona göre etkin örneklem → anlamlılık. Sonucun yanında beş kontrollü bulgu karnesi verilir.")
    try:
        opts, regions = lab_options()
    except Exception as e:  # noqa: BLE001
        st.info(f"İlişki motoru için L1 paketi bulunamadı ({type(e).__name__}). outputs/ klasörünü kontrol edin.")
        return
    variables = sorted(opts, key=lambda v: vname(v))
    cols = st.columns(len(LAB_PRESETS))
    for col, (lab, p) in zip(cols, LAB_PRESETS):
        if p["x"] in opts and p["y"] in opts:
            col.button(lab, key=f"lab_p_{lab}", on_click=_apply_preset, args=(p,), width="stretch")

    with st.container(border=False):
        a, b = st.columns(2)
        x = a.selectbox("Birinci değişken (x)", variables, format_func=vname, key="lab_x",
                        index=variables.index("sicaklik_2m") if "sicaklik_2m" in variables else 0)
        y = b.selectbox("İkinci değişken (y)", variables, format_func=vname, key="lab_y",
                        index=variables.index("kar_ortusu") if "kar_ortusu" in variables else 1)
        ux = uy = None
        if len(opts.get(x, [])) > 1 or len(opts.get(y, [])) > 1:
            a2, b2 = st.columns(2)
            auto = lambda u: u or "Otomatik (Kademe 1 önceliği)"  # noqa: E731
            if len(opts.get(x, [])) > 1:
                ux = a2.selectbox("x ürünü", [None] + opts[x], format_func=auto, key=f"lab_ux_{x}")
            if len(opts.get(y, [])) > 1:
                uy = b2.selectbox("y ürünü", [None] + opts[y], format_func=auto, key=f"lab_uy_{y}")
        c, d, e, f = st.columns([2, 1.4, 1, 1.2])
        keys = [k for k, _ in regions]
        names = dict(regions)
        bolge = c.selectbox("Yer", keys, format_func=names.get, key="lab_bolge",
                            index=keys.index("Erzurum") if "Erzurum" in keys else 0)
        mevsim = d.selectbox("Mevsim / seri", list(LAB_SEASONS), format_func=LAB_SEASONS.get, key="lab_mevsim",
                             index=1)
        gecikme = e.number_input("Gecikme (ay)", 0, 6, 0, key="lab_gec", help="x, y'den kaç ay önce alınsın")
        bek = f.selectbox("Fizik ne bekliyor?", list(LAB_EXPECT), format_func=LAB_EXPECT.get, key="lab_bek", index=2)
        with_karne = st.checkbox("Bulgu karnesini de hesapla (81 ilde yaklaşık 15 sn)", value=True, key="lab_karne")
        go = st.button("Hesapla", type="primary", key="lab_run")
    if go:
        st.session_state["lab_go"] = True
    if not st.session_state.get("lab_go"):
        return
    try:
        with st.spinner("Hesaplanıyor…"):
            res = lab_run(x, ux, y, uy, bolge, mevsim, int(gecikme), bek, with_karne)
    except Exception as ex:  # noqa: BLE001 — SecimHatasi mesajı kullanıcıya yöneliktir
        msg = str(ex).split("\n")[0]
        st.warning(f"Hesaplanamadı: {msg}")
        return
    _lab_result(res)


def _lab_result(res: dict) -> None:
    """Laboratuvar sonucunu çizer: tek yer için sayılar + karne, çok yer için harita + tablo."""
    s, t, k = res["secim"], res["tablo"], res["karne"]
    xn, yn = vname(s["x"]), vname(s["y"])
    season = LAB_ADV.get(s["mevsim"], s["mevsim"])
    esik = s["esik"].replace("0.", "0,")
    st.markdown('<div class="td-section"></div>', unsafe_allow_html=True)
    if res["yaml_cifti"]:
        st.markdown(f'<div class="td-callout">Bu seçim ekibin sabit çiftlerinden <b>{res["yaml_cifti"]}. çift</b> ile aynı; '
                    "kar maskesi gibi ayarları oradan alındı.</div>", unsafe_allow_html=True)
    multi = len(t) > 1
    if not multi:
        r = t.iloc[0]
        if pd.isna(r["r"]):
            header("Sonuç", f"{esc(s['bolge_adi'])} için ilişki hesaplanamadı.", esc(r.get("not") or ""))
            return
        sign = "aynı yönde" if r["r"] > 0 else "ters yönde"
        strength = "güçlü" if abs(r["r"]) >= 0.6 else ("orta" if abs(r["r"]) >= 0.3 else "zayıf")
        sig = r["anlamli"] == 1
        big = (f"{esc(loc(s['bolge_adi']))} {season} {esc(low(xn))} ile {esc(low(yn))} "
               + (f"{strength} ve anlamlı biçimde {sign} değişiyor." if sig else "arasında anlamlı bir ilişki yok."))
        header(f"Sonuç · {esc(s['bolge_adi'])}", big,
               f"r = <b>{fmt(r['r'], digits=2)}</b> (trend çıkarılmadan {fmt(r['r_ham'], digits=2)}) · {fmt_p(r['p'])} · "
               f"{esc(r['donem'])}, n = {int(r['n'])}, etkin n = {fmt(r['etkin_n'], digits=1)}. Eşik: {esc(esik)}.")
        lab = U.CONTROL_LABELS.get(r["etiket"]) if r["etiket"] else None
        kr = k.iloc[0] if k is not None and len(k) else None
        st.markdown((badge(*lab) if lab else badge("beklenti verilmedi", "info")) + " "
                    + (guven_badge(kr["guven"], kr["gerekce"]) if kr is not None else ""), unsafe_allow_html=True)
        stats_strip([(fmt(r["r"], digits=2), "r (trendsiz)"), (fmt(r["r_ham"], digits=2), "r (ham)"),
                     (fmt(r["egim_x_10yil"], digits=2), f"{esc(xn)} eğimi / 10 yıl"),
                     (fmt(r["egim_y_10yil"], digits=2), f"{esc(yn)} eğimi / 10 yıl")])
        if kr is not None:
            subhead("Bulgu karnesi")
            karne_table(kr, U.PAIR_CHECKS)
    else:
        d = t.copy()
        il = d[d["bolge_turu"] == "il"].copy()
        done = d[d["etiket"] != ""] if s["beklenen"] else d[d["anlamli"] == 1]
        n_sig = int((d["anlamli"] == 1).sum())
        header(f"Sonuç · {esc(s['bolge_adi'])}",
               f"{len(d)} yerin {n_sig} tanesinde {season} {esc(low(xn))} ile {esc(low(yn))} anlamlı biçimde "
               "birlikte değişiyor.",
               (f"Beklenen yönde: <b>{int((done['etiket'] == 'beklenen_yonde').sum())}</b>, ters yönde: "
                f"<b>{int((done['etiket'] == 'ters_yonde').sum())}</b>. " if s["beklenen"] else "")
               + f"Eşik: {esc(esik)}.")
        if len(il):
            il["plaka"] = pd.to_numeric(il["bolge_kodu"], errors="coerce").astype("Int64")
            st.plotly_chart(value_map(il, geojson, "r", "r", [("p_fdr", "p_fdr"), ("etiket", "etiket")]),
                            width="stretch", config=PLOT_CFG)
            st.markdown('<div class="td-legend"><span>ters yönde (r &lt; 0)<span class="bar"></span>aynı yönde (r &gt; 0)'
                        "</span></div>", unsafe_allow_html=True)
        view = d[["bolge_adi", "r", "r_ham", "p", "p_fdr", "anlamli", "etiket", "egim_x_10yil", "egim_y_10yil"]]
        if k is not None and len(k):
            view = view.assign(guven=list(k["guven"]))
        with st.expander(f"Bütün satırlar ({len(view)})", expanded=not len(il)):
            html_table(view, max_rows=100)
    for w in res["uyarilar"]:
        st.markdown(f'<div class="td-callout warn">{esc(w)}</div>', unsafe_allow_html=True)
    st.download_button("Sonucu CSV olarak indir", t.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"iliski__{s['x']}__{s['y']}__{s['bolge']}__{s['mevsim']}.csv", mime="text/csv")
    st.caption(f"Ürünler: {s['x']} {s['urun_x']} ({s['urun_x_gerekce']}) · {s['y']} {s['urun_y']} "
               f"({s['urun_y_gerekce']}). Hesap {fmt(res['sure_sn'], digits=1)} sn. Komut satırı karşılığı: "
               f"python -m physics.iliski --x {s['x']} --y {s['y']} --bolge {s['bolge']} --mevsim {s['mevsim']}"
               + (f" --beklenen {s['beklenen']}" if s["beklenen"] else ""))


# ================================================================ Büyüklük testleri
def page_fizik() -> None:
    """Yönün ötesinde: gözlenen büyüklük fiziğin beklediği bantta mı? (sözleşme 2.5)"""
    m = get_magnitude()
    if m["ozet"] is None:
        header("Büyüklük testleri", "Büyüklük testi çıktıları henüz üretilmedi.",
               "Üretmek için: <code>python -m physics.buyukluk --surum v0.1</code>")
        return
    header("Büyüklük testleri", "Fizik yalnız yönü değil, ne kadar değişmesi gerektiğini de söyler.",
           "Üç test: ısınınca havadaki nemin artış oranı, su bütçesinin kapanması ve kar çizgisinin yükselme hızı. "
           "Nokta gözlenen değer, çizgi %95 güven aralığı (blok bootstrap), gri bant fiziğin beklediği aralık. "
           "Aralık bandı kesiyorsa sonuç fizikle tutarlıdır; aralık çok genişse “belirsiz” denir.")
    tabs = st.tabs(["Nem ve sıcaklık (Clausius-Clapeyron)", "Su bütçesi", "Kar çizgisi"])

    with tabs[0]:
        d = m["cc_bolge"] if m["cc_bolge"] is not None else m["ozet"][m["ozet"]["test"] == "cc"]
        a, b = st.columns(2)
        var = a.segmented_control("Nem ölçüsü", ["su_buhari_kolon", "ozgul_nem_2m"], default="su_buhari_kolon",
                                  format_func=vname, key="f_cc_var") or "su_buhari_kolon"
        yol = b.segmented_control("Yöntem", ["a_yillar_arasi", "b_trend_orani"], default="a_yillar_arasi",
                                  format_func={"a_yillar_arasi": "Yıldan yıla", "b_trend_orani": "Trend oranı"}.get,
                                  key="f_cc_yol") or "a_yillar_arasi"
        _magnitude_block(d[(d["degisken"] == var) & (d["yol"] == yol)], "%/K",
                         lambda t: (f"Türkiye'de hava 1 °C ısındığında {low(vname(var))} yaklaşık "
                                    f"%{fmt(t['gozlenen'], digits=1)} artıyor; fizik %5,9–7,3 bekliyor."))
    with tabs[1]:
        d = m["butce_bolge"] if m["butce_bolge"] is not None else m["ozet"][m["ozet"]["test"] == "butce"]
        yol = st.segmented_control("Ölçü", ["ortalama", "trend"], default="ortalama",
                                   format_func={"ortalama": "Ortalama artık", "trend": "Artığın trendi"}.get,
                                   key="f_b_yol") or "ortalama"
        unit = "mm/yıl" if yol == "ortalama" else "(mm/yıl) / 10 yıl"
        _magnitude_block(d[d["yol"] == yol], unit,
                         lambda t: (f"Türkiye'de su bütçesi {fmt(t['gozlenen'], digits=0)} {unit} artıkla kapanıyor; "
                                    "fizik sıfıra yakın (yağışın ±%10'u) bekliyor."),
                         "Artık = depolama değişimi (GRACE) − (yağış − buharlaşma − akış). Bant dışı bir artık; veri, "
                         "model ya da sulama/yeraltı suyu çekimi gibi hesaba girmeyen bir akışa işaret edebilir.")
    with tabs[2]:
        d = m["kar_bolge"] if m["kar_bolge"] is not None else m["ozet"][m["ozet"]["test"] == "kar_cizgisi"]
        yol = st.segmented_control("Mevsim", ["kis", "ilkbahar"], default="kis", format_func=U.SEASONS.get,
                                   key="f_k_yol") or "kis"
        _magnitude_block(d[d["yol"] == yol], "m / 10 yıl",
                         lambda t: (f"Türkiye'de {low(U.SEASONS[yol])} kar çizgisi her 10 yılda yaklaşık "
                                    f"{fmt(t['gozlenen'], digits=0)} m yükseliyor; ısınmanın beklettiği "
                                    f"{fmt(t['beklenen_alt'], digits=0)}–{fmt(t['beklenen_ust'], digits=0)} m."),
                         "Beklenen: aynı bölgenin mevsim sıcaklık trendi ÷ 6,5 °C/km (bant 5,5–7,5 °C/km).")


def _magnitude_block(d: pd.DataFrame, unit: str, sentence, note: str = "") -> None:
    """Bir büyüklük testinin Türkiye cümlesi, bölge grafiği, etiket sayımı ve tablosu."""
    if d.empty:
        st.info("Bu seçim için sonuç yok.")
        return
    tr = d[d["bolge_adi"] == "Türkiye"]
    if len(tr) and pd.notna(tr.iloc[0]["gozlenen"]):
        t = tr.iloc[0]
        lab = t["etiket"]
        cls = {"beklenen büyüklükle tutarlı": "ok", "beklenenden küçük": "bad", "beklenenden büyük": "bad"}.get(lab, "info")
        st.markdown(f'<div class="td-answer" style="font-size:22px;margin-top:14px">{esc(sentence(t))}</div>'
                    f"{badge(lab, cls)} {guven_badge(t.get('guven'), t.get('gerekce'))}", unsafe_allow_html=True)
    counts = d[d["bolge_adi"] != "Türkiye"]["etiket"].value_counts()
    stats_strip([(str(int(counts.get(k, 0))), lab) for k, lab in
                 (("beklenen büyüklükle tutarlı", "bölgede tutarlı"), ("beklenenden küçük", "bölgede küçük"),
                  ("beklenenden büyük", "bölgede büyük"), ("belirsiz", "bölgede belirsiz (aralık geniş)"),
                  ("hesaplanamadı", "bölgede hesaplanamadı"))])
    st.plotly_chart(magnitude_chart(d, unit), width="stretch", config=PLOT_CFG)
    st.markdown('<div class="td-legend"><span><i style="background:#1a2742;border:1px solid #2c3d5c"></i>fiziğin '
                'beklediği aralık</span><span><i style="background:#2fb565"></i>tutarlı</span>'
                '<span><i style="background:#e07a3a"></i>bant dışı</span><span><i style="background:#7d89a3"></i>'
                "belirsiz</span></div>", unsafe_allow_html=True)
    if note:
        st.markdown(f'<p class="td-note">{esc(note)}</p>', unsafe_allow_html=True)
    with st.expander("Bütün satırlar ve karne"):
        cols = [c for c in ["bolge_adi", "donem", "n", "gozlenen", "ga_alt", "ga_ust", "beklenen_alt", "beklenen_ust",
                            "etiket", "a_kaynak_uyumu", "b_donem", "c_ga_genisligi", "guven", "gerekce", "yorum"]
                if c in d.columns]
        html_table(d[cols])


# ================================================================ Veri indir
def page_indir() -> None:
    """Hazır veri paketi ve atıf: herkese açık. Altta bu veriyi kullanan çalışmalar."""
    header("Veri indir", "Seç, indir, çalışmanda kullan.",
           f"Sürüm {U.VERSION} · {U.LICENSE} lisans · DOI yayında verilecek. Dosyadaki her sayı ekrandakiyle aynıdır.")
    il_df = tables["il"]
    variables = [v for v, *_ in U.TIER1 if v in set(il_df["degisken"])]
    st.markdown('<div class="td-step-h"><b>1</b>Değişkenler</div>', unsafe_allow_html=True)
    sel_vars = st.pills("Değişkenler", variables, selection_mode="multi", default=variables[:2], format_func=vname,
                        key="p_vars", label_visibility="collapsed")
    st.markdown('<div class="td-step-h"><b>2</b>Mevsim ve il <span>(boş bırakılırsa hepsi)</span></div>',
                unsafe_allow_html=True)
    sel_seasons = st.pills("Mevsimler", list(U.SEASONS), selection_mode="multi", format_func=U.SEASONS.get,
                           key="p_seasons", label_visibility="collapsed")
    sel_il = st.multiselect("İller", sorted(il_df["il"].unique(), key=U.norm_name), key="p_il",
                            placeholder="Tüm iller (81)", label_visibility="collapsed")
    st.markdown('<div class="td-step-h"><b>3</b>Ekler</div>', unsafe_allow_html=True)
    nc_files = [r for r in U.inventory() if r["katman"] == "L1_kup"]
    include_nc = st.checkbox("Aylık ızgara verisi (L1 NetCDF)", value=False, disabled=not nc_files,
                             help=None if nc_files else "Henüz üretilmiş L1 dosyası yok.")
    extra = []
    karne_files = [(p, f"karne/{p.name}") for p in [U._pkg_file("karne", n) for n in
                                                     ("trend_karne_il.csv", "trend_karne_bolge.csv", "iliski_karne.csv",
                                                      "KURALLAR.txt")] if p]
    mag_dir = U._pkg_file("L4_iliski", "buyukluk")
    mag_files = [(p, f"buyukluk/{p.name}") for p in sorted(mag_dir.glob("*")) if p.is_file()] if mag_dir else []
    if st.checkbox("Bulgu karnesi (her sonucun güven kontrolleri)", value=bool(karne_files), disabled=not karne_files):
        extra += karne_files
    if st.checkbox("Büyüklük testleri (CC, su bütçesi, kar çizgisi)", value=bool(mag_files), disabled=not mag_files):
        extra += mag_files
    st.markdown('<div class="td-step-h"><b>4</b>İndir</div>', unsafe_allow_html=True)
    rows = len(U.filter_trends(il_df, sel_vars, sel_seasons, sel_il, "il"))
    data, name = U.build_bundle(tables, sel_vars, sel_seasons, sel_il, user, include_nc, git_commit(), extra)
    a, b = st.columns([1, 2])
    sel = {"degiskenler": sel_vars or "hepsi", "mevsimler": sel_seasons or "hepsi", "iller": sel_il or "hepsi"}

    def _log() -> None:
        """İndirmeyi veri tabanına kaydeder (bağlı değilse sessizce geçer)."""
        if DB_OK:
            try:
                DB.log_download(user.get("id"), name, rows, sel)
            except Exception:  # noqa: BLE001
                pass

    a.download_button("Paketi indir (.zip)", data, file_name=name, mime="application/zip", type="primary",
                      width="stretch", on_click=_log)
    b.markdown(f'<p class="td-note" style="margin-top:6px">{rows} trend satırı · CSV tablolar, atıf dosyası, NASA kaynak '
               "listesi ve açıklama (BENIOKU.txt)." + (" <b style='color:var(--warn)'>Şu an örnek veri.</b>" if placeholder
                                                         else "") + "</p>", unsafe_allow_html=True)

    cit = U.citation()
    st.markdown('<div class="td-step-h" style="margin-top:36px"><b>5</b>Atıf</div>', unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["APA", "BibTeX", "Python ile aç"])
    t1.code(cit["apa"], language=None, wrap_lines=True)
    t2.code(cit["bibtex"], language="bibtex")
    real = "sen_egimi" in il_df.columns and not placeholder
    t3.code("import pandas as pd\n"
            + (f"trend = pd.read_csv(\"{PH}trend_iller.csv\", encoding=\"utf-8-sig\", dtype={{\"bolge_kodu\": str}})\n"
               "trend.query(\"bolge_adi == 'Erzurum' and mevsim == 'kis' and anlamli == 1\")" if real else
               f"trend = pd.read_csv(\"{PH}trend_iller.csv\", encoding=\"utf-8-sig\")\n"
               "trend.query(\"il == 'Erzurum' and mevsim == 'kis' and anlamli_fdr == 1\")"), language="python")
    st.caption("Kullandığın NASA ürünlerine de atıf yap: "
               + " · ".join(f'{s["short_name"]} (doi:{s["doi"]})' for s in U.nasa_sources() if s["doi"]))
    if not academic:
        st.markdown('<p class="td-note">Çalışmanı “bu veriyi kullanan çalışmalar” listesine eklemek için araştırmacı '
                    "hesabıyla giriş yap.</p>", unsafe_allow_html=True)
    if DB_OK:
        arts = DB.list_articles()
        if len(arts):
            subhead(f"Bu veriyi kullanan çalışmalar ({len(arts)})")
            studies_list(arts)


# ================================================================ Yöntem
def page_yontem() -> None:
    """Yöntem: dört adım, bulgu karnesi kuralı ve tesadüf deneyi."""
    header("Yöntem", "Bir trendi görmek kolay; tesadüf olmadığını göstermek zor.",
           "Her sonuç aynı adımlardan geçer ve yanında, sonuçlar görülmeden sabitlenmiş kurallarla verilen bir "
           "bulgu karnesi taşır.")
    steps = [("1 · Uyumlaştırma", "Bütün NASA ürünleri aynı 0,25° Türkiye ızgarasına, aynı aylara ve aynı birimlere "
              "getirilir (L1)."),
             ("2 · Mevsim serisi", "Her yıl için bir mevsim değeri çıkarılır; mevsim döngüsü yıldan yıla değişimi "
              "gizlemez (L2)."),
             ("3 · Trend ve anlamlılık", "Sen eğimi, otokorelasyona göre düzeltilmiş Mann-Kendall testi ve "
              "Benjamini-Hochberg FDR (α = 0,10) uygulanır (L2/L3)."),
             ("4 · İlişki ve fizik", "Trendi çıkarılmış seriler arasında korelasyon; fiziğin beklediği yön ve "
              "büyüklükle karşılaştırma (L4).")]
    st.markdown('<div class="td-grid">' + "".join(f'<div class="td-tile"><div class="t-name">{t}</div>'
                                                  f'<div class="t-note" style="font-size:14px">{b}</div></div>'
                                                  for t, b in steps) + "</div>", unsafe_allow_html=True)

    st.markdown('<div class="td-section"><h3>Bulgu karnesi</h3><p class="lead">Her trend ve ilişki sonucu beş '
                "kontrolden geçer. “Uygulanamaz” geçti sayılmaz.</p></div>", unsafe_allow_html=True)
    rows = "".join(f"<tr><td>{esc(q)}</td></tr>" for _, _, q in U.TREND_CHECKS)
    levels = [("YÜKSEK", "Anlamlı; beş kontrol de geçti, kritik veri uyarısı yok."),
              ("ORTA", "Anlamlı; karıştırma ve dönem kontrolleri geçti ama başka bir şart sağlanmadı (ör. tek kaynak)."),
              ("DÜŞÜK", "Anlamlı ama karıştırma ya da dönem kontrolünden kaldı."),
              ("YOK", "Sonuç anlamlı değil; değişim ya da ilişki iddiası yok.")]
    a, b = st.columns(2)
    a.markdown('<div class="td-table-wrap"><table class="td-table"><thead><tr><th>Trend kontrolleri</th></tr></thead>'
               f"<tbody>{rows}</tbody></table></div>", unsafe_allow_html=True)
    b.markdown('<div class="td-table-wrap"><table class="td-table"><thead><tr><th>Güven</th><th>Kural</th></tr></thead>'
               "<tbody>" + "".join(f"<tr><td>{guven_badge(lv)}</td><td>{esc(t)}</td></tr>" for lv, t in levels)
               + "</tbody></table></div>", unsafe_allow_html=True)

    st.markdown('<div class="td-section"><h3>Kendin dene: hiç değişmeyen 20 seri</h3><p class="lead">Aşağıdaki seriler '
                "tamamen rastgele; hiçbirinde gerçek bir eğilim yok. Yine de bazıları sıradan bir testte “anlamlı” çıkar. "
                "Haritada 1.300 hücre olunca bu tesadüfler 65'e çıkar; FDR düzeltmesi bunları ayıklar.</p></div>",
                unsafe_allow_html=True)
    if "noise_seed" not in st.session_state:
        st.session_state.noise_seed = 2026
    if st.button("Yeniden üret"):
        st.session_state.noise_seed += 1
    fig, hits = noise_experiment(seed=st.session_state.noise_seed)
    st.markdown(f'<p class="td-note">Bu denemede <b>{hits}</b> seri “anlamlı” göründü (beklenen yaklaşık 1). '
                "Kırmızı çizgiler tesadüf.</p>", unsafe_allow_html=True)
    st.plotly_chart(fig, width="stretch", config=PLOT_CFG)
    if academic:
        with st.expander("Formüller ve kaynaklar"):
            st.markdown("- Trend: Sen eğimi (birim / 10 yıl)\n"
                        "- Test: Hamed-Rao düzeltmeli Mann-Kendall (tanımsızsa düzeltmesiz MK, `mk_yedek = 1`)\n"
                        "- Çoklu test: Benjamini-Hochberg, α_FDR = 0,10 (Wilks, 2016); L3'te dosya × mevsim × düzey içinde\n"
                        "- Anlamlı (`anlamli = 1`): `p_fdr ≤ 0,10` **ve** %95 genişletilmiş aralık sıfırı dışlıyor\n"
                        "- İl/bölge: hücrelerin cos(enlem) ağırlıklı alan ortalaması serisinin trendi\n"
                        "- Gereken yıl: Weatherhead ve ark. (1998)\n"
                        "- İlişkiler: trendi çıkarılmış anomaliler, Bretherton ve ark. (1999) etkin n\n"
                        "- Büyüklük: blok bootstrap (Politis ve Romano, 1992); CC bandı Held ve Soden (2006)")
            a, b = st.columns(2)
            a.latex(r"n_{etkin} = n\,\frac{1-r_1 r_2}{1+r_1 r_2}")
            b.latex(r"n^{*} = \left[\frac{3.3\,\sigma}{|\omega|}\sqrt{\frac{1+\phi}{1-\phi}}\right]^{2/3}")


# ================================================================ Soru sor (Kişi 4: llm.answer)
EXAMPLE_QUESTIONS = [
    "Erzurum'da kar azalıyor mu, ısınmayla ilişkili mi?",
    "Konya'da toprak nemi azalıyor mu?",
    "Doğu Anadolu ısınıyor mu?",
]
EVIDENCE_CLASS = {"anlamli_artis": "ok", "anlamli_azalis": "ok", "beklenen_yonde": "ok", "ters_yonde": "bad",
                  "anlamsiz": "info", "yetersiz": "warn"}


@st.cache_resource(show_spinner=False)
def llm_package() -> tuple[str | None, bool]:
    """LLM katmanının okuyacağı analiz paketi: gerçek paket varsa o, yoksa yer tutucu paket.

    Dönüş: (paket yolu ya da None = llm kendi arasın, yer_tutucu_mu).
    """
    try:
        from llm.evidence import find_package
        real = find_package()
        if real is not None and (Path(real) / "L3_ozet").exists():
            return None, False
    except Exception:  # noqa: BLE001
        pass
    return str(U.write_placeholder_package()), True


@st.cache_data(ttl=600, show_spinner=False)
def ask(question: str, kitle: str, package: str | None) -> dict:
    """llm.answer() çağrısı (aynı soru 10 dk önbellekten gelir)."""
    from llm import answer as llm_answer
    return llm_answer(question, kitle=kitle, package=package)


def render_explanation(text: str) -> str:
    """Markdown açıklamayı güvenli HTML'e çevirir; [ref:id] → kanıt tablosundaki satıra bağlantı."""
    out = []
    for line in html.escape(text or "").splitlines():
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        line = re.sub(r"\[ref:([^\]]+)\]", r'<a class="td-ref" href="#ev-\1">kanıt</a>', line)
        if line.startswith("- "):
            line = f'<div class="td-li">{line[2:]}</div>'
        out.append(line)
    return "<br>".join(x for x in out if x).replace("</div><br>", "</div>")


def evidence_html(rows: list[dict]) -> str:
    """Kanıt tablosu (değerler ham sayı; Türkçe biçimde gösterilir)."""
    body = []
    for r in rows:
        val = r.get("deger")
        val = val if isinstance(val, str) else fmt(val, digits=3 if val is not None and abs(val) < 1 else 2)
        if r.get("aralik_95") and None not in r["aralik_95"]:
            val += f'<br><span class="muted">%95: {fmt(r["aralik_95"][0], digits=2)} … {fmt(r["aralik_95"][1], digits=2)}</span>'
        sig = " · ".join(x for x in (fmt_p(r["p"]) if r.get("p") is not None else "",
                                     fmt_p(r["q"]).replace("p", "q", 1) if r.get("q") is not None else "") if x) or "—"
        lab = r.get("etiket_sade") or r.get("etiket") or ""
        cls = EVIDENCE_CLASS.get(r.get("etiket"), "info")
        extra = " " + badge("doğrulanmadı", "warn") if r.get("dogrulanmadi") else ""
        body.append(f'<tr id="ev-{esc(r.get("id"))}"><td><b>{esc(vname(r.get("degisken") or ""))}</b>'
                    f'<br><span class="muted">{esc(r.get("urun"))} · {esc(r.get("bolge"))}</span></td>'
                    f'<td class="num">{val} <span class="muted">{esc(r.get("birim"))}</span></td>'
                    f'<td class="num">{sig}</td><td>{badge(lab, cls)}{extra}</td></tr>')
    return ('<div class="td-table-wrap"><table class="td-table"><thead><tr><th>Kanıt</th><th>Değer</th>'
            '<th>Anlamlılık</th><th>Sonuç</th></tr></thead><tbody>' + "".join(body) + "</tbody></table></div>")


def _pick_example() -> None:
    """Örnek soru seçilince metin kutusunu doldurur."""
    if st.session_state.get("q_example"):
        st.session_state["q_text"] = st.session_state["q_example"]


def page_soru() -> None:
    """Serbest soru → plan → paketten kanıt → doğrulanmış açıklama (Kişi 4'ün llm.answer katmanı)."""
    kitle = "akademisyen" if academic else "genel"
    header("Soru sor", "Sorunu yaz; cevap analiz paketindeki kanıtlardan kurulsun.",
           "Soru bir konuya ve bölgeye çevrilir, ilgili trend ve ilişki sonuçları paketten okunur. Metindeki her sayı "
           "bir kanıt satırına bağlıdır ve doğrulayıcıdan geçer; dil modeli sayı üretmez.", tag="Yol haritası · deneysel")
    st.pills("Örnek sorular", EXAMPLE_QUESTIONS, key="q_example", on_change=_pick_example)
    q = st.text_area("Soru", key="q_text", height=90, label_visibility="collapsed",
                     placeholder="Örn. Erzurum'da kar azalıyor mu, ısınmayla ilişkili mi?")
    go = st.button("Cevapla", type="primary", key="q_go")
    if go and q.strip():
        st.session_state["q_asked"] = q.strip()
    asked = st.session_state.get("q_asked")
    if not asked:
        return
    pkg, ph = llm_package()
    try:
        with st.spinner("Kanıtlar toplanıyor…"):
            out = ask(asked, kitle, pkg)
    except Exception as e:  # noqa: BLE001
        st.error(f"Soru cevaplanamadı ({type(e).__name__}). Lütfen soruyu farklı yazmayı dene.")
        return

    # llm.evidence.products_of kaynak uyumu dosyasını ürün sanıyor (Kişi 4'e bildirildi): boş satırı gösterme
    out = {**out, "evidence": [e for e in out.get("evidence") or []
                               if not str(e.get("id", "")).startswith("trend__") or "__kaynak_uyumu" not in str(e["id"])]}
    plan = out.get("plan") or {}
    chips = [badge("sayılar doğrulandı" if out.get("verified") else "doğrulanamadı", "ok" if out.get("verified") else "bad"),
             badge(f"açıklama: {'dil modeli' if out.get('explainer') == 'llm' else 'şablon'}", "info")]
    if plan.get("method"):
        chips.append(badge(f"plan: {'dil modeli' if plan['method'] == 'llm' else 'anahtar kelime'}", "info"))
    if ph:
        chips.append(badge("örnek veri · yer tutucu paket", "warn"))
    n_unver = sum(1 for r in out.get("evidence") or [] if r.get("dogrulanmadi"))
    if n_unver:
        chips.append(badge(f"{n_unver} kanıt doğrulanmamış üründen", "warn"))
    st.markdown('<div style="display:flex;gap:6px;flex-wrap:wrap;margin:18px 0 8px">' + "".join(chips) + "</div>",
                unsafe_allow_html=True)
    if out.get("message"):
        st.info(out["message"])
    if plan.get("gerekce"):
        place = plan.get("region_name") or ""
        st.markdown(f'<div class="td-callout"><b>Neden bu verilere baktık?</b> {esc(plan["gerekce"])}'
                    + (f" <span style='color:var(--muted)'>· bölge: {esc(place)}</span>" if place else "")
                    + "</div>", unsafe_allow_html=True)
    if out.get("explanation"):
        st.markdown(f'<div class="td-explain" style="margin-top:14px">{render_explanation(out["explanation"])}</div>',
                    unsafe_allow_html=True)
    if out.get("evidence"):
        subhead("Kanıt tablosu")
        st.markdown(evidence_html(out["evidence"]), unsafe_allow_html=True)
    notes = list(dict.fromkeys((out.get("academic_warnings") or []) + (out.get("warnings") or [])))
    if notes:
        st.markdown(f'<div class="td-callout warn">{badge("dikkat", "warn")} <b>Yorumlarken:</b>'
                    + "".join(f'<div class="td-li">{esc(w)}</div>' for w in notes) + "</div>", unsafe_allow_html=True)
    if academic and out.get("methods"):
        with st.expander("Veri ve yöntem paragrafı (makaleye hazır)"):
            st.code(out["methods"], language=None, wrap_lines=True)
        with st.expander("Veri atıfları ve kaynakça"):
            for c in out.get("data_citations") or []:
                st.markdown(f"- {c}")
            st.markdown("**Yöntem kaynakçası**")
            for c in out.get("method_references") or []:
                st.markdown(f"- {c}")
        if out.get("files"):
            with st.expander("Kullanılan paket dosyaları"):
                st.code("\n".join(out["files"]), language=None)


# ================================================================ Çalışmalar
STATUS = {"yayimlandi": ("Yayımlandı", "ok"), "degerlendirmede": ("Değerlendirmede", "warn"),
          "hazirlaniyor": ("Hazırlanıyor", "info")}


def studies_list(df: pd.DataFrame, mine: bool = False) -> None:
    """Çalışma kartları; `mine` ise her kartın altında silme düğmesi."""
    for _, r in df.iterrows():
        lab, cls = STATUS.get(r["durum"], (r["durum"], "info"))
        tags = " ".join(f'<span class="td-tag">{esc(vname(v))}</span>'
                        for v in str(r["degiskenler"] or "").split(",") if v)
        place = f' · {esc(r["iller"])}' if r["iller"] else ""
        doi = (f' · <a href="https://doi.org/{esc(r["doi"])}" target="_blank">doi:{esc(r["doi"])}</a>'
               if r["doi"] else "")
        journal = f' · <i>{esc(r["dergi"])}</i>' if r["dergi"] else ""
        example = " " + badge("örnek kayıt", "warn") if r["ornek"] else ""
        year = int(r["yil"]) if r["yil"] is not None else ""
        abstract = f'<p>{esc(r["ozet"])}</p>' if r["ozet"] else ""
        st.markdown(f'<div class="td-paper"><div class="p-top">{badge(lab, cls)}{example}'
                    f'<span class="p-year">{year}</span></div><h4>{esc(r["baslik"])}</h4>'
                    f'<div class="p-meta">{esc(r["yazarlar"])}{journal}{doi}</div>'
                    f'<div class="p-meta">Ekleyen: {esc(r["ekleyen"])} · {esc(r["kurum"] or "")}'
                    f' · veri {esc(r["veri_surumu"] or "")}{place}</div>{abstract}<div>{tags}</div></div>',
                    unsafe_allow_html=True)
        if mine and st.button("Sil", key=f"del_{r['id']}"):
            DB.delete_article(user["id"], int(r["id"]))
            st.toast("Çalışma silindi.")
            st.rerun()


def page_makale() -> None:
    """Araştırmacının çalışmaları: ekle, listele, sil; altta diğer çalışmalar."""
    if not DB_OK or not user.get("id"):
        st.markdown('<div class="td-lock"><h3>Çalışma eklemek için veri tabanı gerekli</h3>'
                    "<p>SQL Server bağlı değil ya da demo girişiyle girdin. Kurulum: <code>python app/db/kur.py</code>, "
                    "sonra araştırmacı hesabınla giriş yap.</p></div>", unsafe_allow_html=True)
        return
    mine = DB.list_articles(user["id"])
    header("Çalışmalarım", f"Bu veriyi kullanan {len(mine)} çalışman var.",
           "Makaleni, tezini ya da projeni ekle; “bu veriyi kullanan çalışmalar” listesinde görünsün.")
    with st.expander("Yeni çalışma ekle", expanded=mine.empty):
        a, b = st.columns([3, 1])
        title = a.text_input("Başlık", key="m_title", placeholder="Doğu Anadolu'da kış kar örtüsünün değişimi")
        year = b.number_input("Yıl", min_value=1990, max_value=2100, value=2026, step=1, key="m_year")
        a, b = st.columns(2)
        authors = a.text_input("Yazarlar", key="m_auth", placeholder="Yılmaz, A.; Kaya, E.")
        journal = b.text_input("Dergi / kurum", key="m_journal", placeholder="Dergi adı ya da tez")
        a, b = st.columns(2)
        doi = a.text_input("DOI (varsa)", key="m_doi", placeholder="10.xxxx/xxxxx")
        stat = b.selectbox("Durum", list(STATUS), key="m_status", format_func=lambda k: STATUS[k][0])
        vars_ = st.pills("Kullandığın değişkenler", [v for v, *_ in U.TIER1], selection_mode="multi",
                         format_func=vname, key="m_vars")
        ils = st.multiselect("İller (varsa)", sorted(tables["il"]["il"].unique(), key=U.norm_name), key="m_ils",
                             placeholder="Türkiye geneli")
        abstract = st.text_area("Kısa özet", key="m_abs", height=90)
        if st.button("Çalışmayı ekle", type="primary", key="m_add"):
            art = {"baslik": title, "yazarlar": authors, "dergi": journal, "yil": int(year), "doi": doi,
                   "ozet": abstract, "degiskenler": ",".join(vars_ or []), "iller": ",".join(ils), "durum": stat}
            errs = DB.validate_article(art)
            for e in errs:
                st.error(e)
            if not errs:
                DB.add_article(user["id"], art)
                for k in ("m_title", "m_auth", "m_journal", "m_doi", "m_abs", "m_vars", "m_ils"):
                    st.session_state.pop(k, None)
                st.toast("Çalışma eklendi.")
                st.rerun()
    if len(mine):
        subhead("Benim çalışmalarım")
        studies_list(mine, mine=True)
    others = DB.list_articles()
    others = others[~others["id"].isin(mine["id"])]
    if len(others):
        subhead(f"Bu veriyi kullanan diğer çalışmalar ({len(others)})")
        studies_list(others)


PAGE_FUNCS = {"kesfet": page_kesfet, "il": page_il, "iliski": page_iliski, "lab": page_lab, "fizik": page_fizik,
              "soru": page_soru, "indir": page_indir, "makale": page_makale, "yontem": page_yontem}


# ================================================================ giriş ekranı
ROLE_TABS = {"vatandas": "Vatandaş", "akademisyen": "Akademisyen"}


def _mode(m: str) -> None:
    """Giriş kartındaki görünümü değiştirir: giris | kayit | sifre."""
    st.session_state["auth_mode"] = m
    st.session_state.pop("reset_email", None)


def _login(u: dict) -> None:
    """Oturumu açar ve şifre alanlarını bellekten siler."""
    for k in ("l_pw", "s_pw", "s_pw2", "f_pw", "f_pw2"):
        st.session_state.pop(k, None)
    st.session_state["user"] = u
    st.session_state["auth_mode"] = "giris"
    st.rerun()


def _links(*items: tuple[str, str]) -> None:
    """Kartın altındaki küçük bağlantı düğmeleri."""
    cols = st.columns(len(items))
    for col, (label, mode) in zip(cols, items):
        col.button(label, key=f"lnk_{mode}_{label}", type="tertiary", on_click=_mode, args=(mode,), width="stretch")


def card_login(role: str) -> None:
    """E-posta + şifre ile giriş."""
    st.markdown(f'<div class="td-card-h">Giriş yap</div><div class="td-card-s">'
                f'{"Vatandaş" if role == "vatandas" else "Akademisyen"} hesabınla devam et.</div>', unsafe_allow_html=True)
    email = st.text_input("E-posta", key="l_email", placeholder="ornek@eposta.com")
    pw = st.text_input("Şifre", type="password", key="l_pw")
    if st.button("Giriş yap", type="primary", width="stretch", key="do_login"):
        if not DB_OK:
            if auth.EMAIL_RE.match(email.strip()):
                _login(auth.make_user(role, email.split("@")[0], email, "Demo kurum"))
            st.error("Geçerli bir e-posta yazın.")
        else:
            u = DB.authenticate(email, pw)
            if not u:
                st.error("E-posta ya da şifre hatalı.")
            else:
                if u["rol"] != role:
                    st.toast(f"{ROLE_TABS[u['rol']]} hesabıyla giriş yapıldı.")
                _login(u)
    _links(("Şifremi unuttum", "sifre"), ("Yeni üye ol", "kayit"))
    if role == "vatandas":
        st.markdown('<div class="td-or"><span>ya da</span></div>', unsafe_allow_html=True)
        if st.button("Üye olmadan devam et", width="stretch", key="go_guest"):
            _login(auth.make_user("vatandas", "Ziyaretçi"))


def card_signup(role: str) -> None:
    """Yeni üye formu; akademisyende kurum ve ORCID de istenir."""
    st.markdown(f'<div class="td-card-h">Yeni üye ol</div><div class="td-card-s">'
                f'{"İlini takip et, sonuçları kaydet." if role == "vatandas" else "Veri indir, çalışmanı ekle, atıf yap."}'
                "</div>", unsafe_allow_html=True)
    name = st.text_input("Ad soyad", key="s_name", placeholder="Ayşe Yılmaz")
    inst = orcid = ""
    if role == "akademisyen":
        a, b = st.columns(2)
        inst = a.text_input("Kurum", key="s_inst", placeholder="Üniversite / enstitü")
        orcid = b.text_input("ORCID (isteğe bağlı)", key="s_orcid", placeholder="0000-0000-0000-0000")
    email = st.text_input("Kurum e-postası" if role == "akademisyen" else "E-posta", key="s_email",
                          placeholder="ad.soyad@uni.edu.tr" if role == "akademisyen" else "ornek@eposta.com")
    a, b = st.columns(2)
    pw = a.text_input("Şifre", type="password", key="s_pw", help="En az 8 karakter, harf ve rakam")
    pw2 = b.text_input("Şifre (tekrar)", type="password", key="s_pw2")
    consent = st.checkbox("Bilgilerimin yalnızca bu hizmet için saklanmasını kabul ediyorum.", key="s_ok")
    if st.button("Üye ol", type="primary", width="stretch", key="do_signup"):
        errs = auth.validate_signup(role, name, email, pw, pw2, inst, orcid, consent)
        for e in errs:
            st.error(e)
        if not errs:
            if not DB_OK:
                _login(auth.make_user(role, name, email, inst, orcid))
            try:
                _login(DB.register(name, email, inst, orcid, pw, role=role))
            except ValueError as ex:
                st.error(str(ex))
    _links(("Zaten üye misin? Giriş yap", "giris"))


def card_reset() -> None:
    """Şifremi unuttum: önce e-postaya kod, sonra kod + yeni şifre."""
    st.markdown('<div class="td-card-h">Şifremi unuttum</div>', unsafe_allow_html=True)
    if not DB_OK:
        st.markdown('<div class="td-card-s">Şifre sıfırlama için veri tabanı gerekli.</div>', unsafe_allow_html=True)
        _links(("Girişe dön", "giris"))
        return
    target = st.session_state.get("reset_email")
    if not target:
        st.markdown('<div class="td-card-s">E-postanı yaz, sana 6 haneli bir kod gönderelim.</div>',
                    unsafe_allow_html=True)
        email = st.text_input("E-posta", key="f_email", placeholder="ornek@eposta.com")
        if st.button("Kod gönder", type="primary", width="stretch", key="do_code"):
            if not auth.EMAIL_RE.match(email.strip()):
                st.error("Geçerli bir e-posta yazın.")
            else:
                res = DB.request_reset(email)
                st.session_state["reset_email"] = email.strip().lower()
                st.session_state.pop("reset_demo_code", None)
                if res and eposta.configured():
                    try:
                        eposta.send_reset_code(email, res[1], res[0], DB.RESET_MINUTES)
                    except Exception:  # noqa: BLE001
                        st.session_state["reset_demo_code"] = res[0]
                elif res:
                    st.session_state["reset_demo_code"] = res[0]
                st.rerun()
    else:
        st.markdown(f'<div class="td-card-s">Bu e-posta kayıtlıysa <b>{esc(target)}</b> adresine bir kod '
                    f"gönderildi. Kod {DB.RESET_MINUTES} dakika geçerli.</div>", unsafe_allow_html=True)
        demo = st.session_state.get("reset_demo_code")
        if demo:
            st.markdown(f'<div class="td-demo-code">Demo: e-posta sunucusu ayarlı değil, kod burada gösteriliyor: '
                        f"<b>{demo}</b></div>", unsafe_allow_html=True)
        code = st.text_input("Kod", key="f_code", max_chars=6, placeholder="123456")
        a, b = st.columns(2)
        pw = a.text_input("Yeni şifre", type="password", key="f_pw")
        pw2 = b.text_input("Yeni şifre (tekrar)", type="password", key="f_pw2")
        if st.button("Şifreyi değiştir", type="primary", width="stretch", key="do_reset"):
            errs = auth.validate_password(pw, pw2)
            for e in errs:
                st.error(e)
            if not errs:
                if DB.reset_password(target, code, pw):
                    for k in ("reset_email", "reset_demo_code", "f_code", "f_pw", "f_pw2"):
                        st.session_state.pop(k, None)
                    st.session_state["auth_mode"] = "giris"
                    st.session_state["l_email"] = target
                    st.toast("Şifren değişti. Yeni şifrenle giriş yapabilirsin.")
                    st.rerun()
                st.error("Kod hatalı ya da süresi dolmuş.")
    _links(("Girişe dön", "giris"))


def login_screen() -> None:
    """Tam ekran, kaymayan giriş: arkada Dünya, solda tanıtım, sağda giriş kartı."""
    with st.container(key="herobg"):
        render_hero(build_config(U.YAYIN_BBOX, "2001–2025", U.VERSION, placeholder, mode="bg"))
    n_vars = len({r["dosya"].split("__")[0] for r in U.inventory() if r["katman"] == "L1_kup"}) or 24
    with st.container(key="login"):
        left, right = st.columns([1.15, 1], gap="large", vertical_alignment="center")
        left.markdown(
            f'<div class="td-login-brand" lang="tr">{MARK_SVG}<span>Trend Dedektifi<br>NASA Space Apps Challenge 2026</span></div>'
            '<div class="td-login-h">NASA uydu verisinden <em>Türkiye</em> için analize hazır iklim trendleri</div>'
            '<p class="td-login-p">25 yıllık NASA verisi, 81 il ve 7 bölge için trendler, değişkenler arası ilişkiler ve '
            "her sonucun yanında bir güven karnesi. Vatandaş haritaya bakar; araştırmacı indirir ve atıf yapar.</p>"
            f'<div class="td-login-facts" lang="tr"><div><b>{n_vars}</b><span>NASA değişkeni</span></div>'
            "<div><b>81</b><span>il · 7 bölge</span></div><div><b>2001–2025</b><span>aylık seri</span></div>"
            "<div><b>5</b><span>kontrollü güven karnesi</span></div></div>"
            + ('<div class="td-login-ph">Şu an örnek veri gösteriliyor</div>' if placeholder else ""),
            unsafe_allow_html=True)
        with right, st.container(key="logincard"):
            kw = {} if "login_role" in st.session_state else {"default": "vatandas"}
            role = st.segmented_control("Hesap türü", list(ROLE_TABS), format_func=ROLE_TABS.get, key="login_role",
                                        label_visibility="collapsed", width="stretch", **kw) or "vatandas"
            mode = st.session_state.get("auth_mode", "giris")
            if mode == "kayit":
                card_signup(role)
            elif mode == "sifre":
                card_reset()
            else:
                card_login(role)
            if not DB_OK:
                st.markdown('<p class="td-note">Veri tabanı bağlı değil: demo girişi (bilgiler kaydedilmez).</p>',
                            unsafe_allow_html=True)


def masthead() -> str:
    """Üst çubuk (marka, veri durumu, kullanıcı, çıkış) ve sayfa sekmeleri. Dönüş: seçili sayfa."""
    u = user
    which = tables.get("yer_tutucu_tablolar") or []
    what = ("trendler ve ilişkiler" if len(which) == 3 else "ilişkiler" if which == ["ciftler.csv"] else "trendler")
    ph = (f'<span class="tag warn" title="Analiz paketi bulunamadı ({", ".join(which)}); outputs/ altına gelince site '
          f'gerçek veriye geçer.">ÖRNEK VERİ · {what}</span>') if placeholder else \
        f'<span class="tag live">NASA VERİSİ · {U.VERSION}</span>'
    role = "Akademisyen" if academic else "Vatandaş"
    inst = esc(u.get("kurum")) if academic and u.get("kurum") else role
    with st.container(key="appbg"):
        render_hero(build_config(U.YAYIN_BBOX, "2001–2025", U.VERSION, placeholder, mode="ambient"))
    with st.container(key="masthead"):
        a, b = st.columns([10, 1], vertical_alignment="center")
        a.markdown(f'<div class="td-mast" lang="tr">{MARK_SVG}<span class="wm">Trend Dedektifi'
                   '<small>NASA Space Apps Challenge 2026 · Türkiye iklim trendi veri seti</small></span>'
                   f'{ph}<span class="who"><b>{esc(u["ad"])}</b><span>{inst}</span></span></div>',
                   unsafe_allow_html=True)
        if b.button("Çıkış", key="logout"):
            for k in ("user", "page", "auth_mode"):
                st.session_state.pop(k, None)
            st.rerun()
    pages = auth.pages_for(user)
    with st.container(key="navbar"):
        page = st.segmented_control("Sayfa", pages, default=pages[0], key="page", format_func=auth.PAGES.get,
                                    label_visibility="collapsed") or pages[0]
    return page


# ================================================================ içerik
if not user:
    login_screen()
    st.stop()

page = masthead()
with st.container(key="content"):
    PAGE_FUNCS.get(page, page_kesfet)()
    footer()
