# Giovanni doğrulaması

İşlenmiş 0,25° küplerimiz (`cache/processed/turkiye/`) NASA Giovanni'nin
"Time Series, Area-Averaged" çıktısıyla karşılaştırıldı. Amaç: indirme, kesme, birim dönüşümü ve
ızgaraya getirme adımlarının değerleri bozmadığını göstermek.

- **Araç:** `python -m data.check_giovanni <csv> --degisken <ad> --urun <kod> --giovanni-donusum <dönüşüm>`
- **Bizim seri:** Kutunun içinde merkezi kalan hücrelerin cos(enlem) ağırlıklı ortalaması (`data.regions.area_mean`).
- **Giovanni serisi:** Bizim birime çevrildi (`mm_saat_to_mm_ay`, `K_to_C`, `kg_m2_s_to_mm_ay`).
- **Kutu:** 40,5°D–42,0°D, 39,5°K–40,5°K (batı, güney, doğu, kuzey = 40.5, 39.5, 42, 40.5). CSV'deki
  "User Bounding Box" satırından okundu. Kutu tamamen karada, bu yüzden bizim Türkiye kara maskemiz
  burada hücre düşürmüyor (24 hücre).
- **Giovanni CSV'leri:** 2026-11-14'te indirildi (`cache/giovanni_*.csv`, git dışında).
- **Fark:** biz − Giovanni, bizim birimimizle.

| Değişken | Ürün | Kutu (B, G, D, K) | Dönem | N (ay) | Korelasyon | Ortalama fark | RMSE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `yagis` | GPM_3IMERGM 07 (GPM) | 40.5, 39.5, 42, 40.5 | 2001-01 … 2025-09 | 297 | 1,0000 | +0,001 mm/ay | 0,002 mm/ay |
| `sicaklik_2m` | M2TMNXSLV 5.12.4 (MERRA2) | 40.5, 39.5, 42, 40.5 | 2001-01 … 2025-12 | 300 | 1,0000 | −0,031 °C | 0,048 °C |
| `yagis` | GLDAS_NOAH025_M 2.1 (GLDAS) | 40.5, 39.5, 42, 40.5 | 2001-01 … 2025-12 | 300 | 0,9956 | +0,182 mm/ay | 3,154 mm/ay |
| `yagis` (2025-12 hariç) | GLDAS_NOAH025_M 2.1 (GLDAS) | 40.5, 39.5, 42, 40.5 | 2001-01 … 2025-11 | 299 | 1,0000 | +0,000 mm/ay | 0,000 mm/ay |

Ortalamalar (biz / Giovanni):
- GPM yağış: 57,898 / 57,897 mm/ay
- MERRA-2 sıcaklık: 5,146 / 5,176 °C
- GLDAS yağış: 74,350 / 74,168 mm/ay

## Yorum

- **GPM yağış:** Seriler birebir aynı; fark yuvarlama düzeyinde. IMERG 0,1° hücrelerinin 0,25°'ye
  ortalanması ve mm/saat → mm/ay dönüşümü (ayın gün sayısıyla) değerleri değiştirmiyor. Final ürünün
  gecikmesi yüzünden iki seri de 2025-09'da bitiyor.
- **MERRA-2 sıcaklık:** Korelasyon 0,99999. Bizim seri ortalamada 0,03 °C daha soğuk. Neden şu:
  Giovanni ortalamayı MERRA-2'nin kendi 0,5° × 0,625° hücreleriyle alıyor ("Data Bounding Box"
  40,625–41,875 D, 39,5–40,5 K). Biz ise önce 0,25° ızgaraya aktarıp sonra kutuyu kesiyoruz. Kutu
  kenarındaki hücreler iki yöntemde farklı ağırlık alıyor. Fark trend analizi açısından önemsiz;
  sabit bir kayma, zamanla değişmiyor.
- **GLDAS yağış:** 2001-01 … 2025-11 arasındaki 299 ay birebir aynı (GLDAS'ın kendi ızgarası 0,25°
  olduğu için bizim ızgarayla aynı 24 hücre kullanılıyor). Tablodaki RMSE'nin tamamı **tek bir aydan**
  geliyor:
  - 2025-12'de bizim değer 108,7 mm/ay, Giovanni 54,1 mm/ay.
  - Bizim ham OPeNDAP kesitimiz (`GLDAS_NOAH025_M.A202512.021.nc`, 2026-11-14 indirildi) gerçekten
    4,06e-5 kg m⁻² s⁻¹ veriyor; Giovanni 2,02e-5. Yani fark bizim işleme adımlarımızdan gelmiyor.
  - CMR'de bu granül revizyon 3 (2025-11 granülü revizyon 2). En olası açıklama: Giovanni'nin
    önbelleğindeki 2025-12 dosyası ile bugün arşivden aldığımız dosya farklı sürümler. Bu
    **doğrulanmadı**; GES DISC'e sorulabilir.
  - Öneri: GLDAS'ın 2025-12 ayını kullanan analizlerde bu belirsizlik not edilsin. Ayın bir sonraki
    indirmede değişip değişmediği kontrol edilsin.
  - Karar: değer silinmedi, işaretlendi. `yagis__GLDAS.nc` dosyasında ve yayın paketindeki kopyasında
    `bilinen_sorunlar` attr'ı var. Kaynak: `data/catalog.yaml` kaydı; `harmonize` bu notu dosyaya taşır.

### GLDAS 2025-12: bağımsız ürünlerle karşılaştırma

Aynı kutu (40.5, 39.5, 42, 40.5), bizim işlenmiş dosyalarımız. Aralık ortalaması 2001–2024 arasındaki
24 Aralık ayından hesaplandı.

