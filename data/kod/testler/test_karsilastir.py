# -*- coding: utf-8 -*-
"""
Gsheet beslemeli koşu ile panelin eski yolunu (transfercinin yüklediği orijinal xlsx/csv dosyaları) karşılaştırır.

  python testler/test_karsilastir.py --snap <yerel gsheet kopyası> --orj <orijinal dosyalar klasörü> --tarih 2026-11-24

<orijinal dosyalar klasörü> yapısı (hackathon/data/inputs/24.11 ile aynı):
  ambient/Ambient Relex.xlsx, ambient/Ambient Backlog (Dünkü Çıktı).xlsx, ambient/Water WH Utilization (ham CSV, UTF-16).csv
  cold/Cold Relex.xlsx, cold/Cold Backlog.xlsx
  ms/MS Relex.xlsx, ms/MS Backlog.xlsx, ms/MS Kasa İçi Kilo.xlsx

Her iki koşuda sheet sekmeleri aynı yerel kopyadan gelir; fark yalnızca elle yüklenen dosyaların yolu:
  eski: orijinal xlsx / UTF-16 csv   →   yeni: gsheet sekmesi, /export?format=xlsx ile indirilmiş
Excel'deki her sekme, satır, kolon ve hücre karşılaştırılır; ana tablo parquet'leri de karşılaştırılır.
"""
import os
import sys
import json
import shutil
import argparse
import numpy as np
import pandas as pd

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(BURASI))
import calistir as C          # noqa: E402
import gsheet_kaynak as gk    # noqa: E402

ORJ_DOSYALAR = {
    'ambient': {'relex': 'ambient/Ambient Relex.xlsx', 'backlog': 'ambient/Ambient Backlog (Dünkü Çıktı).xlsx',
                'water': 'ambient/Water WH Utilization (ham CSV, UTF-16).csv'},
    'cold': {'relex': 'cold/Cold Relex.xlsx', 'backlog': 'cold/Cold Backlog.xlsx'},
    'ms': {'relex': 'ms/MS Relex.xlsx', 'backlog': 'ms/MS Backlog.xlsx', 'dokme': 'ms/MS Kasa İçi Kilo.xlsx'},
}


def eski_yol_kosu(urun, tarih, orj, snap, cikti):
    """Panelin eski yolu: orijinal dosyalar + aynı sheet sekmeleri."""
    s = C._surucu()
    u = C.URUN_ADI[urun]
    kok = s.klasorleri_hazirla(os.path.join(cikti, 'eski_yol', urun))
    _, sheet, _ = gk.girdileri_hazirla(u, kok, 'yerel:' + snap, log=lambda *a: None)   # sheet sekmeleri
    dosyalar = {}
    for rol, rel in ORJ_DOSYALAR[urun].items():
        hedef = os.path.join(kok, 'in', 'orj_' + rol + os.path.splitext(rel)[1])
        shutil.copyfile(os.path.join(orj, rel), hedef)
        dosyalar[rol] = hedef
    cfg = {'urun': u, 'param': C.varsayilan_parametreler(urun), 'dosyalar': dosyalar, 'sheet': sheet,
           'tarih': tarih, 'sade': False, 'zaman': tarih + ' 12:00', 'merkez_elle': ''}
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        r = json.loads(s.calistir(json.dumps(cfg, ensure_ascii=False, default=str)))
    return r


def tablo_esit(a, b):
    """İki DataFrame'i hücre hücre karşılaştırır; farkları döndürür."""
    farklar = []
    if list(a.columns) != list(b.columns):
        return [f'kolonlar farklı: {set(a.columns) ^ set(b.columns)}']
    if len(a) != len(b):
        return [f'satır sayısı farklı: {len(a)} / {len(b)}']
    for c in a.columns:
        x, y = a[c], b[c]
        xn, yn = pd.to_numeric(x, errors='coerce'), pd.to_numeric(y, errors='coerce')
        sayisal = xn.notna() & yn.notna()
        f1 = sayisal & ~np.isclose(xn.fillna(0), yn.fillna(0), rtol=1e-9, atol=1e-9)
        f2 = ~sayisal & (x.astype(str).where(x.notna(), '') != y.astype(str).where(y.notna(), ''))
        n = int((f1 | f2).sum())
        if n:
            i = (f1 | f2).idxmax()
            farklar.append(f'{c}: {n} hücre (ör. satır {i}: {x[i]!r} / {y[i]!r})')
    return farklar


