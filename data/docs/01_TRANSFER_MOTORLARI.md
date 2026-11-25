# Transfer Kesim Motorları

Üç motor Relex'in sipariş önerisini alır ve cep deponun kapasitesine ve merkezin limitlerine göre keser. Agent kesimi kendi hesaplamaz; motorları koşturur (ya da hazır çıktıyı alır), çıktıyı okur ve yorumlar. Bu doküman çıktıyı doğru okumak için gereken mantığı anlatır.

| Motor | Kod | Kategori | Ana dolap / kısıt |
|---|---|---|---|
| Ambient & Su | `Ambient_Su.py` | Kuru gıda, içecek, su | Ambient dolap hacmi, TIR palet limiti, su palet alanı |
| +4 (Cold) | `Cold.py` | Soğuk zincir (şarküteri, süt vb.) | +4 dolabındaki ETB ve Other payları |
| MS | `MS.py` | Meyve sebze | +4 ve 8-12 dolapları, dökme (kasa) dağıtımı |

Kod dosyaları canlıdakiyle aynıdır (23.11.2026). Çalıştırmak için `kod/` klasöründeki çalıştırıcıyı kullanın: girdileri gsheet'ten alır, Drive'a yazmaz (bkz. `05_KOD_VE_CALISTIRMA.md`).

## Ortak mantık

**Girdi:** Relex önerisi (depo × ürün), cep depo stok ve doluluk bilgisi, sheet'lerden parametreler (buffer, sharing payları, TIR limiti, sayım günleri, kampanya listesi).

**Kesim kuralı:**

1. Her satıra bir **öncelik puanı** (`Cut_Priority`) verilir.
2. Bir kısıt aşıldığında puanı en düşük satır önce kesilir; aynı puanda **cover'ı en yüksek** olan.
3. Her seferinde bir **sipariş katı** (`Order batch size`) kadar kesilir, ardından cover yeniden hesaplanır.
4. Kısıtlar bittikten sonra boşalan kapasiteye kesilenler geri eklenir.

**Cover (gün)** = (stok + açık sipariş) / günlük satış tahmini (`Daily FC`). Tahmin 0 ise cover sonsuz sayılır ve önce kesilir.

**Öncelik puanları (yüksek = korunur):**

| Puan | Anlam |
|---|---|
| 101 | Demirbaş (poşet vb.) — hiç kesilmez. Tek istisna: sayım günü depo tamamen kapalı |
| 100 | Dokunulmaz: Kampanya (sheet, T / T-1 listesi) ve Waste (elle liste). Kesilebilir ama en son |
| 99 | Listed segment, ya da Supply Shortage + düşük stok + bulunurluk < %60. Cold'da Pick-to-zero da |
| 98 / 85 | A sınıfı, cover eşiğinin altı / üstü |
| 97 / 84 | B sınıfı, cover eşiğinin altı / üstü |
| 83 | Düşük stok (G10 < 3, GB < 7) |
| 81 | C sınıfı ve cover eşiğinin altı |
| 1–19 | Açık satın alma siparişi olanlar ve yüksek cover'lılar (ilk kesilenler) |

Özel depo listeleri: "Sadece A testi" (Atakent) depolarında A dışı her şey sıfırlanır. "Weighted ava" listesindeki 19 depoda 99 puanı verilmez.

**Depo tipleri:** G10 (küçük) ve GB (büyük, "Büyük" ile biten ama ada güvenmeyin; `Domain Type` kolonunu kullanın). Eşikler tipe göre ayrıdır.

## Ambient & Su

Kısıt sırası:

