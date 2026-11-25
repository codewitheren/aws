# BİRLEŞİK SİSTEM: YENİ SİSTEM (paylaşımlı dolap) + ESKİ SİSTEM (47 test deposu)
# 🔀 v2: pooled doluluk verisi GSheet'ten (long format → pivot)
# 🔀 v2: Slot Saati kuralı — Frigo/Çift Rejim slotu öğlen 12:00 ve öncesi biten
#        depolarda lead time sonrası günün 1/3 forecast düşüşü UYGULANMAZ
# 🔀 v3: Ürün hacmi GSheet'ten (Max. Product Volume m3 — değer litre)
# 🔀 v3: Tek Excel çıktısı + Transfer sheet + sadeleştirilmiş Debug
# v4: çıktı direkt drivea gidiyor.
# v5: SAYIM KISITI (Cold Food kuralları) — teslimat günü sayım yasağına denk gelen depoya
#     hiçbir şey gitmez, kesinti nedeni 'Sayım'. + Depo bazlı toplam adet limiti.

import re
import pandas as pd
import numpy as np
import time

# ==========================================
# ⚙️ 0. KULLANICI PARAMETRELERİ (ÇALIŞTIRAN KİŞİ BURAYI SEÇECEK)
# ==========================================
CALISILAN_DEPO = "İzmir"      # Çıktı dosyasının adı olacak (Örn: Maltepe, İzmir vs.)
CALISILAN_KATEGORI = "+4"       # Seçenekler: "+4", "Ambient ve Su", "MS"
ANA_KLASOR_ID = "1V8xr411h9fyC0D0B0RQZw5ahkvKX-MaB"  # Çıktıların ekleneceği Drive klasör ID'si

# ==========================================
# ⚙️ 1. AYARLAR VE DOSYA YOLLARI
# ==========================================
MAX_SATIR_LIMITI_YENI = 6900   # Merkez satır limiti (tüm depolar)

PLUS_4_USABLE_RATIO = 1.1            # Buffer Rates sheet'inde olmayan depolar için varsayılan buffer
FORECAST_LOOKAHEAD_RATIO = 1 / 3     # Lead time sonrası günün kapasiteye eklenecek kırılım oranı

GB_COVER_DAY_LIMIT = 4.0
G10_COVER_DAY_LIMIT = 2.5

A_MIN_COVER = 5.5
B_MIN_COVER = 7.5
C_MIN_COVER = 2.0

# --- YENİ SİSTEM: DEFAULT ORANLAR (GSheet'te olmayan depolar için) ---
G10_DEFAULT_OTHER4_ORAN = 0.81
G10_DEFAULT_ETB_ORAN    = 0.76
GB_DEFAULT_OTHER4_ORAN  = 0.69
GB_DEFAULT_ETB_ORAN     = 0.08

# --- DOKUNULMAYACAK ÜRÜN LİSTELERİ ---
DOKUNULMAYACAK_G10 = [
    "6874e6be0cfe176f8f80c50c",'68eebd7a954e72282a317742', '5a86e06e1bc08f0004e03d3c', '659fd658bcb190b663090924', '69e75b1a136b03d799db0067', '641aa78085669d26f616f639', '659bae102263a29cebd6d8b8',
    "5cfe32bd4a644b0001f2076a", "588af61ef2532a0004000484", "6a206f3ecddd2d2428ddf56b", "68a2fc3cfa9c5a483b21b716", "68a2fc497d820f1e5f263e42",
    "699c403fb2959ed14655f184", "6197ba8c6316883bafe032e8", "63c165dcb7a840277ad5390c", "6a43bf1c6b0d219672d35c22", "5ced4828d349d10001e70504",
    "59e87cdcaee4410004c89a0e", "63519e7e79b1381b8c9e281b", "67caf98f06bdf74ea33d768f", "5ceae03a9d3ea8000196e150", "63da20a34818b3654dd89e6f",
    "5ce6581cfd9b330001c4a882", "60743ff01ec91d27d9ec84fb", "622739f2b36fd15940c8b154", "6257def3764adab6347eb7bd", "655db769e6dc4a3f6eeb9d9d",
    "669e4b1f58d03758bfacf150", "63847eaf5added0c73ca3a44", "638ca48127547f0cd63009b3", "69b7a5d30ecb25d4fae8c04e", "69b7aa8253dea25e459d016e",
    "61adf06ee4a956459279c282", "62fa08957432fa01a2f717e5", "6a3bb664d5903e9ba8cc2078", "6a3bd4ddfdefb038cb0fa147", "628cc303f9d984a4498c9db9",
    "5e2e9c78c0203663a8dfc16b", "5ce65822fd9b330001c4a98f", "5ce65821fd9b330001c4a95b", "687e58fb85bceab1aeb444a1", "5d7f8cc2acc4700001253d9e",
    "5a77491150157200046f1f10", "6718fcd635dc8ff4d578a4be", "65e82d7a7edafe5463a156e3", "65e82e735f06baf8e05114cb", "5ece5e7d1f826cd347302259",
    "5d0b85e6eb66850001856d2d", "5be3f1662201b20012a3a4d7", "5f917a2a8012acc135c0857f", "5bcec8fd9c50285679ac15ab", "5bcec8fd9c50285679ac15ab",
    "603e266ed60f7fbf004162a4", "5bdaa8ae13fd4900121665c3", "5bdaa8ae13fd4900121665c3", "6a1d350d681590b6d7a26967", "6a1d33d45586f57349a1bbcd",
    "6a2be0e84854d9ca4961b074", "55e6bdd04ef8d40c00d1f91d", "55e6bdd04ef8d40c00d1f91d", "646b17797205b11bdfd82f32", "66290003d6689d34c4ab33ff",
    "66290016dcce83c532e55614", "669a4bf025d9d706a58b3b1d", "68b9a98956e641b8a3a23171", "5832ce9554857e00041652dd", "586b9b30aabf9a0004bb61db",
    "5ce6580ea72a950001cc8731", "5ceae038c461e70001cc9808", "5fe9910568293a8eb7677fb4", "69c678588058f96531c8f895", "69c678588058f96531c8f895",
    "69c67ab70f7b32a680abca15", "69c67ab70f7b32a680abca15", "5ced482d4a8a2a000137da66", "5e1c81e902950a878691f4da", "68e3c5e457a6a7d03039ff0f",
    "68e3c5d95096e9b96cbe91fe", "68e3c5cd9f493b47d7ac7923", "644a332524ef892c8d86302c", "61a8cee952b1ab8366c7e083", "5c5b04940de01d0001042350",
    "5f8380543eb6546a2775d008", "5f837de6582f37118b62e334", "5ced482dd349d10001e70539", "559fef68f462100c00461dbf", "55db3bc6f9e1c10c004359a4",
    "5af1bda786fbaa0004940d21", "677bc5135595d03cea8c6375", "6899fb8557a6b9902291f92d", "69833eb141a48959a6b211ff", "682c7d96554fd7170d6c9208",
    "66a89b3d923fc4af24a2c35a", "6751bda332b7492b09cbbef1", "6598198a2263a29cebd6bb6e", "61b855644ab266cfd20e9701", "5ce6581efd9b330001c4a8dc",
    "5cfe32bd010040000122ff01", "5cfe32bd4a644b0001f2076c", "61aa0605dfbac2350e5a8789", "61aa03f98da8b7b9d43e97aa", "61a9d146aece7874eed6fb01",
    "61a9d146aece7874eed6fb01", "5df76c8566d8c9523cefbb6e", "5f18366211699086a99af632", "68e3ca71f78246e0456bb12e", "6053b855b1eb6d22404024e7",
    "6053b68ca5c963515dd585e7", "61b855644ab266cfd20e9701", "61b855644ab266cfd20e9701", "6a3e282b1da5da2520a996ef"
]
DOKUNULMAYACAK_GB = [
    "6304b87e6c7c1a0eea79e01e",'68eebd7a954e72282a317742', '5a86e06e1bc08f0004e03d3c', '659fd658bcb190b663090924', '69e75b1a136b03d799db0067', '641aa78085669d26f616f639', '659bae102263a29cebd6d8b8',
    "5d03bb6836e4a5000117bc05", "566031ffbd8dab0c00937b60", "67d4180189839628639fe27b", "5ced4831d349d10001e7056d", "559eb7770fdb080c004d5e86",
    "5e6752bc9769bdd390e9bd43", "5b0d61b3d3d3a30004143c1f", "67c843eff2f69d9e48fda8fb", "674719692acf245bd5b29a31", "686e6c89b2b18e64d3fa1e7b",
    "68de4052d83aaeab6a49cad9", "566031ffbd8dab0c00937b60", "5ce65818fd9b330001c4a83e", "63bc88bd8ee27c71e0262e3d", "676be35f6703a6e01f7e5451",
    "6551d69ba6df391007a8ed94", "6551dc761d6c1393a82cdb2c", "679394c6f101c372faf1d5d0", "61b857e146223b635dd15093", "6a207194703e87cccb928598",
    "67ceab4611fb0e9878fc27f1", "69e0b88ec4612d10e9038cbb", "657aae4913824a2781982d04", "5cf3d88e4b58210001f49589", "5f199bfc9e35ab6255dd54ca",
    "5bf52908dbaa09001e0dc38e", "69286088c5030bc5033ff0c2", "659f8af17209dcdf6f55bf19", "69aadcc38fdd2522e5cd9858", "690b528b21cce36b2c81b51a",
    "6357833dc34265258cdbac4f", "5ce6581bfd9b330001c4a86e", "5ced482dd349d10001e70531", "59b14d42b573340004d1a143", "5ffedcff77087ac471423262",
    "68c26a2f1075ad41144fcf3b", "5fcdedfc86e43d58746d088b", "643ed6ffdf131ce61d75b34a", "66ce1fbb018b348c16da46a3", "66c863aedce6579e03808830",
    "68c00c42fee7cff283e81b12", "68c00c4fcbbd9a61e6301aff", "698c8a3fe4ea862ac9c8ab99", "64147c8c85669d48b316f147", "64147fd067770dec987ff30e",
    "643fa671fc5403d002d62350", "659bae35faa4a09339b3549b", "65605f1534786890599f4373", "6a05836f27346683da1a670a", "657b6a8154900b665b129187",
    "657b6a8154900b665b129187", "657af432cd1d369cc1390ad2", "657af432cd1d369cc1390ad2", "67daa2aa81a2af09e085ffd2", "67daa2b4e52f5a010638c7fe",
    "67daa2be441b02fd37a85911", "5598305cb1dc700c006a716c", "5598305cb1dc700c006a716c", "68711c6b05682ca49ade0362", "69809555a799e9ccceb19b46",
    "67a07095d54440dd9b8b3449", "6a271ad057c2a50d81830ef0", "6a271bd79289b9c298118264", "69c2e079a6168f0a8b0e0921", "5f563f662dbc894a26f92751",
    "5f359bce8a7a31ef61b95843", "5f356181250d5b1e97215279", "58997315d5b34d0004dd1ea3", "65f2a21498ee5ae3585a6819", "69de335d32e5f8d5ff4fc923",
    "58c6bb56de58040004b73923", "58fa20e19fc5e500045db0e7", "63ef44f653b7f99ca9293490", "5c093f615123490012276a09", "55a0215035a77b0c0075d119",
    "5f8c9aece2314c8414d6925c", "55db3c1ef9e1c10c004359c5", "5c8a822ac7606200016727c4", "64f96d1b039ec2add029a6cb", "55db3bc6f9e1c10c004359a4",
    "6351c7a13c49257f41ca730c", "6351c91e79b138c10d9e283a", "6351cc053c4925913dca7314", "6a326b78ca2d308f17585e6c", "6540f88b304475ff07e4eb87",
    "5e3d3dd5501bd710c6579139", "65a1333bc037b3e6ca0fd87e", "6a4b6557bc5849c0a15b76a6", "6a4b66886d3ac6e4538ac959", "69fb36afff62e218967941c3",
    "625fed3f8caa81533f437b08", "69dc0c8aebefb62069af9375", "67ed4090872fefbc98463874", "63d764acb720ef4bc992727f", "69dc0581911e496d45bd2362",
    "63f47d563816f75dab83fde7", "69833e937c2aebf3776e9dc4", "69833ea38f70bdce80ad0b62", "620525660fb325c18f2efc7c", "5cfe32bd010040000122ff12",
    "6756e78c8faacd82448d7995", "6a60c4b42de7e8a9d8f835fb", "6749b9bf55e8047429dbaf5a", "6749b9cdfb43fb8c04083b38", "6749b9d7b4706e767348b7c2",
    "682498ae82e6fc33dd1fcdc9", "68a4688f54216a186e970748", "6a353e8fd4831d6f114f1328", "6a353d62bd9c8470e737905d", "5cb8cafe69c3750001041dc2",
    "5ad5ac51c8feb3000491d2d5", "559831ecb1dc700c006a71b4", "5f0d6f9c9ec8533e2c3c8893", "5be3da81d0dba200184744de", "64354b20c04f5ac81def2651",
    "64354b7108547f39490b18ee", "64354c84704364e0f00f668b", "64f82e4ab001cfc9fe331bc3", "671221411e3cc0605a9615ba", "69e735a07fd9d667c12e11cf",
    "69e736cc45c39707c3b2a219"
]

