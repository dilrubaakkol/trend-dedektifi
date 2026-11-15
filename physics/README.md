# physics/ — L4 ilişki motoru (Kişi 3)

İki değişkenin yıldan yıla **birlikte değişip değişmediğini** ölçer ve fiziğin beklediği yönle
karşılaştırır. Sonuç bir **ilişkidir**, nedensellik iddiası taşımaz. Yalnız yerel L1 paketi okunur.

Yöntem (her iki komutta aynı): bölgenin cos(enlem) ağırlıklı alan ortalaması → mevsim döngüsü dışarıda
kalan seri (yılda bir mevsim değeri ya da aylık anomali) → iki seriden doğrusal trend çıkarılır →
Pearson r → Bretherton vd. (1999) etkin n ile p → 81 il için BH-FDR (α = 0,10), bölge ve Türkiye için
p < 0,05 → etiket `beklenen_yonde` / `ters_yonde` / `anlamsiz`.

| Dosya | İş |
| --- | --- |
| `ciftler.yaml` | Çiftlerin tanımı (şema: `docs/sozlesmeler.md` 2.3). Yeni çift = yeni madde |
| `ciftler.py` | YAML'ı okur, çiftin serilerini hazırlar |
| `seriler.py` | Mevsim, yıllık, mevsim anomalisi, aylık anomali, gecikme |
| `iliski.py` | Tek seri hesabı (trend çıkarma, r, etkin n, p, FDR); `python -m physics.iliski` girişi |
| `tablo.py`, `harita.py` | İl/bölge tablosu ve hücre haritası |
| `run.py` | Bütün çiftler → `L4_iliski/` |
| `tek_cift.py` | Tek çift komutu → ekran / JSON / `L4_iliski/ozel/` |
| `sapma.py` | Beklentiden sapma haritası ve sulama izi → `L4_iliski/sapma/` |
| `buyukluk.py` | Büyüklük testleri (Clausius-Clapeyron, su bütçesi, kar çizgisi) → `L4_iliski/buyukluk/` |

## Komutlar

```bash
# 1) ciftler.yaml'daki bütün çiftler → outputs/trend-dedektifi-turkiye-v0.1/L4_iliski/
python -m physics.run --surum v0.1

# 2) Tek il, tek mevsim: kış sıcaklığı ile kar örtüsü, Erzurum (~1 sn)
python -m physics.iliski --x sicaklik_2m --y kar_ortusu --bolge Erzurum --mevsim kis --beklenen -

# 3) 81 il birden, FDR ile; yağış 1 ay önce, ilkbahar NDVI; CSV'ye de yaz (~5 sn)
python -m physics.iliski --x yagis --y ndvi --bolge tum_iller --mevsim ilkbahar --gecikme 1 --beklenen + --kaydet
```

`--bolge`: il adı ya da plaka (`Elazığ`, `23`), bölge (`Doğu Anadolu`), `turkiye`, `tum_iller`,
`tum_bolgeler`. `--mevsim`: `yillik`, `kis`, `ilkbahar`, `yaz`, `sonbahar`, `mevsimlik`, `aylik`.
Ürün verilmezse Kademe 1 öncelikli ürün seçilir ve ekranda yazılır (`--urun-x`, `--urun-y` ile değişir).
`--json` makine okunur çıktı verir. `--karne` her satırın altına bulgu karnesini basar (kaynak uyumu,
karıştırma testi, trendden arındırma, gecikme ±1, α = 0,05 ve güven seviyesi; kural: sözleşme 2.4):

```bash
python -m physics.iliski --x sicaklik_2m --y kar_ortusu --bolge Erzurum --mevsim kis --beklenen - --karne   # ~3 sn
```

Bütün L3 trendleri ve L4 ilişkileri için karne dosyaları: `python -m stats.karne --surum v0.1` (→ `karne/`). Yanlış yazılan değişken, ürün ya da il için mevcut seçenekler listelenir.

Ekrandaki **ham r** trendi çıkarmadan, **r (trendsiz)** trendi çıkararak hesaplanır. İkisi çok farklıysa
iki serinin aynı dönemdeki trendi ilişkiyi şişiriyor (sahte korelasyon) ya da gizliyor demektir; yorum
trendsiz r ile yapılır ve komut bunu uyarı olarak yazar.

