"""Arayüz yardımcılarının testleri (Kişi 5). Gerçek veri gerektirmez."""

import codecs
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

from charts import noise_experiment  # noqa: E402
from formatting import _fallback  # noqa: E402
import auth  # noqa: E402
import urun_io as U  # noqa: E402
from hero import build_config  # noqa: E402
from results_io import ci_of, is_placeholder, label_of, load_card, load_results, period_label  # noqa: E402


def test_fallback_formatter_turkish_style():
    assert _fallback(-2.1) == "−2,1"
    assert _fallback(1234.5) == "1.234,5"
    assert _fallback(0.003, digits=3) == "0,003"
    assert _fallback([40, 95], "m", digits=0) == "40 … 95 m"
    assert _fallback(None) == "—"


def test_example_results_are_flagged_placeholder():
    results, path = load_results("dogu_anadolu")
    assert path.name == "results_example.json" or not is_placeholder(results)
    if path.name == "results_example.json":
        assert is_placeholder(results)


def test_ci_reads_both_field_names():
    assert ci_of({"ci95": [1, 2]}) == [1, 2]
    assert ci_of({"ci95_widened": [3, 4], "ci95": [1, 2]}) == [3, 4]
    assert ci_of({}) is None


def test_labels_accept_ascii_and_turkish():
    assert label_of({"label": "celiskili"})[1] == "bad"
    assert label_of({"label": "çelişkili"})[1] == "bad"
    assert label_of({"label": "uyumlu"})[1] == "ok"
    assert label_of({})[0] == "Bilgi"


def test_period_label():
    assert period_label({"donem": "2001–2025"}) == "2001–2025"
    assert period_label({"period": ["2001-01", "2025-12"]}) == "2001–2025"


def test_card_loads():
    card = load_card("kar_isinma")
    assert card and card["belirti"][0]["degisken"] == "kar_ortusu"


def test_hero_config_centers_on_bbox():
    cfg = build_config((25.5, 35.5, 45.0, 42.5), "2001–2025", "v0.1", True)
    assert cfg["target"] == {"lat": 39.0, "lon": 35.25}
    assert cfg["status_label"] == "YER TUTUCU VERİ"
    assert cfg["buttons"][0]["target"] == "giris"
    assert build_config((25.5, 35.5, 45.0, 42.5), "2001–2025", "v0.1", False, True)["buttons"][0]["target"] == "panel"


def test_noise_experiment_false_alarm_rate_is_about_five_percent():
    """Trendsiz gürültüde 'anlamlı' oranı ~%5 olmalı (2000 seri üzerinden geniş bir bantla)."""
    _, hits = noise_experiment(n_series=2000, seed=1)
    assert 0.03 <= hits / 2000 <= 0.07


# ---------------------------------------------------------------- giriş
def test_login_validation():
    assert auth.validate("vatandas", "Ayşe") == []
    assert auth.validate("vatandas", "") != []
    assert auth.validate("akademisyen", "Dr. A", "a@uni.edu.tr", "Atatürk Ü.") == []
    assert auth.validate("akademisyen", "Dr. A", "yanlis", "Atatürk Ü.") != []
    assert auth.validate("akademisyen", "Dr. A", "a@uni.edu.tr", "X Ü.", orcid="123") != []
    assert auth.validate("akademisyen", "Dr. A", "a@uni.edu.tr", "X Ü.", orcid="0000-0002-1825-009X") == []


def test_academic_email_and_pages():
    assert auth.is_academic_email("a@atauni.edu.tr") and not auth.is_academic_email("a@gmail.com")
    user = auth.make_user("akademisyen", " Dr. A ", "a@gmail.com", "Kurum")
    assert user["ad"] == "Dr. A" and user["kurum_eposta"] is False
    assert "indir" in auth.pages_for(user) and auth.is_academic(user) and not auth.is_academic({"rol": "vatandas"})


# ---------------------------------------------------------------- veri seti
def test_bh_fdr():
    p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
    assert U.bh_fdr(p, alpha=0.05).tolist() == [True, True] + [False] * 8
    assert U.bh_fdr([float("nan"), 0.0001]).tolist() == [False, True]


def test_control_label():
    assert U.control_label(-0.5, "negatif", 1) == "beklenen_yonde"
    assert U.control_label(0.5, "negatif", 1) == "ters_yonde"
    assert U.control_label(0.9, "pozitif", 0) == "anlamsiz"


def test_provinces_have_regions():
    il = U.provinces()
    assert len(il) == 81 and il["bolge"].ne("").all()


