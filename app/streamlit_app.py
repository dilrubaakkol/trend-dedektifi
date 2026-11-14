"""Trend Dedektifi — veri setinin vitrini (Kişi 5).

Çalıştırma (repo kökünden):  streamlit run app/streamlit_app.py

Hikâye: Uydu ölçer → biz hazırlarız → sen kullanırsın.
Akış: açılış (dönen Dünya) → nasıl çalışır (3 adım) → giriş (merak eden / araştırmacı) →
Türkiye haritası · İlimi bul · Birlikte değişenler · Veriyi indir · Nasıl hesaplıyoruz?
Her sayfanın başında tek bir büyük cevap cümlesi vardır; ayrıntı araştırmacıya açılır.
Site yeni hesap yapmaz; Katman 1–4 dosyalarını okur. Dosyalar henüz yoksa sentetik yer tutucu
tablolar gösterilir ve işaretlenir.
"""

from __future__ import annotations

import html
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
from charts import noise_experiment, province_trend_map, relation_map, source_comparison  # noqa: E402
from formatting import fmt  # noqa: E402
from hero import build_config, render_hero  # noqa: E402
from theme import inject_theme, section  # noqa: E402

st.set_page_config(page_title="Trend Dedektifi", page_icon="🛰️", layout="wide", initial_sidebar_state="collapsed")
inject_theme()

# Değişkenlerin sade adı ve simgesi (sözleşmedeki adlarla birebir).
VARS = {
    "sicaklik_2m": ("🌡️", "Sıcaklık"),
    "yagis": ("🌧️", "Yağış"),
    "kar_ortusu": ("❄️", "Kar örtüsü"),
    "kar_su_esdegeri": ("🏔️", "Kar suyu"),
    "toprak_nemi": ("💧", "Toprak nemi"),
    "ndvi": ("🌱", "Bitki örtüsü"),
    "toplam_su_depolama": ("🛰️", "Yeraltı + yüzey suyu"),
    "buharlasma": ("♨️", "Buharlaşma"),
    "yuzey_sicakligi_gunduz": ("☀️", "Toprak yüzeyi sıcaklığı"),
}
# İlişki çiftleri, sade soru olarak.
PAIR_QUESTIONS = {
    1: "Kış ısınınca kar azalıyor mu?",
    2: "Yağmur yağınca toprak nemleniyor mu?",
    3: "Toprak nemlenince bitki yeşeriyor mu?",
    4: "Yağış, yer altındaki suyu dolduruyor mu?",
    5: "Yaz ısınınca buharlaşma artıyor mu?",
    6: "İki farklı ölçüm aynı sıcaklığı mı gösteriyor?",
}
PLOT_CFG = {"displayModeBar": False}


# ---------------------------------------------------------------- yardımcılar
def vname(key: str) -> str:
    """Değişkenin sade adı."""
    return VARS.get(key, ("", U.variable_cards().get(key, {}).get("baslik", key)))[1]


def vlabel(key: str) -> str:
    """Simgeli ad (düğmeler için)."""
    icon, name = VARS.get(key, ("", vname(key)))
    return f"{icon} {name}".strip()


def unit_of(birim: str) -> str:
    """'mm/10 yil' → 'mm'; birimsiz NDVI için boş metin."""
    u = str(birim).replace("/10 yil", "").strip()
    return "" if u in ("1", "") else u


def num(v: float) -> str:
    """Eğim için okunur sayı (küçük değerlerde 3 basamak)."""
    return fmt(abs(v), digits=3 if abs(v) < 0.1 else (1 if abs(v) >= 10 else 2))


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
    """Trend ve ilişki tabloları: önce MS SQL, olmazsa dosyalar / yer tutucu (5 dk önbellek)."""
    if use_db:
        try:
            t = DB.load_tables()
            if t is not None:
                return {**t, "kaynak_turu": "mssql"}
        except Exception:  # noqa: BLE001
            pass
    return {**U.load_tables(), "kaynak_turu": "dosya"}


def main_product(var: str) -> str:
    """Kademe 1 tablosundaki ana NASA ürünü."""
    return next((prods[0] for v, prods, _ in U.TIER1 if v == var), "")


def seasons_for(df: pd.DataFrame, var: str) -> list[str]:
    """Bu değişken için tabloda bulunan mevsimler (belgedeki sırayla)."""
    have = set(df.loc[df["degisken"] == var, "mevsim"])
    return [s for s in U.SEASONS if s in have]


