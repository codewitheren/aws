# Transfer Kontrol Paneli

Transfer ekibinin iç aracı. Analist bir merkez depo ve transfer tipi seçer; sistem bugünün Forecast önerisini alır, kesim motorunu çalıştırır, ardından bir AI agent sonucu kontrol eder. Agent aykırı PL önerileri bulursa ne bulduğunu ve ne önerdiğini anlatır, onay ister. Arayüz transfer çıktısını, agent'ın bulgularını, açıklamalarını ve grafikleri gösterir.

**Temel kural:** Agent Forecast'a ya da başka hiçbir sisteme yazmaz. Onaylanan düzeltmeler yalnızca o optimizasyonun çıktısına uygulanır; kullanıcı dosyaları indirip kendisi uygular.

Optimizasyonlar yalnızca bugün için yapılır (tarih seçici yoktur).

## Ekranlar

| Adres | Ekran |
|---|---|
| `#/kosu` | Optimizasyon başlatma: merkez, transfer tipi, Hesapla, optimizasyon durumu ve agent onayları |
| `#/sonuclar` | Sonuç özeti (göstergeler, uyarılar, dosyalar, "Agent'a sor") |
| `#/sonuclar/anomaliler` | Forecast anomalileri |
| `#/trend` | Kısma trendi (30 gün) |
| `#/depolar` | Doluluk–kısma dağılımı, depo listesi, Kavacık özeti |
| `#/depolar/:id` | Depo detayı (örnek veride `goztepe` ve `kavacik`; diğerleri için "detay verisi yok") |

Boş adres `#/kosu`'ya yönlenir. Hash yönlendirme sayesinde S3 + CloudFront'ta yeniden yazma kuralı gerekmez ve uygulama bir alt klasörden de çalışır.

## Yerel geliştirme

