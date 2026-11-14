# Kişi 3: L4 İlişkiler Katmanı, Uygulama Planı (v2, 2026-11-14)

> Proje kapsamı daraldı. Yeni hedef: **Türkiye için NASA verisinden analize hazır, atıf yapılabilir
> iklim trendi veri seti ve onu gezen basit bir site.** Eski plan (sınır, ayna, kayma, su bütçesi)
> `physics/KISI3_PLAN_eski.md` dosyasında arşivde.

**Dayanaklar:**
- "Trend Dedektifi: Veri Ürünü Tanımı (Türkiye)" belgesi (14.11.2026), özellikle "Değişkenler arası ilişkiler" bölümü
- `docs/sozlesmeler.md` bölüm 2.3 (TASLAK)

**Kurallar:** Kişi 3 yalnızca `physics/` klasörüne ve `tests/test_physics_*.py` dosyalarına yazar. Dal `kisi3-fizik`. Her fazdan önce GitHub'daki ana dal (`main`) alınır. Commit ve push yalnızca kullanıcı "gönder" dediğinde yapılır.

---

## 1. Kişi 3'ün yeni işi (sade anlatım)

Birbirini etkilemesi beklenen değişkenlerin yıldan yıla **birlikte** değişip değişmediğine bakıyoruz. Örnek soru: "Kışı sıcak geçen yıllarda kar az mı oluyor?"

Her çift için, her yerde (hücre, il, bölge, Türkiye) üç etiketten biri verilir:

| Etiket | Anlamı |
|---|---|
| `beklenen_yonde` | İlişki var ve fiziğin beklediği yönde |
| `ters_yonde` | İlişki var ama ters yönde. Araştırmacı için en ilginç yerler bunlar: ya veri sorunu ya da sulama, baraj gibi bir insan etkisi olabilir |
| `anlamsiz` | Belirgin bir ilişki yok |

**"Neden" demiyoruz, yalnızca "ilişki" diyoruz.**

### İncelenecek 6 çift

| # | Çift (L1 dosya adlarıyla) | Seri | Beklenen | Kademe | Not |
|---|---|---|---|---|---|
| 1 | `sicaklik_2m__MERRA2` ~ `kar_ortusu__MOD10CM` | Kış (Ara+Oca+Şub) | − | 1 | Yalnızca kış ortalaması kar örtüsü %10 veya üzeri olan hücrelerde |
| 2 | `yagis__GPM` ~ `toprak_nemi__GLDAS` | Mevsimlik | + | 1 | Yağış toplam, toprak nemi ortalama alınır |
| 3 | `toprak_nemi__GLDAS` ~ `ndvi__MOD13C2` | Aylık anomali, Nisan–Eylül, 1 ve 2 ay gecikmeli | + | 1 | Her gecikme ayrı satır (`gecikme_ay`) |
| 4 | `yagis__GPM` ~ `toplam_su_depolama__GRACE` | Yıllık | + | 1 | Hücre bazında yapılmaz, yalnızca bölge ve Türkiye için. GRACE boşluğundaki yıllar atılır |
| 5 | `sicaklik_2m__MERRA2` ~ `buharlasma__GLDAS` | Yaz (Haz–Ağu) | + | 2 | Kurak yerde zayıf ya da ters çıkabilir; açıklama notu eklenir |
| 6 | `sicaklik_2m__MERRA2` ~ `yuzey_sicakligi_gunduz__MOD11C3` | Aylık anomali | + (güçlü) | 2 | Kalite kontrolü: aynı şeyin iki ölçümü |

### Yöntem (4 kural, belgeden)

1. **Önce trend çıkarılır.** İki seri aynı dönemde artıyorsa aralarında bağ olmasa da korelasyon yüksek çıkar. Bu yüzden her serinin doğrusal trendi çıkarılır, korelasyon geriye kalan "yıldan yıla oynama" üzerinden hesaplanır.
2. **Anlamlılıkta etkin örneklem kullanılır** (Bretherton ve ark. 1999):
   - n_etkin = n · (1 − r₁r₂) / (1 + r₁r₂)
   - p değeri t dağılımından, n_etkin − 2 serbestlik derecesiyle hesaplanır.
