> **ARŞİV (2026-11-14):** Bu eski plandır. Proje kapsamı daraldı; güncel plan `physics/KISI3_PLAN.md`.

# Kişi 3 — Mekânsal Analiz ve Fiziksel Testler: Uygulama Planı

Bu plan yalnızca bu repodaki dosyalara dayanır. Başka belge yoktur.

- **Kurallar:** `CLAUDE.md` (repo kökü)
- **Sorumluluk tablosu ve git kuralları:** `README.md`
- **Veri ve sonuç biçimleri:** `docs/sozlesmeler.md`, `examples/results_example.json`
- **Bölgeler:** `data/regions.py`
- **Süreç kartı örneği:** `kb/cards/kar_isinma.yaml`

Kişi 3 yalnızca `physics/` klasörüne ve `tests/test_physics_*.py` dosyalarına yazar.
Dal: `kisi3-fizik`. Her adımı ayrı ayrı uygula. Bir adımın "Bitti kriteri" sağlanmadan
sonrakine geçme.

---

## 1. Kişi 3'ün işi (özet)

Bir değişkenin trend haritasında, aynı sürecin farklı yerlerde zıt yönlü trendler ürettiği
"ayna" bölgeleri bulmak; bir eksen (rakım, enlem, boylam) boyunca trendin işaret değiştirdiği
**sınırı** belirsizliğiyle hesaplamak; sınırın yıllar içindeki **kaymasını** ölçmek ve sonucu
hipotezden türetilen fiziksel tahminle karşılaştırıp `uyumlu` / `celiskili` / `yetersiz`
etiketi vermek.

Proje **Türkiye geneli** çalışacak. Repo şu an iki bölge tanımlıyor (`dogu_anadolu`, `konya`).
Bu yüzden tüm fonksiyonlar **bölge adını parametre olarak alır** ve hiçbir bölgeyi koda
gömmez. Türkiye ve alt bölgeler `data/regions.py`'ye eklendiğinde kod değişmeden çalışır.

## 2. Başlamadan ekibe sorulacak açık noktalar

Bunlar sözleşmeyi ilgilendirir. `CLAUDE.md` gereği Kişi 3 sözleşmeyi kendisi değiştirmez.
Kodda geçici bir varsayım gerekiyorsa varsayım dosyanın başına yazılır.

| # | Konu | Neden önemli | Kişi 3'ün geçici varsayımı |
|---|---|---|---|
| 1 | **Türkiye geneli repoda yok.** `regions.py`'de yalnızca 2 kutu var; ülke maskesi ve 7 coğrafi bölge yok. | Bölge bazlı sınır ve "ters yönlü bölgeler" analizi bölge maskesi gerektirir. | Fonksiyonlar `mask` (boolean `DataArray`) parametresi alır; maske yoksa bölge kutusunun tamamı kullanılır. |
| 2 | **0,05° ve 0,25° dosyaları aynı adı alıyor.** Yol `cache/processed/<bolge>/<degisken>__<urun>.nc`, ama kar ve rakım iki ızgarada saklanacak. | İki dosya birbirinin üzerine yazar. | Ekip bir ad kuralı belirleyene kadar ızgara, dosyanın `attrs["grid"]` alanından okunur (`"005"` / `"025"`). |
| 3 | **`rakim` zamandan bağımsız.** Sözleşme `time, lat, lon` boyutlarını zorunlu tutuyor. | Rakımın `time` boyutu yok. | Rakım dosyası `lat, lon` boyutlu kabul edilir. |
| 4 | **Rakımı kim üretecek?** Sözleşmede `rakim` bir veri değişkeni (Kişi 1). | Sınır analizi rakım olmadan başlayamaz. | Kişi 1 yetişemezse Kişi 3 üretir, sözleşme biçiminde (Adım 1). |
| 5 | **Kış serisinin ilk yılı.** Ortak dönem 2001-01'de başlıyor; Aralık–Mart kışı için Aralık 2000 yok. | İlk kış eksik kalır. | Kış Y = Aralık (Y−1) + Ocak–Mart (Y); analiz kışları **2002–2025**. Kişi 1 Aralık 2000'i eklerse 2001'den başlar. |
| 6 | **Su bütçesi için toplam akış gerekiyor.** Sözleşmede yalnızca `yuzey_akisi` var. | Bütçede R = yüzey + yüzeyaltı akış (GLDAS `Qs` + `Qsb`). Yalnızca yüzey akışı R'yi eksik tahmin eder. | Kişi 1'den yüzeyaltı akış da istenir. Gelmezse sonuç notuna "R eksik" yazılır. |
| 7 | **Clausius-Clapeyron deniz üzerinde geçerli.** | Kara üzerinde bağıl nem düştüğü için eğim %7/°C'nin altında kalabilir. Etiketli test deniz hücrelerinde yapılmalı. | Kişi 1'den Karadeniz için bir deniz kutusu istenir (ör. `karadeniz_deniz`, yaklaşık 31,0 · 42,3 · 37,0 · 43,3; kara içermediği haritada kontrol edilir). |
| 8 | **Etiket kümesi yalnızca 3 değer** (`uyumlu`, `celiskili`, `yetersiz`). | Kara üzerindeki Clausius-Clapeyron sonucu etiketlenmemeli. | Bu sonuç `label` alanı **olmadan**, yalnızca `note` ile yazılır. Kişi 4 ile teyit edilir. |
| 9 | **Trend güven aralığı.** Örnekteki `ci95` otokorelasyonu hesaba katıyor mu? | Fiziksel testler aralıkların örtüşmesine dayanır. Dar aralık yanlış `celiskili` üretir. | Kişi 2'den genişletilmiş aralık istenir (yarı genişlik × √(n/n_etkin)). Gelene kadar `physics/` içinde aynı hesap geçici olarak yapılır. |
| 10 | **Yeni sonuç tipleri.** Örnekte yalnızca `trend` ve `boundary_shift` var. | Ayna, su bütçesi ve Clausius-Clapeyron için yeni tip gerekir. | Bölüm 4'teki alanlar **öneri** olarak Kişi 4 ve 5'e onaylatılır. |

