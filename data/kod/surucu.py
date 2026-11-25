# Sevk Planlama sürücüsü — Sevk_Planlama.html içindeki "kaynak-surucu" ile birebir aynı,
# tek fark: Pyodide klasörleri (/sheets, /in, /out, /allpl) yerine KOK altındaki normal klasörler
# ve motor kodlarının motorlar/ klasöründen okunması. Motor kodlarına dokunulmaz.
# Sevk Planlama — ortak sürücü çekirdeği.
# Her ürün kodu (Ambient & Su, Cold, MS) satırına dokunulmadan çalıştırılır:
#  • Google bağlantıları (gspread / Colab) taklit edilir, sheet'ler /sheets/<gid> dosyalarından okunur,
#  • parametre atamaları arayüzden gelen değerlerle değiştirilir,
#  • Excel / parquet / All PL yerel klasöre yazılır; Drive'a hiçbir şey yüklenmez.
import io, os, re, sys, ast, csv, json, types, traceback, contextlib, math, collections
import numpy as np
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)
import pandas as pd

# Çalışma kökü: sheet sekmeleri KOK/sheets/<gid>, girdi dosyaları KOK/in, çıktılar KOK/out, All PL KOK/allpl.
# (Panelde Pyodide'in /sheets, /in, /out klasörleriydi; burada normal klasör.)
KOK = os.path.abspath(os.environ.get('SEVK_KOK', 'calisma'))

def klasorleri_hazirla(kok=None):
    global KOK
    if kok: KOK = os.path.abspath(kok)
    for _d in ('sheets', 'in', 'out', 'allpl'):
        os.makedirs(os.path.join(KOK, _d), exist_ok=True)
    return KOK

URUNLER = {}      # ürün modülleri kendini buraya kaydeder


# ------------------------------------------------------------------ Google taklitleri
class _Sayfa:
    def __init__(self, gid): self.gid = str(gid).strip()
    def get_all_values(self):
        yol = KOK + '/sheets/' + self.gid
        if not os.path.exists(yol):
            raise RuntimeError(f"Google Sheet sekmesi yüklenmedi (gid {self.gid})")
        with open(yol, encoding='utf-8-sig', newline='') as f:
            satirlar = [r for r in csv.reader(f)]
        satirlar = [r for r in satirlar if any(str(x).strip() for x in r)] or [[]]
        n = max(len(r) for r in satirlar)
        return [r + [''] * (n - len(r)) for r in satirlar]

class _Tablo:
    def get_worksheet_by_id(self, gid): return _Sayfa(gid)

class _GC:
    def open_by_url(self, url): return _Tablo()

def _moduller():
    def mod(ad, **ozellik):
        m = types.ModuleType(ad); m.__dict__.update(ozellik); sys.modules[ad] = m; return m
    google = mod('google'); colab = mod('google.colab')
    colab.auth = types.SimpleNamespace(authenticate_user=lambda *a, **k: None); google.colab = colab
    gauth = mod('google.auth', default=lambda *a, **k: (None, None)); google.auth = gauth
    mod('gspread', authorize=lambda *a, **k: _GC())
_moduller()

_ASIL_READ_CSV = pd.read_csv

def _yonlendirilmis_read_csv(yol, *a, **k):
    """Koddaki Google Sheet CSV adreslerini /sheets/<gid> dosyasına yönlendirir."""
    if isinstance(yol, str) and 'docs.google.com' in yol:
        gidler = re.findall(r'gid=(\d+)', yol)
        if not gidler:
            raise RuntimeError(f'Sheet adresinde sekme numarası yok: {yol}')
        hedef = KOK + '/sheets/' + gidler[-1]
        if not os.path.exists(hedef):
            raise RuntimeError(f'Google Sheet sekmesi yüklenmedi (gid {gidler[-1]})')
        yol = hedef
    return _ASIL_READ_CSV(yol, *a, **k)

@contextlib.contextmanager
def _sheet_yonlendirme():
    pd.read_csv = _yonlendirilmis_read_csv
    try: yield
    finally: pd.read_csv = _ASIL_READ_CSV


# ------------------------------------------------------------------ kaynak kodu okuma
def _ilk_atamalar(agac):
    gorulen = {}
    for n in agac.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            gorulen.setdefault(n.targets[0].id, n)
    return gorulen

_GUVENLI = (ast.Expression, ast.Constant, ast.BinOp, ast.UnaryOp, ast.List, ast.Tuple, ast.Dict, ast.Set,
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd, ast.Load)

def _deger(node):
    try:
        return ast.literal_eval(node)
    except Exception:
        ifade = ast.Expression(node)
        if all(isinstance(x, _GUVENLI) for x in ast.walk(ifade)):
            return eval(compile(ifade, '<deger>', 'eval'), {'__builtins__': {}})
        raise

def _not(satirlar, no):
    s = satirlar[no - 1]
    return s.split('#', 1)[1].strip() if '#' in s else ''

_SID_RE = re.compile(r'/d/([a-zA-Z0-9_-]{20,})')

def kaynak_ozet(spec):
    src = globals()[spec['motor']]
    agac = ast.parse(src); satirlar = src.split('\n'); at = _ilk_atamalar(agac)
    param = {}
    for ad in spec['paramlar']:
        n = at.get(ad)
        if n is None: continue
        try: v = _deger(n.value)
        except Exception: continue
        notlar = None
        if isinstance(n.value, ast.List):
            notlar = [_not(satirlar, e.lineno) if e.lineno != n.lineno or len(n.value.elts) == 1 else '' for e in n.value.elts]
        elif isinstance(v, str):
            notlar = [_not(satirlar, n.lineno)]
        param[ad] = {'deger': v, 'notlar': notlar}
    sheet = []
    for s in spec['sheetler']:
        try: gid = str(_deger(at[s['gid']].value))
        except Exception: gid = ''
        url = ''
        if s.get('url'):
            try: url = _deger(at[s['url']].value)
            except Exception: url = ''
        if not url and s.get('sid'):
            try:
                sid = str(_deger(at[s['sid']].value))
                m = _SID_RE.search(sid); sid = m.group(1) if m else sid
                url = f'https://docs.google.com/spreadsheets/d/{sid}/edit#gid={gid}'
            except Exception: url = ''
        sheet.append({'key': s['key'], 'url': url, 'gid': gid})
    m = re.search(r"for\s+kat\s+in\s+(\[[^\]]*\])", src)
    try: kategoriler = ast.literal_eval(m.group(1)) if m else []
    except Exception: kategoriler = []
    return {'param': param, 'sheet': sheet, 'kategoriler': kategoriler}


def kaynaklar():
    return json.dumps({u: kaynak_ozet(s) for u, s in URUNLER.items()})


def _kaynak_hazirla(src, P, ifadeler=None):
    """Parametre ve dosya atamalarını arayüz değerleriyle değiştirir; 'şimdi' çalışma tarihine bağlanır."""
    src = src.replace('pd.Timestamp.now()', '__SIMDI__()').replace('datetime.datetime.now()', '__SIMDI__()')
    ifadeler = dict(ifadeler or {})
    for a in P: ifadeler.setdefault(a, f'__P__[{a!r}]')
    satirlar = src.split('\n')
    at = _ilk_atamalar(ast.parse(src))
    for n in sorted((at[a] for a in ifadeler if a in at), key=lambda n: -n.lineno):
        ad = n.targets[0].id
        satirlar[n.lineno - 1:n.end_lineno] = [f'{ad} = {ifadeler[ad]}']
    return '\n'.join(satirlar)

# ------------------------------------------------------------------ Excel yazımı (akıtarak)
def _dolu(d):
    return isinstance(d, pd.DataFrame) and not d.empty

_SEVIYE_RENK = {'KRİTİK': 'F8CBAD', 'UYARI': 'FFE699', 'BİLGİ': 'DDEBF7'}

_ID_DESEN = re.compile(r'\s*[0-9a-fA-F]{24}\s*')

def idleri_kucult(df):
    """Çıktıda id'ler küçük harf (Relex depo / ürün kodlarını büyük harfle verir). Değerlerinin çoğu 24 haneli
    hex id olan metin kolonlarında büyük harfli id'ler küçültülür; diğer kolonlara ve motor içi eşleşmeye dokunulmaz.
    Yalnız Excel'e (tüm sekmeler) yazılırken uygulanır; parquet ve All PL Relex'teki haliyle kalır."""
    if not isinstance(df, pd.DataFrame) or df.empty: return df
    out = None
    for i in range(df.shape[1]):
        s = df.iloc[:, i]
        if not (s.dtype == object or pd.api.types.is_string_dtype(s)): continue
        orn = s.dropna().astype(str).head(200)
        if orn.empty or orn.map(lambda x: bool(_ID_DESEN.fullmatch(x))).mean() < 0.5: continue
        t = s.astype(str)
        m = (s.notna() & t.str.fullmatch(_ID_DESEN.pattern) & t.str.contains('[A-F]', regex=True)).to_numpy()
        if m.any():
            if out is None: out = df.copy()
            out.iloc[m, i] = t[m].str.strip().str.lower().to_numpy()
    return df if out is None else out


def _excel_yaz_genel(sayfalar, dosya):
    """sayfalar: [(sekme adı, [df, df, ...])] — aynı sekmedeki tablolar arasında 2 boş satır bırakılır."""
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font, PatternFill
    wb = Workbook(write_only=True)
    kalin = Font(bold=True)
    dolgu = {k: PatternFill('solid', fgColor=v) for k, v in _SEVIYE_RENK.items()}
    for ad, bloklar in sayfalar:
        bloklar = [idleri_kucult(b) for b in bloklar if isinstance(b, pd.DataFrame)]
        if not bloklar: continue
        ws = wb.create_sheet(ad[:31])
        toplam = sum(len(b) for b in bloklar)
        print(f"📝 Excel yazılıyor: {ad} ({toplam:,} satır)".replace(',', '.'))
        for bi, d in enumerate(bloklar):
            if bi: ws.append([]); ws.append([])
            bas = []
            for c in d.columns:
                h = WriteOnlyCell(ws, value=str(c)); h.font = kalin; bas.append(h)
            ws.append(bas)
            if d.empty: continue
            sev = list(d.columns).index('Seviye') if 'Seviye' in d.columns else -1
            o = d.replace([np.inf, -np.inf], np.nan).astype(object)
            o = o.where(o.notna(), None)
            for i, r in enumerate(o.itertuples(index=False, name=None), 1):
                r = list(r)
                if sev >= 0 and r[sev] in dolgu:
                    h = WriteOnlyCell(ws, value=r[sev]); h.fill = dolgu[r[sev]]; r[sev] = h
                ws.append(r)
                if i % 25000 == 0:
                    print(f"   {i:,} / {len(o):,} satır".replace(',', '.'))
    print("📝 Excel dosyası kaydediliyor...")
    wb.save(dosya)
    print("✅ Excel hazır")


# ------------------------------------------------------------------ dosya tanıma
def _norm(x):
    return re.sub(r'[^a-z0-9]', '', str(x).translate(str.maketrans('ıİşŞğĞüÜöÖçÇ', 'iissgguuoocc')).lower())


def _baslik_satirlari(yol, n=8):
    ham = open(yol, 'rb').read(4096)
    if ham[:2] == b'PK':
        import openpyxl
        wb = openpyxl.load_workbook(yol, read_only=True, data_only=True)
        try:
            ws = wb.worksheets[0]
            return [[c for c in r if c is not None] for r in ws.iter_rows(min_row=1, max_row=n, values_only=True)]
        finally:
            wb.close()
    ham = open(yol, 'rb').read(65536)
    metin = ''
    for kod in (('utf-16',) if ham[:2] in (b'\xff\xfe', b'\xfe\xff') else ('utf-8-sig', 'cp1254', 'latin-1')):
        try: metin = ham.decode(kod, errors='ignore'); break
        except Exception: continue
    satirlar = metin.splitlines()[:n]
    ayr = '\t' if satirlar and '\t' in satirlar[0] else (';' if satirlar and satirlar[0].count(';') > satirlar[0].count(',') else ',')
    return [r.split(ayr) for r in satirlar]


def tani(yol, ad='', urun='amb'):
    """Dosyanın türünü kolon başlıklarından (bulamazsa dosya adından) bulur."""
    imzalar = URUNLER[urun]['imzalar']
    try:
        satirlar = _baslik_satirlari(yol)
    except Exception as e:
        return json.dumps({'rol': None, 'neden': f'okunamadı: {e}'})
    hucreler = [_norm(c) for r in satirlar for c in r if str(c).strip()]
    for rol, kolonlar, _ in imzalar:
        if kolonlar and all(any(_norm(k) in h for h in hucreler) for k in kolonlar):
            return json.dumps({'rol': rol, 'neden': 'kolonlar'})
    a = _norm(ad)
    for rol, _, kelimeler in imzalar:
        if any(k in a for k in kelimeler):
            return json.dumps({'rol': rol, 'neden': 'dosya adı'})
    return json.dumps({'rol': None, 'neden': 'tanınmadı'})


# ------------------------------------------------------------------ çıktı yardımcıları
def _t(v):
    if v is None: return None
    if isinstance(v, (bool, np.bool_)): return bool(v)
    if isinstance(v, (int, np.integer)): return int(v)
    if isinstance(v, (float, np.floating)):
        v = float(v)
        return None if (math.isnan(v) or math.isinf(v)) else round(v, 4)
    if isinstance(v, (pd.Timestamp, np.datetime64)):
        try: return pd.Timestamp(v).strftime('%d.%m.%Y')
        except Exception: return None
    try:
        if pd.isna(v): return None
    except Exception: pass
    return str(v)

def _sf(x):
    try:
        x = float(x); return 0.0 if math.isnan(x) else x
    except Exception: return 0.0

def _pct(a, b):
    return (a / b * 100) if b else 0.0

def _tablo(kolonlar, satirlar):
    return {'kolonlar': kolonlar, 'satirlar': [[_t(v) for v in r] for r in satirlar]}

def _df_tablo(d, kolonlar=None, sinir=2000):
    if not isinstance(d, pd.DataFrame): return {'kolonlar': kolonlar or [], 'satirlar': []}
    if kolonlar: d = d[[c for c in kolonlar if c in d.columns]]
    return {'kolonlar': [str(c) for c in d.columns],
            'satirlar': [[_t(v) for v in r] for r in d.head(sinir).itertuples(index=False, name=None)]}


class Kontrol:
    def __init__(self): self.K = []
    def ekle(self, grup, ad, durum, ozet, aciklama='', kolonlar=None, satirlar=None):
        satirlar = [[_t(v) for v in r] for r in (satirlar or [])]
        self.K.append({'grup': grup, 'ad': ad, 'durum': durum, 'ozet': ozet, 'aciklama': aciklama,
                       'kolonlar': kolonlar if satirlar else None, 'satirlar': satirlar[:300] if satirlar else None,
                       'sayi': len(satirlar)})
    def liste(self, grup, ad, ogeler, durum, aciklama, birim='depo', ok='Tümünde var', kolonlar=('Depo',)):
        ogeler = list(ogeler)
        self.ekle(grup, ad, durum if ogeler else 'ok', f'{len(ogeler)} {birim}' if ogeler else ok, aciklama,
                  list(kolonlar), [x if isinstance(x, (list, tuple)) else [x] for x in ogeler])
    def gunluk(self, log, grup='Hesap günlüğündeki uyarılar'):
        son = None
        for satir in log.split('\n'):
            s = satir.strip()
            if not s: continue
            if s.startswith('⚠') or s.startswith('🚨') or s.startswith('❌'):
                metin = re.sub(r'^(⚠️|⚠|🚨|❌)\s*', '', s)
                son = {'grup': grup, 'ad': metin, 'durum': 'uyari' if s.startswith('⚠') else 'hata', 'ozet': '', 'aciklama': '',
                       'kolonlar': ['Kayıt'], 'satirlar': [], 'sayi': 0}
                self.K.append(son)
            elif son is not None and satir.startswith('   ') and s.startswith('-'):
                son['satirlar'].append([s.lstrip('- ').strip()]); son['sayi'] += 1
            else:
                son = None
        for k in self.K:
            if k['grup'] == grup:
                if not k['satirlar']: k['satirlar'] = None; k['kolonlar'] = None
                else: k['ozet'] = f"{k['sayi']} kayıt"


def depo_ozeti(df, depo, oneri, final, kesilen, neden, ekler=None, tip=None, sistem=None, sirala=True):
    """Depo tablosu: öneri, final, kesilen, kesinti %, ana neden + ürüne özel kolonlar."""
    g = df.groupby(depo).agg(o=(oneri, 'sum'), f=(final, 'sum'), k=(kesilen, 'sum'))
    kk = df[df[kesilen] > 0]
    ana = (kk.groupby([depo, neden])[kesilen].sum().reset_index().sort_values(kesilen)
             .groupby(depo).last()[neden]) if len(kk) else pd.Series(dtype=str)
    ilk = df.groupby(depo).first()
    kol = ['Depo'] + (['Tip'] if tip else []) + (['Sistem'] if sistem else []) + ['Öneri', 'Final', 'Kesilen', 'Kesinti %', 'Ana neden']
    ek_kol = [a for a, _ in (ekler or [])]
    satir = []
    for a, r in g.iterrows():
        x = [str(a)]
        if tip: x.append(ilk.loc[a, tip] if tip in ilk.columns else None)
        if sistem: x.append(ilk.loc[a, sistem] if sistem in ilk.columns else None)
        x += [r['o'], r['f'], r['k'], round(_pct(r['k'], r['o']), 1), ana.get(a, '')]
        x += [fn(a) for _, fn in (ekler or [])]
        satir.append([_t(v) for v in x])
    if sirala:
        ki = kol.index('Kesilen'); satir.sort(key=lambda s: -(s[ki] or 0))
    return {'kolonlar': kol + ek_kol, 'satirlar': satir}


def neden_ozeti(df, depo, kesilen, neden):
    kk = df[df[kesilen] > 0]
    top = float(kk[kesilen].sum())
    nd = kk.groupby(neden).agg(depo=(depo, 'nunique'), kes=(kesilen, 'sum')).sort_values('kes', ascending=False)
    return [{'ad': i, 'depo': int(r['depo']), 'kes': float(r['kes']), 'pay': _pct(float(r['kes']), top)} for i, r in nd.iterrows()]


# Öneri uyarısı: kesim sırasını değiştirmez, yalnız ekranda işaretler.
_ASIRI_KAT = 5.0
_ASIRI_MIN_DEPO = 5
_ASIRI_MIN_ONERI = 10.0
_ASIRI_COVER_GUN = 30.0
_ASIRI_SINIR = 5000

def _asiri_oneri(df, depo, urun, ad, oneri, fc, birim='adet', tip=None, batch='Order batch size'):
    """Aynı ürün aynı tip depolar (G10 / GB ayrı) arasında medyanın 5 katı, ya da önerinin kendisi 30 günden fazla satış."""
    d = pd.DataFrame({
        'depo': df[depo].astype(str),
        'urun': df[urun].astype(str),
        'ad': df[ad].astype(str),
        'oneri': pd.to_numeric(df[oneri], errors='coerce').fillna(0),
        'fc': pd.to_numeric(df[fc], errors='coerce').fillna(0),
        'batch': pd.to_numeric(df[batch], errors='coerce') if batch in df.columns else np.nan,
    })
    if tip: d['tip'] = df[tip].astype(str)
    d['dt'] = df['Domain Type'].astype(str).str.strip().str.upper() if 'Domain Type' in df.columns else ''
    poz = d[d['oneri'] > 0].copy()
    baslik_kol = (['Depo', 'Depo tipi', 'Ürün', 'Tür'] if tip else ['Depo', 'Depo tipi', 'Ürün']) + ['Öneri', 'Batch', 'Batch katı', 'Günlük satış', 'Öneri gün', 'Medyan', 'Kat', 'Uyarı']
    kural = (f'Kesime karışmaz. Medyan G10 ve GB depolar için ayrı hesaplanır (yalnız önerisi olan depolar). '
             f'Aynı ürün aynı tipte en az {_ASIRI_MIN_DEPO:g} depoda önerildiyse medyanın {_ASIRI_KAT:g} katını aşan satırlar, '
             f'ya da önerinin kendisi {_ASIRI_COVER_GUN:g} günden fazla satışa denk gelenler. Birim: {birim}.')
    if poz.empty:
        kart = {'baslik': 'Aşırı yüksek öneriler', 'alt': kural, 'ozet': '', 'tablo': _tablo(baslik_kol, []),
                'vurgu': 'Öneri', 'link': 'Depo', 'bos': 'Bu kurala uyan satır yok.'}
        return {'kart': kart, 'kontrol': {'grup': 'Öneri kontrolü', 'ad': 'Aşırı yüksek öneri', 'durum': 'ok', 'ozet': 'Yok',
                                          'aciklama': '', 'kolonlar': None, 'satirlar': None, 'sayi': 0}}
    poz['med'] = poz.groupby(['dt', 'urun'])['oneri'].transform('median')
    poz['cnt'] = poz.groupby(['dt', 'urun'])['oneri'].transform('count')
    poz['kat'] = poz['oneri'] / poz['med'].replace(0, np.nan)
    poz['gun'] = np.where(poz['fc'] > 0, poz['oneri'] / poz['fc'], np.nan)
    m_med = (poz['cnt'] >= _ASIRI_MIN_DEPO) & (poz['oneri'] >= _ASIRI_MIN_ONERI) & (poz['kat'] > _ASIRI_KAT)
    m_gun = (poz['fc'] > 0) & (poz['oneri'] >= _ASIRI_MIN_ONERI) & (poz['gun'] > _ASIRI_COVER_GUN)
    uy = poz[m_med | m_gun].sort_values('oneri', ascending=False)
    def _uyari(r):
        parca = []
        if r['cnt'] >= _ASIRI_MIN_DEPO and r['oneri'] >= _ASIRI_MIN_ONERI and r['kat'] > _ASIRI_KAT:
            parca.append(f"medyanın {r['kat']:.1f} katı".replace('.', ','))
        if r['fc'] > 0 and r['oneri'] >= _ASIRI_MIN_ONERI and r['gun'] > _ASIRI_COVER_GUN:
            parca.append(f"{r['gun']:.0f} gün satış")
        return ' · '.join(parca)
    satir = []
    for _, r in uy.iterrows():
        x = [r['depo'], r['dt'], r['ad']]
        if tip: x.append(r['tip'])
        b = r['batch'] if pd.notna(r['batch']) and r['batch'] > 0 else None
        x += [r['oneri'], b, (r['oneri'] / b) if b else None, r['fc'], None if pd.isna(r['gun']) else r['gun'], r['med'], r['kat'], _uyari(r)]
        satir.append(x)
    goster = satir[:_ASIRI_SINIR]
    alt = kural + (f' Tabloda önerisi en yüksek {_ASIRI_SINIR} satır.' if len(satir) > _ASIRI_SINIR else '')
    kart = {'baslik': 'Aşırı yüksek öneriler', 'alt': alt,
            'ozet': f"{len(satir)} satır · {uy['urun'].nunique()} ürün",
            'tablo': _tablo(baslik_kol, goster), 'vurgu': 'Öneri', 'link': 'Depo', 'bos': 'Bu kurala uyan satır yok.'}
    kontrol = {'grup': 'Öneri kontrolü', 'ad': 'Aşırı yüksek öneri', 'durum': 'uyari' if satir else 'ok',
               'ozet': f'{len(satir)} satır' if satir else 'Yok', 'aciklama': kural if satir else '',
               'kolonlar': baslik_kol if satir else None,
               'satirlar': [[_t(v) for v in r] for r in goster] if satir else None, 'sayi': len(satir)}
    return {'kart': kart, 'kontrol': kontrol}


