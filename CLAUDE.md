# Proje bağlamı (Claude Code için)

Bu repo NASA Space Apps Challenge 2026 "Earth System Trend Detective" için 5 kişilik bir ekibin
projesi: **Trend Dedektifi**. Kullanıcı bir soru sorar , araç belirti ve şüpheli değişkenleri seçer, NASA verisini çeker, trend ve
anlamlılık testleri yapar, fiziksel tahminlerle karşılaştırır ve her sayısı analiz çıktısına bağlı
bir kanıt tablosu üretir.

## Kurallar

- Her kişi yalnızca kendi klasöründe değişiklik yapar (README'deki tablo). Başka bir klasöre
  dokunmak gerekiyorsa önce kullanıcıya sor.
- Modüller arası tek bağlantı `docs/sozlesmeler.md` içindeki veri ve sonuç sözleşmeleridir.
  Sözleşmeyi değiştirme; uyumsuzluk görürsen kullanıcıya bildir.
- Şifre, token veya `.netrc` içeriğini asla koda, loga ya da repoya yazma. Earthdata girişi
  `earthaccess.login(strategy="netrc")` ya da ortam değişkenleriyle yapılır.
- İndirilen ve üretilen veri `cache/` altında durur ve git'e girmez.
- Kod Python 3.10+; bağımlılıklar `requirements.txt` içinde. Yeni paket eklersen oraya da yaz.
- Fonksiyonlar küçük, belgelenmiş (docstring) ve `tests/` altında sentetik veriyle test edilebilir olsun.
- Kod yorumları ve kullanıcıya dönük mesajlar Türkçe, değişken/fonksiyon adları ASCII olabilir.
- Sayı uydurma: örnek veya yer tutucu değerler açıkça "yer tutucu" diye işaretlenir.