def verdict(row) -> tuple[str, str]:
    """Bir trend satırı için sade hüküm ve rengi: (metin, css sınıfı)."""
    if row["anlamli_fdr"] == 1 and not row["belirsiz"]:
        return "Gerçek bir değişim", "ok"
    if row["belirsiz"]:
        return "Testler çelişiyor", "warn"
    return "Henüz belirsiz", "info"


def answer(big: str, small: str = "") -> None:
    """Sayfanın en üstündeki büyük cevap cümlesi."""
    st.markdown(f'<div class="td-answer">{big}</div>' + (f'<div class="td-answer-sub">{small}</div>' if small else ""),
                unsafe_allow_html=True)


def html_table(df: pd.DataFrame, max_rows: int = 200) -> None:
    """Temaya uygun HTML tablo (Streamlit'in hazır tablosu temayla çakıştığı için)."""
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    body = []
    for _, r in df.head(max_rows).iterrows():
        cells = []
        for v in r:
            if isinstance(v, float):
                v = "" if pd.isna(v) else f"{v:.4g}"
            cells.append(f'<td class="num">{html.escape(str(v))}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(f'<div class="td-table-wrap td-scroll"><table class="td-table td-dense"><thead><tr>{head}</tr></thead>'
                f'<tbody>{"".join(body)}</tbody></table></div>', unsafe_allow_html=True)


STAT_COLS = ["degisken", "urun", "mevsim", "donem", "n_yil", "n_hucre", "egim_10yil", "ci_alt", "ci_ust", "birim",
             "p_mk", "p_mk_kontrol", "p_ttest", "belirsiz", "anlamli_fdr", "yil_sayisi_gereken", "kaynak_uyumu"]


def stats_table(df: pd.DataFrame, place_col: str) -> pd.DataFrame:
    """Araştırmacı tablosu: sütun adları CSV ile aynı."""
    return df[[c for c in [place_col] + STAT_COLS if c in df.columns]]


# ---------------------------------------------------------------- durum
DB_OK = db_ok()
tables = get_tables(DB_OK)
placeholder = tables["yer_tutucu"]
user = st.session_state.get("user")
geojson = U.provinces_geojson()
academic = auth.is_academic(user)
PH = "YER_TUTUCU_" if placeholder else ""



def footer() -> None:
    """Alt bilgi: kullanılan NASA ürünleri ve DOI'leri."""
    items = " · ".join(f'<a href="https://doi.org/{s["doi"]}" target="_blank">{s["short_name"]}</a>' if s["doi"]
                       else s["short_name"] for s in U.nasa_sources())
    st.markdown(f'<div class="td-foot"><b style="color:var(--ink)">Kullanılan NASA verileri:</b> {items}<br>'
                f"Trend Dedektifi · NASA Space Apps Challenge 2026 · veri {U.LICENSE}, kod MIT · "
                "Bu araç NASA tarafından yapılmamıştır; NASA'nın açık verilerini kullanır.</div>",
                unsafe_allow_html=True)


# ================================================================ sayfalar
def pick_variable(df: pd.DataFrame, key: str) -> str:
    """Simgeli değişken düğmeleri."""
    variables = [v for v, *_ in U.TIER1 if v in set(df["degisken"])]
    return st.pills("Ne merak ediyorsun?", variables, default=variables[0], format_func=vlabel,
                    key=key) or variables[0]


def pick_season(df: pd.DataFrame, var: str, key: str, default: str | None = None) -> str:
    """Mevsim düğmeleri."""
    seasons = seasons_for(df, var)
    d = default if default in seasons else seasons[0]
    return st.pills("Hangi mevsim?", seasons, default=d, format_func=U.SEASONS.get, key=f"{key}_{var}") or d