3. **Haritalarda şans eseri sonuçlar ayıklanır:** Benjamini-Hochberg FDR, α_FDR = 0,10. Haritada yalnızca Türkiye kara hücreleri, il tablosunda 81 il kullanılır.
4. **Yalnızca bu 6 çift** incelenir. Her şeyi her şeyle karşılaştırmak tesadüfen anlamlı sonuçlar doğurur.

---

## 2. Eski işten ne kalıyor, ne değişiyor?

| Dosya | Durum | Ne olacak |
|---|---|---|
| `_gecici_trend.py` | **Kalıyor, değişiyor** | `lag1_autocorr` ve BH-FDR kodu L4'te kullanılacak. **`winter_mean` Aralık–Mart'tan Aralık–Şubat'a geçmeli** (yeni belge kışı Ara+Oca+Şub tanımlıyor). Yaz, mevsim ve yıllık seriler eklenecek |
| `synthetic.py` | **Kalıyor** | Sahte rakım, kar ve sıcaklık küpleri çift 1'in testinde, GRACE ve yağış çift 4'ün testinde kullanılacak. "İlişkisi bilinen sentetik çift" üreticisi eklenecek |
| `tests_physical._alan_ortalamasi` | **Kalıyor** | Belgedeki kural (alan ağırlığı cos enlem) ile aynı. Yeni modüle taşınacak |
| `run.py` | **Baştan yazılacak** | Çıktı artık `results.json` değil; `L4_iliski/` dosyaları üretilecek |
| `boundary.py`, `mirror.py`, `shift.py`, `climate_velocity`, `water_budget`, `clausius_clapeyron` | **Rafa kalkıyor** (silinmez) | Belgede "sınır kayması göstergeleri" yol haritasına alındı. Kod ve testleri durur, başına "YOL HARİTASI, v0.1'de kullanılmıyor" notu düşülür, `run.py`'den çıkarılır. Sunumda "gelecekte" diye anlatılabilir |
| `tests_physical.label` (uyumlu / celiskili / yetersiz) | **Değişiyor** | Yeni etiketler: `beklenen_yonde` / `ters_yonde` / `anlamsiz` |
| `ornek.py` ve `ornekler/ornek_sonuclar.json` | **Eskidi** | `results.json` biçimi sözleşmeden kalktı. Yerine yer tutucu bir `ciftler.csv` örneği konacak |

---

## 3. Fazlar

Her faz sentetik veriyle test edilir ve testler geçmeden sonraki faza geçilmez.

### Faz 0: Uyum ve kararlar (bugün)
- [x] `main` alındı, yeni sözleşme taslağı okundu
- [x] Eski plan arşivlendi, bu plan yazıldı
- [x] Açık sorular kararlaştırıldı (bölüm 4)
- [x] Sözleşme 2.3'e 6 çift, dosya adları ve sütunlar yazıldı (kullanıcı onayıyla)
- [x] Rafa kalkan modüllere "YOL HARİTASI" notu düşüldü

**Bitti kriteri:** Ekip açık soruları cevapladı ya da varsayımlarımızı kabul etti.

### Faz 1: Tek bir ilişkinin hesaplanması (`physics/iliski.py`)
- `iliski_1d(x, y, beklenen)` fonksiyonu şunları yapar:
  - İki serinin ortak yıllarını alır ve trendlerini çıkarır
  - Hesaplar: r, r₁, r₂, n_etkin, p
  - Etiketi verir
- **Kabul testleri** (sentetik, 1000 seri çifti):
  - Aralarında ilişki olmayan, otokorelasyonlu çiftlerde "anlamlı" oranı %3–7 arasında
  - Bilinen korelasyon geri bulunuyor
  - **Tuzak testi:** İkisi de artan ama birbiriyle ilgisiz iki seri `anlamsiz` çıkıyor (trend çıkarılmasaydı "anlamlı" çıkardı)
  - İşaret ters verilirse etiket `ters_yonde` oluyor

**Durum (2026-11-14): ✅ bitti.** `physics/iliski.py`, `tests/test_physics_iliski.py` (20 test).
- Sahte alarm oranı (ilişkisiz seriler, 1000 deneme): %4–5,5 aralığında, hedef %3–7.
- Küçük örneklem düzeltmesi (r₁ + (1+4r₁)/n) açık. Kapalıyken 24 kışlık hafızalı serilerde oran %8,9'a çıkıyor; bu da bir testle belgelendi.
- Tuzak testi geçti: ortak trendli seriler arasında ham korelasyon 0,8'in üzerinde, trend çıkarılınca tesadüf düzeyine iniyor.

