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

## L2 akıl kontrolü (2026-11-14)

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
