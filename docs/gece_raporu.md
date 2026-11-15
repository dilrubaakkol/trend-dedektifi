# Gece raporu: sapma haritası v2 (2026-11-15, 02:08–03:15)

Dal: `sapma-v2` (`bulgu-karnesi` HEAD'i `db6d7b9`'dan açıldı). Push yapılmadı, main'e dokunulmadı.

## Kısa sonuç

- v2 (tarım maskesi + 0,05°) çalışıyor, ama **bağımsız referansa (GFSAD) göre sulanan alanı genel sıralamada
  çok zayıf ayırt ediyor: ROC AUC 0,55–0,58** (rastgele 0,5).
- Listenin tepesi belirgin biçimde iyileşti: en yüksek %5'te sulanan hücre oranı v1'de taban oranın altındayken
  (0,75×) v2'de taban oranın **2,2 katı**.
- Referansın kendisi Türkiye için şüpheli: GFSAD 2010 Konya ovasını ve Ceylanpınar'ı neredeyse tamamen "yağmura
  dayalı" sayıyor. Bu yüzden ne "yöntem çalışıyor" ne de "yöntem çalışmıyor" kesin söylenebilir.
- Mevcut çıktıların hiçbiri değişmedi (md5); 369 test geçti.

## Ne yapıldı

| Adım | Durum | Ayrıntı |
| --- | --- | --- |
| 0. Hazırlık | ✅ | `sapma-v2` dalı; `outputs/…v0.1/` altındaki 132 dosyanın md5 listesi alındı |
| A1. MCD12C1 tarım oranı | ✅ | CMR: MCD12C1 v061, DOI 10.5067/MODIS/MCD12C1.061, LPCLOUD, 2001–2025. 2021–2025 (5 yıl) |
| A2. GFSAD sulanan oran | ✅ | CMR: GFSAD1KCM v001, DOI 10.5067/MEASURES/GFSAD/GFSAD1KCM.001 (2010). Yalnız `dogrulama/` altında |
| B. v2 yöntemi | ✅ | `python -m physics.sapma --surum v0.1 --v2`; v1 varsayılanı ve dosyaları değişmedi |
| C. Bağımsız doğrulama | ✅ (sınırlı) | 4 yapılandırma, AUC, precision@%5, kümeler; `docs/dogrulama.md` |
| D. Testler | ✅ | 369 geçti, 2 atlandı, 0 başarısız (yeni: `test_data_arazi.py`, `test_physics_sapma_v2.py`) |
| E. Commit, md5, rapor | ✅ | 5 commit; md5: değişen 0, silinen 0, yeni 8 |

**İndirme:** Earthdata girişi `earthaccess.login(strategy="netrc")` ile başarılı.
- GFSAD1KCM: 1 GeoTIFF, 33 MB, 23 sn.
- MCD12C1: 5 HDF4, **6,22 GB, 51 dk**. Bu üründe Cloud OPeNDAP yok, bu yüzden tam dosyalar indirildi.
- Ham dosyalar `cache/raw/MCD12C1/` ve `cache/raw/GFSAD1KCM/` altında duruyor (git dışı, silinmedi).
- İşleme süresi: tarım oranı 2 sn, v2 ve doğrulama 7 sn.

**Yeni dosyalar** (yalnız eklendi):
- `L1_kup/tarim_orani__MCD12C1.nc`: sabit, kademe 2, `dogrulanmadi=evet`, 28 × 78.
- `L4_iliski/sapma/sapma_haritasi_v2_025.nc`, `sapma_haritasi_v2_005.nc`, `sulama_izi_kumeleri_v2.csv`.
- `dogrulama/sulanan_oran__GFSAD1KCM.nc`, `…__005.nc`, `sapma_v2_dogrulama.csv`, `kume_dogrulama_v2.csv`.
- Ayrıca `cache/processed/turkiye/tarim_orani__MCD12C1.nc` ve `…__005.nc`.

## Dört yapılandırma

Hedef: GFSAD sulanan oran ≥ 0,2.

