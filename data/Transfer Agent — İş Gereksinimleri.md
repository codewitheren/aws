# Transfer Agent — İş Gereksinimleri

Nov 24, 2026 · @Dersu

## Amaç ve kapsam

Agent, transfer ekibinin her gün elle yaptığı kontrol ve analiz işini bir supply chain analisti gibi üstlenir: transfer çıktılarını okur, sorunları bulur, nedenini açıklar ve uygulanabilir öneri verir. Kesim hesaplarını yeniden yapmaz; mevcut motorların (Ambient & Su, +4/Cold, MS) çıktısını ve case picking verisini yorumlar.

**Bağlam.** Getir merkez depolarından (Maltepe, İzmir, Adana, Arnavutköy, Ankara, Diyarbakır) yaklaşık 513 cep depoya her gün transfer yapılır. Relex sipariş önerir, bizim motorlarımız bu öneriyi cep depo kapasitesine ve merkez limitlerine göre keser. Günde yaklaşık 100 bin satırlık çıktı oluşur; bunun elle kontrolü mümkün değildir.

| Başlık | Ne zaman çalışır | Kapsam | Ana çıktı |
| --- | --- | --- | --- |
| 1. Debugging & Forecast Accuracy | Anlık: her yeni transfer çıktısında ve sorulduğunda | Ambient & Su, +4, MS | Uyarı listesi, düzeltme önerisi, depo bazlı "neden kıstık" cevabı |
| 2. Cost Minimizing (Case Picking) | Haftalık | Ambient | Gönderim tipi önerisi (adetli / subpackli / kolili / koli ×2) |
| 3. Capacity Management (Sharing) | Haftalık | Cold: +4 Other, MS, ETB | Depo bazlı yeni sharing payları ve beklenen etki |

**Neden script değil agent.** Hesaplar sabit tool'larda kalır, rakamlar güvenilir olur. Agent hangi hesabı ne zaman yapacağına karar verir, sonuçları depo bağlamında yorumlar, önceliklendirir, sorulara cevap verir ve uygulanan önerilerin etkisini takip eder.

**Human in the loop.** Agent yalnız okur ve önerir; Relex'e, Drive'a veya oran sheet'ine kendisi yazmaz. Önerileri uygulanabilir formatta hazırlar, kararı transfer ekibi verir.

## 1. Debugging & Forecast Accuracy

Her transfer çıktısı oluştuğunda agent dosyanın tamamını tarar ve yalnız müdahale gerektiren birkaç düzine satırı öne çıkarır. Transfer gün içinde merkez × kategori bazlı ayrı ayrı koştuğu için agent sabit bir saatte değil, dosya geldiğinde çalışır.

**Tetikleyici.** Yeni bir merkez parquet'i oluştuğunda (ör. `Parquet Arşiv/23.11/+4/Maltepe.parquet`) ya da kullanıcı bir parquet verdiğinde. Her zaman sohbetle soru da sorulabilir.

**Beklentiler**

1. **Koşu bütünlüğü.**
   - Beklenen merkez × kategori dosyaları geldi mi (MS'te Diyarbakır yok)? Aynı merkez için ikinci dosya var mı (`Ankara (1)`)?
   - Dosyadaki cep depolar başka bir merkezle %50'den fazla örtüşüyor mu? Bu, yanlış merkez adıyla kayıt demektir (05.11'de +4 Maltepe koşusu "İzmir" adıyla kaydedildi).
2. **Hatalı çıktı.**
   - Demirbaş (`Cut_Priority = 101`) satırda kesim: hiç olmamalı, kritik hata.
   - `Daily FC` boş ya da 0 iken gönderim; kampanya (`Dokunulmazlik_Nedeni = Kampanya`) veya Listed/Supply Shortage ürünlerin kesilmesi.
   - Buffer Rates sekmesinde olmadığı için varsayılan buffer'a düşen depolar.
3. **Forecast ve öneri anomalisi (istatistiksel).**
   - Aynı ürünün depolar arası dağılımına göre: bir depoya giden öneri veya (stok + açık sipariş + öneri) diğerlerinin çok üstündeyse. G10 ve GB ayrı değerlendirilir. Mevcut kural: üst sınır = Q3 + 1,5 × max(Q3 − Q1, %25 medyan, 1), en az 8 depo.
   - Kendi geçmişine göre: depo × ürünün `Daily FC` değeri son günlere göre sıçradıysa ya da öneri `14 Days Sales`'i aşıyorsa.
   - Hacim olarak: öneri hacmi dolap hacminin belirli bir payını aşıyorsa (Ambient %0,5, +4 Other %2, ETB %5, MS %5).
   - "Öneri var ama satış tahmini 0" satırları.
   - Önerisi 1 batch veya altındaki satırlar ile su, demirbaş ve Beypazarı ürünleri bu kontrollere girmez.