## 3. Kişi 3'ün `physics/` dosyaları

| Dosya | İçerik | Adım |
|---|---|---|
| `physics/_gecici_trend.py` | Kişi 2'nin fonksiyonları gelene kadar geçici Sen eğimi, genişletilmiş aralık, Mann-Kendall. Dosyanın başında "GEÇİCİ — stats/ hazır olunca silinecek" yazar. | 2 |
| `physics/dem.py` | SRTMGL3 indirme, birleştirme, 0,05° ve 0,25°'ye alan ortalaması. **Yalnızca madde 4'te Kişi 3'e verilirse.** | 1 |
| `physics/synthetic.py` | Testler için sentetik trend haritası ve kar küpü | 2 |
| `physics/boundary.py` | İşaret değiştiren sınır + blok bootstrap | 3 |
| `physics/mirror.py` | Ayna kümeleri ve eksen önerisi | 4 |
| `physics/shift.py` | Yıllık kar çizgisi serisi ve kayması | 6 |
| `physics/tests_physical.py` | `climate_velocity`, `water_budget`, `clausius_clapeyron`, ortak `label()` | 5, 7 |
| `tests/test_physics_*.py` | Sentetik veriyle testler (internet gerektirmez) | her adım |

Girdi olarak `xarray.DataArray` alınır (boyutlar sözleşmedeki gibi; `lat` artan). Her
fonksiyon `results.json`'a girecek bir `dict` döndürür. Yeni paket gerekirse
`requirements.txt`'e eklenir (`CLAUDE.md` kuralı). Mevcut paketler yeterlidir.

## 4. Sonuç biçimi (`examples/results_example.json` üzerine)

Örnekteki `boundary_shift` tipi korunur. Örnekteki alanlar (`id`, `type`, `axis`,
`observed_shift_m_per_decade`, `predicted_shift_m_per_decade`, `label`) **aynı adla** kalır.
Aşağıdaki ek alanlar ve yeni tipler **öneridir**; Kişi 4 ve 5 onaylamadan kesinleşmez.

- **`id` benzersizliği:** Türkiye genelinde birden çok bölge olacağı için `id`'ye bölge
  eklenir: `sinir_rakim_kar_dogu_anadolu`. Sözleşme yalnızca benzersizlik istediği için bu
  bir değişiklik değildir, ama Kişi 4'e söylenir.