def page_kesfet() -> None:
    """Türkiye haritası: büyük cevap cümlesi + harita + en çok değişen iller."""
    il_df = tables["il"]
    var = pick_variable(il_df, "k_var")
    season = pick_season(il_df, var, "k_season", "kis")
    prod = main_product(var)
    if academic:
        products = list(dict.fromkeys(il_df.loc[il_df["degisken"] == var, "urun"]))
        if len(products) > 1:
            prod = st.pills("NASA ürünü", products, default=prod, key=f"k_prod_{var}") or prod
    df = il_df[(il_df["degisken"] == var) & (il_df["mevsim"] == season) & (il_df["urun"] == prod)]
    if df.empty:
        st.info("Bu seçim için veri yok.")
        return
    unit = unit_of(df["birim"].iloc[0])
    tr = tables["bolge"]
    tr = tr[(tr["bolge"] == "turkiye") & (tr["degisken"] == var) & (tr["mevsim"] == season) & (tr["urun"] == prod)]
    sig = df[df["anlamli_fdr"] == 1]
    up, down = int((sig["egim_10yil"] > 0).sum()), int((sig["egim_10yil"] < 0).sum())

    season_txt = {"yillik": "", "kis": "kışın ", "ilkbahar": "ilkbaharda ", "yaz": "yazın ",
                  "sonbahar": "sonbaharda "}.get(season, "")
    if len(tr):
        t = tr.iloc[0]
        cls = "up" if t["egim_10yil"] > 0 else "down"
        verb = "arttı" if t["egim_10yil"] > 0 else "azaldı"
        big = (f"Türkiye'de {season_txt}{vname(var).lower()} her 10 yılda "
               f'<span class="{cls}">{num(t["egim_10yil"])} {unit} {verb}</span>.')
    else:
        big = f"Türkiye'de {season_txt}{vname(var).lower()}"
    small = (f"81 ilin <b class='up'>{up}</b>'inde gerçek bir artış, <b class='down'>{down}</b>'inde gerçek bir azalış "
             f"var. Gri iller: değişim henüz tesadüften ayırt edilemiyor. Dönem {str(df['donem'].iloc[0]).replace('-', '–')}.")
    answer(big, small)

    st.plotly_chart(province_trend_map(df, geojson, f"{unit} / 10 yıl" if unit else "/ 10 yıl"), width="stretch",
                    config=PLOT_CFG)
    st.markdown('<div class="td-legend"><span><i style="background:#e8364b"></i>arttı</span>'
                '<span><i style="background:#1f6fe0"></i>azaldı</span>'
                '<span><i style="background:#2b3552"></i>henüz belirsiz</span>'
                '<span>· ilin üzerine gel, ayrıntısını gör</span></div>', unsafe_allow_html=True)

    top = sig.reindex(sig["egim_10yil"].abs().sort_values(ascending=False).index).head(3)
    if len(top):
        st.markdown('<div class="td-mini-h">En çok değişen 3 il</div>', unsafe_allow_html=True)
        cols = st.columns(3)
        for col, (_, r) in zip(cols, top.iterrows()):
            cls = "up" if r["egim_10yil"] > 0 else "down"
            arrow = "▲" if r["egim_10yil"] > 0 else "▼"
            col.markdown(f'<div class="td-tile"><div class="t-name">{html.escape(r["il"])}</div>'
                         f'<div class="t-val {cls}">{arrow} {num(r["egim_10yil"])}<small> {unit} / 10 yıl</small></div>'
                         f'</div>', unsafe_allow_html=True)

    if academic:
        with st.expander("Araştırmacı ayrıntısı · tüm iller, güven aralıkları, p değerleri"):
            view = stats_table(df.sort_values("egim_10yil"), "il")
            html_table(view)
            st.download_button("Bu tabloyu CSV indir", view.to_csv(index=False).encode("utf-8"),
                               file_name=f"{PH}trend_iller__{var}__{prod}__{season}.csv", mime="text/csv")
        rows = tables["bolge"]
        rows = rows[(rows["bolge"] == "turkiye") & (rows["degisken"] == var) & (rows["mevsim"] == season)]
        if len(rows) > 1:
            with st.expander(f"Kaynak karşılaştırması · {len(rows)} NASA ürünü aynı şeyi söylüyor mu?"):
                st.plotly_chart(source_comparison(rows, f"{unit} / 10 yıl"), width="stretch", config=PLOT_CFG)
                st.caption("Nokta: Sen eğimi. Çubuk: otokorelasyona göre genişletilmiş %95 aralık. Ürünler ortak girdi "
                           "paylaştığı için bu bağımsız doğrulama değil, tutarlılık göstergesidir.")


