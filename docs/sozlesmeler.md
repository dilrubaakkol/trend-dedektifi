# Ortak sözleşmeler

Modüller birbirleriyle yalnızca bu iki biçim üzerinden konuşur. Değişiklik ekip onayıyla yapılır.

## 1. Veri sözleşmesi (Kişi 1 → Kişi 2, 3)

- Her değişken × ürün için tüm Türkiye kutusunu (`TURKIYE_BBOX` = 25,0°D–45,5°D, 34,5°K–43,0°K;
  çevre denizler dahil) kapsayan bir NetCDF dosyası:
  `cache/processed/turkiye/<degisken>__<urun>.nc` (ör. `cache/processed/turkiye/sicaklik_2m__MERRA2.nc`).
  Kullanıcının seçtiği bölge (il, coğrafi bölge, deniz, bbox, GeoJSON) bu küpten **yerel olarak**
  `data.load()` / `data.subset()` ile kesilir; bölge başına ayrı dosya yazılmaz.
- 0,05° dosyalara `__005` eki gelir: `cache/processed/turkiye/<degisken>__<urun>__005.nc`.
- Boyutlar: `time`, `lat`, `lon` (bu adlarla, bu sırayla). Sabit alanlar (`rakim`) yalnız `lat`, `lon`.
  `lat` güneyden kuzeye artar, `lon` -180..180. Koordinatlar hücre merkezidir.
- Zaman: aylık, damga ayın 1'i 00:00 UTC. Ortak dönem 2001-01 … 2025-12. Daha geç başlayan ürünler
  kendi başlangıçlarından itibaren yer alır (ör. GRACE 2002-04); eksik aylar `NaN`.
- Izgara: analiz ızgarası 0,25° (`grid="025"`). İnce ürünler (kar örtüsü, NDVI/EVI, kara yüzey
  sıcaklığı, rakım) ayrıca 0,05° (`grid="005"`) olarak saklanır.
- Eksik veri `NaN`. Kara değişkenleri Türkiye kara sınırıyla, deniz değişkenleri deniz maskesiyle
  maskelidir (hücre merkezi kuralı).
- Değişken adı süreç kartındaki adla aynı (aşağıdaki tablo).
- Zorunlu `attrs`: `units`, `long_name`, `source_product` (short name), `source_version`, `doi`,
  `daac`, `download_date`, `processing` (yapılan işlemlerin kısa listesi), `grid`,
  `domain` (`land` | `ocean` | `all`), `valid_start` (gerçek başlangıç ayı; sabit alanda `sabit`).
- Sentetik dosyalar ürün kodu `SENTETIK` taşır; attrs'ta `synthetic_truth` (gerçek parametreler,
  JSON) ve `yer_tutucu` bulunur. Gerçek analizde kullanılmaz.

### Kullanım

```python
from data import load, subset

da = load("sicaklik_2m", region="Erzurum")                       # ana ürün, 0,25°
da = load("kar_ortusu", region="Doğu Anadolu", grid="005")        # 0,05°
da = load("yagis", region=(39.0, 39.0, 41.0, 40.0), product="GLDAS")
da = load("ndvi", region="turkiye", sentetik=False)               # yalnız gerçek veri
```

`load(degisken, region="turkiye", grid="025", product=None, sentetik="otomatik")` →
`xr.DataArray` (attrs: dosya attrs'ı + `region`, `region_label`, `region_kind`, `region_cells`,
`region_method`).

- `region`: il adı (Türkçe karakterli ya da karaktersiz), bölge adı (`marmara`, `ege`, `akdeniz`,
  `ic_anadolu`, `karadeniz`, `dogu_anadolu`, `guneydogu_anadolu`), `"turkiye"`, deniz
  (`deniz_karadeniz`, `deniz_marmara`, `deniz_ege`, `deniz_akdeniz`, `cevre_denizler`), demo kutusu
  (`demo:konya`, `demo:dogu_anadolu`), bbox `(batı, güney, doğu, kuzey)` ya da GeoJSON; `None` = kesme yok.
  Ad çakışmasında önek: `il:`, `bolge:`, `deniz:`, `demo:`. Seçenek listesi: `data.regions.list_regions()`.