# Fazla stok şüphesi: Relex önerisi + eldeki stok + açık sipariş (adet), aynı ürün aynı tip depolar (G10 / GB ayrı)
# arasında karşılaştırılır. Üst sınır = 3. çeyrek + kat × (3. çeyrek − 1. çeyrek); uçtaki birkaç depo sınırı genişletmez.
# Yalnız bugün önerisi olan satırlar uyarılır. Kesime karışmaz. Sıfıra çekilen (PTZ) ve demirbaş ürünler hariç.
_FAZLA_KAT = 1.5
_FAZLA_MIN_DEPO = 8
_FAZLA_SINIR = 5000

def _fazla_stok(df, depo, urun, ad, oneri, birim='adet', batch='Order batch size'):
    sayi = lambda k: pd.to_numeric(df[k], errors='coerce').fillna(0) if k in df.columns else pd.Series(0.0, index=df.index)
    haric = pd.Series(False, index=df.index)
    if 'Cut_Priority' in df.columns: haric |= pd.to_numeric(df['Cut_Priority'], errors='coerce') == 101
    if 'Pick-to-zero' in df.columns: haric |= pd.to_numeric(df['Pick-to-zero'], errors='coerce').fillna(0) == 1
    if 'Is_Water' in df.columns: haric |= df['Is_Water'].fillna(False).astype(bool)     # su ürünleri (Ambient) analize girmez
    tip = df['Domain Type'].astype(str).str.strip().str.upper() if 'Domain Type' in df.columns else pd.Series('', index=df.index)
    d = pd.DataFrame({'depo': df[depo].astype(str), 'urun': df[urun].astype(str), 'ad': df[ad].astype(str), 'tip': tip,
                      'oneri': sayi(oneri), 'eb': sayi('End balance'), 'po': sayi('Open purchase orders'), 'fc': sayi('Daily FC'),
                      'batch': pd.to_numeric(df[batch], errors='coerce') if batch in df.columns else np.nan})
    d = d[~haric & d['tip'].isin(['G10', 'GB'])]
    d = d.groupby(['tip', 'urun', 'depo'], as_index=False).agg(ad=('ad', 'first'), oneri=('oneri', 'sum'), eb=('eb', 'sum'),
                                                               po=('po', 'sum'), fc=('fc', 'max'), batch=('batch', 'max'))
    d['top'] = d['oneri'] + d['eb'] + d['po']
    d['cover'] = np.where(d['fc'] > 0, d['top'] / d['fc'].where(d['fc'] > 0), np.nan)
    kol = ['Depo', 'Ürün', 'Batch', 'Relex öneri', 'Batch katı', 'Eldeki stok', 'Açık sipariş', 'Toplam',
           'Grup medyanı', 'Medyanın katı', 'Cover gün', 'Grup medyan cover']
    kural = (f'Toplam = Relex önerisi + eldeki stok + açık sipariş ({birim}). Grup medyanı: aynı ürünün aynı tip depolarındaki (G10 / GB ayrı) '
             f'toplamlarının ortanca değeri. Toplamı grubun genelinden belirgin yüksek olan (orta yarının üst ucunu, bu bandın {_FAZLA_KAT:g} katından fazla aşan) '
             f've bugün önerisi olan satırlar listelenir; ürün o tipte en az {_FAZLA_MIN_DEPO} depoda olmalı. Batch katı = öneri ÷ batch. '
             f'Cover yalnız bilgi için. Su, PTZ ve demirbaş hariç. Kesime karışmaz.')
    kol = kol[:1] + ['Depo tipi'] + kol[1:]
    kartlar, kontroller, satir = [], [], []
    for t in ('G10', 'GB'):                      # sınırlar her tip için ayrı, tablo tek
        dt = d[(d['tip'] == t) & (d['top'] > 0)]
        for u, g in dt.groupby('urun'):
            if g['depo'].nunique() < _FAZLA_MIN_DEPO: continue
            q1, med, q3 = g['top'].quantile([0.25, 0.5, 0.75]).tolist()
            ust = q3 + _FAZLA_KAT * max(q3 - q1, 0.25 * med, 1.0)
            mc = g['cover'].median(skipna=True)
            for _, r in g[(g['top'] > ust) & (g['oneri'] > 0)].iterrows():
                b = r['batch'] if pd.notna(r['batch']) and r['batch'] > 0 else None
                satir.append([r['depo'], t, r['ad'], b, r['oneri'], (r['oneri'] / b) if b else None, r['eb'], r['po'], r['top'],
                              med, (r['top'] / med) if med > 0 else None, None if pd.isna(r['cover']) else r['cover'],
                              None if pd.isna(mc) else mc])
    satir.sort(key=lambda x: -(x[10] or 0))
    toplam_uyari = len(satir)
    goster = satir[:_FAZLA_SINIR]
    alt = kural + (f' Tabloda medyanın katı en yüksek {_FAZLA_SINIR} satır.' if len(satir) > _FAZLA_SINIR else '')
    tipler = {x[1] for x in satir}
    kartlar.append({'baslik': 'Fazla stok şüphesi', 'alt': alt,
                    'ozet': (f"{len(satir)} ürün-depo · {len({x[2] for x in satir})} ürün · " + ' · '.join(f"{t} {sum(1 for x in satir if x[1] == t)}" for t in ('G10', 'GB') if t in tipler)) if satir else '',
                    'tablo': _tablo(kol, goster), 'vurgu': 'Medyanın katı', 'link': 'Depo', 'bos': 'Grubun dışına taşan ürün-depo yok.'})
    sifir = d[(d['oneri'] > 0) & (d['fc'] <= 0)].sort_values(['tip', 'depo'])
    sk = ['Depo', 'Depo tipi', 'Ürün', 'Batch', 'Relex öneri', 'Eldeki stok']
    ss = [[r['depo'], r['tip'], r['ad'], r['batch'] if pd.notna(r['batch']) else None, r['oneri'], r['eb']] for _, r in sifir.iterrows()]
    kartlar.append({'baslik': 'Relex önerisi var ama satış tahmini 0', 'alt': 'Günlük satış tahmini boş ya da 0 olduğu halde öneri gelen satırlar. Bu satırlarda cover hesaplanamaz.',
                    'ozet': f'{len(ss)} ürün-depo' if ss else '', 'tablo': _tablo(sk, ss[:300]), 'vurgu': 'Relex öneri', 'link': 'Depo',
                    'bos': 'Böyle bir satır yok.'})
    toplam_uyari += len(ss)
    return {'kartlar': kartlar, 'kontrol': kontroller, 'sayi': toplam_uyari}


# Büyük öneri uyarısı (10.11.2026). Kesime karışmaz, yalnız ekranda.
#  Hacim: öneri hacmi (öneri × birim hacim) > ürünün girdiği dolabın hacmi × eşik (pay ve buffer öncesi dolap hacmi).
#  Adet:  öneri > Relex '14 Days Sales'; 14 günlük satış batch'ten küçükse uyarı yok (batch zorunlu).
#  Önerisi 1 batch ya da altında olan satırlar hiç değerlendirilmez. Demirbaş, su ve Beypazarı ürünleri hariç; PTZ dahil.
_BUYUK_ESIK = {'Ambient': 0.005, 'Other': 0.02, 'ETB': 0.05, 'MS +4': 0.05, 'MS 8-12': 0.05}
_BUYUK_HARIC_URUN = ('beypazar',)
_BUYUK_SINIR = 5000

def _buyuk_oneri(df, depo, ad, q, q_hacim, birim_hacim, dolap, kap, birim='adet', adet_haric=None, batch='Order batch size'):
    """q: Relex öneri; q_hacim: hacim için miktar; birim_hacim, kap: L; dolap: satırın dolap adı (_BUYUK_ESIK anahtarı, yoksa hacim kuralı yok)."""
    df = df.reset_index(drop=True); idx = df.index        # seriler df ile aynı sırada gelir; konuma göre hizalanır
    hiza = lambda s: pd.Series(np.asarray(s), index=idx) if isinstance(s, (pd.Series, np.ndarray)) else pd.Series(s, index=idx)
    sayi = lambda s: pd.to_numeric(hiza(s), errors='coerce') if s is not None else pd.Series(np.nan, index=idx)
    q = sayi(q).fillna(0); q_hacim = sayi(q_hacim).fillna(0); birim_hacim = sayi(birim_hacim).fillna(0); kap = sayi(kap)
    dolap = hiza(dolap)
    if adet_haric is not None: adet_haric = hiza(adet_haric).fillna(False).astype(bool)
    b = (pd.to_numeric(df[batch], errors='coerce') if batch in df.columns else pd.Series(1.0, index=idx)).fillna(1).clip(lower=1)
    haric = pd.Series(False, index=idx)
    if 'Cut_Priority' in df.columns: haric |= pd.to_numeric(df['Cut_Priority'], errors='coerce') == 101
    if 'Is_Water' in df.columns: haric |= df['Is_Water'].fillna(False).astype(bool)
    urun_adi = (df['Product name'] if 'Product name' in df.columns else df[ad]).astype(str).str.lower()
    for k in _BUYUK_HARIC_URUN: haric |= urun_adi.str.contains(k, regex=False)
    aday = (q > b) & ~haric
    esik = dolap.map(_BUYUK_ESIK)
    hacim = q_hacim * birim_hacim
    pay = (hacim / kap.where(kap > 0))
    m_h = aday & esik.notna() & pay.notna() & (pay > esik)
    var14 = '14 Days Sales' in df.columns
    s14 = pd.to_numeric(df['14 Days Sales'], errors='coerce') if var14 else pd.Series(np.nan, index=idx)
    m_a = aday & s14.notna() & (s14 >= b) & (q > s14)
    if adet_haric is not None: m_a &= ~adet_haric
    m = m_h | m_a
    tip = df['Domain Type'].astype(str).str.strip().str.upper() if 'Domain Type' in df.columns else pd.Series('', index=idx)
    kol = ['Depo', 'Depo tipi', 'Ürün', 'Dolap', 'Uyarı', 'Relex öneri', 'Batch', 'Batch katı', '14 gün satış', 'Öneri / 14 gün satış',
           'Öneri hacmi L', 'Dolap hacmi L', 'Dolabın %', 'Eşik %']
    satir = []
    for i in idx[m]:
        uy = ' + '.join(a for a, v in (('Hacim', m_h[i]), ('Adet', m_a[i])) if v)
        s = s14[i]; p = pay[i]; e = esik[i]
        satir.append([str(df.at[i, depo]), tip[i], str(df.at[i, ad]), dolap[i] if pd.notna(dolap[i]) else '', uy, q[i], b[i], q[i] / b[i],
                      None if pd.isna(s) else s, (q[i] / s) if pd.notna(s) and s > 0 else None,
                      hacim[i] if hacim[i] > 0 else None, None if pd.isna(kap[i]) else kap[i],
                      None if pd.isna(p) else p * 100, None if pd.isna(e) else e * 100])
    satir.sort(key=lambda x: (-(x[12] / x[13]) if x[12] is not None and x[13] else 0, -(x[9] or 0)))
    esik_metin = ', '.join(f"{k} %{v * 100:g}".replace('.', ',') for k, v in _BUYUK_ESIK.items())
    kural = (f'Kesime karışmaz. Hacim: öneri hacmi, ürünün girdiği dolabın hacminin (pay ve buffer öncesi) eşiğinden büyük ({esik_metin}). '
             f"Adet: öneri, Relex '14 Days Sales' değerinden büyük; 14 günlük satış batch'ten küçükse uyarı verilmez. "
             f'Önerisi 1 batch ya da altında olan satırlar değerlendirilmez. Demirbaş, su ve Beypazarı hariç; PTZ dahil. Birim: {birim}.')
    if not var14: kural += " Relex dosyasında '14 Days Sales' kolonu yok, adet kuralı uygulanmadı."
    goster = satir[:_BUYUK_SINIR]
    alt = kural + (f' Tabloda ilk {_BUYUK_SINIR} satır.' if len(satir) > _BUYUK_SINIR else '')
    nh = sum(1 for x in satir if 'Hacim' in x[4]); na = sum(1 for x in satir if 'Adet' in x[4])
    kart = {'baslik': 'Büyük öneriler (hacim / 14 gün satış)', 'alt': alt,
            'ozet': f"{len(satir)} ürün-depo · hacim {nh} · adet {na} · {len({x[0] for x in satir})} depo" if satir else '',
            'tablo': _tablo(kol, goster), 'vurgu': 'Dolabın %', 'link': 'Depo', 'bos': 'Bu kurala uyan satır yok.'}
    return {'kart': kart, 'sayi': len(satir)}


def satir_detay(df, kolonlar, filtre):
    """Depo detayındaki ürün satırları: [(başlık, kolon)]"""
    d = df[filtre]
    return {'kolonlar': [a for a, _ in kolonlar],
            'satirlar': [[_t(v) for v in r] for r in d[[k for _, k in kolonlar]].itertuples(index=False, name=None)]}