| Ürün | 2025-12 (mm/ay) | Aralık ortalaması 2001–2024 (mm/ay) | Std. sapma | Min … maks |
| --- | --- | --- | --- | --- |
| GLDAS (bizim) | 108,7 | 83,8 | 38,3 | 31,1 … 167,5 |
| GLDAS (Giovanni) | 54,1 | — | — | — |
| MERRA-2 (M2TMNXFLX `PRECTOT`) | 63,1 | 56,4 | 22,8 | 23,9 … 109,5 |
| GPM IMERG Final | — (henüz yok, ürün 2025-09'da bitiyor) | 62,0 | 24,8 | 22,5 … 125,3 |

- **Mutlak değer:** MERRA-2'nin 2025-12 değeri (63,1) Giovanni'nin değerine (54,1) daha yakın.
  Bizim değerden (108,7) 45,6 mm/ay, Giovanni'ninkinden 9,0 mm/ay uzak.
- **Ama bu tek başına karar vermeye yetmez.** GLDAS'ın Aralık ortalaması bu kutuda MERRA-2'ninkinden
  yaklaşık 1,5 kat yüksek (83,8 / 56,4). Her ürünü kendi Aralık ortalamasıyla karşılaştırınca:
  - MERRA-2 2025-12, ortalamanın +0,3 std. sapma üstünde (biraz yağışlı bir Aralık).
  - Bizim GLDAS değeri +0,6 std. sapma üstünde.
  - Giovanni'nin GLDAS değeri −0,8 std. sapma altında.
  - İki GLDAS değeri de GLDAS'ın kendi Aralık aralığı (31–168 mm/ay) içinde kalıyor.
- **Sonuç:** MERRA-2 "ortalamadan biraz yağışlı bir Aralık" diyor. Bu yön bizim değerle (ortalamanın
  üstü) uyumlu, Giovanni'nin değeriyle (ortalamanın altı) değil. Mutlak değerde ise MERRA-2 Giovanni'ye
  daha yakın. Hangi GLDAS değerinin doğru olduğu bu karşılaştırmayla **belirlenemiyor**. GPM Final
  2025-12 yayımlanınca (yaklaşık 3,5 ay gecikmeyle) yeniden bakılmalı.
- **Kara maskesi:** Kutu tamamen karada olduğu için maskenin etkisi yok. Kıyıya ya da sınıra yakın
  kutularda Giovanni deniz ve komşu ülke hücrelerini de ortaladığı için farklar büyüyebilir.

## Kapsam

Yalnız bir kutu ve üç değişken × ürün karşılaştırıldı (yayın paketinde Kademe 1'deki dosyaların bir
kısmı). Diğer Kademe 1 dosyaları (`sicaklik_2m__GLDAS`, `yagis__MERRA2`, `toprak_nemi__GLDAS`,
`kar_ortusu__MOD10CM`, `kar_su_esdegeri__GLDAS`, `ndvi__MOD13C2`, `toplam_su_depolama__GRACE`) için
Giovanni karşılaştırması henüz yapılmadı.

## Bilinen boşluklar

### Kar örtüsü (`kar_ortusu__MOD10CM`): 5 tamamen NaN ay

Şu 5 ayda Türkiye kutusunun tamamı NaN: **2001-06, 2002-03, 2003-12, 2016-02, 2022-10**.

- **Kaynak arşivde, işlemede değil:**
  - NASA CMR'de (`earthaccess.search_data`, `MOD10CM` sürüm 61) bu 5 ayın hiçbiri için granül yok
    (2026-11-14). Karşılaştırma için 2016-03'te granül var.
  - Yerel ham kesitlerde (`cache/raw/MOD10CM/`) de bu aylar yok.
  - Yani ay, işleme sırasında düşmedi; NSIDC'de o ay için aylık ürün üretilmemiş.
- **Olası neden:** O aylarda MODIS Terra'nın veri kesintileri. **Doğrulanmadı**, ama aylık ürünün hiç
  olmaması bununla uyumlu.
- **Etkisi:**
  - L1'de bu aylar NaN; değer uydurulmadı ya da doldurulmadı.
  - L2/L3'te eksik veri kuralı (mevsimde 1 eksik ay → NaN) 2003-12 yüzünden **2004 kışını**, 2016-02
    yüzünden **2016 kışını** ve 2002-03 yüzünden **2002 ilkbaharını** düşürüyor.
  - Yıllık seriler etkilenmiyor (yılda 1 eksik ay < 3).
  - Kar örtüsü trendleri o kış ve ilkbaharlar olmadan hesaplanıyor.

### Diğer beklenen boşluklar

- **`yagis__GPM`:** 2025-10 … 2025-12 NaN. IMERG Final ürünü yaklaşık 3,5 ay gecikmeyle yayımlanıyor.
- **`toplam_su_depolama__GRACE`:** 35 tamamen NaN ay. GRACE batarya yönetimi kaynaklı eksik aylar ve
  2017-07 … 2018-05 GRACE → GRACE-FO boşluğu. Eksik ay eşiği için bkz. sözleşme 2.1.

## L2 akıl kontrolü (2026-11-14, ilk sürüm)

> Bu bölümdeki anlamlılık sayıları **eski kurala** (yalnız `p_fdr ≤ 0,10`) ve GRACE için eski eksik veri
> eşiğine göredir. Güncel sayılar: aşağıdaki "Anlamlılık kuralı ve GRACE eşiği" bölümü.

`python -m stats.l2 --surum v0.1` çıktısı (`outputs/trend-dedektifi-turkiye-v0.1/L2_trend/`), Türkiye
kara hücreleri (1287–1303 hücre), 2001–2025. Eğimler Sen eğimi, anlamlılık BH-FDR α = 0,10.
Kaynak: `L2_trend/OZET.csv` ve `*__kaynak_uyumu.nc`.

### Sıcaklık

| Ürün | Yıllık medyan eğim (°C/10 yıl) | p10 … p90 | Anlamlı artan hücre |
| --- | --- | --- | --- |
| MERRA2 `sicaklik_2m` | 0,68 | 0,57 … 0,86 | %100 |
| GLDAS `sicaklik_2m` | 1,00 | — | %90,2 |

- **MERRA2:** Mevsimlere göre kış 1,07, sonbahar 0,79, yaz 0,52, ilkbahar 0,48 °C/10 yıl. İlkbaharda
  yalnız %0,6 hücre anlamlı; yıllar arası oynaklık büyük olduğu için. MERRA2 değeri, 2001–2025 için
  Türkiye'de beklenen ısınmayla uyumlu (beklenti 0,3–0,6; biraz üstünde).
- **Kaynak uyumu, yıllık:** 2/2 %89,6. İşaret uyumu 1 (iki ürün aynı işaret) %97,2.
- **GLDAS:** MERRA2'den yaklaşık %50 hızlı ısınıyor (aşağıda uyarı 1).

### Yağış uyumu (GPM, GLDAS, MERRA2)

| Ürün | Yıllık medyan eğim (mm/yıl / 10 yıl) | Anlamlı azalan hücre |
| --- | --- | --- |
| GPM | −15,1 | %0,1 |
| GLDAS | −38,8 | %10,5 |
| MERRA2 | +2,2 | %13,5 anlamlı azalan, %1,5 anlamlı artan |

- **Kaynak uyumu, yıllık** (ortak dönem 2001-01 … 2025-09): 0/3 %84,7, 1/3 %14,6, 2/3 %0,2, 3/3 %0.
  Yani üç ürün aynı hücrede birlikte anlamlı trend göstermiyor.
- **İşaret uyumu** (anlamlılık şartı yok): Üç ürünün aynı işarette olduğu hücre oranı yıllıkta
  %37,5, kışta %84,7, sonbaharda %79,7, yazda %67,2, ilkbaharda %39,5.
- **Sonuç:** Yağış trendi ürün seçimine çok duyarlı. Tek ürünle verilen yağış trendi "kaynaklar
  uyuşmuyor" notuyla sunulmalı.

### GRACE

`toplam_su_depolama__GRACE`: yıllık medyan **−8,0 cm/10 yıl**, hücrelerin **%89,1**'inde anlamlı
azalma. Türkiye'de bilinen yeraltı suyu kaybıyla aynı yönde ve büyüklükte. GRACE 2002-04'te başlıyor;
GRACE/GRACE-FO arasındaki boşluk yılları eksik veri kuralıyla düşüyor.

### Uyarılar (L2 dosyalarında `trend_uyarisi` attr'ı)

Değerler silinmedi. Uyarılar trend dosyalarının attrs'ında ve `OZET.csv` içinde.

1. **GLDAS zorlama verisi** (`sicaklik_2m`, `yagis`, `taban_akisi`, `yuzey_akisi`):
   - Sıcaklık eğimi MERRA2'nin yaklaşık 1,5 katı (1,00 / 0,68).
   - Yağış eğimi GPM'in yaklaşık 2,5 katı negatif (−38,8 / −15,1).
   - `taban_akisi` −25,6 mm/yıl / 10 yıl.
   - GLDAS-2.1 zorlama verisi homojen olmayabilir. Trend için MERRA2/GPM tercih edilmeli.
   - `yagis__GLDAS` 2025-12 sorunu (`bilinen_sorunlar`) da L2'ye taşındı, ama bu farkı tek başına
     açıklamaz.
2. **MODIS yüzey sıcaklığı (MOD11C3):**
   - Gündüz +0,03 °C/10 yıl, anlamlı hücre neredeyse yok (artan %0,2, azalan %0,4).
   - Gece +0,81 °C/10 yıl, %99,8 anlamlı artan.
   - Bu kadar büyük gündüz–gece farkı Terra sensör kaymasından kaynaklanıyor olabilir. **Doğrulanmadı**;
     gündüz–gece farkı yorumlanmadan önce kontrol edilmeli.
3. **NDVI / EVI kış serisi:**
   - Kış mevsiminde yalnız 791 kara hücresinde trend var (yazda 1303).
   - Kar ve bulut yüzünden kış ayları eksik; eksik veri kuralı (mevsimde 1 eksik ay → NaN) bu kışları
     düşürüyor.
   - Yıllık NDVI da 1058 hücreyle sınırlı, çünkü yılda 3 ay eksikse yıl düşüyor.

### Diğer gözlemler

- **MK yedeği:** Hamed-Rao tanımsız olduğu için düzeltmesiz MK'ye düşülen hücreler bazı dosyalarda
  sık. Örnekler: `ozgul_nem_2m` yıllıkta 182/1303, MERRA2 sıcaklık sonbaharda 160, `aerosol` ve
  `ruzgar_u_10m` kışta yaklaşık 125. Sayılar `OZET.csv` içindeki `mk_yedek_hucre` sütununda.
- **Makul görünenler:** NDVI %83 hücrede artış. Su buharı ve özgül nem hemen her hücrede artış. Ozon,
  bulut ve deniz seviyesi basıncında anlamlı hücre yok.
- **Tamamen NaN dosya ya da mevsim yok.** Birim sorunu görülmedi.

## Anlamlılık kuralı ve GRACE eşiği (2026-11-14, güncelleme)

Kişi 2 ile alınan karar üç değişiklik getirdi:
- **(a) Anlamlılık:** `anlamli = 1` için artık `p_fdr ≤ 0,10` **ve** %95 genişletilmiş GA'nın sıfırı
  dışlaması gerekiyor. Kural tek yerde: `stats/trend_tests.anlamli_kural`.
- **(c) GRACE eksik veri eşiği:** Yıllıkta en az 6, mevsimde en az 2 geçerli ay.
- **Türkiye satırı:** L3 bölge CSV'lerine eklendi (`duzey = "ulke"`).

L2'de yalnız GRACE yeniden hesaplandı. Diğer dosyalarda `anlamli`, kayıtlı `p_fdr` ve GA'dan yeniden
türetildi. L3 baştan üretildi.

### Önce / sonra: anlamlı sayıları

- Hücre = Türkiye kara hücreleri (L2). İl = 81 il (L3).
- "5 mevsim" sütunları, her mevsimdeki anlamlı sayılarının toplamıdır.
- GRACE'te "sonra" değerine eksik veri eşiği değişikliği de dahil.

| Dosya | Hücre, yıllık | Hücre, 5 mevsim | İl, yıllık | İl, 5 mevsim |
| --- | --- | --- | --- | --- |
| `sicaklik_2m__MERRA2` | 1303 → 1303 | 4795 → 4259 | 81 → 81 | 308 → 271 |
| `toplam_su_depolama__GRACE` | 1172 → 542 | 5939 → 3333 | 75 → 38 | 377 → 225 |
| `yagis__GPM` | 1 → 1 | 413 → 219 | 0 → 0 | 14 → 7 |
| `yagis__GLDAS` | 144 → 135 | 785 → 456 | 10 → 7 | 38 → 22 |
| `yagis__MERRA2` | 196 → 155 | 707 → 512 | 14 → 11 | 46 → 34 |
| `ruzgar_hizi__GLDAS` | 1012 → 427 | 4843 → 2785 | 66 → 25 | 311 → 173 |
| `no2__OMI` | 813 → 322 | 2254 → 1353 | 66 → 14 | 210 → 118 |

- **Sıcaklık:** Yıllık sonuç değişmedi; düşüş mevsimlik serilerde. İlkbaharda GA sıfırı kapsıyor.
- **En çok düşenler:** GRACE, `ruzgar_hizi` ve NO2. Bunlarda MK p küçüktü, ama otokorelasyon yüzünden
  GA geniş.

### GRACE

- **Seri:** Yıllık seride artık **22 yıl** var (2002–2025). Yalnız GRACE → GRACE-FO boşluğu olan 2017 ve
  2018 eksik; önce 16 yıldı.
- **GA genişliği:**
  - Hücre medyanı 16,2 cm/10 yıl.
  - n_etkin = 3'te takılan hücre oranı %9; önceki hesapta %21'di.
  - İl medyanı 13,9 cm/10 yıl. Önce Osmaniye'de GA 150 cm/10 yıl genişliğindeydi.
- **Anlamlı azalma:** Hücrelerin %41,3'ünde (önce %89,1), 38 ilde (önce 75).
- **Türkiye geneli:** −7,5 cm/10 yıl, GA [−12,3, −2,7], anlamlı.

En çok su kaybeden 5 il (yıllık, cm/10 yıl):

| İl | Eğim | GA | n_etkin | Anlamlı | Not |
| --- | --- | --- | --- | --- | --- |
| Karaman | −17,6 | −115,4 … 79,2 | 3,0 | 0 | GA hâlâ çok geniş |
| Osmaniye | −16,7 | −28,2 … −3,1 | 5,4 | 1 | |
| Hatay | −16,5 | −34,2 … 3,1 | 4,3 | 0 | GA sıfırı az farkla kapsıyor |
| Mersin | −16,4 | −48,8 … 14,3 | 3,6 | 0 | |
| Kilis | −15,6 | −28,4 … −2,1 | 5,2 | 1 | az hücre |

GRACE düşüşü doğrusal değil, hızlanıyor. Bu yüzden artık otokorelasyonu yüksek ve bazı illerde GA hâlâ
geniş. Bu bir hata değil: doğrusal trend tanımının sınırını gösteriyor.

### Türkiye geneli (L3 bölge CSV'si, `duzey = "ulke"`, yıllık)

| Değişken | Eğim | %95 GA | Anlamlı | Anlamlı hücre oranı |
| --- | --- | --- | --- | --- |
| Sıcaklık MERRA2 | +0,70 °C/10 yıl | 0,47 … 0,99 | 1 | 1,00 |
| Sıcaklık GLDAS (uyarılı) | +0,98 °C/10 yıl | 0,69 … 1,29 | 1 | 0,82 |
| GRACE | −7,5 cm/10 yıl | −12,3 … −2,7 | 1 | 0,42 |
| Yağış GPM (2001–2024) | −15,1 mm/yıl/10 yıl | −63,9 … 31,1 | 0 | 0,00 |
| Yağış GLDAS (uyarılı) | −42,7 mm/yıl/10 yıl | −88,1 … 4,5 | 0 | 0,10 |
| Yağış MERRA2 | −16,8 mm/yıl/10 yıl | −54,5 … 28,2 | 0 | 0,12 |
| NDVI | +0,018 /10 yıl | 0,009 … 0,027 | 1 | 0,68 |

- **Sıcaklık, mevsimler** (MERRA2, °C/10 yıl): kış 1,16, sonbahar 0,79, yaz 0,59 (anlamlı); ilkbahar
  0,58 (anlamlı değil).
- **Yağış:** Türkiye ortalamasında üç ürünün de yıllık eğimi negatif, ama hiçbiri anlamlı değil.
  - Kaynak uyumu: k/m = 0/3, işaret uyumu 1,0.
  - Mevsimlerde işaret uyumu kış, yaz ve sonbaharda 1,0, ilkbaharda 0,67.
  - Kış ve sonbaharda üç ürün de azalma, yazda artma gösteriyor; hiçbiri anlamlı değil.
- **Yağış, il düzeyi (yıllık):** 0/3 73 il, 1/3 8 il. Üç ürünün aynı işarette olduğu il sayısı 29.
- **NDVI:** Türkiye genelinde anlamlı yeşillenme. Kışta anlamlı değil.

## Bulgu karnesi (2026-11-15)

`python -m stats.karne --surum v0.1` → `karne/` (kural: `docs/sozlesmeler.md` 2.4, `karne-v1`; sonuçlar görülmeden
sabitlendi, sonradan ayarlanmadı). Süre: trend 2,7 dk (12 015 satır), ilişki 1,1 dk (542 satır), toplam 3,8 dk.
L2/L3/L4'ün 96 dosyası karne üretiminden önce ve sonra bayt bayt aynı. Yeniden kurulan serilerin Sen eğimi L3
dosyalarıyla en çok 4,9·10⁻⁶ (göreli; CSV yuvarlaması) farklı.

**Türkiye × yıllık** (✓ geçti · ✗ kaldı · – uygulanamaz):

| Değişken | Ürün | Sen eğimi / 10 yıl | a kaynak | b karıştırma (p_perm) | c dönem | d α=0,05 | e veri | Uyarı | Güven |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sicaklik_2m | MERRA2 | +0,70 °C | ✓ 2/2 | ✓ 0,002 | ✓ | ✓ | ✓ (16 ≤ 25) | — | **YÜKSEK** |
| sicaklik_2m | GLDAS | +0,98 °C | ✓ 2/2 | ✓ 0,002 | ✓ | ✓ | ✓ | trend uyarısı | ORTA |
| toplam_su_depolama | GRACE | −7,55 cm | – tek kaynak | ✓ 0,008 | ✗ | ✓ | ✓ (18 ≤ 22) | — | **DÜŞÜK** |
| yagis | GPM | −15,1 mm | – | ✗ 0,47 | ✗ | ✗ | ✗ (59 > 24) | — | YOK (veri henüz yetmiyor) |
| yagis | GLDAS | −42,7 mm | – | ✓ 0,05 | ✗ | ✗ | ✗ (31 > 25) | trend uyarısı, bilinen sorun | YOK (veri henüz yetmiyor) |
| yagis | MERRA2 | −16,8 mm | – | ✗ 0,43 | ✗ | ✗ | ✗ (54 > 25) | — | YOK (veri henüz yetmiyor) |
| ndvi | MOD13C2 | +0,018 | – tek kaynak | ✓ 0,006 | ✓ | ✓ | ✓ | — | ORTA |

- **GRACE neden DÜŞÜK (kural değişmeden):** son 3 yıl çıkarılınca eğim −6,1 cm/10 yıl, anlamsız (ilk 3 yıl
  çıkarılınca −8,3, anlamlı). Seri 22 geçerli yıl; azalış son yıllarda hızlanmış ve kısaltılmış seride
  genişletilmiş güven aralığı sıfırı içeriyor. Yön sağlam, büyüklük ve anlamlılık son yıllara duyarlı.
- **Yağış:** üç üründe de işaret uyumu 1,00 (hepsi negatif) ama hiçbiri anlamlı değil; Weatherhead'e göre
  31–59 yıl veri gerekiyor.

**İller, MERRA2 sıcaklık yıllık:** 68 YÜKSEK · 5 ORTA (kaynak uyumu kaldı: GLDAS bu illerde anlamlı değil) ·
8 DÜŞÜK · 0 YOK. DÜŞÜK illerin hepsi aynı kuşakta (Bilecik, Bolu, Düzce, Eskişehir, Kocaeli, Kütahya, Sakarya,
Zonguldak) ve hepsinde son 3 yıl (2023–2025) çıkarılınca eğim ≈ +0,6'dan ≈ +0,4 °C/10 yıla iniyor ve anlamlılık
kayboluyor; karıştırma testi hepsinde geçiyor. Bu kuşakta ısınma sinyali büyük ölçüde son birkaç çok sıcak yıla
dayanıyor.

**Genel tablo:** il düzeyinde anlamlı 2 892 trendin 1 379'u DÜŞÜK. Bunların 1 352'si yalnız c'den (dönem
duyarlılığı) kalıyor; c'den kalan satırların **hiçbirinde işaret dönmüyor** (1 378/1 378 işaret korunuyor),
yalnız 22 yıla kısalan seride anlamlılık kayboluyor (449 son 3, 379 ilk 3, 550 ikisinde). Yani DÜŞÜK çoğunlukla
"yön belirsiz" değil, "kısa seride istatistiksel güç sınırda" demektir. YÜKSEK yalnız çok ürünlü değişkenlerde
mümkün (kural: tek kaynak en çok ORTA); il düzeyinde 145 YÜKSEK'in 143'ü MERRA2 sıcaklık (68 yıllık, 47 sonbahar, 16 yaz, 12 kış), 2'si MERRA2 sonbahar yağışı.

