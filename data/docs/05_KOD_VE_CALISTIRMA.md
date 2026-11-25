# Kod ve Çalıştırma — agent motorları nasıl koşturur, çıktıyı nasıl okur

Agent, transfercinin panelde yaptığı işi üstlenir. Akış şöyledir: girdileri Hackathon - Inputs gsheet'inden alır, üç
motoru çalıştırır, çıktıyı analiz eder, öneri verir. Bu doküman kodun yapısını, motorların adım adım ne yaptığını,
parametreleri ve çıktıların nasıl okunacağını anlatır. Girdiler için `04_GIRDI_VERISI.md`, iş kuralları ve kolon
sözlüğü için `01_TRANSFER_MOTORLARI.md` ve `veri_sozlugu.md`.

## 1. Mimari

```
Hackathon - Inputs (gsheet)
   │  CSV (sheet sekmeleri) + tek sekme xlsx (Relex, Backlog, Water, Kasa)
   ▼
gsheet_kaynak.py ──► <çıktı>/<tarih>/<urun>/sheets/<gid>, in/<rol>.xlsx
   ▼
calistir.py  ──►  surucu.py  ──►  motorlar/<Ambient_Su|Cold|MS>.py   (exec, parametreler enjekte edilir)
   ▼
out/<merkez>.xlsx · out/<merkez>.parquet · allpl/<gün Ay> All PL.* · sonuc.json
   ▼
Agent: sonuc.json + parquet'i okur → uyarı, "neden kıstık", öneri, what-if
```

| Dosya (`hackathon/kod/`) | Görev |
|---|---|
| `calistir.py` | Giriş noktası. Komut satırı ve `calistir()` fonksiyonu. Ortam kontrolü, parametre birleştirme, sonuç özeti |
| `gsheet_kaynak.py` | Sekme ve gid tablosu, indirme (anonim ya da servis hesabıyla), yerel kopya |
| `surucu.py` | Panelin (Sevk_Planlama.html) sürücüsü. Motor kodunu çalıştırır, gspread ve Colab'ı yerel dosyalarla taklit eder, parametreleri enjekte eder, Excel / parquet / All PL yazar, panel ekranındaki özet ve kontrolleri (`sonuc.json`) üretir |
| `motorlar/*.py` | Canlıdaki kesim motorları. Hesap kısmı canlıyla aynı; yalnız Drive'a kayıt bölümü çıkarıldı |
| `testler/test_karsilastir.py` | Gsheet yoluyla eski yolu (orijinal dosyalar) hücre hücre karşılaştırır |
| `requirements.txt` | pandas 2.2.3, numpy 1.26.4, openpyxl, pyarrow. **pandas 3 desteklenmez** |

**Önemli tasarım kararı:** motor kodu bir kütüphane değil, baştan sona çalışan bir script'tir (Colab'dan gelir).
Sürücü motoru `exec` ile çalıştırır. Koddaki parametre atamalarını (`MAX_SATIR_LIMITI = 10000` gibi) verilen değerlerle
değiştirir. `pd.Timestamp.now()` çağrılarını koşu tarihinin saat 12:00'sine bağlar. Bu yüzden:

- Motor fonksiyonları tek tek çağrılmaz. Her zaman motorun tamamı koşar (Ambient ~10 sn, Cold ~5 sn, MS ~4 sn).
- Değiştirilebilen şeyler: parametreler (`param=`), sheet değerleri (yerel kopya üzerinden) ve koşu tarihi.

## 2. Agent tool'u: `calistir`

```python
from calistir import calistir
s = calistir(urun, tarih=None, cikti='ciktilar', param=None, merkez=None, kaynak='gsheet', sessiz=False)
```

| Argüman | Değer |
|---|---|
| `urun` | `'ambient'`, `'cold'`, `'ms'` |
| `tarih` | `'YYYY-MM-DD'`. Motorun "bugünü" budur: TIR günü, sayım aralığı, kampanya T/T-1, lead time. Boşsa bugün (İstanbul) |
| `param` | Değiştirilecek parametreler, ör. `{'MAX_SATIR_LIMITI': 12000}`. Bilinmeyen ad hata verir |
| `merkez` | Merkez otomatik tanınmazsa çıktı adı |
| `kaynak` | `'gsheet'` (canlı indir) ya da `'yerel:<klasör>'` (önceden indirilmiş / değiştirilmiş kopya) |

