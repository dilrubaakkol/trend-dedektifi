# Sınır dosyaları

| Dosya | İçerik | Kaynak |
| --- | --- | --- |
| `iller.geojson` | 81 il (özellikler: `plaka`, `ad`, `anahtar`, `iso_3166_2`) | Natural Earth 10m Admin-1 (`ne_10m_admin_1_states_provinces`), `adm0_a3 == "TUR"` |
| `kara.geojson` | Kutudaki tüm kara (komşu ülkeler dahil); deniz maskesi bunun tersidir | Natural Earth 10m Land + Minor Islands |
| `denizler.geojson` | Karadeniz, Marmara (+ İstanbul ve Çanakkale boğazları), Ege (+ Girit Denizi), Akdeniz; karadan arındırılmış | Natural Earth 10m Marine Polygons |
| `bolgeler.yaml` | 7 coğrafi bölge → il listesi (elle yazıldı) | 1941 Coğrafya Kongresi bölümlemesi, il bazında yaygın atama |
| `il_adlari.yaml` | İl adı düzeltmeleri (NE `name_tr` → kullanılan yazım, ör. Elâzığ → Elazığ); `data.regions` okurken uygular, geojson elle değiştirilmez | Elle yazıldı |

- **Lisans:** Natural Earth verisi kamu malıdır (public domain); atıf zorunlu değildir ama önerilir:
  "Made with Natural Earth. Free vector and raster map data @ naturalearthdata.com".
- **Sürüm:** `nvkelso/natural-earth-vector`, commit `ca96624a56bd078437bca8184e78163e5039ad19`
  (GitHub `master`, 2022-06-02; Natural Earth 5.1.x).
- **İşlem:** `python -m data.make_boundaries` — kutuya (TURKIYE_BBOX + 1°) kesme, ~0,005° toleransla
  sadeleştirme (iller ortak kenarları koruyan `shapely.coverage_simplify` ile), koordinatlar 4 ondalık.
- Natural Earth `name` alanında hatalar olduğu için (ör. "Zinguldak") il adı olarak `name_tr` kullanıldı.

## Neden geoBoundaries değil?

geoBoundaries TUR ADM1 (gbOpen) OpenStreetMap kaynaklıdır ve lisansı **CC BY-SA 2.0**'dır (CC BY değil;
API'de `boundaryLicense`). Paylaşım-aynı-lisans koşulu ve kara/deniz maskesiyle kıyı çizgisi
tutarlılığı için tek kaynak (Natural Earth, kamu malı) seçildi. 0,05° (~5 km) ızgara için 1:10M
ölçeği yeterlidir. Daha ayrıntılı sınır gerekirse `make_boundaries.py` geoBoundaries'e çevrilebilir;
o durumda bu README'ye CC BY-SA atfı eklenmelidir.