# G10 gibi ayrışmış (ETB/Other ayrı havuz) muamele gören GB depoları (yeni sistem)
G10_TIPI_DEPOLAR = ['GaziemirBüyük', 'SuadiyeBüyük']

# Yerel dosya yolları
DOSYA_RELEX     = '/content/izmir +4 1509 sıfırsız.xlsx'
DOSYA_BACKLOG   = '/content/+4 Backlog format copy.xlsx'

# 📋 GSheet Ayarları
SPREADSHEET_ID    = '1FArHRLZdwrXcOHOHCK3skES7xGSPABNEm97jIK8H64E'
BUFFER_GID        = '1173976478'   # "Buffer Rates": Depo Adı | Ambient Buffer | Cold Limit → Cold 'Cold Limit' kolonunu kullanır
ORAN_GID          = '2106866758'
POOLED_GID        = '108896607'    # pooled doluluk (long format)
SLOT_GID          = '370075811'    # Slot Saati verisi
URUN_HACIM_GID    = '1098615637'   # 🔀 v3: ürün hacim verisi (long format)
KAMPANYA_GID      = '1527796592'   # 🎯 "Dokunulmayacak Ürünler (Kampanya)": G10 T-1 | GB T-1 | G10 T | GB T

GSHEET_BASE              = f'https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid='
GSHEET_BUFFER_URL        = GSHEET_BASE + BUFFER_GID
GSHEET_ORAN_URL          = GSHEET_BASE + ORAN_GID
GSHEET_POOLED_URL        = GSHEET_BASE + POOLED_GID
GSHEET_SLOT_URL          = GSHEET_BASE + SLOT_GID
GSHEET_URUN_HACIM_URL    = GSHEET_BASE + URUN_HACIM_GID
GSHEET_KAMPANYA_URL      = GSHEET_BASE + KAMPANYA_GID

# 🔀 Ürün hacim sheet ayarı — etiket "m3" ama değer LİTRE (11.5×1.7×2.5 cm = 0.048875 L)
URUN_HACIM_MEASURE = 'Max. Product Volume m3'

# 📋 SAYIM PLANI SHEET'İ (Tarih, Tarih Açıklama, Depo Kodu, Depo Tipi, Sayım Türü ...)
SAYIM_SPREADSHEET_ID = 'https://docs.google.com/spreadsheets/d/1FArHRLZdwrXcOHOHCK3skES7xGSPABNEm97jIK8H64E/edit?gid=1468314948#gid=1468314948'   # <-- Sayım planı spreadsheet ID'si (linkteki /d/ ile /edit arası)
SAYIM_GID            = '1468314948'   # <-- Sayım sekmesinin GID'i

# 📦 DEPO BAZLI MAKSİMUM TOPLAM SİPARİŞ ADEDİ (tüm ürünlerin toplamı bu sayıyı geçemez)
#    Depo adı Türkçe karakter / boşluk duyarsız eşleşir.
DEPO_ADET_LIMITI = {
    'Acıbadem Büyük': 765,
}

# 🧪 SADECE A TESTİ (20.11.2026) — bu depolara yalnız ABC class 'A' ürünler gider; B/C/D (ve sınıfı boş) en baştan sıfır.
#    Dokunulmazlık (kampanya/waste) uygulanmaz, yalnız dolap hacmi kesim yapar: merkez satır limiti ve depo adet
#    limiti bu depoların satırlarını kesmez (satırlar merkez sayımına dahil). Sayım ve backlog blokajı geçerli.
#    Depo adı Türkçe karakter / boşluk duyarsız eşleşir.
SADECE_A_TEST_DEPOLARI = ['Atakent']
SADECE_A_REASON = 'Test: Sadece A Segmenti'

# 🎯 WEIGHTED AVA DEPOLARI (23.11.2026) — bu depolarda 99 puanı (Listed / Supply Shortage koruması) yok: bu ürünler
#    kendi ABC/cover puanına düşer, böylece kesim sırası ABC'ye paralel olur (A/B'nin 6,5/7,5 cover kuralları aynen).
#    Kampanya/Waste (100), demirbaş (101) ve Pick-to-zero (Cold, 99) korumaları sürer. Depo adı Türkçe karakter / boşluk duyarsız.
WEIGHTED_AVA_DEPOLARI = ['UrartuBüyük', 'Lara', 'Akdeniz', 'Atatürk Üniversitesi', 'ÇambaşıBüyük', 'Soyak Yenişehir', 'Acarlar',
                         'Kanlıkavak', 'KutluBüyük', 'AydoğanBüyük', 'MaslakBüyük', 'BüyükbakkalköyBüyük', 'Profilo', 'Yeniköy',
                         'Çekmeköy', 'RamanBüyük', 'İncekBüyük', 'KızılayBüyük', 'Kalkınma']

# ==========================================
# 📋 SAYIM KURALLARI (+4 / COLD FOOD) — teslimat ALINMAYACAK gün aralığı
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

# 🔀 Slot sheet kolon adları
SLOT_COL_DURUM = 'Durum'
SLOT_COL_ID    = 'Depo ID'
SLOT_COL_BAYI  = 'Bayi Adı'
SLOT_COL_TUR   = 'Tür'
SLOT_COL_BITIS = 'Slot Saati Bitiş'
SLOT_HEDEF_TURLER = ['frigo', 'çift rejim', 'cift rejim']   # Ambient hariç
SLOT_OGLE_SINIRI_DK = 720   # 12:00

# 🚚 Transfer sheet — Relex çıktısında merkez depo ID'si yok → boş bırakılıyor
TRANSFER_FROM_WAREHOUSE = ''

if URUN_HACIM_GID == 'BURAYA_GID':
    raise ValueError("URUN_HACIM_GID ayarlanmadı — ürün hacim sheet'inin gid'ini AYARLAR bölümüne yaz.")

print("+4 Verileri yükleniyor...")
start_time = time.time()

# ==========================================
# 📥 VERİ OKUMA FONKSİYONLARI
# ==========================================
def read_and_clean_excel(path):
    d = pd.read_excel(path)
    d.columns = [str(c).strip() for c in d.columns]
    return d

def clean_locale_number(val):
    """Avrupa formatı ('1.009,73') — buffer/oran GSheet'leri için."""
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val = str(val).strip().replace('.', '').replace(',', '.')
    try:
        return float(val)
    except Exception:
        return 0.0

def parse_pooled_number(val):
    """US formatı ('1,009.73') — pooled GSheet için."""
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(' ', '').replace('\u00a0', '').replace('%', '')
    if s == '' or s.lower() in ['nan', 'null', 'none', '-', 'total', 'toplam']:
        return np.nan
    s = s.replace(',', '')
    try:
        return float(s)
    except Exception:
        return np.nan

def parse_hacim_sayi(val):
    """'0.048875' / '0,048875' / '1,234.5' / '1.234,5' -> float"""
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(' ', '').replace('\u00a0', '')
    if not s:
        return np.nan
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.') if s.rfind(',') > s.rfind('.') else s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return np.nan

def read_gsheet_csv(url, thousands=None, dtype=None):
    d = pd.read_csv(url, thousands=thousands, dtype=dtype)
    d.columns = [str(c).strip() for c in d.columns]
    return d

def norm(s):
    return str(s).lower().replace(" ", "").replace("'", "")

def urun_hacim_gsheet_hazirla(df_long, measure_adi):
    """Long format ürün sheet'i → marketproduct_id | hacim2 (litre)."""
    _pc     = {c: c.lower().replace(' ', '').replace('_', '') for c in df_long.columns}
    c_id    = next((c for c in df_long.columns if _pc[c] in ('productid', 'marketproductid')), None)
    c_mname = next((c for c in df_long.columns if 'measure' in _pc[c] and 'name' in _pc[c]), None)
    c_mval  = next((c for c in df_long.columns if 'measure' in _pc[c] and 'val' in _pc[c]), None)
    if None in (c_id, c_mname, c_mval):
        raise ValueError(f"Ürün hacim sheet'inde Product ID / Measure Names / Measure Values yok: "
                         f"{df_long.columns.tolist()}")

    d = df_long[df_long[c_mname].astype(str).str.strip().str.lower() == measure_adi.lower()].copy()
    if d.empty:
        raise ValueError(f"'{measure_adi}' satırı bulunamadı. Mevcut measure'lar: "
                         f"{df_long[c_mname].astype(str).str.strip().unique()[:20].tolist()}")

    d['marketproduct_id'] = d[c_id].astype(str).str.strip().str.lower()
    d['hacim2']           = d[c_mval].apply(parse_hacim_sayi)

    _farkli = d.groupby('marketproduct_id')['hacim2'].nunique()
    _farkli = _farkli[_farkli > 1]
    if len(_farkli):
        print(f"  ⚠️  {len(_farkli)} üründe farklı hacim değerli birden fazla satır (storage type?) "
              f"→ MAX alınıyor. Örnek: {_farkli.index[:3].tolist()}")

    out = d.groupby('marketproduct_id', as_index=False)['hacim2'].max()
    print(f"  ✅ Ürün hacmi GSheet: {len(out)} ürün | boş: {int(out['hacim2'].isna().sum())} | "
          f"≤0: {int((out['hacim2'] <= 0).sum())}")
    return out

# ==========================================
# 📥 DOSYALARI YÜKLE
# ==========================================
df_relex_raw   = read_and_clean_excel(DOSYA_RELEX)
df_backlog_raw = read_and_clean_excel(DOSYA_BACKLOG)

print("GSheet'ten Buffer Rate, Kapasite Oranları, Pooled, Slot ve Ürün Hacmi çekiliyor...")
df_buffer_raw        = read_gsheet_csv(GSHEET_BUFFER_URL)
df_oran_raw          = read_gsheet_csv(GSHEET_ORAN_URL)
df_pooled_raw        = read_gsheet_csv(GSHEET_POOLED_URL)
df_slot_raw          = read_gsheet_csv(GSHEET_SLOT_URL)
df_urun_raw          = read_gsheet_csv(GSHEET_URUN_HACIM_URL, dtype=str)
df_kampanya_raw      = read_gsheet_csv(GSHEET_KAMPANYA_URL, dtype=str)

# 🎯 KAMPANYA ÜRÜNLERİ (dokunulmayacak, sheet'ten otomatik)
# Sekme her perşembe güncellenir: T = önümüzdeki haftanın (pazartesi başlayan) kampanyaları, T-1 = içinde bulunulan haftanınkiler.
# +4 N+1 çalışır: perşembe siparişi cuma iner (kampanya haftası sürüyor) → perşembe T-1, diğer günler T.
# DOKUNULMAYACAK_G10/GB (arayüzden elle) = Waste. İkisi de 100 puan; ikisinde de olan ürün 'Kampanya'.
def kampanya_listeleri(k):
    """Kampanya sekmesi → {('G10' | 'GB', 'T' | 'T-1'): {ürün kodu (küçük harf)}}; '-' ve boşlar atlanır."""
    kol = {re.sub(r'\s+', ' ', str(c)).strip().upper(): c for c in k.columns}
    out = {}
    for dom in ('G10', 'GB'):
        for hafta in ('T-1', 'T'):
            c = kol.get(f'{dom} {hafta}')
            if c is None:
                print(f"   ⚠️  Kampanya sekmesinde '{dom} {hafta}' kolonu yok → boş sayıldı")
                continue
            out[(dom, hafta)] = {str(x).strip().lower() for x in k[c].dropna()
                                 if re.fullmatch(r'[0-9a-fA-F]{24}', str(x).strip())}
    return out

KAMPANYA_LISTELERI = kampanya_listeleri(df_kampanya_raw)
KAMPANYA_HAFTA = 'T-1' if pd.Timestamp.now().weekday() == 3 else 'T'
print(f"🎯 Kampanya listesi ({KAMPANYA_HAFTA}{', perşembe' if KAMPANYA_HAFTA == 'T-1' else ''}): "
      f"G10 {len(KAMPANYA_LISTELERI.get(('G10', KAMPANYA_HAFTA), ()))}, GB {len(KAMPANYA_LISTELERI.get(('GB', KAMPANYA_HAFTA), ()))} ürün")
df_urun              = urun_hacim_gsheet_hazirla(df_urun_raw, URUN_HACIM_MEASURE)

