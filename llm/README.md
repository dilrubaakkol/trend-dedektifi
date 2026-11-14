# LLM katmanı (Kişi 4)

**Kural:** LLM sayı üretmez ve hesap yapmaz. Yalnızca (1) soruyu katalogdan bir seçime çevirir,
(2) analiz sonuçlarını sade dille anlatır. Her sayı `results.json`'dan gelir ve doğrulayıcıdan geçer.

## Akış

```
soru ──► plan_question ──► run_analysis(plan) ──► açıklama (LLM) ──► verify_text ──┬─► geçti: göster
         (LLM seçer, kod     (Kişi 1-3,             her cümlede        sayılar/ref'ler  │
          doğrular; yedek:    pipeline.py)          [ref:id]           kontrol          └─► kaldı: düzeltme
          anahtar kelime)                                                                   talimatıyla en fazla
                                                                                            2 kez yeniden üret,
                                                                                            sonra şablon açıklama
```

| Dosya | Görevi |
| --- | --- |
| `kb.py` | `kb/` kartlarını okur; yer adı → bölge (81 il, 7 bölge), anahtar kelime eşleştirme |
| `plan.py` | Soru → plan (kart, belirti, şüpheliler, bölge, **gerekçe**) |
| `explain.py` | Sonuç → açıklama (LLM ya da şablon) + kanıt tablosu |
| `verify.py` | Metindeki sayılar sonuçta var mı, `[ref:id]`'ler gerçek mi, sayılı cümleler kaynaklı mı |
| `answer.py` | Hepsini bağlayan orkestratör |
| `client.py` | Anthropic ya da OpenAI uyumlu API istemcisi (anahtar yalnızca ortam değişkeninden) |

## Arayüzden kullanım (Kişi 5)

```python
from llm import answer, KnowledgeBase
from pipeline import run_analysis   # plan -> results.json sözlüğü (Kişi 1-3)

out = answer("Konya'da kuraklık artıyor mu?", run_analysis)
out["message"]       # doluysa kullanıcıya sor (bölge eksik/desteklenmiyor), analiz yapılmadı
out["plan"]["gerekce"]   # "neden bu değişkenlere baktık" — açıklanabilirliğin ilk adımı
out["explanation"]   # markdown; [ref:id] -> kanıt tablosundaki satır
out["evidence"]      # kanıt tablosu satırları (id, değişken, ürün, değer, aralık, p, etiket)
out["explainer"]     # "llm" ya da "sablon"; out["verified"] her zaman kontrol edilmiş durumdur
```

## LLM ayarı (ortam değişkenleri, repoya yazılmaz)

```bash
export LLM_PROVIDER=anthropic   # ya da openai (Groq, Gemini OpenAI-uyumlu uç, Ollama için LLM_BASE_URL)
export LLM_MODEL=<model adı>
export LLM_API_KEY=<anahtar>
```
Hiçbiri ayarlı değilse sistem LLM'siz çalışır: anahtar kelime planlayıcı + şablon açıklama.

## Bilgi tabanı (`kb/`)

- `kb/cards/*.yaml` — süreç kartları (konu, belirti, şüpheliler ve **neden** şüpheli oldukları, alternatifler)
- `kb/degiskenler.yaml` — değişkenlerin lise dilinde tanımı; adlar `docs/sozlesmeler.md` ile birebir aynı
- `kb/yerler.yaml` — 81 il → 7 bölge; bölge kimlikleri `data/regions.py` ile eşleşmeli
