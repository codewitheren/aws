# Rota · Transfer planlama

Cognito ve AgentCore üzerinde çalışan günlük transfer uygulaması. Kullanıcı merkezi ve transfer tipini seçer, girdileri inceler ve resmi motor koşusunu onaylar.

## Koşu

- `prepare` seçilen kategorinin Google Sheet sekmelerini bir çalışma kopyasına alır. Girdi kontrolleri kritik bulgu verirse motor başlamaz. Geçerli girdilerde sırasıyla parametre farkları, Relex aykırı önerileri ve taslak motorun hacim yükü incelenir.
- Bulgular en fazla 10'luk sayfalarda gösterilir. Ürün önerileri G10/GB ve adet/kg ayrımıyla gruplanır. Kullanıcı miktarı inceleyip onaylayabilir veya olduğu gibi bırakabilir. Ekranda gösterilmeyen miktarlar açık onayla olduğu gibi bırakılabilir.
- `finish` resmi koşu onayını ve gösterilen uyarıların kararlarını doğrular. Onaylanan miktarlar depo ve ürün koduyla çalışma kopyasına uygulanır. Özgün miktar, batch, kanıt ve onay özel `revize_log.csv` dosyasına kaydedilir. Sonuçlar ekranı revize satırlarının finalini, motorun özetini, Excel ve parquet dosyalarını gösterir. Revizeyi geri alma işlemi özgün kopyayla incelemeyi yeniden açar ve geri alma kaydını ekler.
- Strands agent, taslak veya resmi parquet'ten merkez, depo, ürün ve depo × ürün metriklerini hesaplar. Kesinti nedenlerini, revize kayıtlarını ve önceki en fazla üç iş gününü sorgular. What-if, eşleşen girdi ve motor sürümüyle ayrı bir çalışma dizininde sonuç üretir.
- Geçmiş için aynı kullanıcıya ait önceki resmi koşular ve varsa İzmir arşivi kullanılır. Arşiv paketlemeye `data/data/izmir_gecmis/<gg.aa veya YYYY-MM-DD>/<Ambient ve Su | +4 | MS>/İzmir.parquet` düzeninde eklenebilir. Yerel denemelerde `TRANSFER_HISTORY_DIR` ile alternatif arşiv yolu seçilebilir.
- CloudFront statik `web/` dizinini sunar. Cognito erişim belirteciyle AgentCore'a gider. Koşu ve çıktı anahtarları kullanıcı kimliği ve koşu UUID'siyle sınırlandırılır. İndirme bağlantıları beş dakika geçerlidir.

## Yerel doğrulama

```sh
.venv/bin/python -m unittest discover -s agent/transfer/tests -p test_review.py -v
.venv/bin/python agent/transfer/tests/test_karsilastir.py \
  --snap data/data/gsheet_kopya_24.11 --orj data/data/inputs/24.11 \
  --tarih 2026-11-24 --cikti /tmp/rota-karsilastirma
```

İlk test resmi onayı, eski girdinin koşuyu durdurmasını, revize kaydını ve what-if izolasyonunu kontrol eder. Karşılaştırma testi üç motorun Excel ve parquet çıktısını önceki girdi yoluyla hücre düzeyinde karşılaştırır. Karşılaştırma için yeni bir çıktı dizini kullanılır.

## Motor kuralı değişikliği

Mutabık kalınan kuralı kategori, G10/GB, önceki ve yeni davranış, etkilenen satırlar ve varsa yeni neden metniyle yaz. Yama JSON'u her değişiklik için `kategori` (`amb`, `cold` veya `ms`), benzersiz `once` ve `sonra` kod parçalarını içerir.

```sh
.venv/bin/python agent/transfer/algorithm_candidate.py aday \
  --girdi data/data/gsheet_kopya_24.11 --tarih 2026-11-24 --merkez İzmir \
  --yamalar /tmp/rota-yama.json --kural 'Onaylanan kural' --cikti /tmp/rota-aday
```

Aday ve mevcut motor aynı girdiyle ayrı süreçlerde çalışır. İnceleme için `kod.diff`, `rapor.md` ve değişen satırların CSV'si üretilir. Açık etkinleştirme onayından sonra `uygula --aday /tmp/rota-aday --onay <aday-onay-kodu> --onaylayan <kişi>` yerel motoru yedekler ve duman testini çalıştırır. `geri-al --yedek <yedek-adı>` önceki kaynağı geri yükler. AgentCore, yalnız yeniden dağıtım sonrasında bu sürümü kullanır.

## Yeniden dağıtma

Komutları proje kökünde çalıştır. Bu bilgisayarda Python ortamları ve CLI hazırdır. Geçici AWS oturumunun süresi dolduğunda yerel `hackathon` profilini yeni oturumla güncelle.

```sh
export AWS_PROFILE=hackathon
export AWS_DEFAULT_REGION=us-east-1
.build/cli/bin/aws sts get-caller-identity
.venv/bin/python scripts/deploy.py
```

Dağıtım, model erişimini denetler, iki CloudFormation yığınını oluşturur veya günceller, ARM64 paketini içerik özetiyle S3'e yükler ve web adresini yazdırır. Yalnızca arayüz değiştiğinde `scripts/deploy.py publish` yeterlidir.

İlk giriş için, web yığınının `PoolId` çıktısındaki Cognito kullanıcı havuzunda bir kullanıcı oluştur ve kalıcı parola tanımla. Ardından dağıtımın yazdırdığı web adresinden giriş yap.

Yeni bir bilgisayarda Python 3.11, uv ve AWS CLI kur. Python ortamını aşağıdaki komutlarla oluştur.

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r agent/requirements.txt
```

## Kaynakları kaldırma

Bu işlem iki yığını, Cognito kullanıcılarını, projeye ait S3 nesnelerini ve Runtime günlük grubunu siler. Yalnızca kurulumu kaldırmak istediğinde çalıştır.

```sh
AWS_PROFILE=hackathon .venv/bin/python scripts/teardown.py --confirm-account 391036115091
```