## Beklentiden sapma haritası

```bash
python -m physics.sapma --surum v0.1            # L4_iliski/sapma/: harita (.nc), il tablosu, kümeler (~5 sn)
python -m physics.sapma --surum v0.1 --goster   # ayrıca HTML harita yazar ve tarayıcıda açar
python -m physics.sapma --surum v0.1 --v2       # v2: tarım maskesi + 0,05° (önce: python -m data.arazi --surum v0.1)
```

v2 yalnız `sapma_haritasi_v2_025.nc`, `sapma_haritasi_v2_005.nc`, `sulama_izi_kumeleri_v2.csv` dosyalarını yazar;
`dogrulama/` klasöründe GFSAD katmanı varsa bağımsız doğrulamayı (ROC AUC, precision@%5) da çalıştırır.
Sonuçlar ve sınırlar: `docs/dogrulama.md` "Sapma haritası v2".

```bash
python -m physics.sapma_v3 --surum v0.1         # v3: bitki takvimi (~3 sn; 0,05° dosyaları varsa onları da işler)
```

v3 (`physics/sapma_v3.py`) regresyon yerine bitki takvimine bakar: yazı kurak (Haz–Ağu yağışı < 80 mm, rakım
< 1500 m) bir hücrede NDVI temmuz–ağustosta nisan–mayıstan yüksekse yağmur bunu açıklayamaz. Yalnız
`sapma_haritasi_v3_*.nc`, `sulama_izi_kumeleri_v3.csv`, `KURAL_v3.txt` yazar; `dogrulama/` klasöründe GFSAD1KCM
ve/veya LGRIP30 katmanı varsa `dogrulama/sapma_v3_dogrulama.csv` ölçütlerini de üretir. Eşikler 0,25° NDVI ve
yağışa bakılarak seçildi (keşif notu modülde); doğrulama katmanlarına bakılmadı.

Önce `physics.run` çalışmış olmalı (L4 etiketleri okunur). Çıktı **doğrulanmamış** bir göstergedir:
L4 etiketinin fiziksel beklentiden saptığı yerleri ve yazın yağışın açıkladığından yeşil/serin kalan
hücreleri ("sulama izi") gösterir. Bunlar insan müdahalesiyle (sulama, baraj, yeraltı suyu çekimi)
tutarlı olabilir; iklim rejimi ve veri/ürün sorunu da olası açıklamalardır. Yöntemde yer adı yoktur.


## Büyüklük testleri

Yön testinin yanına "ne kadar" testi. Gözlenen büyüklük, blok bootstrap ile %95 güven aralığı (999 tekrar, sabit
tohum) ve literatürden bir beklenen bantla karşılaştırılır. Etiketler: `beklenen büyüklükle tutarlı`,
`beklenenden küçük`, `beklenenden büyük`, `belirsiz`. Her satırda kısa bir karne de var: kaynak uyumu, dönem
duyarlılığı, GA genişliği. Kural sözleşme 2.5'te.

```bash
python -m physics.buyukluk --surum v0.1                    # üç test, il + bölge + Türkiye (~40 sn)
python -m physics.buyukluk --surum v0.1 --test cc          # yalnız Clausius-Clapeyron (~23 sn)
python -m physics.buyukluk --surum v0.1 --test butce       # yalnız su bütçesi, bölge + Türkiye (~14 sn)
python -m physics.buyukluk --surum v0.1 --test kar_cizgisi # yalnız kar çizgisi (~3 sn)
python -m physics.buyukluk --surum v0.1 --il-yok           # il satırları olmadan, daha hızlı
```

Bu komut yalnız `L4_iliski/buyukluk/` altına yazar. Yol haritasındaki eski kod buraya bağlandı: kar çizgisi serisi
`shift.snowline_series`'ten alınır. `tests_physical.py` ve `run_yol_haritasi.py` değişmedi.
Sonuçlar: `docs/dogrulama.md` "Büyüklük testleri".