# ==========================================
# 📥 BUFFER RATE İŞLEME
# ==========================================
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
df_buffer.rename(columns={depo_col: 'Location name', buffer_col: 'buffer_rate'}, inplace=True)
df_buffer['Location name'] = df_buffer['Location name'].astype(str).str.strip()
df_buffer['buffer_rate'] = df_buffer['buffer_rate'].map(buffer_sayi)
df_buffer = df_buffer.dropna(subset=['buffer_rate'])
_buf_cakisan = df_buffer.groupby('Location name')['buffer_rate'].nunique()
if (_buf_cakisan > 1).any():
    print(f"   ⚠️  Buffer Rates'te farklı değerle tekrarlanan depolar (ilki alındı): {_buf_cakisan[_buf_cakisan > 1].index.tolist()}")
df_buffer = df_buffer.drop_duplicates(subset=['Location name'])
print(f"📐 +4 buffer (Buffer Rates → '{buffer_col}'): {len(df_buffer)} depo · sheet'te olmayan depolara %{PLUS_4_USABLE_RATIO * 100:g}")

# ==========================================
# 📥 KAPASİTE ORANLARI İŞLEME
# ==========================================
df_oran = df_oran_raw.rename(columns={df_oran_raw.columns[0]: 'Location name'}).copy()
etb_col    = next((c for c in df_oran.columns if 'etb' in c.lower().replace(' ', '')), None)
other4_col = next((c for c in df_oran.columns if 'other' in c.lower()), None)

if etb_col is None or other4_col is None:
    raise ValueError(f"Oran GSheet'inde ETB veya Other kolonu bulunamadı. Mevcut kolonlar: {df_oran.columns.tolist()}")

df_oran = df_oran[['Location name', etb_col, other4_col]].copy()
df_oran.rename(columns={etb_col: 'etb_oran', other4_col: 'other4_oran'}, inplace=True)
df_oran['etb_oran']    = df_oran['etb_oran'].apply(clean_locale_number)
df_oran['other4_oran'] = df_oran['other4_oran'].apply(clean_locale_number)
df_oran.loc[df_oran['other4_oran'] == 0, 'other4_oran'] = np.nan
df_oran.loc[df_oran['etb_oran']    == 0, 'etb_oran']    = np.nan
df_oran = df_oran.drop_duplicates(subset=['Location name'])

# ==========================================
# 🔀 SLOT SAATİ — öğlen 12:00 ve öncesi biten Frigo/Çift Rejim slotları
# Kural: bu depolarda lead time sonrası günün FORECAST_LOOKAHEAD_RATIO kadar
# "boşalacak" varsayımı UYGULANMAZ (faktör 0 kabul edilir).
# Eşleştirme "Depo ID" ↔ Relex "Location code" üzerinden yapılır (depo adı DEĞİL).
# ==========================================
def parse_slot_saat_dk(val):
    """'15:00' / '15:00:00' / '3:00:00 PM' -> dakika. Parse edilemiyorsa NaN."""
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
    raise ValueError(f"Slot GSheet'inde beklenen kolonlar yok: {_slot_eksik} | "
                     f"mevcut kolonlar: {df_slot.columns.tolist()}")

if SLOT_COL_DURUM in df_slot.columns:
    _slot_onceki = len(df_slot)
    df_slot = df_slot[df_slot[SLOT_COL_DURUM].astype(str).str.strip().str.lower() == 'aktif'].copy()
    print(f"  Slot: {len(df_slot)}/{_slot_onceki} satır 'Aktif'")

df_slot['Slot_Depo_ID'] = df_slot[SLOT_COL_ID].astype(str).str.strip().str.lower()
df_slot['Tur_Norm']     = df_slot[SLOT_COL_TUR].astype(str).str.strip().str.lower()
df_slot['Bitis_Dk']     = df_slot[SLOT_COL_BITIS].apply(parse_slot_saat_dk)

slot_frigo = df_slot[df_slot['Tur_Norm'].isin(SLOT_HEDEF_TURLER)].copy()
print(f"  Slot: {len(slot_frigo)} Frigo/Çift Rejim satırı "
      f"(tür dağılımı: {df_slot['Tur_Norm'].value_counts().to_dict()})")

_slot_parse_fail = int(slot_frigo['Bitis_Dk'].isna().sum())
if _slot_parse_fail:
    print(f"  ⚠️  {_slot_parse_fail} Frigo/Çift Rejim satırında bitiş saati parse EDİLEMEDİ "
          f"→ bu depolar 1/3 düşüşünü ALMAYA DEVAM edecek! Örnek: "
          f"{slot_frigo.loc[slot_frigo['Bitis_Dk'].isna(), SLOT_COL_BITIS].unique()[:5]}")

# Aynı depo için birden fazla satır varsa en erken bitişi baz al (muhafazakar)
slot_depo_bitis = (
    slot_frigo.dropna(subset=['Bitis_Dk'])
    .groupby('Slot_Depo_ID')['Bitis_Dk'].min()
)
depo_ogle_oncesi_ids = set(
    slot_depo_bitis[(slot_depo_bitis > 0) & (slot_depo_bitis <= SLOT_OGLE_SINIRI_DK)].index
)
print(f"  ✅ Slot Saati: {len(slot_depo_bitis)} depo parse edildi, bunlardan "
      f"{len(depo_ogle_oncesi_ids)} tanesi öğlen 12:00 ve öncesi bitiyor "
      f"→ 1/3 lookahead düşüşü uygulanmayacak")

# Raporlama için yardımcı sözlükler
slot_bitis_dk_map = slot_depo_bitis.to_dict()
slot_id_ad = {}
if SLOT_COL_BAYI in slot_frigo.columns:
    slot_id_ad = (slot_frigo.drop_duplicates('Slot_Depo_ID')
                  .set_index('Slot_Depo_ID')[SLOT_COL_BAYI]
                  .astype(str).str.strip().to_dict())

def _dk_to_saat(dk):
    if pd.isna(dk):
        return ''
    dk = int(dk)
    return f"{dk // 60:02d}:{dk % 60:02d}"

# ==========================================
# 📥 PLUS4 SÜTUN SEÇİMİ — İKİ AYRI KAYNAK
# ==========================================
DEPO_ADI_HEDEF = 'Depo: Depo Adı'

PLUS4_HEDEF_YENI = [
    "ETB' Volume Litre", "ETB' In Transit Volume Litre",
    "ETB' Volume Litre (frc t)", "ETB' Volume Litre (frc t+1)", "ETB' Volume Litre (frc t+2)",
    'Other +4 & MS +4 Volume Litre', 'Other +4 & MS +4 In Transit Volume Litre',
    'Other +4 & MS +4 Volume Litre (frc t)', 'Other +4 & MS +4 Volume Litre (frc t+1)', 'Other +4 & MS +4 Volume Litre (frc t+2)',
    'DC ETB Volume Litre', 'DC ETB In Transit Volume Litre',
    'DC ETB Volume Litre (frc t)', 'DC ETB Volume Litre (frc t+1)', 'DC ETB Volume Litre (frc t+2)',
    'All MS +4 Volume Litre', 'All MS +4 In Transit Volume Litre',
    'All MS +4 Volume Litre (frc t)', 'All MS +4 Volume Litre (frc t+1)', 'All MS +4 Volume Litre (frc t+2)',
    'Max. ETB WH Volume', 'Max. Other +4 & MS +4 WH Volume',
]

# ==========================================
# 🔀 POOLED DOLULUK VERİSİ — GSHEET (long format → pivot)
# ==========================================
def pooled_gsheet_hazirla(df_long, hedefler, kaynak_adi, bos_sifir=True, storagetype=None):
    _pc      = {c: c.lower() for c in df_long.columns}
    c_depo   = next((c for c in df_long.columns if 'depo' in _pc[c]), None)
    c_mname  = next((c for c in df_long.columns if 'measure' in _pc[c] and 'name' in _pc[c]), None)
    c_mval   = next((c for c in df_long.columns if 'measure' in _pc[c] and 'val'  in _pc[c]), None)
    c_date   = next((c for c in df_long.columns if _pc[c].strip() in ('x', 'date', 'tarih', 'row updated at')), None)
    c_sttype = next((c for c in df_long.columns if 'storagetype' in _pc[c].replace(' ', '')), None)

    if c_depo is None or c_mname is None or c_mval is None:
        raise ValueError(f"{kaynak_adi}: Depo / Measure Names / Measure Values kolonları bulunamadı: "
                         f"{df_long.columns.tolist()}")
    print(f"  ✅ {kaynak_adi} kolonları → depo:'{c_depo}' | isim:'{c_mname}' | "
          f"değer:'{c_mval}' | tarih:'{c_date}'")

    d = df_long.copy()

    # İstenirse yalnız belirli storagetype satırları (ör. coldfood sheetinde '+4')
    if storagetype is not None and c_sttype is not None:
        _st = d[c_sttype].astype(str).str.strip()
        if (_st == storagetype).any():
            d = d[_st == storagetype].copy()

    # Sadece en güncel snapshot
    if c_date is not None:
        d['_ts'] = pd.to_datetime(d[c_date], errors='coerce')
        if d['_ts'].notna().any():
            son_ts  = d['_ts'].max()
            son_gun = son_ts.normalize()
            onceki  = len(d)
            d = d[d['_ts'].dt.normalize() == son_gun].copy()
            print(f"  ✅ {kaynak_adi} snapshot: {son_ts:%Y-%m-%d %H:%M} → {len(d)}/{onceki} satır")
            gun_farki = (pd.Timestamp.now().normalize() - son_gun).days
            if gun_farki > 0:
                print(f"  ⚠️  DİKKAT: {kaynak_adi} verisi BUGÜNE AİT DEĞİL ({gun_farki} gün eski)!")

    d['_depo']  = d[c_depo].astype(str).str.strip()
    d['_mname'] = d[c_mname].astype(str).str.strip()
    d['_mval']  = d[c_mval].apply(parse_pooled_number)
    d = d[~d['_depo'].str.lower().isin(['', 'nan', 'none'])].copy()   # depo adı boş satırlar (genel toplam) atılır

    _dup = d.groupby(['_depo', '_mname'])['_mval'].nunique()
    _dup_farkli = _dup[_dup > 1]
    if len(_dup_farkli) > 0:
        print(f"  ⚠️  {len(_dup_farkli)} depo-measure kombinasyonunda FARKLI değerli birden fazla satır "
              f"(muhtemelen storagetype kırılımı) → ilk satır alınıyor. Örnek: {_dup_farkli.index[:3].tolist()}")
        if c_sttype is not None:
            print(f"      storagetype dağılımı: "
                  f"{d[c_sttype].astype(str).str.strip().value_counts().to_dict()}")

    wide = (d.dropna(subset=['_mname'])
              .pivot_table(index='_depo', columns='_mname', values='_mval', aggfunc='first')
              .reset_index()
              .rename(columns={'_depo': 'Location name'}))
    wide.columns.name = None
    print(f"  ✅ {kaynak_adi} pivot: {len(wide)} depo × {len(wide.columns) - 1} measure")

    _wide_norm = {norm(c): c for c in wide.columns if c != 'Location name'}
    out = pd.DataFrame({'Location name': wide['Location name']})

    bulunamayan = []
    for hedef in hedefler:
        kaynak = _wide_norm.get(norm(hedef))
        if kaynak is None:
            bulunamayan.append(hedef)
            out[hedef] = np.nan       # 0 DEĞİL — Doluluk kontrolü yanlış True olmasın
        else:
            out[hedef] = pd.to_numeric(wide[kaynak], errors='coerce')
            if bos_sifir:
                out[hedef] = out[hedef].fillna(0.0)

    if bulunamayan:
        print(f"⚠️  {kaynak_adi} kaynağında BULUNAMAYAN kolonlar ({len(bulunamayan)} adet): {bulunamayan}")
        print(f"    Sheet'teki mevcut measure isimleri: "
              f"{sorted([c for c in wide.columns if c != 'Location name'])}")

    return out

df_plus4      = pooled_gsheet_hazirla(df_pooled_raw, PLUS4_HEDEF_YENI, "Pooled GSheet (yeni sistem)")

# ==========================================
# 📥 RELEX SÜTUN HAZIRLIĞI
# ==========================================
# Parti büyüklüğü diğer kodlarla aynı adla okunur: 'Order batch size'. Eski exportlardaki Batch size adı da kabul edilir.
if 'Order batch size' not in df_relex_raw.columns:
    _obs = next((c for c in df_relex_raw.columns if str(c).strip().lower() in ('order batch size', 'batch size')), None)
    if _obs is not None:
        df_relex_raw = df_relex_raw.rename(columns={_obs: 'Order batch size'})
# Relex '14 Days Sales' (son 14 günlük satış, adet): ana çıktıya taşınır, arayüzdeki büyük öneri uyarısı kullanır. Kesime girmez.
_c14 = next((c for c in df_relex_raw.columns if ' '.join(str(c).lower().split()) == '14 days sales'), None)
if _c14 is not None:
    df_relex_raw = df_relex_raw.rename(columns={_c14: '14 Days Sales'})
    df_relex_raw['14 Days Sales'] = pd.to_numeric(df_relex_raw['14 Days Sales'], errors='coerce')