# ------------------------------------------------------------------ merkez tespiti (çıktı adı)
# Çıktı adı (Excel, parquet, All PL bölgesi) kullanıcıdan alınmaz: ana tablodaki cep depolar haritayla eşlenir,
# depoların MERKEZ_ESIK'ten fazlası tek merkeze düşüyorsa ad o merkezdir. Tanınmazsa ad yalnız o koşu için
# arayüzden elle girilir (merkez_elle); o da yoksa çıktı 'Merkez tanınmadı' adıyla yazılır.
# Harita merkez_haritasi.py ile Parquet Arşiv'den üretilir (kategori → merkez → boşlukla ayrılmış Location code).
# >>> MERKEZ HARİTASI (merkez_haritasi.py üretir: Parquet Arşiv 03.11.2026–16.11.2026; elle düzenleme)
MERKEZ_HARITA_DONEM = '03.11.2026–16.11.2026'
MERKEZ_HARITA = {
    'Ambient ve Su': {
        'Adana': '5fa3ab297a34243da20e90e9 5fa3af888994630469b0af82 5fa3b48a344d8b224374c700 5fa3b55066c23f725aa963af 5fa3b67e9a4f7e54cfab2db1 5fa3b7b8bd17e5f8bd17abf4 5fa5343c4af4b40b7654a1b5 5fa5350f3dd375165ed98b15 5fa536176f8ab748d0a0bb02 5fa5869f4ef85c0bd63857e2 5ffc046075e59200ad24d165 5ffc066f983d9e559136bdf7 5ffc07613a999b117c0bffd6 6087bf1316eedb9ca2517c2f 608e76b7735e47bf71af4793 608e79b439d8e35fe3475666 60b4d13088495730ee368741 60e856cb5826f42d01cc4b53 61028f6f56b9217970b46856 611ba63773aba83977b71e4b 612366bdd3315536b6d52137 61236856ca4b682239921cf3 61250310ba320f26c3e13065 6126090153c5182a9b01a299 613606bff8fb19235345566d 61377d9d4fc9a06ccfe7169f 614350643feefe1f24c45a6d 6148aa3e30b116475c4ec042 61556bc51033c21caef34e3e 615adff58af0674d8e6bbf19 615d7e6f92350b67ff15cb7b 61656002b641dc5b1df752e5 6177b30a7e40476d70a76a3c 617ff66f0ac855a85ec5c87a 619215be517008a82fc4dd5a 61cd5cfd524c4a10e7a4f199 68c129dbbadec12eddea7b3e',
        'Ankara': '5dcafe63e2c61b1e52cf1703 5dcafe6ae2c61b1e52cf1704 5dcafe71e2c61b1e52cf1705 5dcafe78e2c61b1e52cf1706 5dcafe7ee2c61b1e52cf1707 5dcafe85e2c61b1e52cf1708 5dcafe8be2c61b1e52cf1709 5dcafe90e2c61b1e52cf170a 5dcafe95e2c61b1e52cf170b 5dcafe9be2c61b1e52cf170c 5dcafea1e2c61b1e52cf170d 5dfb5587810db101416b794a 5e2dfcdb61df150a60e44ec4 5e50fb25bf9147d76677062d 5e5e4442ef84bd09f36e2732 5edf897f9bf0ab78c42aa0c5 5f0da3a92667170e4214f570 5f100d48000896470fbc6985 5f3f838dcdf7eb5b23d165aa 5f43709ae11e3f851d372de7 5f4371f6b8cc51b6b90cabbe 5f55f386cde1145a4abe40fe 5f7ffdbe55de059f4eb3d96c 5f80649315df6274324209e1 5f817f23649ab4419edcc6f4 5f8c2c74d66856bd8990c41e 5fa3a5a3920ea19e651b25f8 5fa3aa437a342489b70e90e8 5fa506a9aae05af1ea3b508c 5fa5090fec4ec10a14b3cc83 5fa9024a362af02e605c6cf7 5faa3bea7a3424ad240e90ea 5faa85a87a342446b30e90eb 5faa871a3a765ee02b1b72ca 5fbcbd814410e600316a850c 5fbe2f736b630ed66efae5da 5fd1c2ef6fcb7d40917b65ab 5fd5eebdd00a8b222ee6dde5 5fe60830544aa61d591ea44c 5fedde1f8bafd40f79fd45b7 5ffc124fe61279362b93d895 5ffc18b45fdd9e80bae58282 6012a9337421845f2dc0c24f 602d2ceefff95e357d2499a3 602d30b91b34076d2ac7a0da 602d3517d4178d42e6976477 606ff6c264b638409c2f84a6 606ffe31f4105254043f6734 60a3644d1308681278e3de0f 60b9cbd56e86745b690c2abc 60b9cfb4caff94a532ca8e5e 60b9d12581867555ef18bb24 60b9d6bf692579cec6cf9370 60c867a471a4c6225da8e9f0 60c86a81afa0f6425709556a 60c86d684f0a906427e021f5 60c86e90ebd4cafcdd51640b 60d9bd679b269b13dac3c7d1 60d9c4aff1ac4b139bb8c282 60d9c64046bc18552f2590cb 60dac37b7115b0cf4b0163f0 60dc0faffe79bf3f09819119 60dc5b8aa15c7c637cdd0a0c 60ebdac160fa57ace15f6328 60eecd3e355486b4e4302ff2 6113e4b472a14356efd2c990 611baa43af0d808427cefdfa 611babe242f6d07dba2fa1cb 611bb7fbb43df448d3e2bada 611e4f00d48216954301c0ca 611e5455fefdedc56cf75476 612361f16ea1455c4a2d82d0 61236338949bc9f222b0a07a 61236594c75decba7bf48c21 612605f152be9f5c74862efd 61360a9b1c71cf78b9aca448 61360b91d943bd4628033a91 61360d7dd3315533fcd52138 613641b277617778fc2fb413 6148ab5841e4921871ca1fd1 6148ac8730b11672564ec043 6148b4ed7d1100f536384c48 6148bba9b9cf1d2d80362582 614b2a1291d75dc425dec45f 615171338350531ed677dc6c 6155568be422814a367f1520 615b14be87ea9f7e86d4d30e 615c6be8d2e32cf51c75dcd3 615d67d61c340575d0102ac0 61655c8daf0c0273d81ff922 616a786b09c2e7526101b676 616d7f71d4ad4289b6256bd2 616d98ff408ef42f0a1a8ede 617150e61bd2eb07c342bfb3 617152cf8cfe47d79e37f5b6 617156b6bc027cbc6d6979ee 6171575f7d436a77816396d8 6171d10371872e44da7058f5 6176c0455fc28348742218c8 6176c1d6593a60e5937db788 6176c31c96be3fdb17efc26e 6176d46cbc027c712b04ca5d 6176d7f81bd2eb2843e1a420 6176de0f1eee7aa571e3262e 6179ce9f0ba80c36c6913d68 6179d020b9145f409ffda8df 6182b2bb6a5ab66908153c4a 618d1d1cabb358578c9b6bea 61920ea872f8b1f33b914fa7 619221571561be055a6d27b5 61b83c6124c2ab2d369e8453 61f9465a4f2b0a4ddff51884 620208534eb9cc5ed4f3935e 64a7e9c63bb10751c4a76dde 6527f60cddfe60856b14e3a0 65292e33c39e013a7f34dc68 65a11c9282048f4d55a52a41 69d4f6a06522d844f0ec99ee',
        'Arnavutköy': '555cc03c56861c0c00a0bd9b 55646fc47051560c00cc8398 556f0bee1ad7b80c002d44a7 5577f739d8631b0c00fb4b70 56407e825316580c0058c41b 5659d6f23c84c20c003cd032 57bc2fcb851ebd0300209bcf 57bc3760312bf20300ea04f2 57bf38ac96a6b403008227bb 57ea95d7aa27f80300ee9f3b 57ea9884aa27f80300eea12f 57fb617589145b0003a485c5 57ff667348532700039caa58 582b18cf4756f60004e3ea56 584abc3e30c09e0004e0c719 585b9935dcd4ec0004985f9c 586a31f3dc795000045aadf1 587349a7ed1bc700048bda90 587cbf1c56a47000048c16cc 58b4312f292ee600049fc76b 58b432cc292ee600049fc8d7 5a33e25d46ceb9000405f563 5aaa896d0c434d0004db55f0 5b83c4d364195f000456cfbf 5c05793e6ea39a08b22a9616 5c0eaca4110e9a1422c26129 5c20c943f133550001a9e657 5c38ebf04b149200011a4d25 5c4eeb55c1b0120001d7d1ee 5c6e53345b6cb20001bb2602 5cff880339a6920001a3328e 5d5d3c8bd851c00001604c7a 5d62fe0fda5b2d0001bd7fdc 5d692a0c51d774000190e4b2 5d692c6c51d774000190e7cf 5d692df23ebe9000019f2338 5d6e993df4c0350001cb440c 5d6ea5e2f4c0350001cb6011 5d78fa53d555790001fe1fc6 5daee08d730fa8dcf50e3227 5db1f19a0ca56b6f8ac73357 5db9759777a0c71180d7694c 5dd4d68847ab01f7fe3fab98 5dd4d6b547ab010e543fabc9 5dd4d6e147ab01f8d73fabf3 5e6a52ce9e4a6171bb22138e 5e6a572c370b07f1fe12088b 5e6a5825badef2d6e8e19cc2 5e7caaf3a94bbe1adc0d4351 5ea84a1b5896811da091565a 5ea93197776bc1a61a88834e 5eb91e0e40f34feed12d2caf 5ecce6aed2d088aa303221c7 5ee747a92b721c4a2f0de53c 5ee749c32b721cbc680de53d 5ee758226979ef7916643f8a 5ee91204d610549cd90a70d0 5efae8a1c45863487c3ae43c 5efb1d555c8d89a45b94c0fd 5f00419233bec1f8ec2f649d 5f089231dc2c2249d9c9cd7f 5f1007924726a52024fb827f 5f1849c2344af3b6a59b3737 5f28fdff5435c7100b4925c9 5f3f8922dca1057336bd6f6b 5f59e022415eff6d6a7fa0f4 5f72d5f7f1ec3bf53b4bae69 5f8580e6aea5a66ce8148f41 5fae8e6abbe9c45991e4c843 5fd275d27535bcdb9185792c 5fd31533d00a8b05cae6dde3 5fd3189e22d57c0dfa4b0683 5fdb394efd3ebc19897ba6b2 5fdb3b4022d57ca4ee4b0684 5fdb3c3a22d57c6d464b0685 5fdb8a4893c419757f7cb4bf 5feddbe6d472305103600f37 5ffee39ce945a31027220718 602164b86c81807d77b002a2 6030f77b85488486f1d8993b 60544f4df4105265c33f6725 606ffab1adac710b11db5cb5 6087d50638df2aea7b6b6f56 60b4d00f6a99764d6e2f8c0c 60c86ff1e15538b288b76a2d 60cb3458ad2dda5f1fa74d74 60d9bdb373f63934d95dca42 60dc2b0a46bc18b8fd2590cc 60dc2d729274842deeb4c720 60dc2f06aa4bc1e20ddda909 60f5bd4d1308d356fac9a034 61234230a2f72885762cfa60 614344ae79244a7c3588ccad 61434633f7bee7266005efe6 614d882a6b32fbcc536728d1 614da622e4228142317f151b 6155b76809f1d7185b1b3123 615ab6870e29d7447226037b 615ab7ab8dc4b3e0efb75f38 6167f4d4d527d44f104670bf 61702483173bd6168261a927 6171d0347d436a6e9576a591 61784e7071872e09f21ce6c5 617fb16458878a6087255267 618bce2e36ec848950d31987 61921256b5e36f47d11a5bf4 61a743d0831d321398ea1cab 61cd5d428c1b5c2b8683866a 61dc5ca117387455d505df5f 61e816d5c56baff787168946 61f15ff630ef213cbbdee81d 62138f1395913b66bec83f12 6217b6e67b7ea62263223e76 628374d59226f29007574532 64c9ead121b2bc937dd5c630 64e746bfe4b9d5860521d176 65b90e1cbf4377207c34499e 66473b6870415cfd9f145ea0 66ff90b844d68882d5b84dc2',
        'Diyarbakır': '610a8fe4c7e089531ddeafe5 61433daa2df025295c3c7d8a 6148a8221fffd0a893157cf8 61499d3361dc3ca54a3d399b 6151ce0a8ead907a8ceccba4 6152ecaf8ead90106aeccba6 6152f50c00a9a101ae27df14 61545f9fe422815ae87f151f 61548001e0d22984470742fe 61603c347750a95efd55e754 6166efa066ae647fe3dd9d0d 616a7aa48a182c14e5a0e2f8 616b41d48a182c30f5c0999a 6176c4c350f431be5ae4d30c 617fe3ca36aca7fc49809012 6180022fd85ded81860c6374 6184400c9926bb557b83c1e4',
        'Maltepe': '556c72a23ad99d0c00523c5d 564490d03f158a0c00ccae84 564492193f158a0c00ccb086 5659e2e23c84c20c003cdc2d 56a228e90775590f006f8ba0 56d6bd82772a46030078f636 56f43224707a850300a18de8 57d2619f012ab60300bfe504 57ea9b264360d400035ca270 57eba168351c86000321de0d 57ecd7b3adbec60003c69f2c 57f63b451a3ccf0003a8040f 57ff913409143e00032f0b49 5800ee2a0fcf1600038a2047 580228a367c14c0003ef51cf 581c638d64c88f0003d71398 583d63150cf7c000048f2033 58834f4de8c17c0004e950c8 588f5df5274aea00046a1e7b 5899ad98d5b34d0004dd429f 58b57c0e5993b40004e7216d 58b59b92a7f2bb0004c46184 58da7eea2a4d2a0004a096ef 5a33e1540fdedc000401cf0d 5a33e36946ceb9000405f638 5a4ca939b62370000470fce7 5a4caeae14e51900040d596f 5a814b17d6bc3300043b8c73 5a8558e00f85bd0004dd5208 5aaa81050c434d0004db52f2 5aace64d3a335200040a5432 5ad83a11a14ba900046f54a7 5ae306f1a9d26000045e5bc9 5ae6d8a253d0a10004d207f8 5bf7e12808fe46001e121414 5c38e9ab4b149200011a4b9a 5c4ebf49c1b0120001d78d68 5c4ec137bfecd2000159bfec 5c6c0ac6c3e5ed00012ed308 5ca4a9effda114000163f4dd 5cc168ba6fd0e600011ea763 5cc2fa2c57bde7000142fda5 5ceeac17b1fec22f35087aaf 5d22ec3e406d690001cd7e52 5d63047bda5b2d0001bd85be 5d64fb841b9eff00014d688b 5d6926c251d774000190e182 5d692b413ebe9000019f1f4a 5d701e2a7a43350001a6d81f 5d701f557a43350001a6d931 5d78f4c4d555790001fe1093 5d7d34abaef51100013f23cf 5d7feb8d0ed2c200010e06a2 5d853b0bf2f86b33196a3f61 5db1ee560ca56b32f8c731b5 5dda9a7ab434cd6143a33f8d 5dda9a80b434cd6143a33f8e 5dda9a86b434cd6143a33f8f 5dda9a8cb434cd6143a33f90 5de65d51b434cd6143a3485c 5de65d5bb434cd6143a3485e 5dea3a8fb434cd6143a34900 5dee88c8c65a2597f49b857b 5dee890b80f47b48d59af337 5dee893df03a3959016e0bf8 5e2df108c0203649e9df86bb 5e2df2f6c02036ebb1df8887 5e4a5fc4bf9147b62a770611 5e4b7b31f82c2e203559d470 5e6f658b7901c5d8ec21e815 5e724298fe5b822f1cbe10c8 5e812af3e60e408642325ba8 5e8716dcd435d8af185b051f 5e94a21df2d951314c1925ad 5e9ff0e838810045597129fb 5ead3e470e707d2920652220 5eb0973f954838a47ceb50f2 5eb439870d280ad3937efed6 5ec65efe85e06b7a2be9453c 5ece5fa569b2442cdc64d102 5ed744827d41160c7c9cfd03 5ed798c4becdf9633088b1c7 5ed79aea2c77543ed97ca787 5eeb729a0d8b95337f532851 5eeb849959d1541d17ab351a 5efaec3654630152706c00f2 5efb1a030809f701391c3114 5efb1b330809f747231c3115 5f077f7393194c47ca8703a3 5f0d8184213a11d71f0c11b5 5f0d84f650333d17468c663e 5f116842393372706566ca12 5f1f3526dec9f0e1f95b0410 5f28fa18a270338392a902e9 5f3510558603947bca7423cc 5f55f2570d549b3d57c845e6 5f59e137cde114d617be40ff 5f59e2d7daf969677baaf832 5f60cba31ad848c2e23904ba 5f7aea6daea5a611c8148f3e 5f85825f2f42d74cb3d76acc 5fababcc362af038605c6cf8 5fae768dc182819a90ac50ed 5fb2138f5e49603d4eff1bbc 5fbf4e5d63556a29ec2c7792 5fc22385af533462385aa952 5fc51b1533d3f65c9911b52c 5fd319ae1861ba73bbf581e7 5fd31d5dd00a8b7153e6dde4 5fedd769794c7c2008234b35 5ffda6eb081efdad96dedca8 5ffda9d73a999be5610bffd7 6005434540183607721bea33 6005868bd63a66c6831e97ec 600e672f02d6dc43e08645c8 600e69c10ee87b3d4b0a931d 60263f0124953b5f68463b69 603747004e55950dc75a3918 604b1780bed6423e045428c9 60544bd679563423d2832196 607001202da0021db03aff22 60900825baf0957978f9d4a2 60b4cdeed7a0bb507c720de7 60c05dddd0bbf1ef12f67c55 60c1fc25d57f5704b94a1e64 60c6f3457ff64f22e1dbdbb8 60c86e8d4b44e66dfe3514fe 60dc27d28597f8bfd27602ed 60dc3e9cf1ac4b5400b8c284 60dc4f30a0edeb1cbd1955bf 60dc5e0854b13a8cb8f8cda3 60e2f47c27092bc704d55596 60e84d4e8ab4a42979ce550a 610293f704f709c293eb0946 61238d86d00c3bfc6042f2fe 61279c82b18fac4366c10080 613b4240d790b50f342ba2f9 61408b3a9c905253b8f716e1 614b2024777dd847775165e9 614c3a698ead9065dceccba2 614dcac1dafac1b46a639efd 615db7d60e29d78bf526037f 616414519f75712850b11868 62020a14dbd363fbe5214b0b 62020b9b0591df2a67f765dd 65b79896cf09167636d10167 65b79e58897bd68510cee237 69b40ab27e9f7c1a48a00da6',
        'İzmir': '5dc32d8b734a192200caddf8 5dc32db6734a192200caddf9 5dc32dbf734a192200caddfa 5dc32dc9734a192200caddfb 5dc32e4d734a192200caddfc 5dc32e58734a192200caddfd 5dc32e61734a192200caddfe 5dc32e6d734a192200cade00 5e3f09a74377e621e2d73ff5 5e3f0aa14377e68237d73ff6 5e50f79bbf91472a8477062c 5e6f46e4e6f13b313772974a 5e6f4b254e1c5f2f27d6523d 5ee0fceaa15fb53c38d48d91 5f290bfed515c026d83543ed 5f290dd84b4ef65c3ab86ae4 5f6ca58ce2b6ababa49b85ec 5f81b24c6c0ff70e8b19c346 5fbe4392a21e79321275c4ed 5fedcb328bafd45756fd45b6 5fedd2001357b6fdd7d9d23e 5fedd3ab1357b67a9fd9d23f 602b7140fad53a8cfb435b4b 607e938f8c3abe356662f8c5 60865b32979fcc4d0da687dc 6087d6aabe73da6a14916075 609b72dbcd110e353bd2da59 60ab41b331240c2966790480 60b4d307df4c67250e096bfb 60b64027df4c677e48096bfc 60c1b3e4cffa9aff2657b73b 60c1b484c3188d2ceef9f1f7 60c1b520da459c8e2fada176 60c86d577ff64f18d5dbdbb9 60cb306b4b44e6cea63514ff 60cb31f09fabad79b74ccf6c 60d9bc68342412d079ea12ac 60dc4a848597f82f6f7602ee 60e0c2aff2c7e8844b4bf3c7 60e80eca66bd2140cba6444f 610295985258e5f8925b9f3b 61029da94f957af88eb09a83 6111151d56d6a6af12806aa9 61111830f86cde36de2f4119 6113e59fbb8549d0f20e65f5 61160c8e78b27011a2195b7f 611baff3af03923463cc2cff 611bb70321f1a34057dcf5b8 61408df45380c36865e973e8 6148a248dafac1f254639efa 6148bd91d942f83df42656de 614b32ffbd27911bdd5cdf9b 614d81eb1033c2a883f34e3c 614d8bb13c4eaf9f230f2059 61516dee91d75d627ddec462 6151cf763c4eaf778e0f205a 61602cf14cb1bf34e44c7b9c 61656107fa2d653d59ea1b82 6171560a67179b4901f8d97e 61893434e663dcd2cc0c6707 618bcd2a74e6fa6f00b2363b 61922b9384fee08e0c91664c 61f7d6cef1abba527590f6c7 621fe664f11424c78947c3b7 62d82fef2626acf2c7ea8f30 64341b6c9b9df870ff4e677e 6437ee4d967dcb0bf1b5a065 6437efafac657f9b75425a45 646615cff5ab2a9b6bad02c8 64a7ddce263e1d8fc1789fad 64a7e93b070c87bb8739fd63 66742575c8fcc94ecca0adb1 66850aa7315bcc10debf7fce 6a26d2414160333a4e9241e7',
    },
    '+4': {
        'Adana': '5fa3ab297a34243da20e90e9 5fa3af888994630469b0af82 5fa3b48a344d8b224374c700 5fa3b55066c23f725aa963af 5fa3b67e9a4f7e54cfab2db1 5fa3b7b8bd17e5f8bd17abf4 5fa5343c4af4b40b7654a1b5 5fa5350f3dd375165ed98b15 5fa536176f8ab748d0a0bb02 5fa5869f4ef85c0bd63857e2 5ffc046075e59200ad24d165 5ffc066f983d9e559136bdf7 5ffc07613a999b117c0bffd6 6087bf1316eedb9ca2517c2f 608e76b7735e47bf71af4793 608e79b439d8e35fe3475666 60b4d13088495730ee368741 60e856cb5826f42d01cc4b53 61028f6f56b9217970b46856 611ba63773aba83977b71e4b 612366bdd3315536b6d52137 61236856ca4b682239921cf3 61250310ba320f26c3e13065 6126090153c5182a9b01a299 613606bff8fb19235345566d 61377d9d4fc9a06ccfe7169f 614350643feefe1f24c45a6d 6148aa3e30b116475c4ec042 61556bc51033c21caef34e3e 615adff58af0674d8e6bbf19 615d7e6f92350b67ff15cb7b 61656002b641dc5b1df752e5 6177b30a7e40476d70a76a3c 617ff66f0ac855a85ec5c87a 619215be517008a82fc4dd5a 61cd5cfd524c4a10e7a4f199 68c129dbbadec12eddea7b3e',
        'Ankara': '5dcafe63e2c61b1e52cf1703 5dcafe6ae2c61b1e52cf1704 5dcafe71e2c61b1e52cf1705 5dcafe78e2c61b1e52cf1706 5dcafe7ee2c61b1e52cf1707 5dcafe85e2c61b1e52cf1708 5dcafe8be2c61b1e52cf1709 5dcafe90e2c61b1e52cf170a 5dcafe95e2c61b1e52cf170b 5dcafe9be2c61b1e52cf170c 5dcafea1e2c61b1e52cf170d 5dfb5587810db101416b794a 5e2dfcdb61df150a60e44ec4 5e50fb25bf9147d76677062d 5e5e4442ef84bd09f36e2732 5edf897f9bf0ab78c42aa0c5 5f0da3a92667170e4214f570 5f100d48000896470fbc6985 5f3f838dcdf7eb5b23d165aa 5f43709ae11e3f851d372de7 5f4371f6b8cc51b6b90cabbe 5f55f386cde1145a4abe40fe 5f7ffdbe55de059f4eb3d96c 5f80649315df6274324209e1 5f817f23649ab4419edcc6f4 5f8c2c74d66856bd8990c41e 5fa3a5a3920ea19e651b25f8 5fa3aa437a342489b70e90e8 5fa506a9aae05af1ea3b508c 5fa5090fec4ec10a14b3cc83 5fa9024a362af02e605c6cf7 5faa3bea7a3424ad240e90ea 5faa85a87a342446b30e90eb 5faa871a3a765ee02b1b72ca 5fbcbd814410e600316a850c 5fbe2f736b630ed66efae5da 5fd1c2ef6fcb7d40917b65ab 5fd5eebdd00a8b222ee6dde5 5fe60830544aa61d591ea44c 5fedde1f8bafd40f79fd45b7 5ffc124fe61279362b93d895 5ffc18b45fdd9e80bae58282 6012a9337421845f2dc0c24f 602d2ceefff95e357d2499a3 602d30b91b34076d2ac7a0da 602d3517d4178d42e6976477 606ff6c264b638409c2f84a6 606ffe31f4105254043f6734 60a3644d1308681278e3de0f 60b9cbd56e86745b690c2abc 60b9cfb4caff94a532ca8e5e 60b9d12581867555ef18bb24 60b9d6bf692579cec6cf9370 60c867a471a4c6225da8e9f0 60c86a81afa0f6425709556a 60c86d684f0a906427e021f5 60c86e90ebd4cafcdd51640b 60d9bd679b269b13dac3c7d1 60d9c4aff1ac4b139bb8c282 60d9c64046bc18552f2590cb 60dac37b7115b0cf4b0163f0 60dc0faffe79bf3f09819119 60dc5b8aa15c7c637cdd0a0c 60ebdac160fa57ace15f6328 60eecd3e355486b4e4302ff2 6113e4b472a14356efd2c990 611baa43af0d808427cefdfa 611babe242f6d07dba2fa1cb 611bb7fbb43df448d3e2bada 611e4f00d48216954301c0ca 611e5455fefdedc56cf75476 612361f16ea1455c4a2d82d0 61236338949bc9f222b0a07a 61236594c75decba7bf48c21 612605f152be9f5c74862efd 61360a9b1c71cf78b9aca448 61360b91d943bd4628033a91 61360d7dd3315533fcd52138 613641b277617778fc2fb413 6148ab5841e4921871ca1fd1 6148ac8730b11672564ec043 6148b4ed7d1100f536384c48 6148bba9b9cf1d2d80362582 614b2a1291d75dc425dec45f 615171338350531ed677dc6c 6155568be422814a367f1520 615b14be87ea9f7e86d4d30e 615c6be8d2e32cf51c75dcd3 615d67d61c340575d0102ac0 61655c8daf0c0273d81ff922 616a786b09c2e7526101b676 616d7f71d4ad4289b6256bd2 616d98ff408ef42f0a1a8ede 617150e61bd2eb07c342bfb3 617152cf8cfe47d79e37f5b6 617156b6bc027cbc6d6979ee 6171575f7d436a77816396d8 6171d10371872e44da7058f5 6176c0455fc28348742218c8 6176c1d6593a60e5937db788 6176c31c96be3fdb17efc26e 6176d46cbc027c712b04ca5d 6176d7f81bd2eb2843e1a420 6176de0f1eee7aa571e3262e 6179ce9f0ba80c36c6913d68 6179d020b9145f409ffda8df 6182b2bb6a5ab66908153c4a 618d1d1cabb358578c9b6bea 61920ea872f8b1f33b914fa7 619221571561be055a6d27b5 61b83c6124c2ab2d369e8453 61f9465a4f2b0a4ddff51884 620208534eb9cc5ed4f3935e 64a7e9c63bb10751c4a76dde 6527f60cddfe60856b14e3a0 65292e33c39e013a7f34dc68 65a11c9282048f4d55a52a41 69d4f6a06522d844f0ec99ee',
        'Arnavutköy': '555cc03c56861c0c00a0bd9b 55646fc47051560c00cc8398 556f0bee1ad7b80c002d44a7 5577f739d8631b0c00fb4b70 56407e825316580c0058c41b 5659d6f23c84c20c003cd032 57bc2fcb851ebd0300209bcf 57bc3760312bf20300ea04f2 57bf38ac96a6b403008227bb 57ea95d7aa27f80300ee9f3b 57ea9884aa27f80300eea12f 57fb617589145b0003a485c5 57ff667348532700039caa58 582b18cf4756f60004e3ea56 584abc3e30c09e0004e0c719 585b9935dcd4ec0004985f9c 586a31f3dc795000045aadf1 587349a7ed1bc700048bda90 587cbf1c56a47000048c16cc 58b4312f292ee600049fc76b 58b432cc292ee600049fc8d7 5a33e25d46ceb9000405f563 5aaa896d0c434d0004db55f0 5b83c4d364195f000456cfbf 5c05793e6ea39a08b22a9616 5c0eaca4110e9a1422c26129 5c20c943f133550001a9e657 5c38ebf04b149200011a4d25 5c4eeb55c1b0120001d7d1ee 5c6e53345b6cb20001bb2602 5cff880339a6920001a3328e 5d5d3c8bd851c00001604c7a 5d62fe0fda5b2d0001bd7fdc 5d692a0c51d774000190e4b2 5d692c6c51d774000190e7cf 5d692df23ebe9000019f2338 5d6e993df4c0350001cb440c 5d6ea5e2f4c0350001cb6011 5d78fa53d555790001fe1fc6 5daee08d730fa8dcf50e3227 5db1f19a0ca56b6f8ac73357 5db9759777a0c71180d7694c 5dd4d68847ab01f7fe3fab98 5dd4d6b547ab010e543fabc9 5dd4d6e147ab01f8d73fabf3 5e6a52ce9e4a6171bb22138e 5e6a5681092a44687b87f286 5e6a572c370b07f1fe12088b 5e6a5825badef2d6e8e19cc2 5e7caaf3a94bbe1adc0d4351 5ea84a1b5896811da091565a 5ea93197776bc1a61a88834e 5eb91e0e40f34feed12d2caf 5ecce6aed2d088aa303221c7 5ee747a92b721c4a2f0de53c 5ee749c32b721cbc680de53d 5ee758226979ef7916643f8a 5ee91204d610549cd90a70d0 5efae8a1c45863487c3ae43c 5efb1d555c8d89a45b94c0fd 5f00419233bec1f8ec2f649d 5f089231dc2c2249d9c9cd7f 5f1007924726a52024fb827f 5f1849c2344af3b6a59b3737 5f28fdff5435c7100b4925c9 5f3f8922dca1057336bd6f6b 5f59e022415eff6d6a7fa0f4 5f72d5f7f1ec3bf53b4bae69 5f8580e6aea5a66ce8148f41 5fae8e6abbe9c45991e4c843 5fd275d27535bcdb9185792c 5fd31533d00a8b05cae6dde3 5fd3189e22d57c0dfa4b0683 5fdb394efd3ebc19897ba6b2 5fdb3b4022d57ca4ee4b0684 5fdb3c3a22d57c6d464b0685 5fdb8a4893c419757f7cb4bf 5feddbe6d472305103600f37 5ffee39ce945a31027220718 602164b86c81807d77b002a2 6030f77b85488486f1d8993b 60544f4df4105265c33f6725 606ffab1adac710b11db5cb5 6087d50638df2aea7b6b6f56 60b4d00f6a99764d6e2f8c0c 60c86ff1e15538b288b76a2d 60cb3458ad2dda5f1fa74d74 60d9bdb373f63934d95dca42 60dc2b0a46bc18b8fd2590cc 60dc2d729274842deeb4c720 60dc2f06aa4bc1e20ddda909 61234230a2f72885762cfa60 614344ae79244a7c3588ccad 61434633f7bee7266005efe6 614d882a6b32fbcc536728d1 614da622e4228142317f151b 6155b76809f1d7185b1b3123 615ab6870e29d7447226037b 615ab7ab8dc4b3e0efb75f38 6167f4d4d527d44f104670bf 61702483173bd6168261a927 6171d0347d436a6e9576a591 61784e7071872e09f21ce6c5 617fb16458878a6087255267 618bce2e36ec848950d31987 61921256b5e36f47d11a5bf4 61a743d0831d321398ea1cab 61cd5d428c1b5c2b8683866a 61dc5ca117387455d505df5f 61e816d5c56baff787168946 61f15ff630ef213cbbdee81d 62138f1395913b66bec83f12 6217b6e67b7ea62263223e76 628374d59226f29007574532 64c9ead121b2bc937dd5c630 64e746bfe4b9d5860521d176 65b90e1cbf4377207c34499e 66473b6870415cfd9f145ea0 66ff90b844d68882d5b84dc2',
        'Diyarbakır': '610a8fe4c7e089531ddeafe5 61433daa2df025295c3c7d8a 6148a8221fffd0a893157cf8 61499d3361dc3ca54a3d399b 6151ce0a8ead907a8ceccba4 6152ecaf8ead90106aeccba6 6152f50c00a9a101ae27df14 61545f9fe422815ae87f151f 61548001e0d22984470742fe 61603c347750a95efd55e754 6166efa066ae647fe3dd9d0d 616a7aa48a182c14e5a0e2f8 616b41d48a182c30f5c0999a 6176c4c350f431be5ae4d30c 617fe3ca36aca7fc49809012 6180022fd85ded81860c6374 6184400c9926bb557b83c1e4',
        'Maltepe': '556c72a23ad99d0c00523c5d 564490d03f158a0c00ccae84 564492193f158a0c00ccb086 5659e2e23c84c20c003cdc2d 56a228e90775590f006f8ba0 56d6bd82772a46030078f636 56f43224707a850300a18de8 57d2619f012ab60300bfe504 57ea9b264360d400035ca270 57eba168351c86000321de0d 57ecd7b3adbec60003c69f2c 57f63b451a3ccf0003a8040f 57ff913409143e00032f0b49 5800ee2a0fcf1600038a2047 580228a367c14c0003ef51cf 581c638d64c88f0003d71398 583d63150cf7c000048f2033 58834f4de8c17c0004e950c8 588f5df5274aea00046a1e7b 5899ad98d5b34d0004dd429f 58b57c0e5993b40004e7216d 58b59b92a7f2bb0004c46184 58da7eea2a4d2a0004a096ef 5a33e1540fdedc000401cf0d 5a33e36946ceb9000405f638 5a4ca939b62370000470fce7 5a4caeae14e51900040d596f 5a814b17d6bc3300043b8c73 5a8558e00f85bd0004dd5208 5aaa81050c434d0004db52f2 5aace64d3a335200040a5432 5ad83a11a14ba900046f54a7 5ae306f1a9d26000045e5bc9 5ae6d8a253d0a10004d207f8 5bf7e12808fe46001e121414 5c38e9ab4b149200011a4b9a 5c4ebf49c1b0120001d78d68 5c4ec137bfecd2000159bfec 5c6c0ac6c3e5ed00012ed308 5ca4a9effda114000163f4dd 5cc168ba6fd0e600011ea763 5cc2fa2c57bde7000142fda5 5ceeac17b1fec22f35087aaf 5d22ec3e406d690001cd7e52 5d63047bda5b2d0001bd85be 5d64fb841b9eff00014d688b 5d6926c251d774000190e182 5d692b413ebe9000019f1f4a 5d701e2a7a43350001a6d81f 5d701f557a43350001a6d931 5d78f4c4d555790001fe1093 5d7d34abaef51100013f23cf 5d7feb8d0ed2c200010e06a2 5d853b0bf2f86b33196a3f61 5db1ee560ca56b32f8c731b5 5dda9a7ab434cd6143a33f8d 5dda9a80b434cd6143a33f8e 5dda9a86b434cd6143a33f8f 5dda9a8cb434cd6143a33f90 5de65d51b434cd6143a3485c 5de65d5bb434cd6143a3485e 5dea3a8fb434cd6143a34900 5dee88c8c65a2597f49b857b 5dee890b80f47b48d59af337 5dee893df03a3959016e0bf8 5e2df108c0203649e9df86bb 5e2df2f6c02036ebb1df8887 5e4a5fc4bf9147b62a770611 5e4b7b31f82c2e203559d470 5e6f658b7901c5d8ec21e815 5e724298fe5b822f1cbe10c8 5e812af3e60e408642325ba8 5e8716dcd435d8af185b051f 5e94a21df2d951314c1925ad 5e9ff0e838810045597129fb 5ead3e470e707d2920652220 5eb0973f954838a47ceb50f2 5eb439870d280ad3937efed6 5ec65efe85e06b7a2be9453c 5ece5fa569b2442cdc64d102 5ed744827d41160c7c9cfd03 5ed798c4becdf9633088b1c7 5ed79aea2c77543ed97ca787 5eeb729a0d8b95337f532851 5eeb849959d1541d17ab351a 5efaec3654630152706c00f2 5efb1a030809f701391c3114 5efb1b330809f747231c3115 5f077f7393194c47ca8703a3 5f0d8184213a11d71f0c11b5 5f0d84f650333d17468c663e 5f116842393372706566ca12 5f1f3526dec9f0e1f95b0410 5f28fa18a270338392a902e9 5f3510558603947bca7423cc 5f55f2570d549b3d57c845e6 5f59e137cde114d617be40ff 5f59e2d7daf969677baaf832 5f60cba31ad848c2e23904ba 5f7aea6daea5a611c8148f3e 5f85825f2f42d74cb3d76acc 5fababcc362af038605c6cf8 5fae768dc182819a90ac50ed 5fb2138f5e49603d4eff1bbc 5fbf4e5d63556a29ec2c7792 5fc22385af533462385aa952 5fc51b1533d3f65c9911b52c 5fd319ae1861ba73bbf581e7 5fd31d5dd00a8b7153e6dde4 5fedd769794c7c2008234b35 5ffda6eb081efdad96dedca8 5ffda9d73a999be5610bffd7 6005434540183607721bea33 6005868bd63a66c6831e97ec 600e672f02d6dc43e08645c8 600e69c10ee87b3d4b0a931d 60263f0124953b5f68463b69 603747004e55950dc75a3918 604b1780bed6423e045428c9 60544bd679563423d2832196 607001202da0021db03aff22 60900825baf0957978f9d4a2 60b4cdeed7a0bb507c720de7 60c05dddd0bbf1ef12f67c55 60c1fc25d57f5704b94a1e64 60c6f3457ff64f22e1dbdbb8 60c86e8d4b44e66dfe3514fe 60dc27d28597f8bfd27602ed 60dc3e9cf1ac4b5400b8c284 60dc4f30a0edeb1cbd1955bf 60dc5e0854b13a8cb8f8cda3 60e2f47c27092bc704d55596 60e84d4e8ab4a42979ce550a 610293f704f709c293eb0946 61238d86d00c3bfc6042f2fe 61279c82b18fac4366c10080 613b4240d790b50f342ba2f9 61408b3a9c905253b8f716e1 614b2024777dd847775165e9 614c3a698ead9065dceccba2 614dcac1dafac1b46a639efd 615db7d60e29d78bf526037f 616414519f75712850b11868 62020a14dbd363fbe5214b0b 62020b9b0591df2a67f765dd 65b79896cf09167636d10167 65b79e58897bd68510cee237 69b40ab27e9f7c1a48a00da6',
        'İzmir': '5dc32d8b734a192200caddf8 5dc32db6734a192200caddf9 5dc32dbf734a192200caddfa 5dc32dc9734a192200caddfb 5dc32e4d734a192200caddfc 5dc32e58734a192200caddfd 5dc32e61734a192200caddfe 5dc32e6d734a192200cade00 5e3f09a74377e621e2d73ff5 5e3f0aa14377e68237d73ff6 5e50f79bbf91472a8477062c 5e6f46e4e6f13b313772974a 5e6f4b254e1c5f2f27d6523d 5ee0fceaa15fb53c38d48d91 5f290bfed515c026d83543ed 5f290dd84b4ef65c3ab86ae4 5f6ca58ce2b6ababa49b85ec 5f81b24c6c0ff70e8b19c346 5fbe4392a21e79321275c4ed 5fedcb328bafd45756fd45b6 5fedd2001357b6fdd7d9d23e 5fedd3ab1357b67a9fd9d23f 602b7140fad53a8cfb435b4b 607e938f8c3abe356662f8c5 60865b32979fcc4d0da687dc 6087d6aabe73da6a14916075 609b72dbcd110e353bd2da59 60ab41b331240c2966790480 60b4d307df4c67250e096bfb 60b64027df4c677e48096bfc 60c1b3e4cffa9aff2657b73b 60c1b484c3188d2ceef9f1f7 60c1b520da459c8e2fada176 60c86d577ff64f18d5dbdbb9 60cb306b4b44e6cea63514ff 60cb31f09fabad79b74ccf6c 60d9bc68342412d079ea12ac 60dc4a848597f82f6f7602ee 60e0c2aff2c7e8844b4bf3c7 60e80eca66bd2140cba6444f 610295985258e5f8925b9f3b 61029da94f957af88eb09a83 6111151d56d6a6af12806aa9 61111830f86cde36de2f4119 6113e59fbb8549d0f20e65f5 61160c8e78b27011a2195b7f 611baff3af03923463cc2cff 611bb70321f1a34057dcf5b8 61408df45380c36865e973e8 6148a248dafac1f254639efa 6148bd91d942f83df42656de 614b32ffbd27911bdd5cdf9b 614d81eb1033c2a883f34e3c 614d8bb13c4eaf9f230f2059 61516dee91d75d627ddec462 6151cf763c4eaf778e0f205a 61602cf14cb1bf34e44c7b9c 61656107fa2d653d59ea1b82 6171560a67179b4901f8d97e 61893434e663dcd2cc0c6707 618bcd2a74e6fa6f00b2363b 61922b9384fee08e0c91664c 61f7d6cef1abba527590f6c7 621fe664f11424c78947c3b7 62d82fef2626acf2c7ea8f30 64341b6c9b9df870ff4e677e 6437ee4d967dcb0bf1b5a065 6437efafac657f9b75425a45 646615cff5ab2a9b6bad02c8 64a7ddce263e1d8fc1789fad 64a7e93b070c87bb8739fd63 66742575c8fcc94ecca0adb1 66850aa7315bcc10debf7fce 6a26d2414160333a4e9241e7',
    },
    'MS': {
        'Adana': '5fa3ab297a34243da20e90e9 5fa3af888994630469b0af82 5fa3b48a344d8b224374c700 5fa3b55066c23f725aa963af 5fa3b67e9a4f7e54cfab2db1 5fa3b7b8bd17e5f8bd17abf4 5fa5343c4af4b40b7654a1b5 5fa5350f3dd375165ed98b15 5fa536176f8ab748d0a0bb02 5fa5869f4ef85c0bd63857e2 5ffc046075e59200ad24d165 5ffc066f983d9e559136bdf7 5ffc07613a999b117c0bffd6 6087bf1316eedb9ca2517c2f 608e76b7735e47bf71af4793 608e79b439d8e35fe3475666 60b4d13088495730ee368741 60e856cb5826f42d01cc4b53 61028f6f56b9217970b46856 611ba63773aba83977b71e4b 612366bdd3315536b6d52137 61236856ca4b682239921cf3 61250310ba320f26c3e13065 6126090153c5182a9b01a299 613606bff8fb19235345566d 61377d9d4fc9a06ccfe7169f 614350643feefe1f24c45a6d 6148aa3e30b116475c4ec042 61556bc51033c21caef34e3e 615adff58af0674d8e6bbf19 615d7e6f92350b67ff15cb7b 61656002b641dc5b1df752e5 6177b30a7e40476d70a76a3c 617ff66f0ac855a85ec5c87a 619215be517008a82fc4dd5a 61cd5cfd524c4a10e7a4f199 68c129dbbadec12eddea7b3e',
        'Ankara': '5dcafe63e2c61b1e52cf1703 5dcafe6ae2c61b1e52cf1704 5dcafe71e2c61b1e52cf1705 5dcafe78e2c61b1e52cf1706 5dcafe7ee2c61b1e52cf1707 5dcafe85e2c61b1e52cf1708 5dcafe8be2c61b1e52cf1709 5dcafe90e2c61b1e52cf170a 5dcafe95e2c61b1e52cf170b 5dcafe9be2c61b1e52cf170c 5dcafea1e2c61b1e52cf170d 5dfb5587810db101416b794a 5e2dfcdb61df150a60e44ec4 5e50fb25bf9147d76677062d 5e5e4442ef84bd09f36e2732 5edf897f9bf0ab78c42aa0c5 5f0da3a92667170e4214f570 5f100d48000896470fbc6985 5f3f838dcdf7eb5b23d165aa 5f43709ae11e3f851d372de7 5f4371f6b8cc51b6b90cabbe 5f55f386cde1145a4abe40fe 5f7ffdbe55de059f4eb3d96c 5f80649315df6274324209e1 5f817f23649ab4419edcc6f4 5f8c2c74d66856bd8990c41e 5fa3a5a3920ea19e651b25f8 5fa3aa437a342489b70e90e8 5fa506a9aae05af1ea3b508c 5fa5090fec4ec10a14b3cc83 5fa9024a362af02e605c6cf7 5faa3bea7a3424ad240e90ea 5faa85a87a342446b30e90eb 5faa871a3a765ee02b1b72ca 5fbcbd814410e600316a850c 5fbe2f736b630ed66efae5da 5fd1c2ef6fcb7d40917b65ab 5fd5eebdd00a8b222ee6dde5 5fe60830544aa61d591ea44c 5fedde1f8bafd40f79fd45b7 5ffc124fe61279362b93d895 5ffc18b45fdd9e80bae58282 6012a9337421845f2dc0c24f 602d2ceefff95e357d2499a3 602d30b91b34076d2ac7a0da 602d3517d4178d42e6976477 606ff6c264b638409c2f84a6 606ffe31f4105254043f6734 60a3644d1308681278e3de0f 60b9cbd56e86745b690c2abc 60b9cfb4caff94a532ca8e5e 60b9d12581867555ef18bb24 60b9d6bf692579cec6cf9370 60c867a471a4c6225da8e9f0 60c86a81afa0f6425709556a 60c86d684f0a906427e021f5 60c86e90ebd4cafcdd51640b 60d9bd679b269b13dac3c7d1 60d9c4aff1ac4b139bb8c282 60d9c64046bc18552f2590cb 60dac37b7115b0cf4b0163f0 60dc0faffe79bf3f09819119 60dc5b8aa15c7c637cdd0a0c 60ebdac160fa57ace15f6328 60eecd3e355486b4e4302ff2 6113e4b472a14356efd2c990 611baa43af0d808427cefdfa 611babe242f6d07dba2fa1cb 611bb7fbb43df448d3e2bada 611e4f00d48216954301c0ca 611e5455fefdedc56cf75476 612361f16ea1455c4a2d82d0 61236338949bc9f222b0a07a 61236594c75decba7bf48c21 612605f152be9f5c74862efd 61360a9b1c71cf78b9aca448 61360b91d943bd4628033a91 61360d7dd3315533fcd52138 613641b277617778fc2fb413 6148ab5841e4921871ca1fd1 6148ac8730b11672564ec043 6148b4ed7d1100f536384c48 6148bba9b9cf1d2d80362582 614b2a1291d75dc425dec45f 615171338350531ed677dc6c 6155568be422814a367f1520 615b14be87ea9f7e86d4d30e 615c6be8d2e32cf51c75dcd3 615d67d61c340575d0102ac0 61655c8daf0c0273d81ff922 616a786b09c2e7526101b676 616d7f71d4ad4289b6256bd2 616d98ff408ef42f0a1a8ede 617150e61bd2eb07c342bfb3 617152cf8cfe47d79e37f5b6 617156b6bc027cbc6d6979ee 6171575f7d436a77816396d8 6171d10371872e44da7058f5 6176c0455fc28348742218c8 6176c1d6593a60e5937db788 6176c31c96be3fdb17efc26e 6176d46cbc027c712b04ca5d 6176d7f81bd2eb2843e1a420 6176de0f1eee7aa571e3262e 6179ce9f0ba80c36c6913d68 6179d020b9145f409ffda8df 6182b2bb6a5ab66908153c4a 618d1d1cabb358578c9b6bea 61920ea872f8b1f33b914fa7 619221571561be055a6d27b5 61b83c6124c2ab2d369e8453 61f9465a4f2b0a4ddff51884 620208534eb9cc5ed4f3935e 64a7e9c63bb10751c4a76dde 6527f60cddfe60856b14e3a0 65292e33c39e013a7f34dc68 65a11c9282048f4d55a52a41 69d4f6a06522d844f0ec99ee',
        'Arnavutköy': '555cc03c56861c0c00a0bd9b 55646fc47051560c00cc8398 556f0bee1ad7b80c002d44a7 5577f739d8631b0c00fb4b70 56407e825316580c0058c41b 5659d6f23c84c20c003cd032 57bc2fcb851ebd0300209bcf 57bc3760312bf20300ea04f2 57bf38ac96a6b403008227bb 57ea95d7aa27f80300ee9f3b 57ea9884aa27f80300eea12f 57fb617589145b0003a485c5 57ff667348532700039caa58 582b18cf4756f60004e3ea56 584abc3e30c09e0004e0c719 585b9935dcd4ec0004985f9c 586a31f3dc795000045aadf1 587349a7ed1bc700048bda90 587cbf1c56a47000048c16cc 58b4312f292ee600049fc76b 58b432cc292ee600049fc8d7 5a33e25d46ceb9000405f563 5aaa896d0c434d0004db55f0 5b83c4d364195f000456cfbf 5c05793e6ea39a08b22a9616 5c0eaca4110e9a1422c26129 5c20c943f133550001a9e657 5c38ebf04b149200011a4d25 5c4eeb55c1b0120001d7d1ee 5c6e53345b6cb20001bb2602 5cff880339a6920001a3328e 5d5d3c8bd851c00001604c7a 5d62fe0fda5b2d0001bd7fdc 5d692a0c51d774000190e4b2 5d692c6c51d774000190e7cf 5d692df23ebe9000019f2338 5d6e993df4c0350001cb440c 5d6ea5e2f4c0350001cb6011 5d78fa53d555790001fe1fc6 5daee08d730fa8dcf50e3227 5db1f19a0ca56b6f8ac73357 5db9759777a0c71180d7694c 5dd4d68847ab01f7fe3fab98 5dd4d6b547ab010e543fabc9 5dd4d6e147ab01f8d73fabf3 5e6a52ce9e4a6171bb22138e 5e6a5681092a44687b87f286 5e6a572c370b07f1fe12088b 5e6a5825badef2d6e8e19cc2 5e7caaf3a94bbe1adc0d4351 5ea84a1b5896811da091565a 5ea93197776bc1a61a88834e 5eb91e0e40f34feed12d2caf 5ecce6aed2d088aa303221c7 5ee747a92b721c4a2f0de53c 5ee749c32b721cbc680de53d 5ee758226979ef7916643f8a 5ee91204d610549cd90a70d0 5efae8a1c45863487c3ae43c 5efb1d555c8d89a45b94c0fd 5f00419233bec1f8ec2f649d 5f089231dc2c2249d9c9cd7f 5f1007924726a52024fb827f 5f1849c2344af3b6a59b3737 5f28fdff5435c7100b4925c9 5f3f8922dca1057336bd6f6b 5f59e022415eff6d6a7fa0f4 5f72d5f7f1ec3bf53b4bae69 5f8580e6aea5a66ce8148f41 5fae8e6abbe9c45991e4c843 5fd275d27535bcdb9185792c 5fd31533d00a8b05cae6dde3 5fd3189e22d57c0dfa4b0683 5fdb394efd3ebc19897ba6b2 5fdb3b4022d57ca4ee4b0684 5fdb3c3a22d57c6d464b0685 5fdb8a4893c419757f7cb4bf 5feddbe6d472305103600f37 5ffee39ce945a31027220718 602164b86c81807d77b002a2 6030f77b85488486f1d8993b 60544f4df4105265c33f6725 606ffab1adac710b11db5cb5 6087d50638df2aea7b6b6f56 60b4d00f6a99764d6e2f8c0c 60c86ff1e15538b288b76a2d 60cb3458ad2dda5f1fa74d74 60d9bdb373f63934d95dca42 60dc2b0a46bc18b8fd2590cc 60dc2d729274842deeb4c720 60dc2f06aa4bc1e20ddda909 60f5bd4d1308d356fac9a034 61234230a2f72885762cfa60 614344ae79244a7c3588ccad 61434633f7bee7266005efe6 614d882a6b32fbcc536728d1 614da622e4228142317f151b 6155b76809f1d7185b1b3123 615ab6870e29d7447226037b 615ab7ab8dc4b3e0efb75f38 6167f4d4d527d44f104670bf 61702483173bd6168261a927 6171d0347d436a6e9576a591 61784e7071872e09f21ce6c5 617fb16458878a6087255267 618bce2e36ec848950d31987 61921256b5e36f47d11a5bf4 61a743d0831d321398ea1cab 61cd5d428c1b5c2b8683866a 61dc5ca117387455d505df5f 61e816d5c56baff787168946 61f15ff630ef213cbbdee81d 62138f1395913b66bec83f12 6217b6e67b7ea62263223e76 628374d59226f29007574532 64c9ead121b2bc937dd5c630 64e746bfe4b9d5860521d176 65b90e1cbf4377207c34499e 66473b6870415cfd9f145ea0 66ff90b844d68882d5b84dc2',
        'Maltepe': '556c72a23ad99d0c00523c5d 564490d03f158a0c00ccae84 564492193f158a0c00ccb086 5659e2e23c84c20c003cdc2d 56a228e90775590f006f8ba0 56d6bd82772a46030078f636 56f43224707a850300a18de8 57d2619f012ab60300bfe504 57ea9b264360d400035ca270 57eba168351c86000321de0d 57ecd7b3adbec60003c69f2c 57f63b451a3ccf0003a8040f 57ff913409143e00032f0b49 5800ee2a0fcf1600038a2047 580228a367c14c0003ef51cf 581c638d64c88f0003d71398 583d63150cf7c000048f2033 58834f4de8c17c0004e950c8 588f5df5274aea00046a1e7b 5899ad98d5b34d0004dd429f 58b57c0e5993b40004e7216d 58b59b92a7f2bb0004c46184 58da7eea2a4d2a0004a096ef 5a33e1540fdedc000401cf0d 5a33e36946ceb9000405f638 5a4ca939b62370000470fce7 5a4caeae14e51900040d596f 5a814b17d6bc3300043b8c73 5a8558e00f85bd0004dd5208 5aaa81050c434d0004db52f2 5aace64d3a335200040a5432 5ad83a11a14ba900046f54a7 5ae306f1a9d26000045e5bc9 5ae6d8a253d0a10004d207f8 5bf7e12808fe46001e121414 5c38e9ab4b149200011a4b9a 5c4ebf49c1b0120001d78d68 5c4ec137bfecd2000159bfec 5c6c0ac6c3e5ed00012ed308 5ca4a9effda114000163f4dd 5cc168ba6fd0e600011ea763 5cc2fa2c57bde7000142fda5 5ceeac17b1fec22f35087aaf 5d22ec3e406d690001cd7e52 5d63047bda5b2d0001bd85be 5d64fb841b9eff00014d688b 5d6926c251d774000190e182 5d692b413ebe9000019f1f4a 5d701e2a7a43350001a6d81f 5d701f557a43350001a6d931 5d78f4c4d555790001fe1093 5d7d34abaef51100013f23cf 5d7feb8d0ed2c200010e06a2 5d853b0bf2f86b33196a3f61 5db1ee560ca56b32f8c731b5 5dda9a7ab434cd6143a33f8d 5dda9a80b434cd6143a33f8e 5dda9a86b434cd6143a33f8f 5dda9a8cb434cd6143a33f90 5de65d51b434cd6143a3485c 5de65d5bb434cd6143a3485e 5dea3a8fb434cd6143a34900 5dee88c8c65a2597f49b857b 5dee890b80f47b48d59af337 5dee893df03a3959016e0bf8 5e2df108c0203649e9df86bb 5e2df2f6c02036ebb1df8887 5e4a5fc4bf9147b62a770611 5e4b7b31f82c2e203559d470 5e6f658b7901c5d8ec21e815 5e724298fe5b822f1cbe10c8 5e812af3e60e408642325ba8 5e8716dcd435d8af185b051f 5e94a21df2d951314c1925ad 5e9ff0e838810045597129fb 5ead3e470e707d2920652220 5eb0973f954838a47ceb50f2 5eb439870d280ad3937efed6 5ec65efe85e06b7a2be9453c 5ece5fa569b2442cdc64d102 5ed744827d41160c7c9cfd03 5ed798c4becdf9633088b1c7 5ed79aea2c77543ed97ca787 5eeb729a0d8b95337f532851 5eeb849959d1541d17ab351a 5efaec3654630152706c00f2 5efb1a030809f701391c3114 5efb1b330809f747231c3115 5f077f7393194c47ca8703a3 5f0d8184213a11d71f0c11b5 5f0d84f650333d17468c663e 5f116842393372706566ca12 5f1f3526dec9f0e1f95b0410 5f28fa18a270338392a902e9 5f3510558603947bca7423cc 5f55f2570d549b3d57c845e6 5f59e137cde114d617be40ff 5f59e2d7daf969677baaf832 5f60cba31ad848c2e23904ba 5f7aea6daea5a611c8148f3e 5f85825f2f42d74cb3d76acc 5fababcc362af038605c6cf8 5fae768dc182819a90ac50ed 5fb2138f5e49603d4eff1bbc 5fbf4e5d63556a29ec2c7792 5fc22385af533462385aa952 5fc51b1533d3f65c9911b52c 5fd319ae1861ba73bbf581e7 5fd31d5dd00a8b7153e6dde4 5fedd769794c7c2008234b35 5ffda6eb081efdad96dedca8 5ffda9d73a999be5610bffd7 6005434540183607721bea33 6005868bd63a66c6831e97ec 600e672f02d6dc43e08645c8 600e69c10ee87b3d4b0a931d 60263f0124953b5f68463b69 603747004e55950dc75a3918 604b1780bed6423e045428c9 60544bd679563423d2832196 607001202da0021db03aff22 60900825baf0957978f9d4a2 60b4cdeed7a0bb507c720de7 60c05dddd0bbf1ef12f67c55 60c1fc25d57f5704b94a1e64 60c6f3457ff64f22e1dbdbb8 60c86e8d4b44e66dfe3514fe 60dc27d28597f8bfd27602ed 60dc3e9cf1ac4b5400b8c284 60dc4f30a0edeb1cbd1955bf 60dc5e0854b13a8cb8f8cda3 60e2f47c27092bc704d55596 60e84d4e8ab4a42979ce550a 610293f704f709c293eb0946 61238d86d00c3bfc6042f2fe 61279c82b18fac4366c10080 613b4240d790b50f342ba2f9 61408b3a9c905253b8f716e1 614b2024777dd847775165e9 614c3a698ead9065dceccba2 614dcac1dafac1b46a639efd 615db7d60e29d78bf526037f 616414519f75712850b11868 62020a14dbd363fbe5214b0b 62020b9b0591df2a67f765dd 65b79896cf09167636d10167 65b79e58897bd68510cee237 69b40ab27e9f7c1a48a00da6',
        'İzmir': '5dc32d8b734a192200caddf8 5dc32db6734a192200caddf9 5dc32dbf734a192200caddfa 5dc32dc9734a192200caddfb 5dc32e4d734a192200caddfc 5dc32e58734a192200caddfd 5dc32e61734a192200caddfe 5dc32e6d734a192200cade00 5e3f09a74377e621e2d73ff5 5e3f0aa14377e68237d73ff6 5e50f79bbf91472a8477062c 5e6f46e4e6f13b313772974a 5e6f4b254e1c5f2f27d6523d 5ee0fceaa15fb53c38d48d91 5f290bfed515c026d83543ed 5f290dd84b4ef65c3ab86ae4 5f6ca58ce2b6ababa49b85ec 5f81b24c6c0ff70e8b19c346 5fbe4392a21e79321275c4ed 5fedcb328bafd45756fd45b6 5fedd2001357b6fdd7d9d23e 5fedd3ab1357b67a9fd9d23f 602b7140fad53a8cfb435b4b 607e938f8c3abe356662f8c5 60865b32979fcc4d0da687dc 6087d6aabe73da6a14916075 609b72dbcd110e353bd2da59 60ab41b331240c2966790480 60b4d307df4c67250e096bfb 60b64027df4c677e48096bfc 60c1b3e4cffa9aff2657b73b 60c1b484c3188d2ceef9f1f7 60c1b520da459c8e2fada176 60c86d577ff64f18d5dbdbb9 60cb306b4b44e6cea63514ff 60cb31f09fabad79b74ccf6c 60d9bc68342412d079ea12ac 60dc4a848597f82f6f7602ee 60e0c2aff2c7e8844b4bf3c7 60e80eca66bd2140cba6444f 610295985258e5f8925b9f3b 61029da94f957af88eb09a83 6111151d56d6a6af12806aa9 61111830f86cde36de2f4119 6113e59fbb8549d0f20e65f5 61160c8e78b27011a2195b7f 611baff3af03923463cc2cff 611bb70321f1a34057dcf5b8 61408df45380c36865e973e8 6148a248dafac1f254639efa 6148bd91d942f83df42656de 614b32ffbd27911bdd5cdf9b 614d81eb1033c2a883f34e3c 614d8bb13c4eaf9f230f2059 61516dee91d75d627ddec462 6151cf763c4eaf778e0f205a 61602cf14cb1bf34e44c7b9c 61656107fa2d653d59ea1b82 6171560a67179b4901f8d97e 61893434e663dcd2cc0c6707 618bcd2a74e6fa6f00b2363b 61922b9384fee08e0c91664c 61f7d6cef1abba527590f6c7 621fe664f11424c78947c3b7 62d82fef2626acf2c7ea8f30 64341b6c9b9df870ff4e677e 6437ee4d967dcb0bf1b5a065 6437efafac657f9b75425a45 646615cff5ab2a9b6bad02c8 64a7ddce263e1d8fc1789fad 64a7e93b070c87bb8739fd63 66742575c8fcc94ecca0adb1 66850aa7315bcc10debf7fce 6a26d2414160333a4e9241e7',
    },
}
# <<< MERKEZ HARİTASI
MERKEZ_ESIK = 0.90
_MERKEZ_SOZLUK = {}

