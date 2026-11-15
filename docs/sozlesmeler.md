# Ortak sözleşmeler

> **Sürüm v0.1 (2026-11-14), ekip onaylı.** L1 yayın paketi (bölüm 1.1) ve L2/L3/L4 analiz katmanları
> (bölüm 2) kesinleşmiştir. Eski `results.json` sözleşmesi kaldırılmıştır.

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
- **`tarim_orani__MCD12C1.nc`** (2026-11-15, `python -m data.arazi --surum v0.1`): zamansız (lat, lon) 28 × 78,
  birim `1`. Değer: MCD12C1 061 `Land_Cover_Type_1_Percent` için (IGBP %12 tarım + ½·%14 mozaik) / 100,
  2021–2025 ortalaması. Kademe 2, `dogrulanmadi = evet`. `ICINDEKILER.csv`'de `donem = sabit`, `kademe = 2`;
  `donem = sabit` olduğu için L2/L3 trend hesabına girmez. Yalnız sapma v2 tarım maskesinde kullanılır (bölüm 2.3).
  Dosyayı `data.arazi` yazar. `data.export` dosyaya dokunmaz ama yeniden üretimde onu `ICINDEKILER.csv`'ye
  ekler: `L1_kup/` içindeki ayrıca yazılmış sabit katmanlar listelenir ve kademe dosyanın `kademe` attr'ından okunur.
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

### 1.2 Ülke parametresi (2026-11-15)

Veri katmanı ülkeden bağımsızdır. Ülkeler `data/ulkeler.yaml`'da tanımlıdır. Her kayıtta şunlar var: anahtar,
ad, ISO3, işleme kutusu (`ic_kutu`), yayın kutusu (`yayin_kutusu`, 0,25°'ye hizalı), Natural Earth adı, kara
maskesi kaynağı ve ülkeye özgü uyarılar. **Varsayılan `turkiye`** ve davranışı değişmedi; yukarıdaki bütün
kurallar Türkiye için aynen geçerli. Türkiye paketi yeniden export edildiğinde bayt bayt aynı çıkar.

| | Türkiye (varsayılan) | Diğer ülke (`<ulke>`, ör. `yunanistan`) |
| --- | --- | --- |
| Komut | `--ulke` verilmez | `python -m data.build --ulke <ulke> …`, `python -m data.export --ulke <ulke> --surum v0.1` |
| Ham kesit | `cache/raw/<urun>/` | `cache/raw/<ulke>/<urun>/` |
| İşlenmiş | `cache/processed/turkiye/` | `cache/processed/<ulke>/` |
| Paket | `outputs/trend-dedektifi-turkiye-<surum>/` | `outputs/trend-dedektifi-<ulke>-<surum>/` |
| Kara maskesi (`domain: land`) | 81 ilin birleşimi (`data/boundaries/iller.geojson`) | `data/boundaries/<ulke>/kara.geojson` (Natural Earth 10m admin-0, kamu malı) |
| Ek attr'lar | yok (attr yoksa Türkiye) | `ulke`, `ulke_adi`, `ulke_iso3`; `ek_uyarilar` → `bilinen_sorunlar` |

- Izgara, birim, zaman, attr ve kademe kuralları bütün ülkelerde aynıdır. Paketin boyutu yayın kutusundan gelir:
  Türkiye 28 × 78, Yunanistan 29 × 35 hücre.
- İl, bölge ve deniz adları yalnız Türkiye içindir. Başka ülkede bölge = ülkenin tamamı (`subset(ds, "yunanistan")`).
- Fizik ve istatistik tarafında ülke kara maskesi: `data.regions.ulke_maskesi(lat, lon, "<ulke>")`.
  Bu fonksiyon yayın paketindeki `domain: land` maskesiyle aynı maskeyi verir.
- Yeni ülke: `ulkeler.yaml`'a kayıt ekleyin, sonra `python -m data.make_boundaries --ulke <ulke>` çalıştırın.
  Komut yayın kutusunu da hesaplayıp ekrana yazar; o kutu ulkeler.yaml'a girilir.
- Komutlar ve Yunanistan paketi: `docs/ulke_parametresi.md`.

## 2. Analiz katmanları L2–L4 (Kişi 2, 3 → Kişi 4, 5)

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

Üretim: `python -m stats.l2 --surum v0.1`. Kod: `stats/l2.py`, motor `stats/trend_tests.py`, seriler
`stats/preprocessing.py`. Girdi: `L1_kup/ICINDEKILER.csv`'deki bütün dosyalar (rakım hariç).

- **Yol:** `L2_trend/<degisken>__<urun>__trend.nc`
- **Boyutlar:** `mevsim`, `lat`, `lon`. Izgara L1 ile aynı: 28 × 78 hücre, aynı koordinatlar.
- **`mevsim`** (metin koordinatı, bu sırayla):
  - `yillik`: Ocak–Aralık
  - `kis`: Aralık(Y−1)–Şubat(Y); ilk kış 2002
  - `ilkbahar`: Mart–Mayıs
  - `yaz`: Haziran–Ağustos
  - `sonbahar`: Eylül–Kasım
- **Seri:** Her mevsim için yılda bir değer.
  - Ortalama alınan değişkenlerde dönem ortalaması.
  - Toplanan değişkenlerde (`yagis`, `buharlasma`, `yuzey_akisi`, `taban_akisi`) dönem toplamı.
    Seri birimi yıllıkta `mm/yıl`, mevsimlikte `mm/mevsim` olur; eğim birimi `mm/dönem / 10 yıl`.
    Her mevsimin seri birimi `seri_birimi` attr'ında yazılı.
- **Eksik veri kuralı:**
  - Bir yıl ya da mevsimde eksik ay oranı **> 0,20** ise o değer NaN olur. Yıllıkta en çok 2 ay
    eksik olabilir; 3 aylık mevsimde tek eksik ay bile değeri düşürür.
  - **Ürüne göre eşik:** GRACE için yıllıkta en az 6 geçerli ay (eksik oran ≤ 0,50), mevsimde en az
    2/3 ay. Kod: `stats/preprocessing.py` içinde `EKSIK_ESIK_URUN`. Gerekçe:
    - Yaklaşık 2011–2017 arasında uydu bataryası yönetimi yüzünden birkaç ayda bir ay eksik.
    - 2017-07 … 2018-05 arasında GRACE → GRACE-FO boşluğu var.
    - 0,20 eşiğiyle 2011 ve 2013–2018 düşüyor, seri 16 yıla iniyordu. Yeni eşikle 22 yıl kalıyor;
      yalnız 2017 ve 2018 düşüyor.
    - Su depolama yavaş değişir; 6 aylık ortalama yıllık düzeyi temsil eder.
  - Kullanılan eşik dosyanın `eksik_veri_kurali` attr'ında yazılı.
  - Toplanan değişkende eksik ay varsa toplam = geçerli ayların ortalaması × ay sayısı.
  - Bir hücrede en az **12 geçerli yıl** yoksa trend hesaplanmaz (NaN).
  - Örnekler: GPM'in 2025 yılı ve 2025 sonbaharı düşer (ürün 2025-09'da bitiyor). GRACE'in 2017 ve
    2018 yılları düşer.
