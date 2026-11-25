import re
import numpy as np
import pandas as pd
import datetime
# (hackathon) Çıktılar yerel klasöre yazılır, Drive'a kayıt yok.
# Update: SAYIM KISITI — teslimat günü depo sayımının yasak aralığına denk gelirse
#         o depoya hiçbir şey gitmez, kesinti nedeni 'Sayım'.

# ==========================================
# ⚙️ 0. KULLANICI PARAMETRELERİ (ÇALIŞTIRAN KİŞİ BURAYI SEÇECEK)
# ==========================================
CALISILAN_DEPO = "Adana"       # Çıktı dosyasının adı olacak (Örn: Ankara, İzmir vs.)
CALISILAN_KATEGORI = "MS"       # Bu kod MS olduğu için sabit kalabilir

# ==========================================
# 1. PARAMETRELER VE AYARLAR
# ==========================================
MAX_ROWS            = 10000
T1_FACTOR           = 1 / 3
PLUS_4_USABLE_RATIO = 1.1
BLACKLISTED_DEPOTS  = []
COVER_ESIK          = 6.0
DEFAULT_SPOILING_TIME = 5.0

MS4_DEFAULT_GB  = 0.15
MS4_DEFAULT_G10 = 0.19
MS812_DEFAULT   = 1.00

SPREADSHEET_ID  = '1FArHRLZdwrXcOHOHCK3skES7xGSPABNEm97jIK8H64E'
BUFFER_GID      = '1173976478'   # "Buffer Rates": Depo Adı | Ambient Buffer | Cold Limit → MS 'Cold Limit' kolonunu kullanır
ORAN_GID        = '2106866758'
HACIM_GID       = '1615488785'
STORAGETYPE_GID = '1098615637'
SLOT_GID        = '370075811'   # 🔀 Slot Saati verisi (Daily Capacity Data sekmesi)
POOLED_GID      = '108896607'   # 🔀 YENİ: pooled doluluk verisi (long format)

GSHEET_BASE       = f'https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid='
GSHEET_BUFFER_URL = GSHEET_BASE + BUFFER_GID
GSHEET_ORAN_URL   = GSHEET_BASE + ORAN_GID
GSHEET_HACIM_URL  = GSHEET_BASE + HACIM_GID
GSHEET_ST_URL     = GSHEET_BASE + STORAGETYPE_GID
GSHEET_SLOT_URL   = GSHEET_BASE + SLOT_GID
GSHEET_POOLED_URL = GSHEET_BASE + POOLED_GID   # 🔀 YENİ

# 📋 SAYIM PLANI SHEET'İ (Tarih, Tarih Açıklama, Depo Kodu, Depo Tipi, Sayım Türü ...)
SAYIM_SPREADSHEET_ID = 'https://docs.google.com/spreadsheets/d/1FArHRLZdwrXcOHOHCK3skES7xGSPABNEm97jIK8H64E/edit?gid=1468314948#gid=1468314948'   # <-- Sayım planı spreadsheet ID'si (linkteki /d/ ile /edit arası)
SAYIM_GID            = '1468314948'   # <-- Sayım sekmesinin GID'i

# ==========================================
# 📋 SAYIM KURALLARI (MS / FV) — teslimat ALINMAYACAK gün aralığı
#    T = sayım tarihi, aralığın iki ucu da dahil. Örn (-2, -1) → T-2, T-1
# ==========================================
_TR_MAP = str.maketrans('ıİşŞğĞüÜöÖçÇ', 'iissgguuoocc')

def _norm_ad(s):
    return re.sub(r'[^a-z0-9]', '', str(s).translate(_TR_MAP).lower())

_SAYIM_GECELER = [
    'Pazarı Pazartesiye Bağlayan Gece', 'Pazartesiyi Salıya Bağlayan Gece',
    'Salıyı Çarşambaya Bağlayan Gece', 'Çarşambayı Perşembeye Bağlayan Gece',
    'Perşembeyi Cumaya Bağlayan Gece', 'Cumayı Cumartesiye Bağlayan Gece',
    'Cumartesiyi Pazara Bağlayan Gece',
]

def _gunduz(*gunler):
    return [f'{g} {s}' for g in gunler for s in ('Sabah', 'Gün İçinde', 'Akşam')]

_TUM_GUNDUZ = _gunduz('Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar')

SAYIM_KURALLARI = {
    ('GB', 'Rutin'): [
        (_SAYIM_GECELER[:1], (-2, -1)),                                        # Pazar→Pzt gecesi
        (_SAYIM_GECELER[1:], (-1, -1)),                                        # diğer geceler
        (_gunduz('Pazar', 'Pazartesi'), (-1, 0)),
        (_gunduz('Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi'), (0, 0)),
    ],
    ('G10', 'Rutin'): [
        (_SAYIM_GECELER, (-1, -1)),
        (_TUM_GUNDUZ, (0, 0)),
    ],
    ('GB', 'Devir'): [
        (_SAYIM_GECELER, (-4, -1)),
        (_TUM_GUNDUZ, (-3, 0)),
    ],
    ('G10', 'Devir'): [
        (_SAYIM_GECELER, (-4, -1)),
        (_TUM_GUNDUZ, (-3, 0)),
    ],
}

_SAYIM_ARALIK = {}   # (depo tipi, sayım türü, açıklama) -> (baş, bitiş)
for (_tip, _tur), _gruplar in SAYIM_KURALLARI.items():
    for _aciklamalar, _aralik in _gruplar:
        for _a in _aciklamalar:
            _SAYIM_ARALIK[(_tip, _tur, _norm_ad(_a))] = _aralik

SAYIM_REASON = 'Sayım'

# 📦 DEPO BAZLI MAKSİMUM TOPLAM SİPARİŞ ADEDİ (tüm ürünlerin toplamı bu sayıyı geçemez)
#    Depo adı Türkçe karakter / boşluk duyarsız eşleşir.
DEPO_ADET_LIMITI = {
    'Acıbadem Büyük': 915,
}

# 🧪 SADECE A TESTİ (20.11.2026) — bu depolara yalnız ABC class 'A' ürünler gider; B/C/D (ve sınıfı boş) en baştan sıfır,
#    dökme kasa / PTZ / telafi dağıtımlarına da girmez. Yalnız dolap hacmi kesim yapar: merkez satır limiti ve depo adet
#    limiti bu depoların satırlarını kesmez (satırlar merkez sayımına dahil). Sayım ve backlog engeli geçerli.
#    Depo adı Türkçe karakter / boşluk duyarsız eşleşir.
SADECE_A_TEST_DEPOLARI = ['Atakent']
SADECE_A_REASON = 'Test: Sadece A Segmenti'


# ==========================================
# 2. DOSYALARIN OKUNMASI
# ==========================================
print("🔄 Dosyalar yükleniyor...")

def read_gsheet_csv(url):
    d = pd.read_csv(url)
    d.columns = [str(c).strip() for c in d.columns]
    return d

def clean_locale_number(val):
    if pd.isna(val): return 0.0
    if isinstance(val, (int, float)): return float(val)
    val = str(val).strip().replace('.', '').replace(',', '.')
    try: return float(val)
    except: return 0.0

def norm_col(s):
    return str(s).lower().replace(' ', '').replace("'", '').rstrip()

relex_df     = pd.read_excel('/content/adana ms 1609 relex.xlsx')
backlog_df   = pd.read_excel('/content/adana ms backlog.xlsx')
kasa_kilo_df = pd.read_excel('/content/adana dökme kasaiçi 1609.xlsx')

print("📊 GSheet'ten veriler çekiliyor...")
df_buffer_raw      = read_gsheet_csv(GSHEET_BUFFER_URL)
df_oran_raw        = read_gsheet_csv(GSHEET_ORAN_URL)
df_hacim_raw       = read_gsheet_csv(GSHEET_HACIM_URL)
df_storagetype_raw = read_gsheet_csv(GSHEET_ST_URL)
df_slot_raw        = read_gsheet_csv(GSHEET_SLOT_URL)

# --- BUFFER RATE ---
depo_col   = next((c for c in df_buffer_raw.columns if 'depo' in c.lower()), df_buffer_raw.columns[0])
def buffer_sayi(x):
    """Buffer hücresi → oran: '110%' / '1.10' / '1,1' / 1.1 → 1.10; boş, 0 ya da okunamayan → NaN."""
    if isinstance(x, (int, float)) and not pd.isna(x):
        v = float(x)
    else:
        t = str(x).strip().replace(' ', '')
        if t in ('', '-', 'nan', 'None'): return np.nan
        yuzde = t.endswith('%')
        try: v = float(t.rstrip('%').replace(',', '.'))
        except ValueError: return np.nan
        if yuzde: v = v / 100
    if v > 5: v = v / 100
    return v if v > 0 else np.nan

buffer_col = next((c for c in df_buffer_raw.columns if 'cold' in c.lower() or '+4' in c), None)   # 'Cold Limit' (18.11'e kadar adı '+4 ...' idi)
if buffer_col is None:
    raise ValueError(f"Buffer Rates sekmesinde 'Cold Limit' kolonu yok. Kolonlar: {df_buffer_raw.columns.tolist()}")
df_buffer  = df_buffer_raw[[depo_col, buffer_col]].copy()
df_buffer.rename(columns={depo_col: 'Depot_Match_Key', buffer_col: 'buffer_rate'}, inplace=True)
df_buffer['Depot_Match_Key'] = df_buffer['Depot_Match_Key'].astype(str).str.strip()
df_buffer['buffer_rate'] = df_buffer['buffer_rate'].map(buffer_sayi)
df_buffer = df_buffer.dropna(subset=['buffer_rate'])
_buf_cakisan = df_buffer.groupby('Depot_Match_Key')['buffer_rate'].nunique()
if (_buf_cakisan > 1).any():
    print(f"   ⚠️  Buffer Rates'te farklı değerle tekrarlanan depolar (ilki alındı): {_buf_cakisan[_buf_cakisan > 1].index.tolist()}")
df_buffer = df_buffer.drop_duplicates(subset=['Depot_Match_Key'])
print(f"📐 +4 buffer (Buffer Rates → '{buffer_col}'): {len(df_buffer)} depo · sheet'te olmayan depolara %{PLUS_4_USABLE_RATIO * 100:g}")

# --- KAPASİTE ORANLARI ---
df_oran = df_oran_raw.rename(columns={df_oran_raw.columns[0]: 'Depot_Match_Key'}).copy()
print(f"  Oran GSheet kolonları: {df_oran.columns.tolist()}")

oran_cols_norm = {c.strip().lower(): c for c in df_oran.columns}
ms4_col   = oran_cols_norm.get('ms+4')
ms812_col = oran_cols_norm.get('ms+8+12')

if ms4_col is None:
    ms4_col = next((c for c in df_oran.columns
                    if 'ms' in c.lower() and '4' in c and '8' not in c and '12' not in c), None)
if ms812_col is None:
    ms812_col = next((c for c in df_oran.columns
                      if '8' in c and '12' in c and c != 'Depot_Match_Key'), None)

if ms4_col is None:
    print("⚠️  MS+4 oran kolonu bulunamadı → domain bazlı varsayılan")
else:
    print(f"  ✅ MS+4 kolonu: '{ms4_col}'")
if ms812_col is None:
    print("⚠️  MS+8+12 oran kolonu bulunamadı → varsayılan 1.0")
else:
    print(f"  ✅ MS+8+12 kolonu: '{ms812_col}'")

df_oran['ms4_oran']   = df_oran[ms4_col].apply(clean_locale_number)   if ms4_col   else np.nan
df_oran['ms812_oran'] = df_oran[ms812_col].apply(clean_locale_number) if ms812_col else np.nan
df_oran.loc[df_oran['ms4_oran']   == 0, 'ms4_oran']   = np.nan
df_oran.loc[df_oran['ms812_oran'] == 0, 'ms812_oran'] = np.nan
df_oran = df_oran[['Depot_Match_Key', 'ms4_oran', 'ms812_oran']].drop_duplicates(subset=['Depot_Match_Key'])

