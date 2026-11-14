# Ortak sözleşmeler

> **TASLAK (2026-11-14), ekip onayına sunuldu.** Bölüm 1'e L1 yayın paketi eklendi. Bölüm 2'deki
> eski `results.json` sözleşmesi kaldırıldı; yerine L2/L3/L4 şeması yazıldı. Onaylanana kadar
> L2–L4 bölümleri öneridir.

Modüller birbirleriyle yalnızca bu biçimler üzerinden konuşur: içeride veri küpleri (bölüm 1) ve
yayın paketindeki L1–L4 katmanları (bölüm 1.1 ve bölüm 2). Değişiklik ekip onayıyla yapılır.

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
- **Bilinen sorunlar:** `yagis__GLDAS` 2025-12 değeri belirsiz. GES DISC granülü revizyon 3 ve Giovanni
  aynı ay için yaklaşık 2 kat düşük değer veriyor. Değer silinmedi; dosyada `bilinen_sorunlar` attr'ı
  var. Ayrıntı: [`docs/dogrulama.md`](dogrulama.md).

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

### 1.1 L1 yayın paketi (Kişi 1 → herkes, site)

Üretim: `python -m data.export --surum v0.1`. Yayın paketinin kökü
`outputs/trend-dedektifi-turkiye-<surum>/`. `outputs/` git dışındadır; paket Zenodo'ya yüklenir.

- **Yol:** `outputs/trend-dedektifi-turkiye-v0.1/L1_kup/<degisken>__<urun>.nc`
- **Kapsam:** Yalnız 0,25° ve yalnız gerçek veri. `__005` ve `SENTETIK` dosyaları girmez.
- **Kutu:** 25,5°D–45,0°D, 35,5°K–42,5°K, yani 28 enlem × 78 boylam hücre. Hücre kenarları kutu
  sınırına oturur.
- **Boyutlar, zaman, maske ve zorunlu attrs:** Bölüm 1'deki gibi.
- **Yayın attr'ları** (bölüm 1'deki attr'lara ek olarak):

| Attr | Tip | Anlam |
| --- | --- | --- |
| `urun_surumu` | metin | Veri seti sürümü, ör. `v0.1` |
| `veri_seti_doi` | metin | Veri setinin Zenodo DOI'si. Yayına kadar `(yayında doldurulacak)` |
| `doi` | metin | **NASA kaynak ürününün** DOI'si. Bölüm 1'deki gibi; değişmez |
| `kademe` | int32 | `1` = Kademe 1; `2` = Kademe 2; `0` = kademesiz (sabit alanlar, ör. `rakim`) |
| `lisans` | metin | `CC BY 4.0` |
| `dogrulanmadi` | metin | Yalnız Kademe 2 dosyalarında, değeri `evet` |
| `bilinen_sorunlar` | metin | Yalnız bilinen bir veri sorunu varsa (ör. `yagis__GLDAS` 2025-12) |
| `yayin_kutusu` | metin | `25.5, 35.5, 45.0, 42.5` (batı, güney, doğu, kuzey) |
| `katalog_dogrulanmadi` | metin | Katalog kaydının bir kısmı (ürün ya da dosya değişkeni) doğrulanmadıysa. `dogrulanmadi`'dan ayrı bir bayraktır |

- `processing` attr'ının sonuna "yayın kutusuna kırpıldı (…)" eklenir.
- **Kademe 1** (10 dosya): `sicaklik_2m` (MERRA2, GLDAS), `yagis` (GPM, GLDAS, MERRA2), `toprak_nemi`
  (GLDAS), `kar_ortusu` (MOD10CM), `kar_su_esdegeri` (GLDAS), `ndvi` (MOD13C2), `toplam_su_depolama`
  (GRACE). Liste: `data/export.py` içinde `KADEME_1`.
- **Kademe 2:** Paketteki diğer bütün gerçek dosyalar.
- **`L1_kup/ICINDEKILER.csv`:** UTF-8 (BOM'lu), bir satır = bir dosya. Sıralama: önce kademe (1, 2,
  sonra 0), sonra dosya adı.