def _merkez_sozluk(kat):
    if kat not in _MERKEZ_SOZLUK:
        hk = MERKEZ_HARITA.get(kat)
        kaynak = [hk] if hk is not None else list(MERKEZ_HARITA.values())     # kategori haritada yoksa hepsi
        _MERKEZ_SOZLUK[kat] = {k: m for h in kaynak for m, kodlar in h.items() for k in kodlar.split()}
    return _MERKEZ_SOZLUK[kat]


def merkez_tespit(ana, kat):
    """Ana tablonun cep depolarından merkez: {'tespit', 'pay', 'depo', 'eslesen', 'bilinmeyen', 'dagilim', 'not'}."""
    t = {'tespit': None, 'pay': 0.0, 'depo': 0, 'eslesen': 0, 'bilinmeyen': 0, 'dagilim': [], 'not': ''}
    kol = next((c for c in ana.columns if str(c).strip() == 'Location code'), None)
    if kol is None:
        t['not'] = 'ana tabloda Location code kolonu yok'; return t
    kodlar = {str(x).strip().lower() for x in ana[kol].dropna()} - {'', 'nan'}
    if not kodlar:
        t['not'] = 'ana tabloda depo yok'; return t
    sozluk = _merkez_sozluk(str(kat))
    say = collections.Counter(sozluk.get(k, '?') for k in kodlar)
    bilinen = [(m, n) for m, n in say.most_common() if m != '?']
    t.update({'depo': len(kodlar), 'bilinmeyen': say.get('?', 0), 'dagilim': bilinen})
    if bilinen:
        t.update({'tespit': bilinen[0][0], 'eslesen': bilinen[0][1], 'pay': bilinen[0][1] / len(kodlar)})
    else:
        t['not'] = 'depoların hiçbiri haritada yok'
    return t