def page_il() -> None:
    """Bir ilin bütün değişkenleri: her biri için büyük sayı ve sade hüküm."""
    il_df = tables["il"]
    names = sorted(il_df["il"].unique(), key=U.norm_name)
    c1, c2 = st.columns([1, 2.2])
    il = c1.selectbox("İlini seç", names, index=names.index("Erzurum") if "Erzurum" in names else 0, key="i_il")
    with c2:
        season = st.pills("Hangi mevsim?", list(U.SEASONS), default="kis", format_func=U.SEASONS.get,
                          key="i_season") or "kis"
    sub = il_df[il_df["il"] == il]
    main = sub[[u == main_product(v) for u, v in zip(sub["urun"], sub["degisken"])]]
    cur = main[main["mevsim"] == season]
    real = cur[(cur["anlamli_fdr"] == 1) & (cur["belirsiz"] == 0)]
    season_txt = "Yıl boyunca" if season == "yillik" else f"{U.SEASONS[season]} aylarında"
    answer(f"{html.escape(il)}: {season_txt} <span class='ember'>{len(real)} değişkende</span> gerçek bir değişim var.",
           f"{len(cur)} değişkene bakıldı. Kalanlarda değişim, eldeki 25 yılla henüz tesadüften ayırt edilemiyor.")

    tiles = []
    for _, r in cur.iterrows():
        icon, name = VARS.get(r["degisken"], ("", r["degisken"]))
        unit = unit_of(r["birim"])
        lab, cls = verdict(r)
        dir_cls = "up" if r["egim_10yil"] > 0 else "down"
        arrow = "▲" if r["egim_10yil"] > 0 else "▼"
        note = ""
        if lab == "Henüz belirsiz" and pd.notna(r.get("yil_sayisi_gereken")):
            n = r["yil_sayisi_gereken"]
            note = f'<div class="t-note">Emin olmak için {"100+ yıl" if n >= 100 else f"~{int(n)} yıl daha"} veri gerek</div>'
        tiles.append(f'<div class="td-tile {"dim" if cls != "ok" else ""}"><div class="t-ico">{icon}</div>'
                     f'<div class="t-name">{html.escape(name)}</div>'
                     f'<div class="t-val {dir_cls}">{arrow} {num(r["egim_10yil"])}<small> {unit} / 10 yıl</small></div>'
                     f'<span class="td-badge {cls}">{lab}</span>{note}</div>')
    st.markdown(f'<div class="td-grid">{"".join(tiles)}</div>', unsafe_allow_html=True)

    if academic:
        with st.expander(f"Araştırmacı ayrıntısı · {il} için tüm satırlar"):
            html_table(stats_table(sub[sub["mevsim"] == season], "il"))
            st.download_button(f"{il} · tüm mevsimler CSV", stats_table(sub, "il").to_csv(index=False).encode("utf-8"),
                               file_name=f"{PH}trend_iller__{U.norm_name(il)}.csv", mime="text/csv")


def page_iliski() -> None:
    """Birlikte değişen değişkenler: sade soru → büyük cevap → harita."""
    rel = tables["iliski"]
    pairs = [p for p in U.PAIRS if p[0] in set(rel["cift_no"])]
    no = st.pills("Hangi soruyu soralım?", [p[0] for p in pairs], default=pairs[0][0],
                  format_func=lambda n: PAIR_QUESTIONS.get(n, str(n)), key="r_pair") or pairs[0][0]
    meta = next(p for p in U.PAIRS if p[0] == no)
    lags = sorted(set(rel.loc[rel["cift_no"] == no, "gecikme_ay"]))
    lag = lags[0]
    if len(lags) > 1:
        lag = st.pills("Kaç ay sonra?", lags, default=lags[0], format_func=lambda x: f"{x} ay sonra",
                       key=f"r_lag_{no}") or lags[0]
    d = rel[(rel["cift_no"] == no) & (rel["gecikme_ay"] == lag)]
    c = d["kontrol_etiketi"].value_counts()
    yes, rev, none = int(c.get("beklenen_yonde", 0)), int(c.get("ters_yonde", 0)), int(c.get("anlamsiz", 0))
    answer(f"81 ilin <span class='ok'>{yes}</span>'inde evet, <span class='ember'>{rev}</span>'inde tam tersi.",
           f"{none} ilde henüz net bir ilişki yok. Fizik: “{html.escape(meta[6])}”. "
           "Bu bir ilişki, kanıtlanmış bir neden değil.")
    st.plotly_chart(relation_map(d, geojson), width="stretch", config=PLOT_CFG)
    st.markdown('<div class="td-legend"><span><i style="background:#3ddc97"></i>fiziğin beklediği gibi</span>'
                '<span><i style="background:#ff8a3d"></i>tam tersi · incelenmeli</span>'
                '<span><i style="background:#2b3552"></i>net ilişki yok</span></div>', unsafe_allow_html=True)
    rv = d[d["kontrol_etiketi"] == "ters_yonde"]
    if len(rv):
        st.markdown('<div class="td-callout"><b>En ilginç yerler:</b> '
                    + ", ".join(html.escape(x) for x in rv["il"])
                    + ". Fiziğin tersi bir sonuç ya veri sorununa ya da sulama, baraj gibi bir insan etkisine işaret "
                      "eder. Araştırmacılar için en değerli ipuçları bunlardır.</div>", unsafe_allow_html=True)
    if academic:
        with st.expander("Araştırmacı ayrıntısı · r, p, n_etkin"):
            html_table(d[U.ILISKI_COLS].sort_values("r"))


