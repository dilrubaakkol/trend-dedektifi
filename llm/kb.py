"""Bilgi tabanı (kb/) okuyucusu: süreç kartları, değişken kartları ve yer kartları.

Kartlar YAML'dır ve küçük (onlarca) olduğu için vektör veritabanı gerekmez: LLM'e kart
listesinin özeti verilir, yedek eşleştirme ise anahtar kelimeyle yapılır.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

KB_DIR = Path(__file__).resolve().parent.parent / "kb"


def tr_lower(text: str) -> str:
    """Türkçe'ye uygun küçük harf: 'İ'->'i', 'I'->'ı' (Python'un lower()'ı bunu yanlış yapar)."""
    return text.replace("İ", "i").replace("I", "ı").lower()


def _starts_word(name: str, text: str) -> bool:
    """`name`, metinde bir kelimenin BAŞINDA geçiyor mu? ("Konya'da" eşleşir, "olmuş" ≠ "Muş")."""
    return re.search(r"(?<![0-9a-zçğıöşü])" + re.escape(name), text) is not None


@dataclass
class KnowledgeBase:
    cards: dict[str, dict] = field(default_factory=dict)
    variables: dict[str, dict] = field(default_factory=dict)
    places: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ yükleme
    @classmethod
    def load(cls, kb_dir: Path | str = KB_DIR) -> "KnowledgeBase":
        """kb/ klasöründeki tüm kartları okur."""
        kb_dir = Path(kb_dir)
        cards = {}
        for f in sorted((kb_dir / "cards").glob("*.yaml")):
            c = yaml.safe_load(f.read_text(encoding="utf-8"))
            cards[c["id"]] = c
        variables = {v["ad"]: v for v in
                     yaml.safe_load((kb_dir / "degiskenler.yaml").read_text(encoding="utf-8"))}
        places = yaml.safe_load((kb_dir / "yerler.yaml").read_text(encoding="utf-8"))
        return cls(cards, variables, places)

    # ------------------------------------------------------------------ yerler
    def resolve_place(self, text: str, available: set[str] | None = None) -> dict:
        """Metindeki yer adını analiz bölgesine çevirir.

        Sıra: özel bölge (ör. Konya Ovası) -> il -> coğrafi bölge adı.
        available: veri hattında gerçekten bulunan bölge kimlikleri (data/regions.py). Verilirse
        önerilen bölge orada yoksa `missing=True` döner, böylece arayüz kullanıcıya söyler.
        Dönen: {"region": id|None, "matched": "metindeki ad", "via": "ozel|il|bolge", "missing": bool}
        """
        q = tr_lower(text)
        hit = None
        for rid, r in self.places.get("ozel", {}).items():
            if any(_starts_word(tr_lower(a), q) for a in r["takma_adlar"]):
                hit = {"region": rid, "matched": r["ad"], "via": "ozel"}
                break
        if hit is None:
            # Uzun adlar önce: "Kahramanmaraş" "Maraş"tan önce denenir.
            pairs = [(il, rid) for rid, iller in self.places["iller"].items() for il in iller]
            for il, rid in sorted(pairs, key=lambda p: -len(p[0])):
                if _starts_word(tr_lower(il), q):
                    special = self.places.get("il_ozel", {}).get(il)
                    if special and (available is None or special in available):
                        rid = special
                    hit = {"region": rid, "matched": il, "via": "il"}
                    break
        if hit is None:
            for rid, r in self.places["bolgeler"].items():
                if any(_starts_word(tr_lower(a), q) for a in r["takma_adlar"]):
                    hit = {"region": rid, "matched": r["ad"], "via": "bolge"}
                    break
        if hit is None:
            return {"region": None, "matched": None, "via": None, "missing": False}
        hit["missing"] = available is not None and hit["region"] not in available
        return hit

    def region_name(self, region_id: str) -> str:
        """Bölge kimliğinin okunur adı."""
        for group in ("ozel", "bolgeler"):
            if region_id in self.places.get(group, {}):
                return self.places[group][region_id]["ad"]
        return region_id

    # ------------------------------------------------------------------ eşleştirme (yedek)
    def _strip_places(self, q: str) -> str:
        """Yer adlarını sorudan çıkarır: "Karadeniz" içindeki "kar" kar kartını tetiklemesin."""
        names = [a for g in ("ozel", "bolgeler") for r in self.places.get(g, {}).values()
                 for a in r["takma_adlar"]]
        names += [il for iller in self.places["iller"].values() for il in iller]
        for n in sorted((tr_lower(x) for x in names), key=len, reverse=True):
            q = re.sub(r"(?<![0-9a-zçğıöşü])" + re.escape(n) + r"[\w']*", " ", q)
        return q

    def match_card(self, text: str) -> str | None:
        """Anahtar kelimeyle en uygun süreç kartı (LLM yokken/başarısızken yedek).

        Puan = eşleşen kalıp sayısı; beraberlikte soruda İLK geçen konu kazanır
        ("Doğu Anadolu'da kar ... ısınmayla tutarlı mı?" -> kar kartı)."""
        q = self._strip_places(tr_lower(text))
        best, best_key = None, (0, 0)
        for cid, c in self.cards.items():
            pos = [m.start() for k in c.get("soru_kaliplari", [])
                   for m in [re.search(r"(?<![0-9a-zçğıöşü])" + re.escape(tr_lower(k)), q)] if m]
            if pos:
                key = (len(pos), -min(pos))
                if key > best_key:
                    best, best_key = cid, key
        return best

    def match_variable(self, text: str) -> str | None:
        """Anahtar kelimeyle değişken (kartsız, tek değişkenli sorular için)."""
        q = self._strip_places(tr_lower(text))
        best, score = None, 0
        for ad, v in self.variables.items():
            s = sum(len(k) for k in v.get("anahtar_kelimeler", []) if tr_lower(k) in q)
            if s > score:
                best, score = ad, s
        return best

    # ------------------------------------------------------------------ LLM için özet
    def catalog_for_prompt(self) -> str:
        """Planlayıcı LLM'e verilen kısa katalog: kart ve değişken kimlikleri + açıklamaları."""
        lines = ["SÜREÇ KARTLARI (card_id: başlık — örnek soru):"]
        for cid, c in self.cards.items():
            ex = (c.get("ornek_sorular") or [""])[0]
            lines.append(f"- {cid}: {c['baslik']} — örn. \"{ex}\"")
        lines.append("\nDEĞİŞKENLER (degisken: başlık):")
        for ad, v in self.variables.items():
            if ad != "rakim":
                lines.append(f"- {ad}: {v['baslik']}")
        return "\n".join(lines)