```json
{
  "id": "sinir_rakim_kar_dogu_anadolu",
  "type": "boundary_shift",
  "region": "dogu_anadolu",
  "axis": "rakim",
  "boundary_m": 2650,
  "boundary_ci95_m": [2500, 2800],
  "observed_shift_m_per_decade": [40, 95],
  "predicted_shift_m_per_decade": [55, 110],
  "label": "uyumlu",
  "status": "ok",
  "curve": {"x_m": [1500, 1600], "median_trend": [-3.1, -2.8]},
  "snowline": {"kis": [2002, 2003], "rakim_m": [2410, 2390]}
}
```

Sayıların hepsi yer tutucudur. `status` değerleri: `ok`, `uncertain`, `no_boundary`,
`undefined` (kar çizgisi tanımsız).

**Önerilen yeni tipler:** `mirror`, `water_budget`, `clausius_clapeyron`. Alanları Adım 4
ve Adım 7'de tanımlı.

---

## Adım 1 — A0 (0–2. saat): Ekip toplantısı + rakım

1. Bölüm 2'deki 10 maddeyi toplantıda sor ve cevapları bu dosyanın sonundaki
   "Kararlar" bölümüne yaz.
2. **Rakım** (madde 4 sana verildiyse):
   - SRTMGL3 karolarını `earthaccess` ile indir. Arama: `short_name="SRTMGL3"`,
     `version="003"`, bölge kutusu artı her yönde 0,25° pay.
   - Karoları birleştir. Alan ortalamasıyla 0,05° ve 0,25°'ye indir
     (`rioxarray` / `rasterio` average resampling).
   - **Izgara hizası:** hücre kenarları çözünürlüğün katlarında olmalı; 0,05°'de hücre
     merkezleri x,025, 0,25°'de x,125 olur. Bölge kutusu kenarları dışa doğru yuvarlanır.
   - Sözleşmedeki zorunlu `attrs` yazılır: `units`, `long_name`, `source_product`,
     `source_version`, `doi`, `daac`, `download_date`, `processing`, `grid`.
     SRTMGL3 DOI'si: 10.5067/MEaSUREs/SRTM/SRTMGL3.003.
   - Yazılır: `cache/processed/<bolge>/rakim__SRTMGL3.nc` (ızgara adı sorunu, madde 2).

**Bitti kriteri**
- İnternetsiz birim testi: rakımı doğrusal bir fonksiyon olan sahte karolarda, 0,05°
  hücre ortalaması hücre merkezindeki değere eşit çıkıyor.
