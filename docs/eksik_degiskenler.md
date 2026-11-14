# kb/degiskenler.yaml'da eksik değişkenler

`data/catalog.yaml`'da kaydı olup `kb/degiskenler.yaml`'da kartı olmayan değişkenler (2026-11-14).
Kişi 4 ve 5 sitenin "Değişken" sayfası için bu değişkenlerin kartlarını yazmalı. Kartlarda şu alanlar
olmalı: `baslik`, `sade_tanim`, `dikkat`, `ana_urun`.

**Toplam 17 değişken.** 13'ü L1 yayın paketinde (`outputs/trend-dedektifi-turkiye-v0.1/L1_kup/`),
4'ü katalogda var ama ürünü ertelendiği için henüz üretilmiyor.

- **Ürün kodu:** Dosya adındaki kod (`<degisken>__<urun>.nc`). İlk yazılan ana üründür.
- **Birim:** İşlenmiş dosyadaki `units`.
- **Kaynak (short name):** NASA ürününün kısa adı. `kb/degiskenler.yaml` içindeki `ana_urun` alanı bu
  biçimi kullanır.
- Hepsi Kademe 2'dir (bkz. `docs/sozlesmeler.md` 1.1).

| Değişken | Ürün kodu | Birim | Kaynak (short name) | Kategori | Durum |
| --- | --- | --- | --- | --- | --- |
| `ruzgar_u_10m` | MERRA2 | m/s | M2TMNXSLV | atmosfer | L1 paketinde |
| `ruzgar_v_10m` | MERRA2 | m/s | M2TMNXSLV | atmosfer | L1 paketinde |
| `ruzgar_hizi` | GLDAS | m/s | GLDAS_NOAH025_M | atmosfer | L1 paketinde |
| `deniz_seviyesi_basinci` | MERRA2 | hPa | M2TMNXSLV | atmosfer | L1 paketinde |
| `bulut_orani` | MERRA2 | % | M2TMNXRAD | atmosfer | L1 paketinde |
| `yuzey_sicakligi_gunduz` | MOD11C3 | °C | MOD11C3 | arazi | L1 paketinde |
| `yuzey_sicakligi_gece` | MOD11C3 | °C | MOD11C3 | arazi | L1 paketinde |
| `evi` | MOD13C2 | 1 (birimsiz) | MOD13C2 | arazi | L1 paketinde |
| `taban_akisi` | GLDAS | mm/ay | GLDAS_NOAH025_M | su_dongusu | L1 paketinde |
| `kok_bolgesi_nemi` | GLDAS | kg/m² | GLDAS_NOAH025_M | su_dongusu | L1 paketinde |
| `aerosol_optik_derinlik` | MERRA2 | 1 (birimsiz) | M2TMNXAER | hava_kalitesi | L1 paketinde |
| `ozon_kolon` | MERRA2 (ikincil: OMI ⏸) | DU | M2TMNXSLV | hava_kalitesi | L1 paketinde |
| `no2` | OMI | 10^15 molekül/cm² | OMNO2d | hava_kalitesi | L1 paketinde (2004-10'dan) |
| `yanan_alan` | MCD64 | % | MCD64A1 | arazi | Üretilmiyor (ürün ertelendi) |
| `so2` | OMI | DU | OMSO2e | hava_kalitesi | Üretilmiyor (ürün ertelendi) |
| `deniz_yuzey_sicakligi` | MODISA | °C | MODISA_L3m_SST | deniz | Üretilmiyor (ürün ertelendi) |
| `klorofil` | MODISA | mg/m³ | MODISA_L3m_CHL | deniz | Üretilmiyor (ürün ertelendi) |

## Kart yazarken dikkat

- **`ruzgar_hizi`:** Yakın yüzey hızının aylık ortalamasıdır. U/V bileşenlerinden hız hesaplanmamalı.
  `ruzgar_u_10m` ve `ruzgar_v_10m` yön bileşenleridir; aylık ortalamaları hızın ortalaması değildir.
- **`no2`:** Troposferik kolon, bulut oranı %30'un altındaki günlerden. Seri 2004-10'da başlar.
- **`yuzey_sicakligi_gunduz` / `_gece`:** Kara yüzeyinin sıcaklığıdır, hava sıcaklığı (`sicaklik_2m`)
  değildir.
- **Ertelenen 4 değişken:** Ürün üretilene kadar sitede gösterilmemeli. Kartları yazılabilir, ama
  "henüz veri yok" diye işaretlenmeli.