Gereksinim: Node.js 18+.

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # tsc --noEmit + vite build → dist/
npm run preview    # dist/ klasörünü yerelde sunar
```

## Ortam değişkenleri

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `VITE_AGENT_MODE` | `mock` | `mock`: tarayıcı içi örnek agent ve örnek veri. `agentcore`: Cognito girişi + AgentCore Runtime (canlı). |

Canlı mod `/config.json` (`region`, `clientId`, `runtimeArn`) dosyasını okur ve `/runtimes/<arn>/invocations` yoluna gider; ikisini de `scripts/deploy.py publish` hazırlar. Dağıtım için elle `aws s3 sync` gerekmez.

## Mimari

```
src/
  agent/            Agent sözleşmesi ve istemcileri
    types.ts        AgentEvent (RunEvent | ChatEvent) ve komutlar — tek sözleşme
    client.ts       AgentClient arayüzü (startRun / respondToApproval / ask)
    mockClient.ts   Tasarımdaki akışı zamanlayıcılarla canlandıran mock agent
    mockInstruction.ts  Mock agent'ın serbest metin talimatı yorumu
    mockChat.ts     "Agent'a sor" için hazır yanıtlar
    agentcore.ts    Canlı istemci: Cognito girişi, AgentCore çağrısı, onaylar, optimizasyon geri yükleme
    sse.ts          fetch gövdesinden SSE ayrıştırıcı (POST destekler)
    index.ts        VITE_AGENT_MODE'a göre istemci seçimi
  run/              Optimizasyon durumu: tek doğruluk kaynağı
    reducer.ts      AgentEvent'leri tüketen reducer (optimizasyon, onaylar, sohbet)
    RunProvider.tsx React context + eylemler
    selectors.ts    Bulgu durumu, düzeltme sayıları
    depotOutcome.ts Karar → depo rakamları (öneri, kesim, gönderilen)
  data/             Ekran verisi
    types.ts        Veri tipleri
    live.ts         Canlı optimizasyon verisini ekran tiplerine çevirir
    sample.ts       Örnek veri (sabit rakamlar + tohumlu örnek seriler)
    api.ts          Async veri katmanı (backend'e geçişte değişecek tek dosya) + .xlsx isteği
    exports.ts      İstemci tarafında üretilen CSV'ler
  charts/           Elle yazılmış SVG/HTML grafikler (kütüphane yok)
  components/       Küçük arayüz bileşenleri
  pages/            Ekranlar
  router/           Küçük hash yönlendirici
  theme/            Açık/koyu tema (prefers-color-scheme + localStorage)
  lib/              Biçimlendirme (tr-TR), tohumlu RNG, indirme, yardımcılar
  styles.css        Tasarım belirteçleri ve sınıflar
```

Akış: `RunProvider` bir `AgentClient` alır → `startRun` olayları reducer'a aktarılır → tüm ekranlar aynı durumu okur. Optimizasyon sırasında verilen kararlar Sonuçlar özetinde (düzeltme sayısı), anomali CSV'sinde (optimizasyon durumu sütunu) ve Göztepe detayında (öneri kartı, kesim şelalesi, açıklama) görünür. Optimizasyon yapılmadan da sonuç ekranları örnek veriyle açılır.

Mock agent bulguları yalnızca örnek kombinasyon **Maltepe · Ambient & Su** için üretir. Başka bir merkez/tip çalıştırılırsa akış tamamlanır ama aykırı öneri sorulmaz ve sonuç ekranları bunun örnek veri olduğunu açıkça söyler.

### Mock agent'ta serbest metin talimatı

- Bir sayı (ör. "20 ile sınırla") → değer o sayıyla sınırlanır; sayı mevcut değerden küçük değilse değişiklik yapılmaz.
- "ortalama" → G10 ortalamasına çekilir; "medyan" → medyana çekilir.
- Diğer her şey → not olarak kaydedilir, öneri değiştirilmez (ret gibi işlenir) ve not ekranda gösterilir.

Son bulgu yanıtlanınca optimizasyon kendiliğinden devam eder.

## Canlı mod: AgentCore bağlantısı

`src/agent/agentcore.ts` backend'in (`agent/main.py`) eylemleriyle konuşur. Her çağrı `start` → `pending`… → `transfer` olaylarını akıtır. Optimizasyon kimliği Runtime oturum UUID'sidir.

| Arayüz adımı | Backend eylemi |
|---|---|
| Hesapla | `prepare` (merkez, tip `amb`/`cold`/`ms`, İstanbul'a göre bugün) → girdiler + aykırı PL bulguları |
| Onay kartları | Tarayıcıda; kararlar `finish` çağrısına `changes` (satır → sipariş katına yuvarlanmış miktar) olarak gider |
| Kesim motoru | `finish` → özet, dosyalar S3'te |
| Sayfa yenileme | `status` ile bu sekmedeki son optimizasyon geri yüklenir |
| Sonuçlar, Trend, Depolar | `view` (depo tablosu, neden payları, öneri kontrol kartları, tam gönderim doluluğu) |
| Depo detayı | `depot` (motor kanıtı, neden kırılımı, en çok kesilen 10 ürün) |
| Dosyalar | `download` → 5 dakikalık imzalı bağlantı |
| Agent'a sor | `explain` (Strands agent, optimizasyon kanıtıyla) |

Canlı modda geçmiş optimizasyon arşivi olmadığı için 30 günlük trend, ısı haritası, "düne göre" farklar ve kaldıraç tablosu gösterilmez; ekran bunu açıkça yazar ve örnek rakam göstermez.

## Veri: verilen mi, örnek mi? (mock mod)

Mock modda tüm ekran verisi örnektir (Maltepe · Ambient & Su, 23.11.2026). İçinde iki tür rakam vardır:

**Tasarımda verilen sabit değerler** (`src/data/sample.ts`, aynen aktarıldı):
- Optimizasyon ekranı: merkezler, transfer tipleri, Forecast geliş saatleri, öneri satır sayıları, "bugün çalıştırıldı" saatleri.
- Agent bulguları: Göztepe Bulaşık süngeri 5'li 100 (ort. 14, medyan 16); Bostancı Kedi maması 400 g tahmin 86 (ort. 11, medyan 9); Acıbadem Pirinç 1 kg 120 (ort. 19, medyan 18).
- Sonuçlar: 52.872 önerilen / 29.688 gönderilen satır, C/P %56,2, kısma %44,2 (+1,8 / +3,1 puan), satır limiti 9.412 / 10.000, 5 uyarının metni ve kanıtları, 2.032 anomali (682 / 942 / 408).
- Anomali tablosu: SuadiyeBüyük 448, Kozyatağı 212, Moda 196; medyan 68, üst sınır 170.
- Trend: bugünkü %44,2, belirli günlerin değerleri (%49,3, %33,8, %51,6, %42,4), normal bant %36–46, en çok kısılan 15 depo ve oranları, merkez × tip satır limiti kullanımları, Göztepe %93 ve Kavacık %73.
- Depolar: Göztepe (%84,6 dolu, %93 kısma), Kavacık (%144 dolu, %73 kısma), depo listesi.
- Göztepe detayı: öneri 25.605, palet limiti 21.328, su alanı 2.472, gönderilen 1.805, 41,8 palet, TIR limiti 4 / G10 medyanı 12 palet, doluluk %28,6 / %84,6, A sınıfı 6.620, en çok kesilen 6 ürün, kaldıraçlar tablosu.
- Kavacık detayı: öneri 15.753; hacim 9.089, su alanı 1.636, palet limiti 838; gönderilen 4.190; ortalama doluluk %128, tam gönderimde %144, buffer 1,10, ETB %124, +4 Other %78, +4 MS %41, son 24 sipariş gününün 24'ünde hacim kısması. Kavacık için trend, ürün listesi, TIR ve A sınıfı verisi olmadığından bu bölümler gösterilmez.

**Yalnızca görsel örnek (tohumlu sözde rastgele, `rng(seed)`):**
- Anomali grafiğindeki 70 "sınır içinde" depo noktası (tohum 448).
- Trend: 30 günlük merkez kısma serisinin sabitlenmemiş günleri, günlük kesinti nedeni payları, depo × gün ısı haritası hücreleri (tohum 2311).
- Depolar dağılım grafiğindeki adsız noktalar (tohum 513).
- Göztepe 30 günlük kısma trendi ve merkez ortalaması çizgisi (tohum 93).

**Uygulamanın hesapladıkları:** optimizasyon kararlarına göre Göztepe'nin düzeltilmiş önerisi ve palet limiti kesimi (ör. medyan kabulünde 25.521 / 21.244; gönderilen 1.805 değişmez), düzeltme sayıları, CSV içerikleri.

**Not:** Verilen kısma oranı (%44,2) satır sayılarından hesaplanan değerle (1 − 29.688 / 52.872 ≈ %43,8) birebir tutmuyor; muhtemelen miktar bazlı. Tasarımdaki değer olduğu gibi gösteriliyor.

**İndirilen dosyalar:** Anomali CSV'si yalnızca örnek verideki satırları içerir (3 aykırı depo + agent'ın 3 bulgusu ve optimizasyon durumu), 2.032 satırın tamamını değil; düğme etiketi bunu belirtir. Uyarı CSV'si 5 uyarının tamamını içerir. CSV'ler `;` ayırıcılı, UTF-8 BOM'lu (Türkçe Excel için).

## Erişilebilirlik ve tema

- Açık/koyu tema: varsayılan `prefers-color-scheme`; kenar çubuğundaki düğmeyle değiştirilir ve `localStorage`'da saklanır (erişilemezse oturum içinde çalışır).
- Optimizasyon durumu `aria-live` ile duyurulur; yeni agent önerisinde odak önerinin başlığına taşınır; rota değişiminde odak sayfa başlığına gider.
- Grafiklerin metin karşılıkları (`aria-label`) ve her işarette araç ipucu (`<title>`) vardır; uyarı seviyeleri renk + metin + farklı işaret şekliyle gösterilir.
- Tablolar ve geniş grafikler dar ekranda kendi kutularında kayar; sayfa 390 px genişlikte yatay kaymaz.
