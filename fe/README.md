# Transfer Kontrol Paneli

Transfer ekibinin iç aracı. Analist bir merkez depo ve transfer tipi seçer; sistem bugünün Relex önerisini alır, kesim motorunu çalıştırır, ardından bir AI agent sonucu kontrol eder. Agent aykırı PL önerileri bulursa ne bulduğunu ve ne önerdiğini anlatır, onay ister. Arayüz transfer çıktısını, agent'ın bulgularını, açıklamalarını ve grafikleri gösterir.

**Temel kural:** Agent Relex'e ya da başka hiçbir sisteme yazmaz. Onaylanan düzeltmeler yalnızca o koşunun çıktısına uygulanır; kullanıcı dosyaları indirip kendisi uygular.

Koşular yalnızca bugün için yapılır (tarih seçici yoktur).

## Ekranlar

| Adres | Ekran |
|---|---|
| `#/kosu` | Koşu başlatma: merkez, transfer tipi, Hesapla, koşu durumu ve agent onayları |
| `#/sonuclar` | Sonuç özeti (göstergeler, uyarılar, dosyalar, "Agent'a sor") |
| `#/sonuclar/anomaliler` | Relex anomalileri |
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

Derleme zamanında okunur (Vite, `.env` / `.env.production` ya da komut satırı):

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `VITE_AGENT_MODE` | `mock` | `mock`: tarayıcı içinde zamanlayıcılarla çalışan örnek agent. `http`: gerçek agent backend'i. |
| `VITE_API_BASE_URL` | `/api` | Agent backend'inin kökü. Aynı CloudFront dağıtımında `/api` olması amaçlanır. |

Örnek: `VITE_AGENT_MODE=http VITE_API_BASE_URL=/api npm run build`

## S3 + CloudFront'a dağıtım

`dist/` statik bir sitedir. `vite.config.ts` içinde `base: './'` olduğu için bucket kökünde de bir alt klasörde de çalışır.

```bash
npm run build

# 1) Hash'li varlıklar: uzun ömürlü, değişmez
aws s3 sync dist/assets s3://BUCKET/PREFIX/assets \
  --cache-control "public, max-age=31536000, immutable" --delete

# 2) index.html: her seferinde doğrulansın
aws s3 cp dist/index.html s3://BUCKET/PREFIX/index.html \
  --cache-control "no-cache" --content-type "text/html; charset=utf-8"

# 3) Yalnızca index.html'i geçersiz kıl (varlık adları her derlemede değişir)
aws cloudfront create-invalidation --distribution-id DISTRIBUTION_ID --paths "/PREFIX/index.html"
```

(`PREFIX` kökse `/index.html`.) Eski varlıkları hemen silmek yerine bir süre tutmak isterseniz 1. adımda `--delete` kullanmayın; açık sekmeler eski `index.html` ile eski varlıkları istemeye devam edebilir.