- Gerçek veride akıl kontrolü: Ağrı Dağı'nı içeren hücreler bölgenin en yükseğinde
  (hücre bir alan ortalaması olduğu için 5137 m'lik zirveden belirgin biçimde düşük),
  Tuz Gölü hücreleri yaklaşık 900 m.

## Adım 2 — A1 (2–6. saat): Sentetik veri + geçici trend yardımcısı

**`physics/synthetic.py`**
- Verilen rakım alanı üzerinde trend = a × (rakım − z0) + mekânsal olarak ilişkili gürültü
  (beyaz gürültü Gauss filtresiyle düzeltilir).
- Parametreler: seed, z0, gürültü düzeyi, korelasyon uzunluğu.
- "Sınır yok" seçeneği: her yerde aynı işaret.
- Sentetik kış kar küpü: bilinen hızla (ör. +50 m/10 yıl) yükselen bir kar çizgisi;
  altında kar örtüsü düşük, üstünde yüksek, arada gürültü.
- **Gerçekçi rakım dağılımı:** Doğu Anadolu bir platodur (çoğu hücre 1500–2200 m) ve
  yüksek dağlar az yer kaplar. Sentetik rakım bunu yansıtmalıdır; yoksa sınırın üstünde
  çok az piksel kalır ve testler yanıltıcı olur.

**`physics/_gecici_trend.py`**
- Sen eğimi: `scipy.stats.theilslopes(y, x, alpha=0.95)`.
- Genişletilmiş aralık: artıkların gecikme-1 otokorelasyonu r1;
  n_etkin = n × (1 − r1) / (1 + r1) (r1 ≤ 0 ise n_etkin = n). Alt ve üst yarı genişlik
  ayrı ayrı √(n / n_etkin) ile çarpılır.
- Mann-Kendall: `pymannkendall.hamed_rao_modification_test`.
- Birim: on yıl başına (yıllık seride eğim × 10).

**Bitti kriteri:** 1000 sentetik seride (AR(1) gürültü, φ = 0,5) gerçek trend,
genişletilmiş aralığın içinde en az %90 oranında kalıyor.

## Adım 3 — A1–A2: İşaret değiştiren sınır (`physics/boundary.py`)

**Algoritma**
1. Trend haritası ve eksen aynı ızgaradadır; varsa bölge maskesi uygulanır, NaN'lar atılır.
2. Eksen dilimlere ayrılır: rakım için 100 m (0,05°'de), 0,25°'de 200 m; enlem ve boylam
   için 0,25°. Her dilimde trendlerin medyanı alınır. 30'dan az pikselli dilim atılır.
3. Medyan eğri LOWESS ile düzeltilir (`statsmodels`); eğrinin sıfırı kestiği noktalar
   doğrusal ara değerle bulunur. Birden fazla kesişim varsa hepsi raporlanır. "Ana sınır",
   altındaki dilimler bir işarete, üstündekiler ters işarete en iyi ayrılan kesişimdir.
4. **Belirsizlik: blok bootstrap.** Komşu pikseller bağımsız değildir, bu yüzden tek tek
   pikseller değil **0,5°'lik bloklar** yerine koyarak 1000 kez yeniden örneklenir ve her
   seferinde sınır yeniden bulunur. %2,5 ve %97,5 yüzdelikleri güven aralığıdır.
   Bootstrap'lerin %20'sinden fazlasında kesişim kaybolursa `status` = `uncertain` olur.
5. Eksen bir parametredir: `rakim`, `enlem`, `boylam`. Enlem ve boylam koordinatlardan gelir.

**Bitti kriteri** (`tests/test_physics_boundary.py`)
- Sentetik haritada bilinen sınır, tahminin ±100 m içinde.
- "Sınır yok" haritasında `status` = `no_boundary`.
- **Kapsama testi** (uzun test olarak işaretlenir): aynı rakım alanı, 60 veya daha fazla
  farklı gürültü tohumu. Güven aralığı gerçek sınırı en az %90 oranında kapsamalı.
  - Kısa bir ön denemede 0,5° bloklarla kapsama %83–93 çıktı.
  - Düşük çıkarsa blok boyutunu 1°'ye çıkar.
  - Hâlâ düşükse kapsama oranını sonuçla birlikte raporla; ölçütü gevşetme.
- Bölge başına 1000 bootstrap birkaç saniyede bitiyor.

## Adım 4 — A2 (6–16. saat): Gerçek veride sınır + ayna kümeleri

**Girdi:** Kişi 2'nin kar trend haritası (0,05°, kış serisi) ve FDR maskesi. Gelene kadar
Adım 2'deki sentetik harita kullanılır.

**Sınır.** Adım 3, mevcut her bölge için çalıştırılır. Türkiye ve alt bölgeler eklenince
her biri için ayrıca çalışır. Kıyı bölgelerinde kar sinyali zayıfsa `no_boundary` dürüst
bir sonuçtur.

**Ayna kümeleri (`physics/mirror.py`)**
1. FDR'yi geçen pikseller pozitif ve negatif olarak ayrılır. Bitişik pikseller
   `scipy.ndimage.label` ile kümelenir; en küçük küme boyutu bir parametredir.
2. Zıt işaretli kümeler için ortalama rakım, enlem ve boylam hesaplanır.
3. Standartlaştırılmış farkı en büyük olan özellik önerilen eksendir. Ayna bölgeler
   veriden çıkar, önceden varsayılmaz.

Önerilen çıktı:
```json
{"id": "ayna_kar_ortusu_<bolge>", "type": "mirror", "region": "<bolge>",
 "variable": "kar_ortusu", "suggested_axis": "rakim",
 "clusters": [{"cluster_id": 1, "sign": -1, "n_pixels": 5400,
               "mean_rakim_m": 1650, "mean_lat": 39.4, "mean_lon": 41.2}],
 "status": "ok"}
```

**Bitti kriteri:** Doğu Anadolu sınırı ve ayna kümeleri gerçek veriyle hesaplanıyor;
Kişi 4 ve 5'e örnek çıktı verildi.

## Adım 5 — A2 sonu: İklim hızı testi (`physics/tests_physical.py`)

**Hipotez:** Isınma sorumluysa kar çizgisi şu hızla yükselmeli:

> tahmin (m/10 yıl) = dT/dt ÷ |dT/dz|

- **dT/dt:** bölge ortalaması kış sıcaklığı trendi (Aralık–Mart), genişletilmiş aralıkla.
  `sicaklik_2m` MERRA-2 (ana) ve GLDAS (ikincil) için ayrı ayrı hesaplanır.
- **dT/dz:** bölge içinde, kış ortalama sıcaklığının 0,25° hücrelerde
  `T ~ rakım + enlem + boylam` regresyonundaki rakım katsayısı.
  - 6,5 °C/km gibi sabit bir değer varsayılmaz; ölçülür.
  - Uyarı: model sıcaklıkları modelin yumuşatılmış rakımına göredir. SRTM 0,25° ortalaması
    kullanılır ve bu bir varsayım olarak sonuç notuna yazılır.
- **Belirsizlik:** dT/dt ve dT/dz aralıklarından 1000 Monte Carlo çekilişi; tahmin
  aralığı = %2,5–97,5 → `predicted_shift_m_per_decade`.

**`label()` kuralı** (tüm testler aynı fonksiyonu kullanır, öncelik sırasıyla):
1. Trend anlamlı değil, veri kısa ya da aralık anlamlı bir sonuç vermeyecek kadar geniş
   → `yetersiz`
2. İşaret ters ya da gözlenen aralık tahmin aralığını dışlıyor → `celiskili`
3. Aralıklar örtüşüyor → `uyumlu`

**Bitti kriteri:** Sentetik girdiyle üç etiketin her biri doğru üretiliyor. Gözlenen kayma
Adım 6'da gelir.

## Adım 6 — A3 (16–24. saat): Sınır kayması (`physics/shift.py`)

1. Her kış için (Y = Aralık Y−1 + Ocak–Mart Y; kışlar 2002–2025, madde 5), bölge içinde
   her 100 m dilimin medyan kar örtüsü bulunur.
2. Kar örtüsünün %50'yi kestiği rakım doğrusal ara değerle bulunur; bu o kışın kar çizgisidir.
3. %50 hiç kesilmeyen kışlar NaN olur. Bir bölgede kışların çoğu NaN ise o bölgenin
   `status` değeri `undefined` olur (kıyı bölgelerinde beklenir).
4. Kar çizgisi serisinin Sen eğimi ve genişletilmiş aralığı →
   `observed_shift_m_per_decade`. Anlamlılık Mann-Kendall ve t-testiyle ölçülür.
5. Kayan pencereler (ör. 15 yıllık) yalnızca görsel içindir; p değerleri geçersizdir.
6. Adım 5'teki test gözlenen kaymayla çalıştırılır; `boundary_shift` kaydı (Bölüm 4)
   tamamlanır.

**Bitti kriteri**
- Sentetik küpte bilinen +50 m/10 yıl kayma aralığın içinde bulunuyor.
- Doğu Anadolu için `boundary_shift` kaydı gerçek veriyle üretildi.
- **24. saatteki MVP demosu bu sonuca dayanıyor.**

## Adım 7 — A4 (24–36. saat): Su bütçesi + Clausius-Clapeyron

### 7a. Su bütçesi (`konya`)

**Doğru formül:** depolamanın zamanla değişimi akıların kendisine eşittir:
dS/dt = P − ET − R. Bu yüzden **terimlerin trendleri karşılaştırılmaz.**

| Taraf | Ne hesaplanır | Kaynak | Birim |
|---|---|---|---|
| Sol | `toplam_su_depolama` serisinin Sen eğimi, genişletilmiş aralıkla | GRACE | cm → mm (× 10), mm/yıl |
| Sağ | Aynı dönemin **tüm aylarında** P − ET − R ortalaması | P: `yagis` GPM; ET: `buharlasma` GLDAS; R: akış GLDAS (madde 6) | mm/ay × 12 = mm/yıl |
| Artık | sol − sağ | | mm/yıl |
| Belirsizlik | GRACE eğiminin aralığı + üç yağış ürününün (GPM, MERRA-2, GLDAS) yayılımı | | |

- **GRACE:** Nisan 2002'de başlar. 2017–2018 arasındaki yaklaşık 11 aylık boşluk NaN
  kalır, ara değerle doldurulmaz. Sağ taraftaki ortalama ise boşluk dahil tüm aylardan
  alınır, çünkü depolama değişimi boşlukta da birikir.
- **Konya'da büyük olasılıkla `celiskili` çıkar:** GLDAS sulamayı ve yeraltı suyu çekimini
  modellemez. Not: "olası insan kaynaklı kayıp (yeraltı suyu çekimi / sulama)". Bu bir hata
  değil, demonun güçlü bir anıdır.
- **Çözünürlük notu:** GRACE'in etkin çözünürlüğü yüzlerce km'dir; Konya kutusu bu ölçeğe
  yakındır. Bu sonuç notuna yazılır.

Önerilen çıktı:
```json
{"id": "butce_konya", "type": "water_budget", "region": "konya",
 "grace_slope_mm_per_year": [-25, -12], "p_et_r_mean_mm_per_year": [-3, 6],
 "residual_mm_per_year": -15, "label": "celiskili",
 "note": "olası insan kaynaklı kayıp (yeraltı suyu çekimi / sulama); GRACE çözünürlüğü kaba"}
```

### 7b. Clausius-Clapeyron

**Hipotez:** Su buharı 1 °C ısınmada yaklaşık %7 artar.

- **Değişkenler** (sözleşmede mevcut olanlar): `ozgul_nem_2m` (MERRA-2, ana) ve
  `sicaklik_2m` (MERRA-2). İkinci kaynak: `su_buhari_kolon` (AIRS) ile AIRS `sicaklik_2m`;
  AIRS 2002'de başlar, o karşılaştırmada dönem kısadır.
- **Hesap:** aylık anomalilerde ln(nem)'in sıcaklığa eğimi × 100 (%/°C), genişletilmiş aralıkla.
- **Etiketli test:** deniz kutusunda (madde 7). Aralık %6–8/°C ile örtüşüyorsa `uyumlu`.
- **Kara bölgesi:** aynı hesap yapılır ama `label` alanı yazılmaz (madde 8). Not: "karada
  bağıl nem düştüğü için eğim %7'nin altında kalabilir".

Önerilen çıktı:
```json
{"id": "cc_karadeniz_deniz", "type": "clausius_clapeyron", "region": "karadeniz_deniz",
 "slope_pct_per_C": [5.8, 7.9], "expected_pct_per_C": [6, 8], "label": "uyumlu"}
```

Bu bölümdeki tüm sayılar yer tutucudur.

## Adım 8 — A5 (36–48. saat): Kontrol ve sunum desteği

- Her `celiskili` sonucun `note` alanında bir açıklama ya da alternatif var mı, kontrol et.
  Alternatifler süreç kartının `alternatifler` listesinden gelir.
- Kişi 5'e sınır eğrisi (`curve`) ve kar çizgisi serisi (`snowline`) grafikleri için destek ver.
- Jüriye kısa cevaplar hazırla:
  - Neden bölge bazlı sınır? (Türkiye'de farklı iklim rejimleri tek eğride karışır.)
  - dT/dz neden ölçüldü, varsayılmadı?
  - Bootstrap neden bloklu ve kapsama testi ne çıktı?
  - Konya bütçesi neden kapanmıyor?
- Son 4 saatte yeni özellik yok.

---

## Kararlar (toplantıdan sonra doldur)

Kaynak: Kişi 1'in `main`'e birleşen PR #1'i (`docs/sozlesmeler.md`, `data/`).

| # | Karar |
|---|---|
| 1 | ✅ Çözüldü. 81 il, 7 coğrafi bölge, 4 deniz ve `turkiye` maskesi `data/regions.py`'de. Veri `data.load(degisken, region=..., grid=...)` ile bölgeye kesilir; elimizdeki dizi `data.subset(da, region)` ile kesilir. Kişi 3 fonksiyonları yine de `mask` parametresi alır (bölge dışı hücreler zaten NaN gelir). |
| 2 | ✅ Çözüldü. Tek Türkiye küpü: `cache/processed/turkiye/<degisken>__<urun>.nc`; 0,05° için `__005` eki. |
| 3 | ✅ Çözüldü. Sabit alanlar (`rakim`) yalnız `lat, lon` boyutlu. |
| 4 | ✅ Kişi 1 üretiyor (`data/dem.py`, `python -m data.dem`). Kaynak **SRTMGL30 002** (planda SRTMGL3 yazıyordu). Dosyalar `rakim__SRTM.nc`, `rakim__SRTM__005.nc`; okuma `data.dem.load_dem(grid)`. Rakım kara maskeli. → `physics/dem.py` yazılmaz. |
| 5 | ⏳ Açık. Kişi 1'e sorulacak: Aralık 2000 eklenebilir mi? O zamana kadar kışlar 2002–2025 (24 kış). |
| 6 | ✅ Çözüldü. `taban_akisi` (GLDAS `Qsb`) eklendi → R = `yuzey_akisi` + `taban_akisi`. |
| 7 | ✅ Çözüldü (Kişi 1, PR #3/#4). MERRA-2 `sicaklik_2m` ve `ozgul_nem_2m` artık `domain: all`. Deniz için `region="deniz_karadeniz"` kullanılır (`"turkiye"` yalnız kara verir). |
| 8 | ✅ Fiilen uyumlu. Kişi 5'in `app/results_io.py`'si `label` olmayan kaydı "Bilgi" olarak gösteriyor. Kara Clausius-Clapeyron sonucu `label` olmadan yazılacak. |
| 9 | ⏳ Açık. Kişi 2 ile; o zamana kadar `physics/_gecici_trend.py`. **Kişi 2'ye iletilecek bulgu:** planın √(n/n_etkin) formülü 24 kışta yalnız %88 kapsama veriyor. r1 küçük örneklem düzeltmesi + t(n_etkin−2) ile %91,6 (10 000 seri, φ=0,5). Geçici modülde varsayılan bu. |
| 10 | ⏳ Kısmen. Kişi 5'in arayüzü sınırı **ayrı `type: "boundary"`** kaydı olarak okuyor (`boundary_m`, `boundary_ci95_m`, `axis`). Bu yüzden Bölüm 4 değişti: sınır → `boundary` (id `sinir_<eksen>_<degisken>_<bolge>`), kayma → ayrı `boundary_shift` (`observed_shift_m_per_decade`, `predicted_shift_m_per_decade`, `label`; Kişi 4 ve 5 bunu okuyor). `mirror`, `water_budget`, `clausius_clapeyron` hâlâ öneri: arayüzde gösterilmiyor, Kişi 5'e bildirilecek. |

**Adım 3 kapsama sonucu (2026-11-14):** 60 tohumda %95 aralığın gerçek sınırı kapsama oranı
0,5° blokla **%82**, 1° blokla **%82** (hedef ≥ %90 → sağlanmadı, ölçüt gevşetilmedi).
Tahmin yansız (60 tohum ortalaması 2648 m, gerçek 2650 m); sorun aralığın dar olması
(bootstrap saçılımı ~20 m, gerçek saçılım ~28 m). Jüriye: "sınır aralığı yaklaşıktır,
gerçek kapsama ~%82". Blok boyutu 0,5°'de bırakıldı. Uzun test: `YAVAS_TEST=1 pytest -k kapsama`.

**Adım 4 durumu (2026-11-14):** Kod hazır (`physics/mirror.py`, `boundary.find_boundaries`),
sentetik veriyle test edildi. Gerçek veriyle çalıştırma **bekliyor**: Kişi 2'nin kar trend
haritası + FDR maskesi henüz yok. Örnek çıktı: `python -m physics.ornek` →
`physics/ornekler/ornek_sonuclar.json` (yer tutucu) — Kişi 4 ve 5'e gönderilecek.
Ek (plan dışı): rakım ile boylam/enlem birbirine bağlıysa (|r| ≥ 0,6 ve ayırma güçleri
oranı < 2) sonuca `alternative_axis` ve uyarı `note`'u yazılır; Türkiye'de doğu daha yüksek
olduğu için gerçek veride beklenir.

**Adım 5 durumu (2026-11-14):** `physics/tests_physical.py` → `label()` (ortak etiket kuralı,
`label_reason` gerekçesiyle) ve `climate_velocity()` hazır. Sentetik veride tahmin aralığı gerçek
kaymayı 300 denemede **%95** kapsıyor (hedef %95). Çıktı tipi `climate_velocity`; gözlenen kayma
verilirse `observed_shift_m_per_decade` + `label` eklenir (Kişi 5'in arayüzü bu iki alanı görünce
grafiği çizer). Geçici `winter_mean` `_gecici_trend.py`'de. Gerçek veride çalıştırma: MERRA-2 ve
GLDAS `sicaklik_2m` + `rakim__SRTM.nc` (0,25°) gerekli; gözlenen kayma Adım 6'da gelir.

**Adım 6 durumu (2026-11-14):** `physics/shift.py` (kar çizgisi serisi, gözlenen kayma,
`boundary_shift` kaydı + etiket) ve `physics/run.py` (uçtan uca: `python -m physics.run <bolge> --yaz`)
hazır. Sentetik küpte +50 m/10 yıl kayma 100 denemede %95 kapsanıyor. Kişi 1'in sentetik
dosyalarıyla Doğu Anadolu zinciri çalıştı (etiket: uyumlu — YER TUTUCU) ve Kişi 5'in
`load_results` fonksiyonu kaydı okuyup kayma grafiğini çiziyor.
**Bekleyen:** gerçek veri. Kişi 1'in `cache/processed/turkiye/` dosyaları (kar_ortusu__MOD10CM__005,
rakim__SRTM(__005), sicaklik_2m__MERRA2, sicaklik_2m__GLDAS) bu bilgisayara gelince aynı komut
gerçek sonucu `cache/results/`'e yazar. Sentetik sonuç `cache/physics/`'e gider (Kişi 5'in testi
`cache/results/`'te yer tutucu istemiyor). Duyarlılık kontrolü (hücre içi rakım std > 400 m)
yapılmadı: Kişi 1 rakım std dosyası üretmiyor.

**Adım 7 durumu (2026-11-14):** `water_budget()` ve `clausius_clapeyron()` `physics/tests_physical.py`'de;
çalıştırma `python -m physics.run --test butce` (demo:konya) ve `--test cc` (deniz_karadeniz
etiketli + turkiye etiketsiz; `ozgul_nem_2m` ve `su_buhari_kolon`). Sentetikte: gizli kuyu çekimi
→ `celiskili` + "olası insan kaynaklı kayıp" notu; kayıp yok → `uyumlu`; CC %7 → `uyumlu`,
%3 ya da %11 → `celiskili`, aralık 100 denemede ≥ %90 kapsıyor.
- GRACE eğimi mevsim döngüsü çıkarılarak hesaplanır (plan bunu söylemiyordu; mevsimsellik Sen
  eğimini ve r1'i bozar).
- **Bilinen sınırlama:** depolama aylık akıların birikimidir (rastgele yürüyüşe yakın); r1 0,95'te
  kırpıldığından GRACE eğim aralığı gerçekte olduğundan dar olabilir. Konya'da fark büyük
  beklendiği için etiketi değiştirmesi beklenmez; jüriye söylenir.
- **Bekleyen veri (Kişi 1):** `toplam_su_depolama__GRACE`, `yagis__GPM/GLDAS/MERRA2`,
  `buharlasma__GLDAS`, `yuzey_akisi__GLDAS`, `taban_akisi__GLDAS`, `ozgul_nem_2m__MERRA2`,
  `su_buhari_kolon__MERRA2`, `sicaklik_2m__MERRA2`. Sentetik yedekleri yok; dosyalar gelmeden
  komut "Veri eksik" der.
- **Kişi 4'e iletilecek Konya metni:** `celiskili` + note "olası insan kaynaklı kayıp (yeraltı
  suyu çekimi / sulama): GLDAS sulamayı ve kuyu çekimini modellemez; GRACE'in etkin çözünürlüğü
  yüzlerce km". Kart: `su_kaynaklari`. CC için kart: `nem_artisi`.

**Ortam notu (Windows):** Kullanıcı klasörü adında Türkçe karakter olduğu için netCDF4 geçici
klasöre yazamıyor. Testler `pytest --basetemp=D:/pytest_tmp` ile çalıştırılır.
