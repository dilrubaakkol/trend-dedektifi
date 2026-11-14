"""Bilgi tabanı (kb/) okuyucusu: süreç kartları, değişken kartları ve yer kartları.

Kartlar YAML'dır ve küçük (onlarca) olduğu için vektör veritabanı gerekmez: LLM'e kart
listesinin özeti verilir, yedek eşleştirme ise anahtar kelimeyle yapılır.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .evidence import norm_key

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
    def _il_names(self) -> list[tuple[str, str, str]]:
        """(metinde aranacak ad, il anahtarı, bölge anahtarı) üçlüleri; takma adlar dahil."""
        out = []
        for bolge, iller in self.places["iller"].items():
            for il in iller:
                out.append((il, norm_key(il), bolge))
        resmi = {il: (k, b) for il, k, b in out}
        for kisa, tam in self.places.get("il_takma_adlari", {}).items():
            if tam in resmi:
                out.append((kisa, *resmi[tam]))
        return out

    def resolve_place(self, text: str, available: set[str] | None = None) -> dict:
        """Metindeki yer adını analiz bölgesine çevirir (anahtarlar data/regions.py ile aynı).

        Önce il (uzun adlar önce: "Kahramanmaraş" "Maraş"tan önce), sonra coğrafi bölge, sonra Türkiye.
        available: veri tarafında tanımlı bölge anahtarları; verilirse ve bölge yoksa missing=True.
        Dönen: {"region", "level" ("il"|"bolge"|"turkiye"), "bolge" (ilin bölgesi), "matched", "missing"}
        """
        q = tr_lower(text)
        hit = None
        for name, key, bolge in sorted(self._il_names(), key=lambda t: -len(t[0])):
            if _starts_word(tr_lower(name), q):
                resmi = next(n for n, k, _ in self._il_names() if k == key)
                hit = {"region": key, "level": "il", "bolge": bolge, "matched": resmi}
                break
        if hit is None:
            for key, r in self.places["bolgeler"].items():
                if any(_starts_word(tr_lower(a), q) for a in r["takma_adlar"]):
                    level = "turkiye" if key == "turkiye" else "bolge"
                    hit = {"region": key, "level": level, "bolge": None, "matched": r["ad"]}
                    break
        if hit is None:
            return {"region": None, "level": None, "bolge": None, "matched": None, "missing": False}
        hit["missing"] = available is not None and hit["region"] not in available
        return hit

    def region_name(self, region_key: str) -> str:
        """Bölge ya da il anahtarının okunur adı."""
        if region_key in self.places["bolgeler"]:
            return self.places["bolgeler"][region_key]["ad"]
        for name, key, _ in self._il_names():
            if key == region_key:
                return name
        return region_key

    # ------------------------------------------------------------------ eşleştirme (yedek)
    def _strip_places(self, q: str) -> str:
        """Yer adlarını sorudan çıkarır: "Karadeniz" içindeki "kar" kar kartını tetiklemesin."""
        names = [a for r in self.places["bolgeler"].values() for a in r["takma_adlar"]]
        names += [n for n, _, _ in self._il_names()]
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

    def number_phrases(self) -> list[str]:
        """Değişken başlıkları ve birimleri: doğrulayıcı bunlardaki rakamları sonuç saymaz."""
        out = []
        for v in self.variables.values():
            out += [str(v.get("baslik", "")), str(v.get("birim", ""))]
        return out

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
