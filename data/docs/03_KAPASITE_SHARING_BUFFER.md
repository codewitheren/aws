# Capacity Management — Sharing ve Buffer (Cold)

Agent her hafta cep depo bazında soğuk dolapların doluluğuna ve kapasite yüzünden kesilen miktara bakar; iki kaldıraçla öneri verir: **sharing payları** (paylaşılan dolabın gruplar arasında bölünmesi) ve **buffer** (dolabın planlamada ne kadar aşılabileceği). İkisi de yetmiyorsa **ek dolap** ihtiyacını litre olarak çıkarır.

## Kavramlar

**Kapasite (L) = havuz (dolap litresi) × sharing payı × buffer**

- **Havuz:** depodaki dolabın litresi (+4 odası, ETB odası, 8-12 dolabı).
- **Sharing payı:** paylaşılan odada grubun payı. Kaynak: "Cold sharing Hackathon" sheet'i (canlıda oran sheet'i, gid 2106866758).
- **Buffer:** dolabın planlamada aşılabilme oranı (%100, %105, %110). Gün içinde satış olduğu için teslimat anında dolabın biraz üstünde planlamak mümkündür. Kaynak: "Buffer Rates Hackathon" sheet'i, kolonlar `Ambient Buffer` ve ` Cold Limit` (başında boşluk var). Sheet'te olmayan depo varsayılanı alır: Ambient 1,10, Cold 1,10.
- **İhtiyaç (L)** = teslimatta dolu hacim + Relex öneri hacmi = kesinti olmasaydı teslimat sonrası dolu hacim.
- **Doluluk** = ortalama ihtiyaç / ortalama kapasite. > %100 = dolu.
- **Kapasite kısması** = yalnız dolap kapasitesi nedenli kesilen litre / öneri litre. Backlog, merkez satır limiti, kara liste dahil değil.

## Paylaşılan dolaplar

| Oda | Paylar | Kural (G10) | Okuyan motor |
|---|---|---|---|
| +4 odası | `Other+4`, `MS+4` | toplam = 1 | Cold (Other), MS (+4) |
| ETB odası | `Taze Et`, `Şarküteri ve Merkezden Giden ETB` | toplam = 1 | ETB motoru (Taze Et), Cold (ETB) |
| 8-12 | `MS+8+12` | hep 1 | MS |

- **GB depolar tek havuzdur:** dört kalemin toplamı ≈ 1. G10 kuralı uygulanmaz. İlk sürümde kapsam dışı bırakılabilir.
- **Depo tipini addan çıkarmayın:** Büyükbakkalköy ve Büyükçekmece G10'dur; GaziemirBüyük ve SuadiyeBüyük GB ama G10 gibi iki odalıdır. `Domain Type` kullanın.
- Taze Et tarafının doluluğu ETB direkt sevk verisindedir (bu klasörde yok). ETB odası için öneri şimdilik yalnız merkezden giden ETB tarafının doluluğuna göre verilebilir; Cold parquet'inde `ETB_Kesintisiz_Gelecek_Doluluk (%)` var.

## Karar kuralları

**Sharing (ekip kararları):**

1. Bir grup dolu (> %100), diğeri hedefin altında → **kaydır**. Hedef (%100 veya %90) yalnız payı azaltılan tarafa uygulanır: yeni pay = gereken pay / hedef, 0,01'e yukarı yuvarlanır. Gereken pay = ortalama ihtiyaç / (havuz × buffer). Kalan pay dolu tarafa verilir; toplam korunur.
2. İkisi de dolu → **dolap gerekli** (ek hacim litre olarak).
3. İkisi de boş → işlem yok.
4. **MS haftalık dalgalı:** Cuma ≈ ortalamanın 1,3 katı, Cmt 1,15, Pzt 0,85. MS'ten pay alırken MS'in en yoğun gününe göre bakılır; aksi halde Cuma'ları MS kısılır.
5. Hiçbir kategoriye öncelik yok. Net etki = iki grubun toplam kapasite kısması (L/gün).

**Buffer (yeni kaldıraç):**