**İlişkiler (L4):** 81 YÜKSEK · 323 ORTA · 0 DÜŞÜK · 138 YOK.

| Satır | r (ham r) | a | b (p_perm) | c | d | e | Uyarı | Güven |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Çift 1 Türkiye (kış sıcaklığı ~ kar) | −0,90 (−0,93) | ✓ 2/2 | ✓ 0,002 | ✓ | ✓ (gecikme 1: −0,87) | ✓ | — | **YÜKSEK** |
| Çift 5 Türkiye (yaz sıcaklığı ~ buharlaşma) | −0,36 (−0,22) | – (anlamsız) | ✓ 0,058 | ✓ | ✓ | ✓ | Kademe 2, rejime bağlı | YOK (anlamsız) |
| Sıcaklık ~ GRACE, Türkiye yıllık (tek çift komutu) | −0,24 (−0,70) | – (anlamsız) | ✗ 0,31 | **✗** | ✓ | ✓ | — | YOK |

- Çift 1: 79 YÜKSEK satır (il ve bölge). Çift 2 tümü ORTA (mevsimlik seride gecikme testi uygulanamaz), çift 6
  tümü ORTA (MOD11C3 Kademe 2), çift 5'in ters yönlü il satırları ORTA (rejime bağlı çift + Kademe 2 kritik uyarı).
