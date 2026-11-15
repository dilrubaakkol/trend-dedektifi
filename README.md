# Trend Dedektifi

NASA Space Apps Challenge 2026 — *Be An Earth System Trend Detective!*

Türkiye'nin 81 ili, 7 coğrafi bölgesi ve ülke geneli için NASA uydu ve model verilerindeki uzun dönemli
değişimleri **ölçen, istatistiksel olarak sınayan ve kaynağıyla birlikte sunan** açık kaynaklı bir araç.
Bir araştırmacı tek bir soruyla ("Konya'da toprak nemi azalıyor mu?") şu çıktıları alır:

- **Ne değişti, ne kadar?** Theil-Sen eğimi, genişletilmiş %95 güven aralığı, otokorelasyon düzeltmeli
  Mann-Kendall testi ve yanlış keşif oranı (FDR) düzeltmesi.
- **Nerede?** 0,25° hücre haritaları ile il ve bölge özetleri.
- **Neyle birlikte değişti?** Değişken çiftleri arasında trendi giderilmiş korelasyon. Çerçeve
  **ilişki**dir; hiçbir sonuç nedensellik iddia etmez.
- **Ne kadar güvenilir?** Her sonuç için bir bulgu karnesi: ürünler arası uyum, karıştırma (permütasyon)
  testi, dönem kırpma, sıkı eşik ve veri yeterliliği kontrolleriyle güven seviyesi (YÜKSEK / ORTA /
  DÜŞÜK / YOK); doğrulanmamış veri uyarıları.
- **Büyüklük fiziğe uyuyor mu?** Gözlenen büyüklüğün fiziğin beklediği bantla karşılaştırılması
  (Clausius-Clapeyron nem artışı, su bütçesi kapanışı, kar çizgisi kayması).
- **Makaleye hazır metin:** bulgular paragrafı (her sayı bir kanıt satırına bağlı ve doğrulanmış),
  yöntem paragrafı, NASA veri atıfları (DOI) ve yöntem kaynakçası.

Yöntemin ayrıntısı: [`docs/yontem.md`](docs/yontem.md). Dosya biçimleri: [`docs/sozlesmeler.md`](docs/sozlesmeler.md).

## Çıktı: yayın paketi

Bütün sonuçlar tek bir paket klasöründe toplanır: `outputs/trend-dedektifi-turkiye-<sürüm>/`.

| Katman | Yol | İçerik |
| --- | --- | --- |
| L1 | `L1_kup/<degisken>__<urun>.nc` | Türkiye'ye kırpılmış, 0,25° ortak ızgarada aylık veri küpleri |
| L2 | `L2_trend/<degisken>__<urun>__trend.nc` | Hücre bazında trend: eğim, GA, p, q, anlamlılık, gereken yıl (yıllık + 4 mevsim) |
| L3 | `L3_ozet/<degisken>__<urun>__{il,bolge}.csv` | 81 il, 7 bölge ve Türkiye için alan ortalaması trendi ve hücre özeti |
| L4 | `L4_iliski/ciftler.csv` | 6 değişken çifti için il/bölge/Türkiye düzeyinde ilişki tablosu ve haritalar |
| Karne | `karne/{trend_karne_il,trend_karne_bolge,iliski_karne}.csv` | Her trend ve ilişki sonucu için sağlamlık kontrolleri ve güven seviyesi (YÜKSEK / ORTA / DÜŞÜK / YOK) |
| Büyüklük | `L4_iliski/buyukluk/` | "Ne kadar" testleri: Clausius-Clapeyron, su bütçesi kapanışı, kar çizgisi kayması |

Her dosya kaynak NASA ürününün DOI'sini, ürün sürümünü, lisansı ve veri kademesini (Kademe 2 =
bağımsız doğrulaması yapılmamış girdi) taşır.

## Kurulum