| Sütun | Örnek | Anlam |
| --- | --- | --- |
| `dosya` | `yagis__GPM.nc` | Dosya adı |
| `degisken` | `yagis` | Değişken adı (bölüm 1 tablosu) |
| `birim` | `mm/ay` | `units` attr'ı |
| `kaynak` | `GPM_3IMERGM 07` | `source_product` + `source_version` |
| `kaynak_doi` | `10.5067/GPM/IMERG/3B-MONTH/07` | `doi` attr'ı (NASA kaynak DOI'si) |
| `donem` | `2001-01 … 2025-09` | Kutuda en az bir geçerli hücresi olan ilk ve son ay; sabit alanda `sabit` |
| `kademe` | `1` | `1`, `2` ya da `0` |

## 2. Analiz katmanları L2–L4 (Kişi 2, 3 → Kişi 4, 5) — TASLAK

Bütün katmanlar L1 küplerinden üretilir ve aynı paket köküne yazılır:
`outputs/trend-dedektifi-turkiye-<surum>/`. Çerçeve **ilişki**dir, neden değil. Hiçbir sütun ya da
etiket nedensellik iddia etmez.

Ortak kurallar:
- Değişken ve ürün kodları L1 dosya adlarıyla aynıdır (`<degisken>__<urun>`).
- Her dosya kaynak L1 dosyasının `urun_surumu`, `veri_seti_doi`, `kademe`, `lisans` ve `doi` alanlarını
  taşır: NetCDF'te attrs olarak, CSV'de sütun olarak.
- Kademe 2 girdisinden üretilen her sonuç `dogrulanmadi = evet` taşır.
- Ek olarak `donem` (analiz dönemi) ve `seri` alanları bulunur. `seri`, trendin hangi seriden
  hesaplandığını söyler: ör. `yillik_ortalama`, `aylik_anomali`, `kis_DJF`.
- Eksik ya da hesaplanamayan değer `NaN`'dır (CSV'de boş hücre).

### 2.1 L2: hücre bazında trend (Kişi 2)

- **Yol:** `L2_trend/<degisken>__<urun>__trend.nc`
- **Boyutlar:** `lat`, `lon`. L1 ile aynı 28 × 78 ızgara ve aynı koordinatlar. Maskeli hücre `NaN`.

| Değişken | Tip | Birim | Anlam |
| --- | --- | --- | --- |
| `sen_egimi` | float32 | `<birim>/10 yıl` | Sen (Theil-Sen) eğimi |
| `ga_alt`, `ga_ust` | float32 | `<birim>/10 yıl` | Eğimin %95 güven aralığı; etkin n ile genişletilmiş |
| `p_mk` | float32 | 1 | Hamed-Rao düzeltmeli Mann-Kendall p değeri |
| `p_fdr` | float32 | 1 | Benjamini-Hochberg ile düzeltilmiş p (q değeri), dosyadaki tüm geçerli hücreler üzerinden |
| `anlamli` | int8 | — | `1` = `p_fdr ≤ 0,10` (BH, α_FDR = 0,10); `0` = değil; maskeli hücre `-1` |
| `etkin_n` | float32 | yıl ya da ay | Otokorelasyona göre etkin örneklem büyüklüğü |
| `gereken_yil` | float32 | yıl | Weatherhead vd. (1998): gözlenen eğimi ayırt etmek için gereken yıl sayısı (yıllık seride √12 düzeltmesi) |

- **attrs:** Ortak kurallardaki alanlar, ayrıca:
  - `alfa_fdr = 0.10`, `fdr_yontemi = "Benjamini-Hochberg"`, `mk_yontemi = "Hamed-Rao 1998"`
  - `ga_yontemi`: genişletme formülünün kısa tanımı
- **Kaynak uyumu:** `L2_trend/<degisken>__kaynak_uyumu.nc`, boyutlar `lat`, `lon`.
  - `k` (int16): Aynı yönde ve anlamlı trend veren ürün sayısı.
  - `m` (int16): O hücrede veri olan ürün sayısı.
  - attr `urunler`: Karşılaştırılan ürün kodları, ör. `GPM, GLDAS, MERRA2`.
  - Site bunu "k/m kaynak aynı yönde" diye gösterir.
  - Yalnız birden fazla ürünü olan değişkenler için üretilir: `yagis`, `sicaklik_2m`.