- **Anlamlılık kuralı** (tek tanım: `stats/trend_tests.py` içinde `anlamli_kural`; L2 hücreleri, L3
  il/bölge satırları ve kaynak uyumu `k` aynı kuralı kullanır):
  - `anlamli = 1` ⇔ `p_fdr ≤ 0,10` **ve** %95 genişletilmiş GA sıfırı dışlıyor (`ga_alt > 0` ya da
    `ga_ust < 0`).
  - `anlamli = 0` ⇔ `p_fdr` hesaplanmış ama koşullardan biri sağlanmıyor.
  - `anlamli = -1` ⇔ `p_fdr` NaN.
  - Gerekçe: MK testi ile genişletilmiş Sen GA'sı farklı yöntemlerdir. Yalnız `p_fdr` kullanıldığında
    GA'sı sıfırı kapsayan trendler de "anlamlı" görünüyordu. İkisinin birlikte sağlanması temkinli
    taraftır. Kural `anlamlilik_kurali` attr'ında yazılı.

| Değişken | Tip | Birim | Anlam |
| --- | --- | --- | --- |
| `sen_egimi` | float32 | `<seri birimi> / 10 yıl` | Sen (Theil-Sen) eğimi |
| `ga_alt`, `ga_ust` | float32 | `<seri birimi> / 10 yıl` | Eğimin %95 güven aralığı; etkin n ve t dağılımıyla genişletilmiş (aşağıda) |
| `p_mk` | float32 | 1 | Hamed-Rao düzeltmeli Mann-Kendall p değeri |
| `p_fdr` | float32 | 1 | Benjamini-Hochberg q değeri. Her mevsim için ayrı, yalnız Türkiye kara hücreleri üzerinden; diğer hücrelerde NaN |
| `anlamli` | int8 | — | Anlamlılık kuralı (yukarıda): `1` = `p_fdr ≤ 0,10` ve GA sıfırı dışlıyor; `0` = değil; `-1` = kara maskesi dışı ya da hesaplanamadı |
| `etkin_n` | float32 | yıl | Etkin örneklem büyüklüğü |
| `gereken_yil` | float32 | yıl | Weatherhead gereken yıl sayısı (aşağıda); eğim 0 ise NaN |

- **Kara maskesi:** Türkiye kara sınırı, hücre merkezi kuralı (`data.regions.domain_mask("land")`).
  `domain = all` değişkenlerde (ör. `sicaklik_2m__MERRA2`) eğim, GA ve p deniz hücrelerinde de
  hesaplanır. Ama FDR ve `anlamli` yalnız kara hücrelerindedir.
- **Genişletilmiş GA:**
  - r1 = Sen artıklarının gecikme-1 otokorelasyonu, yalnız ardışık yıllardan.
  - Küçük örneklem düzeltmesi: r1_düz = r1 + (1 + 4·r1)/n, en çok 0,95.
  - n_etkin = n·(1 − r1_düz)/(1 + r1_düz). r1_düz ≤ 0 ise n; en az 3.
  - Sen aralığının iki yarısı ayrı ayrı √(n/n_etkin) · t₀.₉₇₅(n_etkin − 2)/t₀.₉₇₅(n − 2) ile çarpılır.
- **MK yedeği:** Güçlü negatif artık otokorelasyonunda Hamed-Rao varyans düzeltmesi negatif çıkabilir
  ve p tanımsız olur. O hücrede düzeltmesiz MK kullanılır. Yedeğin kullanıldığı hücre sayısı
  `mk_yedek_hucre` attr'ında yazılı.
- **Weatherhead gereken yıl:**
  - n* = [3,3 · σ_N/|ω0| · √((1 + φ)/(1 − φ))]^(2/3)
  - ω0: yıllık eğim; σ_N: artıkların std'si; φ: artıkların ham gecikme-1 otokorelasyonu (±0,95).
  - Formül aylık seri için türetilmiştir. Yılda bir değerli seride (yıllık ve mevsimlik) OLS eğim
    varyansı 12 kat büyük olduğundan σ_N yerine **√12 · σ_N** kullanılır.
- **attrs:**
  - Kaynak L1 dosyasının bütün attrs'ı: `kademe`, `lisans`, `urun_surumu`, `veri_seti_doi`, `doi`,
    `bilinen_sorunlar`, `dogrulanmadi` …
  - Yöntem alanları: `mk_yontemi`, `egim_yontemi`, `ga_yontemi`, `fdr_yontemi`, `alfa_fdr = 0.10`,
    `gereken_yil_yontemi`, `eksik_veri_kurali`, `min_yil`.
  - Seri ve dönem alanları: `katman = "L2"`, `kaynak_dosya`, `birim`, `egim_birimi`, `seri_birimi`,
    `seri_tanimi`, `donem` (mevsim başına geçerli ilk–son yıl), `mk_yedek_hucre`, `olusturma_tarihi`.