def page_indir() -> None:
    """Araştırmacıya hazır veri paketi ve atıf; diğerlerine davet kartı."""
    if not academic:
        st.markdown('<div class="td-lock"><div class="big">🎓</div><h3>Veriyi indirmek araştırmacılar için</h3>'
                    "<p>Makale, tez ya da proje yazıyorsan; istediğin il, değişken ve mevsimi seç, tek dosyada indir, "
                    "hazır atıf metniyle kaynak göster.</p></div>", unsafe_allow_html=True)
        _, mid, _ = st.columns([1, 1, 1])
        if mid.button("Araştırmacı olarak giriş yap", type="primary", width="stretch"):
            st.session_state.pop("user", None)
            st.session_state["login_role"] = "akademisyen"
            st.rerun()
        if DB_OK:
            arts = DB.list_articles()
            if len(arts):
                st.markdown(f'<div class="td-mini-h" style="margin-top:40px">Bu veriyi kullanan çalışmalar ({len(arts)})'
                            "</div>", unsafe_allow_html=True)
                studies_list(arts)
        return

    answer("Seç, indir, makalende kullan.",
           f"Sürüm {U.VERSION} · {U.LICENSE} lisans · DOI yayında verilecek. Dosyadaki sayı ekrandakiyle birebir aynıdır.")
    il_df = tables["il"]
    variables = [v for v, *_ in U.TIER1 if v in set(il_df["degisken"])]
    st.markdown('<div class="td-step-h"><b>1</b> Değişkenleri seç</div>', unsafe_allow_html=True)
    sel_vars = st.pills("Değişkenler", variables, selection_mode="multi", default=variables[:2], format_func=vlabel,
                        key="p_vars", label_visibility="collapsed")
    st.markdown('<div class="td-step-h"><b>2</b> Mevsim ve il <span>(boş = hepsi)</span></div>', unsafe_allow_html=True)
    sel_seasons = st.pills("Mevsimler", list(U.SEASONS), selection_mode="multi", format_func=U.SEASONS.get,
                           key="p_seasons", label_visibility="collapsed")
    sel_il = st.multiselect("İller", sorted(il_df["il"].unique(), key=U.norm_name), key="p_il",
                            placeholder="Tüm iller (81)", label_visibility="collapsed")
    nc_files = [r for r in U.inventory() if r["katman"] == "L1_kup"]
    include_nc = st.checkbox("Ham aylık haritaları da ekle (L1 NetCDF)", value=False, disabled=not nc_files,
                             help=None if nc_files else "Henüz üretilmiş L1 dosyası yok.")
    st.markdown('<div class="td-step-h"><b>3</b> İndir</div>', unsafe_allow_html=True)
    rows = len(U.filter_trends(il_df, sel_vars, sel_seasons, sel_il, "il"))
    data, name = U.build_bundle(tables, sel_vars, sel_seasons, sel_il, user, include_nc, git_commit())
    a, b = st.columns([1, 2])
    sel = {"degiskenler": sel_vars or "hepsi", "mevsimler": sel_seasons or "hepsi", "iller": sel_il or "hepsi"}

    def _log() -> None:
        """İndirmeyi veri tabanına kaydeder (bağlı değilse sessizce geçer)."""
        if DB_OK:
            try:
                DB.log_download(user.get("id"), name, rows, sel)
            except Exception:  # noqa: BLE001
                pass

    a.download_button("⬇️  Paketi indir (.zip)", data, file_name=name, mime="application/zip", type="primary",
                      width="stretch", on_click=_log)
    b.markdown(f'<p class="td-note" style="margin-top:6px">{rows} satır · içinde CSV tablolar, atıf dosyası, NASA kaynak '
               "listesi ve açıklama (BENIOKU.txt)." + (" <b style='color:var(--warn)'>Şu an örnek veri.</b>" if placeholder
                                                         else "") + "</p>", unsafe_allow_html=True)

    cit = U.citation()
    st.markdown('<div class="td-step-h" style="margin-top:40px"><b>4</b> Atıf yap</div>', unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["APA", "BibTeX", "Python ile aç"])
    t1.code(cit["apa"], language=None, wrap_lines=True)
    t2.code(cit["bibtex"], language="bibtex")
    t3.code("import pandas as pd\n"
            "trend = pd.read_csv(\"trend_iller.csv\")\n"
            "trend.query(\"il == 'Erzurum' and mevsim == 'kis' and anlamli_fdr == 1\")", language="python")
    st.caption("Kullandığın NASA ürünlerine de atıf yap: "
               + " · ".join(f'{s["short_name"]} (doi:{s["doi"]})' for s in U.nasa_sources() if s["doi"]))


