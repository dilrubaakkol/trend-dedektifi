"""results.json ve süreç kartlarını okuyan, arayüzün ihtiyaç duyduğu biçime getiren yardımcılar.

Arayüz hiçbir sayı üretmez; buradaki her değer `results.json` dosyasından gelir.
Sözleşme: docs/sozlesmeler.md (Kişi 2, 3 → Kişi 4, 5).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_RESULTS = ROOT / "examples" / "results_example.json"
RESULTS_DIR = ROOT / "cache" / "results"
CARDS_DIR = ROOT / "kb" / "cards"

# Sözleşmedeki etiketler ASCII; rehberde Türkçe karakterli yazım da geçiyor, ikisini de kabul et.
LABELS = {
    "uyumlu": ("Uyumlu", "ok"),
    "celiskili": ("Çelişkili", "bad"),
    "çelişkili": ("Çelişkili", "bad"),
    "yetersiz": ("Yetersiz", "warn"),
    None: ("Bilgi", "info"),
    "bilgi": ("Bilgi", "info"),
}


def list_result_files() -> list[Path]:
    """`cache/results/` altındaki gerçek sonuç dosyalarını yeniden eskiye sıralı döndürür."""
    if not RESULTS_DIR.exists():
        return []
    return sorted(RESULTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def is_placeholder(results: dict) -> bool:
    """Sonuç dosyası yer tutucu olarak işaretlenmişse True döner (`_not` alanı ya da örnek dosya)."""
    note = str(results.get("_not", "")).lower()
    return "yer tutucu" in note or "yer tutucudur" in note or bool(results.get("_placeholder"))


def load_results(region: str | None = None) -> tuple[dict, Path]:
    """Bölge için en güncel sonucu yükler; yoksa örnek (yer tutucu) dosyaya düşer.

    Dönüş: (sonuç sözlüğü, okunan dosyanın yolu).
    """
    for path in list_result_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        if region is None or data.get("region", {}).get("name") == region:
            return data, path
    data = json.loads(EXAMPLE_RESULTS.read_text(encoding="utf-8"))
    return data, EXAMPLE_RESULTS


def load_card(card_id: str | None) -> dict | None:
    """`kb/cards/<card_id>.yaml` kartını okur; bulamazsa id alanı eşleşen ilk kartı dener."""
    if not card_id or not CARDS_DIR.exists():
        return None
    direct = CARDS_DIR / f"{card_id}.yaml"
    candidates = [direct] if direct.exists() else sorted(CARDS_DIR.glob("*.yaml"))
    for path in candidates:
        card = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if card.get("id") == card_id:
            return card
    return None


def ci_of(analysis: dict) -> list[float] | None:
    """Güven aralığını döndürür. Örnek dosyada `ci95`, rehberde `ci95_widened` geçiyor; ikisini de okur."""
    return analysis.get("ci95_widened") or analysis.get("ci95")


def label_of(analysis: dict) -> tuple[str, str]:
    """Analizin etiketini (görünen ad, renk sınıfı) olarak döndürür; etiketsiz satır "Bilgi" olur."""
    raw = analysis.get("label")
    key = raw.lower() if isinstance(raw, str) else None
    return LABELS.get(key, (str(raw), "info"))


def by_type(results: dict, *types: str) -> list[dict]:
    """Belirtilen türdeki analizleri sırasıyla döndürür."""
    return [a for a in results.get("analyses", []) if a.get("type") in types]


def period_label(results: dict) -> str:
    """Dönemi "2001–2025" biçiminde verir (`donem` alanı varsa onu, yoksa `period` yıllarını kullanır)."""
    if results.get("donem"):
        return str(results["donem"])
    period = results.get("period") or []
    if len(period) == 2:
        return f"{str(period[0])[:4]}–{str(period[1])[:4]}"
    return "—"