# --- HACİM ---
df_hacim = df_hacim_raw.copy()
if str(df_hacim.iloc[0, 0]).lower().strip() in ['product id', 'marketproduct_id']:
    df_hacim = df_hacim.iloc[1:].reset_index(drop=True)

hacim_id_col  = next((c for c in df_hacim.columns if 'product' in c.lower() and 'id' in c.lower()), df_hacim.columns[0])
hacim_val_col = next((c for c in df_hacim.columns if 'hacim' in c.lower()), df_hacim.columns[2])

df_hacim = df_hacim[[hacim_id_col, hacim_val_col]].copy()
df_hacim.rename(columns={hacim_id_col: 'Product_ID_Clean', hacim_val_col: 'hacim2'}, inplace=True)
df_hacim['Product_ID_Clean'] = df_hacim['Product_ID_Clean'].astype(str).str.strip().str.lower()
df_hacim['hacim2']           = pd.to_numeric(df_hacim['hacim2'], errors='coerce').fillna(0)
df_hacim = df_hacim[df_hacim['Product_ID_Clean'].str.len() > 5]
df_hacim = df_hacim.drop_duplicates(subset=['Product_ID_Clean'], keep='first')
print(f"  ✅ Hacim: {len(df_hacim)} ürün")

# --- STORAGE TYPE ---
st_id_col  = next((c for c in df_storagetype_raw.columns if 'product' in c.lower() and 'id' in c.lower()), None)
st_val_col = next((c for c in df_storagetype_raw.columns if 'storage' in c.lower()), None)

if st_id_col is None:
    raise ValueError(f"Storage type GSheet'inde Product ID kolonu bulunamadı: {df_storagetype_raw.columns.tolist()}")
if st_val_col is None:
    raise ValueError(f"Storage type GSheet'inde Storage Type kolonu bulunamadı: {df_storagetype_raw.columns.tolist()}")

df_storagetype = df_storagetype_raw[[st_id_col, st_val_col]].copy()
df_storagetype.rename(columns={st_id_col: 'Product_ID_Clean', st_val_col: 'storagetype'}, inplace=True)
df_storagetype['Product_ID_Clean'] = df_storagetype['Product_ID_Clean'].astype(str).str.strip().str.lower()
df_storagetype['storagetype']      = df_storagetype['storagetype'].astype(str).str.strip()
df_storagetype = df_storagetype[df_storagetype['Product_ID_Clean'].str.len() > 5]
df_storagetype = df_storagetype.drop_duplicates(subset=['Product_ID_Clean'], keep='first')
print(f"  ✅ Storage type: {len(df_storagetype)} ürün")

df_urun = pd.merge(df_hacim, df_storagetype, on='Product_ID_Clean', how='left')
df_urun['storagetype'] = df_urun['storagetype'].fillna('+4')

# --- SLOT SAATİ (öğlen 12:00 ve öncesi biten Frigo/Çift Rejim slotları) ---
SLOT_COL_DURUM = 'Durum'
SLOT_COL_ID    = 'Depo ID'
SLOT_COL_BAYI  = 'Bayi Adı'
SLOT_COL_TUR   = 'Tür'
SLOT_COL_BITIS = 'Slot Saati Bitiş'