Dönüş (`dict`):

| Anahtar | İçerik |
|---|---|
| `ok`, `hata` | Başarı. Parquet yazılamazsa da `ok=False` olur |
| `merkez` | Tespit edilen merkez (ör. `İzmir`) |
| `excel`, `parquet` | Çıktı dosya yolları |
| `allpl_parquet`, `allpl_xlsx`, `allpl_satir` | Bu koşunun All PL'si |
| `ozet`, `kontrol` | Panel ekranındaki özet ve kontrol listesi. `kpi`, `depo_tablo`, `oneri` ve `detay` yalnız `sonuc.json`'da (bölüm 5) |
| `klasor` | Koşu klasörü; `sonuc.json` burada |
| `sure_sn` | İndirme ve motor süresi |

Komut satırı: `python calistir.py ambient|cold|ms|hepsi [--tarih] [--param JSON] [--merkez] [--kaynak]`,
`python calistir.py parametreler`, `python calistir.py indir --klasor <klasör>`.

**Agent kuralları**

- Motor rakamları resmidir. Kısılan miktar, doluluk ve neden gibi değerleri agent kendi yeniden hesaplamaz;
  parquet / `sonuc.json`'dan okur.
- Kod Drive'a, Relex'e ya da sheet'e yazmaz. Çıktılar yalnız yerel klasöre gider; kullanıcı indirir.
- Her koşu `ciktilar/<tarih>/<urun>/` klasörünü **siler ve yeniden yazar** (`out/` içi). What-if koşuları ayrı bir
  `cikti` klasörüne yazılmalı (bkz. bölüm 6).

## 3. Motor akışları

Üç motorun ortak iskeleti aynıdır:

1. Girdileri oku ve birleştir.
2. Her satıra öncelik puanı ver (`Cut_Priority`).
3. Kısıtları sırayla uygula: kesim düşük puandan başlar, aynı puanda cover'ı yüksek olandan; her adım bir sipariş katı.
4. Boşalan kapasiteye geri yükle.
5. Raporla.

Puan tablosu ve neden metinleri `01_TRANSFER_MOTORLARI.md`'de. Aşağıda koddaki sıra ve bölüm başlıkları var; kodda bu
başlıkları arayarak ilgili yere gidilebilir.

### 3.1 Ambient & Su (`Ambient_Su.py`, ~2.400 satır)

| Bölüm (koddaki başlık) | Ne yapar |
|---|---|
| `0. KULLANICI PARAMETRELERİ`, `1. AYARLAR` | Limitler ve listeler; dikey elleçleme test depoları, su → ambient geçişi, weighted-ava depoları, sayım kuralları |
| `2. VERİ OKUMA` | Relex, Sim, volume_format, ambient_format, Depo Palet Limitleri (bugünün kolonu), teslimat programı, sayım planı, fast acceptance, kampanya, dünkü backlog, Water WH, su palet bilgileri, su palet alanı, Buffer Rates |
| `SU → AMBIENT GEÇİŞİ`, `EKSİK SU SATIRLARI`, `YUMURTA ABC` | Özel düzeltmeler: 7 depoda 2 su ürünü ambient sayılır; Relex'te olmayan su satırları raporlanır |
| `3. LOJİSTİK HESAPLAMALAR` | Cover; palet (ambient: adet / (SON × 50), su: adet / palet); lead time; boşalacak hacim; kalan net hacim; buffer (`Hard_Stop_Orani`); TIR limiti ve kaynağı; etkili backlog; su net stoğu ve kaplanan su paleti |
| `SAYIM KISITI` | Teslimat günü sayım aralığına düşen depo → hepsi 0 (`Sayım`). "Sadece A testi" depolarında A dışı 0 |
| `4. ÖNCELİKLENDİRME` | `priority_score`: 101 demirbaş, 100 kampanya/waste, 99 Listed / Supply Shortage, 98/85 A, 97/84 B, 83 düşük stok, 81 C, 1–19 diğer |
| `5.0 DİKEY ELLEÇLEME` | Test depolarında su paletlerinin dikey yerleşimi |
| `5. OPTİMİZASYON` | Sırayla: **5.1 hacim** (depo öneri hacmi > dolap × buffer − (dolu + yoldaki − boşalacak)) → **5.1.5 su palet alanı** → **5.2 TIR palet limiti** (etkili backlog düşülerek; backlog yüzünden kesilen adet `Backlog_Kesilen_Miktar`) → **5.3 merkez satır limiti** → **5.4 merkez koli limiti** |
| `5.5 GERİ YÜKLEME` | Tüm kısıtlar altında boşluk kalan depolara kesilenleri geri ekler (yüksek puan önce, eşitlikte düşük cover) |
| `5.6 MERKEZ SU STOK MUTABAKATI` | Su toplamı merkez stoğunu (`End Balance DC`) aşarsa keser |
| `6. RAPORLAMA` | Depo özeti, kesinti raporu, layout / dikey kontrol sekmeleri |