def page_yontem() -> None:
    """Nasıl hesaplıyoruz: dört adım ve tesadüf deneyi."""
    answer("Bir trendi görmek kolay. <span class='ember'>Tesadüf olmadığını göstermek</span> zor.",
           "Bu yüzden her sayıyı dört adımdan geçiriyoruz.")
    steps = [("🧹", "Düzenle", "Bütün uydu verileri aynı haritaya, aynı birime, yalnız Türkiye'ye getirilir."),
             ("🗓️", "Mevsimi ayıkla", "“Yazın sıcak, kışın soğuk” döngüsü çıkarılır; geriye yıldan yıla değişim kalır."),
             ("📈", "Trendi ölç", "25 yılda her 10 yılda ne kadar değiştiği ve bunun güven aralığı hesaplanır."),
             ("🎲", "Tesadüfü ayıkla", "Binlerce yer test edilince bazıları şans eseri “değişmiş” görünür; bunlar elenir.")]
    tiles = "".join(f'<div class="td-tile"><div class="t-ico">{i}</div><div class="t-name">{t}</div>'
                    f'<div class="t-note" style="font-size:15px">{b}</div></div>' for i, t, b in steps)
    st.markdown(f'<div class="td-grid">{tiles}</div>', unsafe_allow_html=True)

    section("KENDİN DENE", "Hiç değişmeyen 20 seri. Kaçı “değişmiş” görünecek?",
            "Aşağıdaki çizgiler tamamen rastgele; hiçbirinde gerçek bir eğilim yok. Yine de bazıları istatistik testinde "
            "“anlamlı” çıkar. Haritada 1.300 yer olunca bu tesadüfler 65'e çıkar. Biz bunları ayıklıyoruz.")
    if "noise_seed" not in st.session_state:
        st.session_state.noise_seed = 2026
    if st.button("🎲  Yeniden üret"):
        st.session_state.noise_seed += 1
    fig, hits = noise_experiment(seed=st.session_state.noise_seed)
    answer(f"<span class='ember'>{hits}</span> tanesi “değişmiş” göründü.", "Beklenen yaklaşık 1. Turuncular tesadüf.")
    st.plotly_chart(fig, width="stretch", config=PLOT_CFG)
    if academic:
        with st.expander("Araştırmacı ayrıntısı · yöntem ve formüller"):
            st.markdown("- Trend: Sen eğimi (birim / 10 yıl), `scipy.stats.theilslopes`\n"
                        "- Anlamlılık: Hamed-Rao düzeltmeli Mann-Kendall, p < 0,05; kontrol: TFPW-MK ve n_etkin − 2 sd'li "
                        "t-testi. Farklı sonuç → `belirsiz = 1`\n"
                        "- Çoklu test: Benjamini-Hochberg, α_FDR = 0,10 (Wilks, 2016), yalnız Türkiye kara hücreleri\n"
                        "- Güven aralığı: Sen aralığının yarı genişlikleri √(n / n_etkin) ile genişletilir\n"
                        "- Gereken yıl: Weatherhead ve ark. (1998), yıllık seri için √12 çarpanıyla\n"
                        "- İlişkiler: trendi çıkarılmış anomaliler, Bretherton ve ark. (1999) n_etkin")
            a, b = st.columns(2)
            a.latex(r"n_{etkin} = n\,\frac{1-r_1}{1+r_1}")
            b.latex(r"n^{*} = \left[\frac{3.3\,\sqrt{12}\,\sigma}{|\omega|}\sqrt{\frac{1+\phi}{1-\phi}}\right]^{2/3}")


STATUS = {"yayimlandi": ("Yayımlandı", "ok"), "degerlendirmede": ("Değerlendirmede", "warn"),
          "hazirlaniyor": ("Hazırlanıyor", "info")}