```bash
git clone https://github.com/dilrubaakkol/trend-dedektifi.git
cd trend-dedektifi
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

NASA verisi için Earthdata hesabı gerekir: <https://urs.earthdata.nasa.gov>.
Profil → Applications → Authorized Apps altında **NASA GESDISC DATA ARCHIVE** uygulamasını onaylayın.
Şifre bilgisayarınızdaki `.netrc` (Windows'ta `_netrc`) dosyasında durur; **repoya asla eklenmez.**

> **Windows notu:** NetCDF kütüphanesi Türkçe karakter içeren yollara dosya yazamayabilir (ör. kullanıcı
> adı "kullanıcı"). Repoyu ve `outputs/` klasörünü yalnız ASCII karakterli bir yolda tutun. Testlerde:
> `python -m pytest tests/ --basetemp=C:/pytest_tmp`.

## Çalıştırma

### Arayüz

```bash
streamlit run app/streamlit_app.py
```

Gerçek paket yoksa arayüz **yer tutucu** (sentetik) bir paketle açılır ve bunu her ekranda belirtir.

### Paketi baştan üretmek

Sırayla (her adım bir öncekinin çıktısını okur):

```bash
python -m data.build --vars all          # 1. NASA verisini indir, Türkiye'ye kırp, ortak ızgaraya getir
python -m data.export --surum v0.1       # 2. L1 yayın küpleri
python -m stats.l2 --surum v0.1          # 3. L2 hücre trendleri ve kaynak uyumu
python -m stats.l3 --surum v0.1          # 4. L3 il ve bölge özetleri
python -m physics.run --surum v0.1       # 5. L4 değişken ilişkileri
python -m stats.karne --surum v0.1       # 6. bulgu karnesi (L3 ve L4'ü okur)
python -m physics.buyukluk --surum v0.1  # 7. büyüklük testleri
```

Tam indirme uzun sürer ve birkaç GB yer kaplar. Önce tek ürünle deneyin: `python -m data.fetch --urun GLDAS --test`.

### Yapay zekâ açıklamaları (isteğe bağlı)

"Soru sor" sayfası, bir LLM ayarlıysa soruyu yapay zekâyla yorumlar ve bulguları yapay zekâya yazdırır;
ayarlı değilse anahtar kelimeyle eşleştirir ve şablonla yazar. **İki durumda da sayılar analiz paketinden
gelir ve doğrulayıcıdan geçer;** yapay zekâ sayı üretmez. Yöntem paragrafı ve atıflar her zaman şablonla
üretilir. v0.1'de bu sayfa **yol haritası** özelliğidir (bkz. `llm/README.md`).

```bash
export LLM_PROVIDER=openai                            # ya da anthropic
export LLM_BASE_URL=https://api.groq.com/openai/v1    # OpenAI uyumlu herhangi bir servis
export LLM_MODEL=<model adı>
export LLM_API_KEY=<anahtar>                          # repoya ve koda asla yazılmaz
```

### Testler

```bash
python -m pytest tests/
```

Testler sentetik veriyle çalışır; NASA hesabı ya da internet gerektirmez.

## Belgeler

| Belge | İçerik |
| --- | --- |
| [`docs/yontem.md`](docs/yontem.md) | Veri, ön işleme, trend, anlamlılık, ilişki ve açıklama katmanının yöntemi; sınırlılıklar; kaynakça |
| [`docs/sozlesmeler.md`](docs/sozlesmeler.md) | L1–L4 dosya biçimleri (modüller arası tek bağlantı) |
| [`docs/dogrulama.md`](docs/dogrulama.md) | Giovanni karşılaştırması, L2 akıl kontrolü, bilinen veri boşlukları |
| [`docs/eksik_degiskenler.md`](docs/eksik_degiskenler.md) | Değişken kataloğunun genişletilmesi |
| [`llm/README.md`](llm/README.md) | Açıklama katmanı: planlayıcı, kanıt adaptörü, doğrulayıcı |

## Atıf

Bu veri setini ya da aracı kullanırsanız **hem bizi hem de kullandığınız NASA ürünlerini** kaynak gösterin.
GitHub'da sağ üstteki **"Cite this repository"** düğmesi [`CITATION.cff`](CITATION.cff)'ten hazır atıf verir.

**APA:**

> Akkol, D., Kocakurt, H., Yüce, S., Kaya, E., & Biçer, M. (2026). *Trend Dedektifi: Türkiye NASA iklim
> trendi veri seti* (Sürüm v0.1) [Veri seti]. https://github.com/dilrubaakkol/trend-dedektifi

**BibTeX:**

```bibtex
@misc{trend_dedektifi_2026,
  author       = {Akkol, Dilruba and Kocakurt, Halime and Y{\"u}ce, S{\"u}meyra and Kaya, Esra and Bi{\c{c}}er, Merve},
  title        = {Trend Dedektifi: T{\"u}rkiye NASA iklim trendi veri seti},
  year         = {2026},
  version      = {v0.1},
  howpublished = {\url{https://github.com/dilrubaakkol/trend-dedektifi}},
  note         = {Veri seti. DOI: (yay{\i}nda doldurulacak)}
}
```

**Veri seti DOI'si:** (yayında doldurulacak). Zenodo yayınından sonra aynı DOI üç yere yazılır:
`CITATION.cff`, [`docs/sozlesmeler.md`](docs/sozlesmeler.md) (`veri_seti_doi`) ve `data/export.py`
(`VERI_SETI_DOI`); paketteki her dosya da bu değeri `veri_seti_doi` alanında taşır.

**NASA ürünlerinin DOI'leri** her dosyanın içindedir:

| Katman | DOI nerede |
| --- | --- |
| L1, L2 (`.nc`) | `doi` niteliği (attrs) |
| L3 (`.csv`) | `doi` sütunu |
| L4 (`ciftler.csv`) | `doi_1` ve `doi_2` sütunları (çiftin iki ürünü) |
| Karne, büyüklük testleri | NASA DOI'si taşımaz; dayandıkları L1–L4 dosyasındaki DOI'yi kullanın (büyüklük dosyaları `veri_seti_doi` taşır) |

Bütün ürünlerin DOI listesi `CITATION.cff` içindeki `references` bölümündedir.

## Lisans

- Veri paketi (L1–L4, karne, büyüklük testleri): CC BY 4.0
- Kod: [MIT](LICENSE)
- Kaynak veriler NASA'ya aittir ve NASA'nın açık veri politikasıyla yayımlanır.

## Ekip ve klasörler

| Klasör | Sorumlu | İçerik |
| --- | --- | --- |
| `data/` | Dilruba Akkol (Kişi 1) — Veri | NASA verisini indirme, kesme, aylık ortak ızgaraya getirme, L1 |
| `stats/` | Halime Kocakurt (Kişi 2) — İstatistik | Mevsim serileri, düzeltilmiş Mann-Kendall, Sen, FDR, L2 ve L3 |
| `physics/` | Sümeyra Yüce (Kişi 3) — Mekân/Fizik | Değişken çiftleri ve ilişki haritaları (L4) |
| `kb/`, `llm/` | Esra Kaya (Kişi 4) — Bilgi tabanı/LLM | Süreç ve değişken kartları, soru → plan, kanıt adaptörü, açıklama, doğrulayıcı |
| `app/`, `validation/` | Merve Biçer (Kişi 5) — Arayüz/Doğrulama | Streamlit arayüzü, doğrulama, sunum |
| `tests/` | Herkes | Sentetik veriyle testler |
| `examples/` | Herkes | Örnek betikler ve dosyalar |
| `docs/` | Herkes | Yöntem, sözleşmeler, doğrulama |

### Git çalışma kuralları

1. `main` her zaman çalışır durumda kalır; doğrudan `main`'e push yapılmaz.
2. Herkes kendi dalında çalışır ve Pull Request açar; bir arkadaşı bakıp birleştirir.
3. Başlamadan önce: `git checkout main && git pull`.
4. İndirilen ve üretilen veri (`cache/`, `outputs/`, `*.nc`, `*.hdf`) git'e girmez.
5. Modüller yalnız `docs/sozlesmeler.md`'deki biçimlerle konuşur; sözleşme ekip onayıyla değişir.