# ------------------------------------------------------------------ çalıştırma
class _Tee(io.TextIOBase):
    def __init__(self, a, b): self.a, self.b = a, b
    def write(self, s): self.a.write(s); self.b.write(s); return len(s)
    def flush(self): self.a.flush(); self.b.flush()

_GIZLE = re.compile(r"Drive|Klasör|İzin istenebilir|Tek Excel Dosyası|Excel oluşturuluyor")

def _hata_metni(e):
    if isinstance(e, KeyError):
        return f"Dosyada beklenen kolon bulunamadı: {e.args[0]!s}. Dosyanın doğru rapor olduğunu kontrol et."
    if isinstance(e, FileNotFoundError):
        return 'Dosya bulunamadı: ' + os.path.basename(str(e.filename or e))
    return f'{type(e).__name__}: {e}'


def calistir(cfg_json):
    cfg = json.loads(cfg_json)
    spec = URUNLER[cfg.get('urun', 'amb')]
    P = dict(cfg.get('param') or {})
    ifadeler, D = {}, {}
    for rol, tip, ad in spec['dosyalar']:
        yol = cfg['dosyalar'].get(rol, f'{KOK}/in/{rol}_yok')
        D[rol] = yol
        if tip == 'param': P[ad] = yol
        else: ifadeler[ad] = f'pd.read_excel(__D__[{rol!r}])'
    for s in spec['sheetler']:
        v = (cfg.get('sheet') or {}).get(s['key'])
        if not v: continue
        gid = str(v.get('gid') or '')
        P[s['gid']] = int(gid) if spec.get('gid_sayi') and gid.isdigit() else gid
        if s.get('url'): P[s['url']] = v.get('url', '')
    tarih = cfg.get('tarih') or pd.Timestamp.now().strftime('%Y-%m-%d')
    temiz = lambda x: re.sub(r'[\\/:*?"<>|]+', '_', str(x or '')).strip()
    merkez_elle = temiz(cfg.get('merkez_elle'))
    P['CALISILAN_DEPO'] = merkez_elle or 'cikti'      # tarayıcıda kayıtlı eski "Çıktı dosyası" değeri kullanılmaz
    MT = {}
    def ad_belirle(g):
        """Çıktı adını bir kez belirler (Excel yazılmadan önce): harita → elle girilen → engel."""
        if MT: return MT['ad']
        kat = str(g.get('CALISILAN_KATEGORI') or P.get('CALISILAN_KATEGORI') or '')
        try: t = merkez_tespit(spec['ana'](g), kat)
        except Exception as e: t = {'tespit': None, 'pay': 0.0, 'depo': 0, 'eslesen': 0, 'bilinmeyen': 0, 'dagilim': [], 'not': f'tespit yapılamadı: {type(e).__name__}: {e}'}
        if t['tespit'] and t['pay'] >= MERKEZ_ESIK: ad, kaynak = t['tespit'], 'harita'
        elif merkez_elle: ad, kaynak = merkez_elle, 'elle'
        else: ad, kaynak = 'Merkez tanınmadı', 'yok'
        MT.update(t); MT.update({'ad': ad, 'kaynak': kaynak, 'engel': kaynak == 'yok', 'esik': MERKEZ_ESIK,
                                 'kategori': kat, 'harita_donem': MERKEZ_HARITA_DONEM})
        g['CALISILAN_DEPO'] = P['CALISILAN_DEPO'] = ad
        print(f"📍 Merkez: {ad} ({'harita, ' + format(t['pay'], '.0%') + ' depo eşleşti' if kaynak == 'harita' else 'elle girildi' if kaynak == 'elle' else 'tanınmadı'})")
        return ad
    sade = bool(cfg.get('sade'))
    buf = io.StringIO()
    for f in os.listdir(KOK + '/out'):
        try: os.remove(os.path.join(KOK + '/out', f))
        except Exception: pass
    eski = os.getcwd(); os.chdir(KOK + '/out')
    def excel_yaz(g):
        ad_belirle(g)
        _excel_yaz_genel(spec['excel'](g, sade), f"{g['CALISILAN_DEPO']}.xlsx")
    G = {'__name__': 'urun_' + cfg.get('urun', 'amb'), '__P__': P, '__D__': D,
         '__SIMDI__': lambda: pd.Timestamp(tarih + ' 12:00'), '__EXCEL_YAZ__': excel_yaz}
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, buf)), _sheet_yonlendirme():
            if spec.get('hazirlik'): spec['hazirlik'](P, D)
            src = _kaynak_hazirla(globals()[spec['motor']], P, ifadeler)
            exec(compile(src, spec['motor'], 'exec'), G)
        with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
            ad_belirle(G)                                  # Excel yazılmadıysa (ör. motor hata vermeden bitti) yine de belirle
        log = '\n'.join(s for s in buf.getvalue().split('\n') if not _GIZLE.search(s))
        r = spec['cikti'](G, log)
        r['merkez'] = {k: v for k, v in MT.items()}
        ad = f"{P['CALISILAN_DEPO']}.xlsx"
        r.update({'ok': True, 'log': log, 'dosya': KOK + '/out/' + ad if os.path.exists(KOK + '/out/' + ad) else None, 'dosya_adi': ad})
        r.update(_gunluk_hazirla(cfg, spec, G, P, tarih))
        return json.dumps(r, ensure_ascii=False)
    except Exception as e:
        log = '\n'.join(s for s in buf.getvalue().split('\n') if not _GIZLE.search(s))
        return json.dumps({'ok': False, 'hata': _hata_metni(e), 'log': log + '\n\n' + traceback.format_exc(limit=-3)}, ensure_ascii=False)
    finally:
        os.chdir(eski)


# ------------------------------------------------------------------ parquet + All PL (yerel klasöre)
_STD = {}

def _gunluk_hazirla(cfg, spec, G, P, tarih):
    """Koşunun ana tablosunun parquet halini yazar, All PL satırlarını bellekte tutar."""
    urun = cfg.get('urun', 'amb')
    ek = {'parquet': None, 'parquet_adi': f"{P['CALISILAN_DEPO']}.parquet", 'parquet_hata': None}
    try:
        ana = spec['ana'](G)
        kat = str(G.get('CALISILAN_KATEGORI') or P.get('CALISILAN_KATEGORI') or '')
        _STD[urun] = {'satirlar': allpl_satirlari(ana, kat, P['CALISILAN_DEPO'], tarih, cfg.get('zaman')),
                      'kategori': kat, 'bolge': P['CALISILAN_DEPO'], 'tarih': tarih}
        yol = KOK + '/out/' + ek['parquet_adi']
        parquet_yaz(ana, yol)
        ek['parquet'] = yol
    except Exception as e:
        ek['parquet_hata'] = f'{type(e).__name__}: {e}'
    return ek


def allpl_olustur(urun, eski_yol=None):
    """Günün All PL'sini (eski_yol verilirse o günün önceki All PL parquet'i ile birleştirerek) xlsx + parquet olarak yazar."""
    try:
        k = _STD.get(urun)
        if not k: raise RuntimeError('Önce hesap çalıştırılmalı')
        eski = pd.read_parquet(eski_yol) if eski_yol and os.path.exists(eski_yol) else None
        tum = allpl_birlestir(eski, k['satirlar'], k['kategori'], k['bolge'])
        os.makedirs(KOK + '/allpl', exist_ok=True)
        ad = allpl_adi(k['tarih'])
        parquet_yaz(tum, f'{KOK}/allpl/{ad}.parquet')
        allpl_excel_yaz(tum, f'{KOK}/allpl/{ad}.xlsx')
        return json.dumps({'ok': True, 'ad': ad, 'xlsx': f'{KOK}/allpl/{ad}.xlsx', 'parquet': f'{KOK}/allpl/{ad}.parquet',
                           'satir': int(len(tum)), 'bu_kosu': int(len(k['satirlar'])), 'bolge': int(tum['bolge'].nunique())}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'ok': False, 'hata': f'{type(e).__name__}: {e}'}, ensure_ascii=False)


# >>> ORTAK ÇIKTI: PARQUET + GÜNLÜK ALL PL (üç kodda aynı blok)
# Kategori/depo Excel'inin yanında iki çıktı daha üretilir:
#   • ana tablonun parquet hali  → ANA KLASÖR / parquet / gg.aa / kategori / <depo>.parquet
#   • günün tek Excel'i          → ANA KLASÖR / "15 Ekim All PL.xlsx"
#     (tüm kategori ve bölgelerin siparişli satırları, data takımının veritabanına çektiği dosya)
#     Birleştirme kaynağı: ANA KLASÖR / parquet / gg.aa / "15 Ekim All PL.parquet"
#     Aynı kategori + bölge yeniden çalışırsa eski satırları silinip yenileri yazılır.
import math as _m_math
import datetime as _m_dt
import numpy as _m_np
import pandas as _m_pd

PARQUET_KLASOR_ADI = 'parquet'
_AYLAR_TR = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']
ALLPL_KOLONLAR = ['tarih', 'kategori', 'bolge', 'depo_kodu', 'depo_adi', 'depo_tipi', 'urun_kodu', 'urun_adi', 'urun_grubu',
                  'birim', 'siparis_kati', 'teslim_tarihi', 'relex_oneri', 'final_miktar', 'kesilen_miktar', 'eklenen_miktar',
                  'kesinti_nedeni', 'final_hacim_litre', 'guncelleme_zamani',
                  'abc_sinifi', 'backlog_palet', 'etkili_backlog_palet', 'tir_limiti_palet',
                  'final_palet', 'backlog_kesilen_miktar']


def allpl_adi(tarih):
    t = _m_pd.Timestamp(tarih)
    return f"{t.day} {_AYLAR_TR[t.month - 1]} All PL"


def parquet_hazirla(df):
    """Parquet'in kabul etmediği karışık tipli kolonları düzeltir (sayıya, tarihe ya da metne çevirir)."""
    d = df.copy()
    d.columns = [str(c) for c in d.columns]
    if d.columns.duplicated().any():
        d = d.loc[:, ~d.columns.duplicated()]
    for c in d.columns:
        s = d[c]
        if isinstance(s.dtype, _m_pd.DatetimeTZDtype):
            s = d[c] = s.dt.tz_convert('Europe/Istanbul').dt.tz_localize(None)
        if _m_pd.api.types.is_datetime64_any_dtype(s.dtype):
            if str(s.dtype) != 'datetime64[ns]':
                d[c] = _m_pd.to_datetime(s.astype(object), errors='coerce').astype('datetime64[ns]')
            continue
        if _m_pd.api.types.is_timedelta64_dtype(s.dtype):
            d[c] = s.dt.total_seconds()
            continue
        if s.dtype != object:
            continue
        dolu = s.dropna()
        tipler = {type(x) for x in dolu}
        if not tipler or tipler <= {str}:
            d[c] = s.where(s.notna(), None)
            continue
        if all(issubclass(t, (int, float, _m_np.integer, _m_np.floating)) and not issubclass(t, (bool, _m_np.bool_)) for t in tipler):
            d[c] = _m_pd.to_numeric(s, errors='coerce')
        elif all(issubclass(t, (bool, _m_np.bool_)) for t in tipler):
            d[c] = s.map(lambda x: None if x is None or (isinstance(x, float) and _m_math.isnan(x)) else bool(x))
            d[c] = d[c].astype('boolean')
        elif all(issubclass(t, (_m_pd.Timestamp, _m_dt.datetime, _m_dt.date, _m_np.datetime64)) for t in tipler):
            d[c] = _m_pd.to_datetime(s, errors='coerce')
        else:
            d[c] = s.map(lambda x: None if x is None or (isinstance(x, float) and _m_math.isnan(x)) or x is _m_pd.NaT else str(x))
    return d


def parquet_yaz(df, yol):
    parquet_hazirla(df).to_parquet(yol, index=False, compression='snappy')


def _sayi(df, kolon):
    if kolon not in df.columns:
        return _m_pd.Series(0.0, index=df.index)
    return _m_pd.to_numeric(df[kolon], errors='coerce').fillna(0.0)


def _bos_sayi(df, kolon):
    """Sayısal kolon; kolon yoksa ya da değer okunamazsa boş (0 değil)."""
    if kolon not in df.columns:
        return _m_pd.Series(_m_np.nan, index=df.index, dtype='float64')
    return _m_pd.to_numeric(df[kolon], errors='coerce')


def _backlog_kesilen(df, oneri, final, neden):
    """Satırın backlog yüzünden kesilen miktarı.
    Ambient: palet limiti kesiminde backlog'a düşen pay (motor hesaplar), net kesimi aşamaz.
    +4 / MS: kesinti nedeni backlog blokajı/engeli olan satırın tüm kesimi."""
    kesilen = (oneri - final).clip(lower=0)
    if 'Backlog_Kesilen_Miktar' in df.columns:
        return _m_np.minimum(_m_pd.to_numeric(df['Backlog_Kesilen_Miktar'], errors='coerce').fillna(0.0), kesilen)
    if neden in df.columns:
        return kesilen.where(df[neden].astype(str).str.contains('backlog', case=False, na=False), 0.0)
    return kesilen * 0.0


def _tarih_kolonu(s):
    if _m_pd.api.types.is_datetime64_any_dtype(s.dtype):
        return _m_pd.to_datetime(s, errors='coerce').dt.tz_localize(None).dt.normalize() if getattr(s.dt, 'tz', None) else s.dt.normalize()
    m = s.astype(str).str.strip()
    gun = _m_pd.to_datetime(m, format='%d.%m.%Y', errors='coerce')
    return gun.fillna(_m_pd.to_datetime(m.where(gun.isna()), errors='coerce', format='mixed')).dt.normalize()


