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