### Faz 2: Serilerin hazırlanması (`physics/seriler.py`)
- Mevsim serileri:
  - Kış Ara(Y−1)+Oca+Şub(Y), ilkbahar, yaz, sonbahar, yıllık
  - Birikimli değişkenlerde (yağış, buharlaşma) toplam, diğerlerinde ortalama alınır
  - Ayın biri eksikse o mevsim NaN olur
- Aylık anomali: 12 aylık ortalama yıl çıkarılır. Nisan–Eylül seçimi yapılır, 1 ve 2 ay gecikme uygulanır
- Çifte özel kurallar:
  - Kar örtüsü %10 maskesi (çift 1)
  - GRACE boşluk yılları (çift 4)
  - İki serinin ortak dönemi
- Kişi 2 mevsim ve anomali serilerini yayımlarsa onlarınki kullanılır; o zamana kadar bizimki

**Durum (2026-11-14): ✅ bitti.** `physics/seriler.py` (mevsim, yıllık, anomali, gecikme, kar maskesi, alan ortalaması), `physics/ciftler.py` (6 çift tablosu ve `cift_serileri`), `tests/test_physics_seriler.py` (17 test).
- Kış = Ara + Oca + Şub; ilk kış 2002, toplam 24 kış. Eski `_gecici_trend.winter_mean` (Ara–Mar) yalnızca rafa kalkan modüllerde kullanılıyor.
- **GRACE kararı:** Yıllık GRACE ortalaması için en az 9 ay şartı var (`GRACE_MIN_AY`). Gerçek GRACE'te büyük boşluk dışında da dağınık eksik aylar bulunuyor; 12 ay şartı birçok yılı gereksiz yere atardı. Büyük boşluk yılları (2017: 6 ay, 2018: 7 ay) yine atılıyor. Yağış gibi toplam alınan değişkenlerde eksik ay hiçbir zaman kabul edilmiyor.
- İkinci tuzak testi: aynı yaz–kış döngüsünü paylaşan ama ilgisiz iki değişken. Ham korelasyon 0,95'in üzerinde, anomali alınınca `anlamsiz`.

### Faz 3: Hücre haritaları (`L4_iliski/iliski__<d1>__<d2>.nc`)
- Çift 4 hariç her çift için her 0,25° kara hücresinde şunlar hesaplanır: r, p, n_etkin, anlamli_fdr, etiket
- Vektörleştirilmiş hesap (1.300 hücre birkaç saniyede)
- **Test:** Sentetik haritada bir bölgeye ilişki, bir bölgeye ters ilişki gömülür; doğru yerler doğru etiketi alır, gerisi `anlamsiz` kalır