def allpl_satirlari(df, kategori, bolge, tarih, zaman=None):
    """Bir koşunun ana tablosunu All PL'nin ortak kolonlarına çevirir (yalnız önerisi ya da finali olan satırlar)."""
    c = set(df.columns)
    if 'Final_Quantity' in c:                                   # MS
        oneri, final = _sayi(df, 'Effective quantity'), _sayi(df, 'Final_Quantity')
        neden, kati, hacim = 'Trim_Reason', 'Order batch size', 'Final_Item_Volume'
        grup = df['Cabinet_Type'].astype(str) if 'Cabinet_Type' in c else ''
        birim = _m_np.where(df['Is_Bulk'].fillna(False).astype(bool), 'kg', 'adet') if 'Is_Bulk' in c else 'adet'
    elif 'Item_group' in c:                                     # Cold (+4)
        oneri, final = _sayi(df, 'Orijinal_Miktar'), _sayi(df, 'Final_Miktar')
        neden, kati, hacim = 'Kesinti_Nedeni', 'Order batch size', 'Final_Hacim_Litre'
        grup, birim = df['Item_group'].astype(str), 'adet'
    else:                                                       # Ambient & Su
        oneri, final = _sayi(df, 'Orijinal_Miktar'), _sayi(df, 'Final_Miktar')
        neden, kati, hacim = 'Kesinti_Nedeni', 'Order batch size', 'Final_Hacim_Litre'
        grup = _m_np.where(df['Is_Water'].fillna(False).astype(bool), 'Su', 'Ambient') if 'Is_Water' in c else 'Ambient'
        birim = 'adet'
    t = _m_pd.Timestamp(tarih).normalize()
    z = _m_pd.Timestamp(zaman) if zaman is not None else _m_pd.Timestamp.now(tz='Europe/Istanbul').tz_localize(None)
    al = lambda k: df[k] if k in c else None
    out = _m_pd.DataFrame({
        'tarih': t, 'kategori': str(kategori), 'bolge': str(bolge),
        'depo_kodu': al('Location code'), 'depo_adi': al('Location name'), 'depo_tipi': al('Domain Type'),
        'urun_kodu': al('Product code'), 'urun_adi': al('Product name'), 'urun_grubu': grup, 'birim': birim,
        'siparis_kati': _sayi(df, kati),
        'teslim_tarihi': _tarih_kolonu(df['Delivery date']) if 'Delivery date' in c else _m_pd.NaT,
        'relex_oneri': oneri, 'final_miktar': final,
        'kesilen_miktar': (oneri - final).clip(lower=0), 'eklenen_miktar': (final - oneri).clip(lower=0),
        'kesinti_nedeni': df[neden].astype(str) if neden in c else '',
        'final_hacim_litre': _sayi(df, hacim).round(4), 'guncelleme_zamani': z,
        # ürün-depo ABC sınıfı ve depo backlog'u (backlog kaynaklı kesim oranı analizi için)
        'abc_sinifi': al('ABC class'),
        'backlog_palet': _bos_sayi(df, 'Backlog_Palet_Sayisi' if 'Backlog_Palet_Sayisi' in c else 'Backlog'),
        'etkili_backlog_palet': _bos_sayi(df, 'Etkili_Backlog_Palet'),       # yalnız Ambient: tır zamanına göre kapıda sayılan backlog
        'tir_limiti_palet': _bos_sayi(df, 'Tir_Limiti'),                     # yalnız Ambient
        'final_palet': _bos_sayi(df, 'Final_Palet'),
        'backlog_kesilen_miktar': _backlog_kesilen(df, oneri, final, neden),
    }, index=df.index)
    out = out[(oneri > 0) | (final > 0)].reset_index(drop=True)
    for k in ('siparis_kati', 'relex_oneri', 'final_miktar', 'kesilen_miktar', 'eklenen_miktar', 'final_hacim_litre',
              'backlog_palet', 'etkili_backlog_palet', 'tir_limiti_palet', 'final_palet', 'backlog_kesilen_miktar'):
        out[k] = out[k].astype('float64')
    for k in ('depo_kodu', 'depo_adi', 'depo_tipi', 'urun_kodu', 'urun_adi', 'urun_grubu', 'birim', 'kesinti_nedeni', 'abc_sinifi'):
        out[k] = out[k].map(lambda x: None if x is None or (isinstance(x, float) and _m_math.isnan(x)) else str(x))
    return out[ALLPL_KOLONLAR]


def allpl_birlestir(eski, yeni, kategori, bolge):
    """Günün All PL tablosundan bu kategori + bölgenin eski satırlarını çıkarıp yenilerini ekler."""
    parcalar = []
    if eski is not None and len(eski):
        eski = eski.reindex(columns=ALLPL_KOLONLAR)
        parcalar.append(eski[~((eski['kategori'].astype(str) == str(kategori)) & (eski['bolge'].astype(str) == str(bolge)))])
    parcalar.append(yeni)
    d = _m_pd.concat([p for p in parcalar if len(p)], ignore_index=True) if any(len(p) for p in parcalar) else yeni.iloc[0:0]
    return d.reset_index(drop=True)


def allpl_excel_yaz(d, yol):
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font
    wb = Workbook(write_only=True)
    ws = wb.create_sheet('All PL')
    kalin = Font(bold=True)
    ws.append([WriteOnlyCell(ws, value=k) for k in d.columns])
    o = d.astype(object).where(d.notna(), None)
    for r in o.itertuples(index=False, name=None):
        ws.append([x.to_pydatetime() if isinstance(x, _m_pd.Timestamp) else x for x in r])
    wb.save(yol)


# <<< ORTAK ÇIKTI