- **SPA yeniden yazma kuralı gerekmez.** Tüm rotalar `#/...` biçimindedir; sunucuya her zaman `index.html` istenir. 403/404 → `index.html` hata sayfası tanımlamaya gerek yoktur.
- Bucket'ı herkese açmayın; CloudFront Origin Access Control (OAC) ile okuyun. `Default root object`: `index.html`.
- **Agent backend'i için ikinci origin:** CloudFront'a backend'i (ALB, API Gateway vb.) ikinci origin olarak ekleyin ve `/api/*` için bir cache behavior tanımlayın:
  - Origin: agent backend'i, Viewer protocol: HTTPS only
  - Allowed methods: `GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE`
  - Cache policy: `CachingDisabled`; Origin request policy: `AllViewerExceptHostHeader` (ya da gereken başlıklar/çerezler)
  - SSE akışları için origin tarafında yanıt arabelleğe alınmamalı ve keep-alive yorumları (`: ping`) gönderilmeli; CloudFront origin response/keep-alive zaman aşımlarını uzun süren koşulara göre ayarlayın.
  - Aynı alan adından sunulduğu için CORS gerekmez. Kimlik doğrulama (ör. şirket SSO'su) bu projede yoktur ve dağıtım katmanında ele alınmalıdır.

## Mimari

```
src/
  agent/            Agent sözleşmesi ve istemcileri
    types.ts        AgentEvent (RunEvent | ChatEvent) ve komutlar — tek sözleşme
    client.ts       AgentClient arayüzü (startRun / respondToApproval / ask)
    mockClient.ts   Tasarımdaki akışı zamanlayıcılarla canlandıran mock agent
    mockInstruction.ts  Mock agent'ın serbest metin talimatı yorumu
    mockChat.ts     "Agent'a sor" için hazır yanıtlar
    httpClient.ts   Gerçek backend iskeleti (fetch + SSE) — test EDİLMEDİ
    sse.ts          fetch gövdesinden SSE ayrıştırıcı (POST destekler)
    index.ts        VITE_AGENT_MODE'a göre istemci seçimi
  run/              Koşu durumu: tek doğruluk kaynağı
    reducer.ts      AgentEvent'leri tüketen reducer (koşu, onaylar, sohbet)
    RunProvider.tsx React context + eylemler
    selectors.ts    Bulgu durumu, düzeltme sayıları
    depotOutcome.ts Karar → depo rakamları (öneri, kesim, gönderilen)
  data/             Ekran verisi
    types.ts        Veri tipleri
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

Akış: `RunProvider` bir `AgentClient` alır → `startRun` olayları reducer'a aktarılır → tüm ekranlar aynı durumu okur. Koşu sırasında verilen kararlar Sonuçlar özetinde (düzeltme sayısı), anomali CSV'sinde (koşu durumu sütunu) ve Göztepe detayında (öneri kartı, kesim şelalesi, açıklama) görünür. Koşu yapılmadan da sonuç ekranları örnek veriyle açılır.

Mock agent bulguları yalnızca örnek kombinasyon **Maltepe · Ambient & Su** için üretir. Başka bir merkez/tip koşulursa akış tamamlanır ama aykırı öneri sorulmaz ve sonuç ekranları bunun örnek veri olduğunu açıkça söyler.

### Mock agent'ta serbest metin talimatı

- Bir sayı (ör. "20 ile sınırla") → değer o sayıyla sınırlanır; sayı mevcut değerden küçük değilse değişiklik yapılmaz.
- "ortalama" → G10 ortalamasına çekilir; "medyan" → medyana çekilir.
- Diğer her şey → not olarak kaydedilir, öneri değiştirilmez (ret gibi işlenir) ve not ekranda gösterilir.

Son bulgu yanıtlanınca koşu kendiliğinden devam eder.

## Agent protokolü (backend sözleşmesi)

Tüm yollar `VITE_API_BASE_URL` altındadır. Akış yanıtları `Content-Type: text/event-stream`; her olay tek bir `data:` satırında JSON'dur (`event:`/`id:` yok sayılır, `:` ile başlayan satırlar keep-alive yorumudur).

### `POST /runs` — koşu başlat (SSE akışı döner)

İstek:
```json
{ "type": "start_run", "merkez": "Maltepe", "transferType": "amb" }
```
`transferType`: `amb` | `c4` | `ms`.

Yanıt akışındaki olaylar (`runId` her olayda bulunur):
```json
{ "type": "run_started", "run": { "runId": "r-123", "merkez": "Maltepe", "transferType": "amb", "transferTypeLabel": "Ambient & Su", "runDate": "2026-11-25" } }
{ "type": "step_started",   "runId": "r-123", "step": "relex_read" }
{ "type": "step_completed", "runId": "r-123", "step": "relex_read", "detail": "52.872 öneri satırı okundu" }
{ "type": "step_progress",  "runId": "r-123", "step": "outlier_review", "detail": "3 aykırı öneri buldum. Onayınız bekleniyor" }
{ "type": "approval_requested", "runId": "r-123", "approval": {
    "approvalId": "a-1", "index": 1, "total": 3,
    "findingKey": "goztepe:bulasik-sungeri-5li", "depotId": "goztepe",
    "title": "Göztepe · Bulaşık süngeri 5'li",
    "found": "Relex bu ürün için Göztepe'ye 100 adet öneriyor. …",
    "proposal": "Öneriyi G10 medyanına çekmek: 100 → 16 (−84 adet).",
    "howApplied": "Yalnızca bu koşuda, kesim motorundan önce. Relex kaydı değişmez; …",
    "impact": "Göztepe toplam önerisi 25.605 → 25.521 adet.",
    "question": "Medyana (16) çekeyim mi?",
    "metric": "oneri", "currentValue": 100, "proposedValue": 16,
    "reference": { "group": "G10", "mean": 14, "median": 16 },
    "options": [
      { "id": "accept", "label": "Evet, medyana çek (16)" },
      { "id": "accept_all_remaining", "label": "Evet, kalan 2 bulguyu da sormadan medyana çek" },
      { "id": "reject", "label": "Hayır, olduğu gibi bırak (100)" }
    ],
    "instruction": { "allowed": true, "placeholder": "ör. ortalamaya çek, 20 ile sınırla" } } }
{ "type": "approval_resolved", "runId": "r-123", "resolution": {
    "approvalId": "a-1", "findingKey": "goztepe:bulasik-sungeri-5li", "title": "Göztepe · Bulaşık süngeri 5'li",
    "originalValue": 100, "outcome": { "kind": "applied", "value": 16, "method": "median" },
    "summary": "Medyana çekildi (100 → 16)", "decidedBy": "user" } }
{ "type": "check_progress", "runId": "r-123", "check": "run_integrity", "status": "running" }
{ "type": "check_progress", "runId": "r-123", "check": "run_integrity", "status": "done" }
{ "type": "run_completed", "runId": "r-123", "summary": {
    "headline": "Koşu hazır. 1 kritik, 3 uyarı var.",
    "counts": { "kritik": 1, "uyari": 3, "bilgi": 1 },
    "corrections": { "applied": 2, "unchanged": 1 },
    "finishedAt": "2026-11-25T07:12:00Z", "resultsAvailable": true } }
{ "type": "run_failed", "runId": "r-123", "error": { "code": "relex_input_missing", "message": "…" } }
```
- `step`: `relex_read` → `outlier_review` → `cutting_engine` → `agent_checks` → `ready`
- `check`: `run_integrity` (Koşu bütünlüğü), `faulty_output` (Hatalı çıktı), `relex_anomalies` (Relex anomalileri), `depot_cuts` (Depo kısmaları)
- `outcome`: `{ "kind": "applied", "value": n, "method": "median" | "mean" | "instruction" }` ya da `{ "kind": "unchanged", "reason": "rejected" | "instruction_note" | "instruction_not_lower" }`; serbest metin `note` alanında döner.
- Arayüz seçenek düğmelerini `options` listesinden çizer; metinler backend'den gelir.

### `POST /runs/{runId}/approvals/{approvalId}` — onaya yanıt

```json
{ "response": { "kind": "accept" } }
{ "response": { "kind": "reject" } }
{ "response": { "kind": "accept_all_remaining" } }
{ "response": { "kind": "instruction", "text": "20 ile sınırla" } }
```
2xx dönmesi yeterlidir; sonuç koşu akışında `approval_resolved` (ve gerekiyorsa sonraki `approval_requested`) olarak gelir. `accept_all_remaining` için kalan her bulgu için ayrı `approval_resolved` gönderilmelidir.

### `POST /chat` — "Agent'a sor" (SSE akışı döner)

İstek: `{ "question": "Göztepe'de neden bu kadar kıstık?", "runId": "r-123" }` (`runId` null olabilir)

```json
{ "type": "chat_message_started", "messageId": "m-1" }
{ "type": "chat_delta", "messageId": "m-1", "delta": "**Kısıt dolap değil, TIR limiti.**\n\n" }
{ "type": "chat_message_completed", "messageId": "m-1", "links": [ { "label": "Göztepe detayını aç", "route": "/depolar/goztepe" } ] }
{ "type": "chat_failed", "messageId": "m-1", "error": { "code": "…", "message": "…" } }
```
Metinde boş satır paragraf ayırır, `**…**` kalın yazılır; HTML yorumlanmaz. `route` uygulama içi yoldur.

### `GET /runs/{runId}/files/transfer-output.xlsx`

Transfer çıktısı. İstemci tarafında sahte tablo üretilmez; mock modda düğme bunun backend'den geleceğini söyleyen bir mesaj gösterir.

### HTTP istemcisinin durumu

`src/agent/httpClient.ts` tür denetiminden geçer ve SSE ayrıştırıcısı küçük bir yerel testle denenmiştir, ancak **gerçek bir backend'e karşı hiç çalıştırılmamıştır**. Bilinen eksikler: yeniden bağlanma/`Last-Event-ID` yok, olaylar yalnızca `type` alanına göre doğrulanır (tam şema doğrulaması yok), kimlik doğrulama başlığı yok. Ekran verisi (sonuçlar, trend, depolar) her iki modda da `src/data/sample.ts`'ten gelir; backend uç noktaları belli olunca `src/data/api.ts` değiştirilmelidir.

## Veri: verilen mi, örnek mi?

Tüm ekran verisi bugün örnektir (Maltepe · Ambient & Su, 23.11.2026). İçinde iki tür rakam vardır:

**Tasarımda verilen sabit değerler** (`src/data/sample.ts`, aynen aktarıldı):
- Koşu ekranı: merkezler, transfer tipleri, Relex geliş saatleri, öneri satır sayıları, "bugün koşuldu" saatleri.
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

**Uygulamanın hesapladıkları:** koşu kararlarına göre Göztepe'nin düzeltilmiş önerisi ve palet limiti kesimi (ör. medyan kabulünde 25.521 / 21.244; gönderilen 1.805 değişmez), düzeltme sayıları, CSV içerikleri.

**Not:** Verilen kısma oranı (%44,2) satır sayılarından hesaplanan değerle (1 − 29.688 / 52.872 ≈ %43,8) birebir tutmuyor; muhtemelen miktar bazlı. Tasarımdaki değer olduğu gibi gösteriliyor.

**İndirilen dosyalar:** Anomali CSV'si yalnızca örnek verideki satırları içerir (3 aykırı depo + agent'ın 3 bulgusu ve koşu durumu), 2.032 satırın tamamını değil; düğme etiketi bunu belirtir. Uyarı CSV'si 5 uyarının tamamını içerir. CSV'ler `;` ayırıcılı, UTF-8 BOM'lu (Türkçe Excel için).

## Erişilebilirlik ve tema

- Açık/koyu tema: varsayılan `prefers-color-scheme`; kenar çubuğundaki düğmeyle değiştirilir ve `localStorage`'da saklanır (erişilemezse oturum içinde çalışır).
- Koşu durumu `aria-live` ile duyurulur; yeni agent önerisinde odak önerinin başlığına taşınır; rota değişiminde odak sayfa başlığına gider.
- Grafiklerin metin karşılıkları (`aria-label`) ve her işarette araç ipucu (`<title>`) vardır; uyarı seviyeleri renk + metin + farklı işaret şekliyle gösterilir.
- Tablolar ve geniş grafikler dar ekranda kendi kutularında kayar; sayfa 390 px genişlikte yatay kaymaz.
