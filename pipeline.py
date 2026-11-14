"""Uçtan uca akış: soru → plan → veri → analiz → kanıt → metin.

Her adım ilgili kişinin modülünden çağrılır. Şimdilik iskelet; modüller hazır oldukça doldurulur.
"""


def run(question: str, region: str, period: tuple[str, str] = ("2001-01", "2025-12")) -> dict:
    # 1. Kişi 4: soru → plan (kart, belirti, şüpheliler)      llm/plan.py
    # 2. Kişi 1: plan → işlenmiş NetCDF dosyaları               data/fetch.py, data/harmonize.py
    # 3. Kişi 2: trendler, FDR, regresyon                       stats/
    # 4. Kişi 3: sınır, kayma, fiziksel testler                 physics/
    # 5. Kişi 4: kanıt tablosu + doğrulanmış açıklama            llm/explain.py, llm/verify.py
    raise NotImplementedError("Modüller hazır oldukça doldurulacak.")


if __name__ == "__main__":
    print("Trend Dedektifi iskeleti hazır.")