def test_synthetic_tables_follow_columns():
    il, bolge, rel = U.synthetic_tables()
    assert list(il.columns) == U.TREND_COLS
    assert list(rel.columns) == U.CIFTLER_COLS
    assert set(il["mevsim"]) == set(U.SEASONS) and il["plaka"].nunique() == 81
    assert "turkiye" in set(bolge["bolge"])
    assert set(rel["etiket"]) <= set(U.CONTROL_LABELS) | {""}
    assert set(rel["beklenen_yon"]) <= {"+", "-"} and set(rel["bolge_turu"]) == {"il", "bolge", "turkiye"}
    assert (il["ci_alt"] <= il["egim_10yil"]).all() and (il["egim_10yil"] <= il["ci_ust"]).all()


def test_bundle_marks_placeholder():
    import io
    import zipfile
    tables = {**dict(zip(("il", "bolge", "iliski"), U.synthetic_tables())), "yer_tutucu": True,
              "kaynak": {"trend_iller.csv": None}}
    data, name = U.build_bundle(tables, ["sicaklik_2m"], ["kis"], ["Erzurum"], {"rol": "akademisyen"})
    assert name.startswith("YER_TUTUCU_")
    z = zipfile.ZipFile(io.BytesIO(data))
    assert "YER_TUTUCU_trend_iller.csv" in z.namelist() and "CITATION.bib" in z.namelist()
    pairs = z.read("YER_TUTUCU_ciftler.csv")
    assert pairs.startswith(codecs.BOM_UTF8)  # BOM'lu UTF-8, sözleşmedeki dosya gibi
    import pandas as pd
    pdf = pd.read_csv(io.BytesIO(pairs), encoding="utf-8-sig", dtype={"bolge_kodu": str})
    assert set(pdf.loc[pdf["bolge_turu"] == "il", "bolge_adi"]) == {"Erzurum"}
    assert {"dogu_anadolu", "turkiye"} <= set(pdf.loc[pdf["bolge_turu"] != "il", "bolge_kodu"])
    csv = z.read("YER_TUTUCU_trend_iller.csv").decode("utf-8").splitlines()
    assert csv[0].split(",") == U.TREND_COLS and all(",Erzurum," in "," + line for line in csv[1:])
    assert "SENTETİK YER TUTUCU" in z.read("BENIOKU.txt").decode("utf-8")


# ---------------------------------------------------------------- şifre ve makale
def test_password_hash_roundtrip():
    h = auth.hash_password("gizli1234")
    assert h.startswith("pbkdf2_sha256$") and "gizli1234" not in h
    assert auth.verify_password("gizli1234", h) and not auth.verify_password("yanlis123", h)
    assert not auth.verify_password("x", None) and not auth.verify_password("x", "bozuk")
    assert auth.hash_password("a1b2c3d4") != auth.hash_password("a1b2c3d4")  # her seferinde yeni tuz


def test_password_rules():
    assert auth.validate_password("abc12345", "abc12345") == []
    assert auth.validate_password("kisa1") != []
    assert auth.validate_password("sadeceharf") != []
    assert auth.validate_password("abc12345", "abc12346") != []


def test_article_validation():
    import veritabani as DB
    ok = {"baslik": "Kar örtüsünde değişim", "yazarlar": "Kaya, E.", "yil": 2026, "doi": "10.1234/abc"}
    assert DB.validate_article(ok) == []
    assert DB.validate_article({**ok, "doi": "abc"}) != []
    assert DB.validate_article({**ok, "baslik": ""}) != []


def test_mssql_roundtrip_in_temporary_database():
    """Yerel SQL Server varsa geçici bir veri tabanında kayıt, giriş, makale ve tablo yazma/okuma sınanır."""
    import pytest
    import veritabani as DB
    try:
        with DB.connect(database="master", autocommit=True):
            pass
    except Exception:  # noqa: BLE001
        pytest.skip("SQL Server yok")
    sys.path.insert(0, str(ROOT / "app" / "db"))
    import kur
    name, old = "TrendDedektifi_test", DB.DB_NAME
    DB.DB_NAME = name
    try:
        kur.run_schema()
        u = DB.register("Test Kişi", "test@ornek.edu.tr", "Test Ü.", "", "test12345")
        assert u["id"] and u["kurum_eposta"] and DB.authenticate("test@ornek.edu.tr", "test12345")["id"] == u["id"]
        assert DB.authenticate("test@ornek.edu.tr", "yanlis123") is None
        code, _ = DB.request_reset("test@ornek.edu.tr")
        assert DB.request_reset("yok@ornek.edu.tr") is None
        assert not DB.reset_password("test@ornek.edu.tr", "000000" if code != "000000" else "111111", "yeni12345")
        assert DB.reset_password("test@ornek.edu.tr", code, "yeni12345")
        assert not DB.reset_password("test@ornek.edu.tr", code, "baska1234")  # kod tek kullanımlık
        assert DB.authenticate("test@ornek.edu.tr", "yeni12345") and not DB.authenticate("test@ornek.edu.tr", "test12345")
        v = DB.register("Vatandaş K.", "v@ornek.com", "Kurum yazılmaz", "", "abc12345", role="vatandas")
        assert v["rol"] == "vatandas" and v["kurum"] is None
        aid = DB.add_article(u["id"], {"baslik": "Deneme makalesi", "yazarlar": "Kişi, T.", "yil": 2026})
        assert len(DB.list_articles(u["id"])) == 1 and DB.delete_article(u["id"], aid)
        il, bolge, rel = U.synthetic_tables()
        DB.replace_tables({"il": il, "bolge": bolge, "iliski": rel, "yer_tutucu": True})
        back = DB.load_tables()
        assert back["yer_tutucu"] and len(back["il"]) == len(il) and list(back["il"].columns) == U.TREND_COLS
    finally:
        DB.DB_NAME = old
        with DB.connect(database="master", autocommit=True) as cn:
            cn.cursor().execute(f"ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{name}]")