### 3.2 Cold +4 (`Cold.py`, ~1.500 satır)

| Bölüm | Ne yapar |
|---|---|
| `1. AYARLAR`, `SAYIM KURALLARI` | Limitler, varsayılan paylar, dokunulmaz (waste) listeleri, sayım aralıkları |
| `DOSYALARI YÜKLE` | Relex, backlog, Buffer (`Cold Limit`), Sharing (`Other+4`, ETB), +4 New (pivot), Slot, Product Volume (`Max. Product Volume m3`), Kampanya |
| `SLOT BAYRAĞI` | 12:00 öncesi biten slot → ertesi gün tahmin düşüşü 0 |
| `GRUPLAMA` | `Et, Tavuk & Balık` → ETB, diğerleri Other |
| `KAPASİTE LİMİT HESAPLAMA` | `calculate_group_limits_yeni`: kapasite = havuz × pay × buffer; kullanılabilir = kapasite − (dolu + yoldaki − boşalacak). G10 ve `G10_TIPI_DEPOLAR` için ETB ayrı odadan, GB'de ortak havuzdan |
| `ÖNCELİKLENDİRME` | Ambient'e benzer puanlar; Pick-to-zero 99 |
| `ORTAK OPTİMİZASYON PIPELINE'I` | **Backlog** (G10 ≥ 1, GB > 2 → depo kapalı) → **sayım** → **Sadece A testi** → **hacim** (depo × grup, düşük puandan, grup içinde round-robin birer batch) → **merkez satır limiti** (6.900) → **hacim geri yükleme** → **depo adet limiti** (`DEPO_ADET_LIMITI`) |
| `KAPASİTE DETAYI`, `SLOT & LOOKAHEAD`, `DEBUG SHEET`, `TRANSFER SHEET` | Rapor sekmeleri. Debug sekmesi veri kalitesi kurallarını işletir |

### 3.3 MS (`MS.py`, ~1.650 satır)

| Bölüm | Ne yapar |
|---|---|
| `1. PARAMETRELER`, `SAYIM KURALLARI` | Satır limiti, T1 faktörü, varsayılan paylar, kara liste, adet limiti |
| `2. DOSYALARIN OKUNMASI` | Relex, backlog, kasa kilo, Buffer (`Cold Limit`), Sharing (`MS+4`, `MS+8+12`), volume_format (hacim), Product Volume (saklama tipi), Slot, +4 New |
| `3. CABINET TYPE, BULK` | `Transfer type = BULK` → dökme (kg). Saklama tipine göre dolap: 8-12 / +4 / Ambient (Ambient kısıt dışı). Cover |
| `3.4 SAYIM`, `3.5 BULK ROUND-ROBIN` | Sayım kapanışı; dökme ürünlerin kasalara bölünüp depolara dağıtımı (merkez stoğu sınırı) |
| `4. KAPASİTE` | +4: havuz × `ms4_oran` × buffer; 8-12: havuz × `ms812_oran` × buffer; dolu + yoldaki − (frc t + frc t+1 × T1) |
| `5. BAŞLANGIÇ BLOKAJLAR` | Kara liste, backlog (G10 > 0, GB ≥ 5) |
| `6. DOLAP BAZINDA HACİM KISMA` → `7A. RESTORASYON` | Dolap aşılırsa C → B → A sırasıyla kes, sonra geri yükle |
| `7. SATIR LİMİTİ` → `8. RESTORASYON` | Merkez 10.000 satır |
| `9. PTZ`, `9.6 BULK SIFIRLAMA VE TELAFİ`, `9.65 ADET LİMİTİ` | Pick-to-zero dağıtımı (raf ömrü sınırı), dökme telafi, depo adet limiti |
| `10–11. ANALİZ VE EXCEL` | Ana Cikti, Kapasite Detayi, Merkez Stok Analizi, BULK Panel Cikti |

