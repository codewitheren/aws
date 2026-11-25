# Transfer Agent — Başla Buradan

Getir'in merkez depolarından cep depolara (darkstore) yapılan günlük transferi bir supply chain analisti gibi izleyen, sorun bulan ve öneri veren bir agent yapıyoruz. Bu klasör, agent'ı geliştirecek ekip için iş bilgisini ve veriyi toplar.

## Problem tek paragrafta

Her gün 6 merkez depodan (Maltepe, İzmir, Adana, Arnavutköy, Ankara, Diyarbakır) yaklaşık 513 cep depoya transfer yapılır. Relex sipariş önerir; bizim üç motorumuz (Ambient & Su, +4/Cold, MS) bu öneriyi cep deponun fiziksel kapasitesine ve merkezin limitlerine göre keser. Günde yaklaşık 100 bin satırlık çıktı oluşur. Bugün bu çıktıyı kontrol etmek, "neden kestik?" sorusunu cevaplamak, sharing paylarını, buffer'ları ve gönderim tiplerini (adetli / koli) ayarlamak elle yapılıyor.

## Agent'ın üç işi

| # | Başlık | Ne zaman | Kapsam | Çıktı |
|---|---|---|---|---|
| 1 | **Debugging & Forecast Accuracy** | Anlık: her yeni transfer çıktısında, ve soruldukça | Ambient, +4, MS | Uyarı listesi (kritik / uyarı / bilgi), depo bazlı "neden kıstık", Relex'e gidecek anomali listesi |
| 2 | **Cost Minimizing** (case picking) | Haftalık | Ambient | Depo × ürün gönderim tipi önerisi: adetli / subpackli / kolili / koli ×2 |
| 3 | **Capacity Management** (sharing + buffer) | Haftalık | Cold dolapları (+4 Other, MS +4, ETB) ve depo buffer'ları | Yeni sharing payları, buffer önerileri, ek dolap listesi, beklenen etki |

Agent transfercinin panelde yaptığı koşuyu da üstlenir: girdileri Hackathon - Inputs gsheet'inden alır, üç motoru `kod/` altındaki çalıştırıcıyla koşturur ve çıktıyı analiz eder. Relex'e, Drive'a ve sheet'lere yazmaz; çıktılar yerel klasöre düşer, kullanıcı indirir. Kararı transfer ekibi verir (human in the loop).

**Neden script değil agent:** hesaplar sabit tool'larda kalır, rakamlar güvenilir olur. Agent hangi hesabı ne zaman yapacağına karar verir, birden fazla kaldıracı (sharing, buffer, gönderim tipi, TIR limiti) aynı depo için birlikte tartar, önceliklendirir, açıklar ve uygulanan önerinin sonucunu takip eder.

## Bu klasörde ne var

| Yol | İçerik |
|---|---|
| `docs/00_BASLA_BURADAN.md` | Bu dosya |
| `docs/01_TRANSFER_MOTORLARI.md` | Üç kesim motoru nasıl çalışır, çıktı kolonları, kesinti nedenleri |
| `docs/02_CASE_PICKING.md` | Cost Minimizing: gönderim tipi kuralları, veri, formüller |
| `docs/03_KAPASITE_SHARING_BUFFER.md` | Capacity Management: sharing ve buffer kuralları, veri, simülasyon |
| `docs/04_GIRDI_VERISI.md` | Motor girdileri: Hackathon - Inputs sheet'inin her sekmesi, kolonları, motorun kullanımı, varsayılanlar, koşu öncesi kontroller |
| `docs/05_KOD_VE_CALISTIRMA.md` | Kodun yapısı, `calistir` tool'u, motor akışları, parametreler, çıktılar ve `sonuc.json`, what-if koşuları |
| `kod/` | Çalıştırılabilir kod: `calistir.py`, `gsheet_kaynak.py`, `surucu.py`, `motorlar/`, testler (bkz. `kod/BENIOKU.md`) |
| `Hackathon - Inputs (…)` (sheet) | Motorların tüm girdileri (Relex, backlog, kapasite, buffer, sharing, sayım, kampanya…) |
| `data/inputs/24.11/`, `data/gsheet_kopya_24.11/` | 24.11 İzmir girdileri: orijinal dosyalar ve gsheet'ten indirilmiş kopya (internetsiz test için) |
| `veri_sozlugu.md` | Kolon sözlüğü ve iş formülleri (Kiro steering dosyası olarak kullanılabilir) |
| `Transfer Agent — İş Gereksinimleri.md` | Beklentiler, chat senaryoları, kabul kriterleri |
| `Ambient_Su.py`, `Cold.py`, `MS.py` | Canlıdaki motor kodlarının Colab hâli (23.11.2026, okumak için). Çalıştırılan sürüm `kod/motorlar/` altında |
| `Cold sharing Hackathon` (sheet) | Güncel sharing payları (oran sheet'inin kopyası) |
| `Buffer Rates Hackathon` (sheet) | Güncel depo buffer'ları (Ambient Buffer, Cold Limit) |
| `ornek_veri/` | 23.11 Maltepe gerçek verisinden küçük kesit + beklenen uyarı örneği |
| `data/case_picking/` | Case picking master parquet'leri (tam veri) |
| `data/sharing/` | Sharing için günlük depo × grup doluluk ve kısma tablosu, oran sheet geçmişi, değişiklik kaydı |
| `Copy of Ankara.xlsx` | Bir günlük Ambient motor Excel çıktısı örneği (ana sekme Sheet1) |

Günlük transfer çıktılarının tamamı Drive'da: `Replenishment/Parquet Arşiv/<gg.aa>/<Ambient ve Su | +4 | MS>/<merkez>.parquet` (01.07.2026'dan beri her gün).

## Önerilen okuma sırası

1. Bu dosya
2. `Transfer Agent — İş Gereksinimleri.md` (beklentiler ve chat senaryoları)
3. `docs/01_TRANSFER_MOTORLARI.md`
4. `docs/05_KOD_VE_CALISTIRMA.md` ve `docs/04_GIRDI_VERISI.md` (agent motorları koşturacaksa)
5. İlgili modülün dokümanı (02 veya 03)
6. `veri_sozlugu.md` (geliştirirken referans)

## Demo hikâyesi (5 dk)

1. Bir merkez parquet'i yüklenir → agent otomatik uyarı verir (Debugging).
2. "Göztepe'de neden bu kadar kıstık?" → depo bazlı neden dökümü.
3. "Göztepe için ne yapalım?" → agent kaldıraçları birlikte tartar: TIR limiti (Ambient), buffer ve sharing (Cold).
4. "Bu haftanın case picking önerisi" → PL listesi, satır kazancı, ek hacim, doluluk tahmini.
