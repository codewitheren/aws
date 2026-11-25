---
inclusion: always
---
# Veri Sözlüğü — Transfer Kontrol & Case Picking Agent

Kolon adları 23.11.2026 Maltepe parquet'lerinden doğrulandı (Ambient 134, +4 89, MS 47 kolon).
Kaynak: merkez depo kırılımlı günlük parquet'ler
`Parquet Arşiv/<gg.aa>/<Ambient ve Su | +4 | MS>/<merkez>.parquet`
Merkezler: Maltepe, İzmir, Adana, Arnavutköy, Ankara, Diyarbakır (MS'te Diyarbakır yok).
Her dosya = o merkez × kategori koşusunun tüm satırları (depo × ürün). Klasör adında yıl yok.

## 0. Genel kurallar (her analizde uygula)
- Satır anahtarı: `Location code` (cep depo) + `Product code` (ürün). Eşleştirmeyi ID ile yap, ada değil.
- Merkez adı dosya adından gelir. Aynı merkezin ikinci dosyası (`Ankara (1)`) varsa en yeni olanı al.
- **MS'te kolon adları farklı:** öneri `Effective quantity`, final `Final_Quantity`, neden `Trim_Reason`. `Orijinal_Miktar` / `Final_Miktar` / `Kesinti_Nedeni` MS'te YOK.
- **MS dökme (`Is_Bulk = True`) satırlarda miktarlar kg**, diğer her yerde adet. kg ile adeti toplama.
- Yüzde kolonları `(%)` ile bitenler 0–100 ölçeğindedir.
- Su ürünleri (`Is_Water = True`) Ambient dosyasındadır; ayrı segment olarak raporla.
- Demirbaş (`Cut_Priority = 101`) hiç kesilmez. Demirbaşta final < öneri görürsen HATA olarak raporla; tek istisna sayım (`Kesinti_Nedeni = Sayım`).
- Oranlar: `(%)` ile bitenler 0–100; `Total Ambient Ratio (In Transit Included)`, `Uygulanan_Oran`, `Hard_Stop_Orani` 0–1 (veya 1,10 gibi çarpan).

## 1. İş tanımları (formüller — kendin uydurma, bunları kullan)
- Öneri: Ambient/+4 `Orijinal_Miktar`, MS `Effective quantity`.
- Final (gönderilen): Ambient/+4 `Final_Miktar`, MS `Final_Quantity`.
- Kısılan miktar = Σ max(öneri − final, 0), yalnız öneri > 0 satırlar. Fazla gönderim kısmayı düşürmez.
- Kısma oranı = kısılan / Σ öneri.
- Proposed orderline = öneri > 0 satır. Created = final > 0 satır. Silinen = öneri > 0 ve final = 0. Kısılan = 0 < final < öneri. C/P = created / proposed.
- Cover (gün) = (stok + açık sipariş) / günlük satış tahmini. FC = 0 ise sonsuz.
- Neden kovaları:
  - **Backlog**: `Depo Backlog Blokaji` (+4); `G10 Backlog Engeli`, `GB Backlog Engeli`, `Kara Liste` (MS); Ambient'te `Backlog_Kesilen_Miktar` kolonu.
  - **Merkez Satır Limiti**: `Merkez Depo Satir Limiti Asildi`; MS `Merkez Depo 10000 Satır Limiti Sebebiyle Silindi`.
  - **Kesinti yok**: `Islem Gormedi` / boş; MS'te `Effective_Units <= Final_Quantity`.
  - **DS Capacity**: geri kalan her şey (hacim, palet limiti, su alanı, merkez koli limiti, merkez su stoğu, sayım, dikey).
- Merkez satır limitleri: Ambient 10000, +4 6900, MS 10000.
- Öncelik puanı (`Cut_Priority`): düşük olan önce kesilir. 101 demirbaş · 100 kampanya/waste (dokunulmaz, en son) · 99 Listed / Supply Shortage + düşük stok + bulunurluk <%60 (Cold'da Pick-to-zero) · 98/85 A · 97/84 B · 83 düşük stok · 81 C · 1-2 açık satın alma siparişi olan · düşük tek haneler yüksek cover.

## 2. Ambient & Su dosyası — bakılacak kolonlar
| Amaç | Kolonlar |
|---|---|
| Kimlik | `Location code`, `Location name`, `Domain Type` (G10/GB), `Product code`, `Product name`, `Custom category`, `Custom sub-category` |
| Segment / sınıf | `Is_Water`, `Dikey_Elleçleme_Su`, `ABC class`, `Segment` (Regular/Listed/Supply Shortage/Launch…), `Son 14 Günlük Bulunurluk` (0–1) |
| Öneri ve sonuç | `Order batch size`, `Effective quantity`, `Orijinal_Miktar`, `Final_Miktar`, `Kesinti_Nedeni`, `Kesim_Adedi` |
| Öncelik / koruma | `Cut_Priority`, `Dokunulmazlik_Nedeni` (Kampanya/Waste/boş), `Kampanya_Listesi` (T/T-1), `Sadece_A_Test` |
| Stok, tahmin, cover | `End balance` (cep stok), `Open purchase orders` (açık sipariş), `Daily FC` (günlük satış tahmini), `14 Days Sales`, `End Balance DC` (merkez stok), `Calculated Cover Day`, `Kesim_Cover_Basi`, `Kesim_Cover_Sonu`, `Final_Cover_Gun` |
| Hacim / dolap | `hacim2` (birim litre), `Satir_Onerilen_Hacim`, `Avg. ambient_dolap_hacim`, `Hard_Stop_Orani` (depo buffer), `Orijinal_Teslimat_Sonrasi_Doluluk (%)`, `Gelecek_Teslimat_Sonrasi_Doluluk (%)` |
| Palet / TIR / backlog | `SON_calculated`, `palet`, `Mevcut_Palet`, `Final_Palet`, `Tir_Limiti`, `Tir_Limiti_Kaynagi`, `Depo_Orijinal_Palet_Toplami`, `Depo_Final_Palet_Toplami`, `Backlog_Palet_Sayisi`, `Etkili_Backlog_Palet`, `Backlog_Kesilen_Miktar`, `Backlog_Limiti_Asildi`, `Teslimat_Tarihi` |
| Su | `Max_Su_Palet_Kapasitesi`, `Mevcut_Kaplanan_Su_Paleti`, `Net_Su_Stok` |
| Kapanış | `Sayim_Kisiti` (sayım günü depo kapalı) |

## 3. +4 (Cold) dosyası — bakılacak kolonlar
| Amaç | Kolonlar |
|---|---|
| Kimlik | `Location code`, `Location name`, `Domain Type`, `Product code`, `Product name`, `Item_group` (ETB/Other) |
| Segment / sınıf | `ABC class`, `Segment`, `Son 14 Günlük Bulunurluk`, `Pick-to-zero` |
| Öneri ve sonuç | `Order batch size`, `Orijinal_Miktar`, `Final_Miktar`, `Kesinti_Nedeni`, `Geri_Yukleme_Notu` |
| Öncelik / koruma | `Cut_Priority`, `Dokunulmazlik_Nedeni`, `Kampanya_Listesi`, `Sadece_A_Test` |
| Stok, tahmin, cover | `End balance`, `Open purchase orders`, `Daily FC`, `14 Days Sales`, `Calculated Cover Day`, `Reference spoiling time` |
| Kapasite | `Kapasite_Ham_Litre`, `Uygulanan_Oran`, `Uygulanan_Buffer`, `Kapasite_Litre`, `Anlik_Stok_Litre`, `Yoldaki_Transit_Litre`, `Kullanilabilir_Limit_Litre`, `Satir_Onerilen_Hacim`, `Final_Hacim_Litre`, `ETB_` / `Other_Gelecek_Teslimat_Sonrasi_Doluluk (%)`, `ETB_` / `Other_Kesintisiz_Gelecek_Doluluk (%)`, `Doluluk_Tablosunda_Var_Mi` |
| Slot / kapanış | `Slot_Ogle_Oncesi_Biten`, `Sayim_Kisiti` |

## 4. MS (meyve sebze) dosyası — bakılacak kolonlar
| Amaç | Kolonlar |
|---|---|
| Kimlik | `Location code`, `Location name`, `Domain Type`, `Product code`, `Product name`, `Cabinet_Type` (+4 / 8-12 / Ambient), `Is_Bulk` |
| Sınıf | `ABC class`, `Pick-to-zero` |
| Öneri ve sonuç | `Order batch size`, `Effective quantity`, `Effective_Units` (dökmede kasaya yuvarlanmış öneri), `Final_Quantity`, `Trim_Reason` |
| Stok, tahmin, cover | `End balance`, `Open purchase orders`, `Daily FC`, `14 Days Sales`, `End Balance DC`, `Cover_Day_Calc`, `Reference_Spoiling_Time` (raf ömrü) |
| Dolap | `Vol_Per_Unit`, `Allowed_Space`, `Final_Item_Volume`, `Final_Group_Utilization_Pct`, `Son_Doluluk_Pct`, `Doluluk_Tablosunda_Var_Mi` |
| Dökme / PTZ | `Gercek_Kasa_Kilo`, `BULK_Kasa_Adedi`, `BULK_Final_Kasa`, `BULK_Final_Kilo`, `BULK_Verilen_Kasa`, `BULK_Telafi_Kasa`, `BULK_Sifirlama_Kilo`, `PTZ_Eklenen_Adet` |
| Kapanış | `Backlog`, `Sayim_Bilgisi` |
Not: MS'te nedeni "Onaylandi" olup final ≠ öneri satırlar normaldir (dökme kasa yuvarlaması, PTZ, telafi).

## 5. Görevler ve kullanacağı kolonlar
1. **Koşu bütünlüğü:** her merkez × kategori dosyası var mı; merkez başına dosya sayısı; depo kümesi başka merkezle %50+ örtüşüyor mu (yanlış adla kayıt); demirbaşta kesim var mı.
2. **Kısma KPI:** merkez × kategori × neden kovası; öneri, final, neden kolonları. Dünle kıyas (aynı dosyanın önceki günü).
3. **Merkez limitleri:** created orderline sayısı vs limit; limit nedenli silinen satır.
4. **Depo sinyalleri:** hacim nedeniyle kısılan depolar ve doluluk %; TIR limitinden kısılıp hacmi dolmayan depolar (`Final_Palet` toplamı ≈ `Tir_Limiti` − `Etkili_Backlog_Palet` ve doluluk düşük); `Backlog_Limiti_Asildi`; sayımla kapanan depolar.
5. **Ürün sinyalleri:** A sınıfı / `Segment` Listed-Supply Shortage / `Dokunulmazlik_Nedeni` dolu satırların kesilmesi; aynı ürünün çok depoda silinmesi + `End Balance DC` düşük.
6. **Relex öneri kalitesi:** öneri > 1 batch ve (öneri > `14 Days Sales` veya öneri hacmi > dolap × eşik); `Daily FC` = 0 ama öneri > 0; (stok + açık sipariş + öneri) aynı ürünün diğer depolarının medyanının çok üstünde.
7. **Satır açıklaması ("neden kesildi?"):** `Cut_Priority`, cover kolonları, neden, ilgili limit/doluluk kolonları.

## 6. Case Picking — master dosyaları (`Case Picking/master/`)
Amaç: her depo × ürün için **en uygun gönderim tipini** seçmek: Adetli, Subpackli, Kolili veya Koli ×k. Karar iki yönlüdür:
- **Yukarı** (adetli → subpack / koli / koli ×k): sıklık düşer, satır kazanılır; kapasite, raf ömrü ve hacim izin veriyorsa.
- **Aşağı** (kolili → subpack / adetli): satır kazancı yoksa ya da düşükse, kolili olmak yalnızca yer kaplar; geri al.
Karar **sıklığa** göre verilir: 30 günde satır sayısı ≈ min(depo sipariş günü sayısı, ⌈toplam talep / batch⌉).

**Flag kuralı** (x = batch, koli = `case_qty`, SP = `subpack_qty`; SP > 1 ise geçerli):
SP geçerli → Adetli x < SP · Subpackli SP ≤ x < koli · Kolili x ≥ koli. SP yok → Adetli x < koli · Kolili x ≥ koli.

| Dosya | Satır | Ne için | Ana kolonlar |
|---|---|---|---|
| `son_adaylar.parquet` | ~157 bin aday depo×ürün | **Ana tablo: öneri üret, sırala, açıkla** | `Karar`, `Merkez`, `Depo Tipi`, `Depo`, `Depo ID`, `Ürün ID`, `Ürün`, `Kategori`, `ABC`, `Segment`, `Mevcut Batch Size`, `Subpack İçi Adet`, `Koli İçi Adet`, `Birim Hacim (L)`, `Subpack Hacmi (L)`, `Koli Hacmi (L)`, `Raf Ömrü (gün)`, `Ort. Günlük Satış`, `Subpack Cover (gün)`, `Koli Cover (gün)`, `Öneri Gelen Gün`, `Subpack OK`, `Koli OK`, `Dönüşüm Durumu`, `Subpack: Satır Kazancı (günlük)`, `Koli: Satır Kazancı (günlük)`, `Subpack: Ort. Ek Stok Hacmi (L)`, `Koli: Ort. Ek Stok Hacmi (L)`, `Depo Ort. Doluluk (yoldaki dahil)`, `Depo Dolap Hacmi (L)`, `Depo Hacim Kısma Günü` |
| `depo_kapasite.parquet` | 513 depo | Kapasite sorunlu depo filtresi | `warehouse_id`, `merkez`, `location_name`, `hacim_kisma_gunu`, `tableau_ort_doluluk`, `dolap_hacmi_l`, `kapasite_sorunlu`, `sorun_nedeni` |
| `urun_master.parquet` | 4.978 ürün | Ürün özellikleri, veri kalitesi | `product_id`, `product_name`, `category`, `brand`, `is_water`, `unit_volume_l`, `case_qty`, `case_volume_l`, `case_volume_ratio`, `case_volume_source`, `subpack_qty`, `subpack_valid`, `subpack_ge_case`, `shelf_life_days`, `pallet_qty` |
| `urun_depo_master.parquet` | 1,36 M | Tüm depo×ürün mevcut flag dağılımı | `warehouse_id`, `product_id`, `abc_class`, `relex_segment`, `order_batch_size`, `case_qty`, `subpack_qty`, `flag` |
| `transfer_siklik.parquet` | 1,06 M | Ne sıklıkla öneri/gönderim var (kazanç hesabı) | `oneri_gun`, `gonderim_gun`, `oneri_toplam`, `final_toplam`, `ort_oneri`, `oneri_orani` |
| `satis_ortalama.parquet` | 1,15 M | Düzeltilmiş günlük satış | `ort_satis`, `ort_satis_ham`, `ort_bulunurluk`, `stoksuz_gun` |

**Öneri filtreleri (ekip kuralları):** su hariç; SC depoları hariç; `kapasite_sorunlu = False` (≥3 gün hacim kısması veya Tableau ort. doluluk ≥ %95 → sorunlu); cover ≤ raf ömrü ve < 180 gün (`shelf_life_days = 0` → SKT takibi yok, kısıt yok); koli/subpack hacmi ≤ 150 L; birim hacim ≤ 2 L; depo tahmini doluluk ≤ %90.
**Sıralama:** günlük satır kazancı / ek stok (hacim veya TL) — en verimli önce.
**Veri kalitesi uyarıları:** `case_volume_ratio` 0,3–4 dışında (ölçü hatası), `subpack_ge_case = True`, `shelf_life_days = 0`.
**Koli katı (×2, ×3):** kolili üründe batch = k × koli; kazanç ve cover'ı k için yeniden hesapla, aynı filtreler.

**İki uç durum (sıklığa göre):**
- **Çok sık gidiyor → yukarı (koli ×2, ×3):** kolili ürün neredeyse her sipariş gününde gidiyorsa (`oneri_gun` ≈ `depo_siparis_gunu`) batch'i koli katına çıkar → satır azalır. Kapasite, raf ömrü, hacim filtreleri aynen.
- **Çok seyrek gidiyor → aşağı (kolili → subpackli / adetli) = kapasite kazanımı:** kolili ürün çok seyrek gidiyorsa (ör. 3 ayda bir; koli cover çok yüksek) küçük birime çevir. Satır az artar (ör. 90 günde 1 → 30 günde 1), ama depoda bir koli yerine küçük miktar durur → **yer açılır**. Özellikle **kapasitesi dolu depolarda** (Ambient'te `kapasite_sorunlu = True` / yüksek doluluk) öner.

**Aşağı yönlü öneri detayı:**
- Veri: `urun_depo_master` (mevcut `flag`, `order_batch_size`), `transfer_siklik` (`oneri_gun`, `gonderim_gun`, `ort_oneri`, `depo_siparis_gunu`), `satis_ortalama` (`ort_satis`), `urun_master` (birim / subpack / koli hacmi, raf ömrü), `depo_kapasite`.
- Yeni tipte 30 günlük satır ≈ min(depo sipariş günü, ⌈30 × `ort_satis` / yeni batch⌉). **Eklenen satır** = yeni − mevcut.
- **Açılan hacim** ≈ (mevcut sipariş başı adet − yeni sipariş başı adet) / 2 × birim hacim (döngü stoku).
- Koşul: eklenen satır küçük (eşik parametre, ör. depo × ürün başına ayda ≤ 1–2 satır) ve depo kapasite sorunlu / doluluk yüksek. Koli cover > raf ömrü ise (waste riski) depo dolu olmasa da öner.
- Hedef tip: subpack cover makul ve subpack geçerliyse Subpackli, değilse Adetli.
- Sıralama: açılan hacim (L) / eklenen günlük satır — en çok yer açıp en az satır ekleyen önce. Depo bazında toplam açılan hacim ve yeni tahmini doluluk %'si raporlanır.

**Tek karar fonksiyonu (önerilen):** her depo × ürün için Adetli, Subpackli, Kolili, Koli ×2 seçeneklerini hesapla: günlük satır sayısı, ort. ek stok hacmi (≈ sipariş başı adet / 2 × birim hacim), cover, raf ömrü uygunluğu, depo tahmini doluluk. Uygun seçenekler içinde satır maliyeti + yer maliyeti toplamı en düşük olanı seç; yer maliyeti kapasite sorunlu ya da dolu depoda daha ağır. Mevcut tipten farklıysa öneri üret (yön: yukarı / aşağı).

## 7. Capacity Management — sharing ve buffer
Ayrıntı: `docs/03_KAPASITE_SHARING_BUFFER.md`.

**Kapasite (L) = havuz × sharing payı × buffer.** Doluluk = ortalama ihtiyaç / ortalama kapasite (> 1 = dolu). İhtiyaç = teslimatta dolu + öneri hacmi.

| Kaynak | Kolonlar | Not |
|---|---|---|
| "Cold sharing Hackathon" sheet'i | `Depo Adı`, `Other+4`, `MS+4`, `MS+8+12`, `Taze Et`, `Şarküteri ve Merkezden Giden ETB` | G10: Other+4 + MS+4 = 1, Taze Et + ETB = 1. GB: dört kalem toplamı ≈ 1 (tek havuz). |
| "Buffer Rates Hackathon" sheet'i | `Depo Adı`, `Ambient Buffer`, ` Cold Limit` (başında boşluk) | Değerler "110%" metni → 1,10. Sheet'te olmayan depo: 1,10. |
| `data/sharing/sharing_gunluk_01.10-15.11.parquet` | `Tarih`, `Gun`, `HaftaGunu` (0 = Pzt), `Merkez`, `Depo`, `Grup` (Other / MS), `Havuz`, `Oran`, `Buffer`, `Kapasite`, `Dolu`, `Oneri`, `Final`, `Ihtiyac`, `Oneri_L`, `KapKes_L`, `KisGun`, `Veri_Sorunlu_Gun` | Litre bazında, G10, +4 odası. `Veri_Sorunlu_Gun = True` satırları analize katma. |
| Cold parquet (günlük) | `Item_group`, `Kapasite_Ham_Litre`, `Uygulanan_Oran`, `Uygulanan_Buffer`, `Kapasite_Litre`, `Anlik_Stok_Litre`, `Yoldaki_Transit_Litre`, `ETB_` / `Other_Kesintisiz_Gelecek_Doluluk (%)` | Daha güncel günler için. Kapasite kısması: `Kesinti_Nedeni` = `Kapasite Zorlamasi (Other Limiti) - Kisildi` / `(ETB Limiti)`, kesilen L = (Orijinal − Final) × `hacim2`. |
| MS parquet (günlük) | `Cabinet_Type`, `Allowed_Space`, `Son_Doluluk_Pct`, `Final_Group_Utilization_Pct`, `Vol_Per_Unit` | Kısma: `Trim_Reason` ∈ {`Dolap Kapasite Yetersizligi Sebebiyle Kisildi/Silindi`, `Kapasite Yok (0)`, `Bosa Cikan Hacimle Kismen Geri Yuklendi`}. |
| Ambient parquet (buffer için) | `Hard_Stop_Orani` (uygulanan Ambient buffer), `Total Ambient Ratio (In Transit Included)` (gerçek doluluk, 0–1), `Avg. ambient_dolap_hacim` | |

**Depo tipi:** her zaman `Domain Type` (adda "Büyük" geçmesi GB demek değildir).
**Kaldıraç sırası:** sharing → buffer (5 puan adımlarla) → ek dolap.
