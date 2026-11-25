# Sevk Planlama motorları — gsheet beslemeli çalıştırıcı

Transfercinin panelde (Sevk_Planlama.html) yaptığı işi koddan yapar: girdileri **Hackathon - Inputs** Google Sheet'inden
alır, üç motoru (Ambient & Su, Cold +4, MS) çalıştırır, panelin ürettiği Excel / parquet / All PL çıktılarının aynısını üretir.

Motor kodları (`motorlar/`) canlıdaki ile aynı hesaplamayı yapar. Tek değişiklik: **Google Drive'a kayıt bölümü
kaldırıldı**. Colab'da Excel'i, parquet'i ve All PL'yi Drive'a yükleyen blok, Drive import'ları ve `ANA_KLASOR_ID`
koddan çıkarıldı. Kod hiçbir yere yükleme yapmaz; tüm çıktılar yerel çıktı klasörüne yazılır ve oradan indirilir.
Hesaplama kısmına dokunulmadı: Drive bölümü çıkarılmadan önce ve sonra alınan çıktılar birebir aynı.
`surucu.py` panelin kendi sürücüsüdür. Panelde Pyodide'in `/sheets`, `/in`, `/out` klasörleri olan yerler burada
normal klasör oldu. Kullanılmayan Drive yardımcıları buradan da silindi.

## Kurulum
```
python3.11 -m venv .venv && source .venv/bin/activate     # 3.11 veya 3.12
pip install -r requirements.txt
```
Sürümler önemli. Panel Pyodide 0.26 ile, yani pandas 2.2 ve numpy 1.26 ile çalışıyor. **pandas 3.x ile Ambient
motoru hata verir**; `calistir.py` bunu baştan kontrol eder.

## Çalıştırma
```
python calistir.py ambient --tarih 2026-11-24
python calistir.py cold    --tarih 2026-11-24
python calistir.py ms      --tarih 2026-11-24 --param '{"MAX_ROWS": 12000}'
python calistir.py hepsi                          # tarih verilmezse bugün (İstanbul)
python calistir.py parametreler                   # değiştirilebilir parametreler ve varsayılanları
python calistir.py indir --klasor gsheet_kopya    # tüm girdileri yerel klasöre indir
python calistir.py cold --kaynak yerel:gsheet_kopya   # internetsiz, yerel kopyadan
```
Agent aracı olarak:
```python
from calistir import calistir
s = calistir('cold', tarih='2026-11-24', param={'PLUS_4_USABLE_RATIO': 1.05})
s['ok'], s['excel'], s['parquet'], s['allpl_parquet'], s['kontrol'], s['ozet']
```
`tarih`, motorun "bugün" kabul ettiği gündür (saat 12:00). TIR palet limiti, sayım kısıtı ve kampanyanın T / T-1
listesi bu güne göre seçilir. Bu yüzden her zaman koşunun gerçek gününü ver.

## Girdiler (Hackathon - Inputs, id `1sPUauZX0yE3CQqjJUjB04SIim7_iM8Pw0TXHnUEDW-Y`)
Tüm sekme ve gid listesi `gsheet_kaynak.py` içinde tanımlı.

| Tür | Nasıl indirilir | Neden |
|---|---|---|
| Sheet sekmeleri (Buffer Rates, Product Volume, +4 New, Sim, Sayım...) | `export?format=csv&gid=` | Panel de böyle indiriyor. Motorların sayı, yüzde ve tarih ayrıştırması bu biçime göre yazılmış. |
| Elle yüklenen dosyalar (Ambient/Cold/MS Relex, Backlog, Water WH, MS Kasa İçi Kilo) | `export?format=xlsx&gid=`, sekme tek başına indirilir | CSV olarak inince tipler bozuluyor: 0/1 değerler "No" oluyor, tarih "26/11/2026", oran "98.18%" metni geliyor. Tek sekmelik xlsx ise orijinal dosyadaki tipleri (int, float, datetime) aynen veriyor. |
| Water WH | xlsx olarak indirilir, sonra UTF-16 sekmeli CSV'ye çevrilir | Motor panelden gelen ham CSV'yi bu biçimde okuyor. Başlıklar ve değerler değiştirilmeden çevrilir. |