- `product`: katalog ürün anahtarı (`GLDAS`), dosya kodu (`MERRA2`) ya da `SENTETIK`; `None` = ana ürün.
- `sentetik`: `"otomatik"` → gerçek dosya yoksa uyarıyla sentetiğe düşer; `True` → hep sentetik;
  `False` → yalnız gerçek veri.
- Elinizdeki bir xarray'i kesmek için: `subset(ds, region)`.

Ayrıntılı kayıtlar (sürüm, DOI, dosyadaki değişken adı, dönüşüm): [`data/catalog.yaml`](../data/catalog.yaml).
Dosya adındaki ürün kodu parantez içindedir (ör. `sicaklik_2m__MERRA2.nc`). ⏸ = katalogda var, henüz üretilmiyor.

| Değişken adı | Birim | Ana ürün | İkincil ürünler |
| --- | --- | --- | --- |
| `sicaklik_2m` | °C | M2TMNXSLV 5.12.4 (MERRA2) | GLDAS_NOAH025_M 2.1 (GLDAS) |
| `ozgul_nem_2m` | kg/kg | M2TMNXSLV (MERRA2) | — |
| `ruzgar_u_10m`, `ruzgar_v_10m` | m/s | M2TMNXSLV (MERRA2) | — |
| `ruzgar_hizi` | m/s | GLDAS_NOAH025_M (GLDAS) | — |
| `deniz_seviyesi_basinci` | hPa | M2TMNXSLV (MERRA2) | — |
| `su_buhari_kolon` | kg/m² | M2TMNXSLV `TQV` (MERRA2) | AIRS3STM 7.0 (AIRS) ⏸ |
| `bulut_orani` | % | M2TMNXRAD (MERRA2) | MOD08_M3 ⏸ |
| `yagis` | mm/ay | GPM_3IMERGM V07 (GPM) | GLDAS_NOAH025_M (GLDAS), M2TMNXFLX (MERRA2) |
| `buharlasma` | mm/ay | GLDAS_NOAH025_M (GLDAS) | — |
| `yuzey_akisi` | mm/ay | GLDAS_NOAH025_M (GLDAS) | — |
| `taban_akisi` | mm/ay | GLDAS_NOAH025_M (GLDAS) | — |
| `toprak_nemi` (0–10 cm) | kg/m² | GLDAS_NOAH025_M (GLDAS) | — |
| `kok_bolgesi_nemi` | kg/m² | GLDAS_NOAH025_M (GLDAS) | — |
| `toplam_su_depolama` | cm | JPL GRACE/GRACE-FO Mascon CRI RL06.3Mv04 (GRACE) | — |
| `kar_ortusu` | % | MOD10CM 61 (MOD10CM) | — |
| `kar_su_esdegeri` | mm | GLDAS_NOAH025_M (GLDAS) | — |
| `ndvi`, `evi` | 1 (birimsiz) | MOD13C2 061 (MOD13C2) | — |
| `yuzey_sicakligi_gunduz`, `yuzey_sicakligi_gece` | °C | MOD11C3 061 (MOD11C3) | — |
| `yanan_alan` | % | MCD64A1 061 ⏸ | — |
| `aerosol_optik_derinlik` | 1 | M2TMNXAER (MERRA2) | MOD08_M3 ⏸ |
| `ozon_kolon` | DU | M2TMNXSLV `TO3` (MERRA2) | OMTO3e 004 ⏸ |
| `no2` (troposferik) | 10^15 molekül/cm² | OMNO2d 004 (OMI) ⏸ | — |
| `so2` | DU | OMSO2e 004 (OMI) ⏸ | — |
| `deniz_yuzey_sicakligi` | °C | MODISA_L3m_SST ⏸ | — |
| `klorofil` | mg/m³ | MODISA_L3m_CHL ⏸ | — |
| `rakim` | m | SRTMGL30 002 (SRTM) | — |

## 2. Sonuç sözleşmesi (Kişi 2, 3 → Kişi 4, 5)

Tek bir `results.json`; örnek: [`examples/results_example.json`](../examples/results_example.json).
Her analizin benzersiz `id`'si vardır; LLM metnindeki `[ref:id]` bağlantıları bu kimliklere işaret eder.
Etiketler yalnızca: `"uyumlu"`, `"celiskili"`, `"yetersiz"`.
