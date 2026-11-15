# Ülke parametresi ve Yunanistan L1 paketi (2026-11-15)

Kural: `docs/sozlesmeler.md` 1.2. Ülke ayarları: `data/ulkeler.yaml`. Varsayılan `turkiye`; `--ulke` verilmezse
her şey eskisi gibi çalışır.

## Komutlar

```bash
# 1) (yeni ülke için bir kez) sınır dosyaları + yayın kutusu → data/boundaries/yunanistan/
python -m data.make_boundaries --ulke yunanistan

# 2) indir + işle → cache/raw/yunanistan/<urun>/, cache/processed/yunanistan/  (~24 dk)
python -m data.build --ulke yunanistan --sadece-ana \
    --vars sicaklik_2m,kar_ortusu,yagis,toprak_nemi,ndvi,toplam_su_depolama,buharlasma,yuzey_sicakligi_gunduz,rakim

# 3) L1 yayın paketi → outputs/trend-dedektifi-yunanistan-v0.1/L1_kup/
python -m data.export --ulke yunanistan --surum v0.1

# yalnız özet
python -m data.build --ulke yunanistan --ozet
```

Earthdata girişi yalnız `earthaccess.login(strategy="netrc")` ile yapılır; giriş başarısızsa komut durur.

## Kişi 3 için: fizik tarafı

- **Paket:** `outputs/trend-dedektifi-yunanistan-v0.1/`. Fizik komutlarına `--paket` ile verilir, ör.
  `python -m physics.buyukluk --paket outputs/trend-dedektifi-yunanistan-v0.1`. Komutun hangi dosyaları
  istediğine bakın: Yunanistan paketinde yalnız 9 dosya var.
- **Ülke kara maskesi:** `data.regions.ulke_maskesi(lat, lon, "yunanistan")`, (lat, lon) boolean dizi döndürür.
  Paketteki `domain: land` maskesiyle aynıdır: hücre merkezi Natural Earth GRC sınırının içinde.
  ```python
  from data.regions import ulke_maskesi
  m = ulke_maskesi(da["lat"].values, da["lon"].values, "yunanistan")
  ```
- **Bölge çözümleme:** `data.regions.subset(ds, "yunanistan")` (ya da `"grc"`, `"Greece"`) ülkenin tamamını keser.
  İl, bölge ve deniz adları yalnız Türkiye içindir.
- **Türkiye'ye bağlı kalan yerler** (veri katmanı dışı, değiştirilmedi):
  - `physics.tablo.bolge_listesi` / `bolge_maskeleri`: 81 il + 7 bölge + Türkiye.
  - `physics.tek_cift.paket_koku`, `physics.run`, `physics.sapma`, `stats.preprocessing.paket_koku`: varsayılan
    yol `trend-dedektifi-turkiye-<surum>`. `--paket` verilebiliyor.
  - `app/urun_io.py`, `llm/evidence.py`: Türkiye paketini arar.
- **Veri katmanında Türkiye'ye özgü kalanlar:**
  - `data/arazi.py` (tarım oranı, GFSAD): yalnız Türkiye, `TURKIYE_BBOX`.
  - `data/synthetic.py`: Türkiye benzeri sentetik alan.
  - `data/check_giovanni.py`: Türkiye kutuları.
  - `regions` il, bölge ve deniz listeleri.

## Yunanistan paketi

`outputs/trend-dedektifi-yunanistan-v0.1/L1_kup/`: 8 zamanlı dosya + `rakim__SRTM`, `ICINDEKILER.csv`.
- **Yayın kutusu:** 19,5–28,25 D, 34,75–42,0 K, yani 29 × 35 hücre. Natural Earth GRC sınırının dış kutusu
  0,25°'ye dışa doğru yuvarlandı. NE 10m çokgeninde Meis (Kastellorizo) yok.
- **İşleme kutusu:** 19,0–30,0 D, 34,5–42,0 K. İndirme kesiti bunun 1° fazlası.
- **Kara hücresi:** 218, Natural Earth 10m admin-0 sınırı, adalar dahil.
- **Attr'lar:** Türkiye'yle aynı biçimde (`kademe`, `doi`, `urun_surumu`, `veri_seti_doi`, `lisans`, `domain`,
  `bilinen_sorunlar`). Ek olarak `ulke = yunanistan`, `ulke_adi`, `ulke_iso3 = GRC`.