**Erişim:** Varsayılan anonim indirme. Sheet "bağlantıya sahip herkes görüntüleyebilir" olmalı; panel de böyle çalışıyor.
Paylaşımı kapatmak istersen sheet'i bir servis hesabıyla paylaş, `GOOGLE_APPLICATION_CREDENTIALS=<json>` ayarla ve
`pip install google-auth requests` kur. Başka bir sheet için `HACKATHON_SHEET_ID` ortam değişkenini kullan.

**Günlük güncelleme:** Relex, Backlog, Water WH ve Kasa İçi Kilo sekmeleri her gün o günün dosyasıyla değiştirilmeli.
Sekme adı ve gid'i değişmemeli: sekmenin içeriği temizlenip yeni veri yapıştırılır ya da import'ta "Replace current sheet"
seçilir. Yeni sekme açılırsa gid değişir ve `gsheet_kaynak.py`'deki tablonun güncellenmesi gerekir.

## Çıktılar: `ciktilar/<tarih>/<ambient|cold|ms>/`
- `out/<merkez>.xlsx`: panelden inen Excel'in aynısı. Sekmeleri: Sheet1, Depo Ozet Karnesi, Detayli Kesinti Raporu, Kapasite Detayi, Debug...
- `out/<merkez>.parquet`: ana tablo. Parquet Arşiv'e giden dosya.
- `allpl/<gg Ay> All PL.parquet|xlsx`: bu koşunun All PL satırları.
- `sonuc.json`: panel ekranındaki her şey. Agent'ın analiz için en kullanışlı girdisi:
  - `kpi`: üst kartlar
  - `kontrol`: veri kaynağı ve limit kontrolleri (durum ok/uyari/hata, açıklama, satırlar)
  - `ozet`: kısıntı nedenleri ve merkez özeti
  - `depo_tablo`: depo bazlı öneri → final, kısıntı ve nedeni
  - `oneri`: aşırı öneri, fazla stok ve büyük öneri bulguları
  - `detay`: satır detayı
  - `log`: motorun çıktısı
- `sheets/`, `in/`: o koşuda kullanılan girdilerin kopyası (denetim için).

Merkez adı (İzmir, Maltepe...) panelle aynı yöntemle Relex'teki depolardan otomatik bulunur. Bulunamazsa `--merkez Maltepe` ver.

## Test: `testler/test_karsilastir.py`
Aynı gün için iki koşu yapar ve hücre hücre karşılaştırır:
- gsheet yolu
- panelin eski yolu: transfercinin yüklediği orijinal xlsx/csv dosyaları

```
python testler/test_karsilastir.py --snap gsheet_kopya --orj ../data/inputs/24.11 --tarih 2026-11-24
```
24.11 İzmir verisiyle üç motorun bütün Excel sekmeleri ve parquet'leri birebir aynı çıktı (`testler/test_raporu_24.11.txt`).
İndirme kodu ayrıca sahte bir sunucu üzerinden uçtan uca denendi.

## Bilinen notlar
- `volume_format` sekmesinin "Koli/Palet EY/MD" kolonları kopyada #REF! veriyor (formülün baktığı sekme kopyada yok).
  Motorlar bu kolonları kullanmıyor, yalnızca `hacim2`'yi kullanıyor. `hacim2` orijinalle 12.340 üründe birebir aynı.
- `+4 New`, `ambient_format`, Kampanya ve Sharing sekmeleri kopyalandıkları anın (25.11) değerleri. Orijinal sheet canlı
  güncelleniyor, bu kopya güncellenmiyor. Canlıya bağlamak için bu sekmelere IMPORTRANGE konabilir.
- Panelde kullanıcının elle değiştirdiği parametreler (limitler, Dokunulmayacak/Waste listeleri) burada motor kodundaki
  varsayılanlardır. Değiştirmek için `param=` kullan.