4. **Kısma anomalisi.** Merkez × kategori kısma oranı ve C/P, düne ve geçen haftanın aynı gününe göre normal bandın dışındaysa. Merkez satır limitine yakınlık.
5. **Depo bazlı "neden kıstık?" (her zaman açık).** Kullanıcı bir depo sorduğunda agent o deponun tüm kısma nedenlerini miktarıyla listeler:
   - palet / TIR limiti (ve etkili backlog'un payı),
   - dolap hacmi yetmemesi (doluluk %'si ile),
   - backlog blokajı, sayım günü, merkez satır limiti, su palet alanı,
   - en çok kesilen ürünler ve sınıfları (A kesildiyse özellikle belirtir).
6. **Düzeltme önerisi.** Her bulgu için ne yapılmalı: parametre, liste, sheet, Relex. Kullanıcı öneriyi uygulayıp yeniden koştuğunda agent önce/sonra farkını raporlar.

**Çıktı formatı.** Ciddiyet sıralı uyarı listesi: **Kritik** (sevkiyattan önce düzeltilmeli) · **Uyarı** (bugün bakılmalı) · **Bilgi** (izlenmeli). Her uyarıda: merkez, kategori, depo, ürün (varsa), kanıt rakamı, önerilen aksiyon. Ayrıca Relex'e iletilecek satır listesi (CSV/Excel).

## 2. Cost Minimizing (Case Picking, Ambient)

Agent her hafta Ambient'teki her cep depo × ürün için en uygun gönderim tipini önerir; karar sipariş sıklığına göre iki yönlüdür. Amaç merkezde toplanan satır sayısını (PL, toplama maliyeti) düşürmek ve dolu depolarda yer açmaktır.

**Gönderim tipleri** (x = Relex sipariş katı `Order batch size`, koli = koli içi adet, SP = subpack içi adet; SP > 1 ise geçerli):

| Tip | SP geçerli | SP yok |
| --- | --- | --- |
| Adetli | x < SP | x < koli |
| Subpackli | SP ≤ x < koli | — |
| Kolili | x ≥ koli | x ≥ koli |
| Koli ×k | x = k × koli | x = k × koli |

**Karar mantığı (sıklık).** 30 günde açılan satır ≈ min(depo sipariş günü sayısı, ⌈toplam talep / batch⌉).

- **Çok sık gidiyor → yukarı (satır kazanımı).** Adetli ürün sık gidiyorsa subpack veya koliye; kolili ürün neredeyse her sipariş gününde gidiyorsa koli ×2 / ×3'e. Sıklık düşer, satır azalır.
- **Çok seyrek gidiyor → aşağı (kapasite kazanımı).** Kolili ürün örneğin 3 ayda bir gidiyorsa subpack veya adetliye. Satır biraz artar (90 günde 1 → 30 günde 1) ama depoda bir koli yerine küçük miktar durur, yer açılır. Özellikle kapasitesi dolu depolarda önerilir. Koli cover'ı raf ömrünü aşıyorsa (waste riski) depo dolu olmasa da önerilir.

**Yukarı geçiş filtreleri (ekip kuralları)**

- Su ve SC depoları (adı " SC" ile biten, 33 depo) hariç; segment Regular / Supply Shortage / Launch.
- Depo kapasite sorunlu değil: son 31 günde 3 günden az hacim kısması ve Tableau ortalama doluluk < %95.
- Cover ≤ raf ömrü ve < 180 gün (raf ömrü 0 = SKT takibi yok, kısıt yok).
- Koli / subpack hacmi ≤ 150 L, birim hacim ≤ 2 L, depo tahmini doluluk ≤ %90.

**Her öneri için istenen rakamlar**

- Günlük satır kazancı (yukarı) veya eklenen satır (aşağı).
- Ek stok hacmi veya açılan hacim (L): (sipariş başı adet farkı) / 2 × birim hacim (döngü stoğu).
- Depo tahmini doluluk %'si: önce ve sonra.
- Cover ve raf ömrü kontrolü.

**Sıralama.** Yukarı: satır kazancı / ek stok (en verimli önce). Aşağı: açılan hacim / eklenen satır (en çok yer açıp en az satır ekleyen önce).

**Çıktı.** Relex'e yüklenebilecek PL listesi: merkez, depo, ürün, mevcut tip ve batch, önerilen tip ve batch, yön (yukarı/aşağı), gerekçe rakamları. Yanında özet: toplam günlük satır etkisi, adetli oranı önce/sonra, depo bazında açılan hacim.

**Referans rakam (mevcut son model, 20.11.2026).** 36.528 PL değişikliği (33.636 kolili, 2.892 subpackli), günde 4.647 satır kazancı, adetli oranı %24,5 → %21,3. Bu yalnız yukarı yönlü; agent aşağı yönü ve koli ×k'yı ekler.

## 3. Capacity Management (Sharing ve Buffer, Cold)

Agent her hafta cep depo bazında paylaşımlı dolapların doluluk ve kapasite kısmasına bakar, yeni sharing payları önerir ve beklenen etkiyi verir. Hedef aynı dolapla daha fazla ürün göndermek; kaydırmanın yetmediği depolarda ek dolap ihtiyacını ortaya koymak.

**Paylaşılan dolaplar (oran sheet'i, gid 2106866758).** G10 depolarda iki oda vardır:

| Oda | Paylar | Kural | Okuyan motor |
| --- | --- | --- | --- |
| +4 odası | `Other+4`, `MS+4` | Other+4 + MS+4 = 1 | Cold (`other4_oran`), MS (`ms4_oran`) |
| ETB odası | `Taze Et`, `Şarküteri ve Merkezden Giden ETB` | toplam = 1 | Cold (`etb_oran`), ETB motoru (`taze_et_oran`) |
| 8-12 | `MS+8+12` | hep 1 | MS |

GB depolar tek havuzdur (dört kalem toplamı ≈ 1); ilk sürümde kapsam dışı. İstisnalar: Gaziemir ve Suadiye Büyük GB ama G10 gibi davranır.

**Tanımlar (mevcut Sharing analizi)**

- Kapasite = havuz × pay × buffer (litre).
- İhtiyaç = teslimatta dolu hacim + Relex öneri hacmi (kesinti olmasaydı teslimat sonrası dolu hacim).
- Doluluk = ortalama ihtiyaç / ortalama kapasite; doluluk > %100 = dolu.
- Kapasite kısması = yalnız dolap kapasitesi nedenli kesilen litre / öneri litre. Backlog, merkez satır limiti, kara liste dahil değil.

**Karar kuralları (ekip kararları)**

- Bir taraf dolu, diğeri hedefin altında → **kaydır**. Hedef (%100 veya %90) yalnız payı azaltılan tarafa uygulanır: yeni pay = gereken pay / hedef, 0,01'e yukarı yuvarlanır; kalan pay dolu tarafa verilir.
- İkisi de dolu → **dolap eklenmeli** (ek hacim ihtiyacı litre olarak). İkisi de boş → işlem yok.
- MS ihtiyacı haftalık dalgalıdır (Cuma ≈ ortalamanın 1,3 katı). MS'ten pay alınırken MS'in en yoğun gününe göre bakılır; aksi halde Cuma'ları MS kısılır.
- Hiçbir kategoriye öncelik yok; net etki = Other + MS (veya ETB iki tarafı) toplam kapasite kısması L/gün.

**Agent'tan beklenenler**

1. Son 2–4 haftanın verisiyle depo × grup doluluk ve kapasite kısması tablosu.
2. Depo bazında öneri: kaydır / dolap ekle / işlem yok, yeni paylar ve gerekçe.
3. Simülasyonla beklenen etki: her gün yeni kapasiteyle kısılan = min(max(ihtiyaç − kapasite, 0), öneri). Çıktı: iki tarafın doluluk ve kısma %'si önce/sonra, toplam kısma L/gün önce/sonra, "şu kadar fazla ürün giderdi".
4. Uygulanan değişikliklerin izlenmesi: tahmin vs gerçekleşen (en az 2 tam hafta sonra). 10.11.2026'da 7 depoda (Atmaca, Berdan, Çukurova, Güneykent, Kıyıboyu, Merdivenköy, Zümrütevler) Other+4 → MS+4 kaydırması uygulandı; agent bunların sonucunu raporlamalı.

**Buffer da optimize edilecek alan.** Kapasite = havuz × pay × buffer olduğu için buffer (Buffer Rates sheet'i: `Ambient Buffer`, `Cold Limit`; %100 / %105 / %110) ikinci kaldıraçtır. Kaldıraç sırası: önce sharing (fiziksel risk yok), sonra buffer (5 puanlık adımlarla), en son ek dolap.

- **Artır:** depo kronik olarak kapasiteden kısılıyor, buffer %110'un altında, sharing tek başına yetmiyor ve gerçek doluluk izin veriyor.
- **Düşür:** gerçek doluluk sürekli %100'ün üstünde ya da soğukta bozulma / waste artıyor.

| Göztepe (16.10–15.11) | Pay Other / MS | Buffer | Other doluluk |
| --- | --- | --- | --- |
| Mevcut | 0,77 / 0,23 | 1,00 | %117 (MS %60) |
| Sharing MS → Other (%90 hedef) | 0,84 / 0,16 | 1,00 | %107 |
| + Buffer %110 | 0,84 / 0,16 | 1,10 | %97 |

Aynı dönemde Ayrancı (%125) ve Küçükçekmece (%106) da buffer'ı %100 olan dolu depolar; Other dolu ve MS %90'ın altında olan 22 depo var.

**Çıktı.** Oran sheet'ine girilecek formatta tablo: Depo Adı, mevcut paylar, önerilen paylar, beklenen etki, karar. Ayrıca dolap gereken depolar listesi ve ek hacim ihtiyacı (L).

**Referans (01.10–05.11.2026, 287 G10 depo, %100 hedef).** 47 depoda MS → Other kaydırma önerildi; toplam kapasite kısması 9.301 → 7.528 L/gün. 9 depoda iki taraf da dolu, dolap gerekli. 220 depoda işlem yok.

**Açık nokta.** Mevcut analiz yalnız +4 odasını (Other / MS) kapsıyor. ETB odası için Taze Et tarafının doluluk verisi ETB direkt sevk çıktılarında (`Direkt Sevk/ETB/`); bu veri eklenmeden ETB önerisi yalnız merkezden giden ETB tarafına göre yapılabilir.

## Terimler sözlüğü

Agent bu terimleri aşağıdaki anlam ve formüllerle kullanmalı; kendi tanımını üretmemeli.

| Terim | Anlam |
| --- | --- |
| Merkez depo | Transferin çıktığı depo: Maltepe, İzmir, Adana, Arnavutköy, Ankara, Diyarbakır. Dosya adından gelir. |
| Cep depo (DS) | Transferin gittiği darkstore. `Location code` / `Location name`. |
| G10 / GB | Cep depo tipi (`Domain Type`). Eşikler ve listeler tipe göre ayrıdır. |
| Kategori | Ambient & Su, +4 (Cold), MS (meyve sebze). Her biri ayrı motor ve ayrı dosya. |
| Relex önerisi | Relex'in sipariş önerisi. Ambient/+4 `Orijinal_Miktar`, MS `Effective quantity`. |
| Final | Gönderilen miktar. Ambient/+4 `Final_Miktar`, MS `Final_Quantity`. |
| Kısma (kesim) | Motorun öneriyi azaltması. Kısılan miktar = Σ max(öneri − final, 0), yalnız öneri > 0 satırlar. |
| Kısma oranı | Kısılan / Σ öneri. |
| Orderline (satır, PL) | Bir depo × ürün satırı. Proposed = öneri > 0; Created = final > 0; Silinen = öneri > 0 ve final = 0; Kısılan = 0 < final < öneri. |
| C/P | Created / Proposed (satır veya miktar). |
| Batch (sipariş katı) | `Order batch size`. Öneri bunun katı olur. |
| Cover (gün) | (stok + açık sipariş) / günlük satış tahmini (`Daily FC`). FC = 0 → sonsuz. |
| Öncelik puanı | `Cut_Priority`. Düşük olan önce kesilir; aynı puanda cover'ı yüksek olan. 101 demirbaş (kesilmez), 100 kampanya/waste, 99 Listed / Supply Shortage. |
| Demirbaş | Kesilmeyen sarf malzeme (poşet vb.). Tek istisna: sayım günü depo tamamen kapalıdır. |
| Dokunulmaz | Kampanya (sheet, T / T-1 listesi) ve Waste (elle liste) ürünleri. Kesilebilir ama en son. |
| Backlog | Cep depoda henüz indirilmemiş palet. Ambient'te TIR limitini düşürür (etkili backlog); +4 ve MS'te eşiği aşarsa depoyu kapatır. |
| TIR / palet limiti | Ambient'te depoya bir tırla gidebilecek palet sayısı (`Tir_Limiti`). Palet = adet / (SON × 50); su = adet / `palet`. |
| Sayım | Sayım günü depoya hiçbir şey gitmez (neden `Sayım`). |
| Dolap hacmi / doluluk | Cep depo dolap litresi ve teslimat sonrası doluluk %'si. Buffer (ör. 1,10) dolabın ne kadar aşılabileceği. |
| Merkez satır limiti | Merkezin bir günde toplayabileceği satır: Ambient 10.000, +4 6.900, MS 10.000. |
| Neden kovaları | **DS Capacity** (hacim, palet, su alanı, sayım, koli limiti) · **Backlog** · **Merkez Satır Limiti** · **Kesinti yok**. |
| Item group | +4'te ETB (şarküteri / merkezden giden et-tavuk) ve Other. |
| Cabinet type | MS'te +4, 8-12 veya Ambient dolap. |
| Dökme (bulk) | MS'te kasayla giden ürün; miktarlar **kg**. |
| PTZ (Pick-to-zero) | Merkezde stok sıfırlanacak ürün; kalan stok depolara dağıtılır. |
| Sharing (pay) | Paylaşımlı dolapta grupların payı: Other+4 / MS+4, Taze Et / Merkezden giden ETB. |
| Gönderim tipi | Adetli / Subpackli / Kolili / Koli ×k (bkz. Cost Minimizing). |
| Raf ömrü | Ürünün SKT günü; 0 = takip yok. |
| SC depo | Adı " SC" ile biten depolar; case picking dışı. |

## Veri kaynakları ve örnek çıktılar

Agent'ın ana girdisi merkez depo kırılımlı günlük parquet'lerdir; verimlilik şimdilik öncelik değil. Örnek dosyalar 23.11.2026 Maltepe gerçek verisinden, iki depo (Göztepe, Kavacık) için kesilmiştir ve dokümanla birlikte paylaşılır.

| Kaynak | Yol | Boyut (23.11) | Ne için |
| --- | --- | --- | --- |
| Ambient & Su merkez parquet'i | `Parquet Arşiv/gg.aa/Ambient ve Su/<merkez>.parquet` | Maltepe: 54.470 satır, 134 kolon | Debugging, depo kısma analizi, Relex kalitesi |
| +4 (Cold) merkez parquet'i | `Parquet Arşiv/gg.aa/+4/<merkez>.parquet` | Maltepe: 18.415 satır, 89 kolon | Debugging, sharing (Other / ETB doluluk) |
| MS merkez parquet'i | `Parquet Arşiv/gg.aa/MS/<merkez>.parquet` | Maltepe: 11.346 satır, 47 kolon | Debugging, sharing (MS +4 doluluk) |
| All PL | `Parquet Arşiv/gg.aa/"<gün> <Ay> All PL.parquet"` | 193.772 satır, 25 kolon | Koşu bütünlüğü, hızlı özet |
| Case picking master | `Case Picking/master/*.parquet` | son\_adaylar 156.700 satır; urun\_depo\_master 1,36 M | Cost Minimizing |
| Oran sheet'i | Sheet gid 2106866758 (yedek: `Sharing/veri/oran.csv`) | \~457 depo | Capacity Management (mevcut paylar) |

**Paylaşılan örnek dosyalar** (`Hackathon/ornek_veri/`):

- `ornek_ciktilar_23.11_Maltepe.xlsx`: tüm örnekler tek Excel'de. Sekmeler: Okuma Rehberi, Beklenen Uyarı Örneği, Ambient\_Maltepe, Plus4\_Maltepe, MS\_Maltepe, AllPL\_Maltepe, CasePicking\_Adaylar.
- `ornek_ambient_maltepe_23.11.parquet` (2.353 satır), `ornek_plus4_maltepe_23.11.parquet` (193), `ornek_ms_maltepe_23.11.parquet` (127), `ornek_allpl_23.11.parquet` (2.336), `ornek_case_picking_son_adaylar.parquet` (1.199).
- `beklenen_uyari_ornegi.csv`: agent'ın bu veriden üretmesini beklediğimiz uyarı listesi (elle hazırlandı).
- `veri_sozlugu.md`: bir üst klasörde (\`Hackathon/\`); kolon sözlüğü ve iş kuralları, kolon adları 23.11 parquet'lerinden doğrulandı (Kiro'da steering dosyası olarak kullanılabilir).

**Her kategoride bakılacak ana kolonlar**

| Amaç | Ambient & Su | +4 (Cold) | MS |
| --- | --- | --- | --- |
| Kimlik | `Location code`, `Location name`, `Domain Type`, `Product code`, `Product name` | aynı + `Item_group` (ETB/Other) | aynı + `Cabinet_Type`, `Is_Bulk` |
| Öneri / final / neden | `Orijinal_Miktar`, `Final_Miktar`, `Kesinti_Nedeni` | `Orijinal_Miktar`, `Final_Miktar`, `Kesinti_Nedeni` | `Effective quantity`, `Effective_Units`, `Final_Quantity`, `Trim_Reason` |
| Sınıf / koruma | `ABC class`, `Segment`, `Cut_Priority`, `Dokunulmazlik_Nedeni`, `Is_Water` | `ABC class`, `Segment`, `Cut_Priority`, `Pick-to-zero` | `ABC class`, `Pick-to-zero` |
| Stok / tahmin | `End balance`, `Open purchase orders`, `Daily FC`, `14 Days Sales`, `End Balance DC`, `Calculated Cover Day` | `End balance`, `Open purchase orders`, `Daily FC`, `14 Days Sales`, `Calculated Cover Day`, `Reference spoiling time` | `End balance`, `Open purchase orders`, `Daily FC`, `14 Days Sales`, `End Balance DC`, `Cover_Day_Calc`, `Reference_Spoiling_Time` |
| Kapasite | `Avg. ambient_dolap_hacim`, `Hard_Stop_Orani`, `Orijinal_` / `Gelecek_Teslimat_Sonrasi_Doluluk (%)`, `Total Ambient Ratio (In Transit Included)` | `Kapasite_Ham_Litre`, `Uygulanan_Oran`, `Uygulanan_Buffer`, `Kapasite_Litre`, `Anlik_Stok_Litre`, `ETB_` / `Other_Kesintisiz_Gelecek_Doluluk (%)` | `Allowed_Space`, `Final_Group_Utilization_Pct`, `Son_Doluluk_Pct`, `Vol_Per_Unit` |
| Palet / backlog | `Tir_Limiti`, `Tir_Limiti_Kaynagi`, `Etkili_Backlog_Palet`, `Backlog_Kesilen_Miktar`, `Depo_Orijinal_Palet_Toplami`, `Depo_Final_Palet_Toplami` | `Backlog_Palet_Sayisi` | `Backlog` |
| Kapanış | `Sayim_Kisiti` | `Sayim_Kisiti` | `Sayim_Bilgisi` |

**Dikkat edilecekler (gerçek veriden)**

- MS'te kolon adları farklı ve dökme satırlarda miktar **kg**.
- `(%)` ile biten kolonlar 0–100; `Total Ambient Ratio`, `tableau_ort_doluluk` gibi oranlar 0–1 ölçeğindedir.
- Aynı gün içinde bir merkez × kategori dosyası henüz gelmemiş olabilir; bugünün All PL'i gün bitene kadar eksiktir.
- 23.11 All PL'de +4 Maltepe, +4 Arnavutköy, MS Maltepe ve MS Adana yok; merkez parquet'leri var. Agent bunu yakalamalı (bkz. Beklenen Uyarı Örneği).

## Chat senaryoları (beklenen cevaplar)

Aşağıdaki cevaplar 23.11.2026 Maltepe gerçek verisiyle elle hazırlandı; agent'ın cevabı bu tonda, bu yapıda ve rakamla gelmeli. Ortak kurallar: önce sonuç, sonra kanıt rakamları, en sonda aksiyon; tahmin edilen değerler "tahmini" diye etiketlenir; veri yetmiyorsa ne eksik olduğu söylenir.

### Senaryo 1 · Dosya geldi, otomatik uyarı (Debugging)

*Tetik: `Parquet Arşiv/23.11/Ambient ve Su/Maltepe.parquet` oluştu.*

**Agent:** Maltepe Ambient & Su koşusu geldi: 52.872 öneri satırı, 29.688 satır gönderiliyor, kısma oranı %44. 1 kritik, 3 uyarı var.

- **Kritik – All PL eksik:** +4 Maltepe, +4 Arnavutköy, MS Maltepe ve MS Adana parquet'leri var ama 23 Kasım All PL'de bu satırlar yok. Kayıtları All PL'e yeniden yazdırın, yoksa data ekibi bu günü eksik çeker.
- **Uyarı – Göztepe %93 kısıldı:** kısıt TIR limiti (4 palet), hacim değil. Ayrıntı için "Göztepe" yazın.
- **Uyarı – Kavacık %73 kısıldı:** dolap dolu (tam gönderimde %144). Kronik: son 24 sipariş gününün 24'ünde hacim kısması.
- **Uyarı – Relex:** 682 satır fazla stok şüphesi, 942 satır "tahmin 0 ama öneri var". İlk 20 satır ekte.
- Bilgi: Buyaka'da demirbaş poşet 1.000 → 0 kesildi; depo sayımda, beklenen davranış.

### Senaryo 2 · "Göztepe'de neden bu kadar kıstık?" (Debugging)

**Kullanıcı:** Göztepe'de neden bu kadar kıstık?

**Agent:** Göztepe'de (G10) Ambient'te önerinin %93'ü kesildi: 25.605 adetten 1.805'i gidiyor. Sorun dolap değil, palet.

| Neden | Kesilen adet | Pay |
| --- | --- | --- |
| G10 Palet Limiti Aşıldı | 21.328 | %90 |
| Su Depo Kapasitesi (6 palet) | 2.472 | %10 |

- Öneri 41,8 palet; G10 depolarında medyan 10,7 palet (yaklaşık 4 katı).
- TIR limiti 4 palet (G10'da en düşük değer; medyan 12). Kaynak: günlük TIR sheet'i, Pazartesi. Backlog yok.
- Dolap: tümü gitseydi teslimat sonrası doluluk %84,6 olacaktı; şu an %28,6. Yani yer var.
- A sınıfından 6.620 adet kesildi.

**Öneri:** İki şey birlikte: (1) Öneri olağanın 4 katı, Relex'te Göztepe'ye özel bir sıçrama olup olmadığını kontrol edin. (2) Öneri doğruysa TIR limiti 4 çok düşük; dolap %85'e kadar dolabileceği için limiti artırmak güvenli.

### Senaryo 3 · "Kavacık için ne yapabiliriz?" (kaldıraçları birlikte değerlendirme)

**Kullanıcı:** Kavacık sürekli kısılıyor, ne yapabiliriz?

**Agent:** Kavacık'ta sorun kronik kapasite: Ambient dolabı 22.518 L, Tableau ortalama doluluk %128, son 24 sipariş gününün 24'ünde hacim kısması var. Seçenekleri karşılaştırdım:

| Seçenek | Etki | Değerlendirme |
| --- | --- | --- |
| Seyrek giden kolilileri küçültmek (case picking aşağı) | 15 PL, yaklaşık 69 L yer, günde +0,7 satır | Dolabın %0,3'ü; tek başına yetmez |
| Buffer artırmak | Buffer zaten 1,10 | Daha fazla esnetmek riskli |
| Ek dolap / alan | Tam talep için \~%44 ek hacim gerekiyor (tahmini) | Kalıcı çözüm |
| Cold tarafı | Other+4 %78, MS +4 %41: +4 odasında yer var. ETB odası %124 dolu | ETB için Taze Et doluluk verisi gerekli |

**Öneri:** Ambient için kalıcı çözüm ek dolap. Kısa vadede case picking aşağı geçişi uygulanabilir ama etkisi küçük. Cold tarafında +4 odasına müdahale gerekmiyor.

### Senaryo 4 · "Bugün Relex'e müdahale gereken bir şey var mı?" (Forecast Accuracy)

**Agent:** Evet, öncelik sırasıyla ilk 3:

1. **Göztepe, tüm Ambient:** depo toplamı 41,8 palet, G10 medyanının \~4 katı.
2. **SuadiyeBüyük – Coca-Cola Zero Sugar (250 ml):** öneri 144 + stok 304 = 448; GB depolarında bu ürünün medyanı 68 (6,6 kat). Depo bugün sayımda olduğu için gitmiyor, ama yarın tekrar gelecek.
3. **Coca-Cola Light (6 × 250 ml), 4 G10 depo** (Suadiye, Erenköy, Yeniköy, Maslak Eclipse): toplam (stok + açık + öneri) G10 medyanının 5,5–6,4 katı.

Tam liste (682 satır, katına göre sıralı) Relex'e iletilecek formatta hazır.

### Senaryo 5 · Haftalık case picking önerisi (Cost Minimizing)

**Kullanıcı:** Maltepe için bu haftanın case picking önerisini ver.

**Agent:** Maltepe'de 70 depoda 26.279 adetli PL kolili olmaya uygun (aday havuzu, filtreler sonrası). Hepsi uygulanırsa günde yaklaşık 2.822 satır kazanılır, depolarda toplam 135.700 L ek döngü stoğu oluşur (tahmini).

| Depo | PL | Satır kazancı / gün | Ek stok (L) | Doluluk önce → sonra |
| --- | --- | --- | --- | --- |
| Göztepe | 767 | 153,7 | 3.260 | %72,8 → %81,2 |

- Göztepe'de en verimli örnekler: Mars (51 g) batch 2 → koli 288, günde 0,67 satır; Fellas Fındıklı Meyve Bar batch 2 → koli 144.
- Aşağı yön: Kavacık gibi kapasite sorunlu depolarda seyrek giden kolililer (ör. Fellas Protein Tozu, 138 gün koli cover) adetliye çekilir.
- Veri kalitesi: Marmarabirlik Yeşil Kokteyl Zeytin'de subpack içi 3.888 > koli içi 24 görünüyor; ürün kartı düzeltilmeli.

Relex'e yüklenecek PL listesi ekte (depo, ürün, mevcut / yeni batch, yön, gerekçe).

### Senaryo 6 · Haftalık sharing önerisi (Capacity Management)

**Kullanıcı:** Bu hafta hangi depolarda sharing'i değiştirelim?

**Agent (16.10–15.11 gerçek verisiyle, %90 hedef):**

| Depo | Mevcut pay (Other / MS) · buffer | Doluluk Other / MS (16.10–15.11) | Karar | Beklenen Other doluluk |
| --- | --- | --- | --- | --- |
| Göztepe | 0,77 / 0,23 · 1,00 | %117 / %60 | MS → Other (0,84 / 0,16) + buffer %110 | %97 |
| Ayrancı | 0,79 / 0,21 · 1,00 | %125 / %62 | MS → Other (0,85 / 0,15) + buffer %110 | %106: kısmen çözer, dolap da gerekli |
| Ortaköy | 0,77 / 0,23 · 1,10 | %168 / %68 | Kaydırma yetmez (%158), buffer zaten %110 | Dolap gerekli |
| Kavacık | 0,77 / 0,23 · 1,10 | %95 / %49 | +4'te işlem yok | — |

Oran sheet'ine ve Buffer Rates sheet'ine girilecek iki tablo ekte; MS payları en yoğun güne (Cuma) göre ayrıca kontrol edilir. Kaydırma yetmeyen depolar için ek hacim ihtiyacı (L) ayrı listede.

### Senaryo 7 · Takip (Capacity Management)

**Kullanıcı:** 10 Kasım'da sharing'i değiştirdiğimiz 7 depo ne durumda?

**Agent (beklenen yapı):** Her depo için eski → yeni pay, analizin tahmini ve gerçekleşen. Örnek satır: Kıyıboyu, Other 0,97 → 0,73. Tahmin: Other doluluk %89,6, Other kısma %3,2. Gerçekleşen: (son 2 haftanın verisinden hesaplanır). Sapma büyükse agent geri alma veya yeni pay önerir; motorun eski payı kullandığı günleri ayrıca işaretler.

## Kurallar, kapsam dışı ve kabul kriterleri

Agent rakamları sabit tool'lardan almalı; yorum ve öneri serbest, hesap değil.

**Kurallar**

- Hesaplar (kısma, C/P, cover, satır kazancı, doluluk, simülasyon) bu dokümandaki tanımlarla, sabit tool'larda yapılır. Agent serbest sorular için kod yazabilir, ama resmi rakamlar tool'dan gelir.
- Her öneride kanıt rakamı ve kaynak dosya/kolon belirtilir. Tahminler "tahmini" diye etiketlenir.
- Bilinen istisnalar hata sayılmaz: sayım günü demirbaş kesimi; MS'te nedeni "Onaylandi" olup final ≠ öneri satırlar (dökme kasa yuvarlaması, PTZ, telafi).
- MS dökme kg ve adet birlikte toplanmaz.
- Tek günlük veriyle sharing veya case picking kararı verilmez; haftalık öneriler en az 2–4 haftalık veriye dayanır.

**Kapsam dışı**

- Agent Relex'e, Drive'a, oran sheet'ine veya motorlara yazmaz; öneriyi dosya olarak hazırlar, insan uygular.
- Kesim hesabını yeniden yapmaz; motor çıktısını yorumlar. "Düzeltme uygulanırsa" etkisini göstermek için motorun yeniden koşulması gerekir.
- İlk sürümde GB sharing'i ve ETB odasının Taze Et tarafı (veri eksik) kapsam dışı.

**Kabul kriterleri (bilinen rakamlarla doğrulama)**

- [ ] 23.11 Maltepe Ambient: 52.872 proposed, 29.688 created satır, kısma oranı %44,2.
- [ ] Göztepe için Senaryo 2'deki rakamlar (21.328 adet palet limiti, TIR 4, doluluk %84,6 → %28,6).
- [ ] 23 Kasım All PL'de eksik 4 merkez × kategori yakalanır.
- [ ] Buyaka demirbaş kesimi hata olarak işaretlenmez (sayım).
- [ ] Case picking: kapasite sorunlu depo sayısı 513'te 200 (19.10–18.11); son modelin günlük 4.647 satır kazancı aynı filtrelerle yeniden üretilir.
- [ ] Sharing: 01.10–05.11 verisiyle %100 hedefte 47 depoda MS → Other kaydırma ve toplam kısma 9.301 → 7.528 L/gün yeniden üretilir.
- [ ] Senaryolardaki her cevap önce sonuç, sonra rakam, sonra aksiyon sırasıyla gelir.

**Demo akışı önerisi (5 dk):** dosya yüklenir → Senaryo 1 uyarıları → Senaryo 2 "Göztepe neden?" → Senaryo 3 "Kavacık ne yapalım?" (kaldıraçlar birlikte) → Senaryo 5 haftalık PL listesi.
