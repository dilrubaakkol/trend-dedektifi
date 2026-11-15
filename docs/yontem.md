# Yöntem

Bu belge Trend Dedektifi v0.1 veri paketinin ve açıklama katmanının nasıl üretildiğini anlatır. Bir
makalenin "Veri ve yöntem" bölümüne kaynak olacak biçimde yazılmıştır. Dosya biçimlerinin tam tanımı
[`sozlesmeler.md`](sozlesmeler.md)'de, doğrulama çalışmaları [`dogrulama.md`](dogrulama.md)'dedir. İki
belge çelişirse sözleşme ve kod esastır; bu belge onlara göre güncellenir.

Çerçeve **ilişki**dir, neden değil: Hiçbir sonuç, etiket ya da açıklama cümlesi nedensellik iddia etmez.

## 1. Kapsam

- **Alan:** Türkiye. Yayın kutusu 25,5°D–45,0°D, 35,5°K–42,5°K (0,25°'de 28 × 78 hücre).
- **Bölgeler:** 81 il (Natural Earth 10m Admin-1), 7 coğrafi bölge (`data/boundaries/bolgeler.yaml`) ve
  Türkiye geneli.
- **Dönem:** 2001-01 … 2025-12, aylık. Daha geç başlayan ya da erken biten ürünler kendi dönemleriyle
  yer alır (ör. GRACE 2002-04'te başlar; GPM IMERG Final şu an 2025-09'da biter).

## 2. Veri

Bütün girdiler NASA ürünleridir. Sürüm, DOI ve dosyadaki değişken adları
[`data/catalog.yaml`](../data/catalog.yaml)'dadır; her çıktı dosyası kaynağının DOI'sini taşır.

| Değişken | Ana ürün (sürüm) | İkincil ürün | Kademe |
| --- | --- | --- | --- |
| Hava sıcaklığı (2 m) | MERRA-2 M2TMNXSLV (5.12.4) | GLDAS Noah (2.1) | 1 |
| Yağış | GPM IMERG M (V07) | GLDAS Noah, MERRA-2 M2TMNXFLX | 1 |
| Toprak nemi (0–10 cm) | GLDAS Noah (2.1) | — | 1 |
| Kar örtüsü | MODIS MOD10CM (061) | — | 1 |
| Kar su eşdeğeri | GLDAS Noah (2.1) | — | 1 |
| NDVI | MODIS MOD13C2 (061) | — | 1 |
| Toplam su deposu | JPL GRACE/GRACE-FO Mascon CRI (RL06.3Mv04) | — | 1 |
| Buharlaşma, yüzey/taban akışı, kök bölgesi nemi, rüzgâr hızı | GLDAS Noah (2.1) | — | 2 |
| Nem, rüzgâr bileşenleri, basınç, su buharı, ozon, aerosol, bulut | MERRA-2 (5.12.4) | — | 2 |
| Kara yüzeyi sıcaklığı (gündüz/gece), EVI | MODIS MOD11C3, MOD13C2 (061) | — | 2 |
| Troposferik NO₂ | Aura OMI OMNO2d (004), 2004-10'dan | — | 2 |

**Kademe 1**, ekip belgesinde projenin çekirdeği olarak belirlenen 10 dosyadır (liste: `data/export.py`
içinde `KADEME_1`); doğrulama çalışmaları ([`dogrulama.md`](dogrulama.md)) bunlara odaklanır. **Kademe 2**
dosyaları paketle yayımlanır ama `dogrulanmadi = evet` bayrağı taşır; bunlardan türetilen her sonuç da bu
bayrağı devralır.

MERRA-2 ve GLDAS **model/yeniden analiz** ürünleridir; doğrudan gözlem değildir. Değişkenlerin
yorumuna ilişkin notlar `kb/degiskenler.yaml` içindeki `dikkat` alanlarındadır.

## 3. Ön işleme (L1)

Kod: `data/harmonize.py`, `data/export.py`.

1. Ürünün tüm dosyaları zamanda birleştirilir; bayrak değerleri ve geçerli aralık dışı değerler `NaN`
   yapılır, ürünün kalite maskesi uygulanır (ör. MOD13C2 piksel güvenilirliği).
2. Günlük ürünler aylık ortalamaya çevrilir (en az 5 geçerli gün); zaman damgası ayın 1'i 00:00 UTC.
3. Birimler ortak birimlere dönüştürülür (ör. kg m⁻² s⁻¹ → mm/ay, ay uzunluğuyla).
4. **Izgara:** 0,25° ortak ızgara. Daha ince ürünler alan-örtüşmeli blok ortalamasıyla (hedef hücrenin en
   az %50'si geçerliyse), daha kaba ürünler bilineer interpolasyonla bu ızgaraya getirilir.
5. **Maske:** Kara değişkenleri Türkiye kara sınırıyla maskelenir (hücre merkezi kuralı).

## 4. Hücre bazında trend (L2)

Kod: `stats/l2.py`, `stats/trend_tests.py`, `stats/preprocessing.py`.

### 4.1 Seriler

Her hücre için beş seri üretilir, her biri yılda bir değer içerir: **yıllık** (Ocak–Aralık), **kış**
(Aralık(Y−1)–Şubat(Y)), **ilkbahar** (Mart–Mayıs), **yaz** (Haziran–Ağustos), **sonbahar** (Eylül–Kasım).
Ortalama alınan değişkenlerde dönem ortalaması, birikimli değişkenlerde (yağış, buharlaşma, yüzey ve
taban akışı) dönem toplamı kullanılır.

**Eksik veri:** Bir yıl ya da mevsimde eksik ay oranı %20'yi aşarsa o değer kullanılmaz (yıllıkta en
çok 2 ay eksik olabilir; 3 aylık mevsimde tek eksik ay değeri düşürür). GRACE için yıllıkta en az 6
geçerli ay yeterli sayılır; ürünün 2011–2017 arasındaki dağınık eksik ayları ve 2017-07 … 2018-05
GRACE → GRACE-FO boşluğu bu eşiği gerektirir. Bir hücrede en az **12 geçerli yıl** yoksa trend
hesaplanmaz.

### 4.2 Eğim ve güven aralığı

- **Eğim:** Theil-Sen eğimi (Theil, 1950; Sen, 1968), "birim / 10 yıl" olarak raporlanır.
- **Etkin örneklem büyüklüğü:** Sen artıklarının gecikme-1 otokorelasyonu r₁ (yalnız ardışık yıllardan)
  küçük örneklem için düzeltilir: r₁′ = r₁ + (1 + 4r₁)/n (en çok 0,95). Ardından
  n_etkin = n (1 − r₁′)/(1 + r₁′) (r₁′ ≤ 0 ise n; en az 3).
- **Genişletilmiş %95 GA:** Sen güven aralığının iki yarısı ayrı ayrı
  √(n / n_etkin) · t₀,₉₇₅(n_etkin − 2) / t₀,₉₇₅(n − 2) ile çarpılır.

### 4.3 Anlamlılık

- **Test:** Hamed ve Rao (1998) otokorelasyon düzeltmeli Mann-Kendall testi (Mann, 1945; Kendall, 1975).
  Güçlü negatif otokorelasyonda düzeltilmiş varyans negatif çıkıp p tanımsız kalırsa o hücrede
  düzeltmesiz test kullanılır; bu hücreler sayılır ve dosyada belirtilir.
- **Çoklu test:** Benjamini ve Hochberg (1995) yanlış keşif oranı düzeltmesi, α_FDR = 0,10 (Wilks, 2016),
  her mevsim için ayrı, yalnız Türkiye kara hücreleri üzerinden.
- **Karar kuralı:** Bir trend **anlamlı** kabul edilir ⇔ q ≤ 0,10 **ve** genişletilmiş %95 GA sıfırı
  dışlar. İki koşulun birlikte aranması temkinli taraftır: Mann-Kendall testi ile genişletilmiş Sen
  aralığı farklı yöntemlerdir ve yalnız q kullanıldığında GA'sı sıfırı kapsayan trendler de anlamlı
  görünüyordu ([`dogrulama.md`](dogrulama.md), "Anlamlılık kuralı").

### 4.4 Gereken gözlem süresi

Gözlenen eğimi ayırt etmek için gereken yıl sayısı Weatherhead vd. (1998) ile hesaplanır:
n* = [3,3 · σ_N/|ω₀| · √((1 + φ)/(1 − φ))]^(2/3). Formül aylık seri için türetildiğinden, yılda bir değer
içeren serilerde σ_N yerine √12 · σ_N kullanılır. Gereken süre mevcut seriden uzunsa eğimin büyüklüğü
dikkatle yorumlanmalıdır; açıklama katmanı bunu ayrıca uyarır.

### 4.5 Ürünler arası uyum

Birden çok ürünü olan değişkenlerde (yağış: GPM, GLDAS, MERRA-2; sıcaklık: MERRA-2, GLDAS) ürünler ortak
döneme kırpılır ve trend yeniden hesaplanır. Raporlanan: **m** (trendi hesaplanabilen ürün sayısı),
**k** (anlamlı ve aynı yönde trend veren en büyük ürün grubu) ve **işaret uyumu** (anlamlılığa bakmadan
aynı işaretli eğim veren en büyük grubun m'ye oranı).

### 4.6 Ürüne özgü uyarılar

Değerler silinmez; bilinen sorunlar dosyaya `trend_uyarisi` olarak yazılır ve kullanıcıya gösterilir:
GLDAS sıcaklık, yağış ve akışlarında zorlama verisi homojen olmayabilir (trend için MERRA-2/GPM tercih
edilmeli); MODIS kara yüzeyi sıcaklığında Terra sensör kayması olasılığı doğrulanmadı; NDVI/EVI kış
serisi kar ve bulut yüzünden seyrektir.

## 5. İl ve bölge özetleri (L3)

Kod: `stats/l3.py`.

- **Hücre seçimi:** Merkezi bölge sınırı içinde kalan hücreler; hiçbir merkezin düşmediği küçük
  bölgelerde sınıra değen hücreler (dosyanın `not` sütununda belirtilir).
- **(A) Alan ortalaması serisinin trendi:** Hücrelerin cos(enlem) ağırlıklı ortalaması alınır, ardından
  L2 ile aynı mevsim serileri, eksik veri kuralı ve trend motoru uygulanır. FDR düzey içinde uygulanır
  (81 il kendi içinde, 7 bölge kendi içinde). Türkiye geneli ayrı tek satırlık bir düzeydir; FDR'ye
  girmez (q = p).
- **(B) Hücre özeti:** Bölgedeki L2 hücrelerinden anlamlı olanların oranı (artan/azalan ayrı) ve hücre
  eğimlerinin medyanı.
- Ürünler arası uyum (4.5) il ve bölge düzeyinde de alan ortalaması serileri üzerinden hesaplanır.

## 6. Değişkenler arası ilişki (L4)

Kod: `physics/ciftler.py`, `physics/run.py`. Ekibin önceden belirlediği altı çift incelenir; veri
üzerinden çift taranmaz (çoklu karşılaştırma şişmesini önler).

| No | Çift | Seri | Beklenen | Kapsam |
| --- | --- | --- | --- | --- |
| 1 | Sıcaklık (MERRA-2) ~ kar örtüsü (MOD10CM) | kış | − | Kış ortalaması kar örtüsü ≥ %10 olan hücreler |
| 2 | Yağış (GPM) ~ toprak nemi (GLDAS) | mevsimlik anomali | + | Tüm kara |
| 3 | Toprak nemi (GLDAS) ~ NDVI (MOD13C2) | aylık anomali, Nisan–Eylül; 1 ve 2 ay gecikme | + | Tüm kara |
| 4 | Yağış (GPM) ~ toplam su deposu (GRACE) | yıllık | + | Yalnız 7 bölge ve Türkiye (GRACE çözünürlüğü kaba) |
| 5 | Sıcaklık (MERRA-2) ~ buharlaşma (GLDAS) | yaz | + | Tüm kara; kurak yerde zayıf ya da ters çıkabilir |
| 6 | Sıcaklık (MERRA-2) ~ kara yüzeyi sıcaklığı (MOD11C3) | aylık anomali | + | Kalite kontrolü (güçlü pozitif beklenir) |

- **Seriler:** Mevsimlik/aylık anomaliler kendi uzun dönem ortalamalarından (ya da aylık
  klimatolojiden) arındırılır; her seriden korelasyondan önce doğrusal trend çıkarılır. Böylece iki
  değişkenin aynı anda trend göstermesi tek başına yüksek korelasyon üretmez.
- **İstatistik:** Pearson r; etkin örneklem büyüklüğü Bretherton vd. (1999):
  n_etkin = n (1 − r₁r₂)/(1 + r₁r₂); iki yönlü t testi, n_etkin − 2 serbestlik derecesi.
- **Anlamlılık:** Hücre haritaları ve il satırlarında BH-FDR (α = 0,10; il satırlarında aynı çiftin 81 il
  p değeri üzerinden). Bölge ve Türkiye satırlarında az sayıda test olduğundan düzeltmesiz p < 0,05.
- **Etiketler:** `beklenen_yonde`, `ters_yonde`, `anlamsiz`. "İlişki beklenen yönde" diye okunur.
- **GRACE yıllık ortalaması:** En az 9 ayı dolu yıllar kullanılır; 2017 ve 2018 (GRACE → GRACE-FO
  boşluğu) atılır.

## 7. Açıklama katmanı

Kod: `llm/`, bilgi tabanı `kb/`. Ayrıntı: [`llm/README.md`](../llm/README.md).
v0.1'de "Soru sor" sayfası **yol haritası** özelliğidir: çalışır ve her çıktısı doğrulanır, ama gerçek bir
LLM ile ölçeklenebilirliği henüz sınanmamıştır.

1. **Plan:** Kullanıcının sorusu bir süreç kartına (ör. kuraklık: belirti toprak nemi; olası ilişkili
   değişkenler yağış, sıcaklık, buharlaşma), bir bölgeye (il, bölge ya da Türkiye) ve bir mevsime
   çevrilir. LLM ayarlıysa yalnız katalogdaki kimliklerden **seçim** yapar ve seçimi kodda doğrulanır;
   değilse anahtar kelime eşleştirmesi kullanılır. Planın gerekçesi kullanıcıya gösterilir.
2. **Kanıt:** Plana uyan L3 satırları ve L4 çiftleri analiz paketinden okunur; her birine bir kanıt
   kimliği verilir. Seçilen düzeyde satır yoksa daha geniş bölgeye düşülür ve bu açıkça belirtilir.
   Bu adım sayı üretmez; değerleri paketten olduğu gibi kopyalar.
3. **Bulgular metni:** LLM ya da şablon tarafından yazılır. Sayı içeren her cümle bir kanıt kimliğine
   (`[ref:…]`) bağlanır.
4. **Doğrulayıcı:** Metin yayımlanmadan önce denetlenir: (i) metindeki her sayı, gösterilen basamağa
   yuvarlanmış haliyle kanıtlardaki bir sayıya eşit olmalı; (ii) her kanıt bağlantısı gerçek bir kanıta
   işaret etmeli; (iii) sayı içeren her cümle bir kanıta bağlı olmalı. Geçemeyen LLM metni düzeltme
   talimatıyla en fazla iki kez yeniden üretilir; yine geçemezse şablon metin gösterilir.
5. **Yöntem paragrafı, veri atıfları ve kaynakça** LLM'e yazdırılmaz; kanıtların meta verisinden şablonla
   üretilir.

## 8. Doğrulama

Ayrıntılar [`dogrulama.md`](dogrulama.md)'dedir: NASA Giovanni ile alan ortalaması karşılaştırması, L2
akıl kontrolü (sıcaklık trendinin işareti ve büyüklüğü, yağış ürünlerinin uyumu, GRACE), anlamlılık
kuralının önce/sonra etkisi ve bilinen veri boşlukları. Kodun her katmanı sentetik verilerle birim
testlerinden geçer; sentetik verideki bilinen eğim ve ilişkiler geri bulunur.

## 9. Sınırlılıklar

- **Model ürünleri gözlem değildir.** MERRA-2 ve GLDAS sonuçları modelin fiziğini ve zorlama verisini
  yansıtır. GLDAS'ta zorlama verisinin homojen olmayabileceği bilinmektedir (4.6).
- **Çözünürlük.** 0,25° (yaklaşık 25 km) hücreler küçük illerde birkaç hücreye düşer; GRACE'in gerçek
  çözünürlüğü daha kabadır (yaklaşık 300 km) ve il düzeyinde yorumlanmamalıdır.
- **Kısa seriler.** 25 yıllık seride birçok değişkende gereken gözlem süresi seriden uzundur; anlamsız bir
  trend "değişim yok" anlamına gelmez.
- **İnsan etkisi modelde yoktur.** Sulama, yeraltı suyu çekimi ve barajlar GLDAS'ta temsil edilmez.
- **İlişki, neden değildir.** L4 korelasyonları ortak bir üçüncü etkenden de kaynaklanabilir; trend
  giderme bunu azaltır ama ortadan kaldırmaz.
- **Kademe 2** sonuçları bağımsız veriyle karşılaştırılmadan yayımlanmamalıdır.
- **Eşik seçimleri** (α_FDR = 0,10; bölge satırlarında p < 0,05; eksik veri %20; en az 12 yıl) yöntemsel
  kararlardır; farklı eşikler farklı sayıda anlamlı sonuç verir.

## 10. Kaynakça

### Yöntem

- Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate: a practical and powerful
  approach to multiple testing. *Journal of the Royal Statistical Society B*, 57(1), 289–300.
- Bretherton, C. S., Widmann, M., Dymnikov, V. P., Wallace, J. M., & Bladé, I. (1999). The effective number
  of spatial degrees of freedom of a time-varying field. *Journal of Climate*, 12(7), 1990–2009.
- Hamed, K. H., & Rao, A. R. (1998). A modified Mann-Kendall trend test for autocorrelated data.
  *Journal of Hydrology*, 204(1–4), 182–196.
- Kendall, M. G. (1975). *Rank Correlation Methods* (4th ed.). Griffin.
- Mann, H. B. (1945). Nonparametric tests against trend. *Econometrica*, 13(3), 245–259.
- Sen, P. K. (1968). Estimates of the regression coefficient based on Kendall's tau. *Journal of the
  American Statistical Association*, 63(324), 1379–1389.
- Theil, H. (1950). A rank-invariant method of linear and polynomial regression analysis.
  *Proceedings of the Royal Netherlands Academy of Sciences*, 53, 386–392.
- Weatherhead, E. C., et al. (1998). Factors affecting the detection of trends: Statistical considerations
  and applications to environmental data. *Journal of Geophysical Research*, 103(D14), 17149–17161.
- Wilks, D. S. (2016). "The stippling shows statistically significant grid points": How research results
  are routinely overstated and overinterpreted, and what to do about it. *Bulletin of the American
  Meteorological Society*, 97(12), 2263–2273.

### Veri

Her NASA ürünü için DOI: [`CITATION.cff`](../CITATION.cff) (`references`) ve
[`data/catalog.yaml`](../data/catalog.yaml). Paketteki her dosya kendi kaynağının DOI'sini `doi`
alanında taşır.
