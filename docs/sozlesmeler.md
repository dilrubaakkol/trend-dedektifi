# Ortak sözleşmeler

Modüller birbirleriyle yalnızca bu iki biçim üzerinden konuşur. Değişiklik ekip onayıyla yapılır.

## 1. Veri sözleşmesi (Kişi 1 → Kişi 2, 3)

- Her değişken × ürün × bölge için bir NetCDF dosyası:
  `cache/processed/<bolge>/<degisken>__<urun>.nc` (ör. `cache/processed/dogu_anadolu/sicaklik_2m__MERRA2.nc`)
- Boyutlar: `time`, `lat`, `lon` (bu adlarla, bu sırayla). `lat` güneyden kuzeye artar, `lon` -180..180.
- Zaman: aylık, damga ayın 1'i 00:00 UTC. Ortak dönem 2001-01 … 2025-12.
- Izgara: analiz ızgarası 0,25° (`grid="025"`). Kar ve DEM ayrıca 0,05° (`grid="005"`) olarak saklanır.
- Eksik veri `NaN`.
- Değişken adı süreç kartındaki adla aynı (aşağıdaki tablo).
- Zorunlu `attrs`: `units`, `long_name`, `source_product` (short name), `source_version`, `doi`,
  `daac`, `download_date`, `processing` (yapılan işlemlerin kısa listesi), `grid`.

| Değişken adı | Birim | Ana ürün | İkincil ürünler |
| --- | --- | --- | --- |
| `kar_ortusu` | % | MOD10CM | — |
| `kar_su_esdegeri` | mm | GLDAS_NOAH025_M | — |
| `sicaklik_2m` | °C | M2TMNXSLV (MERRA-2) | GLDAS_NOAH025_M, AIRS3STM |
| `ozgul_nem_2m` | kg/kg | M2TMNXSLV | — |
| `yagis` | mm/ay | GPM_3IMERGM | MERRA-2 (M2TMNXFLX), GLDAS_NOAH025_M |
| `buharlasma` | mm/ay | GLDAS_NOAH025_M | — |
| `yuzey_akisi` | mm/ay | GLDAS_NOAH025_M | — |
| `toprak_nemi` | kg/m² | GLDAS_NOAH025_M | — |
| `ndvi` | — | MOD13C2 | — |
| `su_buhari_kolon` | kg/m² | AIRS3STM | — |
| `toplam_su_depolama` | cm | GRACE/GRACE-FO JPL Mascon | — |
| `rakim` | m | SRTMGL3 / GMTED2010 | — |

## 2. Sonuç sözleşmesi (Kişi 2, 3 → Kişi 4, 5)

Tek bir `results.json`; örnek: [`examples/results_example.json`](../examples/results_example.json).
Her analizin benzersiz `id`'si vardır; LLM metnindeki `[ref:id]` bağlantıları bu kimliklere işaret eder.
Etiketler yalnızca: `"uyumlu"`, `"celiskili"`, `"yetersiz"`.