- **GRACE:** `bilinen_sorunlar` alanında mascon çözünürlüğü notu var (~300 km; küçük ve kıyısı uzun ülkede komşu
  ve deniz sinyali karışır).

### Kontroller (Türkiye'yle aynı fonksiyon)

| Dosya | Birim | Kara hücresi | min … medyan … max | Tamamen NaN ay | Sözleşme |
| --- | --- | --- | --- | --- | --- |
| `sicaklik_2m__MERRA2` | °C | 1015 (domain `all`, bütün kutu) | −8,4 … 17,0 … 32,0 | 0 | uygun |
| `kar_ortusu__MOD10CM` | % | 207 | 0 … 0,04 … 100 | 5 (Türkiye'yle aynı aylar) | uygun |
| `yagis__GPM` | mm/ay | 218 | 0 … 48,7 … 514,6 | 3 (2025-10 … 12, IMERG gecikmesi) | uygun |
| `toprak_nemi__GLDAS` | kg/m² | 198 | 7,2 … 25,5 … 46,5 | 0 | uygun |
| `ndvi__MOD13C2` | 1 | 216 | 0,20 … 0,55 … 0,86 | 0 | uygun |
| `toplam_su_depolama__GRACE` | cm | 218 | −42,4 … −1,2 … 44,1 | 35 (Türkiye'yle aynı aylar) | uygun |
| `buharlasma__GLDAS` | mm/ay | 198 | 0,5 … 42,2 … 170,2 | 0 | uygun |
| `yuzey_sicakligi_gunduz__MOD11C3` | °C | 217 | −6,7 … 20,6 … 44,8 | 0 | uygun |
| `rakim__SRTM` | m | 218 | 5 … 358 … 1456 | (sabit) | uygun |

- Fiziksel aralık dışında değer yok. Aralıklar betikte sabitlendi: sıcaklık −40…50, yağış 0…1500, NDVI −0,2…1 vb.
- Tamamen NaN aylar küresel ürünlerin arşiv boşlukları; Türkiye paketindekilerle birebir aynı (`docs/dogrulama.md`
  "Bilinen boşluklar").
- GLDAS 198 hücre: GLDAS'ın kendi kara maskesi küçük adaları ve kıyı hücrelerinin bir kısmını dışarıda bırakıyor.
  Türkiye'de de 1287 / 1303. MOD10CM 207 hücre: kıyı ve ada hücrelerinde kar örtüsü değeri yok.

### Akıl kontrolü

- **Yıllık ortalama sıcaklık** (MERRA-2, 218 kara hücresi, cos(enlem) ağırlıklı): **15,5 °C**, yıllar arası
  14,6–17,1. Makul: Yunanistan'ın düşük kıyı ve yüksek iç kesimlerinin ortalaması bu düzeyde.
- **Yıllık yağış** (GPM, 2001–2024): **763 mm** (591–927).
  - Batı (lon < 21,5) 1006 mm, güneydoğu Ege 680 mm.
  - Batının daha yağışlı olması Pindus'un batı yamacı ve İyon kıyısıyla uyumlu.
- **Kar:**
  - Kış (Ara–Şub) ortalama kar örtüsü kuzeyde (enlem ≥ 39,5) %14,6, güneyde (< 38) %4,4.
  - En karlı hücre 39,6 K, 21,4 D (Pindus, Metsovo–Tzoumerka çevresi): %60, 0,25° ortalama rakım 1258 m.
  - Kış ortalaması ≥ %20 olan 41 hücre; rakım medyanı 985 m. 24'ü kuzeyde (≥ 39,5), 15'i 38–39,5 kuşağında
    (orta Yunanistan dağları), 2'si 38'in güneyinde (Mora dağları).
  - Kuzeyde (Pindus / Makedonya) kar var.

### Süre ve boyut

- Toplam 23,5 dk (indirme + işleme, 8 ürün, 1810 dosya, hata yok). Export birkaç saniye.
- Diske yazılan ham kesit 354 MB (`cache/raw/yunanistan/`). İşlenmiş dosyalar 15,7 MB, L1 paketi birkaç MB.
- Ağdan aktarılan veri yaklaşık 0,8 GB (**tahmin**). Bu sayı ölçülmedi:
  - OPeNDAP ürünlerinde yalnız kesit aktarıldı (diskteki kesit boyutu kadar).
  - MOD10CM tam dosya indirilip silindi (~0,37 GB, CMR boyutu).
  - GRACE tek dosya (45 MB) ve SRTM 4 karo tam indirildi.