1. **Sayım:** sayım günü depoya hiçbir şey gitmez.
2. **Dikey palet yerleşimi** (test depolarında su için).
3. **Dolap hacmi:** öneri hacmi dolap × buffer'ı aşarsa kesilir. Buffer depo bazlı, "Buffer Rates" sheet'indeki `Ambient Buffer` (yoksa 1,10).
4. **Su palet alanı.**
5. **TIR palet limiti:** depoya bir tırla gidebilecek palet (`Tir_Limiti`; sheet'ten, yoksa G10 12 / GB 25). Etkili backlog bu limitten düşülür. Önce ambient, sonra su kesilir.
6. **Merkez satır limiti:** 10.000 satır.
7. **Merkez koli limiti.**
8. **Geri ekleme**, sonra **merkez su stoğu** kontrolü.

**Palet:** ambient adet / (`SON_calculated` × 50), su adet / `palet`.

**Etkili backlog:** depoda henüz indirilmemiş palet; teslimat programına göre bugünkü TIR limitinden düşülür. Satırın backlog yüzünden kesilen kısmı `Backlog_Kesilen_Miktar` kolonundadır.

`Kesinti_Nedeni` değerleri: `Islem Gormedi` · `Sayım` · `Kapasite Zorlamasi (110% Limit) - Hacim Icin Kisildi` (yüzde depo buffer'ına göre 100/105/110) · `Su Depo Kapasitesi (<n> Palet) Asildi` · `G10 Palet Limiti Asildi` / `GB Palet Limiti Asildi` · `Merkez Depo Satir Limiti Asildi` · `Merkez Koli Limiti Asildi` · `Merkez Depo Su Stogu (End Balance DC) Asildi` · `Dikey Elleçleme - …`.

## +4 (Cold)

Dolap iki gruba ayrılır: **ETB** (şarküteri, merkezden giden et-tavuk) ve **Other** (diğer soğuk ürünler). G10'da +4 odası Other ve MS arasında, ETB odası Taze Et ve merkezden giden ETB arasında paylaşılır (bkz. `03_KAPASITE_SHARING_BUFFER.md`).

Kullanılabilir hacim = dolap × sharing payı × buffer − bugünkü stok − yoldaki + teslime kadar satılacak. Buffer = "Buffer Rates" sheet'indeki `Cold Limit`.

Kısıt sırası: **backlog** (G10 ≥ 1, GB > 2 palet → depo kapalı) → **sayım** → **havuz hacmi** (ETB / Other ayrı) → **merkez satır limiti** (6.900) → **hacim geri yükleme** → **depo adet limiti**.

`Kesinti_Nedeni`: `Islem Gormedi` · `Depo Backlog Blokaji` · `Sayım` · `Kapasite Zorlamasi (ETB Limiti) - Kisildi` · `Kapasite Zorlamasi (Other Limiti) - Kisildi` · `Merkez Depo Satir Limiti Asildi`.

## MS (meyve sebze)

Dolaplar: **+4** (Other ile paylaşılır) ve **8-12**. Ambient MS ürünleri dolap kısıtına girmez.

Özellikler:

- **Dökme (bulk) ürünler kasa ile gider; miktarlar kg'dır.** Kasa dağıtımı blokajlardan önce yapılır.
- **PTZ (Pick-to-zero):** merkezde stoğu sıfırlanacak ürünlerde kalan stok düşük cover'lı depolara dağıtılır.
- Kolon adları farklıdır: öneri `Effective quantity`, kasaya yuvarlanmış öneri `Effective_Units`, final `Final_Quantity`, neden `Trim_Reason`.

Kısıt sırası: sayım → dökme kasa dağıtımı → kapanan depolar (kara liste, backlog G10 > 0 / GB ≥ 5) → dolap hacmi (C → B → A) → geri yükleme → merkez satır limiti (10.000) → PTZ tamamlama → dökme telafi → depo adet limiti.

`Trim_Reason`: `Onaylandi (Kisma Yapilmadi)` · `Kara Liste` · `G10 Backlog Engeli` / `GB Backlog Engeli` · `Sayım` · `Dolap Kapasite Yetersizligi Sebebiyle Kisildi/Silindi` · `Kapasite Yok (0)` · `Merkez Depo 10000 Satır Limiti Sebebiyle Silindi` · `Onaylandi (Acilan Bosliga Geri Yuklendi)` · `Bosa Cikan Hacimle Kismen Geri Yuklendi` · `BULK …`.

Not: nedeni "Onaylandi" olup final ≠ öneri olan satırlar normaldir (kasa yuvarlaması, PTZ, telafi).

## Çıktılar

| Çıktı | Yol | İçerik |
|---|---|---|
| Merkez parquet'i | `Parquet Arşiv/<gg.aa>/<kategori>/<merkez>.parquet` | Motorun ana tablosunun tüm satır ve kolonları (Ambient ~134, +4 ~89, MS ~47 kolon) |
| Kategori Excel'i | `Replenishment/<gg.aa>/<kategori>/<merkez>.xlsx` | Ana sekme + özet sekmeleri (Depo Ozet Karnesi, Kapasite Detayi vb.) |
| All PL | `Parquet Arşiv/<gg.aa>/"<gün> <Ay> All PL.parquet"` | Günün tüm koşularının siparişli satırları, 25 sabit kolon |

Gün içinde her merkez × kategori ayrı koşar; dosyalar farklı saatlerde gelir. Agent'ın tetikleyicisi yeni merkez parquet'inin oluşmasıdır.

## Arayüzdeki "öneri kontrolü" kuralları (forecast accuracy için temel)

Bu kontroller canlı arayüzde var, motor koduna girmez; agent bunları temel alıp genişletir.

- **Fazla stok şüphesi:** depo × ürün için (öneri + stok + açık sipariş), aynı ürünün aynı tipteki (G10 / GB) depolarındaki dağılımına göre üst sınırı aşarsa. Üst sınır = Q3 + 1,5 × max(Q3 − Q1, %25 medyan, 1); ürün en az 8 depoda olmalı; yalnız bugün önerisi olan satırlar.
- **Büyük öneri (hacim):** öneri hacmi > dolap hacmi × eşik (Ambient %0,5 · +4 Other %2 · ETB %5 · MS %5).
- **Büyük öneri (adet):** öneri > `14 Days Sales` (14 günlük satış batch'ten küçükse uyarı yok).
- **Satış tahmini 0 ama öneri var.**
- Hariç: önerisi ≤ 1 batch satırlar, su, demirbaş, Beypazarı ürünleri.

## Bilinen tuzaklar

- MS'te kg ve adet birlikte toplanmaz.
- Aynı merkez için ikinci dosya olabilir (`Ankara (1)`): en yenisini alın.
- Yanlış merkez adıyla kayıt olabilir: dosyanın depo kümesi başka merkezle %50+ örtüşüyorsa uyarı.
- Bugünün All PL'i gün bitene kadar eksiktir; 23.11'de +4 Maltepe / Arnavutköy ve MS Maltepe / Adana All PL'de yoktu.
- Klasör adında yıl yok (`gg.aa`).