relex_cols = ['Product code', 'Product name', 'Location code', 'Location name', 'Domain Type',
              'Order batch size', 'End balance', 'Open purchase orders', 'Effective quantity',
              'Delivery date', 'Daily FC', 'ABC class', 'Custom category',
              'Custom sub-category', 'Son 14 Günlük Bulunurluk', 'Segment', 'Pick-to-zero',
              'Reference spoiling time', '14 Days Sales']
df_relex = df_relex_raw[[c for c in df_relex_raw.columns if any(k in c for k in relex_cols)]].copy()
df_relex['Product code'] = df_relex['Product code'].astype(str).str.lower().str.strip()

if 'Location code' not in df_relex.columns:
    raise ValueError("Relex dosyasında 'Location code' kolonu yok — slot eşleştirmesi yapılamaz.")

# DUPLİKELERİ ENGELLE
df_urun = df_urun.drop_duplicates(subset=['marketproduct_id'])
df_plus4 = df_plus4.drop_duplicates(subset=['Location name'])
df_backlog_sade = df_backlog_raw.groupby('Location name').agg({'Backlog_Palet_Sayisi': 'max'}).reset_index()

# MERGE
df_urun['marketproduct_id'] = df_urun['marketproduct_id'].astype(str).str.lower().str.strip()
df = pd.merge(df_relex, df_urun[['marketproduct_id', 'hacim2']], left_on='Product code', right_on='marketproduct_id', how='left')
df = pd.merge(df, df_backlog_sade, on='Location name', how='left')
df = pd.merge(df, df_oran, on='Location name', how='left')
df = pd.merge(df, df_buffer, on='Location name', how='left')

# ==========================================
# 🔧 DEFAULT DEĞERLER
# ==========================================
df['Domain Type'] = df['Domain Type'].fillna('GB')
is_g10 = df['Domain Type'] == 'G10'

df['etb_oran'] = np.where(
    df['etb_oran'].isna() & is_g10, G10_DEFAULT_ETB_ORAN,
    np.where(df['etb_oran'].isna() & ~is_g10, GB_DEFAULT_ETB_ORAN, df['etb_oran'])
)
df['other4_oran'] = np.where(
    df['other4_oran'].isna() & is_g10, G10_DEFAULT_OTHER4_ORAN,
    np.where(df['other4_oran'].isna() & ~is_g10, GB_DEFAULT_OTHER4_ORAN, df['other4_oran'])
)
df['buffer_rate'] = df['buffer_rate'].fillna(PLUS_4_USABLE_RATIO)
df['hacim2'] = df['hacim2'].fillna(0)

# ==========================================
# 🔀 SLOT BAYRAĞI — Depo ID (slot sheet) ↔ Location code (Relex)
# ==========================================
df['Location_Code_Clean']    = df['Location code'].astype(str).str.strip().str.lower()
df['Slot_Ogle_Oncesi_Biten'] = df['Location_Code_Clean'].isin(depo_ogle_oncesi_ids)
df['Slot_Bitis_Dk']          = df['Location_Code_Clean'].map(slot_bitis_dk_map)
df['Slot_Bitis_Saati']       = df['Slot_Bitis_Dk'].apply(_dk_to_saat)

# 🔀 Satır bazında uygulanacak lookahead faktörü
df['Lookahead_Faktor'] = np.where(
    df['Slot_Ogle_Oncesi_Biten'].fillna(False).astype(bool), 0.0, FORECAST_LOOKAHEAD_RATIO
)

_relex_ids       = set(df['Location_Code_Clean'].dropna().unique())
_slot_eslesen    = depo_ogle_oncesi_ids & _relex_ids
_slot_eslesmeyen = depo_ogle_oncesi_ids - _relex_ids
_slot_bayrakli   = df[df['Slot_Ogle_Oncesi_Biten']]['Location name'].nunique()
print(f"  Slot eşleşme: {len(_slot_eslesen)}/{len(depo_ogle_oncesi_ids)} depo ID Relex'te bulundu "
      f"→ {_slot_bayrakli} depo bayraklandı")
if _slot_eslesmeyen:
    print(f"  ⚠️  Slot'ta öğlen öncesi olup Relex'te bulunamayan {len(_slot_eslesmeyen)} depo: "
          f"{[slot_id_ad.get(i, i) for i in sorted(_slot_eslesmeyen)][:10]}")
if _slot_bayrakli == 0 and depo_ogle_oncesi_ids:
    print("  ❌ DİKKAT: Slot listesi dolu ama HİÇBİR depo bayraklanmadı — "
          "Depo ID formatı Location code ile uyuşmuyor olabilir.")

# ==========================================
# 📋 SAYIM KISITI — sayım planı okunur, teslimat günü yasak aralığa düşen depolar işaretlenir
# ==========================================
bugun = pd.Timestamp.now().normalize()
SAYIM_KAYITLARI = {}   # depo kodu -> [sayım kayıtları]
df_sayim = pd.DataFrame()
if not (SAYIM_SPREADSHEET_ID and SAYIM_GID):
    print("🚨 SAYIM PLANI LİNKİ GİRİLMEMİŞ → sayım kısıtı UYGULANMAYACAK!")