MS'te kolon adları farklıdır (`Effective quantity` / `Final_Quantity` / `Trim_Reason`) ve dökmede birim kg'dır.

## 4. Parametreler

`python calistir.py parametreler` tam listeyi değerleriyle verir. En çok kullanılanlar:

| Parametre | Motor | Varsayılan | Anlam |
|---|---|---|---|
| `MAX_SATIR_LIMITI` | Ambient | 10.000 | Merkez satır limiti |
| `MAX_KOLI_LIMITI` | Ambient | 20.000 | Merkez koli limiti |
| `HARD_STOP_CAPACITY` | Ambient | 1,10 | Buffer Rates'te olmayan depoların buffer'ı |
| `PALETIN_YUZDE_KACI` | Ambient | 0,35 | Su paleti, bu oranın üstünde doluysa tam palet sayılır |
| `G10_COVER_DAY_LIMIT` / `GB_COVER_DAY_LIMIT` | Ambient 4 / 6 · Cold 2,5 / 4 | | "Yüksek cover" eşiği (puan 1–19 içinde sıralama) |
| `A_MIN_COVER` / `B_MIN_COVER` / `C_MIN_COVER` | Ambient 6,5 / 7,5 / 3 · Cold 5,5 / 7,5 / 2 | | Bu cover'ın altındaki A / B / C korunur (98 / 97 / 81) |
| `DOKUNULMAYACAK_URUNLER_G10/GB` | Ambient | liste | Waste listesi (100 puan) |
| `SADECE_A_TEST_DEPOLARI` | hepsi | `['Atakent']` | Yalnız A sınıfı giden test depoları |
| `MAX_SATIR_LIMITI_YENI` | Cold | 6.900 | Merkez satır limiti |
| `PLUS_4_USABLE_RATIO` | Cold, MS | 1,10 | Buffer Rates'te olmayan depoların buffer'ı |
| `FORECAST_LOOKAHEAD_RATIO` / `T1_FACTOR` | Cold / MS | 1/3 | Teslim sonrası günün tahmin düşüşünden kapasiteye eklenen pay |
| `G10_DEFAULT_OTHER4_ORAN`, `G10_DEFAULT_ETB_ORAN`, `GB_DEFAULT_*` | Cold | 0,81 / 0,76 / 0,69 / 0,08 | Sharing sheet'inde olmayan depoların payları |
| `DOKUNULMAYACAK_G10/GB` | Cold | liste | Waste listesi |
| `G10_TIPI_DEPOLAR` | Cold | Gaziemir, Suadiye Büyük | GB ama ETB odası ayrı (G10 gibi) |
| `DEPO_ADET_LIMITI` | Cold, MS | `{'Acıbadem Büyük': …}` | Depo başına toplam adet tavanı |
| `MAX_ROWS` | MS | 10.000 | Merkez satır limiti |
| `MS4_DEFAULT_G10/GB`, `MS812_DEFAULT` | MS | 0,19 / 0,15 / 1,0 | Varsayılan MS payları |
| `DEFAULT_SPOILING_TIME` | MS | 5 | Raf ömrü boşsa kullanılan gün |
| `BLACKLISTED_DEPOTS` | MS | `[]` | Kara listedeki depolar (hiç gönderilmez) |