def studies_list(df: pd.DataFrame, mine: bool = False) -> None:
    """Makale kartları; `mine` ise her kartın altında silme düğmesi."""
    for _, r in df.iterrows():
        lab, cls = STATUS.get(r["durum"], (r["durum"], "info"))
        tags = " ".join(f'<span class="td-tag">{html.escape(vlabel(v))}</span>'
                        for v in str(r["degiskenler"] or "").split(",") if v)
        place = f' · {html.escape(r["iller"])}' if r["iller"] else ""
        doi = (f' · <a href="https://doi.org/{html.escape(r["doi"])}" target="_blank">doi:{html.escape(r["doi"])}</a>'
               if r["doi"] else "")
        journal = f' · <i>{html.escape(r["dergi"])}</i>' if r["dergi"] else ""
        example = ' <span class="td-badge warn">örnek kayıt</span>' if r["ornek"] else ""
        year = int(r["yil"]) if r["yil"] is not None else ""
        abstract = f'<p>{html.escape(r["ozet"])}</p>' if r["ozet"] else ""
        st.markdown(f'<div class="td-paper"><div class="p-top"><span class="td-badge {cls}">{lab}</span>{example}'
                    f'<span class="p-year">{year}</span></div><h4>{html.escape(r["baslik"])}</h4>'
                    f'<div class="p-meta">{html.escape(r["yazarlar"])}{journal}{doi}</div>'
                    f'<div class="p-meta">Ekleyen: {html.escape(r["ekleyen"])} · {html.escape(r["kurum"] or "")}'
                    f' · veri {html.escape(r["veri_surumu"] or "")}{place}</div>{abstract}<div>{tags}</div></div>',
                    unsafe_allow_html=True)
        if mine and st.button("🗑️  Sil", key=f"del_{r['id']}"):
            DB.delete_article(user["id"], int(r["id"]))
            st.toast("Makale silindi.")
            st.rerun()


def page_makale() -> None:
    """Araştırmacının makaleleri: ekle, listele, sil; altta tüm çalışmalar."""
    if not DB_OK or not user.get("id"):
        st.markdown('<div class="td-lock"><div class="big">🗄️</div><h3>Makale eklemek için veri tabanı gerekli</h3>'
                    "<p>SQL Server bağlı değil ya da demo girişiyle girdin. Kurulum: <code>python app/db/kur.py</code>, "
                    "sonra araştırmacı hesabınla giriş yap.</p></div>", unsafe_allow_html=True)
        return
    mine = DB.list_articles(user["id"])
    answer(f"Bu veriyi kullanan <span class='ember'>{len(mine)} çalışman</span> var.",
           "Makaleni, tezini ya da projeni ekle; “bu veriyi kullanan çalışmalar” listesinde görünsün.")
    with st.expander("➕  Yeni makale ekle", expanded=mine.empty):
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
                         format_func=vlabel, key="m_vars")
        ils = st.multiselect("İller (varsa)", sorted(tables["il"]["il"].unique(), key=U.norm_name), key="m_ils",
                             placeholder="Türkiye geneli")
        abstract = st.text_area("Kısa özet", key="m_abs", height=90)
        if st.button("Makaleyi ekle", type="primary", key="m_add"):
            art = {"baslik": title, "yazarlar": authors, "dergi": journal, "yil": int(year), "doi": doi,
                   "ozet": abstract, "degiskenler": ",".join(vars_ or []), "iller": ",".join(ils), "durum": stat}
            errs = DB.validate_article(art)
            for e in errs:
                st.error(e)
            if not errs:
                DB.add_article(user["id"], art)
                for k in ("m_title", "m_auth", "m_journal", "m_doi", "m_abs", "m_vars", "m_ils"):
                    st.session_state.pop(k, None)
                st.toast("Makale eklendi.")
                st.rerun()
    if len(mine):
        st.markdown('<div class="td-mini-h">Benim çalışmalarım</div>', unsafe_allow_html=True)
        studies_list(mine, mine=True)
    others = DB.list_articles()
    others = others[~others["id"].isin(mine["id"])]
    if len(others):
        st.markdown(f'<div class="td-mini-h">Bu veriyi kullanan diğer çalışmalar ({len(others)})</div>',
                    unsafe_allow_html=True)
        studies_list(others)


PAGE_FUNCS = {"kesfet": page_kesfet, "il": page_il, "iliski": page_iliski, "indir": page_indir,
              "makale": page_makale, "yontem": page_yontem}


