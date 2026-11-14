# LLM katmanı (Kişi 4)

Hedef kitle: **akademisyenler**. Araç, bir araştırma sorusunu NASA verisi üzerindeki hazır trend ve ilişki
analizlerine bağlar; bulgular paragrafı, yöntem paragrafı, veri atfı ve uyarıları tek seferde verir.

**Kural:** LLM sayı üretmez ve hesap yapmaz. Yalnızca (1) soruyu katalogdan bir seçime çevirir,
(2) kanıtları anlatır. Her sayı analiz paketinden (L3/L4) gelir ve doğrulayıcıdan geçer. Yöntem paragrafı,
veri atfı ve kaynakça LLM'e **yazdırılmaz**; şablonla üretilir (makalede hata kabul edilemez).

## Akış

```
soru ─► plan_question ─► collect_evidence ─► açıklama (LLM) ─► verify_text ─┬─► geçti: göster
        (LLM seçer, kod     (L3_ozet/*.csv,       her sayılı      sayılar/ref'ler │
         doğrular; yedek:    L4_iliski/ciftler)   cümlede [ref])  kontrol         └─► kaldı: en fazla 2 kez
         anahtar kelime)                                                              düzeltme talimatıyla
                                     └─► academic: yöntem, veri atfı, kaynakça,       yeniden üret, sonra
                                                    dosyalar, uyarılar (şablon)        şablon açıklama
```

| Dosya | Görevi |
| --- | --- |
| `kb.py` | `kb/` kartlarını okur; yer adı → il/bölge anahtarı (`data/regions.py` ile aynı), anahtar kelime eşleştirme |
| `plan.py` | Soru → plan (kart, belirti, şüpheliler, bölge + düzey, **gerekçe**). İlçe adı geçerse LLM ilini yazar |
| `evidence.py` | Analiz paketi → kanıt listesi. L3 il satırı yoksa ilin bölgesine, L4'te bölge/Türkiye'ye düşer; ürünler arası yön uyumunu sayar |
| `explain.py` | Kanıt → bulgular metni (LLM ya da şablon) + kanıt tablosu. `kitle="akademisyen"` (varsayılan) ya da `"genel"` |
| `academic.py` | Yöntem paragrafı, NASA ürün atıfları (katalogdaki DOI/sürüm), yöntem kaynakçası, kullanılan dosyalar, hakem uyarıları |
| `verify.py` | Metindeki sayılar kanıtta var mı (Türkçe ve İngilizce yazım), `[ref:id]`'ler gerçek mi, sayılı cümleler kaynaklı mı |
| `format_tr.py` | Projedeki **tek** sayı biçimlendirici: `format_tr(-2.1, "mm", 1)` → `"−2,1 mm"`. Arayüz de bunu kullanır |
| `answer.py` | Orkestratör |
| `client.py` | Anthropic ya da OpenAI uyumlu API istemcisi (anahtar yalnızca ortam değişkeninden) |

## Arayüzden kullanım (Kişi 5)

```python
from llm import answer, format_tr

out = answer("Konya'da toprak nemi azalıyor mu, sıcaklıkla ilişkili mi?")   # paket: outputs/ ya da TD_PAKET
out["message"]            # doluysa kullanıcıya sor (bölge eksik/desteklenmiyor/sonuç yok)
out["plan"]["gerekce"]    # neden bu değişkenlere bakıldı
out["explanation"]        # markdown; [ref:id] -> kanıt tablosundaki satır
out["evidence"]           # kanıt satırları (ham sayılar; göstermek için format_tr)
out["methods"]            # "Veri ve yöntem" paragrafı
out["data_citations"]     # NASA ürünleri + proje veri paketi atıfları
out["method_references"]  # Sen 1968, Hamed-Rao 1998, Benjamini-Hochberg 1995, ...
out["files"]              # kullanılan paket dosyaları (indirme bağlantısı için)
out["academic_warnings"]  # Kademe 2, gereken yıl > seri, ürün uyumsuzluğu, değişken notları
```

## LLM ayarı (ortam değişkenleri, repoya yazılmaz)

```bash
export LLM_PROVIDER=anthropic   # ya da openai (Groq, Gemini OpenAI-uyumlu uç, Ollama için LLM_BASE_URL)
export LLM_MODEL=<model adı>
export LLM_API_KEY=<anahtar>
export TD_PAKET=outputs/trend-dedektifi-turkiye-v0.1   # isteğe bağlı; yoksa en yeni sürüm aranır
```
LLM ayarı yoksa sistem LLM'siz çalışır: anahtar kelime planlayıcı + şablon bulgular.

## Bilgi tabanı (`kb/`)

- `kb/cards/*.yaml` — 8 süreç kartı (kar, kuraklık, ısınma, nem, bitki örtüsü, su kaynakları, akış, hava kalitesi)
- `kb/degiskenler.yaml` — `data/catalog.yaml`'daki tüm değişkenlerin kartı (test bunu denetler);
  ertelenen ürünler `henuz_veri_yok: true`
- `kb/yerler.yaml` — 81 il ve 7 bölge; anahtarlar `data/regions.py` ile aynı (test bunu denetler)