# ================================================================== AMBIENT & SU
def _amb_water_hazirla(P, D):
    """Water WH dosyası kod tarafından UTF-16 sekmeli okunur; başka biçimde geldiyse çevrilir."""
    yol = P.get('DOSYA_WATER_WH')
    if not yol or not os.path.exists(yol): return
    ham = open(yol, 'rb').read()
    if ham[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return
    if ham[:2] == b'PK':
        d = pd.read_excel(io.BytesIO(ham), dtype=str)
    else:
        metin = ''
        for kod in ('utf-8-sig', 'cp1254', 'latin-1'):
            try: metin = ham.decode(kod); break
            except UnicodeDecodeError: continue
        ilk = metin.split('\n', 1)[0]
        ayr = '\t' if '\t' in ilk else (';' if ilk.count(';') > ilk.count(',') else ',')
        d = _ASIL_READ_CSV(io.StringIO(metin), sep=ayr, dtype=str, keep_default_na=False)
    d.columns = [str(c).strip() for c in d.columns]
    d.to_csv(yol, sep='\t', index=False, encoding='utf-16')


def _amb_neden(s):
    s = str(s or '')
    if not s or s == 'Islem Gormedi': return ''
    if 'Hacim Icin Kisildi' in s: return 'Dolap hacmi'
    if s.startswith('Su Depo Kapasitesi'): return 'Su palet alanı'
    if 'DİKEY PALET IPTAL' in s: return 'TIR limiti, dikey palet iptali'
    if 'Palet Limiti' in s: return 'TIR palet limiti'
    if 'Satir Limiti' in s: return 'Merkez satır limiti'
    if 'Koli Limiti' in s: return 'Merkez koli limiti'
    if 'End Balance DC' in s: return 'Merkez su stoğu' + (', dikey palet bozuldu' if 'BOZULDU' in s else '')
    if s == 'Sayım': return 'Sayım'
    if s == 'Test: Sadece A Segmenti': return 'Test: sadece A'
    if s.startswith('Dikey Elleçleme') or 'Paleti' in s or 'Palet (' in s: return 'Dikey palet yerleşimi'
    return s


def _amb_excel(G, sade):
    df = G['df']
    if sade: df = df[(df['Orijinal_Miktar'] > 0) | (df['Final_Miktar'] > 0)]
    s = [('Sheet1', [df]), ('Depo Ozet Karnesi', [G['depo_final_ozet']]), ('Detayli Kesinti Raporu', [G['islem_gorenler']])]
    if _dolu(G.get('_df_dikey_ozet')):
        s += [('Layout Uyum Kontrol', [G['_df_uyum']]), ('Dikey Palet Kontrol', [G['_df_dikey_kontrol']]),
              ('Dikey Ellecleme Ozet', [G['_df_dikey_ozet']])]
        if _dolu(G.get('_df_su_mutabakat')): s.append(('Su DC Mutabakat', [G['_df_su_mutabakat']]))
    if _dolu(G.get('_df_sayim_rapor')): s.append(('Sayim Kisiti', [G['_df_sayim_rapor']]))
    if _dolu(G.get('_df_ambient_gecis')): s.append(('Su-Ambient Gecis', [G['_df_ambient_gecis']]))
    if _dolu(G.get('_df_eksik_su')):
        s += [('Eksik Su Satirlari', [G['_df_eksik_su']]), ('Eksik Su Depo Ozet', [G['_eks_ozet']])]
    return s


def _amb_kontrol(G, log):
    df = G['df']; K = Kontrol()
    depo = df.groupby('Location name', dropna=True)
    g1 = 'Kaynak eşleşmesi'
    hac = depo['Avg. ambient_dolap_hacim'].first()
    K.liste(g1, 'Dolap hacmi tanımlı olmayan depolar', sorted(hac[(hac.isna()) | (hac.astype(float) <= 0)].index), 'uyari',
            'Ambient kapasite sheet’inde bulunamadı; bu depolarda hacim kısıtı uygulanmadı.')
    if 'location' in df.columns:
        sc = depo['location'].first(); eks = sorted(sc[sc.isna()].index)
    else:
        eks = sorted(depo.groups.keys())
    K.liste(g1, 'Teslimat programında olmayan depolar', eks, 'uyari', 'Teslim süresi 1 gün, önceki sipariş günü yok kabul edildi.')
    tk = depo['Tir_Limiti_Kaynagi'].first(); dt = depo['Domain Type'].first(); tl = depo['Tir_Limiti'].first()
    K.liste(g1, 'Günlük TIR limiti sheet’te olmayan depolar',
            [[x, dt.get(x), tl.get(x)] for x in sorted(tk[tk.astype(str).str.startswith('Kod')].index)], 'bilgi',
            'Varsayılan limit kullanıldı: G10 için 12, GB için 25 palet.', kolonlar=('Depo', 'Depo tipi', 'Kullanılan limit'))
    try:
        bl = set(G['df_dunku_sade']['Location name'].dropna())
        K.liste(g1, 'Dünkü sipariş / backlog dosyasında olmayan depolar', sorted(set(depo.groups.keys()) - bl), 'bilgi',
                'Bu depolarda backlog ve dünkü sipariş 0 kabul edildi.')
    except Exception:
        pass
    su = df['Is_Water'] == True
    def urun_liste(d):
        u = d.groupby('Product code').agg(ad=('Product name', 'first'), depo=('Location name', 'nunique')).reset_index()
        return u.values.tolist()
    if su.any():
        sl = df[su].groupby('Location name')['Max_Su_Palet_Kapasitesi'].first()
        K.liste(g1, 'Su palet alanı limiti olmayan depolar', sorted(sl[sl.isna()].index), 'uyari', 'Bu depolarda su palet alanı kısıtı uygulanmadı.')
        K.liste(g1, 'Palet adedi tanımsız su ürünleri', urun_liste(df[su & (pd.to_numeric(df['palet'], errors='coerce') >= 9999)]), 'uyari',
                'Su ürün listesinde yok; palet hesabında 9999 adet kabul edildi.', 'ürün', 'Hepsi tanımlı', ('Ürün kodu', 'Ürün', 'Depo sayısı'))
    amb = (~su) & (df['Orijinal_Miktar'] > 0) & (df['Cut_Priority'] != 101)
    K.liste(g1, 'Hacmi tanımsız ürünler', urun_liste(df[amb & pd.to_numeric(df['hacim2'], errors='coerce').isna()]), 'uyari',
            'Ürün hacmi sheet’inde yok; 0,5 L varsayıldı. Dolap hacmi aşımında bu ürünlerden kesinti yapılamaz.', 'ürün', 'Hepsi tanımlı',
            ('Ürün kodu', 'Ürün', 'Depo sayısı'))
    K.liste(g1, 'Palet bilgisinde olmayan ürünler', urun_liste(df[amb & df['SON'].isna()]), 'bilgi',
            'Koli içi adet yerine sipariş katı kullanıldı.', 'ürün', 'Hepsi tanımlı', ('Ürün kodu', 'Ürün', 'Depo sayısı'))
    g2 = 'Merkez depo'
    koli = float((df['Final_Miktar'] / df['SON_calculated']).sum()); kl = float(G['MAX_KOLI_LIMITI'])
    K.ekle(g2, 'Koli limiti', 'uyari' if koli > kl + 0.5 else 'ok', f'{koli:,.0f} / {kl:,.0f} koli'.replace(',', '.'),
           'Kesilebilecek satır kalmadığı için limit aşılı kaldı.' if koli > kl + 0.5 else '')
    sat = int((df['Final_Miktar'] > 0).sum()); sl_ = int(G['MAX_SATIR_LIMITI'])
    K.ekle(g2, 'Satır limiti', 'uyari' if sat > sl_ else 'ok', f'{sat:,} / {sl_:,} satır'.replace(',', '.'))
    mt = G.get('_df_su_mutabakat')
    if _dolu(mt):
        kot = mt[mt['Durum'].astype(str) != 'OK']
        K.ekle(g2, 'Merkez su stoğu', 'uyari' if len(kot) else 'ok', f'{len(kot)} ürün kontrol edilemedi / aşıyor' if len(kot) else 'Tüm ürünlerde yeterli',
               'Merkez stok verisi olmayan ya da hâlâ aşan su ürünleri.', [str(c) for c in kot.columns], kot.values.tolist())
    K.gunluk(log)
    return K.K


def _amb_cikti(G, log):
    df = G['df'].copy()
    su = df['Is_Water'] == True
    fark = pd.to_numeric(df['Fark (Kesilen Miktar)'], errors='coerce').fillna(0)
    df['_kes'] = fark.clip(lower=0); df['_ekl'] = (-fark).clip(lower=0)
    df['_neden'] = [(_amb_neden(n) if (k > 0 or e > 0) else '') for n, k, e in zip(df['Kesinti_Nedeni'], df['_kes'], df['_ekl'])]
    df['_ad'] = df['Product name'].where(df['Product name'].notna() & (df['Product name'].astype(str).str.strip() != ''), df['Product code']).astype(str)
    df['_tip'] = np.where(su, 'Su', np.where(df['Cut_Priority'] == 101, 'Demirbaş', 'Ambient'))
    O = float(df['Orijinal_Miktar'].sum()); Kk = float(df['_kes'].sum())
    koli = float((df['Final_Miktar'] / df['SON_calculated']).sum())
    _son = pd.to_numeric(df['SON_calculated'], errors='coerce').replace(0, np.nan)
    _sim_final = (pd.to_numeric(df['Final_Miktar'], errors='coerce').fillna(0) / _son).where(~su, 0).fillna(0)
    _sim_oneri = (pd.to_numeric(df['Effective quantity'], errors='coerce').fillna(0) / _son).where(~su, 0).fillna(0)
    sim_depo = _sim_final.groupby(df['Location name']).sum()
    kpi = [
        {'ad': 'Kesinti oranı (adet)', 'deger': _pct(Kk, O), 'birim': '%', 'vurgu': True},
        {'ad': 'Kesilen', 'deger': Kk, 'birim': 'adet'},
        {'ad': 'Kesinti olan depo', 'deger': int(df.loc[df['_kes'] > 0, 'Location name'].nunique()), 'birim': f"/ {df['Location name'].nunique()}"},
        {'ad': 'Sevk hacmi', 'deger': float(df['Final_Hacim_Litre'].sum()), 'birim': 'L'},
        {'ad': 'Sevk paleti', 'deger': float(df['Final_Palet'].sum()), 'birim': 'palet'},
        {'ad': 'Öneri koli, su hariç', 'deger': float(_sim_oneri.sum()), 'birim': 'koli'},
        {'ad': 'Final koli, su hariç', 'deger': float(_sim_final.sum()), 'birim': 'koli'},
    ]
    merkez = [{'ad': 'Koli', 'deger': koli, 'limit': float(G['MAX_KOLI_LIMITI']), 'birim': 'koli'},
              {'ad': 'Satır', 'deger': int((df['Final_Miktar'] > 0).sum()), 'limit': float(G['MAX_SATIR_LIMITI']), 'birim': 'satır'}]
    sayimli = sorted(df.loc[df['Sayim_Kisiti'] == True, 'Location name'].dropna().unique().tolist())
    oz = G['depo_final_ozet'].copy().set_index('Location name')
    def ozk(c): return lambda a: oz.loc[a, c] if a in oz.index else None
    depo_tablo = depo_ozeti(df, 'Location name', 'Orijinal_Miktar', 'Final_Miktar', '_kes', '_neden', tip='Domain Type', ekler=[
        ('Hacim doluluk %', ozk('Gelecek_Teslimat_Sonrasi_Doluluk (%)')),
        ('TIR yükü', lambda a: (_sf(oz.loc[a, 'Depo_Final_Palet_Toplami']) + _sf(oz.loc[a, 'Etkili_Sarkan_Backlog'])) if a in oz.index else None),
        ('TIR limiti', ozk('Tir_Limiti'))])
    depo_tablo['asim'] = [['TIR yükü', 'TIR limiti']]
    # ---- palet limitinden kısılıp hacmi dolmayan depolar
    amb = (~su) & (df['Cut_Priority'] != 101)
    son50 = (pd.to_numeric(df['SON_calculated'], errors='coerce').fillna(1) * 50).replace(0, 50)
    ad_ = df.assign(_po=np.where(amb, df['Orijinal_Miktar'] / son50, 0),
                    _ho=np.where(amb, df['Orijinal_Miktar'] * pd.to_numeric(df['hacim2'], errors='coerce').fillna(0.5), 0))
    ag = ad_.groupby('Location name').agg(po=('_po', 'sum'), ho=('_ho', 'sum'))
    ag_lpp = float(ag['ho'].sum() / ag['po'].sum()) if ag['po'].sum() > 0 else None
    paletli = set(df.loc[df['Kesinti_Nedeni'].astype(str).str.contains('Palet Limiti', na=False) & (df['_kes'] > 0), 'Location name'])
    palet_rapor, doldurma = [], {}
    for a_, r in ag.iterrows():
        if a_ not in oz.index: continue
        z = oz.loc[a_]
        M = _sf(z['Maksimum_Hacim_Litre']); N = _sf(z['Net_Hacim_Boslugu_Litre']); F = _sf(z['Final_Toplam_Hacim_Litre'])
        lpp = float(r['ho'] / r['po']) if r['po'] > 0.05 else ag_lpp
        bos = N - F
        dp = (bos / lpp) if (M > 0 and lpp and bos > 0) else 0.0
        doldurma[a_] = {'lpp': lpp, 'bos': bos if M > 0 else None, 'doldur': dp}
        if a_ in paletli and M > 0 and bos > 0:
            palet_rapor.append([a_, z['Domain_Type'], z['Gelecek_Teslimat_Sonrasi_Doluluk (%)'], bos, z['Depo_Orijinal_Palet_Toplami'],
                                z['Depo_Final_Palet_Toplami'], _sf(z['Depo_Orijinal_Palet_Toplami']) - _sf(z['Depo_Final_Palet_Toplami']),
                                dp, z['Tir_Limiti'], z['Etkili_Sarkan_Backlog']])
    palet_rapor.sort(key=lambda x: -(x[7] or 0))
    ek = [{'baslik': 'Paletten kısılan ama hacmi dolmayan depolar',
           'alt': 'TIR palet limiti yüzünden kısılan, teslim sonrası dolap hacmi %100’ün altında kalan depolar. “Doldurmak için palet”: kalan boş hacmi doldurmak için gereken ambient palet (deponun kendi litre/palet ortalamasıyla).',
           'ozet': f"Toplam {sum(x[7] for x in palet_rapor):,.1f} palet daha gönderilebilirdi".replace(',', 'X').replace('.', ',').replace('X', '.') if palet_rapor else '',
           'tablo': _tablo(['Depo', 'Tip', 'Teslim sonrası doluluk %', 'Boş hacim L', 'Mevcut palet', 'Gönderilen palet', 'Kısılan palet',
                            'Doldurmak için palet', 'TIR limiti', 'Sarkan backlog'], palet_rapor),
           'vurgu': 'Doldurmak için palet', 'link': 'Depo', 'bos': 'Böyle bir depo yok.'}]
    _fazla = _fazla_stok(df, 'Location name', 'Product code', '_ad', 'Effective quantity', 'adet')
    _buyuk = _buyuk_oneri(df, 'Location name', '_ad', df['Effective quantity'], df['Effective quantity'], df.get('hacim2'),
                          'Ambient', df.get('Avg. ambient_dolap_hacim'), 'adet')
    _oneri = {'kartlar': [_buyuk['kart']] + _fazla['kartlar'], 'sayi': _fazla['sayi'] + _buyuk['sayi']}
    # ---- depo detayı
    kol = [('Depo', 'Location name'), ('Ürün', '_ad'), ('Tip', '_tip'), ('Öneri', 'Orijinal_Miktar'), ('Final', 'Final_Miktar'),
           ('Kesilen', '_kes'), ('Neden', '_neden'), ('Cover final', 'Final_Cover_Gun')]
    es_vars = float(G['HARD_STOP_CAPACITY'])
    ilk = df.groupby('Location name').first()
    sudf = df[su]
    su_mev = sudf.groupby('Location name')['Mevcut_Kaplanan_Su_Paleti'].sum()
    su_fin = sudf.assign(_p=sudf['Final_Miktar'] / sudf['palet']).groupby('Location name')['_p'].sum()
    su_on = sudf.assign(_p=sudf['Orijinal_Miktar'] / sudf['palet']).groupby('Location name')['_p'].sum()
    lay = df[df['Layout_Tipi'] != '-'].groupby('Location name')['Layout_Tipi'].first() if 'Layout_Tipi' in df.columns else pd.Series(dtype=str)
    dg = df.groupby('Location name').agg(o=('Orijinal_Miktar', 'sum'), k=('_kes', 'sum'))
    depolar = {}
    for a, z in oz.iterrows():
        f = ilk.loc[a] if a in ilk.index else pd.Series(dtype=object)
        gv = lambda c: f[c] if c in f.index else None
        es = _sf(gv('Hard_Stop_Orani')) or es_vars          # depo bazlı (Buffer Rates → Ambient Buffer)
        M = _sf(z['Maksimum_Hacim_Litre']); N = _sf(z['Net_Hacim_Boslugu_Litre'])
        L = _sf(z['Tir_Limiti']); B = _sf(z['Etkili_Sarkan_Backlog'])
        Po = _sf(z['Depo_Orijinal_Palet_Toplami']); Pf = _sf(z['Depo_Final_Palet_Toplami'])
        dd_ = doldurma.get(a, {}); layout = lay.get(a)
        defter = [{'bolum': 'Dolap hacmi, litre'}]
        if M > 0:
            defter += [{'ad': 'Dolap hacmi', 'deger': M},
                       {'op': '−', 'ad': 'Mevcut + yoldaki hacim', 'deger': _sf(gv('ambient_volume Litre')) + _sf(gv('ambient_volume Litre (Total Transit)'))},
                       {'op': '+', 'ad': 'Teslime kadar satılacak', 'deger': gv('Bosalacak_Hacim_Litre')},
                       {'op': '=', 'ad': 'Teslim günü boş hacim', 'deger': N, 'sinif': 'd-ara'},
                       {'op': '+', 'ad': 'Esnek pay', 'not': f'%{(es - 1) * 100:g}', 'deger': M * (es - 1)},
                       {'op': '=', 'ad': 'Hacim limiti', 'deger': N + M * (es - 1), 'sinif': 'd-ara'},
                       {'ad': 'Final hacim', 'not': f"öneri {_sf(z['Onerilen_Toplam_Hacim_Litre']):,.0f}".replace(',', '.'), 'deger': z['Final_Toplam_Hacim_Litre'], 'sinif': 'd-sonuc'}]
            if _sf(dd_.get('bos')) > 0:
                defter += [{'ad': 'Teslim sonrası kalan boş hacim', 'deger': dd_['bos']},
                           {'ad': 'Doldurmak için palet', 'not': f"~{dd_['lpp']:,.0f} L/palet".replace(',', '.') if dd_.get('lpp') else '', 'deger': dd_['doldur'], 'sinif': 'd-ara'}]
        else:
            defter.append({'ad': 'Dolap hacmi tanımlı değil, kısıt uygulanmadı', 'deger': None})
        defter += [{'bolum': 'TIR, palet'},
                   {'ad': 'Günlük limit', 'not': 'varsayılan' if str(z['Tir_Limiti_Kaynagi']).startswith('Kod') else '', 'deger': L},
                   {'op': '−', 'ad': 'Sarkan backlog', 'deger': B}, {'op': '=', 'ad': 'Sipariş için yer', 'deger': L - B, 'sinif': 'd-ara'},
                   {'ad': 'Mevcut palet', 'not': 'öneri', 'deger': Po}, {'op': '−', 'ad': 'Kısılan palet', 'deger': Po - Pf},
                   {'op': '=', 'ad': 'Gönderilen palet', 'deger': Pf, 'sinif': 'd-sonuc'}]
        sa = gv('Max_Su_Palet_Kapasitesi')
        dol = []
        if M > 0: dol.append({'ad': 'Hacim', 'birim': 'L', 'doluAd': 'Teslim günü dolu', 'dolu': M - N, 'fin': z['Final_Toplam_Hacim_Litre'],
                              'kes': _sf(z['Onerilen_Toplam_Hacim_Litre']) - _sf(z['Final_Toplam_Hacim_Litre']), 'tavan': M * es})
        dol.append({'ad': 'TIR', 'birim': 'palet', 'doluAd': 'Sarkan backlog', 'dolu': B, 'fin': Pf, 'kes': Po - Pf, 'tavan': L})
        if sa is not None and not pd.isna(sa) and not layout:
            defter += [{'bolum': 'Su alanı, palet'}, {'ad': 'Su palet alanı', 'deger': sa},
                       {'op': '−', 'ad': 'Dolu su paleti', 'deger': su_mev.get(a)},
                       {'op': '=', 'ad': 'Boş su alanı', 'deger': _sf(sa) - _sf(su_mev.get(a)), 'sinif': 'd-ara'},
                       {'ad': 'Final su paleti', 'not': f"öneri {_sf(su_on.get(a)):.1f}".replace('.', ','), 'deger': su_fin.get(a), 'sinif': 'd-sonuc'}]
            dol.append({'ad': 'Su alanı', 'birim': 'palet', 'doluAd': 'Dolu su paleti', 'dolu': su_mev.get(a), 'fin': su_fin.get(a),
                        'kes': _sf(su_on.get(a)) - _sf(su_fin.get(a)), 'tavan': sa})
        o_, k_ = (dg.loc[a, 'o'], dg.loc[a, 'k']) if a in dg.index else (0, 0)
        roz = [{'metin': z['Domain_Type']}]
        if gv('Teslimat_Tarihi') is not None: roz.append({'metin': 'Teslim ' + str(_t(gv('Teslimat_Tarihi')))})
        if layout: roz.append({'metin': layout, 'tur': 'mor'})
        if gv('Sayim_Bilgisi'): roz.append({'metin': 'Sayım: ' + str(gv('Sayim_Bilgisi')), 'tur': 'kirmizi'})
        if _norm(a) in {_norm(x) for x in (G.get('SADECE_A_TEST_DEPOLARI') or [])}:
            roz.append({'metin': 'Test: sadece A · TIR ve merkez limitleri uygulanmadı', 'tur': 'mor'})
        if a in paletli and _sf(dd_.get('bos')) > 0:
            roz.append({'metin': f"Paletten kısıldı · hacim %{_sf(z['Gelecek_Teslimat_Sonrasi_Doluluk (%)']):.1f} dolu".replace('.', ','), 'tur': 'kirmizi'})
        if str(gv('Backlog_Limiti_Asildi') or '').startswith('Asildi'): roz.append({'metin': 'Backlog kritik', 'tur': 'kirmizi'})
        depolar[a] = {'rozetler': roz, 'defter': [{k: _t(v) for k, v in x.items()} for x in defter],
                      'doluluk': [{k: _t(v) for k, v in x.items()} for x in dol],
                      'kpi': [['Kesinti oranı (adet)', _pct(k_, o_), '%', True], ['Kesilen', _t(k_), 'adet'],
                              ['Final hacim', _t(z['Final_Toplam_Hacim_Litre']), 'L'], ['Final palet', _t(Pf), 'palet'],
                              ['SİM koli, su hariç', _t(float(sim_depo.get(a, 0))), 'koli']]}
    _amb_k = _amb_kontrol(G, log)
    return {'kpi': kpi,
            'ozet': {'nedenler': neden_ozeti(df, 'Location name', '_kes', '_neden'), 'merkez': merkez, 'sayimli': sayimli, 'ekKartlar': ek},
            'depo_tablo': depo_tablo, 'kontrol': _amb_k, 'oneri': _oneri,
            'detay': {**satir_detay(df, kol, (df['Orijinal_Miktar'] > 0) | (df['Final_Miktar'] > 0)), 'depolar': depolar}}


URUNLER['amb'] = {
    'motor': 'MOTOR_AMB',
    'ana': lambda G: G['df'], 'gid_sayi': True,
    'paramlar': ['CALISILAN_DEPO', 'CALISILAN_KATEGORI', 'MAX_SATIR_LIMITI', 'MAX_KOLI_LIMITI', 'HARD_STOP_CAPACITY',
                 'PALETIN_YUZDE_KACI', 'DIKEY_MIN_PAY', 'GB_COVER_DAY_LIMIT', 'G10_COVER_DAY_LIMIT', 'A_MIN_COVER', 'B_MIN_COVER', 'C_MIN_COVER',
                 'DOKUNULMAYACAK_URUNLER_G10', 'DOKUNULMAYACAK_URUNLER_GB', 'SADECE_A_TEST_DEPOLARI', 'AMBIENT_GECIS_URUNLERI', 'AMBIENT_GECIS_DEPO_AD_ANAHTAR',
                 'DIKEY_DEPO_BATCH', 'MIDI_L1_DEPO_KODU', 'MINI_L1_DEPO_KODLARI', 'MINI_L2_DEPO_KODLARI', 'XS_L1_DEPO_KODLARI',
                 'XS_L2_DEPO_KODLARI', 'XS_L3_DEPO_KODLARI', 'XS_L1_V2_DEPO_KODLARI', 'XS_L2_V2_DEPO_KODLARI', 'XS_L3_V2_DEPO_KODLARI',
                 'MINI_L2_V2_DEPO_KODLARI'],
    'dosyalar': [('relex', 'param', 'DOSYA_RELEX'), ('backlog', 'param', 'DOSYA_DUNKU_RAPOR'), ('water', 'param', 'DOSYA_WATER_WH')],
    'sheetler': [{'key': 'urun', 'url': 'GSHEET_URUN_URL', 'gid': 'URUN_GID'}, {'key': 'ambient', 'url': 'GSHEET_AMBIENT_URL', 'gid': 'AMBIENT_GID'},
                 {'key': 'gunluk', 'url': 'GSHEET_GUNLUK_PALET_URL', 'gid': 'GUNLUK_PALET_GID'},
                 {'key': 'schedule', 'url': 'GSHEET_SCHEDULE_URL', 'gid': 'SCHEDULE_GID'},
                 {'key': 'sayim', 'url': 'GSHEET_SAYIM_URL', 'gid': 'SAYIM_GID'}, {'key': 'fast', 'url': 'GSHEET_FAST_ACC_URL', 'gid': 'FAST_ACC_GID'},
                 {'key': 'kampanya', 'url': 'GSHEET_KAMPANYA_URL', 'gid': 'KAMPANYA_GID'}, {'key': 'sim', 'url': 'GSHEET_SIM_URL', 'gid': 'SIM_GID'},
                 {'key': 'suliste', 'url': 'GSHEET_SU_LISTE_URL', 'gid': 'SU_LISTE_GID'}, {'key': 'paletalani', 'url': 'GSHEET_SU_PALET_ALANI_URL', 'gid': 'SU_PALET_ALANI_GID'},
                 {'key': 'buffer', 'url': 'GSHEET_BUFFER_URL', 'gid': 'BUFFER_GID'}],
    'imzalar': [('backlog', ['Backlog_Palet_Sayisi'], ['backlog']),        # dünkü çıktı Relex kolonlarını da taşır, önce bakılır
                ('relex', ['Effective quantity', 'Location code', 'Product code'], ['relex']),
                ('water', ['Warehouse Available Stock'], ['water', 'utilization'])],
    'hazirlik': _amb_water_hazirla, 'excel': _amb_excel, 'cikti': _amb_cikti,
}


# ================================================================== COLD (+4)
def _cold_neden(s):
    s = str(s or '')
    if not s or s == 'Islem Gormedi': return ''
    if s == 'Depo Backlog Blokaji': return 'Backlog blokajı'
    if s == 'Sayım': return 'Sayım'
    if s == 'Test: Sadece A Segmenti': return 'Test: sadece A'
    if s.startswith('Kapasite Zorlamasi (ETB'): return 'Dolap hacmi (ETB)'
    if s.startswith('Kapasite Zorlamasi'): return 'Dolap hacmi (Other)'
    if 'Satir Limiti' in s: return 'Merkez satır limiti'
    return s


def _cold_excel(G, sade):
    df = G['df_final']
    if sade: df = df[(pd.to_numeric(df['Orijinal_Miktar'], errors='coerce').fillna(0) > 0) | (df['Final_Miktar'] > 0)]
    s = [('Sheet1', [df]), ('Transfer', [G['transfer_df']]), ('Depo Ozet Karnesi', [G['depo_final_ozet']]),
         ('Kapasite Detayi', [G['kapasite_detay']]), ('Slot Lookahead Kontrol', [G['slot_kontrol']])]
    if _dolu(G.get('sayim_rapor')): s.append(('Sayim Kisiti', [G['sayim_rapor']]))
    s += [('Debug Ozet', [G['debug_ozet'], G['debug_depo']]), ('Debug Detay', [G['debug_detay']])]
    return s


_COLD_SEVIYE = {'KRİTİK': 'hata', 'UYARI': 'uyari', 'BİLGİ': 'bilgi'}

def _cold_kontrol(G, log, df):
    K = Kontrol()
    kd = G['kapasite_detay']
    yok = kd[kd['Doluluk_Tablosunda_Var_Mi'] != True][['Location name', 'Item_group']].values.tolist()
    K.liste('Kaynak eşleşmesi', 'Kapasite verisi olmayan depolar', yok, 'uyari',
            'Doluluk sheet’inde bulunamadı; bu depo / gruplarda hacim kısıtı uygulanmadı.', kolonlar=('Depo', 'Grup'))
    n = int((df['Final_Miktar'] > 0).sum()); lim = G['MAX_SATIR_LIMITI_YENI']
    K.ekle('Merkez depo', 'Satır limiti', 'uyari' if n > lim else 'ok', f'{n:,} / {lim:,} satır'.replace(',', '.'))
    dd = G.get('debug_detay'); do = G.get('debug_ozet')
    if isinstance(do, pd.DataFrame):
        for _, r in do.iterrows():
            alt = dd[dd['Kod'] == r['Kod']] if isinstance(dd, pd.DataFrame) else pd.DataFrame()
            K.ekle('Veri kalitesi', f"{r['Kontrol']}", _COLD_SEVIYE.get(r['Seviye'], 'bilgi'),
                   f"{int(r['Kayit_Sayisi'])} kayıt · {int(r['Etkilenen_Depo'])} depo", r['Ne_Yapmali'],
                   ['Depo', 'Ürün', 'Grup', 'Değer', 'Eşik'],
                   alt[['Location name', 'Product name', 'Item_group', 'Deger', 'Esik']].values.tolist() if len(alt) else None)
    K.gunluk(log)
    return K.K


def _cold_cikti(G, log):
    df = G['df_final'].copy()
    for c in ('Orijinal_Miktar', 'Final_Miktar', 'Daily FC', 'End balance', 'Open purchase orders'):
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    df['_kes'] = (df['Orijinal_Miktar'] - df['Final_Miktar']).clip(lower=0)
    df['_neden'] = [_cold_neden(n) if k > 0 else '' for n, k in zip(df['Kesinti_Nedeni'], df['_kes'])]
    df['_ad'] = df['Product name'].fillna(df['Product code']).astype(str)
    fc = df['Daily FC'].where(df['Daily FC'] > 0)
    df['_cover'] = ((df['End balance'].clip(lower=0) + df['Open purchase orders'].clip(lower=0) + df['Final_Miktar']) / fc).round(1)
    O = float(df['Orijinal_Miktar'].sum()); Kk = float(df['_kes'].sum())
    aktif = df['Final_Miktar'] > 0
    kpi = [{'ad': 'Kesinti oranı (adet)', 'deger': _pct(Kk, O), 'birim': '%', 'vurgu': True},
           {'ad': 'Kesilen', 'deger': Kk, 'birim': 'adet'},
           {'ad': 'Kesinti olan depo', 'deger': int(df.loc[df['_kes'] > 0, 'Location name'].nunique()), 'birim': f"/ {df['Location name'].nunique()}"},
           {'ad': 'Sevk hacmi', 'deger': float(pd.to_numeric(df['Final_Hacim_Litre'], errors='coerce').fillna(0).sum()), 'birim': 'L'},
           {'ad': 'Aktif satır', 'deger': int(aktif.sum()), 'birim': ''}]
    merkez = [{'ad': 'Satır', 'deger': int(aktif.sum()), 'limit': float(G['MAX_SATIR_LIMITI_YENI']), 'birim': 'satır'}]
    sayimli = sorted(df.loc[df['Sayim_Kisiti'] == True, 'Location name'].dropna().unique().tolist())
    oz = G['depo_final_ozet'].set_index(['Location name', 'Item_group'])
    def dol(g): return lambda a: oz.loc[(a, g), 'Gelecek_Teslimat_Sonrasi_Doluluk (%)'] if (a, g) in oz.index else None
    depo_tablo = depo_ozeti(df, 'Location name', 'Orijinal_Miktar', 'Final_Miktar', '_kes', '_neden', tip='Domain Type',
                            ekler=[('ETB doluluk %', dol('ETB')), ('Other doluluk %', dol('Other'))])
    # ---- ek kartlar
    ek = []
    sk = G['slot_kontrol']; sk = sk[sk['Slot_Ogle_Oncesi_Biten'] == True]
    if len(sk):
        ek.append({'baslik': 'Slot saati 12:00’den önce biten depolar',
                   'alt': 'Bu depolarda teslimattan sonraki günün satışı boşalacak hacme eklenmedi. Kural etkisi: bu yüzden kapasiteye eklenmeyen hacim.',
                   'ozet': f"Toplam {sk['Slot_Kurali_Etkisi_Litre'].sum():,.0f} L".replace(',', '.'),
                   'tablo': _df_tablo(sk.rename(columns={'Location name': 'Depo', 'Item_group': 'Grup', 'Slot_Bitis_Saati': 'Slot bitiş',
                                                          'Slot_Kurali_Etkisi_Litre': 'Kural etkisi L', 'Kullanilabilir_Limit_Litre': 'Teslim günü boş alan L'}),
                                      ['Depo', 'Grup', 'Slot bitiş', 'Kural etkisi L', 'Teslim günü boş alan L']),
                   'link': 'Depo', 'vurgu': 'Kural etkisi L'})
    bl = df[df['Kesinti_Nedeni'] == 'Depo Backlog Blokaji'].groupby('Location name').agg(
        tip=('Domain Type', 'first'), b=('Backlog_Palet_Sayisi', 'max'), k=('_kes', 'sum')).reset_index()
    if len(bl):
        ek.append({'baslik': 'Backlog nedeniyle sipariş verilmeyen depolar', 'alt': 'G10’da 1, GB’de 3 ve üstü palet backlog olan depolara bugün sevk yok.',
                   'ozet': f'{len(bl)} depo', 'tablo': _tablo(['Depo', 'Tip', 'Backlog palet', 'Engellenen adet'], bl.values.tolist()), 'link': 'Depo'})
    _oneri_kol = 'Effective quantity' if 'Effective quantity' in df.columns else 'Orijinal_Miktar'
    _fazla = _fazla_stok(df, 'Location name', 'Product code', '_ad', _oneri_kol, 'adet')
    _buyuk = _buyuk_oneri(df, 'Location name', '_ad', df['Orijinal_Miktar'], df['Orijinal_Miktar'], df.get('hacim2'),
                          df['Item_group'], df.get('Kapasite_Ham_Litre'), 'adet')
    _oneri = {'kartlar': [_buyuk['kart']] + _fazla['kartlar'], 'sayi': _fazla['sayi'] + _buyuk['sayi']}
    # ---- depo detayı
    kd = G['kapasite_detay']
    adet = {_norm(k): v for k, v in (G.get('DEPO_ADET_LIMITI') or {}).items()}
    dg = df.groupby('Location name').agg(o=('Orijinal_Miktar', 'sum'), k=('_kes', 'sum'), f=('Final_Hacim_Litre', 'sum'),
                                         a=('Final_Miktar', lambda s: int((s > 0).sum())), dt=('Domain Type', 'first'),
                                         sayim=('Sayim_Bilgisi', 'first'), slot=('Slot_Bitis_Saati', 'first'),
                                         slotb=('Slot_Ogle_Oncesi_Biten', 'first'), bl=('Kesinti_Nedeni', lambda s: (s == 'Depo Backlog Blokaji').any()),
                                         tes=('Teslimat_Tarihi', 'first'))
    depolar = {}
    for a, r in dg.iterrows():
        defter, dolu = [], []
        for _, k in kd[kd['Location name'] == a].iterrows():
            grup = k['Item_group']
            defter.append({'bolum': f"{grup} havuzu, litre"})
            if k['Doluluk_Tablosunda_Var_Mi'] != True:
                defter.append({'ad': 'Kapasite verisi yok, kısıt uygulanmadı', 'deger': None}); continue
            kap = _sf(k['Kapasite_Kullanilabilir_Litre'])
            defter += [{'ad': 'Ham kapasite', 'deger': k['Kapasite_Ham_Litre']},
                       {'ad': 'Kullanılabilir kapasite', 'not': f"× %{_sf(k['Uygulanan_Oran']) * 100:g} oran × %{_sf(k['Uygulanan_Buffer']) * 100:g} buffer",
                        'deger': kap, 'sinif': 'd-ara'},
                       {'op': '−', 'ad': 'Mevcut + yoldaki stok', 'deger': k['Stok_Plus_Transit_Litre']},
                       {'op': '+', 'ad': 'Teslime kadar satılacak', 'not': 'ertesi gün eklenmedi (slot)' if k['Slot_Ogle_Oncesi_Biten'] else '',
                        'deger': k['Forecast_Bosalacak_Toplam_Litre']},
                       {'op': '=', 'ad': 'Teslim günü boş alan', 'deger': k['Teslimatta_Bos_Alan_Litre'], 'sinif': 'd-ara'},
                       {'ad': 'Final hacim', 'not': f"öneri {_sf(k['Onerilen_Hacim_Litre']):,.0f}".replace(',', '.'), 'deger': k['Final_Hacim_Litre'], 'sinif': 'd-sonuc'}]
            dolu.append({'ad': grup, 'birim': 'L', 'doluAd': 'Teslim günü dolu', 'dolu': k['Teslimatta_Dolu_Litre'], 'fin': k['Final_Hacim_Litre'],
                         'kes': max(0, _sf(k['Onerilen_Hacim_Litre']) - _sf(k['Final_Hacim_Litre'])), 'tavan': kap})
        roz = [{'metin': r['dt']}]
        if not pd.isna(r['tes']): roz.append({'metin': 'Teslim ' + str(_t(r['tes']))})
        if r['slotb']: roz.append({'metin': f"Slot {r['slot']} bitiyor"})
        if r['sayim']: roz.append({'metin': 'Sayım: ' + str(r['sayim']), 'tur': 'kirmizi'})
        if r['bl']: roz.append({'metin': 'Backlog blokajı', 'tur': 'kirmizi'})
        if _norm(a) in adet: roz.append({'metin': f"Adet limiti {adet[_norm(a)]}"})
        if _norm(a) in {_norm(x) for x in (G.get('SADECE_A_TEST_DEPOLARI') or [])}:
            roz.append({'metin': 'Test: sadece A · merkez limitleri uygulanmadı', 'tur': 'mor'})
        depolar[a] = {'rozetler': roz, 'defter': [{x: _t(v) for x, v in d.items()} for d in defter],
                      'doluluk': [{x: _t(v) for x, v in d.items()} for d in dolu],
                      'kpi': [['Kesinti oranı (adet)', _pct(r['k'], r['o']), '%', True], ['Kesilen', _t(r['k']), 'adet'],
                              ['Final hacim', _t(r['f']), 'L'], ['Aktif satır', int(r['a']), '']]}
    kol = [('Depo', 'Location name'), ('Ürün', '_ad'), ('Grup', 'Item_group'), ('Öneri', 'Orijinal_Miktar'), ('Final', 'Final_Miktar'),
           ('Kesilen', '_kes'), ('Neden', '_neden'), ('Cover final', '_cover')]
    _cold_k = _cold_kontrol(G, log, df)
    return {'kpi': kpi,
            'ozet': {'nedenler': neden_ozeti(df, 'Location name', '_kes', '_neden'), 'merkez': merkez, 'sayimli': sayimli, 'ekKartlar': ek},
            'depo_tablo': depo_tablo, 'kontrol': _cold_k, 'oneri': _oneri,
            'detay': {**satir_detay(df, kol, (df['Orijinal_Miktar'] > 0) | (df['Final_Miktar'] > 0)), 'depolar': depolar}}


_COLD_SID = 'SPREADSHEET_ID'
URUNLER['cold'] = {
    'motor': 'MOTOR_COLD',
    'ana': lambda G: G['df_final'],
    'paramlar': ['CALISILAN_DEPO', 'CALISILAN_KATEGORI', 'MAX_SATIR_LIMITI_YENI',
                 'PLUS_4_USABLE_RATIO', 'FORECAST_LOOKAHEAD_RATIO', 'GB_COVER_DAY_LIMIT', 'G10_COVER_DAY_LIMIT',
                 'A_MIN_COVER', 'B_MIN_COVER', 'C_MIN_COVER', 'G10_DEFAULT_OTHER4_ORAN', 'G10_DEFAULT_ETB_ORAN',
                 'GB_DEFAULT_OTHER4_ORAN', 'GB_DEFAULT_ETB_ORAN', 'DOKUNULMAYACAK_G10', 'DOKUNULMAYACAK_GB',
                 'G10_TIPI_DEPOLAR', 'DEPO_ADET_LIMITI', 'SADECE_A_TEST_DEPOLARI'],
    'dosyalar': [('relex', 'param', 'DOSYA_RELEX'), ('backlog', 'param', 'DOSYA_BACKLOG')],
    'sheetler': [{'key': 'buffer', 'gid': 'BUFFER_GID', 'sid': _COLD_SID}, {'key': 'oran', 'gid': 'ORAN_GID', 'sid': _COLD_SID},
                 {'key': 'pooled', 'gid': 'POOLED_GID', 'sid': _COLD_SID},
                 {'key': 'slot', 'gid': 'SLOT_GID', 'sid': _COLD_SID}, {'key': 'hacim', 'gid': 'URUN_HACIM_GID', 'sid': _COLD_SID},
                 {'key': 'sayim', 'gid': 'SAYIM_GID', 'sid': 'SAYIM_SPREADSHEET_ID'}, {'key': 'kampanya', 'gid': 'KAMPANYA_GID', 'sid': _COLD_SID}],
    'imzalar': [('backlog', ['Backlog_Palet_Sayisi'], ['backlog']),
                ('relex', ['Effective quantity', 'Location code', 'Product code'], ['relex', '+4', 'cold'])],
    'excel': _cold_excel, 'cikti': _cold_cikti,
}


# ================================================================== MS (meyve sebze)
_MS_NEDEN = {
    'Kara Liste': 'Kara liste', 'G10 Backlog Engeli': 'Backlog engeli', 'GB Backlog Engeli': 'Backlog engeli', 'Sayım': 'Sayım',
    'Test: Sadece A Segmenti': 'Test: sadece A',
    'BULK Oneri Kasa Kilosundan Kucuk - Gonderilmedi': 'Dökme: öneri bir kasadan az',
    'BULK MD Stok Yetersiz - Kasa Yok': 'Dökme: merkez stok yetersiz',
    'BULK Kismen Yuklendi (MD Stok Limiti)': 'Dökme: merkez stok sınırı',
    'Kapasite Yok (0)': 'Dolapta yer yok',
    'Dolap Kapasite Yetersizligi Sebebiyle Kisildi/Silindi': 'Dolap hacmi',
    'Bosa Cikan Hacimle Kismen Geri Yuklendi': 'Dolap hacmi',
}

def _ms_neden(s, kes):
    s = str(s or '')
    if 'Satır Limiti' in s or 'Satir Limiti' in s: return 'Merkez satır limiti'
    if s in _MS_NEDEN: return _MS_NEDEN[s]
    if kes <= 0 or s.startswith('Onaylandi'): return 'Dökme kasa yuvarlama' if kes > 0 else ''
    return s


def _ms_excel(G, sade):
    s1 = G['sheet1']
    if sade: s1 = s1[(s1['Effective quantity'] > 0) | (s1['Final_Quantity'] > 0)]
    s = [('Ana Cikti', [s1]), ('Kapasite Detayi', [G['sheet2']]), ('Merkez Stok Analizi', [G['sheet3']]), ('BULK Panel Cikti', [G['sheet4']])]
    if _dolu(G.get('sheet5')): s.append(('Sayim Kisiti', [G['sheet5']]))
    return s


def _ms_kontrol(G, log, df):
    K = Kontrol(); g1 = 'Kaynak eşleşmesi'
    dep = df.groupby('Depot_Match_Key')
    yok = dep['Doluluk_Tablosunda_Var_Mi'].first()
    K.liste(g1, 'Kapasite verisi olmayan depolar', sorted(a for a, v in yok.items() if not v), 'uyari',
            'Doluluk sheet’inde bulunamadı; bu depolarda dolap kısıtı uygulanmadı.')
    def urunler(m):
        u = df[m].groupby('Product_Code_Clean').agg(ad=('Product name', 'first'), d=('Depot_Match_Key', 'nunique')).reset_index()
        return u.values.tolist()
    hk = set(G['df_hacim']['Product_ID_Clean']); sk = set(G['df_storagetype']['Product_ID_Clean'])
    kk = set(G['kasa_kilo_df']['Product_ID_Clean'])
    oner = df['Effective quantity'] > 0
    K.liste(g1, 'Hacmi tanımsız ürünler', urunler(oner & ~df['Product_Code_Clean'].isin(hk)), 'uyari',
            'Ürün hacmi sheet’inde yok; birim hacim 1 L kabul edildi.', 'ürün', 'Hepsi tanımlı', ('Ürün kodu', 'Ürün', 'Depo sayısı'))
    K.liste(g1, 'Saklama tipi tanımsız ürünler', urunler(oner & ~df['Product_Code_Clean'].isin(sk)), 'bilgi',
            'Saklama tipi sheet’inde yok; +4 dolabına alındı.', 'ürün', 'Hepsi tanımlı', ('Ürün kodu', 'Ürün', 'Depo sayısı'))
    K.liste(g1, 'Kasa kilosu tanımsız dökme ürünler', urunler(df['Is_Bulk'] & oner & ~df['Product_Code_Clean'].isin(kk)), 'uyari',
            'Dökme kasa dosyasında yok; kasa kilosu yerine sipariş katı kullanıldı.', 'ürün', 'Hepsi tanımlı', ('Ürün kodu', 'Ürün', 'Depo sayısı'))
    depolar = set(df['Depot_Match_Key'])
    K.liste(g1, 'Kapasite oranı sheet’te olmayan depolar', sorted(depolar - set(G['df_oran']['Depot_Match_Key'])), 'bilgi',
            'Varsayılan MS oranı kullanıldı.')
    K.liste(g1, 'Buffer sheet’te olmayan depolar', sorted(depolar - set(G['df_buffer']['Depot_Match_Key'])), 'bilgi',
            f"Varsayılan buffer kullanıldı (%{_sf(G['PLUS_4_USABLE_RATIO']) * 100:g}).")
    n = int((df['Final_Quantity'] > 0).sum()); lim = int(G['MAX_ROWS'])
    K.ekle('Merkez depo', 'Satır limiti', 'uyari' if n > lim else 'ok', f'{n:,} / {lim:,} satır'.replace(',', '.'))
    K.gunluk(log)
    return K.K


def _ms_cikti(G, log):
    df = G['merged_df'].copy()
    eq = pd.to_numeric(df['Effective quantity'], errors='coerce').fillna(0)
    fq = pd.to_numeric(df['Final_Quantity'], errors='coerce').fillna(0)
    df['_kes'] = (eq - fq).clip(lower=0); df['_ekl'] = (fq - eq).clip(lower=0)
    df['_neden'] = [_ms_neden(n, k) for n, k in zip(df['Trim_Reason'], df['_kes'])]
    df['_ad'] = df['Product name'].fillna(df['Product code']).astype(str)
    df['_tur'] = np.where(df['Is_Bulk'], 'Dökme', np.where(df['Pick-to-zero'] == 1, 'PTZ', 'Normal'))
    df['_kasa'] = pd.to_numeric(df['BULK_Final_Kasa'], errors='coerce').fillna(0)
    df['_cover'] = df['Cover_Final_Qty_Day'].where(df['Cover_Final_Qty_Day'] < 99999)
    nb = ~df['Is_Bulk']
    O = float(eq[nb].sum()); Kk = float(df.loc[nb, '_kes'].sum())
    aktif = fq > 0
    kpi = [{'ad': 'Kesinti oranı (adet, dökme hariç)', 'deger': _pct(Kk, O), 'birim': '%', 'vurgu': True},
           {'ad': 'Kesilen', 'deger': Kk, 'birim': 'adet'},
           {'ad': 'Dökme gönderilen', 'deger': float(df['_kasa'].sum()), 'birim': 'kasa'},
           {'ad': 'Kesinti olan depo', 'deger': int(df.loc[df['_kes'] > 0, 'Depot_Match_Key'].nunique()), 'birim': f"/ {df['Depot_Match_Key'].nunique()}"},
           {'ad': 'Sevk hacmi', 'deger': float(pd.to_numeric(df['Final_Item_Volume'], errors='coerce').fillna(0).sum()), 'birim': 'L'}]
    merkez = [{'ad': 'Satır', 'deger': int(aktif.sum()), 'limit': float(G['MAX_ROWS']), 'birim': 'satır'}]
    sayimli = sorted(df.loc[df['Sayim_Kisiti'] == True, 'Depot_Match_Key'].dropna().unique().tolist())
    s2 = G['sheet2'].set_index(['Location name', 'Cabinet_Type'])
    def dol(c): return lambda a: s2.loc[(a, c), 'Son_Doluluk_Pct'] if (a, c) in s2.index else None
    kasa = df.groupby('Depot_Match_Key')['_kasa'].sum()
    dfn = df[nb]
    depo_tablo = depo_ozeti(dfn, 'Depot_Match_Key', 'Effective quantity', 'Final_Quantity', '_kes', '_neden', tip='Domain Type',
                            ekler=[('+4 doluluk %', dol('+4')), ('8-12 doluluk %', dol('8-12')), ('Dökme kasa', lambda a: kasa.get(a, 0))])
    # ---- ek kartlar: dökme, PTZ
    s3 = G['sheet3']; ek = []
    if _dolu(s3):
        b = s3[s3['Is_Bulk'] == True].copy()
        if len(b):
            topk = int(pd.to_numeric(b['Toplam Final Kasa'], errors='coerce').fillna(0).sum())
            kal = int(pd.to_numeric(b['Kalan Kasa'], errors='coerce').fillna(0).sum())
            ek.append({'baslik': 'Dökme ürünler', 'alt': 'Kasa kasa dağıtım: merkez stoğu kadar kasa, öneri sırasına ve cover’a göre depolara paylaştırılır; kısma sonrası açılan yere telafi kasası eklenir.',
                       'ozet': f'{len(b)} ürün · {topk:,} kasa gönderildi · merkezde {kal:,} kasa kaldı'.replace(',', '.'),
                       'tablo': _df_tablo(b.rename(columns={'Product name': 'Ürün', 'Gercek_Kasa_Kilo': 'Kasa kilo', 'End Balance DC': 'Merkez stok',
                                                            'Oneri Kasa': 'Merkezdeki kasa', 'RR Verilen Kasa': 'Dağıtılan kasa',
                                                            'Telafi Kasasi': 'Telafi kasası', 'Toplam Final Kasa': 'Gönderilen kasa',
                                                            'Kalan Kasa': 'Kalan kasa', 'Yollanan Depo Sayisi': 'Depo',
                                                            'Kalan Sebebi Dagilimi': 'Gönderilmeme nedeni'}),
                                          ['Ürün', 'Kasa kilo', 'Merkez stok', 'Merkezdeki kasa', 'Dağıtılan kasa', 'Telafi kasası', 'Gönderilen kasa',
                                           'Kalan kasa', 'Depo', 'Gönderilmeme nedeni']),
                       'vurgu': 'Kalan kasa'})
        p = s3[(s3['Pick-to-zero'] == True) & (s3['Is_Bulk'] != True)].copy()
        if len(p):
            pe = df[df['Pick-to-zero'] == 1].groupby('Product_Code_Clean')['PTZ_Eklenen_Adet'].sum()
            p['PTZ ile eklenen'] = p['Product code'].map(pe).fillna(0)
            mk = float(pd.to_numeric(p['Merkez Kalan'], errors='coerce').fillna(0).sum())
            ms_ = float(pd.to_numeric(p['End Balance DC'], errors='coerce').fillna(0).sum())
            ek.append({'baslik': 'Sıfıra çekilen (PTZ) ürünler', 'alt': 'Merkezde kalmaması gereken ürünler: öneri kesildiyse açık, cover’ı en düşük depodan başlayarak raf ömrünü aşmayacak kadar tamamlanır.',
                       'ozet': f'{len(p)} ürün · merkezde kalan %{_pct(mk, ms_):.1f}'.replace('.', ','),
                       'tablo': _df_tablo(p.rename(columns={'Product name': 'Ürün', 'End Balance DC': 'Merkez stok', 'Toplam EQ (Relex)': 'Relex önerisi',
                                                            'Toplam Final Qty': 'Gönderilen', 'Merkez Kalan': 'Merkezde kalan',
                                                            'Merkez Kalan %': 'Merkezde kalan %', 'Yollanan Depo Sayisi': 'Depo'}),
                                          ['Ürün', 'Merkez stok', 'Relex önerisi', 'Gönderilen', 'PTZ ile eklenen', 'Merkezde kalan', 'Merkezde kalan %', 'Depo']),
                       'vurgu': 'Merkezde kalan'})
    _fazla = _fazla_stok(df, 'Depot_Match_Key', 'Product_Code_Clean', '_ad', 'Effective quantity', 'adet; dökmede kg')
    _cab = df['Cabinet_Type'].astype(str)
    _buyuk = _buyuk_oneri(df, 'Depot_Match_Key', '_ad', df['Effective quantity'], df['Effective_Units'], df.get('Vol_Per_Unit'),
                          _cab.map({'+4': 'MS +4', '8-12': 'MS 8-12'}),
                          np.where(_cab == '+4', pd.to_numeric(df.get('Max_MS_Volume_+4'), errors='coerce'),
                                   np.where(_cab == '8-12', pd.to_numeric(df.get('Max_MS_Volume_8-12'), errors='coerce'), np.nan)),
                          'adet; dökmede kg (dökme adet kuralına girmez)', adet_haric=df['Is_Bulk'])
    _oneri = {'kartlar': [_buyuk['kart']] + _fazla['kartlar'], 'sayi': _fazla['sayi'] + _buyuk['sayi']}
    # ---- depo detayı
    adet = {_norm(k): v for k, v in (G.get('DEPO_ADET_LIMITI') or {}).items()}
    dg = df.groupby('Depot_Match_Key').agg(
        o=('Effective quantity', lambda s: float(s[~df.loc[s.index, 'Is_Bulk']].sum())),
        k=('_kes', lambda s: float(s[~df.loc[s.index, 'Is_Bulk']].sum())), kasa=('_kasa', 'sum'),
        v=('Final_Item_Volume', 'sum'), dt=('Domain Type', 'first'), tes=('Teslimat_Tarihi', 'first'), sayim=('Sayim_Bilgisi', 'first'),
        slot=('Slot_Ogle_Oncesi_Biten', 'first'),
        tr=('Trim_Reason', lambda s: '|'.join(sorted(set(s.astype(str))))), amb=('Cabinet_Type', lambda s: (s == 'Ambient').any()))
    s2r = G['sheet2']
    depolar = {}
    for a, r in dg.iterrows():
        defter, dolu = [], []
        for _, k in s2r[s2r['Location name'] == a].iterrows():
            cab = k['Cabinet_Type']
            defter.append({'bolum': f'{cab} dolabı, litre'})
            if k['Doluluk_Tablosunda_Var_Mi'] != True:
                defter.append({'ad': 'Kapasite verisi yok, kısıt uygulanmadı', 'deger': None}); continue
            kap = _sf(k['MS_Kapasite_Bufferli_Litre'])
            mt = kap * _sf(k['Initial_Doluluk_Pct']) / 100
            defter += [{'ad': 'Ham kapasite', 'deger': k['Max_Pool_Litre']},
                       {'ad': 'Kullanılabilir kapasite', 'not': f"× %{_sf(k['ms_oran']) * 100:g} MS oranı × %{_sf(k['buffer_rate']) * 100:g} buffer",
                        'deger': kap, 'sinif': 'd-ara'},
                       {'op': '−', 'ad': 'Mevcut + yoldaki', 'deger': mt},
                       {'op': '+', 'ad': 'Teslime kadar satılacak', 'not': 'ertesi gün eklenmedi (slot)' if k['Slot_Ogle_Oncesi_Biten'] else '',
                        'deger': k['Forecast_Freed_Litre']},
                       {'op': '=', 'ad': 'Teslim günü boş alan', 'deger': k['Allowed_Space_Litre'], 'sinif': 'd-ara'},
                       {'ad': 'Final hacim', 'not': f"öneri {_sf(k['Proposed_Total_Vol']):,.0f}".replace(',', '.'), 'deger': k['Final_Total_Vol'], 'sinif': 'd-sonuc'},
                       {'ad': 'Teslim sonrası doluluk', 'not': '%', 'deger': k['Son_Doluluk_Pct']}]
            dolu.append({'ad': cab, 'birim': 'L', 'doluAd': 'Teslim günü dolu', 'dolu': k['Initial_Dolu_Hacim_Litre'], 'fin': k['Final_Total_Vol'],
                         'kes': max(0, _sf(k['Proposed_Total_Vol']) - _sf(k['Final_Total_Vol'])), 'tavan': kap})
        if r['amb']: defter += [{'bolum': 'Ambient'}, {'ad': 'Ambient ürünler dolap kısıtına girmez', 'deger': None}]
        roz = [{'metin': r['dt']}]
        if not pd.isna(r['tes']): roz.append({'metin': 'Teslim ' + str(_t(r['tes']))})
        if 'Backlog Engeli' in r['tr']: roz.append({'metin': 'Backlog engeli', 'tur': 'kirmizi'})
        if 'Kara Liste' in r['tr']: roz.append({'metin': 'Kara liste', 'tur': 'kirmizi'})
        if r['slot']: roz.append({'metin': 'Slot 12:00’den önce bitiyor'})
        if r['sayim']: roz.append({'metin': 'Sayım: ' + str(r['sayim']), 'tur': 'kirmizi'})
        if _norm(a) in adet: roz.append({'metin': f"Adet limiti {adet[_norm(a)]}"})
        if _norm(a) in {_norm(x) for x in (G.get('SADECE_A_TEST_DEPOLARI') or [])}:
            roz.append({'metin': 'Test: sadece A · merkez limitleri uygulanmadı', 'tur': 'mor'})
        depolar[a] = {'rozetler': roz, 'defter': [{x: _t(v) for x, v in d.items()} for d in defter],
                      'doluluk': [{x: _t(v) for x, v in d.items()} for d in dolu],
                      'kpi': [['Kesinti oranı (adet)', _pct(r['k'], r['o']), '%', True], ['Kesilen', _t(r['k']), 'adet'],
                              ['Dökme', _t(r['kasa']), 'kasa'], ['Final hacim', _t(r['v']), 'L']]}
    kol = [('Depo', 'Depot_Match_Key'), ('Ürün', '_ad'), ('Dolap', 'Cabinet_Type'), ('Tür', '_tur'), ('Öneri', 'Effective quantity'),
           ('Final', 'Final_Quantity'), ('Kesilen', '_kes'), ('Eklenen', '_ekl'), ('Neden', '_neden'), ('Cover final', '_cover')]
    _ms_k = _ms_kontrol(G, log, df)
    return {'kpi': kpi,
            'ozet': {'nedenler': neden_ozeti(df, 'Depot_Match_Key', '_kes', '_neden'), 'neden_birim': 'adet; dökmede kg',
                     'merkez': merkez, 'sayimli': sayimli, 'ekKartlar': ek},
            'depo_tablo': depo_tablo, 'kontrol': _ms_k, 'oneri': _oneri,
            'detay': {**satir_detay(df, kol, (eq > 0) | (fq > 0)), 'depolar': depolar}}


URUNLER['ms'] = {
    'motor': 'MOTOR_MS',
    'ana': lambda G: G['sheet1'],
    'paramlar': ['CALISILAN_DEPO', 'CALISILAN_KATEGORI', 'MAX_ROWS', 'T1_FACTOR', 'PLUS_4_USABLE_RATIO',
                 'DEFAULT_SPOILING_TIME', 'MS4_DEFAULT_GB', 'MS4_DEFAULT_G10', 'MS812_DEFAULT',
                 'BLACKLISTED_DEPOTS', 'DEPO_ADET_LIMITI', 'SADECE_A_TEST_DEPOLARI'],
    'dosyalar': [('relex', 'ifade', 'relex_df'), ('backlog', 'ifade', 'backlog_df'), ('dokme', 'ifade', 'kasa_kilo_df')],
    'sheetler': [{'key': 'buffer', 'gid': 'BUFFER_GID', 'sid': 'SPREADSHEET_ID'}, {'key': 'oran', 'gid': 'ORAN_GID', 'sid': 'SPREADSHEET_ID'},
                 {'key': 'pooled', 'gid': 'POOLED_GID', 'sid': 'SPREADSHEET_ID'}, {'key': 'hacim', 'gid': 'HACIM_GID', 'sid': 'SPREADSHEET_ID'},
                 {'key': 'saklama', 'gid': 'STORAGETYPE_GID', 'sid': 'SPREADSHEET_ID'}, {'key': 'slot', 'gid': 'SLOT_GID', 'sid': 'SPREADSHEET_ID'},
                 {'key': 'sayim', 'gid': 'SAYIM_GID', 'sid': 'SAYIM_SPREADSHEET_ID'}],
    'imzalar': [('dokme', ['Kasa Kilo'], ['dokme', 'kasaici', 'kasa']),
                ('relex', ['Effective quantity', 'Location code', 'Product code'], ['relex']),
                ('backlog', ['backlog'], ['backlog'])],
    'excel': _ms_excel, 'cikti': _ms_cikti,
}


# ================================================================== MOTORLAR (motorlar/ klasöründen, değiştirilmeden)
_MOTOR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'motorlar')
def _motor_oku(ad):
    with open(os.path.join(_MOTOR_DIR, ad), encoding='utf-8') as f:
        return f.read()
MOTOR_AMB = _motor_oku('Ambient_Su.py')
MOTOR_COLD = _motor_oku('Cold.py')
MOTOR_MS = _motor_oku('MS.py')