- **`trend_uyarisi`** (attr, isteğe bağlı): Trendin güvenilirliğiyle ilgili bilinen bir sorun varsa
  bulunur. Değerler silinmez; uyarı yalnız işarettir. Site ve L3 bu metni kullanıcıya göstermelidir.
  - Biçim: Birden fazla uyarı ` | ` ile ayrılır. Tüm mevsimler için geçerli uyarı düz metindir;
    yalnız bir mevsime ait uyarı `[mevsim] metin` biçimindedir.
  - Uyarılar (kaynak: `stats/l2.py` içinde `TREND_UYARILARI`):
    - **GLDAS** `sicaklik_2m`, `yagis`, `taban_akisi`, `yuzey_akisi`: zorlama verisi homojen
      olmayabilir; trend için MERRA2/GPM tercih edilmeli.
    - **MOD11C3** `yuzey_sicakligi_gunduz` / `_gece`: Terra sensör kayması olasılığı doğrulanmadı.
    - **MOD13C2** `ndvi`, `evi`: yalnız `[kis]`. Kar ve bulut yüzünden kış serisi seyrek; hücre sayısı
      metne yazılır.
  - Var olan dosyalara trendi yeniden hesaplamadan eklemek için:
    `python -m stats.l2 --surum v0.1 --yalniz-isaretler`.
    - Bu komut `anlamli`'yı da `p_fdr` ve GA'dan yeniden türetir; eğim, GA, p ve `p_fdr` değişmez.
    - Kaynak uyumunu ve OZET'i de yeniden yazar.
    - `--dosyalar` ile yalnız bazı dosyalar yeniden hesaplandığında bu adım tüm dosyalar için
      kendiliğinden çalışır.

#### Kaynak uyumu

- **Yol:** `L2_trend/<degisken>__kaynak_uyumu.nc`. Boyutlar `mevsim`, `lat`, `lon`.
- **Hangi değişkenler:** Yalnız birden fazla ürünü olan değişkenler:
  - `yagis`: GPM, GLDAS, MERRA2
  - `sicaklik_2m`: MERRA2, GLDAS
- **Ortak dönem:** Ürünlerin veri dönemlerinin kesişimi. Her ürün bu döneme kırpılır, L2 (FDR dahil)
  yeniden hesaplanır. Dönem `ortak_donem` attr'ında yazılı.
- **`m`** (int16): Hücrede trendi hesaplanabilen ürün sayısı (`anlamli ≥ 0`).
- **`k`** (int16): Anlamlı (`anlamli = 1`) ve aynı yönde trend veren en büyük ürün grubu:
  max(anlamlı artan, anlamlı azalan). Kara maskesi dışında `k = m = -1`.
- **`isaret_uyumu`** (float32, 0–1): Anlamlılığa bakmadan aynı işaretli eğim veren en büyük ürün
  grubu / `m`.
  - Örnek: 3 üründen 2'sinin eğimi negatifse 0,67; üçü de aynı işaretliyse 1.
  - Kara maskesi dışında ya da `m = 0` ise NaN.
  - Her zaman `isaret_uyumu ≥ k/m` olur.
- **attrs:** `urunler`, `ortak_donem`, `alfa_fdr`, `tanim`, `kaynak_doi`, `urun_surumu`,
  `veri_seti_doi`, `lisans`.
- Site bunu "m kaynağın k tanesi aynı yönde anlamlı; yön uyumu %…" diye gösterir.

#### Özet tablo

`L2_trend/OZET.csv` (UTF-8, BOM'lu). Bir satır = bir dosya × bir mevsim. Sütunlar:
- `dosya`, `mevsim`
- `kara_hucre`: trendi hesaplanan kara hücresi sayısı
- `anlamli_artan_yuzde`, `anlamli_azalan_yuzde`: `kara_hucre`'ye göre yüzde
- `medyan_egim`: kara hücrelerinde
- `egim_birimi`
- `trend_uyarisi`: O mevsime düşen uyarılar, tüm-mevsim uyarıları dahil. Uyarı yoksa boş.
- `mk_yedek_hucre`: O mevsimde MK yedeğinin kullanıldığı hücre sayısı.

### 2.2 L3: il ve bölge özetleri (Kişi 2 / Kişi 3)

Üretim: `python -m stats.l3 --surum v0.1` (`stats/l3.py`). Girdi: L1 küpleri (rakım hariç) ve L2 trend
dosyaları.

- **Yollar:**
  - `L3_ozet/<degisken>__<urun>__il.csv` (81 il)
  - `L3_ozet/<degisken>__<urun>__bolge.csv` (7 bölge)
  - `L3_ozet/<degisken>__kaynak_uyumu__{il,bolge}.csv` (`yagis`, `sicaklik_2m`)
  - `L3_ozet/ICINDEKILER.csv`
- **Bölgeler:** İller Natural Earth, coğrafi bölgeler `data/boundaries/bolgeler.yaml`.
  - Hücre seçimi `data.regions.subset` ile, hücre merkezi kuralına göre yapılır.
  - Hiçbir hücre merkezi düşmeyen küçük bölgede, sınıra değen hücreler alınır ve `not` sütununa yazılır.
- **Satır:** Bir il ya da bölge × bir mevsim (`yillik`, `kis`, `ilkbahar`, `yaz`, `sonbahar`).
  CSV'ler UTF-8 (BOM'lu). `bolge_kodu` metin olarak okunmalı (`"01"`).
- **İki tür sonuç:**
  - **(A) Alan ortalaması serisinin trendi:**
    - Bölge hücrelerinin cos(enlem) ağırlıklı ortalaması alınır (`data.regions.area_mean`; NaN hücreler
      atlanır).
    - Sonra L2 ile aynı mevsim serisi, aynı eksik veri kuralı ve aynı trend motoru kullanılır.
    - BH-FDR (α = 0,10) her dosya × mevsim × düzey içinde uygulanır: iller kendi içinde, bölgeler
      kendi içinde.
    - `anlamli` bölüm 2.1'deki anlamlılık kuralıyla belirlenir.
  - **Türkiye satırı:** Bölge CSV'sinde `bolge_anahtari = "turkiye"`, `duzey = "ulke"` satırları
    bulunur (tüm Türkiye kara hücreleri, mevsim başına bir satır).
    - Ayrı bir düzeydir: FDR'ye girmez. Tek satırlık grup olduğundan `p_fdr = p_mk`.
    - Kaynak uyumu bölge CSV'sinde de bulunur.
  - **(B) L2 hücre özeti:** Bölgedeki L2 hücrelerinin özeti.

