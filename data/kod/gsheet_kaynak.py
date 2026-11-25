# -*- coding: utf-8 -*-
"""
Hackathon - Inputs Google Sheet'inden motor girdilerini indirir.

İki tür sekme var:
  1) "Sheet" sekmeleri (Buffer Rates, Product Volume, Sayım Schedule ...): motorlar bunları zaten
     CSV dışa aktarımıyla okuyor. Panelle birebir aynı olsun diye yine
     /export?format=csv&gid=<gid> ile indirilir ve <kök>/sheets/<gid> dosyasına yazılır.
     (Sayı biçimi, yüzde, tarih metinleri motorun beklediği gibi kalır.)
  2) Elle yüklenen dosyalar (Ambient/Cold/MS Relex, Backlog, Water WH, MS Kasa İçi Kilo):
     Eskiden transferci bunları panele .xlsx/.csv olarak yüklüyordu. Artık gsheet sekmesi.
     CSV ile indirmek tipleri bozar (ör. "Order proposal accepted" 0/1 yerine "No", tarih "26/11/2026",
     "98.18%"), bu yüzden sekme tek başına .xlsx olarak indirilir: /export?format=xlsx&gid=<gid>.
     pd.read_excel orijinal dosyadaki tipleri (int, float, datetime) aynen verir.

Erişim:
  - Varsayılan: anonim (sheet "bağlantıya sahip herkes görüntüleyebilir" olmalı; panel de böyle çalışıyor).
  - Servis hesabı: GOOGLE_APPLICATION_CREDENTIALS=<servis hesabı json> verilirse ve google-auth kuruluysa
    Bearer token ile indirilir (sheet o servis hesabıyla paylaşılmalı).
  - Yerel kopya: kaynak='yerel:<klasör>' -> <klasör>/sheets/<gid> ve <klasör>/xlsx/<ad>.xlsx okunur
    (internet yokken / test için; `python calistir.py indir` ile oluşturulur).
"""
import os
import time
import shutil
import urllib.request
import urllib.error

# ------------------------------------------------------------------ AYARLAR
SPREADSHEET_ID = os.environ.get('HACKATHON_SHEET_ID', '1sPUauZX0yE3CQqjJUjB04SIim7_iM8Pw0TXHnUEDW-Y')
GSHEET_HOST = os.environ.get('GSHEET_HOST', 'https://docs.google.com')   # test için değiştirilebilir

# Motorun okuduğu sheet sekmeleri: anahtar (surucu.py'deki 'key') -> (sekme adı, gid)
SHEET_SEKMELERI = {
    'amb': {
        'urun':       ('volume_format', 1615488785),
        'ambient':    ('ambient_format', 1473098648),
        'gunluk':     ('Depo Palet Limitleri', 670096216),
        'schedule':   ('Copy of custom_delivery_schedule', 476136392),
        'sayim':      ('Sayım Schedule', 1468314948),
        'fast':       ('Fast Acceptance Depoları', 1181864150),
        'kampanya':   ('Dokunulmayacak Ürünler (Kampanya)', 1527796592),
        'sim':        ('Sim', 823638127),
        'suliste':    ('Su palet bilgileri', 1975210347),
        'paletalani': ('Su palet alanı', 868077377),
        'buffer':     ('Buffer Rates', 1173976478),
    },
    'cold': {
        'buffer':   ('Buffer Rates', 1173976478),
        'oran':     ('MS_Other4_Sharing', 2106866758),
        'pooled':   ('+4 New', 108896607),
        'slot':     ('Slot', 370075811),
        'hacim':    ('Product Volume', 1098615637),
        'sayim':    ('Sayım Schedule', 1468314948),
        'kampanya': ('Dokunulmayacak Ürünler (Kampanya)', 1527796592),
    },
    'ms': {
        'buffer':   ('Buffer Rates', 1173976478),
        'oran':     ('MS_Other4_Sharing', 2106866758),
        'pooled':   ('+4 New', 108896607),
        'hacim':    ('volume_format', 1615488785),
        'saklama':  ('Product Volume', 1098615637),
        'slot':     ('Slot', 370075811),
        'sayim':    ('Sayım Schedule', 1468314948),
    },
}

# Elle yüklenen dosyaların sekmeleri: rol (surucu.py'deki dosya rolü) -> (sekme adı, gid)
ELLE_SEKMELER = {
    'amb':  {'relex':   ('Ambient Relex', 142593033),
             'backlog': ('Ambient Backlog', 2061822606),
             'water':   ('Water WH Utilization', 440644371)},
    'cold': {'relex':   ('Cold Relex', 952635685),
             'backlog': ('Cold Backlog', 58755837)},
    'ms':   {'relex':   ('MS Relex', 1130379808),
             'backlog': ('MS Backlog', 1494883435),
             'dokme':   ('MS Kasa İçi Kilo', 776529766)},
}


def sheet_url(gid):
    """Motorun ve panelin kullandığı biçimde sekme adresi."""
    return f'https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid={gid}'


def dosya_adi(sekme_adi):
    return sekme_adi.replace('/', '_') + '.xlsx'


# ------------------------------------------------------------------ indirme
_TOKEN = {'deger': None, 'zaman': 0}

