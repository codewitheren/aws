# -*- coding: utf-8 -*-
"""
Sevk Planlama motorlarını (Ambient & Su, Cold +4, MS) Hackathon - Inputs Google Sheet'inden besleyerek koşturur.
Transfercinin panelde yaptığı işin aynısı: girdileri topla -> motoru çalıştır -> Excel + parquet + All PL.

Kullanım:
  python calistir.py ambient                      # bugünün tarihiyle, girdiler gsheet'ten
  python calistir.py cold --tarih 2026-11-24
  python calistir.py ms --cikti ciktilar --param '{"MAX_ROWS": 12000}'
  python calistir.py hepsi --tarih 2026-11-24     # üçü sırayla
  python calistir.py indir --klasor gsheet_kopya  # tüm girdileri yerel klasöre indir
  python calistir.py ambient --kaynak yerel:gsheet_kopya   # internetsiz, yerel kopyadan

Python'dan (agent aracı olarak):
  from calistir import calistir
  sonuc = calistir('cold', tarih='2026-11-24')
  sonuc['ok'], sonuc['excel'], sonuc['parquet'], sonuc['allpl_parquet'], sonuc['ozet']

Çıktı klasörü: <cikti>/<tarih>/<urun>/
  out/<merkez>.xlsx        motorun Excel'i (panelden inen dosyanın aynısı)
  out/<merkez>.parquet     ana tablo (Parquet Arşiv'e giden dosya)
  allpl/<gg Ay> All PL.*   günün All PL'si (bu koşunun satırları)
  sonuc.json               panelin gösterdiği tüm özet/kontrol/depo tabloları + log
  sheets/, in/             bu koşuda kullanılan girdiler (denetim için saklanır)
"""
import os
import sys
import json
import time
import argparse
import datetime

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)

import gsheet_kaynak as gk  # noqa: E402

URUN_ADI = {'ambient': 'amb', 'amb': 'amb', 'cold': 'cold', '+4': 'cold', 'ms': 'ms'}
_SURUCU = None


def ortam_kontrol():
    """Motorlar panelde Pyodide 0.26 (pandas 2.2, numpy 1.26) ile çalışıyor. pandas 3 metin tipini
    değiştirdiği için Ambient motoru hata verir; parquet için pyarrow gerekir."""
    import pandas as pd
    ana = int(pd.__version__.split('.')[0])
    if ana >= 3:
        raise RuntimeError(f'pandas {pd.__version__} kurulu; motorlar pandas 2.x ister. '
                           f'pip install -r requirements.txt (pandas==2.2.3, numpy==1.26.4)')
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        raise RuntimeError('pyarrow kurulu değil (parquet çıktısı için gerekli): pip install -r requirements.txt')


def _surucu():
    global _SURUCU
    if _SURUCU is None:
        ortam_kontrol()
        import surucu
        _SURUCU = surucu
    return _SURUCU


def bugun_istanbul():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=3)).strftime('%Y-%m-%d')


def varsayilan_parametreler(urun):
    """Motor kodundaki parametre değerleri (panelin 'Parametreler' bölümünün varsayılanları)."""
    s = _surucu()
    oz = s.kaynak_ozet(s.URUNLER[URUN_ADI[urun]])
    return {k: (v['deger'] if isinstance(v, dict) and 'deger' in v else v) for k, v in oz['param'].items()}


