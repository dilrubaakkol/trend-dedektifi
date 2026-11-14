"""Arayüz yardımcılarının testleri (Kişi 5). Gerçek veri gerektirmez."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

from charts import noise_experiment  # noqa: E402
from formatting import _fallback  # noqa: E402
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
    cfg = build_config("kar_isinma", (38.0, 37.5, 44.0, 41.5), "2001–2025", True)
    assert cfg["target"] == {"lat": 39.5, "lon": 41.0}
    assert cfg["status_label"] == "YER TUTUCU SONUÇ"


def test_noise_experiment_false_alarm_rate_is_about_five_percent():
    """Trendsiz gürültüde 'anlamlı' oranı ~%5 olmalı (2000 seri üzerinden geniş bir bantla)."""
    _, hits = noise_experiment(n_series=2000, seed=1)
    assert 0.03 <= hits / 2000 <= 0.07
