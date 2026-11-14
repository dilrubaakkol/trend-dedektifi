# Trend Dedektifi

NASA Space Apps Challenge 2026 — *Be An Earth System Trend Detective!*

NASA uydu ve model verilerindeki değişimlerin yalnızca ne olduğunu değil, olası nedenleriyle
tutarlı olup olmadığını da sınayan açık kaynaklı bir "veri dedektifi" aracı.

## Klasör yapısı ve sorumlular

| Klasör | Sorumlu | İçerik |
| --- | --- | --- |
| `data/` | Kişi 1 — Veri | NASA verisini indirme, kesme, aylık ortak ızgaraya getirme |
| `stats/` | Kişi 2 — İstatistik | Mevsimsellik, t-testi, düzeltilmiş Mann-Kendall, Sen, FDR, regresyon |
| `physics/` | Kişi 3 — Mekân/Fizik | Sınır bulma, sınır kayması, fiziksel testler, ayna bölgeler |
| `kb/cards/`, `llm/` | Kişi 4 — KB/LLM | Süreç kartları, soru → plan, açıklama, sayı doğrulayıcı |
| `app/`, `validation/` | Kişi 5 — Arayüz/Doğrulama | Streamlit arayüzü, istasyon karşılaştırması, sunum |
| `tests/` | Herkes | Sentetik veriyle testler |
| `examples/` | Herkes | Ortak dosya biçimlerinin örnekleri |
| `docs/` | Herkes | Veri ve sonuç sözleşmeleri |

Ortak dosya biçimleri: [`docs/sozlesmeler.md`](docs/sozlesmeler.md). Bu biçimler ekip onayı olmadan değiştirilmez.

## Kurulum

```bash
git clone https://github.com/<KULLANICI>/trend-dedektifi.git
cd trend-dedektifi
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

NASA verisi için Earthdata hesabı gerekir: <https://urs.earthdata.nasa.gov>.
Profil → Applications → Authorized Apps altında **NASA GESDISC DATA ARCHIVE** uygulamasını onaylayın.
Şifre bilgisayarınızdaki `.netrc` (Windows'ta `_netrc`) dosyasında durur; **repoya asla eklenmez.**

## Git çalışma kuralları

1. `main` her zaman çalışır durumda kalır; doğrudan `main`'e push yapılmaz.
2. Herkes kendi dalında çalışır: `kisi1-veri`, `kisi2-istatistik`, `kisi3-fizik`, `kisi4-llm`, `kisi5-arayuz`.
3. Başlamadan önce: `git checkout main && git pull`, sonra `git checkout kisiN-... && git merge main`.
4. İş bitince: `git push`, GitHub'da Pull Request açın, bir arkadaşınız bakıp birleştirsin.
5. İndirilen veri (`cache/`, `*.nc`, `*.hdf`) git'e girmez; `.gitignore` bunu sağlar.
6. Her 4 saatte bir ekip toplantısında PR'lar birleştirilir.