### Faz 4: İl, bölge ve Türkiye tablosu (`L4_iliski/ciftler.csv`)
- 81 il, 7 bölge ve Türkiye için alan ağırlıklı (cos enlem) ortalama seriler üzerinden 6 çift hesaplanır
- İl satırlarında FDR, 81 il üzerinden yapılır
- Sütunlar: sözleşme 2.3'teki sütunlar ile belgedeki ek sütunlar (`zaman_olcegi`, `gecikme_ay`, `beklenen_yon`, `anlamli_fdr`) ve ortak alanlar (`urun_surumu`, `veri_seti_doi`, `kademe`, `lisans`, `dogrulanmadi`, `donem`, `seri`)
- Bölge listesi `data.regions` ile alınır (Kişi 1'in Natural Earth il sınırları)

### Faz 5: Yayın paketine bağlantı (`python -m physics.run`)
- L1 küplerini okur (yayın paketi ya da `cache/processed/`) ve `outputs/trend-dedektifi-turkiye-<surum>/L4_iliski/` klasörüne yazar
- Kademe 2 girdili çiftlerde (5, 6) `dogrulanmadi = evet` yazılır
- Gerçek veri yoksa yalnızca `cache/physics/` klasörüne, "YER TUTUCU" işaretli olarak yazar. Yayın paketine asla sentetik sonuç girmez

### Faz 6: Gerçek veriyle çalıştırma ve fizik kontrolü
- Kişi 1'in gerçek L1 dosyalarıyla çalıştırılır
- Akıl kontrolleri:
  - Çift 6 her yerde güçlü pozitif mi? Değilse veri sorunu var
  - Çift 1 dağlarda negatif mi?
- `ters_yonde` çıkan yerlerin listesi incelenip her birine kısa bir açıklama yazılır. Örnek: Konya ovasında sulama, kurak bölgede çift 5
- Kişi 5'e: "İlişkiler" sayfası için haritalar ve `ters_yonde` listesi. Demo adım 4: sıcaklık–kar ilişkisi
- Kişi 4'e: yöntem belgesinin (YONTEM.pdf) L4 paragrafı ve sınırlılıklar

### Faz 7: Jüri hazırlığı
Kısa cevaplar hazırlanacak:
- Neden korelasyondan önce trend çıkarıyoruz?
- Neden etkin örneklem kullanıyoruz?
- Neden yalnızca 6 çift?
- `ters_yonde` ne anlama gelir?
- Neden "neden" değil de "ilişki" diyoruz?

---

## 4. Ekibe sorulacak açık noktalar

| # | Konu | Neden önemli | Önerimiz |
|---|---|---|---|
| 1 | ✅ **Kış tanımı (KARAR 2026-11-14, kullanıcı):** Aralık + Ocak + Şubat. Mart dahil değil | Kişi 2 ile aynı tanım | `winter_mean` buna göre değişecek. İlk kış 2002 (Aralık 2000 yoksa) |
| 2 | ✅ **L4 dosya adları (KARAR):** `L4_iliski/ciftler.csv` (il, bölge, Türkiye tek tabloda, `bolge_turu` sütunu) + çift başına `L4_iliski/iliski__<d1>__<d2>.nc` harita. Ayrı `iliski_iller.csv` yok | Sözleşme 2.3'e yazıldı | — |
| 3 | ✅ **Etiket sütunu:** `etiket` | Sözleşme 2.3 | — |
| 4 | **Klasör adları** (L2/L3): belge ile sözleşme farklı | Bizi etkilemez (`L4_iliski` aynı) | Kişi 1 ve 2 karar versin |
| 5 | ✅ **α:** haritalar ve il satırları FDR 0,10; bölge ve Türkiye p < 0,05 | Sözleşme 2.3 | — |
| 6 | ✅ **Çift 6:** gündüz yüzey sıcaklığı | Sözleşme 2.3 | — |
| 7 | ✅ **Çift 3:** gecikme 1 ve 2 ayrı satır ve ayrı harita dosyası | Sözleşme 2.3 | — |
| 8 | ✅ **Bölgeler:** 81 il, 7 bölge, Türkiye. Çift 4 yalnızca bölge ve Türkiye | Sözleşme 2.3 | — |
| 9 | ✅ **Ek çift yok** (kullanıcı kararı); yalnızca belgedeki 6 çift | — | — |

---

## 5. Bağımlılıklar

- **Kişi 1 (L1 küpleri):** 6 çift için gereken 9 dosya:
  - `sicaklik_2m__MERRA2`, `kar_ortusu__MOD10CM`, `yagis__GPM`, `toprak_nemi__GLDAS`, `ndvi__MOD13C2`
  - `toplam_su_depolama__GRACE`, `buharlasma__GLDAS`, `yuzey_sicakligi_gunduz__MOD11C3`, il maskeleri
  - Bunlar Kişi 1'in yayın paketinde var; bizim makinemize kopyalanmaları gerekiyor
- **Kişi 2:** L4 Kişi 2'nin trend dosyalarını **kullanmaz**. Yalnızca mevsim tanımı ve anomali yönteminde aynı kuralı kullanmamız gerekir (madde 1)
- **Kişi 5:** `ciftler.csv` ve `.nc` dosyalarının sütunlarını okuyacak. Faz 4 bitince bir örnek dosya verilecek

## 6. Windows notu
Testler `.venv/Scripts/python -m pytest -q --basetemp=D:/pytest_tmp` ile çalıştırılır. Kullanıcı adındaki "Ü" harfi netCDF4'ü bozuyor.