| Yapılandırma | ROC AUC | precision@%5 | Taban oran | Kaldıraç |
| --- | --- | --- | --- | --- |
| v1 (0,25°, maskesiz) | 0,577 | 0,061 | 0,081 | 0,75 |
| maske (0,25°) | 0,545 | 0,152 | 0,081 | 1,88 |
| 0,05° (maskesiz) | 0,581 | 0,121 | 0,097 | 1,25 |
| maske + 0,05° | 0,548 | 0,215 | 0,097 | **2,21** |

**Katkılar:**
- **Çözünürlük:** AUC'yi neredeyse değiştirmiyor (+0,004); tepedeki isabeti 0,75×'ten 1,25×'e çıkarıyor.
- **Maske:** AUC'yi 0,03 düşürüyor; tepedeki isabeti 1,88×'e çıkarıyor. Düşüşün nedeni şu: GFSAD'ın sulanan dediği
  hücrelerin %62'si MODIS tarım ≥ 0,3 maskesinin dışında kalıyor ve en düşük skoru alıyor.
- **Maske eşiği duyarlılığı (0,2 / 0,5):** sonuçları anlamlı değiştirmiyor (AUC 0,50–0,57).
- *Tanı:* Yalnız tarım hücreleri içinde AUC 0,67–0,70. Bu önceden tanımlı yapılandırmalardan biri değil, yalnız tanı.

**En yüksek 10 küme (maske + 0,05°):**
- 1–2 Şanlıurfa (Harran; Ceylanpınar–Viranşehir), 3 ve 5 Konya, 4 Afyonkarahisar, 6 Ağrı, 7 Van, 8 Yozgat,
  9 Malatya, 10 Samsun.
- GFSAD'a göre tepe hücresi hedef olan: 2/10 (Ağrı, Malatya).
- Genel bilgiye göre (kör değil, kanıt değil) ilk kümelerin çoğu bilinen sulama alanlarına düşüyor; v1'de bu 10'da 1'di.
- Konum ve sınıf ayrıntısı: `docs/dogrulama.md`.

## Karşılaşılan sorunlar ve verdiğim kararlar

1. **MCD12C1'de OPeNDAP yok.** Kesit sunucuda alınamadığı için 6,22 GB tam dosya indirildi. Disk alanı yeterliydi
   (111 GB boş). Ham dosyalar silinmedi; isterseniz `cache/raw/MCD12C1/` silinebilir.
2. **Ortak `data/fetch.py` değiştirilmedi.** OPeNDAP okuyucusu sınıf boyutunu (17 IGBP katmanı) desteklemiyor.
   Mevcut yardımcıları kullanan ayrı bir `data/arazi.py` yazdım; sınıf eşlemesini dosyanın kendi özniteliklerinden
   doğruladım (Layer 12 croplands, 14 mosaic, dolgu 255).
3. **Katalog:** `data/catalog.yaml`'a yalnız iki *ürün* kaydı eklendi (`okuyucu: ozel`). Değişken kaydı eklenmedi;
   böylece toplu `fetch`/`harmonize` akışı bu ürünleri denemez (testle doğrulandı).
4. **GFSAD sınıfları:**
   - İlk varsayımım yanlıştı (0'ı "tarım dışı" sanmıştım).
   - Alt ajan resmî sayfadan tabloyu çıkaramadı. Kılavuz PDF'ini yerelde açıp 2.2.4 tablosunu buldum:
     **0 veri yok, 9 tarım dışı**, 1 sulama majör, 2 sulama minör, 3–5 yağmura dayalı.
   - Katmanı üretmeden önce düzelttim.
   - "Sulanan" = sınıf 1 ve 2, eşit ağırlıkla (en basit, önceden sabit seçim).
5. **Maske regresyondan sonra uygulandı.** Bu, "regresyon biçimi aynı" şartını birebir korumak için seçildi.
   Regresyonu yalnız tarım hücrelerinde kurmak denenmedi; sonuca bakıp seçmek yasaktı.
6. **0,05°'de rakım ve tarım oranı** en yakın komşu değil, kendi 0,05° dosyalarından alındı (SRTM 0,05°, MCD12C1
   0,05°). Yalnız yağış ve T2M en yakın komşu ile aktarıldı. Dosya attr'larında yazılı.