else:
    try:
        df_sayim = read_gsheet_csv(
            f'https://docs.google.com/spreadsheets/d/{SAYIM_SPREADSHEET_ID}/export?format=csv&gid={SAYIM_GID}',
            dtype=str
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
        _relex_tip = (df.drop_duplicates('Location_Code_Clean')
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
if 'Delivery date' not in df.columns:
    print("🚨 Relex'te 'Delivery date' kolonu yok → sayım kısıtı kontrol EDİLEMEZ!")
    df['Delivery date'] = pd.NaT
_tes = pd.to_datetime(df['Delivery date'], dayfirst=True, errors='coerce').dt.normalize()
df['Teslimat_Tarihi'] = _tes.groupby(df['Location name']).transform('min')
_tes_farkli = _tes.groupby(df['Location name']).nunique()
if (_tes_farkli > 1).any():
    print(f"   ⚠️  Birden fazla teslimat tarihi olan {int((_tes_farkli > 1).sum())} depo → en erken tarih alındı: "
          f"{_tes_farkli[_tes_farkli > 1].index.tolist()[:10]}")

df['Sayim_Kisiti']  = False
df['Sayim_Bilgisi'] = ''
_sayim_rapor   = []
_tarihsiz_depo = []
_bir_gun = pd.Timedelta(days=1)

for _depo, _g in df.groupby('Location name'):
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
        df.loc[_g.index, 'Sayim_Kisiti']  = True
        df.loc[_g.index, 'Sayim_Bilgisi'] = (f"{_engel['T'].strftime('%d.%m')} {_engel['aciklama']} "
                                             f"({_engel['tip']} {_engel['tur']})")
if _tarihsiz_depo:
    print(f"   🚨 Sayımı olan ama Relex teslimat tarihi BOŞ olan {len(_tarihsiz_depo)} depo kontrol EDİLEMEDİ: "
          f"{_tarihsiz_depo[:10]}")
print(f"📋 Sayım kısıtı: {df.loc[df['Sayim_Kisiti'], 'Location name'].nunique()} depo / "
      f"{int(df['Sayim_Kisiti'].sum())} satır tamamen kesilecek")

_ADET_LIMIT_NORM = {_norm_ad(k): v for k, v in DEPO_ADET_LIMITI.items()}
_adet_eslesen = set()

# ==========================================
# 🔀 KAPASİTE VERİSİ (pooled doluluk) — tüm depolar aynı sistemle (19.11.2026'dan beri eski sistem yok)
# ==========================================
df_yeni = pd.merge(df.copy(), df_plus4, on='Location name', how='left')
df_yeni.loc[df_yeni['Location name'] == 'BüyükbakkalköyBüyük', 'Max. Other +4 & MS +4 WH Volume'] = 5000

print(f"Depolar: {df_yeni['Location name'].nunique()} depo, {len(df_yeni)} satır")

# ==========================================
# 🧮 GRUPLAMA MANTIĞI — YENİ SİSTEM
# ==========================================
def identify_group_yeni(row):
    cat = str(row.get('Custom category', '')).strip()
    if cat == 'Et, Tavuk & Balık':
        return 'ETB'
    return 'Other'

df_yeni['Item_group'] = df_yeni.apply(identify_group_yeni, axis=1)

# Cover Day ve Lead Time
for d in (df_yeni,):
    temp_fc = pd.to_numeric(d['Daily FC'], errors='coerce').replace(0, np.nan)
    d['Calculated Cover Day'] = (
        (pd.to_numeric(d['End balance'], errors='coerce') +
         pd.to_numeric(d['Open purchase orders'], errors='coerce')) / temp_fc
    ).fillna(0)
    d['Delivery date'] = pd.to_datetime(d['Delivery date'], errors='coerce')
    d['Lead_Time_Days'] = (d['Delivery date'] - pd.Timestamp.now().normalize()).dt.days.clip(lower=0).fillna(0)

# ==========================================
# 🔀 ORTAK BOŞ HACİM HESABI
# ==========================================
def bos_hesapla(gunluk_degerler, lt, faktor):
    lt = int(lt) if not pd.isna(lt) else 0
    if lt <= 0:
        return 0.0, 0.0, 0.0
    n_tam = min(lt, 3)
    tam = float(np.nansum(gunluk_degerler[:n_tam]))
    ham_lookahead = float(gunluk_degerler[lt]) if lt < 3 else 0.0
    if np.isnan(ham_lookahead):
        ham_lookahead = 0.0
    return tam, ham_lookahead, tam + ham_lookahead * faktor

# ==========================================
# 💡 KAPASİTE LİMİT HESAPLAMA — YENİ SİSTEM
# ==========================================
def calculate_group_limits_yeni(row):
    lt           = row['Lead_Time_Days']
    faktor       = row['Lookahead_Faktor']
    usable_ratio = row.get('buffer_rate', PLUS_4_USABLE_RATIO)
    other4_oran  = row.get('other4_oran', GB_DEFAULT_OTHER4_ORAN)
    etb_oran     = row.get('etb_oran',    GB_DEFAULT_ETB_ORAN)
    max_pool     = row.get('Max. Other +4 & MS +4 WH Volume', 0)
    is_g10_tipi  = (row['Domain Type'] == 'G10') or (row['Location name'] in G10_TIPI_DEPOLAR)

    if row['Item_group'] == 'ETB':
        kapasite_ham = row.get('Max. ETB WH Volume', 0) if is_g10_tipi else max_pool
        oran_uyg     = etb_oran
        kapasite     = kapasite_ham * oran_uyg * usable_ratio

        mevcut  = row.get('DC ETB Volume Litre', 0)
        transit = row.get('DC ETB In Transit Volume Litre', 0)

        gunluk = [
            row.get('DC ETB Volume Litre (frc t)', 0),
            row.get('DC ETB Volume Litre (frc t+1)', 0),
            row.get('DC ETB Volume Litre (frc t+2)', 0),
        ]
    else:
        kapasite_ham = max_pool
        oran_uyg     = other4_oran
        kapasite     = kapasite_ham * oran_uyg * usable_ratio
        mevcut  = row.get('Other +4 & MS +4 Volume Litre', 0)            - row.get('All MS +4 Volume Litre', 0)
        transit = row.get('Other +4 & MS +4 In Transit Volume Litre', 0) - row.get('All MS +4 In Transit Volume Litre', 0)

        gunluk = [
            row.get('Other +4 & MS +4 Volume Litre (frc t)', 0)   - row.get('All MS +4 Volume Litre (frc t)', 0),
            row.get('Other +4 & MS +4 Volume Litre (frc t+1)', 0) - row.get('All MS +4 Volume Litre (frc t+1)', 0),
            row.get('Other +4 & MS +4 Volume Litre (frc t+2)', 0) - row.get('All MS +4 Volume Litre (frc t+2)', 0),
        ]

    tam, ham_la, bos = bos_hesapla(gunluk, lt, faktor)
    limit = kapasite - (mevcut + transit - bos)
    return pd.Series({
        'Kullanilabilir_Limit_Litre': max(0, limit),
        'Bos_Tam_Gunler_Litre':       tam,
        'Bos_Lookahead_Ham_Litre':    ham_la,
        'Bos_Toplam_Litre':           bos,
        'Kapasite_Ham_Litre':         kapasite_ham,
        'Uygulanan_Oran':             oran_uyg,
        'Uygulanan_Buffer':           usable_ratio,
        'Anlik_Stok_Litre':           mevcut,
        'Yoldaki_Transit_Litre':      transit,
    })

_limit_cols = ['Kullanilabilir_Limit_Litre', 'Bos_Tam_Gunler_Litre',
               'Bos_Lookahead_Ham_Litre', 'Bos_Toplam_Litre',
               'Kapasite_Ham_Litre', 'Uygulanan_Oran', 'Uygulanan_Buffer',
               'Anlik_Stok_Litre', 'Yoldaki_Transit_Litre']

df_yeni[_limit_cols] = df_yeni.apply(calculate_group_limits_yeni, axis=1)

# Doluluk tablosunda var mı
df_yeni['Doluluk_Tablosunda_Var_Mi'] = df_yeni['Max. Other +4 & MS +4 WH Volume'].notna()

# ==========================================
# 🛑 ÖNCELİKLENDİRME SKORLAMASI
# ==========================================
def priority_score(row):
    p_code = str(row['Product code']).lower().strip()

    # 1. Demirbaş Koruması (101 Puan - Asla Kesilmez)
    cat = str(row.get('Custom category', '')).lower() + " " + str(row.get('Custom sub-category', '')).lower()
    if 'demirbaş' in cat or 'demirbas' in cat:
        return 101

    # 2. Dokunulmayacak Ürünler (100 Puan - İhtiyaç Halinde En Son Çare Kesilebilir): kampanya (sheet) + waste (elle)
    if row['Dokunulmazlik_Nedeni'] in ('Kampanya', 'Waste'):
        return 100

    # 3. Pick-to-Zero, Listed & Supply Shortage (99 Puan)
    if str(row.get('Pick-to-zero', '')).strip().lower() in ['1', '1.0', 'yes', 'true']:
        return 99

    abc = row['ABC class']
    cd = row['Calculated Cover Day']
    bulunurluk = row.get('Son 14 Günlük Bulunurluk', 1.0)
    end_bal = row['End balance']
    segment = str(row.get('Segment', '')).strip()

    if row['Domain Type'] == 'G10':
        if not row.get('WAva_Depo', False) and (segment.lower() == 'listed' or (end_bal < 3 and bulunurluk < 0.60 and segment == 'Supply Shortage')):
            return 99
        if abc == 'A':
            return 98 if cd < A_MIN_COVER else 85
        if abc == 'B':
            return 97 if cd < B_MIN_COVER else 84
        if end_bal < 3:
            return 83
        if row['Open purchase orders'] > 0 and cd > G10_COVER_DAY_LIMIT:
            return 1
        if row['Open purchase orders'] > 0:
            return 2
        if cd > G10_COVER_DAY_LIMIT:
            return {'E': 3, 'D': 4, 'C': 5}.get(abc, 7)
        return 81 if abc == 'C' and cd < C_MIN_COVER else 10
    else:
        if not row.get('WAva_Depo', False) and (segment.lower() == 'listed' or (end_bal < 7 and bulunurluk < 0.60 and segment == 'Supply Shortage')):
            return 99
        if abc == 'A':
            return 98 if cd < A_MIN_COVER else 85
        if abc == 'B':
            return 97 if cd < B_MIN_COVER else 84
        if end_bal < 7:
            return 83
        if row['Open purchase orders'] > 0 and cd > GB_COVER_DAY_LIMIT:
            return 1
        if row['Open purchase orders'] > 0:
            return 2
        if cd > GB_COVER_DAY_LIMIT:
            return {'E': 12, 'D': 13, 'C': 14}.get(abc, 16)
        return 81 if abc == 'C' and cd < C_MIN_COVER else 19

# ==========================================
# ⚡ ORTAK OPTİMİZASYON PIPELINE'I
# ==========================================
def run_optimizasyon(d, satir_limiti, sistem_adi):
    d = d.copy()
    d['Orijinal_Miktar'] = d['Effective quantity']
    d['Hacimden_Kesilen_Miktar'] = 0
    d['Final_Miktar'] = d['Orijinal_Miktar']
    d['Satir_Onerilen_Hacim'] = d['Orijinal_Miktar'] * d['hacim2'].fillna(0)
    d['Kesinti_Nedeni'] = 'Islem Gormedi'

    # BACKLOG KURALI
    mask_bloke = (
        ((d['Domain Type'] == 'G10') & (d['Backlog_Palet_Sayisi'] >= 1)) |
        ((d['Domain Type'] == 'GB') & (d['Backlog_Palet_Sayisi'] > 2))
    )
    d.loc[mask_bloke, 'Final_Miktar'] = 0
    d.loc[mask_bloke, 'Kesinti_Nedeni'] = 'Depo Backlog Blokaji'

    # 📋 SAYIM KISITI — depoya hiçbir şey gitmez (demirbaş dahil). Backlog nedeninin üstüne yazar.
    #    Hacim kesimine girmediği için geri yükleme de bu satırlara miktar ekleyemez.
    _m_sayim = d['Sayim_Kisiti'] == True
    d.loc[_m_sayim, 'Final_Miktar'] = 0
    d.loc[_m_sayim, 'Kesinti_Nedeni'] = SAYIM_REASON

    # 🧪 SADECE A TESTİ — test depolarında A dışı her satır en baştan sıfır (sayımlı depoda neden 'Sayım' kalır)
    _a_test = d['Location name'].map(_norm_ad).isin({_norm_ad(x) for x in SADECE_A_TEST_DEPOLARI})
    d['Sadece_A_Test'] = _a_test
    d['WAva_Depo'] = d['Location name'].map(_norm_ad).isin({_norm_ad(x) for x in WEIGHTED_AVA_DEPOLARI})
    if d['WAva_Depo'].any():
        print(f"[{sistem_adi}] 🎯 Weighted ava depoları (99 koruması yok): {sorted(d.loc[d['WAva_Depo'], 'Location name'].unique())}")
    _m_a = _a_test & (d['ABC class'].astype(str).str.upper().str.strip() != 'A') & ~_m_sayim
    d.loc[_m_a, 'Final_Miktar'] = 0
    d.loc[_m_a, 'Kesinti_Nedeni'] = SADECE_A_REASON
    if _a_test.any():
        print(f"[{sistem_adi}] 🧪 Sadece A testi: {sorted(d.loc[_a_test, 'Location name'].unique())} → "
              f"{int(_m_a.sum())} A dışı satır sıfırlandı, {int((_a_test & ~_m_a).sum())} satır değerlendirmede")

    # 🎯 Dokunulmazlık nedeni: Kampanya (sheet, KAMPANYA_HAFTA listesi) > Waste (elle girilen liste)
    #    Sadece A test depolarında dokunulmazlık yok.
    _pc = d['Product code'].astype(str).str.lower().str.strip()
    _dom = d['Domain Type'].astype(str).str.strip()
    _kamp = (((_dom == 'G10') & _pc.isin(KAMPANYA_LISTELERI.get(('G10', KAMPANYA_HAFTA), set()))) |
             ((_dom == 'GB') & _pc.isin(KAMPANYA_LISTELERI.get(('GB', KAMPANYA_HAFTA), set())))) & ~_a_test
    _waste = (((_dom == 'G10') & _pc.isin([str(x).lower().strip() for x in DOKUNULMAYACAK_G10])) |
              ((_dom == 'GB') & _pc.isin([str(x).lower().strip() for x in DOKUNULMAYACAK_GB]))) & ~_a_test
    d['Dokunulmazlik_Nedeni'] = np.select([_kamp, _waste], ['Kampanya', 'Waste'], default='')
    d['Kampanya_Listesi'] = np.where(_kamp, KAMPANYA_HAFTA, '')
    print(f"[{sistem_adi}] 🎯 Dokunulmazlık: Kampanya {int(_kamp.sum())} satır, Waste {int((_waste & ~_kamp).sum())} satır")

    d['Cut_Priority'] = d.apply(priority_score, axis=1)
    d.drop(columns=['WAva_Depo'], inplace=True)   # yalnız puanlama için; çıktıya girmez

    # --- ROUND-ROBIN KESİNTİ ---
    print(f"[{sistem_adi}] Optimizasyon hesaplanıyor...")
    depo_group_hacim = d[d['Final_Miktar'] > 0].groupby(['Location name', 'Item_group']).agg({
        'Satir_Onerilen_Hacim': 'sum',
        'Kullanilabilir_Limit_Litre': 'first'
    }).reset_index()

    for _, r in depo_group_hacim.iterrows():
        loc = str(r['Location name'])
        tabloda_var_mi = d[d['Location name'] == loc]['Doluluk_Tablosunda_Var_Mi'].any()
        if not tabloda_var_mi:
            continue

        if r['Satir_Onerilen_Hacim'] > r['Kullanilabilir_Limit_Litre']:
            fark = r['Satir_Onerilen_Hacim'] - r['Kullanilabilir_Limit_Litre']
            loc_mask = (
                (d['Location name'] == r['Location name']) &
                (d['Item_group'] == r['Item_group']) &
                (d['Cut_Priority'] < 101) &
                (d['Final_Miktar'] > 0)
            )
            h_df = d.loc[loc_mask].copy()
            k_hacim = 0

            for cp in sorted(h_df['Cut_Priority'].unique()):
                if k_hacim >= fark:
                    break
                p_idx = h_df[h_df['Cut_Priority'] == cp].index.tolist()
                while k_hacim < fark and p_idx:
                    to_rem = []
                    for idx in p_idx:
                        if k_hacim >= fark:
                            break
                        bh = d.at[idx, 'hacim2']
                        if bh <= 0:
                            to_rem.append(idx)
                            continue
                        batch = d.at[idx, 'Order batch size']
                        dus = min(batch, d.at[idx, 'Final_Miktar'])
                        if dus <= 0:
                            to_rem.append(idx)
                            continue
                        d.at[idx, 'Final_Miktar'] -= dus
                        d.at[idx, 'Hacimden_Kesilen_Miktar'] += dus
                        k_hacim += (dus * bh)
                        d.at[idx, 'Kesinti_Nedeni'] = f"Kapasite Zorlamasi ({r['Item_group']} Limiti) - Kisildi"
                        if d.at[idx, 'Final_Miktar'] <= 0:
                            to_rem.append(idx)
                    for idx in to_rem:
                        p_idx.remove(idx)

    # --- MERKEZ SATIR LİMİTİ ---
    aktif_satirlar = d[d['Final_Miktar'] > 0]
    if len(aktif_satirlar) > satir_limiti:
        sil_sayisi = len(aktif_satirlar) - satir_limiti
        sil_idx = (
            aktif_satirlar[(aktif_satirlar['Cut_Priority'] < 101) & ~aktif_satirlar['Sadece_A_Test']]
            .sort_values('Cut_Priority')
            .head(sil_sayisi)
            .index
        )
        d.loc[sil_idx, 'Final_Miktar'] = 0
        d.loc[sil_idx, 'Kesinti_Nedeni'] = "Merkez Depo Satir Limiti Asildi"

    # --- HACİM GERİ YÜKLEME ---
    print(f"[{sistem_adi}] Hacim geri yükleme fazı çalışıyor...")
    d['Geri_Eklenen_Miktar'] = 0
    d['Geri_Yukleme_Yapildi'] = False
    d['Geri_Yukleme_Notu'] = ''
    d['Satir_Tamamen_Silindi'] = (d['Orijinal_Miktar'] > 0) & (d['Final_Miktar'] == 0)
    d['Guncel_Hacim_Litre'] = d['Final_Miktar'] * d['hacim2'].fillna(0)

    depo_grup_guncel = (
        d.groupby(['Location name', 'Item_group'])
         .agg(Mevcut_Hacim=('Guncel_Hacim_Litre', 'sum'), Limit=('Kullanilabilir_Limit_Litre', 'first'))
         .reset_index()
    )

    for _, grp in depo_grup_guncel.iterrows():
        bosluk = grp['Limit'] - grp['Mevcut_Hacim']
        if bosluk <= 0:
            continue

        aday_mask = (
            (d['Location name'] == grp['Location name']) &
            (d['Item_group'] == grp['Item_group']) &
            (d['Hacimden_Kesilen_Miktar'] > 0) &
            (~d['Satir_Tamamen_Silindi'])
        )
        adaylar = d.loc[aday_mask].sort_values('Cut_Priority', ascending=False)

        for idx in adaylar.index:
            if bosluk <= 0:
                break
            urun_hacmi = d.at[idx, 'hacim2']
            if pd.isna(urun_hacmi) or urun_hacmi <= 0:
                continue
            batch = d.at[idx, 'Order batch size']
            if pd.isna(batch) or batch <= 0:
                continue
            kalan_kesilen = d.at[idx, 'Hacimden_Kesilen_Miktar']
            while kalan_kesilen > 0:
                eklenecek = min(batch, kalan_kesilen)
                eklenecek_hacim = eklenecek * urun_hacmi
                if eklenecek_hacim > bosluk:
                    break
                d.at[idx, 'Final_Miktar'] += eklenecek
                d.at[idx, 'Hacimden_Kesilen_Miktar'] -= eklenecek
                d.at[idx, 'Geri_Eklenen_Miktar'] += eklenecek
                d.at[idx, 'Geri_Yukleme_Yapildi'] = True
                d.at[idx, 'Geri_Yukleme_Notu'] = 'Kesildi ve geri yuklendi'
                bosluk -= eklenecek_hacim
                kalan_kesilen -= eklenecek
                if d.at[idx, 'Final_Miktar'] >= d.at[idx, 'Orijinal_Miktar']:
                    break

    # --- 📦 DEPO TOPLAM ADET LİMİTİ (geri yüklemeden SONRA) ---
    # Kesim sırası hacim kısmasıyla aynı: düşük priority önce, grup içinde round-robin birer batch.
    for loc, g in d.groupby('Location name'):
        limit = _ADET_LIMIT_NORM.get(_norm_ad(loc))
        if limit is None:
            continue
        _adet_eslesen.add(_norm_ad(loc))
        if g['Sadece_A_Test'].any():
            print(f"[{sistem_adi}] 📦 {loc}: sadece A test deposu → adet limiti uygulanmadı")
            continue
        toplam = float(d.loc[g.index, 'Final_Miktar'].sum())
        if toplam <= limit:
            print(f"[{sistem_adi}] 📦 {loc}: toplam {toplam:,.0f} adet ≤ limit {limit} → kısma yok")
            continue
        fazla = toplam - limit
        a_df = d.loc[g.index][(d.loc[g.index, 'Cut_Priority'] < 101) & (d.loc[g.index, 'Final_Miktar'] > 0)]
        for cp in sorted(a_df['Cut_Priority'].unique()):
            if fazla <= 0:
                break
            p_idx = a_df[a_df['Cut_Priority'] == cp].index.tolist()
            while fazla > 0 and p_idx:
                to_rem = []
                for idx in p_idx:
                    if fazla <= 0:
                        break
                    batch = d.at[idx, 'Order batch size']
                    batch = 1 if (pd.isna(batch) or batch <= 0) else batch
                    dus = min(batch, d.at[idx, 'Final_Miktar'])
                    if dus <= 0:
                        to_rem.append(idx)
                        continue
                    d.at[idx, 'Final_Miktar'] -= dus
                    fazla -= dus
                    d.at[idx, 'Kesinti_Nedeni'] = f"Kapasite Zorlamasi ({d.at[idx, 'Item_group']} Limiti) - Kisildi"
                    if d.at[idx, 'Final_Miktar'] <= 0:
                        to_rem.append(idx)
                for idx in to_rem:
                    p_idx.remove(idx)
        print(f"[{sistem_adi}] 📦 {loc}: toplam {toplam:,.0f} adet → limit {limit} için "
              f"{d.loc[g.index, 'Final_Miktar'].sum():,.0f} adete kısıldı")

    d['Fark (Kesilen Miktar)'] = d['Orijinal_Miktar'] - d['Final_Miktar']
    d['Final_Hacim_Litre'] = d['Final_Miktar'] * d['hacim2']
    return d

df_yeni = run_optimizasyon(df_yeni, MAX_SATIR_LIMITI_YENI, "YENİ SİSTEM")

for _k in set(_ADET_LIMIT_NORM) - _adet_eslesen:
    print(f"   ⚠️  Adet limiti tanımlı ama bu koşuda bulunamayan depo: '{_k}'")

# ==========================================
# 📊 RAPORLAMA İÇİN KAPASİTE_LİTRE — SİSTEM BAZLI
# ==========================================
is_g10_tipi_yeni = (df_yeni['Domain Type'] == 'G10') | (df_yeni['Location name'].isin(G10_TIPI_DEPOLAR))
df_yeni['Kapasite_Litre'] = np.where(
    df_yeni['Item_group'] == 'ETB',
    np.where(
        is_g10_tipi_yeni,
        df_yeni['Max. ETB WH Volume'] * df_yeni['etb_oran'] * df_yeni['buffer_rate'],
        df_yeni['Max. Other +4 & MS +4 WH Volume'] * df_yeni['etb_oran'] * df_yeni['buffer_rate']
    ),
    df_yeni['Max. Other +4 & MS +4 WH Volume'] * df_yeni['other4_oran'] * df_yeni['buffer_rate']
)

# ==========================================
# 🔗 BİRLEŞTİRME
# ==========================================
df_final = df_yeni.reset_index(drop=True)

# --- Depo özet karnesi ---
depo_final_ozet = df_final.groupby(['Location name', 'Item_group']).agg(
    Domain_Type=('Domain Type', 'first'),
    Maksimum_Hacim_Litre=('Kapasite_Litre', 'first'),
    Net_Hacim_Boslugu_Litre=('Kullanilabilir_Limit_Litre', 'first'),
    Onerilen_Toplam_Hacim_Litre=('Satir_Onerilen_Hacim', 'sum'),
    Final_Toplam_Hacim_Litre=('Final_Hacim_Litre', 'sum')
).reset_index()

depo_final_ozet['Teslimat_Anindaki_Dolu_Hacim'] = (
    depo_final_ozet['Maksimum_Hacim_Litre'] - depo_final_ozet['Net_Hacim_Boslugu_Litre']
)
depo_final_ozet['Gelecek_Teslimat_Sonrasi_Doluluk (%)'] = (
    ((depo_final_ozet['Teslimat_Anindaki_Dolu_Hacim'] + depo_final_ozet['Final_Toplam_Hacim_Litre']) /
     depo_final_ozet['Maksimum_Hacim_Litre']) * 100
).fillna(0).round(1)
depo_final_ozet['Kesintisiz_Gelecek_Doluluk (%)'] = (
    ((depo_final_ozet['Teslimat_Anindaki_Dolu_Hacim'] + depo_final_ozet['Onerilen_Toplam_Hacim_Litre']) /
     depo_final_ozet['Maksimum_Hacim_Litre']) * 100
).fillna(0).round(1)

depo_final_ozet['Sistem'] = 'Yeni Sistem'   # kolon Sharing raporu için korunuyor; eski sistem 19.11.2026'da kaldırıldı

dol_piv = depo_final_ozet.pivot(
    index='Location name',
    columns='Item_group',
    values=['Gelecek_Teslimat_Sonrasi_Doluluk (%)', 'Kesintisiz_Gelecek_Doluluk (%)']
).reset_index()
dol_piv.columns = [f"{c[1]}_{c[0]}" if c[1] else c[0] for c in dol_piv.columns]
df_final = pd.merge(df_final, dol_piv, on='Location name', how='left')

# ==========================================
# 🔀 SHEET: KAPASİTE DETAYI
# ==========================================
kapasite_detay = df_final.groupby(['Location name', 'Item_group']).agg(
    Location_code=('Location code', 'first'),
    Domain_Type=('Domain Type', 'first'),
    Doluluk_Tablosunda_Var_Mi=('Doluluk_Tablosunda_Var_Mi', 'first'),
    Kapasite_Ham_Litre=('Kapasite_Ham_Litre', 'first'),
    Uygulanan_Oran=('Uygulanan_Oran', 'first'),
    Uygulanan_Buffer=('Uygulanan_Buffer', 'first'),
    Anlik_Stok_Litre=('Anlik_Stok_Litre', 'first'),
    Yoldaki_Transit_Litre=('Yoldaki_Transit_Litre', 'first'),
    Forecast_Bosalacak_Tam_Gunler_Litre=('Bos_Tam_Gunler_Litre', 'first'),
    Forecast_Bosalacak_Lookahead_Ham_Litre=('Bos_Lookahead_Ham_Litre', 'first'),
    Forecast_Bosalacak_Toplam_Litre=('Bos_Toplam_Litre', 'first'),
    Slot_Ogle_Oncesi_Biten=('Slot_Ogle_Oncesi_Biten', 'first'),
    Slot_Bitis_Saati=('Slot_Bitis_Saati', 'first'),
    Lookahead_Faktor=('Lookahead_Faktor', 'first'),
    Lead_Time_Days=('Lead_Time_Days', 'first'),
    Teslimatta_Bos_Alan_Litre=('Kullanilabilir_Limit_Litre', 'first'),
    Onerilen_Hacim_Litre=('Satir_Onerilen_Hacim', 'sum'),
    Final_Hacim_Litre=('Final_Hacim_Litre', 'sum'),
    Toplam_Satir=('Final_Miktar', 'size'),
    Aktif_Satir=('Final_Miktar', lambda s: int((s > 0).sum())),
).reset_index()

kapasite_detay['Sistem'] = 'Yeni Sistem'   # kolon Sharing raporu için korunuyor; eski sistem 19.11.2026'da kaldırıldı

kapasite_detay['Kapasite_Oranli_Litre'] = kapasite_detay['Kapasite_Ham_Litre'] * kapasite_detay['Uygulanan_Oran']
kapasite_detay['Kapasite_Kullanilabilir_Litre'] = kapasite_detay['Kapasite_Oranli_Litre'] * kapasite_detay['Uygulanan_Buffer']
_kap = kapasite_detay['Kapasite_Kullanilabilir_Litre']

kapasite_detay['Anlik_Doluluk_Pct'] = np.where(_kap > 0, kapasite_detay['Anlik_Stok_Litre'] / _kap * 100, 0).round(1)
kapasite_detay['Anlik_Bos_Alan_Litre'] = (_kap - kapasite_detay['Anlik_Stok_Litre']).clip(lower=0)

kapasite_detay['Stok_Plus_Transit_Litre'] = kapasite_detay['Anlik_Stok_Litre'] + kapasite_detay['Yoldaki_Transit_Litre']
kapasite_detay['Transit_Dahil_Doluluk_Pct'] = np.where(_kap > 0, kapasite_detay['Stok_Plus_Transit_Litre'] / _kap * 100, 0).round(1)
kapasite_detay['Transit_Dahil_Bos_Alan_Litre'] = (_kap - kapasite_detay['Stok_Plus_Transit_Litre']).clip(lower=0)

kapasite_detay['Teslimatta_Dolu_Litre'] = (kapasite_detay['Stok_Plus_Transit_Litre'] - kapasite_detay['Forecast_Bosalacak_Toplam_Litre']).clip(lower=0)
kapasite_detay['Teslimatta_Doluluk_Pct'] = np.where(_kap > 0, kapasite_detay['Teslimatta_Dolu_Litre'] / _kap * 100, 0).round(1)

kapasite_detay['Kesilen_Hacim_Litre'] = kapasite_detay['Onerilen_Hacim_Litre'] - kapasite_detay['Final_Hacim_Litre']
kapasite_detay['Bos_Alan_Kullanim_Pct'] = np.where(
    kapasite_detay['Teslimatta_Bos_Alan_Litre'] > 0,
    kapasite_detay['Final_Hacim_Litre'] / kapasite_detay['Teslimatta_Bos_Alan_Litre'] * 100,
    0
).round(1)

kapasite_detay['Teslimat_Sonrasi_Doluluk_Pct'] = np.where(
    _kap > 0,
    (kapasite_detay['Teslimatta_Dolu_Litre'] + kapasite_detay['Final_Hacim_Litre']) / _kap * 100,
    0
).round(1)
kapasite_detay['Kesintisiz_Olsaydi_Doluluk_Pct'] = np.where(
    _kap > 0,
    (kapasite_detay['Teslimatta_Dolu_Litre'] + kapasite_detay['Onerilen_Hacim_Litre']) / _kap * 100,
    0
).round(1)

_kd_yuvarla = [
    'Kapasite_Ham_Litre', 'Kapasite_Oranli_Litre', 'Kapasite_Kullanilabilir_Litre',
    'Anlik_Stok_Litre', 'Anlik_Bos_Alan_Litre',
    'Yoldaki_Transit_Litre', 'Stok_Plus_Transit_Litre', 'Transit_Dahil_Bos_Alan_Litre',
    'Forecast_Bosalacak_Tam_Gunler_Litre', 'Forecast_Bosalacak_Lookahead_Ham_Litre',
    'Forecast_Bosalacak_Toplam_Litre',
    'Teslimatta_Dolu_Litre', 'Teslimatta_Bos_Alan_Litre',
    'Onerilen_Hacim_Litre', 'Final_Hacim_Litre', 'Kesilen_Hacim_Litre',
]
for _c in _kd_yuvarla:
    kapasite_detay[_c] = kapasite_detay[_c].astype(float).round(1)
kapasite_detay['Uygulanan_Oran']   = kapasite_detay['Uygulanan_Oran'].astype(float).round(4)
kapasite_detay['Uygulanan_Buffer'] = kapasite_detay['Uygulanan_Buffer'].astype(float).round(4)
kapasite_detay['Lookahead_Faktor'] = kapasite_detay['Lookahead_Faktor'].astype(float).round(4)

KAPASITE_DETAY_SIRA = [
    'Location name', 'Location_code', 'Domain_Type', 'Sistem', 'Item_group',
    'Doluluk_Tablosunda_Var_Mi',
    'Kapasite_Ham_Litre', 'Uygulanan_Oran', 'Kapasite_Oranli_Litre',
    'Uygulanan_Buffer', 'Kapasite_Kullanilabilir_Litre',
    'Anlik_Stok_Litre', 'Anlik_Doluluk_Pct', 'Anlik_Bos_Alan_Litre',
    'Yoldaki_Transit_Litre', 'Stok_Plus_Transit_Litre',
    'Transit_Dahil_Doluluk_Pct', 'Transit_Dahil_Bos_Alan_Litre',
    'Lead_Time_Days', 'Slot_Ogle_Oncesi_Biten', 'Slot_Bitis_Saati', 'Lookahead_Faktor',
    'Forecast_Bosalacak_Tam_Gunler_Litre', 'Forecast_Bosalacak_Lookahead_Ham_Litre',
    'Forecast_Bosalacak_Toplam_Litre',
    'Teslimatta_Dolu_Litre', 'Teslimatta_Doluluk_Pct', 'Teslimatta_Bos_Alan_Litre',
    'Onerilen_Hacim_Litre', 'Final_Hacim_Litre', 'Kesilen_Hacim_Litre',
    'Bos_Alan_Kullanim_Pct', 'Aktif_Satir', 'Toplam_Satir',
    'Teslimat_Sonrasi_Doluluk_Pct', 'Kesintisiz_Olsaydi_Doluluk_Pct',
]
kapasite_detay = kapasite_detay[[c for c in KAPASITE_DETAY_SIRA if c in kapasite_detay.columns]]
kapasite_detay = kapasite_detay.sort_values(['Location name', 'Item_group']).reset_index(drop=True)

# ==========================================
# 🔀 SHEET: SLOT & LOOKAHEAD KONTROL
# ==========================================
slot_kontrol = df_final.groupby(['Location name', 'Item_group']).agg(
    Location_code=('Location code', 'first'),
    Domain_Type=('Domain Type', 'first'),
    Slot_Ogle_Oncesi_Biten=('Slot_Ogle_Oncesi_Biten', 'first'),
    Slot_Bitis_Saati=('Slot_Bitis_Saati', 'first'),
    Lookahead_Faktor=('Lookahead_Faktor', 'first'),
    Lead_Time_Days=('Lead_Time_Days', 'first'),
    Doluluk_Tablosunda_Var_Mi=('Doluluk_Tablosunda_Var_Mi', 'first'),
    Kapasite_Litre=('Kapasite_Litre', 'first'),
    Bos_Tam_Gunler_Litre=('Bos_Tam_Gunler_Litre', 'first'),
    Bos_Lookahead_Ham_Litre=('Bos_Lookahead_Ham_Litre', 'first'),
    Bos_Toplam_Litre=('Bos_Toplam_Litre', 'first'),
    Kullanilabilir_Limit_Litre=('Kullanilabilir_Limit_Litre', 'first'),
    Onerilen_Hacim_Litre=('Satir_Onerilen_Hacim', 'sum'),
    Final_Hacim_Litre=('Final_Hacim_Litre', 'sum'),
    Aktif_Satir=('Final_Miktar', lambda s: int((s > 0).sum())),
).reset_index()

slot_kontrol['Sistem'] = 'Yeni Sistem'   # kolon Sharing raporu için korunuyor; eski sistem 19.11.2026'da kaldırıldı

slot_kontrol['Bos_Kural_Yoksa_Litre'] = (
    slot_kontrol['Bos_Tam_Gunler_Litre'] +
    slot_kontrol['Bos_Lookahead_Ham_Litre'] * FORECAST_LOOKAHEAD_RATIO
)
slot_kontrol['Slot_Kurali_Etkisi_Litre'] = (
    slot_kontrol['Bos_Kural_Yoksa_Litre'] - slot_kontrol['Bos_Toplam_Litre']
).round(1)

_beklenen = (slot_kontrol['Bos_Tam_Gunler_Litre'] +
             slot_kontrol['Bos_Lookahead_Ham_Litre'] * slot_kontrol['Lookahead_Faktor'])
slot_kontrol['Formul_Tutuyor_Mu'] = (
    (slot_kontrol['Bos_Toplam_Litre'] - _beklenen).abs() < 0.01
)

for _c in ['Kapasite_Litre', 'Bos_Tam_Gunler_Litre', 'Bos_Lookahead_Ham_Litre',
           'Bos_Toplam_Litre', 'Bos_Kural_Yoksa_Litre', 'Kullanilabilir_Limit_Litre',
           'Onerilen_Hacim_Litre', 'Final_Hacim_Litre']:
    slot_kontrol[_c] = slot_kontrol[_c].astype(float).round(1)
slot_kontrol['Lookahead_Faktor'] = slot_kontrol['Lookahead_Faktor'].round(4)

slot_kontrol = slot_kontrol.sort_values(
    ['Slot_Ogle_Oncesi_Biten', 'Location name', 'Item_group'], ascending=[False, True, True]
).reset_index(drop=True)

# ==========================================
# 🐞 DEBUG SHEET — VERİ KALİTE KONTROLLERİ
# ==========================================
from openpyxl.styles import PatternFill, Font

DBG_SPOILING_ORANI             = 1.0
DBG_FC_MEDYAN_KATI             = 5.0
DBG_FC_MIN_DEPO_SAYISI         = 5
DBG_FC_MIN_DEGER               = 1.0

SEVIYE_SIRA  = {'KRİTİK': 0, 'UYARI': 1, 'BİLGİ': 2}
DBG_KOLONLAR = ['Seviye', 'Kod', 'Kontrol', 'Location name', 'Location code', 'Sistem',
                'Domain Type', 'Item_group', 'Product code', 'Product name',
                'Deger', 'Esik', 'Orijinal_Miktar', 'Final_Miktar', 'Kesinti_Nedeni', 'Ne_Yapmali']

_dbg_parcalar  = []
_relex_depolar = set(df_final['Location name'].dropna())
_loc_code_map  = (df_final.dropna(subset=['Location name'])
                  .drop_duplicates('Location name')
                  .set_index('Location name')['Location code'])

def _num(d, c):
    return pd.to_numeric(d[c], errors='coerce') if c in d.columns else pd.Series(np.nan, index=d.index)

def dbg(kaynak, mask, seviye, kod, kontrol, deger, esik, oneri):
    if kaynak is None or len(kaynak) == 0:
        return
    if mask is not None:
        mask = pd.Series(mask, index=kaynak.index).fillna(False).astype(bool)
        kaynak = kaynak.loc[mask]
        if len(kaynak) == 0:
            return
    k = kaynak.rename(columns={'Domain_Type': 'Domain Type', 'Location_code': 'Location code'})
    out = pd.DataFrame(index=k.index)
    for c in DBG_KOLONLAR:
        out[c] = k[c] if c in k.columns else ''
    if 'Location code' not in k.columns:
        out['Location code'] = out['Location name'].map(_loc_code_map)
    out['Sistem'] = np.where(out['Location name'].isin(_relex_depolar), 'Yeni Sistem', '')
    out['Seviye']     = seviye
    out['Kod']        = kod
    out['Kontrol']    = kontrol
    out['Ne_Yapmali'] = oneri
    for col, val in (('Deger', deger), ('Esik', esik)):
        if isinstance(val, pd.Series):
            v = val.reindex(k.index)
            out[col] = v.round(2) if pd.api.types.is_numeric_dtype(v) else v
        else:
            out[col] = val if np.isscalar(val) else str(val)
    _dbg_parcalar.append(out[DBG_KOLONLAR].reset_index(drop=True))

F = df_final
orj, fin    = _num(F, 'Orijinal_Miktar'), _num(F, 'Final_Miktar')
fc, eb, opo = _num(F, 'Daily FC'), _num(F, 'End balance'), _num(F, 'Open purchase orders')
gonderim = orj > 0
fc_pos   = fc.where(fc > 0)

urun_yok = F['marketproduct_id'].isna() if 'marketproduct_id' in F.columns else pd.Series(False, index=F.index)
dbg(F, gonderim & urun_yok, 'KRİTİK', 'S01', "Ürün, hacim GSheet'inde yok", "hacim yok", "-",
    "Hacim 0 sayıldı: satır kapasiteye girmiyor ve kesilemiyor. Ürün hacim sheet'ini kontrol et.")

dbg(F, gonderim & (fc.isna() | (fc <= 0)), 'UYARI', 'S08', "Gönderim var ama Daily FC boş / 0", fc, "> 0",
    "Talep yokken ürün gidiyor. FC=0 → cover 0 → A/B ürün 97-98 önceliği alıp en son kesiliyor.")

cover_sonra = (eb.clip(lower=0).fillna(0) + opo.clip(lower=0).fillna(0) + fin) / fc_pos
spoiling    = _num(F, 'Reference spoiling time')
spoil_esik  = spoiling.where(spoiling > 0) * DBG_SPOILING_ORANI
if 'Reference spoiling time' not in F.columns:
    print("  ⚠️  Relex'te 'Reference spoiling time' kolonu yok → S11 (yüksek cover) kontrolü çalışmadı")
else:
    _spoil_yok = int(((fin > 0) & spoil_esik.isna()).sum())
    if _spoil_yok:
        print(f"  ⚠️  {_spoil_yok} gönderim satırında spoiling time boş/0 → S11 bu satırlarda kontrol edilmedi")
dbg(F, (fin > 0) & (cover_sonra > spoil_esik), 'UYARI', 'S11',
    "Gönderim sonrası cover spoiling time'ı aşıyor", cover_sonra, spoil_esik,
    "Ürün satılmadan bozulabilir: miktar veya Daily FC hatalı olabilir.")

_keys  = [F['Product code'], F['Domain Type']]
fc_med = fc_pos.groupby(_keys).transform('median')
fc_cnt = fc_pos.groupby(_keys).transform('count')
fc_kat = fc / fc_med
dbg(F, gonderim & (fc_cnt >= DBG_FC_MIN_DEPO_SAYISI) & (fc >= DBG_FC_MIN_DEGER) & (fc_kat > DBG_FC_MEDYAN_KATI),
    'UYARI', 'S14', "Daily FC diğer depolara göre aşırı yüksek (x medyan)", fc_kat,
    f"≤ {DBG_FC_MEDYAN_KATI}x", "Forecast şişmiş olabilir (promo, açılış, veri hatası).")

_bl = (F[F['Kesinti_Nedeni'] == 'Depo Backlog Blokaji']
       .groupby('Location name').agg(Backlog=('Backlog_Palet_Sayisi', 'max')).reset_index())
dbg(_bl, None, 'BİLGİ', 'D11', "Depo backlog nedeniyle bloke", _bl['Backlog'], "G10 ≥1 / GB >2 palet",
    "Bugün sevkiyat yok; backlog verisi güncel mi?")

_yeni_df = pd.DataFrame({'Location name': sorted(df_yeni['Location name'].dropna().unique())})
_oran_ok = set(df_oran.dropna(subset=['etb_oran', 'other4_oran'])['Location name'])
dbg(_yeni_df, ~_yeni_df['Location name'].isin(_oran_ok), 'BİLGİ', 'D12',
    "Kapasite oranı GSheet'te yok → default oran kullanıldı", "default", "-", "Oran sheet'ine depo eklenmeli mi?")
dbg(_yeni_df, ~_yeni_df['Location name'].isin(set(df_buffer['Location name'])), 'BİLGİ', 'D13',
    "Buffer rate GSheet'te yok → default buffer kullanıldı", PLUS_4_USABLE_RATIO, "-", "Buffer sheet'ini kontrol et.")

debug_detay = (pd.concat(_dbg_parcalar, ignore_index=True) if _dbg_parcalar
               else pd.DataFrame(columns=DBG_KOLONLAR))
debug_detay['_s'] = debug_detay['Seviye'].map(SEVIYE_SIRA)
debug_detay = (debug_detay.sort_values(['_s', 'Kod', 'Location name'], kind='stable')
               .drop(columns='_s').reset_index(drop=True))

debug_ozet = pd.DataFrame(columns=['Seviye', 'Kod', 'Kontrol', 'Kayit_Sayisi', 'Etkilenen_Depo', 'Ne_Yapmali'])
debug_depo = pd.DataFrame(columns=['Location name', 'KRİTİK', 'UYARI', 'BİLGİ', 'Kontroller'])
if len(debug_detay):
    debug_ozet = (debug_detay.groupby(['Seviye', 'Kod', 'Kontrol'], sort=False)
                  .agg(Kayit_Sayisi=('Ne_Yapmali', 'size'),
                       Etkilenen_Depo=('Location name', 'nunique'),
                       Ne_Yapmali=('Ne_Yapmali', 'first'))
                  .reset_index())
    debug_depo = (debug_detay.groupby('Location name')
                  .agg(**{s: ('Seviye', lambda x, s=s: int((x == s).sum())) for s in SEVIYE_SIRA},
                       Kontroller=('Kod', lambda x: ', '.join(sorted(x.unique()))))
                  .reset_index()
                  .sort_values(['KRİTİK', 'UYARI'], ascending=False))

print(f"\n🐞 Debug: {(debug_detay['Seviye'] == 'KRİTİK').sum()} KRİTİK | "
      f"{(debug_detay['Seviye'] == 'UYARI').sum()} UYARI | "
      f"{(debug_detay['Seviye'] == 'BİLGİ').sum()} BİLGİ → 'Debug Ozet' / 'Debug Detay' sheet'lerine bak")

_DBG_RENK = {'KRİTİK': 'F8CBAD', 'UYARI': 'FFE699', 'BİLGİ': 'DDEBF7'}

def _dbg_format(ws, filtre=True):
    ws.freeze_panes = 'A2'
    if filtre and ws.max_row > 1:
        ws.auto_filter.ref = ws.dimensions
    for c in ws[1]:
        c.font = Font(bold=True)
    for row in ws.iter_rows(min_row=2, max_col=1):
        if row[0].value in _DBG_RENK:
            row[0].fill = PatternFill('solid', fgColor=_DBG_RENK[row[0].value])
    for col in ws.columns:
        w = max((len(str(c.value)) for c in col[:300] if c.value is not None), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(max(10, w + 2), 70)

def debug_sheetlerini_yaz(writer):
    debug_ozet.to_excel(writer, sheet_name='Debug Ozet', index=False)
    _bas = len(debug_ozet) + 3
    debug_depo.to_excel(writer, sheet_name='Debug Ozet', index=False, startrow=_bas)
    debug_detay.to_excel(writer, sheet_name='Debug Detay', index=False)
    ws = writer.sheets['Debug Ozet']
    _dbg_format(ws, filtre=False)
    for c in ws[_bas + 1]:
        c.font = Font(bold=True)
    _dbg_format(writer.sheets['Debug Detay'])

# ==========================================
# 📋 SHEET: SAYIM KISITI
# ==========================================
sayim_rapor = pd.DataFrame(_sayim_rapor)
if not sayim_rapor.empty:
    _sk_ozet = (df_final[df_final['Sayim_Kisiti'] == True].groupby('Location name')
                .agg(_satir=('Orijinal_Miktar', lambda x: int((x > 0).sum())), _miktar=('Orijinal_Miktar', 'sum')))
    _kisildi = sayim_rapor['Durum'].str.startswith('KISILDI')
    sayim_rapor['Kesilen Satır']  = np.where(_kisildi, sayim_rapor['Depo'].map(_sk_ozet['_satir']), 0)
    sayim_rapor['Kesilen Miktar'] = np.where(_kisildi, sayim_rapor['Depo'].map(_sk_ozet['_miktar']), 0)
    sayim_rapor = sayim_rapor.sort_values(['Durum', 'Depo', 'Sayım Tarihi']).reset_index(drop=True)

# ==========================================
# 🚚 TRANSFER SHEET
# ==========================================
_tr_miktar = pd.to_numeric(df_final['Final_Miktar'], errors='coerce')
_tr = df_final.loc[_tr_miktar > 0]

transfer_df = pd.DataFrame({
    'fromWarehouse': TRANSFER_FROM_WAREHOUSE,
    'toWarehouse':   _tr['Location code'],
    'item':          _tr['Product code'],
    'count':         _tr_miktar.loc[_tr.index].round().astype(int),
    'eta':           pd.to_datetime(_tr['Delivery date'], errors='coerce').dt.date,
}).reset_index(drop=True)

print(f"🚚 Transfer: {len(transfer_df):,} satır | toplam adet: {int(transfer_df['count'].sum()):,}")

# ==========================================
# 📁 OTOMATİK GOOGLE DRIVE KAYIT SİSTEMİ
# ==========================================
import datetime
from google.colab import auth
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

print("\n🚀 Google Drive'a yükleniyor... (İzin istenebilir)")
auth.authenticate_user()
drive_service = build('drive', 'v3')

def get_or_create_folder(folder_name, parent_id):
    """Belirtilen klasörü bulur, yoksa yaratır ve ID'sini döner."""
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed=false"
    results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    items = results.get('files', [])

    if not items:
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        folder = drive_service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')
    else:
        return items[0].get('id')

# 1. Günün tarihini formatla (Örn: 16.09)
bugun_str = datetime.datetime.now().strftime("%d.%m")

# 2. Ana klasör altında bugünün klasörünü bul/yarat
print(f"📁 Klasör kontrolü yapılıyor: {bugun_str}...")
gun_klasor_id = get_or_create_folder(bugun_str, ANA_KLASOR_ID)

# 3. Günün klasörü altında 3 standart klasörü garanti altına al
for kat in ["Ambient ve Su", "+4", "MS"]:
    get_or_create_folder(kat, gun_klasor_id)

# Hedef kategorimizin ID'sini al
hedef_kategori_id = get_or_create_folder(CALISILAN_KATEGORI, gun_klasor_id)

# 4. Excel'i geçici olarak Colab ortamına kaydet
gecici_dosya = f"{CALISILAN_DEPO}.xlsx"
print(f"Excel oluşturuluyor: {gecici_dosya}...")

with pd.ExcelWriter(gecici_dosya, engine='openpyxl') as writer:
    df_final.to_excel(writer,        sheet_name='Sheet1', index=False)
    transfer_df.to_excel(writer,     sheet_name='Transfer', index=False)
    depo_final_ozet.to_excel(writer, sheet_name='Depo Ozet Karnesi', index=False)
    kapasite_detay.to_excel(writer,  sheet_name='Kapasite Detayi', index=False)
    slot_kontrol.to_excel(writer,    sheet_name='Slot Lookahead Kontrol', index=False)
    if not sayim_rapor.empty:
        sayim_rapor.to_excel(writer, sheet_name='Sayim Kisiti', index=False)
    debug_sheetlerini_yaz(writer)

# 5. Drive'da aynı isimde dosya var mı kontrol et (Üstüne yazmak için)
query = f"name='{gecici_dosya}' and '{hedef_kategori_id}' in parents and trashed=false"
results = drive_service.files().list(q=query, spaces='drive', fields='files(id)').execute()
items = results.get('files', [])

media = MediaFileUpload(gecici_dosya, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', resumable=True)

if items:
    # Dosya zaten var -> Üstüne Yaz (Update)
    file_id = items[0].get('id')
    drive_service.files().update(fileId=file_id, media_body=media).execute()
    print(f"🔄 MEVCUT DOSYA GÜNCELLENDİ: Drive ➔ {bugun_str} ➔ {CALISILAN_KATEGORI} ➔ {gecici_dosya}")
else:
    # Dosya yok -> Yeni Yarat (Create)
    file_metadata = {
        'name': gecici_dosya,
        'parents': [hedef_kategori_id]
    }
    drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    print(f"✅ YENİ DOSYA YÜKLENDİ: Drive ➔ {bugun_str} ➔ {CALISILAN_KATEGORI} ➔ {gecici_dosya}")

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


# ---------- yalnız Colab'da kullanılır (uygulama bu adımları kendi Drive köprüsüyle yapar)
def _drive_klasor(servis, ad, ust):
    q = f"name='{ad}' and mimeType='application/vnd.google-apps.folder' and '{ust}' in parents and trashed=false"
    f = servis.files().list(q=q, spaces='drive', fields='files(id)').execute().get('files', [])
    if f:
        return f[0]['id']
    return servis.files().create(body={'name': ad, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [ust]},
                                 fields='id').execute()['id']


def _drive_dosya_bul(servis, ad, ust):
    q = f"name='{ad}' and '{ust}' in parents and trashed=false"
    f = servis.files().list(q=q, spaces='drive', fields='files(id)').execute().get('files', [])
    return f[0]['id'] if f else None


def _drive_yukle(servis, yerel, ad, ust, mime):
    from googleapiclient.http import MediaFileUpload
    media = MediaFileUpload(yerel, mimetype=mime, resumable=True)
    fid = _drive_dosya_bul(servis, ad, ust)
    if fid:
        servis.files().update(fileId=fid, media_body=media).execute()
    else:
        servis.files().create(body={'name': ad, 'parents': [ust]}, media_body=media, fields='id').execute()


def gunluk_ciktilari_yukle(servis, ana_klasor_id, gun_str, kategori, bolge, ana_df, tarih, kategoriler=('Ambient ve Su', '+4', 'MS')):
    """Colab: parquet'i ve günün All PL dosyasını Drive'a yazar."""
    import io
    from googleapiclient.http import MediaIoBaseDownload
    pq_kok = _drive_klasor(servis, PARQUET_KLASOR_ADI, ana_klasor_id)
    pq_gun = _drive_klasor(servis, gun_str, pq_kok)
    for k in kategoriler:
        _drive_klasor(servis, k, pq_gun)
    pq_kat = _drive_klasor(servis, kategori, pq_gun)
    yerel_pq = f"{bolge}.parquet"
    parquet_yaz(ana_df, yerel_pq)
    _drive_yukle(servis, yerel_pq, yerel_pq, pq_kat, 'application/octet-stream')
    print(f"✅ Parquet: {PARQUET_KLASOR_ADI} ➔ {gun_str} ➔ {kategori} ➔ {yerel_pq}")

    ad = allpl_adi(tarih)
    eski = None
    fid = _drive_dosya_bul(servis, ad + '.parquet', pq_gun)
    if fid:
        tampon = io.BytesIO()
        indir = MediaIoBaseDownload(tampon, servis.files().get_media(fileId=fid))
        bitti = False
        while not bitti:
            _, bitti = indir.next_chunk()
        tampon.seek(0)
        eski = _m_pd.read_parquet(tampon)
    yeni = allpl_satirlari(ana_df, kategori, bolge, tarih)
    tum = allpl_birlestir(eski, yeni, kategori, bolge)
    parquet_yaz(tum, ad + '.parquet')
    allpl_excel_yaz(tum, ad + '.xlsx')
    _drive_yukle(servis, ad + '.parquet', ad + '.parquet', pq_gun, 'application/octet-stream')
    # ana klasörde tek All PL Excel'i: bugünün adıyla yoksa önceki günün dosyası bugünün adına çevrilip içeriği yenilenir
    if not _drive_dosya_bul(servis, ad + '.xlsx', ana_klasor_id):
        q = f"name contains 'All PL.xlsx' and '{ana_klasor_id}' in parents and trashed=false"
        eskiler = servis.files().list(q=q, spaces='drive', fields='files(id, name, modifiedTime)', orderBy='modifiedTime desc',
                                      supportsAllDrives=True, includeItemsFromAllDrives=True).execute().get('files', [])
        if eskiler:
            servis.files().update(fileId=eskiler[0]['id'], body={'name': ad + '.xlsx'}, supportsAllDrives=True).execute()
    _drive_yukle(servis, ad + '.xlsx', ad + '.xlsx', ana_klasor_id,
                 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    print(f"✅ {ad}: {len(tum):,} satır ({len(yeni):,} satır bu koşudan, {tum['bolge'].nunique()} bölge)")
# <<< ORTAK ÇIKTI

# 📦 Parquet ve günlük All PL
gunluk_ciktilari_yukle(drive_service, ANA_KLASOR_ID, bugun_str, CALISILAN_KATEGORI, CALISILAN_DEPO, df_final,
                       datetime.datetime.now())

# ==========================================
# 📋 ÖZET
# ==========================================
_bayrakli_depo   = int(slot_kontrol[slot_kontrol['Slot_Ogle_Oncesi_Biten']]['Location name'].nunique())
_toplam_etki     = float(slot_kontrol['Slot_Kurali_Etkisi_Litre'].sum())
_formul_hatasi   = int((~slot_kontrol['Formul_Tutuyor_Mu']).sum())

print(f"\nİşlem tamamlandı. Toplam Sevk: {round(df_final['Final_Hacim_Litre'].sum()):,} L")
print(f"\n🔀 Slot kuralı: {_bayrakli_depo} depo öğlen 12:00 ve öncesi bitiyor "
      f"(1/3 lookahead uygulanmadı)")
print(f"   Kural sayesinde kapasiteye eklenmeyen toplam hacim: {round(_toplam_etki):,} L")
if _formul_hatasi:
    print(f"   ⚠️  {_formul_hatasi} satırda doğrulama formülü tutmadı — Slot Lookahead Kontrol sheet'ine bak!")
else:
    print(f"   ✅ Tüm satırlarda doğrulama formülü tutuyor")
print(f"📋 Sayım kısıtı: {df_final.loc[df_final['Sayim_Kisiti'] == True, 'Location name'].nunique()} depo "
      f"({int(((df_final['Sayim_Kisiti'] == True) & (df_final['Orijinal_Miktar'] > 0)).sum())} satır kesildi)")
print(f"Toplam süre: {round(time.time() - start_time, 1)} saniye")