### 2.2 L3: il ve bölge özetleri (Kişi 2 / Kişi 3)

- **Yollar:** `L3_ozet/<degisken>__<urun>__il.csv` ve `L3_ozet/<degisken>__<urun>__bolge.csv`
- **Bölgeler:** İller Natural Earth, coğrafi bölgeler `data/boundaries/bolgeler.yaml`. Hücre seçimi
  `data.regions` hücre merkezi kuralıyla yapılır.
- Bir satır = bir il ya da bölge.

| Sütun | Anlam |
| --- | --- |
| `bolge_kodu` | İl: plaka (`25`); bölge: anahtar (`dogu_anadolu`) |
| `bolge_adi` | Türkçe ad |
| `hucre_sayisi` | Ortalamaya giren 0,25° hücre sayısı |
| `sen_egimi`, `ga_alt`, `ga_ust` | Alan ortalaması serisinin trendi (`<birim>/10 yıl`) |
| `p_mk`, `p_fdr`, `anlamli` | L2 ile aynı tanım. FDR, dosyadaki tüm iller ya da tüm bölgeler üzerinden |
| `etkin_n`, `gereken_yil` | L2 ile aynı tanım |
| `anlamli_hucre_orani` | Bölgedeki L2 hücrelerinden `anlamli = 1` olanların oranı (0–1) |
| `birim`, `donem`, `seri`, `kademe`, `dogrulanmadi` | Ortak alanlar |

### 2.3 L4: değişken çiftleri arasındaki ilişki (Kişi 3)

> Kişi 3 doldurdu (2026-11-14). Çift listesi ekip belgesindeki ("Veri Ürünü Tanımı") 6 çifttir; ek çift
> yok. Kış = Aralık (Y−1) + Ocak + Şubat (Y); Mart dahil değil.

**Dosyalar** (paket kökü altında):

| Yol | İçerik |
| --- | --- |
| `L4_iliski/ciftler.csv` | Tek tablo. Bir satır = bir çift × bir bölge (× bir gecikme). İller, 7 bölge ve `turkiye` aynı dosyada, `bolge_turu` sütunuyla ayrılır |
| `L4_iliski/iliski__<degisken1>__<degisken2>.nc` | Bir çiftin 0,25° hücre haritası. Çift 3 iki gecikme için iki dosyadır: `…__gecikme1.nc`, `…__gecikme2.nc`. Çift 4 (GRACE) için harita **yoktur** |

Ayrı bir `iliski_iller.csv` dosyası yoktur; il satırları `ciftler.csv` içindedir (`bolge_turu = il`).

**Çiftler** (beklenen işaret: `+` aynı yönde, `−` zıt yönde):

| `cift_no` | `cift` | `seri` | Beklenen | Kademe | Kapsam |
| --- | --- | --- | --- | --- | --- |
| 1 | `sicaklik_2m__MERRA2~kar_ortusu__MOD10CM` | `kis_DJF` | − | 1 | Yalnız kış ortalaması kar örtüsü ≥ %10 olan hücreler |
| 2 | `yagis__GPM~toprak_nemi__GLDAS` | `mevsim_anomali` | + | 1 | Tüm kara |
| 3 | `toprak_nemi__GLDAS~ndvi__MOD13C2` | `aylik_anomali_nis_eyl` | + | 1 | Tüm kara; gecikme 1 ve 2 ay (NDVI, toprak neminden sonra) |
| 4 | `yagis__GPM~toplam_su_depolama__GRACE` | `yillik` | + | 1 | Yalnız 7 bölge ve `turkiye` (GRACE çözünürlüğü kaba); GRACE boşluk yılları atılır |
| 5 | `sicaklik_2m__MERRA2~buharlasma__GLDAS` | `yaz_JJA` | + | 2 | Tüm kara; kurak yerde zayıf ya da ters çıkabilir (`not` sütununda açıklanır) |
| 6 | `sicaklik_2m__MERRA2~yuzey_sicakligi_gunduz__MOD11C3` | `aylik_anomali` | + | 2 | Tüm kara; kalite kontrolü (güçlü pozitif beklenir) |