- **Artır** (ör. %100 → %105 → %110): depo kronik olarak kapasiteden kısılıyor, buffer %110'un altında, sharing kaydırması tek başına yetmiyor ve fiziksel doluluk buna izin veriyor (gerçek doluluk sürekli %100'ün üstünde değil, operasyonda taşma şikâyeti yok).
- **Düşür:** buffer yüksek ama gerçek doluluk sürekli %100'ün üstünde ya da soğukta bozulma / waste artıyor.
- Adımlar 5 puan; tek seferde bir adım.
- Ambient için aynı mantık `Ambient Buffer` ile geçerli (Ambient parquet'inde uygulanan değer `Hard_Stop_Orani`, gerçek doluluk `Total Ambient Ratio (In Transit Included)`).

**Kaldıraç sırası:** önce sharing (fiziksel risk yok), sonra buffer, en son ek dolap.

## Simülasyon (beklenen etki)

Her gün için yeni kapasite = havuz × yeni pay × yeni buffer; simüle kısılan = min(max(ihtiyaç − kapasite, 0), öneri). Çıktı: iki grubun doluluk ve kısma %'si önce / sonra, toplam kapasite kısması L/gün önce / sonra, "şu kadar fazla ürün giderdi". Doğrulama: mevcut paylarla simülasyon gerçeğe yakın (MS %5,9 sim / %5,2 gerçek; Other %15,7 / %14,2). Batch, satır limiti ve backlog modelde yok; yön ve büyüklük için okunur.

## Örnek: Göztepe (16.10–15.11 ortalaması)

| Adım | Pay Other / MS | Buffer | Other doluluk |
|---|---|---|---|
| Mevcut | 0,77 / 0,23 | 1,00 | %117 (MS %60) |
| Sharing: MS → Other (%90 hedef) | 0,84 / 0,16 | 1,00 | %107 |
| + Buffer %110 | 0,84 / 0,16 | 1,10 | %97 |

Agent'tan beklenen cevap: "Sharing tek başına yetmiyor; Göztepe'nin Cold Limit'i %100 (depoların çoğu %110). İkisi birlikte Other'ı %97'ye indiriyor. MS en yoğun gününde (Cuma) kontrol edilmeli." Aynı dönemde Ayrancı (%125, buffer 1,00) ve Küçükçekmece (%106, buffer 1,00) benzer adaylar.

## Veri (`data/sharing/`)

| Dosya | İçerik |
|---|---|
| `sharing_gunluk_01.10-15.11.parquet` | G10 depo × grup (Other, MS +4) × gün: `Havuz`, `Oran` (uygulanan pay), `Buffer`, `Kapasite`, `Dolu`, `Oneri` (L), `Final`, `Ihtiyac`, `Oneri_L`, `KapKes_L` (kapasite nedenli kesilen L), `KisGun`, `HaftaGunu`, `Merkez`. 41 gün, 295 depo. `Veri_Sorunlu_Gun = True` olan 4 günü (19, 21, 22, 25.10) analize katmayın. 06.11–15.11 arasında 09.11 yok. |
| `oran_sheet_snapshot_16.11.csv` | Oran sheet'inin 16.11 hali |
| `oran_sheet_09.11_degisiklik_oncesi.csv` | 10.11 değişikliğinden önceki hali |
| `sharing_degisiklik_kaydi.csv` | 10.11'de uygulanan 7 depo değişikliği: eski / yeni pay, analizin tahmini (takip senaryosu için) |

Daha güncel veri gerekirse Cold ve MS merkez parquet'lerinden günlük olarak hesaplanabilir: Cold'da `Kapasite_Ham_Litre`, `Uygulanan_Oran`, `Uygulanan_Buffer`, `Kapasite_Litre`, `Anlik_Stok_Litre`, `Satir_Onerilen_Hacim`, kısma nedeni `Kapasite Zorlamasi (Other/ETB Limiti) - Kisildi`; MS'te `Allowed_Space`, `Son_Doluluk_Pct`, `Vol_Per_Unit`, kısma nedeni `Dolap Kapasite Yetersizligi …`, `Kapasite Yok (0)`.

## Referans rakamlar (doğrulama için)

01.10–05.11, 287 G10 depo, %100 hedef: 47 depoda MS → Other kaydırma, 10 depoda Other → MS, 9 depoda dolap gerekli, 220 depoda işlem yok. MS → Other kaydırmalarında toplam kapasite kısması 9.301 → 7.528 L/gün.

## Agent çıktısı

- Depo bazlı tablo: mevcut paylar ve buffer, doluluk (iki grup), karar (kaydır / buffer / dolap / işlem yok), önerilen paylar ve buffer, beklenen etki (L/gün).
- Oran sheet'ine ve Buffer Rates sheet'ine girilecek formatta iki ayrı liste.
- Dolap gereken depolar ve ek hacim ihtiyacı (L).
- Takip: uygulanan değişikliklerde tahmin vs gerçekleşen (en az 2 tam hafta sonra).