def excel_karsilastir(yol_a, yol_b):
    xa, xb = pd.ExcelFile(yol_a), pd.ExcelFile(yol_b)
    sonuc = {}
    if xa.sheet_names != xb.sheet_names:
        sonuc['_sekmeler'] = [f'{xa.sheet_names} / {xb.sheet_names}']
    for sh in xa.sheet_names:
        if sh not in xb.sheet_names: continue
        a = pd.read_excel(yol_a, sheet_name=sh, header=None)
        b = pd.read_excel(yol_b, sheet_name=sh, header=None)
        sonuc[sh] = (a.shape, tablo_esit(a, b))
    return sonuc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--snap', required=True)
    ap.add_argument('--orj', required=True)
    ap.add_argument('--tarih', required=True)
    ap.add_argument('--cikti', default='test_ciktilari')
    ap.add_argument('--urunler', default='ambient,cold,ms')
    a = ap.parse_args()
    cikti = os.path.abspath(a.cikti)
    if os.path.exists(cikti): shutil.rmtree(cikti)
    rapor, basarili = [], True
    for urun in a.urunler.split(','):
        yeni = C.calistir(urun, a.tarih, os.path.join(cikti, 'gsheet_yolu'), kaynak='yerel:' + os.path.abspath(a.snap), sessiz=True)
        eski = eski_yol_kosu(urun, a.tarih, os.path.abspath(a.orj), os.path.abspath(a.snap), cikti)
        rapor.append(f'\n=== {urun.upper()}  (merkez: gsheet {yeni["merkez"]} / eski {(eski.get("merkez") or {}).get("ad")})')
        if not yeni['ok'] or not eski.get('ok'):
            basarili = False
            rapor.append(f'  ❌ koşu hatası: gsheet={yeni.get("hata")} eski={eski.get("hata")}')
            continue
        rapor.append(f'  gsheet koşusu: {yeni["sure_sn"]["motor"]} sn, All PL {yeni.get("allpl_satir")} satır')
        for sh, v in excel_karsilastir(yeni['excel'], eski['dosya']).items():
            if sh == '_sekmeler':
                basarili = False; rapor.append(f'  ❌ sekme listesi farklı {v}'); continue
            shape, fark = v
            if fark: basarili = False
            rapor.append(f'  {"✅" if not fark else "❌"} {sh:<28} {shape[0]:>6} satır × {shape[1]:>3} kolon' +
                         ('' if not fark else '  FARK: ' + ' | '.join(fark[:5])))
        pa, pb = pd.read_parquet(yeni['parquet']), pd.read_parquet(eski['parquet'])
        fark = tablo_esit(pa, pb)
        if fark: basarili = False
        rapor.append(f'  {"✅" if not fark else "❌"} {"parquet (ana tablo)":<28} {pa.shape[0]:>6} satır × {pa.shape[1]:>3} kolon' +
                     ('' if not fark else '  FARK: ' + ' | '.join(fark[:5])))
    rapor.append('\nSONUÇ: ' + ('✅ gsheet yolu eski yolla birebir aynı çıktı verdi' if basarili else '❌ fark var'))
    metin = '\n'.join(rapor)
    print(metin)
    open(os.path.join(cikti, 'test_raporu.txt'), 'w', encoding='utf-8').write(metin)
    sys.exit(0 if basarili else 1)


if __name__ == '__main__':
    main()