Depo bazlı buffer, sharing payı ve TIR limiti **parametre değil, sheet değeridir**. Bunları denemek için bölüm 6'daki
yerel kopya yöntemi kullanılır.

## 5. Çıktılar

Koşu klasörü: `ciktilar/<tarih>/<ambient|cold|ms>/`

| Dosya | İçerik |
|---|---|
| `out/<merkez>.xlsx` | Panelden inen Excel. Ambient: Sheet1 (ana tablo), Depo Ozet Karnesi, Detayli Kesinti Raporu, Layout Uyum Kontrol, Dikey Palet Kontrol, Dikey Ellecleme Ozet, Su DC Mutabakat, Sayim Kisiti, Su-Ambient Gecis, Eksik Su Satirlari, Eksik Su Depo Ozet. Cold: Sheet1, Transfer, Depo Ozet Karnesi, Kapasite Detayi, Slot Lookahead Kontrol, Sayim Kisiti, Debug Ozet, Debug Detay. MS: Ana Cikti, Kapasite Detayi, Merkez Stok Analizi, BULK Panel Cikti, Sayim Kisiti |
| `out/<merkez>.parquet` | Ana tablonun tamamı (Ambient 134, Cold 89, MS 47 kolon). Canlıda Parquet Arşiv'e giden dosyanın aynısı. Kolonlar için `veri_sozlugu.md` |
| `allpl/<gün Ay> All PL.parquet/.xlsx` | Bu koşunun siparişli satırları, 25 sabit kolon: tarih, kategori, bolge, depo, ürün, relex_oneri, final_miktar, kesilen_miktar, kesinti_nedeni, final_hacim_litre, backlog ve palet kolonları |
| `sonuc.json` | Panel ekranının verisi (aşağıda) + `log` (motorun çıktısı) + `calistir` (özet) |
| `sheets/`, `in/` | Bu koşunun girdileri (denetim için) |

### `sonuc.json`: agent'ın birincil analiz girdisi

| Anahtar | Yapı | Kullanım |
|---|---|---|
| `kpi` | `[{ad, deger, birim}]` | Üst özet: kesinti oranı, kesilen, kesinti olan depo, sevk hacmi / palet, koli |
| `kontrol` | `[{grup, ad, durum: ok/bilgi/uyari/hata, ozet, aciklama, kolonlar, satirlar}]` | Veri kaynağı eşleşmesi, merkez limitleri, veri kalitesi, log uyarıları. **Debugging'in hazır girdisi** |
| `ozet.nedenler` | `[{ad, depo, kes, pay}]` | Neden kovalarına göre kesilen miktar ve payı |
| `ozet.ekKartlar` | `[{baslik, alt, ozet, tablo}]` | Ör. Ambient "Paletten kısılan ama hacmi dolmayan depolar" (TIR limitini artırma adayı) |
| `depo_tablo` | `{kolonlar, satirlar}` | Depo bazında öneri, final, kesilen, kesinti %, ana neden, doluluk %, TIR yükü / limiti. **"Neden kıstık?" cevabının özeti** |
| `oneri.kartlar` | 3 kart: Büyük öneriler (hacim / 14 gün satış), Fazla stok şüphesi, Satış tahmini 0 ama öneri var | **Forecast accuracy uyarıları**, satır listeleriyle |
| `detay` | `{kolonlar, satirlar, depolar}` | Satır detayı (depo filtreli inceleme için) |
| `merkez` | `{ad, kaynak, pay, ...}` | Merkez tespiti ve güveni |

Örnek (24.11 Ambient İzmir): `ozet.nedenler` → TIR palet limiti 25.162 adet (%67, 4 depo), su palet alanı 6.264
(%17), dolap hacmi 5.888 (%16). `depo_tablo`'nun ilk satırı: ÇamlıkuleBüyük GB, öneri 16.342 → 1.348, %91,8,
TIR palet limiti, doluluk %55,9, TIR 15/15. Yani depoda yer var, TIR limiti kısıyor: agent'ın önereceği kaldıraç
TIR limitidir.