def _yetki_basligi():
    yol = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if not yol:
        return {}
    if _TOKEN['deger'] and time.time() - _TOKEN['zaman'] < 45 * 60:
        return {'Authorization': 'Bearer ' + _TOKEN['deger']}
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
    except ImportError:
        raise RuntimeError('GOOGLE_APPLICATION_CREDENTIALS verildi ama google-auth kurulu değil: pip install google-auth requests')
    kimlik = service_account.Credentials.from_service_account_file(
        yol, scopes=['https://www.googleapis.com/auth/drive.readonly'])
    kimlik.refresh(Request())
    _TOKEN.update(deger=kimlik.token, zaman=time.time())
    return {'Authorization': 'Bearer ' + kimlik.token}


def _indir(url, deneme=3, zaman_asimi=120):
    son = None
    for i in range(deneme):
        try:
            istek = urllib.request.Request(url, headers={'User-Agent': 'sevk-planlama-agent', **_yetki_basligi()})
            with urllib.request.urlopen(istek, timeout=zaman_asimi) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            son = e
            if e.code in (401, 403, 404):
                raise RuntimeError(
                    f'Sheet indirilemedi (HTTP {e.code}). Sheet "bağlantıya sahip herkes" ile paylaşılmalı '
                    f'ya da GOOGLE_APPLICATION_CREDENTIALS ile yetkili bir servis hesabı verilmeli. Adres: {url}')
        except Exception as e:
            son = e
        time.sleep(2 * (i + 1))
    raise RuntimeError(f'Sheet indirilemedi: {url} ({son})')


def csv_indir(gid):
    b = _indir(f'{GSHEET_HOST}/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={gid}')
    if b.lstrip()[:1] == b'<':
        raise RuntimeError(f'gid {gid}: CSV yerine HTML geldi (giriş sayfası?). Sheet paylaşımını kontrol et.')
    return b


def xlsx_indir(gid):
    b = _indir(f'{GSHEET_HOST}/spreadsheets/d/{SPREADSHEET_ID}/export?format=xlsx&gid={gid}')
    if b[:2] != b'PK':
        raise RuntimeError(f'gid {gid}: xlsx yerine başka bir şey geldi (giriş sayfası?). Sheet paylaşımını kontrol et.')
    return b


# ------------------------------------------------------------------ hazırlama
def girdileri_hazirla(urun, kok, kaynak='gsheet', log=print):
    """
    Motorun girdilerini <kok>/sheets ve <kok>/in altına koyar.
    Dönüş: (dosyalar {rol: yol}, sheet {key: {'url', 'gid'}}, ozet [satırlar])
    """
    sheets_dir = os.path.join(kok, 'sheets'); in_dir = os.path.join(kok, 'in')
    os.makedirs(sheets_dir, exist_ok=True); os.makedirs(in_dir, exist_ok=True)
    yerel = kaynak[len('yerel:'):] if kaynak.startswith('yerel:') else None
    ozet, sheet, dosyalar = [], {}, {}

    for key, (ad, gid) in SHEET_SEKMELERI[urun].items():
        hedef = os.path.join(sheets_dir, str(gid))
        t0 = time.time()
        if yerel:
            shutil.copyfile(os.path.join(yerel, 'sheets', str(gid)), hedef)
        else:
            with open(hedef, 'wb') as f:
                f.write(csv_indir(gid))
        sheet[key] = {'url': sheet_url(gid), 'gid': str(gid)}
        ozet.append(f'  sheet  {ad:<36} gid {gid:<11} {os.path.getsize(hedef):>11,} bayt  {time.time() - t0:.1f} sn')

    for rol, (ad, gid) in ELLE_SEKMELER[urun].items():
        hedef = os.path.join(in_dir, f'{rol}.xlsx')
        t0 = time.time()
        if yerel:
            shutil.copyfile(os.path.join(yerel, 'xlsx', dosya_adi(ad)), hedef)
        else:
            with open(hedef, 'wb') as f:
                f.write(xlsx_indir(gid))
        if rol == 'water':
            # Ambient motoru Water WH'yi panelden gelen ham hâliyle (UTF-16, sekmeyle ayrılmış CSV) okur.
            # Sekme metin olarak tutuluyor ("1,295", "9%"); başlıklar dahil hiçbir şeye dokunmadan çevrilir.
            import pandas as pd
            d = pd.read_excel(hedef, dtype=str, keep_default_na=False)
            hedef = os.path.join(in_dir, 'water.csv')
            d.to_csv(hedef, sep='\t', index=False, encoding='utf-16')
        dosyalar[rol] = hedef
        ozet.append(f'  dosya  {ad:<36} gid {gid:<11} {os.path.getsize(hedef):>11,} bayt  {time.time() - t0:.1f} sn')

    for s in ozet:
        log(s)
    return dosyalar, sheet, ozet


def yerel_kopya_al(klasor, urunler=('amb', 'cold', 'ms'), log=print):
    """Tüm girdileri bir kerede indirip klasöre yazar (internetsiz çalışma / test için)."""
    os.makedirs(os.path.join(klasor, 'sheets'), exist_ok=True)
    os.makedirs(os.path.join(klasor, 'xlsx'), exist_ok=True)
    gorulen = set()
    for u in urunler:
        for ad, gid in SHEET_SEKMELERI[u].values():
            if gid in gorulen: continue
            gorulen.add(gid)
            with open(os.path.join(klasor, 'sheets', str(gid)), 'wb') as f:
                f.write(csv_indir(gid))
            log(f'  sheet {ad} ({gid})')
        for ad, gid in ELLE_SEKMELER[u].values():
            with open(os.path.join(klasor, 'xlsx', dosya_adi(ad)), 'wb') as f:
                f.write(xlsx_indir(gid))
            log(f'  dosya {ad} ({gid})')
