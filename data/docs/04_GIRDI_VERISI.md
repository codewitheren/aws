# Motor Girdileri — Hackathon - Inputs Google Sheet'i

Bu doküman, agent'ın transfer motorlarını çalıştırırken okuduğu her girdiyi anlatır: hangi sekme, hangi kolonlar, motor
onu ne için kullanıyor, eksik ya da bozuk olursa ne olur. Çıktı kolonları için `veri_sozlugu.md` ve
`01_TRANSFER_MOTORLARI.md`'ye, kodun nasıl çalıştırılacağı için `05_KOD_VE_CALISTIRMA.md`'ye bak.

**Tek kaynak:** Hackathon - Inputs, id `1sPUauZX0yE3CQqjJUjB04SIim7_iM8Pw0TXHnUEDW-Y`.
Canlıdaki "Daily Capacity Data" sheet'inin 25.11.2026 kopyasıdır. Sekme adları ve gid'ler (sekme numaraları) orijinaliyle
aynıdır. Kod sekmeleri **gid ile** bulur, adla değil. Sekmenin adı değişebilir ama gid değişmemeli.

## 1. Genel bakış

Girdiler iki türdür:

- **Elle yüklenen dosyalar.** Transferci her gün sistemden indirip panele yüklüyordu. Artık birer gsheet sekmesi:
  Relex, Backlog, Water WH, Kasa İçi Kilo. Kod bunları sekme başına `.xlsx` olarak indirir, böylece tipler (sayı, tarih)
  bozulmaz.
- **Sheet sekmeleri.** Canlıda otomatik ya da haftalık güncellenen referans tablolar. Kod bunları panel gibi CSV olarak
  indirir.

| Sekme | gid | Tür | Ambient | Cold | MS | Güncelleme |
|---|---|---|:-:|:-:|:-:|---|
| Ambient Relex | 142593033 | elle | ✓ | | | her gün, koşudan önce |
| Ambient Backlog | 2061822606 | elle | ✓ | | | her gün (dünkü çıktıdan) |
| Water WH Utilization | 440644371 | elle | ✓ | | | her gün |
| Cold Relex | 952635685 | elle | | ✓ | | her gün |
| Cold Backlog | 58755837 | elle | | ✓ | | her gün |
| MS Relex | 1130379808 | elle | | | ✓ | her gün |
| MS Backlog | 1494883435 | elle | | | ✓ | her gün |
| MS Kasa İçi Kilo | 776529766 | elle | | | ✓ | her gün |
| Buffer Rates | 1173976478 | sheet | ✓ | ✓ | ✓ | ekip kararıyla |
| MS_Other4_Sharing | 2106866758 | sheet | | ✓ | ✓ | ekip kararıyla |
| +4 New | 108896607 | sheet | | ✓ | ✓ | Tableau, her gün |
| ambient_format | 1473098648 | sheet | ✓ | | | Tableau, her gün (Ambient sekmesinden formülle) |
| volume_format | 1615488785 | sheet | ✓ | | ✓ | ürün kartı |
| Product Volume | 1098615637 | sheet | | ✓ | ✓ | ürün kartı, her gün |
| Sim | 823638127 | sheet | ✓ | | | ürün kartı |
| Su palet bilgileri | 1975210347 | sheet | ✓ | | | nadiren |
| Su palet alanı | 868077377 | sheet | ✓ | | | nadiren |
| Depo Palet Limitleri | 670096216 | sheet | ✓ | | | ekip kararıyla |
| Copy of custom_delivery_schedule | 476136392 | sheet | ✓ | | | teslimat programı |
| Sayım Schedule | 1468314948 | sheet (IMPORTRANGE) | ✓ | ✓ | ✓ | sayım ekibi |
| Dokunulmayacak Ürünler (Kampanya) | 1527796592 | sheet | ✓ | ✓ | | her perşembe |
| Slot | 370075811 | sheet | | ✓ | ✓ | nadiren |
| Fast Acceptance Depoları | 1181864150 | sheet | ✓ | | | şu an boş |

`Ambient` (gid 0) sekmesini kod doğrudan okumaz, ama `ambient_format` formülleri ondan beslenir. Bu yüzden silinmemeli.

**Kopyanın durumu (25.11).** `+4 New`, `ambient_format`, Kampanya ve Sharing sekmeleri kopyalandıkları anın değerleridir,
kendiliğinden güncellenmez. Canlı veri gerekirse bu sekmelere orijinal sheet'ten IMPORTRANGE konmalı.