`seri` değerleri:
- `kis_DJF`, `yaz_JJA`, `yillik`: her yıla bir değer. Birikimli değişkenlerde (yağış, buharlaşma) toplam, ötekilerde ortalama. Mevsimin bir ayı eksikse değer `NaN`.
- `mevsim_anomali`: dört mevsimin değerleri art arda dizilir, her mevsimden kendi uzun dönem ortalaması çıkarılır.
- `aylik_anomali`: her aydan o ayın 12 aylık klimatolojisi çıkarılır. `_nis_eyl`: yalnız Nisan–Eylül ayları (NDVI tarafı).
- Her seriden korelasyondan önce doğrusal trend çıkarılır.

**`ciftler.csv` sütunları:**

| Sütun | Anlam |
| --- | --- |
| `cift_no`, `cift`, `degisken_1`, `degisken_2`, `seri` | Yukarıdaki tablo |
| `gecikme_ay` | Çift 3'te 1 ya da 2; ötekilerde 0 |
| `beklenen_yon` | `+` ya da `-` |
| `bolge_turu` | `il`, `bolge` ya da `turkiye` |
| `bolge_kodu`, `bolge_adi` | L3 ile aynı: il plakası / bölge anahtarı (`dogu_anadolu`), Türkçe ad |
| `hucre_sayisi` | Bölge serisine giren 0,25° hücre sayısı (çift 1'de kar maskesinden sonra) |
| `donem`, `n` | İki serinin ortak dönemi; kullanılan değer sayısı |
| `r` | Trendi giderilmiş seriler arasındaki Pearson korelasyonu |
| `r1_1`, `r1_2` | İki serinin gecikme-1 otokorelasyonu |
| `etkin_n` | Bretherton vd. (1999): n·(1 − r₁·r₂)/(1 + r₁·r₂) |
| `p` | `etkin_n − 2` serbestlik dereceli t testiyle iki yönlü p değeri |
| `p_fdr` | Yalnız `bolge_turu = il` satırlarında: aynı çiftin 81 il p değerleri üzerinden Benjamini-Hochberg. Ötekilerde boş |
| `anlamli` | `1` / `0`. İl: `p_fdr ≤ 0,10`. Bölge ve Türkiye: `p < 0,05` |
| `etiket` | `beklenen_yonde` · `ters_yonde` · `anlamsiz` (hesaplanamadıysa boş) |
| `not` | Kısa açıklama (ör. çift 5 kurak bölge, `ters_yonde` satırları için olası nedenler) |
| `urun_surumu`, `veri_seti_doi`, `lisans` | Ortak alanlar |
| `kademe` | İki girdinin büyüğü (çift 5 ve 6 = 2) |
| `dogrulanmadi` | Kademe 2 çiftlerde `evet`, ötekilerde boş |
| `doi_1`, `doi_2` | İki NASA kaynak ürününün DOI'si |

**Harita dosyası (`iliski__*.nc`) içeriği:** Boyutlar `lat`, `lon` (L1 ile aynı 28 × 78 ızgara).

| Değişken | Tip | Anlam |
| --- | --- | --- |
| `r`, `etkin_n`, `p`, `p_fdr` | float32 | Yukarıdaki gibi; FDR, Türkiye kara hücreleri üzerinden (α_FDR = 0,10) |
| `anlamli` | int8 | `1` = `p_fdr ≤ 0,10`, `0` = değil, `-1` = maskeli ya da hesaplanamadı |
| `etiket` | int8 | `1` = beklenen_yonde, `-1` = ters_yonde, `0` = anlamsiz, `-99` = maskeli ya da hesaplanamadı (attrs: `flag_values`, `flag_meanings`) |

attrs: ortak alanlar, ayrıca `cift`, `cift_no`, `seri`, `gecikme_ay`, `beklenen_yon`, `donem`, `alfa_fdr = 0.10`, `doi_1`, `doi_2`.

- **Etiketler yalnız bu üç değerdir.** Hiçbiri nedensellik anlamına gelmez; "ilişki beklenen yönde"
  diye okunur.
- **Anlamlılık eşikleri:**
  - Haritalar ve il satırları: FDR (α_FDR = 0,10). Bu, belgedeki ve L2'deki eşikle aynıdır.
  - Bölge ve Türkiye satırları: p < 0,05. Bu satırlar az sayıda olduğu için çoklu test düzeltmesi yapılmaz.