## 6. What-if: değişiklik yapıp yeniden koşturma

Agent bir öneri verdiğinde (buffer artır, sharing kaydır, limit değiştir), etkisini motoru yeniden koşturarak
gösterebilir. İki yol var:

**a) Parametre değişikliği**

```python
once  = calistir('ambient', '2026-11-24', cikti='wi/once')
sonra = calistir('ambient', '2026-11-24', cikti='wi/sonra', param={'MAX_SATIR_LIMITI': 12000})
```

**b) Sheet değeri değişikliği** (depo buffer'ı, sharing payı, TIR limiti, kampanya listesi). Girdiler bir kez yerel
kopyaya indirilir, kopyada ilgili hücre değiştirilir, iki kopya ayrı ayrı koşturulur:

```python
import gsheet_kaynak as gk, shutil, pandas as pd
gk.yerel_kopya_al('snap', urunler=('cold',))            # bugünün girdileri
shutil.copytree('snap', 'snap_wi')
yol = 'snap_wi/sheets/1173976478'                        # Buffer Rates (CSV, gid adlı dosya)
t = open(yol, encoding='utf-8').read().replace('Bir Eylül,110%,110%', 'Bir Eylül,110%,120%')
open(yol, 'w', encoding='utf-8').write(t)
a = calistir('cold', '2026-11-24', cikti='wi/once',  kaynak='yerel:snap')
b = calistir('cold', '2026-11-24', cikti='wi/sonra', kaynak='yerel:snap_wi')
```

24.11 İzmir'de denendi: Bir Eylül'ün `Cold Limit`'i %110 → %120 olunca final 997 → 1.178 adet oldu
(öneri 1.407); merkez toplamı 26.710 → 26.891.

Sheet dosyaları gsheet'in CSV dışa aktarımıdır. Biçimi korumak gerekir: yüzde `120%`, ondalık nokta. Sharing ve TIR
sekmelerinde de aynı yöntem geçerlidir. Gerçek sheet'e yazmak transfer ekibinin işidir.

## 7. Hatalar ve çözümleri

| Belirti | Neden | Çözüm |
|---|---|---|
| `pandas 3.x kurulu; motorlar pandas 2.x ister` | Yanlış ortam | `pip install -r requirements.txt` (Python 3.11 / 3.12) |
| `Sheet indirilemedi (HTTP 401/403)` ya da "CSV yerine HTML geldi" | Sheet herkese açık değil | Bağlantı paylaşımını aç ya da `GOOGLE_APPLICATION_CREDENTIALS` ile servis hesabı ver |
| `Dosyada beklenen kolon bulunamadı: X` | Elle sekmeye yanlış dosya yapıştırılmış | Sekmeyi doğru raporla değiştir (kolon adları bölüm 3'te, `04_GIRDI_VERISI.md`) |
| Merkez `Merkez tanınmadı` | Relex depoları haritayla %90 eşleşmiyor | `merkez='Maltepe'` ver; Relex'in doğru merkez olduğunu kontrol et |
| `kontrol` içinde çok sayıda "… olmayan depolar" | Sheet'te depo adı farklı yazılmış ya da eksik | Sheet'e depoyu ekle; o zamana kadar varsayılan değer kullanılır |
| Koşu başarılı ama kesinti beklenenden çok düşük | `+4 New` / `ambient_format` boş ya da eski → hacim kısıtı uygulanmadı | `kontrol` → "Kapasite verisi olmayan depolar" sayısına bak |

## 8. Test

`python testler/test_karsilastir.py --snap ../data/gsheet_kopya_24.11 --orj ../data/inputs/24.11 --tarih 2026-11-24`

Aynı gün için iki koşu yapar: gsheet yolu ve eski yol (transfercinin yüklediği orijinal dosyalar). Her Excel sekmesini
ve parquet'i hücre hücre karşılaştırır. Son sonuç üç motorda da birebir aynı (`testler/test_raporu_24.11.txt`). Motor
ya da girdi kodunda bir değişiklik yapıldığında bu test yeniden koşturulmalı.