# ================================================================ giriş ekranı
ROLE_TABS = {"vatandas": "🌍  Vatandaş", "akademisyen": "🎓  Akademisyen"}


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
    st.markdown(f'<div class="td-card-h">Tekrar hoş geldin</div><div class="td-card-s">'
                f'{"Vatandaş" if role == "vatandas" else "Akademisyen"} hesabınla giriş yap.</div>', unsafe_allow_html=True)
    email = st.text_input("E-posta", key="l_email", placeholder="ornek@eposta.com")
    pw = st.text_input("Şifre", type="password", key="l_pw", placeholder="••••••••")
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
                    st.toast(f"{auth.ROLES[u['rol']]['ad']} hesabıyla giriş yapıldı.")
                _login(u)
    _links(("Şifremi unuttum", "sifre"), ("Yeni üye ol", "kayit"))
    if role == "vatandas":
        st.markdown('<div class="td-or"><span>ya da</span></div>', unsafe_allow_html=True)
        if st.button("Üye olmadan devam et", width="stretch", key="go_guest"):
            _login(auth.make_user("vatandas", "Ziyaretçi"))


def card_signup(role: str) -> None:
    """Yeni üye formu; akademisyende kurum ve ORCID de istenir."""
    st.markdown(f'<div class="td-card-h">Yeni üye ol</div><div class="td-card-s">'
                f'{"Haritaları kaydet, ilini takip et." if role == "vatandas" else "Veri indir, makaleni ekle, atıf yap."}'
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
        st.markdown(f'<div class="td-card-s">Bu e-posta kayıtlıysa <b>{html.escape(target)}</b> adresine bir kod '
                    f"gönderildi. Kod {DB.RESET_MINUTES} dakika geçerli.</div>", unsafe_allow_html=True)
        demo = st.session_state.get("reset_demo_code")
        if demo:
            st.markdown(f'<div class="td-demo-code">DEMO · e-posta sunucusu ayarlı değil, kod burada gösteriliyor: '
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
    """Tam ekran, kaymayan giriş: arkada dönen Dünya, solda tanıtım, sağda giriş kartı."""
    with st.container(key="herobg"):
        render_hero(build_config(U.YAYIN_BBOX, "2001–2025", U.VERSION, placeholder, mode="bg"))
    with st.container(key="login"):
        left, right = st.columns([1.1, 1], gap="large", vertical_alignment="center")
        left.markdown(
            '<div class="td-login-h">NASA verisi, <span style="color:var(--ice)">Türkiye</span> için analize '
            '<span style="color:var(--ember)">hazır.</span></div>'
            '<p class="td-login-p">25 yıllık uydu verisi, 81 il, tesadüflerden ayıklanmış trendler. Merak eden haritaya '
            "bakar; araştırmacı indirir, makalesinde atıf yapar.</p>"
            '<div class="td-login-feats"><div><b>🛰️ NASA</b><span>MODIS · GPM · GRACE · MERRA-2</span></div>'
            "<div><b>🗺️ 81 il</b><span>2001–2025, aylık</span></div>"
            "<div><b>🎓 Atıf</b><span>sürümlü, DOI'li</span></div></div>"
            + ('<div class="td-login-ph">⚠ Şu an örnek veri gösteriliyor</div>' if placeholder else ""),
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


def top_bar() -> None:
    """Giriş sonrası üst çubuk: marka, veri durumu, kullanıcı, çıkış."""
    u = user
    who = (f'🎓 <b>{html.escape(u["ad"])}</b><span class="meta">{html.escape(u.get("kurum") or "Akademisyen")}</span>'
           if academic else f'🌍 <b>{html.escape(u["ad"])}</b><span class="meta">Vatandaş</span>')
    ph = ('<span class="td-chip warn" title="Trend tabloları henüz üretilmedi; gelince site gerçek veriye geçer.">'
          "⚠ ÖRNEK VERİ</span>") if placeholder else ""
    src = ('<span class="td-chip ok">🗄️ MS SQL</span>' if tables.get("kaynak_turu") == "mssql"
           else '<span class="td-chip">📁 dosya</span>')
    a, b = st.columns([6, 1], vertical_alignment="center")
    a.markdown(f'<div class="td-topbar"><span class="brand">🛰️ TREND DEDEKTİFİ</span>{ph}{src}'
               f'<span class="who">{who}</span></div>', unsafe_allow_html=True)
    if b.button("Çıkış", width="stretch", key="logout"):
        for k in ("user", "page", "auth_mode"):
            st.session_state.pop(k, None)
        st.rerun()


# ================================================================ içerik
if not user:
    login_screen()
    st.stop()

with st.container(key="content"):
    top_bar()
    pages = auth.pages_for(user)
    st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)
    page = st.segmented_control("Sayfa", pages, default=pages[0], key="page",
                                format_func=lambda k: auth.PAGES[k] + (" 🔒" if k == "indir" and not academic else ""),
                                label_visibility="collapsed") or pages[0]
    PAGE_FUNCS[page]()
    footer()