| Sütun | Anlam |
| --- | --- |
| `bolge_kodu` | İl: iki haneli plaka (`"25"`, `"01"`); bölge: anahtar (`dogu_anadolu`) |
| `bolge_anahtari` | ASCII anahtar (`erzurum`, `dogu_anadolu`); `iller.geojson` içindeki `anahtar` ile aynı |
| `bolge_adi` | Türkçe ad |
| `duzey` | `il`, `bolge` ya da `ulke` (Türkiye satırı, bölge CSV'sinde) |
| `ust_bolge` | İl için bağlı olduğu bölgenin anahtarı; bölgede boş |
| `mevsim` | `yillik`, `kis`, `ilkbahar`, `yaz`, `sonbahar` |
| `hucre_sayisi` | Bölgeye giren 0,25° hücre sayısı |
| `sen_egimi`, `ga_alt`, `ga_ust` | (A) Alan ortalaması serisinin Sen eğimi ve genişletilmiş %95 GA (`egim_birimi`) |
| `p_mk`, `p_fdr`, `anlamli` | (A) Hamed-Rao p; BH q (düzey içinde; `ulke` satırında `p_fdr = p_mk`); `anlamli` bölüm 2.1'deki kuralla `1` / `0`, hesaplanamadıysa `-1` |
| `etkin_n`, `gereken_yil` | (A) L2 ile aynı tanım |
| `mk_yedek` | (A) `1` = Hamed-Rao tanımsız, düzeltmesiz MK kullanıldı |
| `anlamli_hucre_orani` | (B) Bölgede trendi hesaplanan L2 hücrelerinden `anlamli = 1` olanların oranı (0–1) |
| `anlamli_artan_orani`, `anlamli_azalan_orani` | (B) Aynı paydayla, anlamlı ve artan / azalan hücre oranı |
| `medyan_hucre_egimi` | (B) Bölgedeki L2 hücre eğimlerinin medyanı |
| `birim` | Mevsim serisinin birimi (ör. `°C`, `mm/yıl`, `mm/mevsim`) |
| `egim_birimi` | Eğim birimi (ör. `°C / 10 yıl`, `mm/dönem / 10 yıl`) |
| `donem_baslangic`, `donem_bitis` | Alan ortalaması serisinde geçerli ilk ve son yıl |
| `trend_uyarisi` | L2 dosyasındaki uyarıdan o mevsime düşen metin (bölüm 2.1); yoksa boş |
| `not` | `az hücre` (`hucre_sayisi < 3`) ve/veya `merkezi düşen hücre yok; değen hücreler` |
| `kademe`, `dogrulanmadi`, `urun_surumu`, `veri_seti_doi`, `lisans`, `doi` | Ortak alanlar (L1 attrs) |

- **Kaynak uyumu CSV'si:**
  - L2 kaynak uyumuyla aynı tanım, ama hücreler yerine alan ortalaması serileri üzerinden.
  - Ortak dönem L2'dekiyle aynıdır. Her ürün o döneme kırpılır, bölge trendi ve FDR yeniden hesaplanır.
  - Sütunlar: `bolge_kodu`, `bolge_anahtari`, `bolge_adi`, `duzey`, `mevsim`, `k`, `m`, `isaret_uyumu`,
    her ürün için `egim_<urun>` ve `anlamli_<urun>`, ayrıca `egim_birimi`, `ortak_donem`, `urunler`.
- **`ICINDEKILER.csv`:** `dosya`, `tur` (`trend` | `kaynak_uyumu`), `degisken`, `urun`, `duzey`,
  `satir`, `kademe`, `trend_uyarisi` (`evet` / boş), `l2_ozeti` (`evet` ya da L2 bulunamadıysa açıklama),
  `olusturma_tarihi`.

### 2.3 L4: değişken çiftleri arasındaki ilişki (Kişi 3)

> Kişi 3 doldurdu (2026-11-14). Çift listesi ekip belgesindeki ("Veri Ürünü Tanımı") 6 çifttir; ek çift
> yok. Kış = Aralık (Y−1) + Ocak + Şubat (Y); Mart dahil değil.
> **Güncelleme (2026-11-15, genel ilişki motoru):** Çift tanımları koddan `physics/ciftler.yaml` dosyasına
> taşındı (şema aşağıda, "Çift ayar dosyası"). 6 çiftin `ciftler.csv` ve harita çıktısı birebir aynı kaldı.
> Tek çift komutu `python -m physics.iliski` eklendi; çıktısı `L4_iliski/ozel/` altına gider.

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
- **GRACE yıllık ortalaması (çift 4, Kişi 3 kararı 2026-11-14):** Yıl, en az 9 ayı doluysa geçerli sayılır
  (`physics/ciftler.py`, `GRACE_MIN_AY = 9`). GRACE'te 2017–2018 büyük boşluğu dışında da dağınık eksik aylar
  var; 12 ay şartı birçok yılı gereksiz yere atardı. Büyük boşluk yılları (2017: 6 ay, 2018: 7 ay) yine atılır.
  Toplam alınan değişkenlerde (yağış, buharlaşma) eksik aya hiç izin verilmez.

**`ciftler.csv` sütunları:**

| Sütun | Anlam |
| --- | --- |
| `cift_no`, `cift`, `degisken_1`, `degisken_2`, `seri` | Yukarıdaki tablo |
| `gecikme_ay` | Çift 3'te 1 ya da 2; ötekilerde 0 |
| `beklenen_yon` | `+` ya da `-` (ciftler.yaml'da beklentisiz çift için `0`; o zaman anlamlı satırın `etiket`'i boştur) |
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

**Çift ayar dosyası `physics/ciftler.yaml`** (2026-11-15). `physics.run` çiftleri yalnız bu dosyadan okur;
yeni çift = yeni bir madde (`python -m physics.run --ciftler <yaml>` ile başka bir dosya da verilebilir).

| Alan | Zorunlu | Anlam |
| --- | --- | --- |
| `no` | evet | `cift_no`; dosyada benzersiz |
| `ad` | hayır | Kısa Türkçe ad (ekran ve belge için) |
| `x`, `y` | evet | `{degisken, urun}` → `L1_kup/<degisken>__<urun>.nc`. `degisken_1 = x`, `degisken_2 = y` |
| `mevsim` | evet | `yillik`, `kis`, `ilkbahar`, `yaz`, `sonbahar` (yılda bir değer), `mevsimlik` (→ `seri = mevsim_anomali`), `aylik` (→ `aylik_anomali`) |
| `aylar` | hayır | Yalnız `aylik`: y'nin kullanılan ayları. `[4..9]` → `seri = aylik_anomali_nis_eyl` |
| `gecikme_ay` | hayır | Sayı ya da liste (varsayılan 0). x, y'den bu kadar ay önce alınır; her gecikme ayrı satır ve (birden çoksa) ayrı harita |
| `beklenen` | evet | `"+"`, `"-"` ya da `"0"` (beklenti yok; `harita: false` olmalı) |
| `kademe` | evet | 1 ya da 2 |
| `harita` | hayır | `iliski__*.nc` üretilsin mi (varsayılan `true`) |
| `fiziksel_gerekce` | hayır | Beklenen ilişkinin bir cümlelik açıklaması ("ilişki" dili; nedensellik iddiası değil) |
| `not` | hayır | `not` sütununa her satırda yazılır |
| `kar_maskesi_esik` | hayır | Kış ortalaması kar örtüsü bu yüzdenin altındaki hücreler dışarıda (x ya da y `kar_ortusu` olmalı) |
| `etiket_notlari` | hayır | `{beklenen_yonde, ters_yonde, anlamsiz: metin}`: etikete göre ek not (çift 5). Yoksa `ters_yonde` satırına genel "incelenmeli" notu |
| `kalite_kontrolu` | hayır | `true`: güçlü ilişki çıkmazsa "veri sorunu olabilir" notu (çift 6) |
| `rejime_bagli` | hayır | `true`: beklenen yön iklim rejimine bağlı (çift 5). Sapma haritasında su sınırlı yerdeki ters sonuç "rejimle açıklanabilir" sayılır. `true` iken `rejim_gerekcesi` zorunlu |
| `rejim_gerekcesi` | koşullu | Rejime bağlılığın bir paragraflık fiziksel açıklaması |

Dosyanın başında ayrıca `rejim:` bölümü durur: kuraklık göstergesinin girdileri (`yagis`, `buharlasma`:
`{degisken, urun}`, varsayılan GLDAS) ve `su_sinirli_esik` (E/P ≥ eşik → su sınırlı; 0,7). Yer adı ya da yere
özel eşik yazılmaz. Ayrıca dosyanın başında `urun_onceligi: {degisken: [urun, …]}` durur; tek çift komutunda ürün verilmezse
bu sıra (Kademe 1 ana ürünü önce) kullanılır. Değişkene bağlı kurallar kodda kalır: GRACE yıllık ortalaması
için en az 9 ay, birikimli değişkenlerde mevsim toplamı.

**Tek çift çıktısı `L4_iliski/ozel/`** (`python -m physics.iliski … --kaydet`). Yayın paketinin sabit
parçası değildir; kullanıcının istediği çift için üretilir.

| Yol | İçerik |
| --- | --- |
| `L4_iliski/ozel/<x>__<y>__<bolge>__<mevsim>[__gecikmeN].csv` | `<bolge>`: il/bölge anahtarı (`erzurum`, `dogu_anadolu`), `turkiye`, `tum_iller` ya da `tum_bolgeler`. `__gecikmeN` yalnız gecikme > 0 iken eklenir (aynı seçimin farklı gecikmesi üzerine yazılmasın) |

Sütunlar: yukarıdaki `ciftler.csv` sütunları, sonra şu ekler.

| Sütun | Anlam |
| --- | --- |
| `r_ham`, `p_ham` | Trend **çıkarılmadan** korelasyon ve p (aynı etkin n yöntemi). `r` ile farkı büyükse ortak trend ilişkiyi şişiriyor (sahte korelasyon) ya da gizliyor demektir; yorum `r` ile yapılır |
| `egim_x_10yil`, `egim_y_10yil` | İki bölge serisinin doğrusal eğimi (birim / 10 yıl) |
| `yon` | `pozitif` / `negatif` (`r`'nin işareti) |
| `uyari` | L1 `bilinen_sorunlar` / `trend_uyarisi`, Kademe 2 ve ortak trend uyarıları (` \| ` ile ayrılmış) |

Yöntem `ciftler.csv` ile aynıdır. `cift_no` 0 ise seçim ciftler.yaml'daki bir çifte karşılık gelmez; karşılık
geliyorsa o çiftin numarası ve ayarları (kar maskesi, aylar, notlar) kullanılır. Anlamlılık: `tum_iller`'de
81 il üzerinde BH-FDR (`p_fdr ≤ 0,10`); tek il, bölge ve Türkiye satırında `p < 0,05` (`p_fdr` boş).
Beklenen yön verilmezse anlamlı satırın `etiket`'i boştur. GRACE (`toplam_su_depolama`) il için hesaplanmaz.

**Beklentiden sapma `L4_iliski/sapma/`** (2026-11-15, `python -m physics.sapma --surum v0.1`). L4 ve L1'den
türetilir; L4 dosyalarını değiştirmez. **Doğrulanmamış bir göstergedir; nedensellik göstermez.** Sonuçlar
"fiziksel beklentiden sapma" diye okunur; olası açıklamalar iklim rejimi, veri/ürün sorunu ve insan müdahalesidir
(sulama, baraj, yeraltı suyu çekimi).

| Yol | İçerik |
| --- | --- |
| `sapma/sapma_haritasi.nc` | (lat, lon) 28 × 78 harita, değişkenler aşağıda |
| `sapma/sapma_iller.csv` | 81 il satırı (sapma: `ciftler.csv` il etiketlerinden; sulama izi: il alanının cos(enlem) ağırlıklı ortalaması) |
| `sapma/sulama_izi_kumeleri.csv` | En yüksek tepe `sulama_izi` değerli en çok 10 küme |
| `sapma/sapma_haritasi.html` | İsteğe bağlı (`--goster`): sunum için iki panelli harita, il sınırları ve küme numaraları |

Yöntem:
- **Sapma skoru.** Her çiftin L4 etiketi: `ters_yonde` = 1, `beklenen_yonde` / `anlamsiz` = 0, hesaplanamadı = boş.
  Birden çok gecikmeli çiftte bir gecikmede beklenen yön varsa 0, yoksa herhangi bir gecikmede ters ise 1.
  `rejime_bagli` çiftin su sınırlı (E/P ≥ `su_sinirli_esik`) yerdeki tersi `rejimle_aciklanan`'a yazılır ve
  sapma sayılmaz (paydada kalır). `sapma_orani = sapma_sayisi / degerlendirilen`. Haritasız çift (GRACE) hücrede
  ve ilde yer almaz.
- **Kuraklık göstergesi.** GLDAS uzun dönem yıllık buharlaşma / yağış (E/P). GLDAS-2.1 Noah sulamayı simüle etmez.
- **Sulama izi.** 2001–2025 iklimsel yaz (Haz–Ağu) değerleri bütün kara hücrelerinde
  `değer ~ log(1 + yaz yağışı) + log(1 + kış + ilkbahar yağışı) + rakım/1000` EKK regresyonuyla açıklanır (yağış:
  GPM; rakım: SRTM); artık, artıkların standart sapmasına bölünür. `z_yesil`: yaz NDVI (MOD13C2) artığı.
  `z_serin`: yaz (gündüz LST − T2M) artığının eksi işaretlisi (MOD11C3, MERRA-2). `sulama_izi` = mevcut z'lerin
  ortalaması, `n_bilesen` = kullanılan bileşen sayısı. Toprak nemi kullanılmaz (GLDAS model çıktısı, sulama yok).
  Trend değil iklimsel seviye kullanıldığı için MODIS L2 trend uyarısı bu göstergeyi doğrudan etkilemez (not düşülür).
- **Kümeler.** Kara hücrelerinde `sulama_izi`'nin 90. yüzdeliği üstündeki hücreler 8 komşulukla birleştirilir;
  tepe değere göre sıralanır. Yöntemde hiçbir yer adı, kutu ya da yere özel eşik yoktur.

`sapma_haritasi.nc` değişkenleri:

| Değişken | Tip | Anlam |
| --- | --- | --- |
| `sapma_sayisi`, `degerlendirilen`, `sapma_orani` | float32 | Yukarıdaki gibi (deniz ve etiketsiz hücre boş) |
| `rejimle_aciklanan`, `sapma_sayisi_rejim_oncesi` | float32 | Rejimle açıklanan ters sayısı; ayrım yapılmadan ters sayısı |
| `ters_ciftler`, `rejimle_aciklanan_ciftler` | int32 | Bit maskesi: bit (no − 1) = o çift (attrs `flag_masks`, `flag_meanings`) |
| `kuraklik_gostergesi`, `su_sinirli` | float32, int8 | E/P ve `1` = su sınırlı |
| `sulama_izi`, `z_yesil`, `z_serin`, `n_bilesen` | float32, int8 | Sulama izi ve bileşenleri |

attrs: `yontem`, `uyari` ("Doğrulanmadı; neden göstermez. …"), `not` (MODIS ve toprak nemi notu), `girdiler`,
`lisans`, `urun_surumu`, `veri_seti_doi`.

`sapma_iller.csv` sütunları: `bolge_kodu`, `il`, `sapma_sayisi`, `degerlendirilen_cift`, `sapma_orani`,
`ters_ciftler` (ör. `3,5`), `rejimle_aciklanan`, `rejimle_aciklanan_ciftler`, `sapma_sayisi_rejim_oncesi`,
`kuraklik_gostergesi`, `su_sinirli`, `sulama_izi`, `z_yesil`, `z_serin`, `sulama_izi_hucre_en_yuksek`,
`en_yuksek_bilesen`, `not`, `urun_surumu`, `veri_seti_doi`, `lisans`, `uyari`.

`sulama_izi_kumeleri.csv` sütunları: `kume`, `hucre_sayisi`, `tepe_sulama_izi`, `ortalama_sulama_izi`, `tepe_lat`,
`tepe_lon`, `merkez_lat`, `merkez_lon` (skor ağırlıklı), `il` (tepe hücrenin ili), `iller`, `esik`.

**Sapma v2: DENEYSEL, bağımsız doğrulamada başarısız (AUC 0,55)** (2026-11-15,
`python -m physics.sapma --surum v0.1 --v2`). Yöntem v1 sulama iziyle aynıdır. Fark iki noktadadır: (1) regresyondan
sonra tarım maskesi uygulanır; `tarim_orani` < 0,3 olan hücre boş bırakılır. (2) Ek bir 0,05° sürüm üretilir;
bu sürümde NDVI, LST, rakım ve tarım oranı kendi 0,05° dosyalarından, yağış ve T2M ise 0,25°'den en yakın komşu
ile alınır. Bağımsız referansa (GFSAD1KCM 2010, sulanan oran ≥ 0,2) göre maske + 0,05° yapılandırmasında
ROC AUC 0,548'dir (rastgele 0,5) ve en üst %5'teki isabet taban oranın 2,2 katıdır (`docs/dogrulama.md`).
Sunumda yalnız "deneysel" etiketiyle kullanılır. v1 dosyaları değişmez.

| Yol | İçerik |
| --- | --- |
| `sapma/sapma_haritasi_v2_025.nc` | (lat, lon) 28 × 78 |
| `sapma/sapma_haritasi_v2_005.nc` | (lat, lon) 140 × 390 |
| `sapma/sulama_izi_kumeleri_v2.csv` | Küme listesi, 0,05° maskeli sürümden. Sütunlar `sulama_izi_kumeleri.csv` ile aynı |

v2 değişkenleri: `sulama_izi`, `z_yesil`, `z_serin`, `n_bilesen` (v1 gibi; tarım dışı hücre boş), `tarim_orani`
(float32), `tarim_disi` (`1` = maskelendi). attrs: v1'deki gibi, ek olarak `surum = v2`, `tarim_esigi`, `uretim`.

**Doğrulama klasörü `<paket>/dogrulama/`** (yalnız rapor). Bu klasördeki hiçbir dosya sulama izi hesabına girmez;
bunu `tests/test_physics_sapma_v2.py` sınar. Kademe yoktur ve klasör L1 paketinin parçası değildir.

| Yol | İçerik |
| --- | --- |
| `sulanan_oran__GFSAD1KCM.nc` | (lat, lon) 0,25°, `sulanan_oran`: GFSAD1KCM 001 (2010) sınıf 1–2 piksel oranı. Payda sınıf 1–5 ve 9; sınıf 0 (veri yok) paydaya girmez |
| `sulanan_oran__GFSAD1KCM__005.nc` | Aynısı, 0,05° (170 × 410; kutuya kırpılmamış, değerlendirmede hizalanır) |
| `sapma_v2_dogrulama.csv` | `yapilandirma`, `tur` (`ana` \| `duyarlılık`), `izgara`, `tarim_esigi`, `hucre`, `hedef_hucre`, `taban_oran`, `skorlu_hucre`, `auc`, `precision_ust5`, `rastgele_auc`, `kaldirac_ust5` |
| `kume_dogrulama_v2.csv` | `sulama_izi_kumeleri_v2.csv` sütunları + `sulanan_oran_tepe`, `sulanan_oran_3x3`, `hedef_tepe` |

### 2.4 Bulgu karnesi (2026-11-15; `python -m stats.karne --surum v0.1`)

Her trend (L3) ve ilişki (L4) sonucunun yanına şeffaf bir güven karnesi. L2/L3/L4 dosyalarını **değiştirmez**;
`<paket>/karne/` altına ayrı yazılır. Karne bir **sağlamlık ve tutarlılık** özetidir; bir sonucun doğruluğunu
ya da nedenselliğini göstermez. Kural sonuçlar görülmeden sabitlendi (`kural_surumu = karne-v1`) ve
`karne/KURALLAR.txt` dosyasına da yazılır.

| Yol | İçerik |
| --- | --- |
| `karne/trend_karne_il.csv` | L3 il satırları (bütün L1 değişkenleri × 5 mevsim) |
| `karne/trend_karne_bolge.csv` | L3 bölge ve Türkiye (`duzey = ulke`) satırları |
| `karne/iliski_karne.csv` | L4 `ciftler.csv` satırları |
| `karne/KURALLAR.txt` | Güven kuralı, tekrar sayısı, tohum, üretim tarihi |

Her kontrol iki sütundur: durum (`geçti` / `kaldı` / `uygulanamaz`) ve sayı/açıklama. **`uygulanamaz` geçti sayılmaz.**

**Trend kontrolleri** (seriler L3 ile aynı fonksiyonlarla yeniden kurulur):

| Sütunlar | Kontrol | Geçti |
| --- | --- | --- |
| `a_kaynak_uyumu`, `a_sayi` | L3 kaynak uyumu (yalnız `sicaklik_2m`: MERRA2, GLDAS; `yagis`: GPM, GLDAS, MERRA2). Tek ürün → `uygulanamaz` ("tek kaynak"); anlamsız sonuçta da `uygulanamaz` | Satır anlamlı ve bu ürün dahil en az 2 ürün anlamlı ve aynı yönde |
| `b_karistirma`, `b_p_perm`, `b_blok` | Dairesel blok permütasyonu: blok = ceil(n / etkin_n) (en az 1, en çok n/2), 499 tekrar, satıra özgü sabit tohum. p_perm = (1 + #{\|Sen_perm\| ≥ \|Sen\|}) / 500 | p_perm < 0,10 |
| `c_donem`, `c_sayi` | İlk 3 ve son 3 geçerli yıl ayrı ayrı çıkarılır. Alt dönemde FDR uygulanamadığı için anlamlılık p_mk ≤ 0,10 ve %95 GA sıfırı dışlar | İki kırpmada da işaret aynı ve anlamlı |
| `d_esik`, `d_sayi` | α = 0,05: p_fdr ≤ 0,05 ve GA sıfırı dışlar | Anlamlı |
| `e_yeterlilik`, `e_sayi` | Weatherhead `gereken_yil` ile geçerli yıl sayısı | gereken ≤ mevcut |
| `f_uyarilar`, `f_kritik` | `trend_uyarisi`, L1 `bilinen_sorunlar`, Kademe 2 (doğrulanmadı) → **kritik**; `mk_yedek` yalnız listelenir | — |

Diğer sütunlar: `degisken`, `urun`, `bolge_kodu`, `bolge_adi`, `duzey`, `mevsim`, `sen_egimi`, `egim_birimi`,
`ga_alt`, `ga_ust`, `p_fdr`, `anlamli` (L3'ten aynen), `guven`, `gerekce`, `kural_surumu`.

**İlişki kontrolleri** (`iliski_karne.csv`; ayrıca `python -m physics.iliski … --karne`):

| Sütunlar | Kontrol | Geçti |
| --- | --- | --- |
| `a_kaynak_uyumu`, `a_sayi` | x/y'nin pakette bulunan alternatif ürünleriyle (ör. yağış GPM/GLDAS/MERRA2, sıcaklık MERRA2/GLDAS) aynı çift ve kapsam yeniden hesaplanır. Alternatif yok ya da sonuç anlamsız → `uygulanamaz` | Satır anlamlı ve ana kombinasyon dahil en az 2 kombinasyon aynı etiket |
| `b_karistirma`, `b_p_perm`, `b_blok` | Trendi giderilmiş y serisi dairesel blok permütasyonuyla karıştırılır (blok = ceil(n / etkin_n), 499, sabit tohum); \|r_perm\| ≥ \|r\| oranı | p_perm < 0,10 |
| `c_trend`, `c_sayi`, `r_ham` | Trendden arındırma: trendsiz r ile ham r | Aynı işaret ve \|r\| ≥ \|ham r\| / 2 |
| `d_gecikme`, `d_sayi` | Gecikme ±1 ay (negatif gecikme ve `mevsim_anomali` serisi → `uygulanamaz`) | r'nin işareti korunur |
| `e_esik`, `e_sayi` | α = 0,05: il satırında p_fdr ≤ 0,05; bölge/Türkiye satırı zaten p < 0,05 | Etiket aynı |
| `f_uyarilar`, `f_kritik` | Ürün uyarıları (`bilinen_sorunlar`, `trend_uyarisi`, Kademe 2), `rejime_bagli` çift, az hücre (< 3) → **kritik** | — |

**Güven seviyesi** (trend ve ilişki için aynı kural):

| `guven` | Kural |
| --- | --- |
| `YOK` | Sonuç anlamlı değil (trend/ilişki iddiası yok). Trendde `e` kaldıysa gerekçeye "veri henüz yetmiyor" yazılır |
| `DÜŞÜK` | Anlamlı ama `b` ya da `c` geçmedi |
| `YÜKSEK` | Anlamlı; `a`, `b`, `c`, `d`, `e` geçti; kritik uyarı yok |
| `ORTA` | Anlamlı; `b` ve `c` geçti ama `YÜKSEK`'in başka bir şartı sağlanmadı (ör. tek kaynak, `d`/`e` kaldı, kritik uyarı) |

Sonuç: tek ürünlü değişkenler ve mevsimlik seri çifti en çok `ORTA` olabilir (bağımsız ikinci kaynak / gecikme
testi yok). Ürünler ortak girdi paylaşabildiği için `a` bağımsız doğrulama değil, tutarlılık göstergesidir.


### 2.5 Büyüklük testleri (2026-11-15; `python -m physics.buyukluk --surum v0.1 [--test cc|butce|kar_cizgisi]`)

Yön testinin (L4) yanına "ne kadar" testi: gözlenen büyüklük, fiziğin beklediği bantla karşılaştırılır. L1–L4 ve
karne dosyalarını **değiştirmez**; L1 (ve `trend_uyarisi` için L2) yalnız okunur. Çıktı `L4_iliski/buyukluk/`:

| Yol | İçerik |
| --- | --- |
| `<test>__il.csv` | İl satırları (`cc`, `kar_cizgisi`). Su bütçesinde il yok: GRACE il ölçeğine uygun değil |
| `<test>__bolge.csv` | 7 bölge + Türkiye satırı |
| `ozet.csv` | Üç testin bölge ve Türkiye satırları (seçili sütunlar) |
| `KURAL.txt` | Etiket ve güven kuralı, beklenen bantların kaynakları |

Testler (`yol` sütunu):
- **`cc`, Clausius-Clapeyron.** Nem: `ozgul_nem_2m` ve `su_buhari_kolon` (MERRA2); sıcaklık `sicaklik_2m` MERRA2.
  `a_yillar_arasi`: trendi giderilmiş yıllık ln(nem) anomalisinin trendi giderilmiş sıcaklığa EKK eğimi × 100.
  `b_trend_orani`: Sen eğimi(ln nem) × 100 / Sen eğimi(T). Birim %/K. Beklenen 6,6, bant **5,9–7,3 %/K**
  (100·L/(R_v T²), 30 °C ve 0 °C; Held ve Soden 2006). "Beklenenden küçük" satırına kara notu yazılır (Simmons vd.
  2010; Byrne ve O'Gorman 2018); etiket değişmez.
- **`butce`, su bütçesi kapanışı.** Artık = dS/dt − (P − ET − R); dS/dt GRACE'ten merkezî fark (komşu ay yoksa boş),
  P GPM, ET `buharlasma`, R `yuzey_akisi` + `taban_akisi` (GLDAS). `ortalama`: artığın ortalaması (mm/yıl).
  `trend`: aylık artık anomalisinin eğimi ((mm/yıl)/10 yıl) = trend(dS/dt) − trend(P − ET − R); iki terimin ayrı
  trendi `ek` sütununda. Bant **0 ± ortalama yıllık P'nin %10'u** (trendde /10 yıl). Bu bir proje seçimidir
  (kaynak metni `KURAL.txt`'te). Bant dışı satıra olası açıklamalar yazılır; hangisi olduğu iddia edilmez.
- **`kar_cizgisi`, kar çizgisi kayması** (`kis`, `ilkbahar`). Her yıl, bölgedeki 0,25° hücreler 200 m rakım
  dilimlerine ayrılır (dilimde en az 3 hücre); medyan kar örtüsünün %50'yi aşağıdan yukarı kestiği yükselti
  (`physics.shift.snowline_series`). Gözlenen: bu serinin Sen eğimi (m/10 yıl). Beklenen: aynı yıllarda aynı
  bölgenin mevsim sıcaklık trendi (MERRA2) ÷ 6,5 °C/km, bant ÷ **7,5–5,5 °C/km**. En az 4 dolu dilim ve kar
  çizgisinin en az 10 yılda (ve yılların yarısında) tanımlı olması gerekir; yoksa `hesaplanamadı`. Eksik ayı olan
  mevsim düşer (MOD10CM boş ayları; düşen yıllar `ek` sütununda).

**Güven aralığı:** dairesel blok bootstrap (Politis ve Romano 1992), blok = ceil(n / etkin n) (Bretherton vd. 1999
gecikme-1), 999 tekrar, satıra özgü sabit tohum (crc32(anahtar) ^ 2026); GA = 2,5 ve 97,5 yüzdelikleri. Aynı
girdiyle iki çalıştırma bayt bayt aynı dosyayı verir.

**Etiket** (öncelik sırasıyla; `kural_surumu = buyukluk-v1`, sonuçlar görülmeden sabitlendi):

| `etiket` | Kural |
| --- | --- |
| `hesaplanamadı` | GA ya da bant hesaplanamadı (gerekçe `etiket_gerekce`'de) |
| `belirsiz` | GA genişliği > 3 × bant genişliği |
| `beklenen büyüklükle tutarlı` | GA bantla kesişiyor |
| `beklenenden küçük` / `beklenenden büyük` | GA tamamen bandın altında / üstünde |

**Karne kontrolleri ve güven:**

| Sütunlar | Kontrol | Geçti |
| --- | --- | --- |
| `a_kaynak_uyumu`, `a_sayi` | Alternatif ürünle tekrar (cc ve kar: sıcaklık GLDAS; bütçe: yağış MERRA2) | Aynı etiket |
| `b_donem`, `b_sayi` | İlk 3 ve son 3 geçerli yıl ayrı ayrı çıkarılır | İkisinde de aynı etiket |
| `c_ga_genisligi`, `c_sayi` | GA genişliği / bant genişliği | ≤ 1 |
| `uyarilar`, `kritik` | Kademe 2, L1 `bilinen_sorunlar`, L2 `trend_uyarisi` → kritik | — |

| `guven` | Kural |
| --- | --- |
| `YOK` | Etiket `belirsiz` ya da `hesaplanamadı` (büyüklük iddiası yok) |
| `DÜŞÜK` | `b` geçmedi ("uygulanamaz" geçti sayılmaz) |
| `YÜKSEK` | `a`, `b`, `c` geçti; kritik uyarı yok |
| `ORTA` | `b` geçti ama `YÜKSEK`'in başka bir şartı sağlanmadı |

Nem (Kademe 2) ve GLDAS akı/buharlaşma (Kademe 2, `trend_uyarisi`) kullanan satırlar en çok `ORTA` olabilir.

Sütunlar: `test`, `yol`, `degisken`, `urun`, `bolge_turu`, `bolge_kodu`, `bolge_adi`, `hucre_sayisi`, `donem`,
`n`, `gozlenen`, `ga_alt`, `ga_ust`, `birim`, `beklenen`, `beklenen_alt`, `beklenen_ust`, `beklenen_kaynak`,
`etiket`, `etiket_gerekce`, `yorum`, `blok`, `tekrar`, karne sütunları (yukarıda), `guven`, `gerekce`, `ek`,
`kural_surumu`, `urun_surumu`, `veri_seti_doi`, `lisans`. Bu bir büyüklük tutarlılığı özetidir; nedensellik
göstermez.