## 2. Ortak kurallar

- **Eşleştirme anahtarları.** Ürün: `Product code` (Relex) = `Product ID` / `marketproduct_id` / `SKUkodu` (sheet'ler).
  Hepsi 24 karakterlik hex ID'dir ve kod bunları küçük harfe çevirerek eşler.
  Cep depo: `Location code` (Relex) = `location` / `Depo Kodu` / `Depo ID`. Bazı sheet'ler depoyu **adla** eşler:
  Buffer Rates, Sharing, Su palet alanı, Depo Palet Limitleri, `+4 New`, `ambient_format`. Ad eşleşmesi Türkçe karakter ve
  boşluk duyarsızdır (`Çamlıkule Büyük` = `ÇamlıkuleBüyük`), ama yazımı farklı ad eşleşmez. Eşleşmeyen depo varsayılan
  değere düşer; motor bunu `kontrol` listesinde "… olmayan depolar" diye raporlar.
- **Sayı biçimi.** Sheet sekmelerinde ondalık ayırıcı nokta, binlik ayırıcı virgüldür (`"1,295"`, `0.77`). Yüzdeler
  `110%` biçimindedir. Motorların ayrıştırıcıları (`clean_locale_number`, `buffer_sayi`) bunları ve `1,1` / `1.10` gibi
  varyasyonları da okur. Elle sekmeler xlsx olarak indiği için orada biçim sorunu yoktur.
- **Depo tipi.** `Domain Type`: G10 (küçük) veya GB (büyük). Relex'te boşsa Ambient GB kabul eder. Eşiklerin çoğu tipe
  göre ayrıdır.
- **Merkez.** Relex dosyası tek merkezin (ör. İzmir) depolarını içerir. Merkez adı Relex'teki depolardan otomatik bulunur
  (depoların en az %90'ı haritada aynı merkeze düşmeli). Bulunamazsa koşuya `merkez` parametresi verilir.

## 3. Elle yüklenen dosyalar

### 3.1 Relex (Ambient Relex, Cold Relex, MS Relex)

Relex'in o günkü sipariş önerisi. Her satır bir cep depo × üründür. Üç kategorinin dosyası aynı 37 kolona sahiptir.
24.11 İzmir'de satır sayıları: Ambient 9.279, Cold 4.221, MS 3.371.

| Kolon | Anlam | Motor ne yapıyor |
|---|---|---|
| `Location code`, `Location name` | Cep depo ID ve adı | Satır anahtarı; sheet'lerle eşleştirme |
| `Domain Type` | G10 / GB | Eşikler, limitler, kampanya listesi |
| `Product code`, `Product name` | Ürün ID ve adı | Satır anahtarı |
| `Custom category`, `Custom sub-category` | Kategori | Demirbaş tespiti ("demirbaş" geçen → 101 puan). Cold: `Et, Tavuk & Balık` → ETB grubu, diğerleri Other |
| `Segment` | Regular / Listed / Supply Shortage / Launch | Listed ya da (Supply Shortage + düşük stok + bulunurluk < %60) → 99 puan |
| `ABC class` | A / B / C / D / E | Öncelik puanı, "Sadece A testi" |
| `Effective quantity` | **Relex önerisi** (adet; MS dökmede kg) | Kesimin başlangıç miktarı. Çıktıda `Orijinal_Miktar` |
| `Order batch size` | Sipariş katı | Kesim ve geri yükleme bu katlarla yapılır. Eski dosyalarda `Batch size` adıyla gelir |
| `End balance` | Cep depo stoğu | Cover, düşük stok kuralı |
| `Open purchase orders` | Yoldaki / açık sipariş | Cover; açık siparişi olan satır önce kesilir (puan 1–2) |
| `Daily FC` | Günlük satış tahmini | Cover = (stok + açık sipariş) / Daily FC. 0 ise cover hesaplanamaz |
| `14 Days Sales`, `1 Day Sales`, `14 Days FC` | Satış geçmişi ve tahmini | Öneri kontrolleri ("büyük öneri") |
| `End Balance DC` | Merkez depo stoğu | Ambient: merkez su stoğu mutabakatı. MS: PTZ ve dökme dağıtımı |
| `Delivery date` | Teslim tarihi | Lead time; sayım ve kampanya (T / T-1) kararı |
| `Son 14 Günlük Bulunurluk` | Raf bulunurluğu (0–1) | 99 puan kuralı |
| `Reference spoiling time` | Raf ömrü (gün) | Cold: cover > raf ömrü uyarısı. MS: PTZ dağıtım sınırı |
| `Pick-to-zero` | Merkezde sıfırlanacak ürün (0/1) | Cold: 99 puan. MS: kalan stok dağıtımı |
| `Transfer type` | AMBIENT / COLD_FOOD / BULK ... | MS: `BULK` = dökme (kasa ile, kg) |
| `Order proposal accepted`, `Order proposal sent` | 0/1 | Kullanılmıyor |

Dikkat edilecekler:

- **İlk kolon** (`aaa` / `aa`) Relex'in birleşik anahtarıdır; kullanılmaz ve adı dosyadan dosyaya değişebilir.
- **Tekrarlı başlık.** `Projected order proposals` kolonu iki kez var. Okununca ikincisi `Projected order proposals.1` olur.
- **Tipler.** CSV olarak indirilirse tipler bozulur: `Order proposal accepted` "No", tarih "26/11/2026", bulunurluk
  "98.18%" metni olarak gelir. Bu yüzden kod bu sekmeleri xlsx olarak indirir.
- **Cold Relex adlandırması.** Transferci "sıfırsız" dosya kullanır (önerisi 0 olan satırlar çıkarılmış).

### 3.2 Backlog

Cep depoda henüz indirilmemiş palet sayısı. Kaynağı bir önceki günün motor çıktısıdır.

| Sekme | Kolonlar | Kullanım |
|---|---|---|
| Ambient Backlog | `Location name`, `Domain Type`, `Depo_Final_Palet_Toplami` (dün gönderilen palet), `Backlog_Palet_Sayisi` | Etkili backlog = teslimat programına göre bugünkü tıra binecek palet. TIR limitinden düşülür. G10 > 6 / GB > 20 palet ise `Backlog_Limiti_Asildi` |
| Cold Backlog | `Location name`, `Domain Type`, `Backlog_Palet_Sayisi` | G10 ≥ 1 ya da GB > 2 palet → depo kapalı (`Depo Backlog Blokaji`) |
| MS Backlog | aynı | G10 > 0 ya da GB ≥ 5 → depo kapalı (`G10 / GB Backlog Engeli`) |

Yalnız backlog'u olan depolar listelenir. Listede olmayan depo 0 kabul edilir; 24.11'de Cold'da 5, MS'te 1 depo vardı.
Ambient dosyası ise bütün depoları içerir (54 satır). Ambient'te depo dosyada yoksa motor bunu "Dünkü sipariş / backlog
dosyasında olmayan depolar" diye uyarır.

### 3.3 Water WH Utilization (Ambient)

Depo × su ürünü bazında stok, satış tahmini ve palet bilgisi (Tableau). 24.11'de 9.451 satır, 32 kolon. Sekme **metin**
olarak tutulur (`"1,295"`, `9%`). Kod bu sekmeyi panelin beklediği UTF-16 sekmeli CSV'ye çevirir.

Kullanılan kolonlar: `Depo: Depo Adı`, `Product ID`, `Warehouse Available Stock`, `Transfer Remaining Stock (9 Days)`,
`water frc t` … `water frc t+3`, `Cover Day`. Hesap:
**Net su stoğu** = stok + yoldaki − teslimata kadar satılacak. Bu değer, su paletlerinin depoda kapladığı alanı
(`Mevcut_Kaplanan_Su_Paleti`) bulmakta kullanılır.

### 3.4 MS Kasa İçi Kilo (MS)

Dökme ürünlerde bir kasanın kaç kilo olduğu. Kolonlar: `Product id`, `Kasa Adedi`, `Toplam Kilo`, `Kasa Kilo`.
Motor yalnız `Kasa Kilo`'yu kullanır (yuvarlanır). Dökme bir ürün listede yoksa sipariş katı kasa kilosu sayılır ve
`kontrol` listesinde "Kasa kilosu tanımsız dökme ürünler" uyarısı çıkar.

## 4. Sheet sekmeleri

### 4.1 Buffer Rates (gid 1173976478)

`Depo Adı | Ambient Buffer | Cold Limit`, değerler `110%` gibi. Dolabın ne kadar aşılabileceğini söyler; kapasite
hesabında çarpandır.

| Kolon | Okuyan | Depo listede yoksa |
|---|---|---|
| `Ambient Buffer` | Ambient (`Hard_Stop_Orani`) | `HARD_STOP_CAPACITY` = 1,10 |
| `Cold Limit` (başlığın başında boşluk var) | Cold ve MS (`buffer_rate`) | `PLUS_4_USABLE_RATIO` = 1,10 |

24.11 İzmir'de 7 SC depo listede yoktu ve varsayılana düştü. Bu, Capacity Management'ın ikinci kaldıracıdır
(bkz. `03_KAPASITE_SHARING_BUFFER.md`).

### 4.2 MS_Other4_Sharing (gid 2106866758)

`Depo Adı | Other+4 | MS+4 | MS+8+12 | Taze Et | Şarküteri ve Merkezden Giden ETB`, 0–1 arası paylar.

- **Cold** `Other+4` payını `other4_oran`, `Şarküteri ve Merkezden Giden ETB` payını `etb_oran` olarak okur.
  Depo yoksa ya da değer 0 ise G10 için 0,81 / 0,76, GB için 0,69 / 0,08 kullanılır.
- **MS** `MS+4` payını `ms4_oran`, `MS+8+12` payını `ms812_oran` olarak okur. Varsayılanlar: MS+4 G10 0,19, GB 0,15;
  MS+8+12 1,0.

### 4.3 +4 New (gid 108896607) — soğuk dolap doluluğu

Tableau'dan gelir. **Uzun formattadır:** `Row Updated At | Depo: Depo Adı | storagetype | Measure Names | Measure Values`.
Motor bunu depo × measure tablosuna çevirir; 24.11'de 486 depo × 63 measure. `Row Updated At` alanındaki en son zaman
damgası alınır; çıktıdaki log'da "snapshot: 2026-11-24 11:30" olarak görünür.

Kullanılan measure'lar:

| Measure | Anlam |
|---|---|
| `Max. Other +4 & MS +4 WH Volume` | +4 odası (Other + MS ortak) toplam litre. GB'de ETB de bu havuzu kullanır |
| `Max. ETB WH Volume` | ETB odası litre (G10 ve G10 gibi davranan GB'ler) |
| `Max. MS +8-12 WH Volume` | 8-12 dolabı litre (MS) |
| `Other +4 & MS +4 Volume Litre`, `… In Transit Volume Litre` | +4 odasında bugün dolu / yoldaki litre |
| `All MS +4 Volume Litre`, `… In Transit …` | Bunun MS kısmı. Other = toplam − MS |
| `DC ETB Volume Litre`, `… In Transit …` | Merkezden giden ETB dolu / yoldaki |
| `MS +8-12 Volume Litre`, `… In Transit …` | 8-12 dolu / yoldaki |
| `… (frc t)`, `(frc t+1)`, `(frc t+2)` | Teslime kadar satılacak (dolaptan boşalacak) litre tahmini |

Kapasite formülü (Cold, MS):
**Kullanılabilir litre = havuz × pay × buffer − (dolu + yoldaki − teslime kadar boşalacak)**.
Depo bu tabloda yoksa (24.11'de Cold'da 14, MS'te 8 depo) hacim kısıtı uygulanmaz.

### 4.4 ambient_format (gid 1473098648) — Ambient dolap doluluğu

Depo bazında ambient dolap durumu. `Ambient` (gid 0) sekmesinden formülle üretilir. İlk iki satır başlık tekrarıdır.

| Kolon | Kullanım |
|---|---|
| `Depo: Depo Adı` | Depo adı (adla eşleşir) |
| `Avg. ambient_dolap_hacim` | Dolap hacmi (L) |
| `ambient_volume Litre`, `ambient_volume Litre (Total Transit)` | Dolu ve yoldaki litre |
| `today_forecast`, `next_day_forecast`, `next_2_days_forecast` | Teslime kadar boşalacak litre (lead time'a göre, son gün × 0,3) |
| `Total Ambient Ratio (In Transit Included)` | Doluluk oranı (0–1, raporlama) |

Hesap: **izin verilen hacim = dolap × buffer − (dolu + yoldaki − boşalacak)**. Depo toplam öneri hacmi bunu aşarsa
fark kadar kesilir.
Depo yoksa hacim kısıtı uygulanmaz; 24.11'de 7 SC depo böyleydi.

### 4.5 Ürün hacmi ve palet

| Sekme | Kolonlar | Okuyan | Not |
|---|---|---|---|
| volume_format (1615488785) | `marketproduct_id`, `hacim2` (L/adet), `L3`, `Koli/Palet EY/MD` | Ambient, MS | 2. satır başlık tekrarıdır. Yalnız `hacim2` kullanılır. Hacmi olmayan ürün Ambient'te 0,5 L sayılır. `Koli/Palet` kolonları kopyada #REF! (kullanılmıyor) |
| Product Volume (1098615637) | Uzun format: `Product ID`, `Storage Type`, `Measure Names`, `Measure Values` | Cold (hacim: `Max. Product Volume m3`), MS (saklama tipi: `Storage Type`) | MS'te saklama tipi dolabı belirler: `+8-12` → 8-12, `ambient` → Ambient (dolap kısıtı dışı), diğerleri +4 |
| Sim (823638127) | `SKUkodu`, `SKU tanımı`, `SON` | Ambient | SON = bir palet katındaki koli adedi. Ambient palet = adet / (SON × 50). `batch eşitle` ise sipariş katı kullanılır |
| Su palet bilgileri (1975210347) | `Product ID`, `sıra`, `palet` (palet başına adet), `transfer_coli_count` | Ambient | Bu listedeki ürünler **su** sayılır (`Is_Water`). Su paleti = adet / `palet` |
| Su palet alanı (868077377) | `Depo`, `Su/ Euro Palet …` (palet adedi) | Ambient | Depodaki su palet yeri. Aşılırsa `Su Depo Kapasitesi (n Palet) Asildi` |

### 4.6 Depo Palet Limitleri (gid 670096216) — TIR limiti

`Depo Adı | Pazartesi … Pazar | Güncel Palet Limiti`. Motor **koşu gününün** kolonunu okur. Depo listede yoksa ya da
değer boşsa varsayılan G10 12, GB 25 palettir. Kaynak çıktıda `Tir_Limiti_Kaynagi` kolonunda yazar. 24.11 İzmir'de
41 depo varsayılana düştü; liste ağırlıkla diğer merkezlerin depolarını içerdiği için bu normal.

### 4.7 Copy of custom_delivery_schedule (gid 476136392) — teslimat programı

Kolonlar: `location`, `custom_transfer_type` (yalnız `Ambient` satırları), `delivery_all` (lead time: 1 = N+1,
2 = N+2), `order_0` … `order_6` (pazartesi … pazar sipariş günleri, TRUE / FALSE).

Ambient bundan iki şey hesaplar:

- bugünkü tırın kaç günde varacağı,
- önceki siparişin tırının ne zaman indiği.

Bu ikisinden **etkili backlog** çıkar. Cuma ve cumartesi kaymaları kodda sabittir.

### 4.8 Sayım Schedule (gid 1468314948)

Sayım ekibinin planı (IMPORTRANGE). Kullanılan kolonlar: `Tarih` (gg.aa.yyyy), `Tarih Açıklama` (ör. "Salıyı
Çarşambaya Bağlayan Gece", "Salı Akşam"), `Depo Kodu`, `Depo Tipi`, `Sayım Türü` (Rutin / Devir), `Genel Sayım Statu`
(İptal Edildi olanlar atlanır).

Teslimat günü depo tipine, sayım türüne ve açıklamaya göre belirlenen yasak aralığa düşerse depoya **hiçbir şey
gitmez**, demirbaş dahil. Aralıklar T'ye göre, uçlar dahil:

| Tip, tür | Gece sayımı | Gündüz sayımı |
|---|---|---|
| GB Rutin | Pazar→Pzt gecesi T-3..T-1, diğer geceler T-2..T-1 | Pazar / Pzt T-2..T; Salı–Cmt T-1..T |
| G10 Rutin | T-1..T | T..T+1 |
| Devir (GB, G10) | T-4..T-1 | T-3..T |

Bu aralıklar Ambient için. Cold ve MS'in kendi tabloları var (kodda `SAYIM_KURALLARI`).

Kurala eşlenemeyen satırlar atlanır ve log'a yazılır. 24.11'de iki satır atlandı: "Sarıçam SC | Salı Akşam | SC" ve
"GetirSu | … | GSU". Depo tipi SC / GSU kurallarda yok.

### 4.9 Dokunulmayacak Ürünler (Kampanya) (gid 1527796592)

Dört kolonda ürün ID listesi: `G10 T-1 | GB T-1 | G10 T | GB T`. Her perşembe güncellenir.

- **T:** önümüzdeki haftanın kampanyaları.
- **T-1:** içinde bulunulan haftanınkiler.

Hangi liste kullanılır:

- **Ambient:** perşembe koşusunda teslimatı ertesi güne düşen (N+1) depolar T-1 listesini alır. Diğer depolar ve diğer
  günler hep T listesini alır.
- **Cold:** perşembe koşusunda bütün depolar T-1 listesini alır, diğer günler T. Cold perşembe günleri T-1'den
  beslenir, çünkü teslimat N+1'dir. Listedeki ürün 100 puan alır (`Dokunulmazlik_Nedeni = Kampanya`) ve en son kesilir.

**Waste** listesi sheet'te değil, motor parametresidir: `DOKUNULMAYACAK_URUNLER_G10/GB` (Ambient),
`DOKUNULMAYACAK_G10/GB` (Cold). Bu ürünler de 100 puan alır.

### 4.10 Slot (gid 370075811) — Cold ve MS

`Durum | Merkez Depo | Depo ID | Bayi Adı | Tür | Domain | Slot Saati Başlangıç | Slot Saati Bitiş`. Frigo / Çift Rejim
slotu 12:00 ve öncesinde biten depolarda, ertesi günün 1/3 tahmin düşüşü kapasiteye eklenmez
(`FORECAST_LOOKAHEAD_RATIO`, `T1_FACTOR` → 0).

**24.11 bulgusu:** Cold log'u "Slot listesi dolu ama hiçbir depo bayraklanmadı" diyor. Öğlen öncesi biten iki depo
(Ayrancı, Çeliktepe) İzmir'e ait değil, yani bu koşu için sorun değil. Yine de `Depo ID` formatı her merkezde kontrol
edilmeli.

### 4.11 Fast Acceptance Depoları (gid 1181864150)

Tek kolon (`Depo`). Şu an boş; motor yalnız bilgi kolonu üretir.

## 5. Koşudan önce agent'ın kontrol edeceği şeyler

Motor eksik girdide çoğu zaman durmaz, varsayılana düşer ve devam eder. Bu yüzden koşudan önce ve sonra şunlara bakılmalı:

1. **Elle sekmeler bugünün mü?** Relex'teki `Delivery date` koşu gününden önce olmamalı. Backlog dünkü çıktıdan mı
   geliyor? Ambient Backlog'daki depo kümesi Relex'tekiyle aynı mı?
2. **Doğru kategori ve merkez mi?** Cold Relex'te `Transfer type` COLD_FOOD, MS'te `Custom category` Meyve & Sebze
   olmalı. Merkez tespiti `merkez.kaynak = harita` ve `pay ≥ %90` ise güvenilirdir.
3. **Sheet sekmeleri dolu mu?** `+4 New` ve `ambient_format` boş ya da eski tarihli ise kapasite kısıtı sessizce
   uygulanmaz. Bakılacak yerler: `+4 New` → `Row Updated At`; `ambient_format` → satır sayısı (~490).
4. **Koşudan sonra `sonuc.json` → `kontrol`.** "Kaynak eşleşmesi" grubu hangi depoların hangi sheet'te bulunamadığını
   listeler: dolap hacmi, kapasite verisi, buffer, oran, TIR limiti, su palet alanı, hacmi tanımsız ürünler. Durum
   `hata` olan her satır kritik uyarı olarak raporlanmalı.
5. **Varsayılana düşen depolar.** Buffer / sharing / TIR'da varsayılan kullanıldıysa bu bir Capacity Management sinyalidir.
   Depo sheet'e eklenmeli.

## 6. 24.11.2026 İzmir koşusundan referans rakamlar

| | Ambient | Cold | MS |
|---|---|---|---|
| Relex satırı / depo | 9.279 / 52 | 4.221 / 56 | 3.371 / 56 |
| Kesinti oranı (adet) | %17,8 | %14,8 | %5,0 (dökme hariç) |
| Kesilen | 37.465 adet | 4.648 adet | 388 adet + dökme |
| Ana neden | TIR palet limiti %67 | Backlog blokajı %57 | Dökme kasa yuvarlama %42 |
| Merkez satır | 7.291 / 10.000 | 3.561 / 6.900 | 1.656 / 10.000 |
| Merkez koli | 17.564 / 20.000 | — | — |

Bu rakamlar `kod/testler/test_karsilastir.py` ile yeniden üretilebilir. Girdi kopyası `data/gsheet_kopya_24.11/`
klasöründe.