- Sıcaklık ~ GRACE: beklendiği gibi c kalıyor; ham −0,70 korelasyonunun büyük kısmı iki serinin aynı dönemde
  trendli olmasından geliyor (sahte korelasyon örneği).

## Sapma haritası v2: bağımsız doğrulama (2026-11-15, gece işi)

**Önceden tanımlı değişiklikler (v1 sonuçlarına bakılarak ayarlanmadı):** (1) tarım maskesi: MCD12C1 v061
`tarim_orani` = (%IGBP 12 + ½·%14)/100, 2021–2025 ortalaması; `tarim_orani < 0,3` → sulama izi NaN. Maske
regresyondan **sonra** uygulanır (regresyon v1'deki gibi bütün kara hücrelerinde). (2) 0,05° çözünürlük: NDVI
(MOD13C2) ve LST (MOD11C3) 0,05° CMG dosyaları, rakım SRTM 0,05°; yağış (GPM) ve T2M (MERRA-2) 0,25°'den en yakın
komşu. Bileşenler ve regresyon biçimi v1 ile aynı. Maskesiz 0,25° v2, v1 dosyasıyla birebir aynı (fark 0).

**Referans:** GFSAD1KCM v001 (2010 nominal, ~1 km), sulanan = sınıf 1 (Irrigation major) + 2 (Irrigation minor),
payda = kara pikselleri (1–5 ve 9; 0 = veri yok; User Guide v1, 2.2.4). Hedef hücre: sulanan oran ≥ 0,2 (sabit).
Maskeli ya da skorsuz hücre en düşük skoru alır. Referans sulama izi hesabına girmez (testle doğrulandı).

| Yapılandırma | Hücre | Hedef (taban oran) | ROC AUC | precision@%5 | Kaldıraç (p@5 / taban) |
| --- | --- | --- | --- | --- | --- |
| v1 (0,25°, maskesiz) | 1 302 | 105 (%8,1) | 0,577 | 0,061 | 0,75 |
| maske (0,25°) | 1 302 | 105 (%8,1) | 0,545 | 0,152 | 1,88 |
| 0,05° (maskesiz) | 32 472 | 3 151 (%9,7) | 0,581 | 0,121 | 1,25 |
| maske + 0,05° | 32 472 | 3 151 (%9,7) | 0,548 | 0,215 | 2,21 |
| *duyarlılık: maske 0,2 / 0,5 (0,25°)* | | | *0,571 / 0,504* | *0,136 / 0,167* | |
| *duyarlılık: maske 0,2 / 0,5 (0,05°)* | | | *0,556 / 0,534* | *0,213 / 0,205* | |

Rastgele beklenti: AUC 0,5; precision@%5 = taban oran.

- **AUC ≈ 0,55–0,58: yöntem sulanan alanı genel sıralamada çok zayıf ayırt ediyor.** Maske AUC'yi düşürüyor,
  çünkü GFSAD'ın sulanan dediği hücrelerin yalnız %38'i MCD12C1 tarım ≥ 0,3 maskesinin içinde kalıyor; kalan %62'si
  maskelenip en düşük skoru alıyor.
- **Listenin tepesi zenginleşiyor:** en yüksek %5'te isabet v1'de taban oranın altında (0,75×), maske + 0,05°'de
  taban oranın 2,2 katı. Katkı: çözünürlük 0,75× → 1,25×, maske 0,75× → 1,88×, ikisi birlikte 2,21×.
- *Tanı (önceden tanımlı yapılandırma değil):* yalnız tarım hücreleri içinde sulama izinin AUC'si 0,70 (0,25°) /
  0,67 (0,05°). Bileşen AUC'leri (maskesiz 0,05°): z_yesil 0,59, z_serin 0,55.

**En yüksek 10 küme (maske + 0,05°) ve referansın o noktadaki sınıfları** (tepe hücre, ±0,075° pencere):

| # | Tepe (K, D) | İl(ler) | Hücre | Tepe z | GFSAD sulanan oran (tepe / 3×3) | GFSAD sınıf karışımı |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 36,98 · 39,02 | Şanlıurfa | 85 | 4,12 | 0,16 / 0,22 | sulama majör %21, yağmur %78 |
| 2 | 36,98 · 40,12 | Şanlıurfa, Mardin | 165 | 4,04 | 0,00 / 0,00 | yağmur %99 |
| 3 | 37,67 · 33,27 | Konya | 74 | 2,65 | 0,00 / 0,00 | yağmur %80, tarım dışı %16 |
| 4 | 38,62 · 31,12 | Afyonkarahisar, Konya | 21 | 2,48 | 0,00 / 0,01 | yağmur %72 (küçük parçalar dahil), tarım dışı %25 |
| 5 | 38,42 · 33,02 | Konya, Aksaray | 48 | 2,22 | 0,00 / 0,00 | yağmur %99 |
| 6 | 39,38 · 43,67 | Ağrı, Van | 14 | 2,12 | **1,00** / 0,58 | sulama minör %58 |
| 7 | 38,98 · 43,33 | Van | 2 | 2,07 | 0,10 / 0,11 | tarım dışı %70 |
| 8 | 40,08 · 35,27 | Yozgat | 8 | 2,01 | 0,04 / 0,00 | tarım dışı %40, yağmur %60 |
| 9 | 38,48 · 38,27 | Malatya | 13 | 2,01 | **0,24** / 0,05 | yağmur %88 |
| 10 | 40,98 · 35,98 | Samsun, Amasya | 53 | 1,98 | 0,00 / 0,07 | tarım dışı %49, yağmur %45 |

GFSAD'a göre tepe hücresi hedef olan küme: 2/10 (6 ve 9).

**Referansın sınırı (yalnız yorum; yöntem değiştirilmedi):** GFSAD 2010, genel bilgiye göre yeraltı suyu ve
GAP sulamasının yoğun olduğu Konya ovasını ve Ceylanpınar–Viranşehir bölgesini neredeyse tamamen "yağmura dayalı"
sınıflıyor; Harran'da bile sulanan payı %21. Ürünün kendi kılavuzu sulanan/yağmura dayalı ayrımındaki belirsizliği
açıkça yazıyor; ayrıca 2010 haritası 2021–2025 tarım örtüsüyle aynı dönem değil. Bu yüzden düşük AUC'nin bir kısmı
referanstan kaynaklanıyor olabilir, ama bu kanıtlanmış değil. Genel bilgiye dayalı (bağımsız olmayan) bir
karşılaştırmada v2'nin ilk kümelerinin çoğu bilinen sulama alanlarına (Harran, Ceylanpınar, Konya ovası)
düşüyor; v1'de bu 10'da 1'di. Bu ikinci karşılaştırma kör değildir ve kanıt olarak kullanılmamalıdır.

## Büyüklük testleri (2026-11-15)

`python -m physics.buyukluk --surum v0.1` → `L4_iliski/buyukluk/`. Kural sözleşme 2.5'te (`buyukluk-v1`). Etiket ve güven
kuralları, bantlar ve eşikler gerçek veride çalıştırılmadan önce sabitlendi ve commit edildi (`9112ff0`); sonuç
görüldükten sonra hiçbiri değiştirilmedi. Süre: üç test, 81 il + 7 bölge + Türkiye, yaklaşık 40 sn. Aynı komut iki kez
çalıştırıldı; dosyalar bayt bayt aynı (sabit tohum). Paketteki mevcut 140 dosyanın md5'i değişmedi, yalnız
`buyukluk/` altında 7 yeni dosya var.
**Clausius-Clapeyron, özgül nem** (%/K; bant 5,9–7,3):

| Bölge | Yol | Gözlenen [%95 GA] | Beklenen bant | Etiket | Güven |
| --- | --- | --- | --- | --- | --- |
| Marmara | a_yillar_arasi | +4,42 [+1,54, +6,77] | +5,9 … +7,3 | belirsiz | YOK |
| Ege | a_yillar_arasi | +3,02 [-0,712, +5,91] | +5,9 … +7,3 | belirsiz | YOK |
| Akdeniz | a_yillar_arasi | +4,04 [+0,709, +6,05] | +5,9 … +7,3 | belirsiz | YOK |
| İç Anadolu | a_yillar_arasi | +3,11 [+0,0761, +5,78] | +5,9 … +7,3 | belirsiz | YOK |
| Karadeniz | a_yillar_arasi | +4,19 [+2,66, +5,59] | +5,9 … +7,3 | beklenenden küçük | ORTA |
| Doğu Anadolu | a_yillar_arasi | +3,04 [+0,213, +5,13] | +5,9 … +7,3 | belirsiz | YOK |
| Güneydoğu Anadolu | a_yillar_arasi | +2,65 [-1,64, +6,5] | +5,9 … +7,3 | belirsiz | YOK |
| **Türkiye** | a_yillar_arasi | +4,47 [+1,71, +6,6] | +5,9 … +7,3 | belirsiz | YOK |
| Marmara | b_trend_orani | +5,34 [+3,19, +10,7] | +5,9 … +7,3 | belirsiz | YOK |
| Ege | b_trend_orani | +5,39 [+2,39, +15,9] | +5,9 … +7,3 | belirsiz | YOK |
| Akdeniz | b_trend_orani | +4,36 [+1,3, +8,45] | +5,9 … +7,3 | belirsiz | YOK |
| İç Anadolu | b_trend_orani | +5,91 [+2,79, +12,6] | +5,9 … +7,3 | belirsiz | YOK |
| Karadeniz | b_trend_orani | +5,93 [+3,51, +10,6] | +5,9 … +7,3 | belirsiz | YOK |
| Doğu Anadolu | b_trend_orani | +2,98 [+0,403, +7,96] | +5,9 … +7,3 | belirsiz | YOK |
| Güneydoğu Anadolu | b_trend_orani | +5,01 [+1,66, +11,7] | +5,9 … +7,3 | belirsiz | YOK |
| **Türkiye** | b_trend_orani | +4,84 [+2,12, +9,54] | +5,9 … +7,3 | belirsiz | YOK |

**Clausius-Clapeyron, su buharı kolonu** (%/K):

| Bölge | Yol | Gözlenen [%95 GA] | Beklenen bant | Etiket | Güven |
| --- | --- | --- | --- | --- | --- |
| Marmara | a_yillar_arasi | +4,8 [+1,06, +7,91] | +5,9 … +7,3 | belirsiz | YOK |
| Ege | a_yillar_arasi | +4,22 [+0,238, +7,7] | +5,9 … +7,3 | belirsiz | YOK |
| Akdeniz | a_yillar_arasi | +5,56 [+2,39, +8,65] | +5,9 … +7,3 | belirsiz | YOK |
| İç Anadolu | a_yillar_arasi | +4,63 [+2,24, +6,76] | +5,9 … +7,3 | belirsiz | YOK |
| Karadeniz | a_yillar_arasi | +5,33 [+3,29, +6,98] | +5,9 … +7,3 | beklenen büyüklükle tutarlı | DÜŞÜK |
| Doğu Anadolu | a_yillar_arasi | +4 [+0,542, +6,84] | +5,9 … +7,3 | belirsiz | YOK |
| Güneydoğu Anadolu | a_yillar_arasi | +4,37 [+0,306, +8,25] | +5,9 … +7,3 | belirsiz | YOK |
| **Türkiye** | a_yillar_arasi | +5,71 [+2,98, +8,32] | +5,9 … +7,3 | belirsiz | YOK |
| Marmara | b_trend_orani | +6,05 [+3,06, +13,1] | +5,9 … +7,3 | belirsiz | YOK |
| Ege | b_trend_orani | +6,11 [+3,52, +18] | +5,9 … +7,3 | belirsiz | YOK |
| Akdeniz | b_trend_orani | +6,22 [+2,71, +11,7] | +5,9 … +7,3 | belirsiz | YOK |
| İç Anadolu | b_trend_orani | +7,88 [+4,23, +15,5] | +5,9 … +7,3 | belirsiz | YOK |
| Karadeniz | b_trend_orani | +6,14 [+3,41, +13,1] | +5,9 … +7,3 | belirsiz | YOK |
| Doğu Anadolu | b_trend_orani | +4,35 [+1,64, +9,94] | +5,9 … +7,3 | belirsiz | YOK |
| Güneydoğu Anadolu | b_trend_orani | +6,1 [+2,49, +11,5] | +5,9 … +7,3 | belirsiz | YOK |
| **Türkiye** | b_trend_orani | +5,77 [+3,17, +10,2] | +5,9 … +7,3 | belirsiz | YOK |

**Su bütçesi** (ortalama: mm/yıl; trend: (mm/yıl)/10 yıl; bant 0 ± P'nin %10'u):

| Bölge | Yol | Gözlenen [%95 GA] | Beklenen bant | Etiket | Güven |
| --- | --- | --- | --- | --- | --- |
| Marmara | ortalama | +45,5 [-23,2, +111] | -78 … +78 | beklenen büyüklükle tutarlı | ORTA |
| Marmara | trend | -36,2 [-98,8, +21,5] | -78 … +78 | beklenen büyüklükle tutarlı | ORTA |
| Ege | ortalama | -10,8 [-67, +47,8] | -69,3 … +69,3 | beklenen büyüklükle tutarlı | ORTA |
| Ege | trend | -13,9 [-73,8, +41,3] | -69,3 … +69,3 | beklenen büyüklükle tutarlı | ORTA |
| Akdeniz | ortalama | -69,5 [-130, -8,83] | -69,7 … +69,7 | beklenen büyüklükle tutarlı | ORTA |
| Akdeniz | trend | -10 [-63,9, +40,7] | -69,7 … +69,7 | beklenen büyüklükle tutarlı | ORTA |
| İç Anadolu | ortalama | +95,5 [+48,9, +141] | -51,6 … +51,6 | beklenen büyüklükle tutarlı | DÜŞÜK |
| İç Anadolu | trend | +0,0106 [-35,1, +38,6] | -51,6 … +51,6 | beklenen büyüklükle tutarlı | ORTA |
| Karadeniz | ortalama | -102 [-175, -26,2] | -87,4 … +87,4 | beklenen büyüklükle tutarlı | ORTA |
| Karadeniz | trend | -12,6 [-80,7, +52,4] | -87,4 … +87,4 | beklenen büyüklükle tutarlı | ORTA |
| Doğu Anadolu | ortalama | +109 [+44,1, +176] | -64 … +64 | beklenen büyüklükle tutarlı | ORTA |
| Doğu Anadolu | trend | +6,09 [-35,4, +49] | -64 … +64 | beklenen büyüklükle tutarlı | ORTA |
| Güneydoğu Anadolu | ortalama | -84,7 [-134, -34] | -58,8 … +58,8 | beklenen büyüklükle tutarlı | ORTA |
| Güneydoğu Anadolu | trend | +10,9 [-44,1, +63,8] | -58,8 … +58,8 | beklenen büyüklükle tutarlı | ORTA |
| **Türkiye** | ortalama | +14,1 [-39,8, +73,4] | -66,6 … +66,6 | beklenen büyüklükle tutarlı | ORTA |
| **Türkiye** | trend | -5,72 [-38,7, +28] | -66,6 … +66,6 | beklenen büyüklükle tutarlı | ORTA |

**Kar çizgisi** (m/10 yıl):

| Bölge | Yol | Gözlenen [%95 GA] | Beklenen bant | Etiket | Güven |
| --- | --- | --- | --- | --- | --- |
| Marmara | kis | — | — | hesaplanamadı (kar çizgisi yalnız 8 yılda tanımlı (< 13)) | YOK |
| Ege | kis | — | — | hesaplanamadı (kar çizgisi yalnız 2 yılda tanımlı (< 13)) | YOK |
| Akdeniz | kis | +116 [-45,3, +219] | +124 … +170 | belirsiz | YOK |
| İç Anadolu | kis | +174 [+27,1, +309] | +117 … +159 | belirsiz | YOK |
| Karadeniz | kis | +184 [+55, +354] | +167 … +228 | belirsiz | YOK |
| Doğu Anadolu | kis | +177 [+61,9, +265] | +187 … +255 | beklenen büyüklükle tutarlı | DÜŞÜK |
| Güneydoğu Anadolu | kis | +129 [+41,7, +199] | +128 … +175 | belirsiz | YOK |
| **Türkiye** | kis | +166 [+19,1, +285] | +165 … +225 | belirsiz | YOK |
| Marmara | ilkbahar | — | — | hesaplanamadı (kar çizgisi yalnız 0 yılda tanımlı (< 13)) | YOK |
| Ege | ilkbahar | — | — | hesaplanamadı (kar çizgisi yalnız 0 yılda tanımlı (< 13)) | YOK |
| Akdeniz | ilkbahar | — | — | hesaplanamadı (kar çizgisi yalnız 0 yılda tanımlı (< 13)) | YOK |
| İç Anadolu | ilkbahar | — | — | hesaplanamadı (kar çizgisi yalnız 0 yılda tanımlı (< 13)) | YOK |
| Karadeniz | ilkbahar | +97,9 [+7,74, +172] | +100 … +137 | belirsiz | YOK |
| Doğu Anadolu | ilkbahar | +114 [-18,3, +238] | +89,3 … +122 | belirsiz | YOK |
| Güneydoğu Anadolu | ilkbahar | — | — | hesaplanamadı (kar çizgisi yalnız 5 yılda tanımlı (< 13)) | YOK |
| **Türkiye** | ilkbahar | +123 [-24,9, +230] | +83,5 … +114 | belirsiz | YOK |

**İl düzeyi (81 il), etiket ve güven sayıları:**

| Test | Yol | Değişken | Etiket | Güven |
| --- | --- | --- | --- | --- |
| cc | a_yillar_arasi | ozgul_nem_2m | belirsiz 57, beklenenden küçük 15, beklenen büyüklükle tutarlı 9 | YOK 57, DÜŞÜK 15, ORTA 9 |
| cc | b_trend_orani | ozgul_nem_2m | belirsiz 81 | YOK 81 |
| cc | a_yillar_arasi | su_buhari_kolon | belirsiz 69, beklenen büyüklükle tutarlı 12 | YOK 69, DÜŞÜK 11, ORTA 1 |
| cc | b_trend_orani | su_buhari_kolon | belirsiz 81 | YOK 81 |
| kar_cizgisi | kis | kar_ortusu | hesaplanamadı 77, belirsiz 4 | YOK 81 |
| kar_cizgisi | ilkbahar | kar_ortusu | hesaplanamadı 80, belirsiz 1 | YOK 81 |

**Kısa okuma:**
- **Clausius-Clapeyron:** bütün bölge nokta tahminleri 7 %/K'nin altında. Yıllar arası yolda özgül nem 2,7–4,5,
  su buharı kolonu 4,0–5,7 %/K. Ama güven aralıkları çoğunlukla bandın 3 katından geniş: Türkiye yıllar arası satırında
  GA 4,89 / bant 1,4 = 3,5 kat, yani `belirsiz`. Trend oranı yolu (b) her yerde `belirsiz`, çünkü 25 yılda sıcaklık
  trendinin belirsizliği oranı çok genişletiyor. Tek ayırt edici satır Karadeniz, özgül nem: `beklenenden küçük`
  (+4,19 [+2,66, +5,59]), güven ORTA (nem Kademe 2). Karada bağıl nemin azalabileceği notu satırda yazılı;
  etiket değiştirilmedi.
- **Su bütçesi:** bütün satırlar kurala göre `beklenen büyüklükle tutarlı`. Ama bu güçlü bir kapanış değil:
  - 7 bölgenin 5'inde ortalama artığın nokta tahmini bandın dışında: İç Anadolu +95, Doğu Anadolu +109, Karadeniz
    −102, Güneydoğu Anadolu −85, Akdeniz −70 mm/yıl. Bu satırlar yalnız GA'nın bir ucu banda değdiği için "tutarlı".
  - Bant (P'nin %10'u) bir proje seçimidir.
  - Türkiye ortalaması kapanıyor: +14 [−40, +73] mm/yıl. Trend kapanışı her bölgede bandın içinde; Türkiye −5,7
    (mm/yıl)/10 yıl.
  - GLDAS akışlarındaki `trend_uyarisi` ve Kademe 2 uyarıları her satırda, bu yüzden güven en çok ORTA.
- **Kar çizgisi:**
  - Gözlenen yükselme +98 ile +184 m/10 yıl arasında. Beklenen de büyük, çünkü MERRA-2'de kış ısınması L3'te Türkiye
    için 1,16 °C/10 yıl.
  - Ama GA'lar bandın 3,4–8,4 katı geniş, satırlar `belirsiz`. Tek istisna Doğu Anadolu kış: `beklenen
    büyüklükle tutarlı`, güven DÜŞÜK. Bu satır sınırda: GA bandın 2,98 katı (eşik 3). İlk ya da son 3 yıl çıkınca
    ve GLDAS sıcaklığıyla etiket `belirsiz` oluyor.
  - İl düzeyinde 0,25° hücreler yükselti aralığını çözmeye yetmiyor: 162 il satırının 157'si `hesaplanamadı`.
  - Önceden seçildiği için 0,05° cache dosyaları kullanılmadı (yalnız paket okunur).

**Beklenmedik sonuçlar ve olası açıklamalar** (hangisinin geçerli olduğu belirlenmedi):
- *CC nokta tahminlerinin hep 7 %/K'nin altında olması:*
  - karada bağıl nemin azalması (Simmons vd. 2010; Byrne ve O'Gorman 2018);
  - yıllık ortalamanın farklı sıcaklıktaki mevsimleri karıştırması;
  - MERRA-2 nem alanının asimilasyonla sınırlanması;
  - Kademe 2 nem dosyalarının bağımsız doğrulamasının yapılmamış olması.
- *Su bütçesi artığının bölgeden bölgeye işaret değiştirmesi* (İç ve Doğu Anadolu artı; Güneydoğu Anadolu,
  Karadeniz ve Akdeniz eksi):
  - ölçülmeyen yeraltı suyu çekimi ya da sulama (GLDAS-2.1 Noah modellemez);
  - yağış, buharlaşma ve akış ürünlerinin bölgesel yanlılığı;
  - GRACE mascon çözünürlüğü (~300 km), komşu bölgeler ve denizle sızıntı;
  - bölge sınırlarının mascon sınırlarıyla örtüşmemesi.
- *Kar çizgisinde büyük ama çok belirsiz yükselme:*
  - 0,25° ızgarada dağ yamaçlarının yumuşaması;
  - kar örtüsünün yağış yıllarına da bağlı olması;
  - kışın yüzey sıcaklık azalma oranının 6,5 °C/km'den düşük olabilmesi (bandın alt ucu);
  - MOD10CM boş aylarının 2004 ve 2016 kışlarını düşürmesi.