# Cost Minimizing — Case Picking (Ambient)

Agent her hafta Ambient'teki her cep depo × ürün için en uygun gönderim tipini önerir. Amaç iki yönlü: sık giden ürünlerde merkezde toplanan satır sayısını (PL, toplama maliyeti) düşürmek; seyrek giden ürünlerde dolu depolarda yer açmak.

## Arka plan

Merkezde toplama maliyeti açılan satır sayısıyla artar (bir depo × ürün siparişi = bir satır). Relex her siparişte en az **batch** (`Order batch size`) kadar önerir. Batch'i koliye çekersek ürün depoya daha seyrek gider, satır azalır; ama depoda daha fazla stok durur. Batch'i küçültürsek tersi olur.

Şu anki dağılım (18.11.2026, sular hariç, 513 depo, 1,36 M depo × ürün): Adetli %24,4 · Subpackli %11,6 · Kolili %64,0.

## Gönderim tipleri

x = batch, koli = koli içi adet (`case_qty`), SP = subpack içi adet (`subpack_qty`; SP > 1 ise geçerli).

| Tip | SP geçerli | SP yok |
|---|---|---|
| Adetli | x < SP | x < koli |
| Subpackli | SP ≤ x < koli | — |
| Kolili | x ≥ koli | x ≥ koli |
| Koli ×k | x = k × koli | x = k × koli |

## Karar: sıklığa göre iki yön

30 günde açılan satır ≈ min(depo sipariş günü sayısı, ⌈30 × günlük satış / batch⌉)

| Durum | Öneri | Kazanım |
|---|---|---|
| Adetli ürün sık gidiyor | Subpack veya koli | Satır azalır |
| Kolili ürün neredeyse her sipariş gününde gidiyor | Koli ×2 / ×3 | Satır azalır |
| Kolili ürün çok seyrek gidiyor (ör. 3 ayda bir), depo dolu | Subpack veya adetli | Yer açılır; satır az artar (ör. 90 günde 1 → 30 günde 1) |
| Koli cover'ı raf ömrünü aşıyor | Subpack veya adetli | Waste riski düşer (depo dolu olmasa da) |

## Filtreler (ekip kuralları)

Yukarı geçiş (adetli → büyük birim) için hepsi sağlanmalı:

- Su hariç; SC depoları (adı " SC" ile biten, 33 depo) hariç; segment Regular / Supply Shortage / Launch.
- Depo kapasite sorunlu değil: son 31 günde 3 günden az hacim kısması **ve** Tableau ortalama doluluk < %95 (`depo_kapasite.kapasite_sorunlu = False`).
- Cover ≤ raf ömrü ve < 180 gün (raf ömrü 0 = SKT takibi yok, kısıt yok).
- Koli / subpack hacmi ≤ 150 L; birim hacim ≤ 2 L.
- Depo tahmini doluluk (dönüşüm sonrası) ≤ %90.

Aşağı geçiş (kolili → küçük birim) için:

- Eklenen satır küçük (parametre; ör. depo × ürün başına ayda en çok 1–2 satır).
- Depo kapasite sorunlu ya da doluluğu yüksek; veya koli cover'ı raf ömrünü aşıyor.
- Hedef tip: subpack geçerli ve subpack cover makulse Subpackli, değilse Adetli.

## Formüller

- **Satır kazancı (günlük)** = (mevcut 30 günlük satır − yeni 30 günlük satır) / 30.
- **Ek stok hacmi (L)** ≈ (yeni sipariş başı adet − mevcut sipariş başı adet) / 2 × birim hacim (döngü stoku). Aşağı geçişte negatif = açılan hacim.
- **Depo tahmini doluluk** = Tableau ortalama doluluk + Σ ek stok hacmi / dolap hacmi.
- **Cover** = birim içi adet (koli / subpack) / günlük ortalama satış.
- **Günlük satış ortalaması:** stoksuz günler (bulunurluk 0) hariç; bulunurluk < %60 olan günlerde satış ×1,5 (kaçan satış düzeltmesi).

**Sıralama:** yukarı geçişte satır kazancı / ek stok (en verimli önce); aşağı geçişte açılan hacim / eklenen satır (en çok yer açıp en az satır ekleyen önce). Tek bir karar fonksiyonu olarak: her depo × ürün için uygun seçenekler içinde satır maliyeti + yer maliyeti en düşük olan seçilir; dolu depoda yer maliyeti daha ağırdır.

## Veri (`data/case_picking/`)

| Dosya | Satır | İçerik |
|---|---|---|
| `son_adaylar.parquet` | 156.700 | Yukarı geçiş aday havuzu, tüm hesaplanmış kolonlarla (satır kazancı, ek hacim, cover, depo doluluğu). Ana tablo. |
| `urun_depo_master.parquet` | 1,36 M | Tüm depo × ürünler: mevcut batch, koli, subpack, flag (Adetli / Subpackli / Kolili). Aşağı geçiş için gerekli. |
| `transfer_siklik.parquet` | 1,06 M | Depo × ürün son 30 gün: öneri gelen gün, gönderilen gün, ortalama öneri. |
| `satis_ortalama.parquet` | 1,15 M | Düzeltilmiş günlük satış ortalaması, bulunurluk. |
| `urun_master.parquet` | 4.978 | Ürün: hacimler, koli / subpack adetleri, raf ömrü, kategori, su mu. |
| `depo_kapasite.parquet` | 513 | Depo: hacim kısma günü, Tableau doluluk, dolap hacmi, kapasite sorunlu mu, nedeni. |
| `depo_master.parquet`, `depo_siparis_gunu.parquet`, `hedef_cover.parquet` | — | Depo bilgileri, depo sipariş günü sayısı, hedef kitle cover'ı. |

Anahtarlar: `warehouse_id`, `product_id` (küçük harf, 24 haneli). Dönem: 19.10–18.11.2026.

## Referans rakamlar (doğrulama için)

- 19.10–18.11: 513 depodan **200'ü kapasite sorunlu**, 313'ü sorunsuz.
- Mevcut son model (20.11.2026, yalnız yukarı yön): 36.528 PL (33.636 kolili, 2.892 subpackli), **günde 4.647 satır kazancı**, adetli oranı %24,5 → %21,3, kalıcı ek stok 13,3 M TL.
- Örnek: Göztepe 767 kolili aday, günde 153,7 satır, 3.260 L ek stok, doluluk %72,8 → %81,2 (aday havuzu, son model öncesi).
- Örnek aşağı geçiş: Kavacık (kapasite sorunlu, Tableau doluluk %128) seyrek giden 15 kolili → yalnız ~69 L açar; tek başına çözüm değil.

## Veri kalitesi uyarıları (agent işaretlemeli)

- `case_volume_ratio` 0,3–4 dışında: koli ölçüsü veya birim ölçüsü hatalı.
- `subpack_ge_case = True`: subpack ≥ koli (ör. Marmarabirlik Yeşil Kokteyl Zeytin: subpack 3.888, koli 24).
- `shelf_life_days = 0`: SKT takibi yok.
- Relex job export'unda ı / ş / ğ / İ silinmiş; eşleştirme her zaman ID ile.
