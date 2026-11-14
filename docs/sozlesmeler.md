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
- **Kutu notu:** İçeride (`cache/processed/`) `TURKIYE_BBOX` kullanılır. Yayın paketi
  (`python -m data.export`) 25,5°D–45,0°D, 35,5°K–42,5°K kutusuna kırpılır (0,25°'de 28 × 78 hücre).
- **İl sınırları:** Natural Earth 10m Admin-1 (kamu malı). geoBoundaries TUR ADM1, lisansı
  CC BY-SA 2.0 olduğu için seçilmedi. Ayrıntı: [`data/boundaries/README.md`](../data/boundaries/README.md).

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
Domain: `land` = Türkiye kara maskeli, `ocean` = deniz maskeli, `all` = kutunun tamamı (kara + deniz).
`all` değişkenlerde de `region="turkiye"` yalnız Türkiye kara hücrelerini verir; deniz için `deniz_*` bölgelerini kullanın.

| Değişken adı | Birim | Domain | Ana ürün | İkincil ürünler |
| --- | --- | --- | --- | --- |
| `sicaklik_2m` | °C | all (MERRA2), land (GLDAS) | M2TMNXSLV 5.12.4 (MERRA2) | GLDAS_NOAH025_M 2.1 (GLDAS) |
| `ozgul_nem_2m` | kg/kg | all | M2TMNXSLV (MERRA2) | — |
| `ruzgar_u_10m`, `ruzgar_v_10m` | m/s | all | M2TMNXSLV (MERRA2) | — |
| `ruzgar_hizi` | m/s | land | GLDAS_NOAH025_M (GLDAS) — yakın yüzey hızı, aylık ortalama; U/V bileşenlerinden hız hesaplamayın | — |
| `deniz_seviyesi_basinci` | hPa | all | M2TMNXSLV (MERRA2) | — |
| `su_buhari_kolon` | kg/m² | all | M2TMNXSLV `TQV` (MERRA2) | AIRS3STM 7.0 (AIRS) ⏸ |
| `bulut_orani` | % | all | M2TMNXRAD (MERRA2) | MOD08_M3 ⏸ |
| `yagis` | mm/ay | land | GPM_3IMERGM V07 (GPM) — Final ürün ~3 ay gecikmeli; son aylar NaN (şu an 2025-09'a kadar) | GLDAS_NOAH025_M (GLDAS), M2TMNXFLX (MERRA2) |
| `buharlasma` | mm/ay | land | GLDAS_NOAH025_M (GLDAS) | — |
| `yuzey_akisi` | mm/ay | land | GLDAS_NOAH025_M (GLDAS) | — |
| `taban_akisi` | mm/ay | land | GLDAS_NOAH025_M (GLDAS) | — |
| `toprak_nemi` (0–10 cm) | kg/m² | land | GLDAS_NOAH025_M (GLDAS) | — |
| `kok_bolgesi_nemi` | kg/m² | land | GLDAS_NOAH025_M (GLDAS) | — |
| `toplam_su_depolama` | cm | land | JPL GRACE/GRACE-FO Mascon CRI RL06.3Mv04 (GRACE) | — |
| `kar_ortusu` | % | land | MOD10CM 61 (MOD10CM) | — |
| `kar_su_esdegeri` | mm | land | GLDAS_NOAH025_M (GLDAS) | — |
| `ndvi`, `evi` | 1 (birimsiz) | land | MOD13C2 061 (MOD13C2) | — |
| `yuzey_sicakligi_gunduz`, `yuzey_sicakligi_gece` | °C | land | MOD11C3 061 (MOD11C3) | — |
| `yanan_alan` | % | land | MCD64A1 061 ⏸ | — |
| `aerosol_optik_derinlik` | 1 | all | M2TMNXAER (MERRA2) | MOD08_M3 ⏸ |
| `ozon_kolon` | DU | all | M2TMNXSLV `TO3` (MERRA2) | OMTO3e 004 ⏸ |
| `no2` (troposferik) | 10^15 molekül/cm² | all | OMNO2d 004 (OMI), 2004-10'dan | — |
| `so2` | DU | all | OMSO2e 004 (OMI) ⏸ | — |
| `deniz_yuzey_sicakligi` | °C | ocean | MODISA_L3m_SST ⏸ | — |
| `klorofil` | mg/m³ | ocean | MODISA_L3m_CHL ⏸ | — |
| `rakim` | m | land | SRTMGL30 002 (SRTM) | — |

## 2. Sonuç sözleşmesi (Kişi 2, 3 → Kişi 4, 5)

Tek bir `results.json`; örnek: [`examples/results_example.json`](../examples/results_example.json).
Her analizin benzersiz `id`'si vardır; LLM metnindeki `[ref:id]` bağlantıları bu kimliklere işaret eder.
Etiketler yalnızca: `"uyumlu"`, `"celiskili"`, `"yetersiz"`.
