# Rota · Transfer planlama

Mevcut Cognito ve AgentCore kurulumu üzerinden çalışan Türkçe günlük transfer uygulaması. Web arayüzü derleme gerektirmez. Kullanıcı giriş yapar, merkez ve transfer tipini seçer, aykırı Relex önerilerini inceler ve kesim motorunun sonuçlarını indirir.

## Koşu

- CloudFront özel S3 kovasının `web/` dizinini yayımlar. Aynı alan adındaki `/runtimes/*` çağrıları Cognito erişim belirteciyle AgentCore'a gider.
- `agent/transfer/gsheet_kaynak.py` yapılandırılmış Google Sheet'ten seçili kategorinin sekmelerini okur. Dosya erişimi Runtime ortamından sağlanmalıdır. Koşu tarihi sayım ve teslimat hesaplarının iş tarihidir. Tarih seçimi geçmiş girdi arşivi getirmez.
- `prepare` girdileri sabitler, merkezi depo kodlarıyla doğrular ve aynı ürün/depo tipinde aykırı önerileri çıkarır. Kullanıcı kararları yalnız çalışma kopyasındaki Effective quantity alanını etkiler. Karara kadar yapılan seçimler aynı tarayıcı sekmesinde tutulur.
- `finish` Ambient & Su, Cold veya MS motorunu ayrı Python sürecinde çalıştırır. Motorun Excel, parquet, All PL ve sonuc.json çıktıları, uyarı ve anomali CSV dosyaları özel S3 alanına gider. Sonuç kaydı dosyaların tamamı yazılınca yayımlanır.
- Koşu kimliği Runtime oturum UUID'sidir. S3 anahtarları doğrulanmış Cognito sub ve bu kimlikle oluşturulur. Backend başka bir kullanıcının dosya anahtarını istemciden kabul etmez. Dosya bağlantıları beş dakika geçerlidir.
- Sonuçlar ekranında tek Strands agent `agent/transfer/SKILL.md` kurallarını ve ilgili koşunun depo kanıtını kullanır. Günlük koşunun dışında kalan haftalık optimizasyon ve geçmiş gün karşılaştırmaları bu sürümde sunulmaz.

## Yerel doğrulama

`agent/transfer/tests/test_karsilastir.py` aynı iş gününün orijinal dosyaları ve girdi kopyasıyla çalışır. Parametreler `--snap`, `--orj`, `--tarih` ve yeni bir çıktı dizini için `--cikti`. Test her motorun Excel sekmelerini ve ana parquet tablosunu hücre düzeyinde karşılaştırır. Uygulama ve dağıtım, tasarım referansları veya örnek veri klasörleri gerektirmez.

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