7. **L1 `ICINDEKILER.csv` güncellenmedi.** Güncellemek mevcut bir dosyayı değiştirirdi (DUR koşulu). Yeni katman
   klasörde var ama içindekiler listesinde yok.
8. **`docs/sozlesmeler.md` değiştirilmedi** (CLAUDE.md kuralı; görevde istenmedi). Yeni katman ve çıktıların
   sözleşmeye eklenmesi sabaha bırakıldı.
9. **`requirements.txt`'e `rasterio` eklendi** (GFSAD GeoTIFF). Bu bilgisayarda zaten kuruluydu.
10. **Tek çift komutu:** zamansız `tarim_orani` değişken listesinde gösterilmiyor; seçilseydi hata verirdi.
11. **Zaman uyumsuzluğu:** referans 2010, tarım oranı 2021–2025. Sulama alanları bu sürede büyüdüyse bu fark
    ölçütleri düşürür.
12. **Bir test beklentisi** benim yanlış hesabımdı (AUC örneği). Testi düzelttim, kodu değil.

**md5 sonucu:** önce 132, sonra 140 dosya; **değişen 0, silinen 0, yeni 8** (listesi yukarıda).
**Test sonucu:** `pytest -q` → 369 geçti, 2 atlandı, 0 başarısız.

## Sunumda kullanılabilir mi?

**Ancak "deneysel" etiketiyle ve kısa.** Harita görsel olarak v1'den çok daha mantıklı: kümeler orman ve kıyı
yerine Harran, Konya ve Ceylanpınar gibi tarım ovalarına düşüyor. Ama bunu söyleyen benim genel bilgim. Ölçülebilir
bağımsız doğrulama zayıf (AUC ≈ 0,55); tek olumlu ölçüt tepedeki isabetin 2,2 kat artması. Referansın da sorunlu
olması, iddiayı iki yönde de belirsiz bırakıyor. "Sulamayı bulduk" denmemeli.

**Ekranda okunacak 2 cümle:**
> "Tarım alanlarıyla sınırlayıp 5 kat ince çözünürlüğe geçince, yazın yağışın açıkladığından yeşil ve serin kalan
> yerler Harran ve Konya gibi tarım ovalarında toplanıyor; en üst yüzde 5'lik dilimde bağımsız bir NASA sulama
> haritasıyla örtüşme şansın 2,2 katı. Ama genel ayırt etme gücü zayıf (AUC 0,55) ve referans haritanın kendisi
> Türkiye'de yeraltı suyu sulamasını kaçırıyor; bu yüzden bu bir kanıt değil, insan müdahalesiyle tutarlı
> olabilecek, doğrulanmamış bir sapma göstergesidir."

## Sabah yapmanız gerekenler

1. Raporu ve `docs/dogrulama.md` "Sapma haritası v2" bölümünü okuyun; sunumda kullanıp kullanmayacağınıza karar verin.
2. **Push ve PR sırası:** `sapma-v2`, henüz main'e girmemiş `bulgu-karnesi`'nin üzerinde. Önce `bulgu-karnesi`
   birleşmeli:
   ```bash
   git push -u origin bulgu-karnesi
   # GitHub'da PR: https://github.com/dilrubaakkol/trend-dedektifi/pull/new/bulgu-karnesi  (base: main)
   git push -u origin sapma-v2
   # bulgu-karnesi birleşince PR: https://github.com/dilrubaakkol/trend-dedektifi/pull/new/sapma-v2  (base: main)
   ```
   (`gh` bu bilgisayarda kurulu değil; PR'lar web arayüzünden açılır.)
3. Kararlar:
   - L1 `ICINDEKILER.csv`'ye `tarim_orani__MCD12C1.nc` satırı eklensin mi?
   - Sözleşmeye (1.1 L1 dosyaları, 2.3 sapma v2, yeni `dogrulama/` klasörü) bölüm eklensin mi?
4. Diğer bilgisayarlarda `pip install -r requirements.txt` (`rasterio` eklendi).
5. İsterseniz 6,2 GB ham dosya silinebilir: `cache/raw/MCD12C1/`. Tarım oranı katmanı işlendi; ham dosya yalnız
   yeniden üretim için gerekir.