def calistir(urun, tarih=None, cikti='ciktilar', param=None, merkez=None, kaynak='gsheet', sessiz=False):
    """
    urun   : 'ambient' | 'cold' | 'ms'
    tarih  : 'YYYY-MM-DD' (motor bugünü bu tarih 12:00 kabul eder: TIR günü, sayım, kampanya T/T-1). Boşsa bugün.
    param  : motor parametrelerinden değiştirilecekler, ör. {'MAX_SATIR_LIMITI': 12000}
    merkez : merkez adı otomatik tanınmazsa kullanılacak ad (panelde 'merkez' kutusu)
    kaynak : 'gsheet' (varsayılan) veya 'yerel:<klasör>'
    """
    s = _surucu()
    u = URUN_ADI[urun.lower()]
    tarih = tarih or bugun_istanbul()
    log = (lambda *a, **k: None) if sessiz else print
    kok = s.klasorleri_hazirla(os.path.join(os.path.abspath(cikti), tarih, {'amb': 'ambient', 'cold': 'cold', 'ms': 'ms'}[u]))
    log(f'== {urun} | tarih {tarih} | kaynak {kaynak} | klasör {kok}')

    t0 = time.time()
    dosyalar, sheet, _ = gk.girdileri_hazirla(u, kok, kaynak, log=log)
    t_indir = time.time() - t0

    P = varsayilan_parametreler(u)
    bilinmeyen = [k for k in (param or {}) if k not in P]
    if bilinmeyen:
        raise ValueError(f'Bilinmeyen parametre: {bilinmeyen}. Geçerliler: {sorted(P)}')
    P.update(param or {})
    cfg = {'urun': u, 'param': P, 'dosyalar': dosyalar, 'sheet': sheet, 'tarih': tarih, 'sade': False,
           'zaman': tarih + ' 12:00', 'merkez_elle': merkez or ''}

    t1 = time.time()
    if sessiz:
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            r = json.loads(s.calistir(json.dumps(cfg, ensure_ascii=False, default=str)))
    else:
        r = json.loads(s.calistir(json.dumps(cfg, ensure_ascii=False, default=str)))
    t_motor = time.time() - t1

    sonuc = {'ok': bool(r.get('ok')), 'urun': urun, 'tarih': tarih, 'klasor': kok,
             'sure_sn': {'indirme': round(t_indir, 1), 'motor': round(t_motor, 1)},
             'excel': r.get('dosya'), 'parquet': r.get('parquet'), 'parquet_hata': r.get('parquet_hata'),
             'merkez': (r.get('merkez') or {}).get('ad'), 'hata': r.get('hata')}
    if r.get('ok') and r.get('parquet_hata'):
        sonuc['ok'] = False
        sonuc['hata'] = 'Excel yazıldı ama parquet yazılamadı: ' + r['parquet_hata']
    if r.get('ok'):
        a = json.loads(s.allpl_olustur(u))
        sonuc.update({'allpl_ok': a.get('ok'), 'allpl_xlsx': a.get('xlsx'), 'allpl_parquet': a.get('parquet'),
                      'allpl_satir': a.get('satir'), 'allpl_hata': a.get('hata')})
        sonuc['ozet'] = r.get('ozet')
        sonuc['kontrol'] = r.get('kontrol')
    with open(os.path.join(kok, 'sonuc.json'), 'w', encoding='utf-8') as f:
        json.dump({**r, 'calistir': {k: v for k, v in sonuc.items() if k not in ('ozet', 'kontrol')}},
                  f, ensure_ascii=False, default=str)
    if sonuc['ok']:
        log(f"✅ {urun}: merkez {sonuc['merkez']} | Excel {sonuc['excel']} | parquet {sonuc['parquet']} | "
            f"All PL {sonuc.get('allpl_satir')} satır | indirme {t_indir:.0f} sn, motor {t_motor:.0f} sn")
    else:
        log(f"❌ {urun}: {sonuc['hata']}")
        log((r.get('log') or '')[-3000:])
    return sonuc


def main():
    ap = argparse.ArgumentParser(description='Sevk Planlama motorlarını gsheet girdileriyle çalıştırır.')
    ap.add_argument('urun', choices=['ambient', 'cold', 'ms', 'hepsi', 'indir', 'parametreler'])
    ap.add_argument('--tarih', help='YYYY-MM-DD (varsayılan: bugün, İstanbul)')
    ap.add_argument('--cikti', default='ciktilar')
    ap.add_argument('--param', help='JSON, ör. \'{"MAX_SATIR_LIMITI": 12000}\'')
    ap.add_argument('--merkez', help='Merkez otomatik tanınmazsa kullanılacak ad')
    ap.add_argument('--kaynak', default='gsheet', help="'gsheet' veya 'yerel:<klasör>'")
    ap.add_argument('--klasor', default='gsheet_kopya', help='indir komutu için hedef klasör')
    a = ap.parse_args()

    if a.urun == 'indir':
        gk.yerel_kopya_al(a.klasor)
        print('✅ indirildi:', os.path.abspath(a.klasor))
        return
    if a.urun == 'parametreler':
        for u in ('ambient', 'cold', 'ms'):
            print(u, json.dumps(varsayilan_parametreler(u), ensure_ascii=False)[:2000])
        return
    param = json.loads(a.param) if a.param else None
    urunler = ['ambient', 'cold', 'ms'] if a.urun == 'hepsi' else [a.urun]
    hata = False
    for u in urunler:
        r = calistir(u, a.tarih, a.cikti, param if a.urun != 'hepsi' else None, a.merkez, a.kaynak)
        hata |= not r['ok']
    sys.exit(1 if hata else 0)


if __name__ == '__main__':
    main()