def parse_slot_saat_dk(val):
    if pd.isna(val):
        return np.nan
    s = str(val).strip()
    m = re.match(r'^(\d{1,2}):(\d{2})(?::\d{2})?$', s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    t = pd.to_datetime(s, errors='coerce')
    return np.nan if pd.isna(t) else t.hour * 60 + t.minute

df_slot = df_slot_raw.copy()
df_slot.columns = [str(c).strip() for c in df_slot.columns]

_slot_eksik = [c for c in [SLOT_COL_ID, SLOT_COL_TUR, SLOT_COL_BITIS] if c not in df_slot.columns]
if _slot_eksik:
    raise ValueError(f"Slot GSheet'inde beklenen kolonlar yok: {_slot_eksik}")

# Sadece aktif slotlar
if SLOT_COL_DURUM in df_slot.columns:
    _slot_onceki = len(df_slot)
    df_slot = df_slot[df_slot[SLOT_COL_DURUM].astype(str).str.strip().str.lower() == 'aktif'].copy()
    print(f"  Slot: {len(df_slot)}/{_slot_onceki} satır 'Aktif'")

df_slot['Slot_Depo_ID'] = df_slot[SLOT_COL_ID].astype(str).str.strip().str.lower()
df_slot['Tur_Norm']     = df_slot[SLOT_COL_TUR].astype(str).str.strip().str.lower()
df_slot['Bitis_Dk']     = df_slot[SLOT_COL_BITIS].apply(parse_slot_saat_dk)

# 🔀 Sadece Frigo / Çift Rejim satırları — Ambient hariç
slot_frigo = df_slot[df_slot['Tur_Norm'].isin(['frigo', 'çift rejim', 'cift rejim'])].copy()
print(f"  Slot: {len(slot_frigo)} Frigo/Çift Rejim satırı (tür dağılımı: {df_slot['Tur_Norm'].value_counts().to_dict()})")

_slot_parse_fail = int(slot_frigo['Bitis_Dk'].isna().sum())
if _slot_parse_fail:
    print(f"  ⚠️  {_slot_parse_fail} Frigo/Çift Rejim satırında bitiş saati parse EDİLEMEDİ "
          f"→ bu depolar 1/3 düşüşünü ALMAYA DEVAM edecek!")

slot_depo_bitis = (
    slot_frigo.dropna(subset=['Bitis_Dk'])
    .groupby('Slot_Depo_ID')['Bitis_Dk'].min()
)

depo_ogle_oncesi_ids = set(
    slot_depo_bitis[(slot_depo_bitis > 0) & (slot_depo_bitis <= 720)].index
)
print(f"  ✅ Slot Saati: {len(slot_depo_bitis)} depo parse edildi, bunlardan "
      f"{len(depo_ogle_oncesi_ids)} tanesi öğlen 12:00 ve öncesi bitiyor "
      f"→ +4 için 1/3 forecast düşüşü uygulanmayacak")

slot_id_ad = {}
if SLOT_COL_BAYI in slot_frigo.columns:
    slot_id_ad = (slot_frigo.drop_duplicates('Slot_Depo_ID')
                  .set_index('Slot_Depo_ID')[SLOT_COL_BAYI]
                  .astype(str).str.strip().to_dict())

# ==========================================
# 🔀 POOLED DOLULUK VERİSİ — ARTIK GSHEET'TEN (long format → pivot)
# ==========================================
pooled_keep = [
    'Depo: Depo Adı',
    'All MS +4 Volume Litre',
    'All MS +4 In Transit Volume Litre',
    'All MS +4 Volume Litre (frc t)',
    'All MS +4 Volume Litre (frc t+1)',
    'All MS +4 Volume Litre (frc t+2)',
    'MS +8-12 Volume Litre',
    'MS +8-12 In Transit Volume Litre',
    'MS +8-12 Volume Litre (frc t)',
    'MS +8-12 Volume Litre (frc t+1)',
    'MS +8-12 Volume Litre (frc t+2)',
    'Max. Other +4 & MS +4 WH Volume',
    'Max. MS +8-12 WH Volume',
]

def parse_pooled_number(val):
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(' ', '').replace('\u00a0', '').replace('%', '')
    if s == '' or s.lower() in ['nan', 'null', 'none', '-', 'total', 'toplam']:
        return np.nan
    s = s.replace(',', '')            # binlik ayracı
    try:
        return float(s)
    except Exception:
        return np.nan

print("📊 Pooled doluluk verisi GSheet'ten çekiliyor...")
pooled_long = read_gsheet_csv(GSHEET_POOLED_URL)

_pc      = {c: c.lower() for c in pooled_long.columns}
c_depo   = next((c for c in pooled_long.columns if 'depo' in _pc[c]), None)
c_mname  = next((c for c in pooled_long.columns if 'measure' in _pc[c] and 'name' in _pc[c]), None)
c_mval   = next((c for c in pooled_long.columns if 'measure' in _pc[c] and 'val'  in _pc[c]), None)
c_date   = next((c for c in pooled_long.columns if _pc[c].strip() in ('x', 'date', 'tarih')), None)
c_sttype = next((c for c in pooled_long.columns if 'storagetype' in _pc[c].replace(' ', '')), None)

if c_depo is None or c_mname is None or c_mval is None:
    raise ValueError(f"Pooled GSheet'te Depo / Measure Names / Measure Values kolonları bulunamadı.")

# --- Sadece en güncel snapshot ---
if c_date is not None:
    pooled_long['_ts'] = pd.to_datetime(pooled_long[c_date], errors='coerce')
    if pooled_long['_ts'].notna().any():
        son_ts  = pooled_long['_ts'].max()
        son_gun = son_ts.normalize()
        pooled_long = pooled_long[pooled_long['_ts'].dt.normalize() == son_gun].copy()

pooled_long['_depo']  = pooled_long[c_depo].astype(str).str.strip()
pooled_long['_mname'] = pooled_long[c_mname].astype(str).str.strip()
pooled_long['_mval']  = pooled_long[c_mval].apply(parse_pooled_number)

# --- PIVOT: long → wide ---
pooled_wide = (
    pooled_long
    .dropna(subset=['_mname'])
    .pivot_table(index='_depo', columns='_mname', values='_mval', aggfunc='first')
    .reset_index()
    .rename(columns={'_depo': 'Depot_Match_Key'})
)
pooled_wide.columns.name = None

# --- Hedef kolon adlarına normalize eşleştirme ---
_wide_norm = {norm_col(c): c for c in pooled_wide.columns if c != 'Depot_Match_Key'}
pooled_sel = pd.DataFrame({'Depot_Match_Key': pooled_wide['Depot_Match_Key']})

for hedef in [k for k in pooled_keep if k != 'Depo: Depo Adı']:
    kaynak = _wide_norm.get(norm_col(hedef))
    if kaynak is None:
        pooled_sel[hedef] = 0.0
    else:
        pooled_sel[hedef] = pd.to_numeric(pooled_wide[kaynak], errors='coerce').fillna(0.0)

pooled_sel = pooled_sel.drop_duplicates(subset=['Depot_Match_Key'])

# --- RELEX VE DİĞER DOSYALAR ---
for df_temp in [relex_df, backlog_df, kasa_kilo_df]:
    df_temp.columns = df_temp.columns.str.strip().str.replace(r'\s+', ' ', regex=True)

relex_df['Domain Type'] = (
    relex_df['Domain Type'].astype(str).str.strip()
    .replace({'': 'GB', 'nan': 'GB', 'None': 'GB', 'NaN': 'GB'})
)

relex_df['Depot_Match_Key']    = relex_df['Location name'].astype(str).str.strip()
relex_df['Product_Code_Clean'] = relex_df['Product code'].astype(str).str.strip().str.lower()

# 🔀 REFERENCE SPOILING TIME (raf ömrü, gün)
spoiling_col = next((c for c in relex_df.columns if 'spoiling' in c.lower()), None)
if spoiling_col is None:
    relex_df['Reference_Spoiling_Time'] = DEFAULT_SPOILING_TIME
else:
    relex_df['Reference_Spoiling_Time'] = pd.to_numeric(relex_df[spoiling_col], errors='coerce')
    relex_df['Reference_Spoiling_Time'] = relex_df['Reference_Spoiling_Time'].fillna(DEFAULT_SPOILING_TIME)

backlog_loc_col = next(
    (c for c in backlog_df.columns if c in ['Location name', 'Location', 'Depo Adi', 'Depo']),
    backlog_df.columns[0]
)
backlog_val_col = (
    next((c for c in backlog_df.columns if 'backlog' in c.lower()), None) or
    next((c for c in backlog_df.columns if any(x in c.lower() for x in ['palet', 'kalan'])),
         backlog_df.columns[1] if len(backlog_df.columns) > 1 else backlog_df.columns[0])
)
backlog_df['Depot_Match_Key'] = backlog_df[backlog_loc_col].astype(str).str.strip()
backlog_df = backlog_df.drop_duplicates(subset=['Depot_Match_Key'], keep='first')

relex_df['Daily FC']             = pd.to_numeric(relex_df['Daily FC'],             errors='coerce').fillna(0)
relex_df['End balance']          = pd.to_numeric(relex_df['End balance'],          errors='coerce').fillna(0)
relex_df['End Balance DC']       = pd.to_numeric(relex_df['End Balance DC'],       errors='coerce').fillna(0)
relex_df['Open purchase orders'] = pd.to_numeric(relex_df['Open purchase orders'], errors='coerce').fillna(0)
relex_df['Effective quantity']   = pd.to_numeric(relex_df['Effective quantity'],   errors='coerce').fillna(0)
relex_df['Pick-to-zero']         = pd.to_numeric(relex_df['Pick-to-zero'],         errors='coerce').fillna(0).astype(int)
relex_df['Order batch size']     = pd.to_numeric(relex_df['Order batch size'],     errors='coerce').fillna(1).clip(lower=1).astype(int)
# Relex '14 Days Sales' (son 14 günlük satış): Ana Cikti'ya taşınır, arayüzdeki büyük öneri uyarısı kullanır. Kesime girmez.
_c14 = next((c for c in relex_df.columns if ' '.join(str(c).lower().split()) == '14 days sales'), None)
if _c14 is not None:
    relex_df = relex_df.rename(columns={_c14: '14 Days Sales'})
    relex_df['14 Days Sales'] = pd.to_numeric(relex_df['14 Days Sales'], errors='coerce')

# BİRLEŞTİRME
merged_df = pd.merge(relex_df,
    df_urun[['Product_ID_Clean', 'hacim2', 'storagetype']],
    left_on='Product_Code_Clean', right_on='Product_ID_Clean', how='left')
merged_df = pd.merge(merged_df, backlog_df[['Depot_Match_Key', backlog_val_col]], on='Depot_Match_Key', how='left')
merged_df.rename(columns={backlog_val_col: 'Backlog'}, inplace=True)
merged_df = pd.merge(merged_df, pooled_sel, on='Depot_Match_Key', how='left')
merged_df = pd.merge(merged_df, df_buffer,  on='Depot_Match_Key', how='left')
merged_df = pd.merge(merged_df, df_oran,    on='Depot_Match_Key', how='left')

merged_df['hacim2_prod']      = pd.to_numeric(merged_df['hacim2'],          errors='coerce').fillna(0)

hacim_sifir_mask = merged_df['hacim2_prod'] == 0
if hacim_sifir_mask.any():
    merged_df.loc[hacim_sifir_mask, 'hacim2_prod'] = 1.0

merged_df['Backlog']          = pd.to_numeric(merged_df['Backlog'],          errors='coerce').fillna(0)
merged_df['Order batch size'] = pd.to_numeric(merged_df['Order batch size'], errors='coerce').fillna(1).clip(lower=1).astype(int)
merged_df['Domain Type']      = merged_df['Domain Type'].astype(str).str.strip().replace({'': 'GB', 'nan': 'GB', 'None': 'GB', 'NaN': 'GB'})
merged_df['buffer_rate']      = pd.to_numeric(merged_df['buffer_rate'], errors='coerce').fillna(PLUS_4_USABLE_RATIO)
merged_df['storagetype']      = merged_df['storagetype'].fillna('+4')

merged_df['ms4_oran']   = pd.to_numeric(merged_df['ms4_oran'],   errors='coerce')
merged_df['ms812_oran'] = pd.to_numeric(merged_df['ms812_oran'], errors='coerce')
ms4_eksik = merged_df['ms4_oran'].isna()
merged_df.loc[ms4_eksik & (merged_df['Domain Type'] == 'G10'), 'ms4_oran'] = MS4_DEFAULT_G10
merged_df.loc[ms4_eksik & (merged_df['Domain Type'] != 'G10'), 'ms4_oran'] = MS4_DEFAULT_GB
merged_df['ms812_oran'] = merged_df['ms812_oran'].fillna(MS812_DEFAULT)

for col in [c for c in pooled_sel.columns if c != 'Depot_Match_Key']:
    if col in merged_df.columns:
        merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce').fillna(0)

merged_df['Doluluk_Tablosunda_Var_Mi'] = (
    (merged_df['Max. Other +4 & MS +4 WH Volume'] > 0) |
    (merged_df['Max. MS +8-12 WH Volume'] > 0)
)

merged_df['Sistem'] = 'Yeni Sistem'   # kolon raporlar için korunuyor; eski sistem 19.11.2026'da kaldırıldı

# 🔀 Slot Saati bayrağı
merged_df['Location_Code_Clean']    = merged_df['Location code'].astype(str).str.strip().str.lower()
merged_df['Slot_Ogle_Oncesi_Biten'] = merged_df['Location_Code_Clean'].isin(depo_ogle_oncesi_ids)

# ==========================================
# 3. CABINET TYPE, TRIM_EXEMPT, BULK FLAG
# ==========================================
merged_df['Is_Bulk'] = (
    merged_df['Transfer type'].astype(str).str.strip().str.upper() == 'BULK'
)

kasa_kilo_df['Product_ID_Clean'] = kasa_kilo_df['Product id'].astype(str).str.strip().str.lower()
kasa_kilo_df = kasa_kilo_df.drop_duplicates(subset=['Product_ID_Clean'], keep='first')
merged_df = pd.merge(
    merged_df,
    kasa_kilo_df[['Product_ID_Clean', 'Kasa Kilo']].rename(columns={'Kasa Kilo': 'Gercek_Kasa_Kilo'}),
    on='Product_ID_Clean', how='left'
)
merged_df['Gercek_Kasa_Kilo'] = (
    pd.to_numeric(merged_df['Gercek_Kasa_Kilo'], errors='coerce')
    .apply(lambda x: float(round(x)) if not pd.isna(x) else 0.0)
)

fallback_mask = merged_df['Is_Bulk'] & (merged_df['Gercek_Kasa_Kilo'] <= 0)
if fallback_mask.any():
    fallback_batch = pd.to_numeric(
        merged_df.loc[fallback_mask, 'Order batch size'], errors='coerce'
    ).fillna(1).clip(lower=1)
    merged_df.loc[fallback_mask, 'Gercek_Kasa_Kilo'] = fallback_batch

merged_df['Cabinet_Type'] = merged_df['storagetype'].astype(str).str.strip().apply(
    lambda x: '8-12' if '8-12' in x else '+4'
)
ambient_mask = merged_df['storagetype'].astype(str).str.strip().str.lower().str.contains('ambient', na=False)
merged_df.loc[ambient_mask, 'Cabinet_Type'] = 'Ambient'

merged_df['Trim_Exempt'] = ambient_mask
merged_df['Is_GB_Depot'] = merged_df['Domain Type'].astype(str).str.upper().str.strip() == 'GB'

merged_df['Cover_Day_Calc'] = np.where(
    merged_df['Daily FC'] > 0,
    (merged_df['End balance'] + merged_df['Open purchase orders']) / merged_df['Daily FC'],
    999999
)
merged_df['Trim_Reason']         = 'Onaylandi (Kisma Yapilmadi)'

# 🧪 Sadece A testi işaretleri (uygulama _sayim_kisiti_uygula içinde, her çağrıda yeniden)
merged_df['Sadece_A_Test'] = merged_df['Location name'].map(_norm_ad).isin({_norm_ad(x) for x in SADECE_A_TEST_DEPOLARI})
merged_df['Sadece_A_Iptal'] = merged_df['Sadece_A_Test'] & (merged_df['ABC class'].astype(str).str.upper().str.strip() != 'A')
if merged_df['Sadece_A_Test'].any():
    print(f"🧪 Sadece A testi: {sorted(merged_df.loc[merged_df['Sadece_A_Test'], 'Location name'].unique())} → "
          f"{int(merged_df['Sadece_A_Iptal'].sum())} A dışı satır sıfırlanacak, "
          f"{int((merged_df['Sadece_A_Test'] & ~merged_df['Sadece_A_Iptal']).sum())} satır değerlendirmede")
merged_df['PTZ_Eklenen_Adet']    = 0
merged_df['BULK_Telafi_Kasa']    = 0
merged_df['BULK_Sifirlama_Kilo'] = 0.0

# ==========================================
# 3.4. 📋 SAYIM KISITI — teslimat günü sayım yasağına denk gelen depoya hiçbir şey gitmez
#      Dökme kasa dağıtımından ÖNCE işaretlenir ki o depoya kasa ayrılmasın.
# ==========================================
bugun = pd.Timestamp.now().normalize()
SAYIM_KAYITLARI = {}   # depo kodu -> [sayım kayıtları]
df_sayim = pd.DataFrame()
if not (SAYIM_SPREADSHEET_ID and SAYIM_GID):
    print("🚨 SAYIM PLANI LİNKİ GİRİLMEMİŞ → sayım kısıtı UYGULANMAYACAK!")
else:
    try:
        df_sayim = read_gsheet_csv(
            f'https://docs.google.com/spreadsheets/d/{SAYIM_SPREADSHEET_ID}/export?format=csv&gid={SAYIM_GID}'
        ).fillna('')
    except Exception as _e:
        print(f"🚨 SAYIM PLANI OKUNAMADI → sayım kısıtı UYGULANMAYACAK! Hata: {_e}")

if not df_sayim.empty:
    def _sayim_kolon(ad):
        return next((c for c in df_sayim.columns if _norm_ad(c) == _norm_ad(ad)), None)
    _sk = {k: _sayim_kolon(k) for k in ['Tarih', 'Tarih Açıklama', 'Depo Kodu', 'Depo Adı',
                                        'Depo Tipi', 'Sayım Türü', 'Genel Sayım Statu']}
    _sk_eksik = [k for k in ['Tarih', 'Tarih Açıklama', 'Depo Kodu', 'Depo Tipi', 'Sayım Türü'] if _sk[k] is None]
    if _sk_eksik:
        print(f"🚨 Sayım planında kolon bulunamadı: {_sk_eksik} → sayım kısıtı UYGULANMAYACAK! "
              f"(Sheet linkle paylaşılmamış olabilir) Kolonlar: {df_sayim.columns.tolist()[:10]}")
    else:
        # Sheet'te depo tipi boşsa Relex'teki depo tipine düşülür
        _relex_tip = (merged_df.drop_duplicates('Location_Code_Clean')
                      .set_index('Location_Code_Clean')['Domain Type'].to_dict())
        _tanimsiz = []
        for _, _r in df_sayim.iterrows():
            _kod = str(_r[_sk['Depo Kodu']]).lower().strip()
            if not _kod: continue
            if _sk['Genel Sayım Statu'] and 'iptal' in _norm_ad(_r[_sk['Genel Sayım Statu']]): continue
            _acik = str(_r[_sk['Tarih Açıklama']]).strip()
            _ad = str(_r[_sk['Depo Adı']]).strip() if _sk['Depo Adı'] else _kod
            _T = pd.to_datetime(str(_r[_sk['Tarih']]).strip(), dayfirst=True, errors='coerce')
            _tip = str(_r[_sk['Depo Tipi']]).strip().upper() or str(_relex_tip.get(_kod, '')).strip().upper()
            _tur_n = _norm_ad(_r[_sk['Sayım Türü']])
            _tur = 'Devir' if 'devir' in _tur_n else ('Rutin' if 'rutin' in _tur_n else str(_r[_sk['Sayım Türü']]))
            _aralik = _SAYIM_ARALIK.get((_tip, _tur, _norm_ad(_acik)))
            if pd.isna(_T) or _aralik is None:
                _tanimsiz.append(f"{_ad} | {_r[_sk['Tarih']]} | {_acik} | {_tip} | {_tur}")
                continue
            SAYIM_KAYITLARI.setdefault(_kod, []).append({
                'T': _T.normalize(), 'bas': _aralik[0], 'bit': _aralik[1],
                'aciklama': _acik, 'tur': _tur, 'tip': _tip})
        print(f"📋 Sayım planı: {sum(len(v) for v in SAYIM_KAYITLARI.values())} sayım / "
              f"{len(SAYIM_KAYITLARI)} depo okundu")
        if _tanimsiz:
            print(f"   ⚠️  Kurala eşlenemeyen {len(_tanimsiz)} sayım satırı ATLANDI "
                  f"(tarih/açıklama/tip/tür tanınmadı):")
            for _t in _tanimsiz[:15]: print(f"      - {_t}")

# Teslimat tarihi: Relex 'Delivery date' (depo bazında en erken)
if 'Delivery date' not in merged_df.columns:
    print("🚨 Relex'te 'Delivery date' kolonu yok → sayım kısıtı kontrol EDİLEMEZ!")
    merged_df['Delivery date'] = pd.NaT
_tes = pd.to_datetime(merged_df['Delivery date'], dayfirst=True, errors='coerce').dt.normalize()
merged_df['Teslimat_Tarihi'] = _tes.groupby(merged_df['Depot_Match_Key']).transform('min')
_tes_farkli = _tes.groupby(merged_df['Depot_Match_Key']).nunique()
if (_tes_farkli > 1).any():
    print(f"   ⚠️  Birden fazla teslimat tarihi olan {int((_tes_farkli > 1).sum())} depo → en erken tarih alındı: "
          f"{_tes_farkli[_tes_farkli > 1].index.tolist()[:10]}")

merged_df['Sayim_Kisiti']  = False
merged_df['Sayim_Bilgisi'] = ''
_sayim_rapor   = []
_tarihsiz_depo = []
_bir_gun = pd.Timedelta(days=1)

for _depo, _g in merged_df.groupby('Depot_Match_Key'):
    _kod = _g['Location_Code_Clean'].iloc[0]
    _sayimlar = SAYIM_KAYITLARI.get(_kod, [])
    if not _sayimlar: continue
    _tt = _g['Teslimat_Tarihi'].iloc[0]
    if pd.isna(_tt):
        _tarihsiz_depo.append(_depo)
        continue
    _engel = None
    for _s in sorted(_sayimlar, key=lambda s: s['T']):
        _bas, _bit = _s['T'] + _s['bas'] * _bir_gun, _s['T'] + _s['bit'] * _bir_gun
        _kapsar = _bas <= _tt <= _bit
        if _kapsar and _engel is None: _engel = _s
        # Raporda teslimat gününe yakın sayımlar (dün .. +7 gün) görünsün
        if _kapsar or (bugun - _bir_gun <= _s['T'] <= bugun + 7 * _bir_gun):
            _sayim_rapor.append({
                'Depo': _depo, 'Depo Kodu': _kod, 'Depo Tipi': _s['tip'], 'Sayım Türü': _s['tur'],
                'Sayım Tarihi': _s['T'].strftime('%d.%m.%Y'), 'Sayım Açıklaması': _s['aciklama'],
                'Kural': f"T{_s['bas']:+d} .. T{_s['bit']:+d}".replace('+0', ''),
                'Teslimat Alınmayan Günler': f"{_bas.strftime('%d.%m')} - {_bit.strftime('%d.%m')}",
                'Teslimat Tarihi': _tt.strftime('%d.%m.%Y'),
                'Durum': 'KISILDI - SAYIM' if _kapsar else 'Teslimat yasak aralık dışında',
            })
    if _engel is not None:
        merged_df.loc[_g.index, 'Sayim_Kisiti']  = True
        merged_df.loc[_g.index, 'Sayim_Bilgisi'] = (f"{_engel['T'].strftime('%d.%m')} {_engel['aciklama']} "
                                                    f"({_engel['tip']} {_engel['tur']})")
if _tarihsiz_depo:
    print(f"   🚨 Sayımı olan ama Relex teslimat tarihi BOŞ olan {len(_tarihsiz_depo)} depo kontrol EDİLEMEDİ: "
          f"{_tarihsiz_depo[:10]}")

def _sayim_kisiti_uygula():
    """Sayım kısıtlı depolarda tüm satırları sıfırlar. Arada nedeni ezebilecek
    adımlardan (backlog blokajı vb.) sonra tekrar çağrılır. Önce sadece A testinin A dışı
    satırlarını sıfırlar; sayım sonra gelir, sayımlı depoda neden 'Sayım' kalır."""
    _a = merged_df['Sadece_A_Iptal'] == True
    if _a.any():
        if 'Final_Quantity' in merged_df.columns:
            merged_df.loc[_a, 'Final_Quantity'] = 0
        merged_df.loc[_a, 'Trim_Reason'] = SADECE_A_REASON
    _m = merged_df['Sayim_Kisiti'] == True
    if _m.any():
        if 'Final_Quantity' in merged_df.columns:
            merged_df.loc[_m, 'Final_Quantity'] = 0
        merged_df.loc[_m, 'Trim_Reason'] = SAYIM_REASON

_sayim_kisiti_uygula()
print(f"📋 Sayım kısıtı: {merged_df.loc[merged_df['Sayim_Kisiti'], 'Depot_Match_Key'].nunique()} depo / "
      f"{int(merged_df['Sayim_Kisiti'].sum())} satır tamamen kesilecek")

# ==========================================
# 3.5. BULK ROUND-ROBIN DAĞITIM — FLOOR
# ==========================================
blocked_reasons_set = {
    'Kara Liste', 'G10 Backlog Engeli', 'GB Backlog Engeli', SAYIM_REASON, SADECE_A_REASON,
}
bulk_products = merged_df[merged_df['Is_Bulk']]['Product_Code_Clean'].unique()

merged_df['BULK_Verilen_Kasa'] = 0
merged_df['BULK_Oneri_Kasa']   = 0

for prod_code in bulk_products:
    prod_mask = merged_df['Product_Code_Clean'] == prod_code
    prod_rows = merged_df[prod_mask]

    kasa_kilo = prod_rows['Gercek_Kasa_Kilo'].iloc[0]
    if kasa_kilo <= 0:
        continue

    is_ptz = prod_rows['Pick-to-zero'].iloc[0] == 1

    if is_ptz:
        aday_mask = prod_mask & (~merged_df['Trim_Reason'].isin(blocked_reasons_set))
    else:
        aday_mask = prod_mask & (merged_df['Effective quantity'] > 0) & (~merged_df['Trim_Reason'].isin(blocked_reasons_set))

    if not aday_mask.any():
        continue

    if is_ptz:
        end_bal_dc  = prod_rows['End Balance DC'].iloc[0]
        toplam_kasa = int(np.floor(end_bal_dc / kasa_kilo)) if end_bal_dc > 0 else 0
    else:
        toplam_eq   = merged_df.loc[aday_mask, 'Effective quantity'].sum()
        toplam_kasa = int(np.floor(toplam_eq / kasa_kilo))

    if toplam_kasa <= 0:
        continue

    merged_df.loc[aday_mask, 'BULK_Oneri_Kasa'] = np.maximum(
        1,
        np.floor(merged_df.loc[aday_mask, 'Effective quantity'] / kasa_kilo)
    ).astype(int)

    merged_df.loc[prod_mask, 'BULK_Verilen_Kasa'] = 0
    kalan_kasa = toplam_kasa

    while kalan_kasa > 0:
        if is_ptz:
            tur_mask_faz1 = (
                prod_mask &
                (~merged_df['Trim_Reason'].isin(blocked_reasons_set)) &
                (merged_df['BULK_Verilen_Kasa'] < merged_df['BULK_Oneri_Kasa'])
            )
            tur_mask_faz2 = (
                prod_mask &
                (~merged_df['Trim_Reason'].isin(blocked_reasons_set))
            )
            tur_mask = tur_mask_faz1 if tur_mask_faz1.any() else tur_mask_faz2
        else:
            tur_mask = (
                prod_mask &
                (~merged_df['Trim_Reason'].isin(blocked_reasons_set)) &
                (merged_df['BULK_Verilen_Kasa'] < merged_df['BULK_Oneri_Kasa'])
            )

        if not tur_mask.any():
            break

        tur_df = merged_df.loc[tur_mask].copy()
        tur_df['_kalan_oneri'] = tur_df['BULK_Oneri_Kasa'] - tur_df['BULK_Verilen_Kasa']

        if is_ptz and not tur_mask_faz1.any():
            tur_df = tur_df.sort_values('Cover_Day_Calc', ascending=True)
        elif is_ptz:
            tur_df['_eq_var'] = (tur_df['Effective quantity'] > 0).astype(int)
            tur_df = tur_df.sort_values(
                by=['_eq_var', '_kalan_oneri', 'Cover_Day_Calc'],
                ascending=[False, False, True]
            )
        else:
            tur_df = tur_df.sort_values(
                by=['_kalan_oneri', 'Cover_Day_Calc'], ascending=[False, True]
            )

        for idx in tur_df.index:
            if kalan_kasa <= 0:
                break
            merged_df.loc[idx, 'BULK_Verilen_Kasa'] += 1
            kalan_kasa -= 1

    for idx in merged_df.loc[prod_mask].index:
        if merged_df.loc[idx, 'Trim_Reason'] in blocked_reasons_set:
            continue
        verilen = merged_df.loc[idx, 'BULK_Verilen_Kasa']
        oneri   = merged_df.loc[idx, 'BULK_Oneri_Kasa']
        eq      = merged_df.loc[idx, 'Effective quantity']
        if verilen == 0 and eq > 0:
            if eq < kasa_kilo:
                merged_df.loc[idx, 'Trim_Reason'] = 'BULK Oneri Kasa Kilosundan Kucuk - Gonderilmedi'
            else:
                merged_df.loc[idx, 'Trim_Reason'] = 'BULK MD Stok Yetersiz - Kasa Yok'
        elif verilen > 0 and eq > 0 and verilen < oneri:
            merged_df.loc[idx, 'Trim_Reason'] = 'BULK Kismen Yuklendi (MD Stok Limiti)'

merged_df['BULK_Kasa_Adedi'] = np.where(
    merged_df['Is_Bulk'], merged_df['BULK_Verilen_Kasa'], 0
).astype(float)

merged_df['Effective_Units'] = np.where(
    merged_df['Is_Bulk'],
    merged_df['BULK_Verilen_Kasa'] * merged_df['Gercek_Kasa_Kilo'],
    merged_df['Effective quantity']
).astype(float)

merged_df['Vol_Per_Unit']   = merged_df['hacim2_prod']
merged_df['Final_Quantity'] = merged_df['Effective_Units'].copy()
_sayim_kisiti_uygula()

# ==========================================
# 4. KAPASİTE HESAPLAMA
# ==========================================
def _safe(col):
    return pd.to_numeric(merged_df.get(col, 0), errors='coerce').fillna(0)

merged_df['Max_MS_Volume_+4']   = _safe('Max. Other +4 & MS +4 WH Volume')
merged_df['Max_MS_Volume_8-12'] = _safe('Max. MS +8-12 WH Volume')

merged_df['T1_Factor_Uygulanan'] = np.where(
    merged_df['Slot_Ogle_Oncesi_Biten'].fillna(False).astype(bool), 0.0, T1_FACTOR
)
_t1_factor_effective = merged_df['T1_Factor_Uygulanan']

_mevcut_4  = _safe('All MS +4 Volume Litre')
_transit_4 = _safe('All MS +4 In Transit Volume Litre')
_frc_t_4   = _safe('All MS +4 Volume Litre (frc t)')
_frc_t1_4  = _safe('All MS +4 Volume Litre (frc t+1)')
_bos_4     = _frc_t_4 + _frc_t1_4 * _t1_factor_effective
_kapasite_4 = merged_df['Max_MS_Volume_+4'] * merged_df['ms4_oran'] * merged_df['buffer_rate']
merged_df['Order_Allowed_Empty_Space_+4'] = (_kapasite_4 - (_mevcut_4 + _transit_4 - _bos_4)).clip(lower=0)

_mevcut_8  = _safe('MS +8-12 Volume Litre')
_transit_8 = _safe('MS +8-12 In Transit Volume Litre')
_frc_t_8   = _safe('MS +8-12 Volume Litre (frc t)')
_frc_t1_8  = _safe('MS +8-12 Volume Litre (frc t+1)')
_bos_8     = _frc_t_8 + _frc_t1_8 * _t1_factor_effective
_kapasite_8 = merged_df['Max_MS_Volume_8-12'] * merged_df['ms812_oran'] * merged_df['buffer_rate']
merged_df['Order_Allowed_Empty_Space_8-12'] = (_kapasite_8 - (_mevcut_8 + _transit_8 - _bos_8)).clip(lower=0)

merged_df['Initial_Dolu_Hacim_+4']            = (_mevcut_4 + _transit_4 - _bos_4).clip(lower=0)
merged_df['Initial_Ratio_Pct_+4']             = np.where(_kapasite_4 > 0, (_mevcut_4 + _transit_4) / _kapasite_4 * 100, 0).round(2)
merged_df['Initial_Empty_Space_Litre_+4']     = (_kapasite_4 - _mevcut_4 - _transit_4).clip(lower=0)
merged_df['Forecast_Freed_Volume_Total_+4']   = _bos_4
merged_df['Forecast_T_Litre_+4']              = _frc_t_4
merged_df['Forecast_T1_Litre_+4']             = _frc_t1_4

merged_df['Initial_Dolu_Hacim_8-12']          = (_mevcut_8 + _transit_8 - _bos_8).clip(lower=0)
merged_df['Initial_Ratio_Pct_8-12']           = np.where(_kapasite_8 > 0, (_mevcut_8 + _transit_8) / _kapasite_8 * 100, 0).round(2)
merged_df['Initial_Empty_Space_Litre_8-12']   = (_kapasite_8 - _mevcut_8 - _transit_8).clip(lower=0)
merged_df['Forecast_Freed_Volume_Total_8-12'] = _bos_8
merged_df['Forecast_T_Litre_8-12']            = _frc_t_8
merged_df['Forecast_T1_Litre_8-12']           = _frc_t1_8

merged_df['Proposed_Item_Volume']        = merged_df['Effective_Units'] * merged_df['Vol_Per_Unit']
merged_df['Group_Total_Proposed_Volume'] = merged_df.groupby(['Depot_Match_Key', 'Cabinet_Type'])['Proposed_Item_Volume'].transform('sum')

# ==========================================
# 5. BAŞLANGIÇ BLOKAJLAR
# ==========================================
for idx, row in merged_df.iterrows():
    domain      = str(row['Domain Type']).upper().strip()
    backlog_val = row['Backlog']
    if row['Location name'] in BLACKLISTED_DEPOTS:
        merged_df.loc[idx, 'Final_Quantity'] = 0
        merged_df.loc[idx, 'Trim_Reason']    = 'Kara Liste'
    elif domain == 'G10' and backlog_val > 0:
        merged_df.loc[idx, 'Final_Quantity'] = 0
        merged_df.loc[idx, 'Trim_Reason']    = 'G10 Backlog Engeli'
    elif domain == 'GB' and backlog_val >= 5:
        merged_df.loc[idx, 'Final_Quantity'] = 0
        merged_df.loc[idx, 'Trim_Reason']    = 'GB Backlog Engeli'

# Sayım, kara liste/backlog blokajlarından önce gelir → neden 'Sayım' kalsın
_sayim_kisiti_uygula()

# ==========================================
# 5.5 PTZ SPOILING TIME YARDIMCI FONKSİYONU
# ==========================================
def max_batches_within_spoiling(idx, batch, max_batches_allowed):
    if merged_df.loc[idx, 'Pick-to-zero'] != 1:
        return max_batches_allowed
    if batch <= 0 or max_batches_allowed <= 0:
        return 0

    daily_fc = merged_df.loc[idx, 'Daily FC']
    if daily_fc <= 0:
        return max_batches_allowed

    spoiling = merged_df.loc[idx, 'Reference_Spoiling_Time']
    end_bal  = merged_df.loc[idx, 'End balance']
    opo      = merged_df.loc[idx, 'Open purchase orders']
    fq       = merged_df.loc[idx, 'Final_Quantity']

    count = 0
    while count < max_batches_allowed:
        new_cover = (end_bal + opo + fq + (count + 1) * batch) / daily_fc
        if new_cover > spoiling:
            break
        count += 1
    return count


def ptz_batch_would_exceed_spoiling(idx, batch):
    if merged_df.loc[idx, 'Pick-to-zero'] != 1:
        return False
    daily_fc = merged_df.loc[idx, 'Daily FC']
    if daily_fc <= 0:
        return False
    spoiling  = merged_df.loc[idx, 'Reference_Spoiling_Time']
    end_bal   = merged_df.loc[idx, 'End balance']
    opo       = merged_df.loc[idx, 'Open purchase orders']
    fq        = merged_df.loc[idx, 'Final_Quantity']
    new_cover = (end_bal + opo + fq + batch) / daily_fc
    return new_cover > spoiling

# ==========================================
# 6. DOLAP BAZINDA HACİM KISMA
# ==========================================
abc_trim_map = {'C': 0, 'B': 1, 'A': 2}
merged_df['ABC_Trim_Weight'] = (
    merged_df['ABC class'].astype(str).str.upper().str.strip()
    .map(abc_trim_map).fillna(2)
)

for (loc, cab), group in merged_df.groupby(['Depot_Match_Key', 'Cabinet_Type']):
    if cab == 'Ambient':
        continue
    if not group['Doluluk_Tablosunda_Var_Mi'].iloc[0]:
        continue

    allowed_vol = (
        group['Order_Allowed_Empty_Space_+4'].iloc[0]
        if cab == '+4'
        else group['Order_Allowed_Empty_Space_8-12'].iloc[0]
    )

    if allowed_vol <= 0:
        zero_indices = group[(group['Final_Quantity'] > 0) & (~group['Trim_Exempt'])].index
        merged_df.loc[zero_indices, 'Final_Quantity'] = 0
        merged_df.loc[zero_indices, 'Trim_Reason']    = 'Kapasite Yok (0)'
        continue

    mask = (
        (merged_df['Depot_Match_Key'] == loc) &
        (merged_df['Cabinet_Type']    == cab) &
        (~merged_df['Trim_Exempt'])
    )
    current_total_vol = (merged_df[mask]['Final_Quantity'] * merged_df[mask]['Vol_Per_Unit']).sum()

    if current_total_vol <= allowed_vol:
        continue

    trimmable    = group[~group['Trim_Exempt']]
    sorted_group = trimmable.sort_values(by=['ABC_Trim_Weight', 'Cover_Day_Calc'], ascending=[True, False])

    for idx in sorted_group.index:
        if current_total_vol <= allowed_vol:
            break
        fq           = merged_df.loc[idx, 'Final_Quantity']
        vol_per_unit = merged_df.loc[idx, 'Vol_Per_Unit']
        if fq <= 0 or vol_per_unit <= 0:
            continue

        batch = pd.to_numeric(merged_df.loc[idx, 'Order batch size'], errors='coerce')
        batch = 1 if (pd.isna(batch) or batch <= 0) else int(batch)
        if merged_df.loc[idx, 'Is_Bulk']:
            batch = merged_df.loc[idx, 'Gercek_Kasa_Kilo']

        qty_to_trim = min(fq, np.ceil(np.ceil((current_total_vol - allowed_vol) / vol_per_unit) / batch) * batch)
        new_fq      = max(0, fq - qty_to_trim)

        current_total_vol                   -= (fq - new_fq) * vol_per_unit
        merged_df.loc[idx, 'Final_Quantity'] = new_fq
        merged_df.loc[idx, 'Trim_Reason']    = 'Dolap Kapasite Yetersizligi Sebebiyle Kisildi/Silindi'

# ==========================================
# 7A. HACİM KISMASI SONRASI RESTORASYON
# ==========================================
abc_restore_map = {'A': 0, 'B': 1, 'C': 2}
merged_df['ABC_Restore_Weight'] = (
    merged_df['ABC class'].astype(str).str.upper().str.strip()
    .map(abc_restore_map).fillna(2)
)

for (loc, cab), group in merged_df.groupby(['Depot_Match_Key', 'Cabinet_Type']):
    if cab == 'Ambient':
        continue
    if not group['Doluluk_Tablosunda_Var_Mi'].iloc[0]:
        continue

    allowed_vol = (
        group['Order_Allowed_Empty_Space_+4'].iloc[0]
        if cab == '+4'
        else group['Order_Allowed_Empty_Space_8-12'].iloc[0]
    )
    if allowed_vol == 0:
        continue

    mask = (
        (merged_df['Depot_Match_Key'] == loc) &
        (merged_df['Cabinet_Type']    == cab) &
        (~merged_df['Trim_Exempt'])
    )
    current_total_vol  = (merged_df[mask]['Final_Quantity'] * merged_df[mask]['Vol_Per_Unit']).sum()
    remaining_vol      = allowed_vol - current_total_vol
    if remaining_vol <= 0:
        continue

    aktif_satir_sayisi = int((merged_df['Final_Quantity'] > 0).sum())

    kismi_restore = group[
        (~group['Trim_Exempt']) &
        (group['Final_Quantity'] > 0) &
        (group['Final_Quantity'] < group['Effective_Units'])
    ]
    tam_sifir_restore = group[
        (~group['Trim_Exempt']) &
        (group['Final_Quantity'] == 0) &
        (group['Effective_Units'] > 0) &
        (group['Trim_Reason'] == 'Dolap Kapasite Yetersizligi Sebebiyle Kisildi/Silindi') &
        (aktif_satir_sayisi < MAX_ROWS)
    ]

    restore_candidates = pd.concat([kismi_restore, tam_sifir_restore])
    if restore_candidates.empty:
        continue

    sorted_restore = restore_candidates.sort_values(
        by=['ABC_Restore_Weight', 'Cover_Day_Calc'], ascending=[True, True]
    )

    for idx in sorted_restore.index:
        if remaining_vol <= 0:
            break
        fq           = merged_df.loc[idx, 'Final_Quantity']
        eff_q        = merged_df.loc[idx, 'Effective_Units']
        vol_per_unit = merged_df.loc[idx, 'Vol_Per_Unit']
        if vol_per_unit <= 0 or fq >= eff_q:
            continue

        if fq == 0 and int((merged_df['Final_Quantity'] > 0).sum()) >= MAX_ROWS:
            continue

        batch = pd.to_numeric(merged_df.loc[idx, 'Order batch size'], errors='coerce')
        batch = 1 if (pd.isna(batch) or batch <= 0) else int(batch)
        if merged_df.loc[idx, 'Is_Bulk']:
            batch = merged_df.loc[idx, 'Gercek_Kasa_Kilo']

        max_batches_by_vol = np.floor(np.floor(remaining_vol / vol_per_unit) / batch)
        batches_to_eff_q   = np.ceil((eff_q - fq) / batch)
        actual_batches     = min(max_batches_by_vol, batches_to_eff_q)
        actual_batches     = max_batches_within_spoiling(idx, batch, actual_batches)

        if actual_batches <= 0:
            continue

        qty_to_add         = actual_batches * batch
        new_fq             = min(fq + qty_to_add, eff_q)
        current_total_vol += (new_fq - fq) * vol_per_unit
        remaining_vol      = allowed_vol - current_total_vol

        merged_df.loc[idx, 'Final_Quantity'] = new_fq
        merged_df.loc[idx, 'Trim_Reason']    = (
            'Onaylandi (Acilan Bosliga Geri Yuklendi)'
            if new_fq == eff_q
            else 'Bosa Cikan Hacimle Kismen Geri Yuklendi'
        )

# ==========================================
# 7. SATIR LİMİTİ KONTROLÜ
# ==========================================
active_rows = merged_df[merged_df['Final_Quantity'] > 0]

if len(active_rows) > MAX_ROWS:
    print(f"⚠️  Satır limiti aşıldı! Aktif satır: {len(active_rows)}. {MAX_ROWS}'a düşürülüyor...")
    rows_to_delete_sorted = active_rows[~active_rows['Sadece_A_Test']].sort_values(
        by=['ABC_Trim_Weight', 'Cover_Day_Calc'], ascending=[True, False]
    )
    num_to_delete     = len(active_rows) - MAX_ROWS
    indices_to_delete = rows_to_delete_sorted.index[:num_to_delete]
    merged_df.loc[indices_to_delete, 'Final_Quantity'] = 0
    merged_df.loc[indices_to_delete, 'Trim_Reason']    = 'Merkez Depo 10000 Satır Limiti Sebebiyle Silindi'

# ==========================================
# 8. SATIR LİMİTİ SONRASI RESTORASYON
# ==========================================
for (loc, cab), group in merged_df.groupby(['Depot_Match_Key', 'Cabinet_Type']):
    if cab == 'Ambient':
        continue
    if not group['Doluluk_Tablosunda_Var_Mi'].iloc[0]:
        continue

    allowed_vol = (
        group['Order_Allowed_Empty_Space_+4'].iloc[0]
        if cab == '+4'
        else group['Order_Allowed_Empty_Space_8-12'].iloc[0]
    )
    if allowed_vol == 0:
        continue

    mask = (
        (merged_df['Depot_Match_Key'] == loc) &
        (merged_df['Cabinet_Type']    == cab) &
        (~merged_df['Trim_Exempt'])
    )
    current_total_vol = (merged_df[mask]['Final_Quantity'] * merged_df[mask]['Vol_Per_Unit']).sum()
    remaining_vol     = allowed_vol - current_total_vol
    if remaining_vol <= 0:
        continue

    restore_candidates = group[
        (~group['Trim_Exempt']) &
        (group['Final_Quantity'] > 0) &
        (group['Final_Quantity'] < group['Effective_Units'])
    ]
    if restore_candidates.empty:
        continue

    sorted_restore = restore_candidates.sort_values(
        by=['ABC_Restore_Weight', 'Cover_Day_Calc'], ascending=[True, True]
    )

    for idx in sorted_restore.index:
        if remaining_vol <= 0:
            break
        fq           = merged_df.loc[idx, 'Final_Quantity']
        eff_q        = merged_df.loc[idx, 'Effective_Units']
        vol_per_unit = merged_df.loc[idx, 'Vol_Per_Unit']
        if vol_per_unit <= 0 or fq >= eff_q:
            continue

        batch = pd.to_numeric(merged_df.loc[idx, 'Order batch size'], errors='coerce')
        batch = 1 if (pd.isna(batch) or batch <= 0) else int(batch)
        if merged_df.loc[idx, 'Is_Bulk']:
            batch = merged_df.loc[idx, 'Gercek_Kasa_Kilo']

        max_batches_by_vol = np.floor(np.floor(remaining_vol / vol_per_unit) / batch)
        batches_to_eff_q   = np.ceil((eff_q - fq) / batch)
        actual_batches     = min(max_batches_by_vol, batches_to_eff_q)
        actual_batches     = max_batches_within_spoiling(idx, batch, actual_batches)

        if actual_batches <= 0:
            continue

        qty_to_add         = actual_batches * batch
        new_fq             = min(fq + qty_to_add, eff_q)
        current_total_vol += (new_fq - fq) * vol_per_unit
        remaining_vol      = allowed_vol - current_total_vol

        merged_df.loc[idx, 'Final_Quantity'] = new_fq
        merged_df.loc[idx, 'Trim_Reason']    = (
            'Onaylandi (Acilan Bosliga Geri Yuklendi)'
            if new_fq == eff_q
            else 'Bosa Cikan Hacimle Kismen Geri Yuklendi'
        )

# ==========================================
# 9. PICK-TO-ZERO (PTZ) DAGITIM
# ==========================================
ptz_products = merged_df[
    (merged_df['Pick-to-zero'] == 1) & (~merged_df['Is_Bulk'])
]['Product_Code_Clean'].unique()

for prod_code in ptz_products:
    prod_rows = merged_df[merged_df['Product_Code_Clean'] == prod_code]
    total_eff = prod_rows['Effective_Units'].sum()
    total_fin = prod_rows['Final_Quantity'].sum()

    if total_fin >= total_eff:
        continue

    deficit = total_eff - total_fin
    eligible_idx = list(prod_rows[
        (~prod_rows['Trim_Reason'].isin(blocked_reasons_set)) &
        (prod_rows['Daily FC'] > 0)
    ].index)
    if not eligible_idx:
        continue

    while deficit > 0 and eligible_idx:
        covers = {}
        for idx in eligible_idx:
            daily_fc = merged_df.loc[idx, 'Daily FC']
            covers[idx] = (
                merged_df.loc[idx, 'End balance'] +
                merged_df.loc[idx, 'Open purchase orders'] +
                merged_df.loc[idx, 'Final_Quantity']
            ) / daily_fc if daily_fc > 0 else 999999

        best_idx     = min(covers, key=covers.get)
        is_exempt    = merged_df.loc[best_idx, 'Trim_Exempt']
        cab          = merged_df.loc[best_idx, 'Cabinet_Type']
        loc          = merged_df.loc[best_idx, 'Depot_Match_Key']
        vol_per_unit = merged_df.loc[best_idx, 'Vol_Per_Unit']
        batch        = int(merged_df.loc[best_idx, 'Order batch size'])

        if not (is_exempt or cab == 'Ambient'):
            if not merged_df.loc[best_idx, 'Doluluk_Tablosunda_Var_Mi']:
                eligible_idx.remove(best_idx)
                continue

            allowed_vol = (
                merged_df.loc[best_idx, 'Order_Allowed_Empty_Space_+4']
                if cab == '+4'
                else merged_df.loc[best_idx, 'Order_Allowed_Empty_Space_8-12']
            )
            non_exempt_mask = (
                (merged_df['Depot_Match_Key'] == loc) &
                (merged_df['Cabinet_Type']    == cab) &
                (~merged_df['Trim_Exempt'])
            )
            current_total_vol = (merged_df[non_exempt_mask]['Final_Quantity'] * merged_df[non_exempt_mask]['Vol_Per_Unit']).sum()
            remaining_vol     = allowed_vol - current_total_vol

            if remaining_vol <= 0 or vol_per_unit <= 0 or remaining_vol < vol_per_unit * batch:
                eligible_idx.remove(best_idx)
                continue

        if ptz_batch_would_exceed_spoiling(best_idx, batch):
            eligible_idx.remove(best_idx)
            continue

        merged_df.loc[best_idx, 'Final_Quantity']   += batch
        merged_df.loc[best_idx, 'PTZ_Eklenen_Adet'] += batch
        deficit -= batch

# ==========================================
# 9.6. BULK SIFIRLAMA VE TELAFİ
# ==========================================
def get_kalan_kapasite(idx):
    loc_ = merged_df.loc[idx, 'Depot_Match_Key']
    vpu  = merged_df.loc[idx, 'Vol_Per_Unit']
    cab_    = merged_df.loc[idx, 'Cabinet_Type']
    allowed = (
        merged_df.loc[idx, 'Order_Allowed_Empty_Space_+4']
        if cab_ == '+4'
        else merged_df.loc[idx, 'Order_Allowed_Empty_Space_8-12']
    )
    non_ex  = (
        (merged_df['Depot_Match_Key'] == loc_) &
        (merged_df['Cabinet_Type']    == cab_) &
        (~merged_df['Trim_Exempt'])
    )
    current = (merged_df[non_ex]['Final_Quantity'] * merged_df[non_ex]['Vol_Per_Unit']).sum()
    return allowed - current, vpu

print("🔄 BULK sıfırlama/telafi (kısma sonrası) yapılıyor...")

for prod_code in bulk_products:
    prod_mask = merged_df['Product_Code_Clean'] == prod_code
    prod_rows = merged_df[prod_mask]

    kasa_kilo = prod_rows['Gercek_Kasa_Kilo'].iloc[0]
    if kasa_kilo <= 0:
        continue

    is_ptz     = prod_rows['Pick-to-zero'].iloc[0] == 1
    toplam_eq  = prod_rows['Effective quantity'].sum()
    end_bal_dc = prod_rows['End Balance DC'].iloc[0]

    if is_ptz:
        hedef_kilo = int(np.floor(end_bal_dc / kasa_kilo)) * kasa_kilo
    else:
        batch_size = prod_rows['Order batch size'].iloc[0]
        fark = end_bal_dc - toplam_eq
        if fark < 0 or fark >= batch_size:
            continue
        hedef_kilo = int(np.floor(toplam_eq / kasa_kilo)) * kasa_kilo

    toplam_final_kilo = prod_rows['Final_Quantity'].sum()
    acik_kilo         = hedef_kilo - toplam_final_kilo

    if acik_kilo <= 0:
        continue

    acik_kasa = int(np.floor(acik_kilo / kasa_kilo))
    if acik_kasa <= 0:
        continue

    aday_mask = (
        prod_mask &
        (~merged_df['Trim_Reason'].isin(blocked_reasons_set)) &
        merged_df['Doluluk_Tablosunda_Var_Mi'] &
        (merged_df['Cabinet_Type'] != 'Ambient') &
        ((not is_ptz) | (merged_df['Daily FC'] > 0))
    )
    if not aday_mask.any():
        continue

    adaylar      = merged_df.loc[aday_mask].sort_values('Cover_Day_Calc', ascending=True)
    kalan_acik   = acik_kasa
    eklenen_kasa = 0

    for idx in adaylar.index:
        if kalan_acik <= 0:
            break
        if merged_df.loc[idx, 'BULK_Telafi_Kasa'] >= 1:
            continue
        kap, vpu = get_kalan_kapasite(idx)
        if vpu > 0 and kap >= kasa_kilo * vpu:
            if is_ptz and ptz_batch_would_exceed_spoiling(idx, kasa_kilo):
                continue
            merged_df.loc[idx, 'Final_Quantity']   += kasa_kilo
            merged_df.loc[idx, 'BULK_Telafi_Kasa'] += 1
            kalan_acik   -= 1
            eklenen_kasa += 1

for prod_code in bulk_products:
    prod_mask = merged_df['Product_Code_Clean'] == prod_code
    prod_rows = merged_df[prod_mask]

    kasa_kilo = prod_rows['Gercek_Kasa_Kilo'].iloc[0]
    if kasa_kilo <= 0:
        continue

    is_ptz     = prod_rows['Pick-to-zero'].iloc[0] == 1
    end_bal_dc = prod_rows['End Balance DC'].iloc[0]
    if end_bal_dc <= 0:
        continue

    toplam_eq = prod_rows['Effective quantity'].sum()

    if is_ptz:
        hedef_kilo = int(np.floor(end_bal_dc / kasa_kilo)) * kasa_kilo
    else:
        batch_size = prod_rows['Order batch size'].iloc[0]
        fark       = end_bal_dc - toplam_eq
        if fark < 0 or fark >= batch_size:
            continue
        hedef_kilo = int(np.floor(toplam_eq / kasa_kilo)) * kasa_kilo

    toplam_final_kilo = prod_rows['Final_Quantity'].sum()

    if not is_ptz and toplam_final_kilo < hedef_kilo - 0.01:
        continue

    kalan_kilo = end_bal_dc - toplam_final_kilo
    if kalan_kilo <= 0:
        continue

    tam_kasa   = int(np.floor(kalan_kilo / kasa_kilo))
    artik_kilo = round(kalan_kilo - (tam_kasa * kasa_kilo), 6)

    aday_mask = (
        prod_mask &
        (~merged_df['Trim_Reason'].isin(blocked_reasons_set)) &
        merged_df['Doluluk_Tablosunda_Var_Mi'] &
        (merged_df['Cabinet_Type'] != 'Ambient') &
        ((not is_ptz) | (merged_df['Daily FC'] > 0))
    )
    if not aday_mask.any():
        continue

    adaylar      = merged_df.loc[aday_mask].sort_values('Cover_Day_Calc', ascending=True)
    eklenen_kilo = 0

    kalan_kasa = tam_kasa
    for idx in adaylar.index:
        if kalan_kasa <= 0:
            break
        kap, vpu = get_kalan_kapasite(idx)
        if vpu > 0 and kap >= kasa_kilo * vpu:
            if is_ptz and ptz_batch_would_exceed_spoiling(idx, kasa_kilo):
                continue
            merged_df.loc[idx, 'Final_Quantity']      += kasa_kilo
            merged_df.loc[idx, 'BULK_Sifirlama_Kilo'] += kasa_kilo
            kalan_kasa   -= 1
            eklenen_kilo += kasa_kilo

    kalan_artik = int(np.floor(artik_kilo))
    for idx in adaylar.index:
        if kalan_artik <= 0:
            break
        if merged_df.loc[idx, 'Final_Quantity'] <= 0:
            continue
        kap, vpu = get_kalan_kapasite(idx)
        if vpu > 0 and kap >= 1.0 * vpu:
            if is_ptz and ptz_batch_would_exceed_spoiling(idx, 1.0):
                continue
            merged_df.loc[idx, 'Final_Quantity']      += 1.0
            merged_df.loc[idx, 'BULK_Sifirlama_Kilo'] += 1.0
            kalan_artik  -= 1
            eklenen_kilo += 1.0

# ==========================================
# 9.65 📦 DEPO TOPLAM ADET LİMİTİ — tüm geri yükleme/telafi adımlarından SONRA
#      Kesim sırası hacim kısmasıyla aynı: C → B → A, aynı sınıfta cover'ı yüksek olan önce.
# ==========================================
_ADET_LIMIT_NORM = {_norm_ad(k): v for k, v in DEPO_ADET_LIMITI.items()}
_HACIM_REASON = 'Dolap Kapasite Yetersizligi Sebebiyle Kisildi/Silindi'
_adet_eslesen = set()

for _depo, _g in merged_df.groupby('Depot_Match_Key'):
    _limit = _ADET_LIMIT_NORM.get(_norm_ad(_depo))
    if _limit is None: continue
    _adet_eslesen.add(_norm_ad(_depo))
    if _g['Sadece_A_Test'].any():
        print(f"📦 {_depo}: sadece A test deposu → adet limiti uygulanmadı")
        continue
    _toplam = float(merged_df.loc[_g.index, 'Final_Quantity'].sum())
    if _toplam <= _limit:
        print(f"📦 {_depo}: toplam {_toplam:,.0f} adet ≤ limit {_limit} → kısma yok")
        continue
    _fazla = _toplam - _limit
    _sirali = _g.sort_values(by=['ABC_Trim_Weight', 'Cover_Day_Calc'], ascending=[True, False]).index
    for idx in _sirali:
        if _fazla <= 0: break
        fq = merged_df.loc[idx, 'Final_Quantity']
        if fq <= 0: continue
        batch = pd.to_numeric(merged_df.loc[idx, 'Order batch size'], errors='coerce')
        batch = 1 if (pd.isna(batch) or batch <= 0) else int(batch)
        if merged_df.loc[idx, 'Is_Bulk']:
            batch = merged_df.loc[idx, 'Gercek_Kasa_Kilo']
        qty_to_trim = min(fq, np.ceil(_fazla / batch) * batch)
        merged_df.loc[idx, 'Final_Quantity'] = fq - qty_to_trim
        merged_df.loc[idx, 'Trim_Reason']    = _HACIM_REASON
        _fazla -= qty_to_trim
    print(f"📦 {_depo}: toplam {_toplam:,.0f} adet → limit {_limit} için "
          f"{merged_df.loc[_g.index, 'Final_Quantity'].sum():,.0f} adete kısıldı")

for _k in set(_ADET_LIMIT_NORM) - _adet_eslesen:
    print(f"   ⚠️  Adet limiti tanımlı ama bu koşuda bulunamayan depo: '{_k}'")

# Son güvenlik: hiçbir adım sayım kısıtlı depoya miktar yazmamış olmalı
_sayim_ihlal = int(((merged_df['Sayim_Kisiti']) & (merged_df['Final_Quantity'] > 0)).sum())
if _sayim_ihlal:
    print(f"   ⚠️  Sayım kısıtlı depolarda {_sayim_ihlal} satıra sonradan miktar yazılmıştı → sıfırlandı.")
_sayim_kisiti_uygula()

# ==========================================
# 9.7 PTZ MERKEZ DEPO KALAN MİKTARI
# ==========================================
merged_df['PTZ_Merkez_Kalan_Miktar'] = np.nan
ptz_all_products = merged_df[merged_df['Pick-to-zero'] == 1]['Product_Code_Clean'].unique()
for prod_code in ptz_all_products:
    prod_mask    = merged_df['Product_Code_Clean'] == prod_code
    end_bal_dc   = merged_df.loc[prod_mask, 'End Balance DC'].iloc[0]
    toplam_final = merged_df.loc[prod_mask, 'Final_Quantity'].sum()
    merkez_kalan = max(0.0, end_bal_dc - toplam_final)
    merged_df.loc[prod_mask, 'PTZ_Merkez_Kalan_Miktar'] = round(merkez_kalan, 3)

# ==========================================
# 10. KISMA SONRASI ANALİZLER
# ==========================================
merged_df['Final_Item_Volume'] = merged_df['Final_Quantity'] * merged_df['Vol_Per_Unit']
group_final_vol = merged_df.groupby(['Depot_Match_Key', 'Cabinet_Type'])['Final_Item_Volume'].transform('sum')

merged_df['Allowed_Space'] = np.where(
    merged_df['Cabinet_Type'] == '+4',   merged_df['Order_Allowed_Empty_Space_+4'],
    np.where(
        merged_df['Cabinet_Type'] == '8-12', merged_df['Order_Allowed_Empty_Space_8-12'],
        np.nan
    )
)

merged_df['Final_Group_Utilization_Pct'] = np.where(
    (merged_df['Allowed_Space'] > 0) & (~merged_df['Trim_Exempt']),
    (group_final_vol / merged_df['Allowed_Space']) * 100,
    np.nan
).round(2)

merged_df['Cover_Effective_Qty_Day'] = np.where(
    merged_df['Daily FC'] > 0,
    (merged_df['End balance'] + merged_df['Open purchase orders'] + merged_df['Effective_Units']) / merged_df['Daily FC'],
    999999
).round(1)

merged_df['Cover_Final_Qty_Day'] = np.where(
    merged_df['Daily FC'] > 0,
    (merged_df['End balance'] + merged_df['Open purchase orders'] + merged_df['Final_Quantity']) / merged_df['Daily FC'],
    999999
).round(1)

merged_df['BULK_Final_Kilo'] = np.where(merged_df['Is_Bulk'], merged_df['Final_Quantity'], 0)

merged_df['BULK_Final_Kasa'] = np.where(
    merged_df['Is_Bulk'] & (merged_df['Gercek_Kasa_Kilo'] > 0),
    np.floor(
        merged_df['Final_Quantity'] / merged_df['Gercek_Kasa_Kilo']
    ).clip(lower=0),
    0
).astype(int)

# ==========================================
# 11. EXCEL ÇIKTI HAZIRLIKLARI: 4 SAYFA
# ==========================================

# --- SHEET 2: KAPASİTE DETAYI ---
audit_rows = []
for (loc, cab), grp in merged_df.groupby(['Depot_Match_Key', 'Cabinet_Type']):
    if cab == 'Ambient':
        continue

    allowed      = grp['Allowed_Space'].iloc[0] if not pd.isna(grp['Allowed_Space'].iloc[0]) else 0
    proposed_vol = (grp['Effective_Units'] * grp['Vol_Per_Unit']).sum()
    final_vol    = (grp['Final_Quantity']  * grp['Vol_Per_Unit']).sum()
    active_count = (grp['Final_Quantity'] > 0).sum()

    ms_oran  = grp['ms4_oran'].iloc[0]   if cab == '+4' else grp['ms812_oran'].iloc[0]
    buf      = grp['buffer_rate'].iloc[0]
    max_vol  = grp['Max_MS_Volume_+4'].iloc[0]   if cab == '+4' else grp['Max_MS_Volume_8-12'].iloc[0]
    raw_emp  = grp['Initial_Empty_Space_Litre_+4'].iloc[0]   if cab == '+4' else grp['Initial_Empty_Space_Litre_8-12'].iloc[0]
    frc_fr   = grp['Forecast_Freed_Volume_Total_+4'].iloc[0] if cab == '+4' else grp['Forecast_Freed_Volume_Total_8-12'].iloc[0]
    init_rat = grp['Initial_Ratio_Pct_+4'].iloc[0]            if cab == '+4' else grp['Initial_Ratio_Pct_8-12'].iloc[0]
    init_dol = grp['Initial_Dolu_Hacim_+4'].iloc[0]          if cab == '+4' else grp['Initial_Dolu_Hacim_8-12'].iloc[0]
    frc_t    = grp['Forecast_T_Litre_+4'].iloc[0]             if cab == '+4' else grp['Forecast_T_Litre_8-12'].iloc[0]
    frc_t1   = grp['Forecast_T1_Litre_+4'].iloc[0]            if cab == '+4' else grp['Forecast_T1_Litre_8-12'].iloc[0]
    t1_fac   = grp['T1_Factor_Uygulanan'].iloc[0]

    kap_oransiz  = max_vol
    kap_oranli   = max_vol * ms_oran
    kap_bufferli = max_vol * ms_oran * buf
    son_doluluk  = round((init_dol + final_vol) / kap_bufferli * 100, 2) if kap_bufferli > 0 else 0

    audit_rows.append({
        'Location name':              grp['Location name'].iloc[0],
        'Domain_Type':                grp['Domain Type'].iloc[0],
        'Sistem':                     grp['Sistem'].iloc[0],
        'Cabinet_Type':               cab,
        'Doluluk_Tablosunda_Var_Mi':  grp['Doluluk_Tablosunda_Var_Mi'].iloc[0],
        'Slot_Ogle_Oncesi_Biten':     grp['Slot_Ogle_Oncesi_Biten'].iloc[0],
        'T1_Factor_Uygulanan':        round(t1_fac, 4),
        'ms_oran':                    round(ms_oran, 4),
        'buffer_rate':                round(buf, 4),
        'Max_Pool_Litre':             round(kap_oransiz,  1),
        'MS_Kapasite_Oranli_Litre':   round(kap_oranli,   1),
        'MS_Kapasite_Bufferli_Litre': round(kap_bufferli, 1),
        'Initial_Doluluk_Pct':        round(init_rat, 2),
        'Initial_Dolu_Hacim_Litre':   round(init_dol, 1),
        'Raw_Empty_Litre':            round(raw_emp,  1),
        'Forecast_T_Litre':           round(frc_t,    1),
        'Forecast_T1_Litre':          round(frc_t1,   1),
        'Forecast_Freed_Litre':       round(frc_fr,   1),
        'Allowed_Space_Litre':        round(allowed,  1),
        'Proposed_Total_Vol':         round(proposed_vol, 2),
        'Final_Total_Vol':            round(final_vol,    2),
        'Proposed_Utilization_Pct':   round(proposed_vol / kap_bufferli * 100, 2) if kap_bufferli > 0 else 0,
        'Final_Utilization_Pct':      round(final_vol    / kap_bufferli * 100, 2) if kap_bufferli > 0 else 0,
        'Son_Doluluk_Pct':            son_doluluk,
        'Aktif_Satir_Sayisi':         int(active_count),
        'Toplam_Effective_Units':     round(grp['Effective_Units'].sum(), 2),
        'Toplam_Final_Qty':           round(grp['Final_Quantity'].sum(),  2),
        'Toplam_BULK_Final_Kilo':     round(grp['BULK_Final_Kilo'].sum(), 2),
    })

sheet2 = pd.DataFrame(audit_rows).sort_values(['Location name', 'Cabinet_Type']).reset_index(drop=True)

son_doluluk_map = sheet2[['Location name', 'Cabinet_Type', 'Son_Doluluk_Pct']].copy()
merged_df = pd.merge(merged_df, son_doluluk_map, on=['Location name', 'Cabinet_Type'], how='left')

# --- SHEET 1: ANA ÇIKTI ---
sheet1_cols = [
    'Location name', 'Location code', 'Domain Type', 'Sistem', 'Backlog',
    'Product code', 'Product name', 'Cabinet_Type', 'Trim_Exempt',
    'Is_Bulk', 'Transfer type', 'Gercek_Kasa_Kilo', 'BULK_Kasa_Adedi',
    'ABC class', 'Pick-to-zero', 'Order batch size',
    'Daily FC', '14 Days Sales', 'End balance', 'Open purchase orders', 'End Balance DC',
    'PTZ_Merkez_Kalan_Miktar',
    'Delivery date',
    'Cover_Day_Calc', 'Cover_Effective_Qty_Day', 'Cover_Final_Qty_Day', 'Reference_Spoiling_Time',
    'hacim2_prod', 'Vol_Per_Unit',
    'Effective quantity', 'Effective_Units',
    'Final_Quantity', 'BULK_Final_Kilo', 'BULK_Final_Kasa',
    'BULK_Verilen_Kasa', 'BULK_Telafi_Kasa', 'BULK_Sifirlama_Kilo',
    'PTZ_Eklenen_Adet',
    'Trim_Reason',
    'Sayim_Bilgisi',
    'Doluluk_Tablosunda_Var_Mi',
    'Slot_Ogle_Oncesi_Biten',
    'T1_Factor_Uygulanan',
    'Allowed_Space',
    'Final_Item_Volume',
    'Final_Group_Utilization_Pct',
    'Son_Doluluk_Pct',
]
sheet1_cols_mevcut = [c for c in sheet1_cols if c in merged_df.columns]
sheet1 = merged_df[sheet1_cols_mevcut].copy()

# --- SHEET 3: MERKEZ STOK ANALİZİ ---
ptz_urunler   = set(merged_df[merged_df['Pick-to-zero'] == 1]['Product_Code_Clean'].unique())
bulk_urunler  = set(merged_df[merged_df['Is_Bulk']]['Product_Code_Clean'].unique())
takip_urunler = ptz_urunler | bulk_urunler

merkez_rows = []
for prod_code in takip_urunler:
    prod_mask = merged_df['Product_Code_Clean'] == prod_code
    prod_rows = merged_df[prod_mask]
    if prod_rows.empty:
        continue

    is_bulk    = prod_rows['Is_Bulk'].iloc[0]
    is_ptz     = prod_rows['Pick-to-zero'].iloc[0] == 1
    urun_adi   = prod_rows['Product name'].iloc[0] if 'Product name' in prod_rows.columns else ''
    end_bal_dc = prod_rows['End Balance DC'].iloc[0]
    kasa_kilo  = prod_rows['Gercek_Kasa_Kilo'].iloc[0] if is_bulk else 0

    toplam_eq        = prod_rows['Effective quantity'].sum()
    toplam_effective = prod_rows['Effective_Units'].sum()
    toplam_final     = prod_rows['Final_Quantity'].sum()
    toplam_end_bal   = prod_rows['End balance'].sum()
    toplam_opo       = prod_rows['Open purchase orders'].sum()
    merkez_kalan     = end_bal_dc - toplam_final

    if is_bulk:
        toplam_rr_kasa    = int(prod_rows['BULK_Verilen_Kasa'].sum())
        toplam_telafi     = int(prod_rows['BULK_Telafi_Kasa'].sum())
        toplam_sif_kilo   = round(prod_rows['BULK_Sifirlama_Kilo'].sum(), 3)
        toplam_final_kasa = int(prod_rows['BULK_Final_Kasa'].sum())
        oneri_kasa        = int(np.floor(end_bal_dc / kasa_kilo)) if kasa_kilo > 0 else 0
        kalan_kasa        = max(0, oneri_kasa - toplam_final_kasa)
    else:
        toplam_rr_kasa = toplam_telafi = toplam_final_kasa = oneri_kasa = kalan_kasa = 0
        toplam_sif_kilo = 0

    trim_dagilim = prod_rows[
        prod_rows['Final_Quantity'] < prod_rows['Effective_Units']
    ]['Trim_Reason'].value_counts().to_dict()
    trim_ozet = ' | '.join([f"{v}x {k}" for k, v in trim_dagilim.items()])

    yollanan_depo = int((prod_rows['Final_Quantity'] > 0).sum())
    bloke_depo    = int(prod_rows['Trim_Reason'].isin(blocked_reasons_set).sum())
    kapsiz_depo   = int((prod_rows['Final_Quantity'] == 0).sum()) - bloke_depo

    merkez_rows.append({
        'Product code':           prod_code,
        'Product name':           urun_adi,
        'Is_Bulk':                is_bulk,
        'Pick-to-zero':           is_ptz,
        'Gercek_Kasa_Kilo':       kasa_kilo if is_bulk else '-',
        'End Balance DC':         end_bal_dc,
        'End balance (depo top)': round(toplam_end_bal, 1),
        'Open purchase orders':   round(toplam_opo, 1),
        'Toplam EQ (Relex)':      round(toplam_eq, 1),
        'Oneri Kasa':             oneri_kasa if is_bulk else '-',
        'Toplam Effective Units': round(toplam_effective, 1),
        'Toplam Final Qty':       round(toplam_final, 3),
        'RR Verilen Kasa':        toplam_rr_kasa if is_bulk else '-',
        'Telafi Kasasi':          toplam_telafi if is_bulk else '-',
        'Sifirlama Kilo':         toplam_sif_kilo if is_bulk else '-',
        'Toplam Final Kasa':      toplam_final_kasa if is_bulk else '-',
        'Merkez Kalan':           round(merkez_kalan, 3),
        'Kalan Kasa':             kalan_kasa if is_bulk else '-',
        'Merkez Kalan %':         round(merkez_kalan / end_bal_dc * 100, 1) if end_bal_dc > 0 else 0,
        'Yollanan Depo Sayisi':   yollanan_depo,
        'Bloke Depo Sayisi':      bloke_depo,
        'Kapsiz Depo Sayisi':     kapsiz_depo,
        'Kalan Sebebi Dagilimi':  trim_ozet if trim_ozet else 'Tumu yollandi',
    })

sheet3 = pd.DataFrame(merkez_rows).sort_values(
    ['Is_Bulk', 'Pick-to-zero', 'Product code']
).reset_index(drop=True)

# --- SHEET 4: BULK PANEL ÇIKTISI ---
bulk_panel_rows = []
bulk_aktif = merged_df[(merged_df['Is_Bulk']) & (merged_df['Final_Quantity'] > 0)]

for _, row in bulk_aktif.iterrows():
    bulk_panel_rows.append({
        'Main Warehouse Id':   '',
        'Main Warehouse Name': '',
        'Warehouse Id':        row.get('Location code', ''),
        'Warehouse Name':      row['Location name'],
        'Product Id':          row['Product code'],
        'Product Name':        row.get('Product name', ''),
        'yeni':                round(row['Final_Quantity'], 3),
        'kasa adedi':          int(row['BULK_Final_Kasa']),
    })

sheet4 = pd.DataFrame(bulk_panel_rows)

# --- SHEET 5: SAYIM KISITI ---
sheet5 = pd.DataFrame(_sayim_rapor)
if not sheet5.empty:
    _sk_ozet = (merged_df[merged_df['Sayim_Kisiti']].groupby('Depot_Match_Key')
                .agg(_satir=('Effective quantity', lambda x: int((x > 0).sum())), _miktar=('Effective quantity', 'sum')))
    _kisildi = sheet5['Durum'].str.startswith('KISILDI')
    sheet5['Kesilen Satır']  = np.where(_kisildi, sheet5['Depo'].map(_sk_ozet['_satir']), 0)
    sheet5['Kesilen Miktar'] = np.where(_kisildi, sheet5['Depo'].map(_sk_ozet['_miktar']), 0)
    sheet5 = sheet5.sort_values(['Durum', 'Depo', 'Sayım Tarihi']).reset_index(drop=True)

# ==========================================
# 📁 ÇIKTI YAZIMI (yerel klasör — Drive'a kayıt yok)
# ==========================================
# Excel, parquet ve All PL sürücü (surucu.py) tarafından çalışma klasörünün out/ ve allpl/ altına yazılır.
# Eskiden burada Google Drive'a yükleme vardı; kaldırıldı.
__EXCEL_YAZ__(globals())

# ==========================================
# 13. ÖZET RAPOR
# ==========================================
total_active  = int((merged_df['Final_Quantity'] > 0).sum())
bulk_active   = int(((merged_df['Final_Quantity'] > 0) & merged_df['Is_Bulk']).sum())
exempt_active = int(((merged_df['Final_Quantity'] > 0) & merged_df['Trim_Exempt']).sum())
normal_active = total_active - bulk_active - exempt_active
kisma_yok     = int((~merged_df['Doluluk_Tablosunda_Var_Mi']).sum())

sifirlar_df  = merged_df[merged_df['Final_Quantity'] == 0]
trim_counts  = sifirlar_df['Trim_Reason'].value_counts()
ptz_count    = int((merged_df['PTZ_Eklenen_Adet'] > 0).sum())
telafi_urun  = merged_df[merged_df['BULK_Telafi_Kasa']    > 0]['Product_Code_Clean'].nunique()
sifir_urun   = merged_df[merged_df['BULK_Sifirlama_Kilo'] > 0]['Product_Code_Clean'].nunique()

slot_depo_sayisi = merged_df[merged_df['Slot_Ogle_Oncesi_Biten']]['Depot_Match_Key'].nunique()

print("\n" + "=" * 52)
print("ÖZET RAPOR")
print("=" * 52)
print(f"  Toplam aktif satır:               {total_active}")
print(f"    - Normal:                        {normal_active}")
print(f"    - BULK:                          {bulk_active}")
print(f"    - Muaf (Ambient):                {exempt_active}")
print(f"  Kısma yapılmayan (doluluk yok):   {kisma_yok}")
print(f"  Sayım kısıtlı depo:               {merged_df.loc[merged_df['Sayim_Kisiti'], 'Depot_Match_Key'].nunique()} depo "
      f"({int((merged_df['Sayim_Kisiti'] & (merged_df['Effective quantity'] > 0)).sum())} satır kesildi)")
print(f"  Slot öğlen 12:00 öncesi biten depo: {slot_depo_sayisi} (bu depolarda +4 ve 8-12 için 1/3 T1 düşüşü uygulanmadı)")
print(f"  BULK kısma telafisi yapılan ürün: {telafi_urun}")
print(f"  BULK birer kilo sıfırlama ürün:   {sifir_urun}")
print(f"\n  Sıfırlanan satırlar:")
for reason, count in trim_counts.items():
    print(f"    - {reason}: {count}")
print(f"\n  PTZ ek adet alan satır:           {ptz_count}")
print(f"  Merkez stok takip ürün sayısı:    {len(sheet3)}")
print(f"  BULK panel satır sayısı:          {len(sheet4)}")
print("=" * 52)
print(f"✅ Sonuç Drive'a başarıyla kaydedildi!")