def test_signup_validation_by_role():
    assert auth.validate_signup("vatandas", "Ayşe", "a@b.com", "abc12345", "abc12345") == []
    assert auth.validate_signup("vatandas", "Ayşe", "eposta-yok", "abc12345", "abc12345") != []
    assert auth.validate_signup("akademisyen", "Dr. A", "a@uni.edu.tr", "abc12345", "abc12345", "Ü") != []  # kurum kısa
    assert auth.validate_signup("vatandas", "Ayşe", "a@b.com", "abc12345", "abc12345", consent=False) != []


def test_hero_background_mode():
    cfg = build_config((25.5, 35.5, 45.0, 42.5), "2001–2025", "v0.1", True, mode="bg")
    assert cfg["mode"] == "bg"


# ---------------------------------------------------------------- L4 ciftler.csv (sözleşme 2.3)
def test_norm_sign_accepts_all_forms():
    assert [U.norm_sign(x) for x in ("+", "-", "−", "pozitif", "negatif")] == ["+", "-", "-", "+", "-"]
    assert U.control_label(-0.4, "−", 1) == "beklenen_yonde" and U.control_label(0.4, "-", 1) == "ters_yonde"


def test_pair4_is_region_only():
    _, _, rel = U.synthetic_tables()
    p4 = rel[rel["cift_no"] == 4]
    assert (p4["bolge_turu"] != "il").all() and len(p4) == 8  # 7 bölge + Türkiye
    assert rel.loc[rel["bolge_turu"] != "il", "p_fdr"].isna().all()  # FDR yalnız il satırlarında


def test_bh_qvalues_match_reference():
    import numpy as np
    q = U.bh_qvalues([0.01, 0.04, 0.03, 0.2])
    assert np.allclose(q, [0.04, 0.0533333, 0.0533333, 0.2], atol=1e-6)


def test_load_tables_reads_bom_ciftler(tmp_path, monkeypatch):
    """Yayın klasörüne BOM'lu ciftler.csv konunca site onu okur (yer tutucu yerine)."""
    _, _, rel = U.synthetic_tables()
    (tmp_path / "L4_iliski").mkdir()
    rel.assign(beklenen_yon=rel["beklenen_yon"].replace({"-": "−"})).to_csv(
        tmp_path / "L4_iliski" / "ciftler.csv", index=False, encoding="utf-8-sig")
    monkeypatch.setattr(U, "SEARCH_DIRS", [tmp_path])
    t = U.load_tables()
    assert t["kaynak"]["ciftler.csv"] is not None and list(t["iliski"].columns) == U.CIFTLER_COLS
    assert set(t["iliski"]["beklenen_yon"]) == {"+", "-"}  # Unicode eksi de '-' olur
    il = U.pair_rows(t["iliski"], "il")
    assert il["plaka"].min() == 1 and il["plaka"].max() == 81


# ---------------------------------------------------------------- Kişi 4 katmanı bağlantısı
def test_placeholder_package_feeds_llm_answer(tmp_path):
    """Yer tutucu paket sözleşme biçiminde yazılır ve llm.answer() onunla uçtan uca çalışır (LLM'siz şablon)."""
    from llm import answer
    pkg = U.write_placeholder_package(tmp_path / "paket")
    assert (pkg / "L4_iliski" / "ciftler.csv").exists() and (pkg / "L3_ozet" / "kar_ortusu__MOD10CM__il.csv").exists()
    out = answer("Erzurum'da kar azalıyor mu, ısınmayla ilişkili mi?", client=None, kitle="akademisyen", package=pkg)
    assert out["verified"] and out["evidence"] and not out.get("message")
    assert "/10 yıl/10 yıl" not in out["explanation"]  # birim tek kez
    assert any(e["id"].startswith("trend__kar_ortusu") for e in out["evidence"])
