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
