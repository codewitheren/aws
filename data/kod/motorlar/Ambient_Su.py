# ==========================================
# SON DÜZENLEME: DİKEY ELLEÇLEME NORMALİZASYONU (%25 TABAN),
# DİNAMİK COVER, PALETLİ SU MUAFİYETLERİ, LISTED SEGMENTİ (99 PUAN),
# DEMİRBAŞ DOKUNULMAZLIĞI (101 PUAN & <101 KESİM FİLTRESİ)
# + FAST ACCAPTENCE KOLONU + GOOGLE DRIVE OTOMASYONU
#v4: (hackathon) çıktılar yerel klasöre yazılır, Drive'a kayıt yok.
#v5: 4 dikey depoya özel V2 layout (6304c187 & 5fbce44d paylaşımlı palete girdi),
#    7 depoda 5b30d3c4 & 5a7b1f60 su'dan çıkıp ambient'e geçti (Relex OBS ile)
#v8: TIR palet limiti artık SADECE günlük Google Sheet'ten (Depo Adı + haftanın günleri).
#    Eski 'Palet Sınırı' sheet'i tamamen kaldırıldı.
#    Sıra: Günlük sheet → kod içi default (G10=12 / GB=25).
#v9: SAYIM KISITI — teslimat günü depo sayımının yasak aralığına denk gelirse
#    o depoya hiçbir şey gitmez (su + ambient + demirbaş), kesinti nedeni 'Sayım'.
# ==========================================

import pandas as pd
import numpy as np
import time
import datetime
import re
import heapq
from google.colab import auth
import gspread
from google.auth import default

# ==========================================
# ⚙️ 0. KULLANICI PARAMETRELERİ (ÇALIŞTIRAN KİŞİ BURAYI SEÇECEK)
# ==========================================
CALISILAN_DEPO = "test"             # Çıktı dosyasının adı olacak (Örn: Maltepe, Gebze vs.)
CALISILAN_KATEGORI = "Ambient ve Su"   # Bu kod Ambient ve Su olduğu için sabit kalabilir

# ==========================================
# ⚙️ 1. AYARLAR VE DOSYA YOLLARI
# ==========================================
MAX_SATIR_LIMITI = 10000
MAX_KOLI_LIMITI = 20000
HARD_STOP_CAPACITY = 1.10   # varsayılan esnek hacim tavanı — yalnız Buffer Rates sekmesinde olmayan depolara uygulanır
PALETIN_YUZDE_KACI = 0.35

DIKEY_MIN_PAY = 0.25   # dikey palette her SKU en az %25 pay almalı

# 🧪 SADECE A TESTİ (20.11.2026) — bu depolara yalnız ABC class 'A' ürünler gider (su dahil); B/C/D (ve sınıfı boş)
#    en baştan sıfır. Dokunulmazlık (kampanya/waste) uygulanmaz. Yalnız yer kontrolü: ambient dolap hacmi, su için su
#    palet alanı. TIR palet limiti uygulanmaz; merkez satır/koli limiti bu depoların satırlarını kesmez (satırlar merkez
#    sayımına dahil). Sayım ve merkez su stoğu (End Balance DC) geçerli. Depo adı Türkçe karakter / boşluk duyarsız.
SADECE_A_TEST_DEPOLARI = ['Atakent']
SADECE_A_REASON = 'Test: Sadece A Segmenti'

# 🎯 WEIGHTED AVA DEPOLARI (23.11.2026) — bu depolarda 99 puanı (Listed / Supply Shortage koruması) yok: bu ürünler
#    kendi ABC/cover puanına düşer, böylece kesim sırası ABC'ye paralel olur (A/B'nin 6,5/7,5 cover kuralları aynen).
#    Kampanya/Waste (100), demirbaş (101) ve Pick-to-zero (Cold, 99) korumaları sürer. Depo adı Türkçe karakter / boşluk duyarsız.
WEIGHTED_AVA_DEPOLARI = ['UrartuBüyük', 'Lara', 'Akdeniz', 'Atatürk Üniversitesi', 'ÇambaşıBüyük', 'Soyak Yenişehir', 'Acarlar',
                         'Kanlıkavak', 'KutluBüyük', 'AydoğanBüyük', 'MaslakBüyük', 'BüyükbakkalköyBüyük', 'Profilo', 'Yeniköy',
                         'Çekmeköy', 'RamanBüyük', 'İncekBüyük', 'KızılayBüyük', 'Kalkınma']

# ==========================================
# 🏭 DİKEY ELLEÇLEME TEST DEPOLARI (LAYOUT KODLARI)
# ==========================================
MIDI_L1_DEPO_KODU = '602d30b91b34076d2ac7a0da'    # Elvankent

MINI_L1_DEPO_KODLARI = [
    '58b57c0e5993b40004e7216d',  # Zumrutevler
    '5dc32db6734a192200caddf9',  # Balcova
    '60e2f47c27092bc704d55596',  # Gozdagi
]
MINI_L2_DEPO_KODLARI = [
    '617fb16458878a6087255267',  # Bagcilar
    '5aaa81050c434d0004db52f2',  # Bati Atasehir
    '614da622e4228142317f151b',  # Gurpinar
    '60c86e90ebd4cafcdd51640b',  # Elcilikler
]
XS_L1_DEPO_KODLARI = [
    '58b4312f292ee600049fc76b',  # Cihangir
    '610295985258e5f8925b9f3b',  # Esrefpasa
    '6176c1d6593a60e5937db788',  # Kanlikavak
    '61238d86d00c3bfc6042f2fe',  # Anadolu Hisari
    '5f60cba31ad848c2e23904ba',  # Emirgan
    '583d63150cf7c000048f2033',  # Pendik
]
XS_L2_DEPO_KODLARI = [
    '602d2ceefff95e357d2499a3',  # Baglica
]
XS_L3_DEPO_KODLARI = [
    '5fa5090fec4ec10a14b3cc83',  # Zafer
]

# 🔁 V2 LAYOUT DEPOLARI (4 depoya özel güncel layout — diğer depolar eski layout'ta kalır)
XS_L1_V2_DEPO_KODLARI = ['5dc32e58734a192200caddfd']    # Guzelyali
XS_L2_V2_DEPO_KODLARI = ['586a31f3dc795000045aadf1']    # TEM Avrupa Konutlari
XS_L3_V2_DEPO_KODLARI = ['5faa3bea7a3424ad240e90ea']    # Meydankavagi
MINI_L2_V2_DEPO_KODLARI = ['5d7d34abaef51100013f23cf']  # Kuzguncuk

DIKEY_TEST_DEPO_KODLARI = [str(k).lower().strip() for k in (
    [MIDI_L1_DEPO_KODU] + MINI_L1_DEPO_KODLARI + MINI_L2_DEPO_KODLARI +
    XS_L1_DEPO_KODLARI + XS_L2_DEPO_KODLARI + XS_L3_DEPO_KODLARI +
    XS_L1_V2_DEPO_KODLARI + XS_L2_V2_DEPO_KODLARI + XS_L3_V2_DEPO_KODLARI + MINI_L2_V2_DEPO_KODLARI
)]

# ==========================================
# 🔀 SU → AMBIENT GEÇİŞİ (7 DEPOYA ÖZEL)
# ==========================================
AMBIENT_GECIS_URUNLERI = [
    '5b30d3c4cebeab0004808a00',
    '5a7b1f608e19da0004bb2706',
]
# Dikey 4 depo koddan, dikeysiz 3 depo addan eşleşir (kodları biliniyorsa buraya da eklenebilir)
AMBIENT_GECIS_DEPO_KODLARI = (XS_L1_V2_DEPO_KODLARI + XS_L2_V2_DEPO_KODLARI +
                              XS_L3_V2_DEPO_KODLARI + MINI_L2_V2_DEPO_KODLARI + [
    # 'alacaatli_kodu', 'torekent_kodu', 'asansor_kodu',
])
AMBIENT_GECIS_DEPO_AD_ANAHTAR = ['alacaatli', 'torekent', 'asansor']

AMBIENT_GECIS_URUNLERI_T = [str(x).lower().strip() for x in AMBIENT_GECIS_URUNLERI]
AMBIENT_GECIS_DEPO_KODLARI_T = [str(x).lower().strip() for x in AMBIENT_GECIS_DEPO_KODLARI]

_TR_MAP = str.maketrans('ıİşŞğĞüÜöÖçÇ', 'iissgguuoocc')

def _norm_ad(s):
    s = str(s).translate(_TR_MAP).lower()
    return re.sub(r'[^a-z0-9]', '', s)

def _ad_eslesir(ad):
    a = _norm_ad(ad)
    return any(k in a for k in AMBIENT_GECIS_DEPO_AD_ANAHTAR)

def _ambient_gecis_mask(loc_ad, loc_kod, prod):
    loc_ad = pd.Series(loc_ad)
    _kod = pd.Series(loc_kod, index=loc_ad.index).astype(str).str.lower().str.strip()
    _prd = pd.Series(prod, index=loc_ad.index).astype(str).str.lower().str.strip()
    _depo = _kod.isin(AMBIENT_GECIS_DEPO_KODLARI_T) | loc_ad.map(_ad_eslesir)
    return (_depo & _prd.isin(AMBIENT_GECIS_URUNLERI_T)).fillna(False).astype(bool)

# ==========================================
# 📦 DİKEY DEPO SABİT BATCH (OBS) TABLOSU
# ==========================================
DIKEY_DEPO_BATCH = {
    '5fbce44d7d580fc3304aee67': 1,
    '66ab86deeee276842220d0d9': 1,
    '642c2ad21631f0ea0b9bb3a0': 1,
    '66e29d43bbae44b6c5d3b9b0': 1,
    '66e29d2f798e4ec0b3881644': 1,
    '6304c187a3a9db67ff436dd2': 1,
    '6811ea8c1f692e53caa0fb7d': 1,
    '68711c6b05682ca49ade0362': 1,
    '6304b87e6c7c1a0eea79e01e': 1,
    '5a7b21f69ccf1d00040084bf': 2,
    '5981ec31e97e8b000484eb96': 2,
    '6811ed10ba8812453ab3c152': 2,
    '659fa14bbcb190b6630904de': 2,
    '66e29d3a0aa85482a2d3d5b3': 2,
    '6582a9c2b77a0d5b0a5b63f1': 2,
    '5a7b20fd8e19da0004bb27f8': 6,
    '5bdaa8ae13fd4900121665c3': 6,
    '659fa13a840f38903fe72bfe': 6,
    '6582a9acaeb2c80ce3643aab': 6,
    '5911e8a76dc435000404d472': 6,
    '5981eac3ffae51000428afc9': 6,
    '5b30d3c4cebeab0004808a00': 12,
    '5a7b1f608e19da0004bb2706': 12,
    '63e64188ae9b3e290fec7009': 12,
    '659fa008133de16aee7b7b17': 12,
    '5981e929ffae51000428aecd': 12,
}
DIKEY_DEPO_BATCH = {str(k).lower().strip(): v for k, v in DIKEY_DEPO_BATCH.items()}

_DIKEY_PALET_MAP = {
    'Midi Layout 1': {
        '5981ec31e97e8b000484eb96': (1, 'Dikey 5L (Tek SKU)'),
        '5a7b21f69ccf1d00040084bf': (2, 'Dikey 5L (Tek SKU)'),
        '6304b87e6c7c1a0eea79e01e': (3, 'Dikey 1.5L'),
        '6811ea8c1f692e53caa0fb7d': (3, 'Dikey 1.5L'),
        '5a7b20fd8e19da0004bb27f8': (4, 'Dikey 1.5L'),
        '5981eac3ffae51000428afc9': (4, 'Dikey 1.5L'),
        '5fbce44d7d580fc3304aee67': (5, 'Paylasimli 1L'),
        '5bdaa8ae13fd4900121665c3': (5, 'Paylasimli 1L'),
        '66ab86deeee276842220d0d9': (6, 'Paylasimli Kucukler'),
        '6304c187a3a9db67ff436dd2': (6, 'Paylasimli Kucukler'),
        '5a7b1f608e19da0004bb2706': (6, 'Paylasimli Kucukler'),
        '5b30d3c4cebeab0004808a00': (6, 'Paylasimli Kucukler'),
    },
    'Mini Layout 1': {
        '5981ec31e97e8b000484eb96': (1, 'Dikey 5L (Tek SKU)'),
        '5a7b21f69ccf1d00040084bf': (2, 'Dikey 5L (Tek SKU)'),
        '6304b87e6c7c1a0eea79e01e': (3, 'Dikey 1.5L'),
        '5a7b20fd8e19da0004bb27f8': (3, 'Dikey 1.5L'),
        '5fbce44d7d580fc3304aee67': (4, 'Paylasimli 1L'),
        '5bdaa8ae13fd4900121665c3': (4, 'Paylasimli 1L'),
        '5a7b1f608e19da0004bb2706': (5, 'Paylasimli Kucukler'),
        '5b30d3c4cebeab0004808a00': (5, 'Paylasimli Kucukler'),
    },
    'Mini Layout 2': {
        '5981ec31e97e8b000484eb96': (1, 'Dikey 5L (Tek SKU)'),
        '5a7b21f69ccf1d00040084bf': (2, 'Dikey 5L (Tek SKU)'),
        '6304b87e6c7c1a0eea79e01e': (3, 'Dikey 1.5L'),
        '5a7b20fd8e19da0004bb27f8': (3, 'Dikey 1.5L'),
        '5fbce44d7d580fc3304aee67': (4, 'Paylasimli Kucukler'),
        '5bdaa8ae13fd4900121665c3': (4, 'Paylasimli Kucukler'),
        '5a7b1f608e19da0004bb2706': (4, 'Paylasimli Kucukler'),
        '5b30d3c4cebeab0004808a00': (4, 'Paylasimli Kucukler'),
    },
    'XS Layout 1': {
        '5981ec31e97e8b000484eb96': (1, 'Dikey 5L'),
        '5a7b21f69ccf1d00040084bf': (1, 'Dikey 5L'),
        '6304b87e6c7c1a0eea79e01e': (2, 'Dikey 1.5L'),
        '5a7b20fd8e19da0004bb27f8': (2, 'Dikey 1.5L'),
        '5bdaa8ae13fd4900121665c3': (3, 'Paylasimli Kucukler'),
        '5a7b1f608e19da0004bb2706': (3, 'Paylasimli Kucukler'),
        '5b30d3c4cebeab0004808a00': (3, 'Paylasimli Kucukler'),
    },
    'XS Layout 2': {
        '5981ec31e97e8b000484eb96': (1, 'Dikey 5L (Tek SKU)'),
        '5a7b21f69ccf1d00040084bf': (2, 'Dikey 5L (Tek SKU)'),
        '6304b87e6c7c1a0eea79e01e': (3, 'Dikey 1.5L'),
        '5a7b20fd8e19da0004bb27f8': (3, 'Dikey 1.5L'),
        '5bdaa8ae13fd4900121665c3': (4, 'Paylasimli Kucukler'),
        '5a7b1f608e19da0004bb2706': (4, 'Paylasimli Kucukler'),
        '5b30d3c4cebeab0004808a00': (4, 'Paylasimli Kucukler'),
    },
    'XS Layout 3': {
        '5981ec31e97e8b000484eb96': (1, 'Dikey 5L'),
        '5a7b21f69ccf1d00040084bf': (1, 'Dikey 5L'),
        '6304b87e6c7c1a0eea79e01e': (2, 'Paylasimli Kalan'),
        '5a7b20fd8e19da0004bb27f8': (2, 'Paylasimli Kalan'),
        '5bdaa8ae13fd4900121665c3': (2, 'Paylasimli Kalan'),
        '5a7b1f608e19da0004bb2706': (2, 'Paylasimli Kalan'),
        '5b30d3c4cebeab0004808a00': (2, 'Paylasimli Kalan'),
    },
    # ---------- V2 LAYOUT'LAR (Guzelyali, TEM, Meydankavagi, Kuzguncuk) ----------
    'XS Layout 1 V2': {
        '5981ec31e97e8b000484eb96': (1, 'Dikey 5L'),
        '5a7b21f69ccf1d00040084bf': (1, 'Dikey 5L'),
        '6304b87e6c7c1a0eea79e01e': (2, 'Dikey 1.5L'),
        '5a7b20fd8e19da0004bb27f8': (2, 'Dikey 1.5L'),
        '5bdaa8ae13fd4900121665c3': (3, 'Paylasimli Kucukler'),
        '6304c187a3a9db67ff436dd2': (3, 'Paylasimli Kucukler'),
        '5fbce44d7d580fc3304aee67': (3, 'Paylasimli Kucukler'),
    },
    'XS Layout 2 V2': {
        '5981ec31e97e8b000484eb96': (1, 'Dikey 5L (Tek SKU)'),
        '5a7b21f69ccf1d00040084bf': (2, 'Dikey 5L (Tek SKU)'),
        '6304b87e6c7c1a0eea79e01e': (3, 'Dikey 1.5L'),
        '5a7b20fd8e19da0004bb27f8': (3, 'Dikey 1.5L'),
        '5bdaa8ae13fd4900121665c3': (4, 'Paylasimli Kucukler'),
        '6304c187a3a9db67ff436dd2': (4, 'Paylasimli Kucukler'),
        '5fbce44d7d580fc3304aee67': (4, 'Paylasimli Kucukler'),
    },
    'XS Layout 3 V2': {
        '5981ec31e97e8b000484eb96': (1, 'Dikey 5L'),
        '5a7b21f69ccf1d00040084bf': (1, 'Dikey 5L'),
        '6304b87e6c7c1a0eea79e01e': (2, 'Paylasimli Kalan'),
        '5a7b20fd8e19da0004bb27f8': (2, 'Paylasimli Kalan'),
        '5bdaa8ae13fd4900121665c3': (2, 'Paylasimli Kalan'),
        '6304c187a3a9db67ff436dd2': (2, 'Paylasimli Kalan'),
        '5fbce44d7d580fc3304aee67': (2, 'Paylasimli Kalan'),
    },
    'Mini Layout 2 V2': {
        '5981ec31e97e8b000484eb96': (1, 'Dikey 5L (Tek SKU)'),
        '5a7b21f69ccf1d00040084bf': (2, 'Dikey 5L (Tek SKU)'),
        '6304b87e6c7c1a0eea79e01e': (3, 'Dikey 1.5L'),
        '5a7b20fd8e19da0004bb27f8': (3, 'Dikey 1.5L'),
        '5fbce44d7d580fc3304aee67': (4, 'Paylasimli Kucukler'),
        '5bdaa8ae13fd4900121665c3': (4, 'Paylasimli Kucukler'),
        '6304c187a3a9db67ff436dd2': (4, 'Paylasimli Kucukler'),
    },
}

DIKEY_DEPO_LAYOUT = {}
for _k in [MIDI_L1_DEPO_KODU]:             DIKEY_DEPO_LAYOUT[str(_k).lower().strip()] = 'Midi Layout 1'
for _k in MINI_L1_DEPO_KODLARI:            DIKEY_DEPO_LAYOUT[str(_k).lower().strip()] = 'Mini Layout 1'
for _k in MINI_L2_DEPO_KODLARI:            DIKEY_DEPO_LAYOUT[str(_k).lower().strip()] = 'Mini Layout 2'
for _k in XS_L1_DEPO_KODLARI:              DIKEY_DEPO_LAYOUT[str(_k).lower().strip()] = 'XS Layout 1'
for _k in XS_L2_DEPO_KODLARI:              DIKEY_DEPO_LAYOUT[str(_k).lower().strip()] = 'XS Layout 2'
for _k in XS_L3_DEPO_KODLARI:              DIKEY_DEPO_LAYOUT[str(_k).lower().strip()] = 'XS Layout 3'
for _k in XS_L1_V2_DEPO_KODLARI:           DIKEY_DEPO_LAYOUT[str(_k).lower().strip()] = 'XS Layout 1 V2'
for _k in XS_L2_V2_DEPO_KODLARI:           DIKEY_DEPO_LAYOUT[str(_k).lower().strip()] = 'XS Layout 2 V2'
for _k in XS_L3_V2_DEPO_KODLARI:           DIKEY_DEPO_LAYOUT[str(_k).lower().strip()] = 'XS Layout 3 V2'
for _k in MINI_L2_V2_DEPO_KODLARI:         DIKEY_DEPO_LAYOUT[str(_k).lower().strip()] = 'Mini Layout 2 V2'

DIKEY_DEPO_SKU = {
    _kod: set(_DIKEY_PALET_MAP.get(_lay, {}).keys())
    for _kod, _lay in DIKEY_DEPO_LAYOUT.items()
}

GB_COVER_DAY_LIMIT = 6.0
G10_COVER_DAY_LIMIT = 4.0
A_MIN_COVER = 6.5
B_MIN_COVER = 7.5
C_MIN_COVER = 3.0

DOKUNULMAYACAK_URUNLER_G10 = [
       "588af61ef2532a0004000484", "6a206f3ecddd2d2428ddf56b", "6284ff7c03db2e33855b2227", "5b768e105b65a300042738b7",
    "5bc4b020e46dce001eb33eff", "68a2fc497d820f1e5f263e42", "68a2fc3cfa9c5a483b21b716", "6197ba8c6316883bafe032e8",
    "63c165dcb7a840277ad5390c", "65969cad5a103d5c025a7669", "65969d042c407fd3dceae244", "5ca77cc2d1b0a8000103db2c",
    "5cf2724a9463890001c3fc7b", "6461f2879b4d51d0f57f3559", "673714a10c2d8084bc4828bf", "66990addc0f970edb6d176af",
    "559831e0b1dc700c006a71b0", "5cdd79613cc2730001bb132f", "5cfe32bd4a644b0001f2076a", "6a047389e23222b30a9e2e56",
    "5ced4828d349d10001e70504", "5ce65823a72a950001cc88c0", "62bc0df9df86f299f5dac9c9", "5a004ce7c99cc70004c78a7e",
    "5cae01d93150750001edd9fb", "5df88f90780ecc5c88d56839", "655db769e6dc4a3f6eeb9d9d", "5eb3cc73d27f6821167c5491",
    "678e4dabe39e2a9b41b2cc80", "69528f571f95548f54e4b29f", "678e4db529037aebf4cc5d89", "6992c44f17ae33eb2b0f36f1",
    "6992c43b06fb235d757fa89d", "6992c44565c440515b29ddbc", "6992c432a948f8b680c95d9e", "61dd880bd9ed7fa9a7b8ae97",
    "61c56e97c9e60e203413cde5", "55b259f3a7602a0c0019cabc", "57ce9d348ada940300f85d67", "590888a1838b130004808f45",
    "5efc5718fcdccbdf0160c361", "5efc594a605c1ed49d4d7eac", "60e59f5c482d5e7dae49ef92", "55b25973a7602a0c0019ca99",
    "6a2adf43408fc8f5f9f3427d", "6a2adde90d0ebac942a2b310", "6a329f0cbb9df4c3e6ffe758", "55d2f07fd99c8f0c006e0a8c",
    "55d2ef4ad99c8f0c006e0a15", "6a271ad057c2a50d81830ef0", "6a271bd79289b9c298118264", "5ce65824a72a950001cc88ef",
    "5ce6581afd9b330001c4a85b", "6304b87e6c7c1a0eea79e01e", "5f9174ff367f353300bb98ec", "5f9171d579d9116df06e6cdf",
    "67daa2a0bc9d68f77d5fc73c", "6a05836f27346683da1a670a", "5832ce9554857e00041652dd", "586b9b30aabf9a0004bb61db",
    "5ce6580ea72a950001cc8731", "5ceae038c461e70001cc9808", "5fe9910568293a8eb7677fb4", "5bc757c608f9730036d99fd8",
    "619b39009c77273abc8a15b2", "5cf00cd58ebae600018b942f", "58a1b6707ba9660004c96471", "5baa13ad1bcb7c7a0da5e802",
    "67652db6ef0940dac336eb03", "5b6461403c75db0004c6cb72", "5683e84c06df100f0046fc8f", "5bbc5b4cf612c20ea3f4bcfc",
    "6540f88b304475ff07e4eb87", "64f974b025fd4149b563b68e", "64f97b2e792312a9f0bd9e0a", "6729bf2cd486b4e313c693fa",
    "6729bf40a110d4a938d4472a", "5cb8e2daff9117000171adde", "69b9a600c051a091f7b8cb84", "693974cdda8fae9114ba06e3",
    "693974d788585a4c2efb2f49", "5bb89dab3f98e4001e22810c", "61a8cee952b1ab8366c7e083", "63917aec64198fdfb9a34377",
    "5f8380543eb6546a2775d008", "693974e19ea9c1c45081aa3f", "63519e7e79b1381b8c9e281b", "612e15f0b80e0342ea9b6749",
    "574b2219dee8a90300f18d24", "59b14d42b573340004d1a143", "62fa08957432fa01a2f717e5", "6304e7e0e48b890657935624",
    "61813c63941c1e7f957c8c60", "5ac7795b599fa70004cb73d4", "5ac7798ec68ac90004a070bb", "55a004bf35a77b0c0075cd0c",
    "63847eaf5added0c73ca3a44", "638ca48127547f0cd63009b3", "5d03bb6789c5f10001c36b3a", "5fcdedfc86e43d58746d088b",
    "65707786c7792a51683603cc", "600cad6614fc5316e39eb332", "59477b2a93463800043cb05f", "5f2ba2fe722d827b5a5bf189",
    "61b855644ab266cfd20e9701", "66fe53d74556767886b52b08", "66fe53cd962712ee9721c71e", "66fe53c0f78d2e48efd6abec",
    "5d03bb6789c5f10001c36b35", "5a7b21f69ccf1d00040084bf", "668fc116cf5912f993160459", "668fccd5c7283129e71b2fac",
    "668fc135743b16364e0fc398", "6787b4fc8523820185c16e9a", "668fc241e16678cb7c857ca0", "5bbdbbbaa6e9de25524a27fc",
    "6787b4f2f3eacd2ba0065b23", "5b62cb88fb2eea00042dc2c0", "64ae942571c99fed8f754886", "668fc12180c1141f3f4bcf6c",
    "60018c5bca2126d84459c47f", "668fc12bc0fd6e0e46027d1f", "5d0b918feb66850001859259", "63ee3a4738bb1682fe7d061a",
    "6787b4e9bcfa02e79b58165f", "689af81719857e8352969849", "69809555a799e9ccceb19b46", "699ee6b50aeff121172007bf",
    "56dafd4d76d96e030066497f", "5ce6581dfd9b330001c4a8b0", "692aa5aff65b0d7812f8cb95", "619cc11b939e5301c0b48d9c",
    "5ced48314a8a2a000137dab7", "5ce65822fd9b330001c4a9a0", "699704d9ac9d5cdbca6c3117", "5ced4832d349d10001e7059c",
    "60d0f5e575a5fccaab2a8ff0", "69f9a83ccb01c7fa65371b80", "69f9cb6644544cb5a4457bad", "69f9c7e2741406eaab345372",
    "69f9a96dff62e2189675bfce", "64e3418e548133e8e5bb502f", "68a332114df8bccbf1cf2345", "5e3a96b7b6e4422200f7e3a0",
    "6238698ce60a0f02dee33ca1", "6422e8b52cb445fbfc9e031e", "68a331f9326b89637f0793e7", "6422e8b7a9955d25245e159b",
]
DOKUNULMAYACAK_URUNLER_GB = [
    "66fe53d74556767886b52b08", "66fe53cd962712ee9721c71e", "66fe53c0f78d2e48efd6abec", "5d03bb6789c5f10001c36b35",
    "5ce65818fd9b330001c4a83e", "63bc88bd8ee27c71e0262e3d", "6551d69ba6df391007a8ed94", "6551dc761d6c1393a82cdb2c",
    "6a207194703e87cccb928598", "63e62e07b72d01d717dcc279", "641ae42b2cb445fbfc9d4507", "566031ffbd8dab0c00937b60",
    "695cf95ed602415532cd5431", "69d4e1619ab1f47d26f86e99", "65969e5a5e96a86b121f2263", "669909ace07f24d2bb7a766f",
    "616052c9d6439998da2cbfc1", "691c39820b1ff68cd86bff22", "69aeb9cf5383ebe7ccf84a9a", "5bc595e8be25480017255546",
    "659f8af17209dcdf6f55bf19", "659f8b003d91c592df705f02", "6565f97b4059bdacc50b33a9", "6a6b255a3a29f6c5bc2e3eff",
    "690b528b21cce36b2c81b51a", "60b603f043da950f025bb275", "68c41f3314a2782bb69e8c01", "65731b8e87016ceb1192c8e5",
    "65731b8e74c079439cc5f54a", "65731cb9552117f74b504a90", "65731b8ee8887921e080121f", "6a4b97bd3d8d79a26599c788",
    "6a4b9c640d8d0e8f57be61a8", "67a0c1dfb5e65262a979c30f", "623aea348edc5f3dbed0c3dc", "618276e27ab088e71b89c1f8",
    "6605737980987e9d94f8c7da", "660573824089c8af0099418b", "614dab98472682f67ab1c881", "618e2a4af145bc675f7f12da",
    "68b5933115a01c54dc1867e7", "692ada70b2b4cc47cbebab17", "69b15dfbc65a4db97cf4718f", "5c8a822ac7606200016727c4",
    "5e1731d8594057b67254ab8b", "602f5949e5f1431ceec72478", "5ef3140c6b28dc4894aaec11", "602f592ddc0d6d5e2e1cdf4f",
    "615ee2304565acec180de197", "6992c414b29dd0baf2081f98", "5cf3d88b4f843c0001d98667", "5ced4831d349d10001e7056d",
    "691c54288e6b976b0a410616", "628e3f3488145c54a408f851", "6598198a2263a29cebd6bb6e", "66ff9b26019c41b49264ec49",
    "66ff9b1931df2adf9dccc008", "5a279a26f5a2790004ee21d7", "6352a1bf0101e85cacea2446", "5d03bb6689c5f10001c36b2e",
    "600caee13e046f467d696552", "649407c4204f67ab25d5a01b", "6453d39674d0c1732be19548", "6453d3ee74d0c1732be19552",
    "6880d4aef9f3e4ad425d0b61", "5ce6581ea72a950001cc87e5", "6802576661bfd4e5b66b3217", "5cfe32bd010040000122ff12",
    "5ac760c1679a5e0004bf4155", "5ac761a2b306630004c8dc4b", "5ac4b343138ef30004553092", "5ac7621ab306630004c8dc8b",
    "5ac762c7b306630004c8dcfc", "572301d7d4549603004bc826", "67e274269ba7e09dae33f450", "67e27434c4f9530f78256c8a",
    "6a2bea3cf2b9a4aaec0d1ef8", "6a0f14aee69e86029f5a76b6", "6a0f1382db85d84b1209e4e5", "6a32bb2cb0ab0d7fbe71a31f",
    "5bceca90cf48f700126f5db5", "603e030d1880692932cacb5a", "5bcec8fd9c50285679ac15ab", "5a7b1f608e19da0004bb2706",
    "671a0cd79bb66471141959d5", "5cb8e11669c3750001042b44", "5ad5afaa11d0bf0004e07147", "559831b7b1dc700c006a71a8",
    "699c06cb577a120c0833c0ea", "5cf272559463890001c3fd4c", "60d9eed98b4b0b39ea9c116b", "5614e7c088047e0c00c22951",
    "66ed5111b5ac2d68282d9b45", "5614e88688047e0c00c2298f", "559ddb895dc7a20c0016621a", "5f353062579f1f6e9bcfa98f",
    "696e482fd131a88b7b013fbc", "696e48253400f8142e0088fa", "647eecf1625e9b4e8ec04a89", "647eecc7b1b28d9221763247",
    "672dd45bcb565cf9a95e1c06", "68ee250afe76a0fedcb094f5", "5f43cbae03564256136b01a9", "699704a8f8594b29b1ad7107",
    "65fad0fd2f687850a691185b", "5fc26ef5f86ca13ef0fdae59", "6821d7d193dd86b9e9010364", "5cfe32bd4a644b0001f20774",
    "5898a1d0a4502d0004af9aeb", "566031ffbd8dab0c00937b60", "6a3be2f7d5903e9ba8cc6573", "6a3be42ac783a43756216a81",
    "5e54db1c448af7ffd339fe48", "5a7b21f69ccf1d00040084bf", "6224010c6fa886a3b1f26cd4", "5755322df43fe40300152b00",
    "5ced482dd349d10001e70531", "668fc116cf5912f993160459", "668fccd5c7283129e71b2fac", "668fc135743b16364e0fc398",
    "6787b4fc8523820185c16e9a", "668fc241e16678cb7c857ca0", "5bbdbbbaa6e9de25524a27fc", "6787b4f2f3eacd2ba0065b23",
    "5b62cb88fb2eea00042dc2c0", "64ae942571c99fed8f754886", "668fc12180c1141f3f4bcf6c", "60018c5bca2126d84459c47f",
    "668fc12bc0fd6e0e46027d1f", "5d0b918feb66850001859259", "63ee3a4738bb1682fe7d061a", "6787b4e9bcfa02e79b58165f",
    "689af81719857e8352969849", "69809555a799e9ccceb19b46", "699ee6b50aeff121172007bf", "56dafd4d76d96e030066497f",
    "5ce6581dfd9b330001c4a8b0", "692aa5aff65b0d7812f8cb95", "619cc11b939e5301c0b48d9c", "5ced48314a8a2a000137dab7",
    "5ce65822fd9b330001c4a9a0", "699704d9ac9d5cdbca6c3117", "5ced4832d349d10001e7059c", "60d0f5e575a5fccaab2a8ff0",
    "69f9a83ccb01c7fa65371b80", "69f9cb6644544cb5a4457bad", "69f9c7e2741406eaab345372", "69f9a96dff62e2189675bfce",
    "64e3418e548133e8e5bb502f", "68a332114df8bccbf1cf2345", "5e3a96b7b6e4422200f7e3a0", "6238698ce60a0f02dee33ca1",
    "6422e8b52cb445fbfc9e031e", "68a331f9326b89637f0793e7", "6422e8b7a9955d25245e159b",
]

DOSYA_RELEX = '/content/arn amb relex son 1210.xlsx'
# 📦 SİM (ürün palet bilgisi: SKUkodu, SON) — eskiden "Sim <tarih>.xlsx" dosyasıydı, artık sheet
GSHEET_SIM_URL = 'https://docs.google.com/spreadsheets/d/1FArHRLZdwrXcOHOHCK3skES7xGSPABNEm97jIK8H64E/edit'
SIM_GID = 823638127   # <-- GID'i buraya gir
DOSYA_DUNKU_RAPOR = '/content/backlog arn amb 1210.xlsx'
GSHEET_URUN_URL = 'https://docs.google.com/spreadsheets/d/1FArHRLZdwrXcOHOHCK3skES7xGSPABNEm97jIK8H64E/edit?gid=1615488785#gid=1615488785'
URUN_GID = 1615488785
GSHEET_AMBIENT_URL = 'https://docs.google.com/spreadsheets/d/1FArHRLZdwrXcOHOHCK3skES7xGSPABNEm97jIK8H64E/edit?gid=1473098648#gid=1473098648'
AMBIENT_GID = 1473098648
# 🚚 GÜNLÜK TIR PALET LİMİTİ SHEET'İ (Depo Adı + Pazartesi..Pazar kolonlari)
# TEK KAYNAK. Sheet'te olmayan depo → kod ici default (G10=12 / GB=25)
GSHEET_GUNLUK_PALET_URL = 'https://docs.google.com/spreadsheets/d/1FArHRLZdwrXcOHOHCK3skES7xGSPABNEm97jIK8H64E/edit?gid=670096216#gid=670096216'
GUNLUK_PALET_GID = 670096216            # <-- GID'i buraya gir
GSHEET_SCHEDULE_URL = 'https://docs.google.com/spreadsheets/d/1Rx0FxFAPbjJ9pdLfjwcUFluDITDjm8gmvnDvgbW2lGc/edit?gid=502994405#gid=502994405'
SCHEDULE_GID = 502994405

# 📋 SAYIM PLANI SHEET'İ (Tarih, Tarih Açıklama, Depo Kodu, Depo Tipi, Sayım Türü ...)
GSHEET_SAYIM_URL = 'https://docs.google.com/spreadsheets/d/1FArHRLZdwrXcOHOHCK3skES7xGSPABNEm97jIK8H64E/edit?gid=1468314948#gid=1468314948'   # <-- Sayım planı sheet linkini buraya gir
SAYIM_GID = 1468314948           # <-- GID'i buraya gir

# ==========================================
# 📋 SAYIM KURALLARI (AMBIENT) — teslimat ALINMAYACAK gün aralığı
#    T = sayım tarihi, aralığın iki ucu da dahil. Örn (-3, -1) → T-3, T-2, T-1
# ==========================================
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
        (_SAYIM_GECELER[:1], (-3, -1)),                                        # Pazar→Pzt gecesi
        (_SAYIM_GECELER[1:], (-2, -1)),                                        # diğer geceler
        (_gunduz('Pazar', 'Pazartesi'), (-2, 0)),
        (_gunduz('Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi'), (-1, 0)),
    ],
    ('G10', 'Rutin'): [
        (_SAYIM_GECELER, (-1, 0)),
        (_TUM_GUNDUZ, (0, 1)),
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

_NEDEN_SAYIM = 'Sayım'

# ⚡ FAST ACCAPTENCE KAYNAGI (ayni dosya, gid'i asagiya gir)
GSHEET_FAST_ACC_URL = 'https://docs.google.com/spreadsheets/d/1FArHRLZdwrXcOHOHCK3skES7xGSPABNEm97jIK8H64E/edit'
FAST_ACC_GID = 1181864150   # <-- GID'i buraya gir

# 🎯 KAMPANYA ÜRÜNLERİ KAYNAĞI (ayni dosya) — "Dokunulmayacak Ürünler (Kampanya)" sekmesi: G10 T-1 | GB T-1 | G10 T | GB T
GSHEET_KAMPANYA_URL = 'https://docs.google.com/spreadsheets/d/1FArHRLZdwrXcOHOHCK3skES7xGSPABNEm97jIK8H64E/edit'
KAMPANYA_GID = 1527796592   # <-- GID'i buraya gir

DOSYA_WATER_WH = '/content/Water WH Utilization % With Relex New (35%) 1210.csv'
# 💧 SU PALET BİLGİLERİ (Product ID, sıra, palet) ve SU PALET ALANI (Depo, palet limiti) — eskiden dosya, artık sheet
GSHEET_SU_LISTE_URL = 'https://docs.google.com/spreadsheets/d/1FArHRLZdwrXcOHOHCK3skES7xGSPABNEm97jIK8H64E/edit'
SU_LISTE_GID = 1975210347   # <-- GID'i buraya gir
GSHEET_SU_PALET_ALANI_URL = 'https://docs.google.com/spreadsheets/d/1FArHRLZdwrXcOHOHCK3skES7xGSPABNEm97jIK8H64E/edit'
SU_PALET_ALANI_GID = 868077377   # <-- GID'i buraya gir
# 📐 DEPO BAZLI ESNEK HACİM TAVANI — "Buffer Rates" sekmesi (Depo Adı | Ambient Buffer | Cold Limit); Ambient 'Ambient Buffer' kolonunu kullanır
GSHEET_BUFFER_URL = 'https://docs.google.com/spreadsheets/d/1FArHRLZdwrXcOHOHCK3skES7xGSPABNEm97jIK8H64E/edit'
BUFFER_GID = 1173976478   # <-- GID'i buraya gir

print("Veriler yükleniyor...")
start_time = time.time()

auth.authenticate_user()
creds, _ = default()
gc = gspread.authorize(creds)

# ==========================================
# 📥 2. VERİ OKUMA VE HAZIRLIK KANALLARI
# ==========================================
def read_and_clean_excel(path):
    d = pd.read_excel(path)
    d.columns = [str(c).strip() for c in d.columns]
    return d

def clean_locale_number(val):
    if pd.isna(val): return 0.0
    if isinstance(val, (int, float)): return float(val)
    val = str(val).strip()
    if not val or val == '-': return 0.0
    if ',' in val and '.' in val:
        if val.rfind(',') > val.rfind('.'):
            val = val.replace('.', '').replace(',', '.')
        else:
            val = val.replace(',', '')
    elif ',' in val:
        val = val.replace(',', '.')
    elif val.count('.') > 1:
        val = val.replace('.', '')
    val = re.sub(r'[^\d\.\-]', '', val)
    try: return float(val)
    except: return 0.0

def clean_ratio(val):
    val_str = str(val).strip()
    if '%' in val_str:
        try: return float(val_str.replace('%', '')) / 100.0
        except: return 0.0
    else:
        try:
            v = float(val_str)
            if v > 1.5: return v / 100.0
            return v
        except: return 0.0

df_relex = read_and_clean_excel(DOSYA_RELEX)

def sheet_tablo(url, gid):
    """Sheet sekmesi → DataFrame (ilk satır başlık, tamamen boş satırlar atılır; değerler metin)."""
    v = gc.open_by_url(url).get_worksheet_by_id(gid).get_all_values()
    if not v:
        raise ValueError(f"Sheet sekmesi boş (gid {gid})")
    d = pd.DataFrame([r for r in v[1:] if any(str(x).strip() for x in r)], columns=[str(c).strip() for c in v[0]])
    return d.loc[:, [c for c in d.columns if c]]

def sheet_sayi(x):
    """Sheet hücresi → sayı ('2.508' / '2,508' binlik, '1,5' ondalık); boş ya da '-' → NaN; sayı değilse metin aynen (ör. 'batch eşitle')."""
    t = str(x).strip()
    if t in ('', '-'): return np.nan
    if re.fullmatch(r'\d{1,3}(\.\d{3})+', t): t = t.replace('.', '')
    elif ',' in t and '.' in t: t = t.replace('.', '').replace(',', '.') if t.rfind(',') > t.rfind('.') else t.replace(',', '')
    else: t = t.replace(',', '.')
    try: return float(t)
    except ValueError: return x

df_palet = sheet_tablo(GSHEET_SIM_URL, SIM_GID)
df_palet['SON'] = df_palet['SON'].map(sheet_sayi)
print(f"📦 Sim: {len(df_palet)} ürün")
df_dunku_rapor = read_and_clean_excel(DOSYA_DUNKU_RAPOR)

sh_urun = gc.open_by_url(GSHEET_URUN_URL)
ws_urun = sh_urun.get_worksheet_by_id(URUN_GID)
urun_data = ws_urun.get_all_values()
df_urun = pd.DataFrame(urun_data[1:], columns=[str(c).strip() for c in urun_data[0]])

sh_ambient = gc.open_by_url(GSHEET_AMBIENT_URL)
ws_ambient = sh_ambient.get_worksheet_by_id(AMBIENT_GID)
ambient_data = ws_ambient.get_all_values()
df_ambient = pd.DataFrame(ambient_data[1:], columns=[str(c).strip() for c in ambient_data[0]])

# ==========================================
# 🚚 GÜNLÜK TIR PALET LİMİTİ (haftanın gününe göre)
# ==========================================
_GUN_ADLARI = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']
_BUGUN_NO = pd.Timestamp.now().normalize().weekday()
_BUGUN_ADI = _GUN_ADLARI[_BUGUN_NO]

GUNLUK_PALET_LIMIT = {}
try:
    _sh_gp = gc.open_by_url(GSHEET_GUNLUK_PALET_URL)
    _ws_gp = _sh_gp.get_worksheet_by_id(GUNLUK_PALET_GID)
    _gp_data = _ws_gp.get_all_values()
    _df_gunluk = pd.DataFrame(_gp_data[1:], columns=[str(c).strip() for c in _gp_data[0]])

    # Depo kolonu: adinda 'depo' gecen ilk kolon, yoksa ilk kolon
    _gp_depo_col = next((c for c in _df_gunluk.columns if 'depo' in _norm_ad(c)), _df_gunluk.columns[0])

    # Gun kolonu: bugunun adiyla eslesen kolon (Turkce karakter/bosluk duyarsiz)
    _gun_hedef = _norm_ad(_BUGUN_ADI)
    _gp_gun_col = next((c for c in _df_gunluk.columns if _norm_ad(c) == _gun_hedef), None)

    if _gp_gun_col is None:
        print(f"⚠️  Günlük palet sheet'inde '{_BUGUN_ADI}' kolonu bulunamadı "
              f"→ günlük limit uygulanmayacak. Kolonlar: {_df_gunluk.columns.tolist()}")
    else:
        for _, _gr in _df_gunluk.iterrows():
            _ad = _norm_ad(_gr[_gp_depo_col])
            if not _ad: continue
            _lim = clean_locale_number(_gr[_gp_gun_col])
            if _lim > 0:
                GUNLUK_PALET_LIMIT[_ad] = _lim
        print(f"🚚 Günlük palet limiti ({_BUGUN_ADI}): {len(GUNLUK_PALET_LIMIT)} depo okundu")
except Exception as _e:
    print(f"⚠️  Günlük palet limiti sheet'i okunamadı → eski kaynaklar kullanılacak. Hata: {_e}")

sh = gc.open_by_url(GSHEET_SCHEDULE_URL)
ws = sh.get_worksheet_by_id(SCHEDULE_GID)
schedule_data = ws.get_all_values()
df_schedule = pd.DataFrame(schedule_data[1:], columns=[str(c).strip() for c in schedule_data[0]])
df_schedule = df_schedule[df_schedule['custom_transfer_type'] == 'Ambient']
df_schedule = df_schedule.drop_duplicates(subset=['location'])

# ==========================================
# 📋 SAYIM PLANI OKUMA
# ==========================================
SAYIM_KAYITLARI = {}   # depo kodu -> [sayım kayıtları]
df_sayim = pd.DataFrame()
if not GSHEET_SAYIM_URL:
    print("🚨 SAYIM PLANI LİNKİ GİRİLMEMİŞ → sayım kısıtı UYGULANMAYACAK!")
else:
    try:
        _s_data = gc.open_by_url(GSHEET_SAYIM_URL).get_worksheet_by_id(SAYIM_GID).get_all_values()
        df_sayim = pd.DataFrame(_s_data[1:], columns=[str(c).strip() for c in _s_data[0]])
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
              f"Kolonlar: {df_sayim.columns.tolist()}")
    else:
        # Sheet'te depo tipi boşsa Relex'teki depo tipine düşülür
        _relex_tip = (df_relex.dropna(subset=['Location code'])
                      .assign(_k=lambda d: d['Location code'].astype(str).str.lower().str.strip())
                      .drop_duplicates('_k').set_index('_k')['Domain Type'].to_dict())
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
                'aciklama': _acik, 'tur': _tur, 'tip': _tip, 'depo_adi': _ad})
        print(f"📋 Sayım planı: {sum(len(v) for v in SAYIM_KAYITLARI.values())} sayım / "
              f"{len(SAYIM_KAYITLARI)} depo okundu")
        if _tanimsiz:
            print(f"   ⚠️  Kurala eşlenemeyen {len(_tanimsiz)} sayım satırı ATLANDI "
                  f"(tarih/açıklama/tip/tür tanınmadı):")
            for _t in _tanimsiz[:15]: print(f"      - {_t}")

# ==========================================
# ⚡ FAST ACCAPTENCE DEPO LISTESI
# ==========================================
sh_fast = gc.open_by_url(GSHEET_FAST_ACC_URL)
ws_fast = sh_fast.get_worksheet_by_id(FAST_ACC_GID)
fast_data = ws_fast.get_all_values()
df_fast = pd.DataFrame(fast_data[1:], columns=[str(c).strip() for c in fast_data[0]])

_fast_col = next((c for c in df_fast.columns if str(c).strip().lower() == 'depo'), df_fast.columns[0])
FAST_ACC_DEPOLAR = set(
    df_fast[_fast_col].astype(str).str.strip().str.lower()
    .replace('', np.nan).dropna().unique()
)
FAST_ACC_DEPOLAR.discard('depo')
print(f"⚡ Fast Accaptence listesi: {len(FAST_ACC_DEPOLAR)} depo okundu")

# ==========================================
# 🎯 KAMPANYA ÜRÜNLERİ (dokunulmayacak, sheet'ten otomatik)
# Sekme her perşembe güncellenir: T = önümüzdeki haftanın (pazartesi başlayan) kampanyaları, T-1 = içinde bulunulan haftanınkiler.
# Hangi liste: perşembe koşusunda teslimatı ertesi güne (cuma) düşen N+1 depolar T-1'i, N+2 depolar (cumartesi) T'yi alır;
# diğer günler hep T. DOKUNULMAYACAK_URUNLER_G10/GB (arayüzden elle) = Waste. İkisi de 100 puan; ikisinde de olan ürün 'Kampanya'.
# ==========================================
def kampanya_listeleri(veri):
    """get_all_values çıktısı → {('G10' | 'GB', 'T' | 'T-1'): {ürün kodu (küçük harf)}}; '-' ve boşlar atlanır."""
    if not veri or not veri[0]:
        return {}
    bas = [re.sub(r'\s+', ' ', str(c)).strip().upper() for c in veri[0]]
    out = {}
    for dom in ('G10', 'GB'):
        for hafta in ('T-1', 'T'):
            ad = f'{dom} {hafta}'
            if ad not in bas:
                print(f"   ⚠️  Kampanya sekmesinde '{ad}' kolonu yok → boş sayıldı")
                continue
            j = bas.index(ad)
            out[(dom, hafta)] = {str(r[j]).strip().lower() for r in veri[1:]
                                 if j < len(r) and re.fullmatch(r'[0-9a-fA-F]{24}', str(r[j]).strip())}
    return out

KAMPANYA_LISTELERI = kampanya_listeleri(gc.open_by_url(GSHEET_KAMPANYA_URL).get_worksheet_by_id(KAMPANYA_GID).get_all_values())
print("🎯 Kampanya listesi: " + ", ".join(f"{d} {h} {len(KAMPANYA_LISTELERI.get((d, h), ()))}" for d in ('G10', 'GB') for h in ('T-1', 'T')) + " ürün")

for i in range(7):
    col_name = f'order_{i}'
    if col_name in df_schedule.columns:
        df_schedule[col_name] = df_schedule[col_name].astype(str).str.upper().isin(['TRUE', '1', '1.0'])

if 'Location name' not in df_ambient.columns:
    olasi_depo_sutunlari = [c for c in df_ambient.columns if 'depo' in str(c).lower()]
    if olasi_depo_sutunlari:
        df_ambient.rename(columns={olasi_depo_sutunlari[0]: 'Location name'}, inplace=True)
    else:
        df_ambient.rename(columns={df_ambient.columns[0]: 'Location name'}, inplace=True)

ratio_cols = [c for c in df_ambient.columns if 'totalambientratio' in str(c).lower().replace(" ", "")]
if ratio_cols: df_ambient[ratio_cols[0]] = df_ambient[ratio_cols[0]].apply(clean_ratio)

ambient_keep = ['Location name', 'Total Ambient Ratio (In Transit Included)',
                'ambient_volume Litre', 'ambient_volume Litre (Total Transit)',
                'Avg. ambient_dolap_hacim', 'today_forecast', 'next_day_forecast', 'next_2_days_forecast']

guncel_keep = ['Location name']

for hedef_sutun in ambient_keep[1:]:
    hedef_temiz = str(hedef_sutun).lower().replace(" ", "").replace("(", "").replace(")", "").replace("_", "")
    eslesen_sutun = None
    for c in df_ambient.columns:
        c_temiz = str(c).lower().replace(" ", "").replace("(", "").replace(")", "").replace("_", "")
        if hedef_temiz == c_temiz:
            eslesen_sutun = c
            break
    if not eslesen_sutun:
        kelimeler = str(hedef_sutun).lower().replace("(", "").replace(")", "").replace("_", " ").split()
        for c in df_ambient.columns:
            if all(k in str(c).lower().replace("_", " ") for k in kelimeler):
                eslesen_sutun = c
                break
    if eslesen_sutun:
        guncel_keep.append(eslesen_sutun)
    else:
        df_ambient[hedef_sutun] = 0.0
        guncel_keep.append(hedef_sutun)

df_ambient = df_ambient[guncel_keep]
df_ambient.columns = ambient_keep

numeric_cols = ['ambient_volume Litre', 'ambient_volume Litre (Total Transit)',
                'Avg. ambient_dolap_hacim', 'today_forecast', 'next_day_forecast', 'next_2_days_forecast']

for col in numeric_cols:
    df_ambient[col] = df_ambient[col].apply(clean_locale_number)

relex_keep = ['Product code', 'Product name', 'Location code', 'Location name', 'Domain Type',
              'Order batch size', 'End balance', 'End Balance DC', 'Open purchase orders',
              'Effective quantity', 'Delivery date', 'Daily FC', 'ABC class',
              'Custom category', 'Custom sub-category', 'Son 14 Günlük Bulunurluk', 'Segment']
# Relex '14 Days Sales' (son 14 günlük satış, adet): ana çıktıya taşınır, arayüzdeki büyük öneri uyarısı kullanır. Kesime girmez.
_c14 = next((c for c in df_relex.columns if ' '.join(str(c).lower().split()) == '14 days sales'), None)
if _c14 is not None:
    df_relex = df_relex.rename(columns={_c14: '14 Days Sales'})
    df_relex['14 Days Sales'] = pd.to_numeric(df_relex['14 Days Sales'], errors='coerce')
    relex_keep = relex_keep + ['14 Days Sales']
df_relex = df_relex[relex_keep]

if 'Son 14 Günlük Bulunurluk' in df_relex.columns:
    df_relex['Son 14 Günlük Bulunurluk'] = df_relex['Son 14 Günlük Bulunurluk'].apply(clean_ratio)

df_relex['Product code'] = df_relex['Product code'].astype(str).str.lower().str.strip()
df_palet['SKUkodu'] = df_palet['SKUkodu'].astype(str).str.lower().str.strip()
df_urun['marketproduct_id'] = df_urun['marketproduct_id'].astype(str).str.lower().str.strip()

df_urun = df_urun.drop_duplicates(subset=['marketproduct_id'])
df_palet = df_palet.drop_duplicates(subset=['SKUkodu'])
df_ambient = df_ambient.drop_duplicates(subset=['Location name'])

if 'Depo_Final_Palet_Toplami' not in df_dunku_rapor.columns:
    print("⚠️  Dünkü raporda 'Depo_Final_Palet_Toplami' yok → 0 kabul edildi. "
          f"Mevcut kolonlar: {df_dunku_rapor.columns.tolist()[:15]}")
    df_dunku_rapor['Depo_Final_Palet_Toplami'] = 0.0

df_dunku_sade = df_dunku_rapor.groupby('Location name').agg({
    'Depo_Final_Palet_Toplami': 'first',
    'Backlog_Palet_Sayisi': 'first'
}).reset_index().rename(columns={'Depo_Final_Palet_Toplami': 'Dunun_Siparisi_Palet'})

df = pd.merge(df_relex, df_ambient, on='Location name', how='left')
df = pd.merge(df, df_palet[['SKUkodu', 'SON']], left_on='Product code', right_on='SKUkodu', how='left')
df = pd.merge(df, df_urun[['marketproduct_id', 'hacim2']], left_on='Product code', right_on='marketproduct_id', how='left')

df = pd.merge(df, df_dunku_sade, on='Location name', how='left')
df[['Dunun_Siparisi_Palet', 'Backlog_Palet_Sayisi']] = df[['Dunun_Siparisi_Palet', 'Backlog_Palet_Sayisi']].fillna(0)

schedule_cols = ['location', 'delivery_all', 'order_0', 'order_1', 'order_2', 'order_3', 'order_4', 'order_5', 'order_6']
schedule_cols = [c for c in schedule_cols if c in df_schedule.columns]
df = pd.merge(df, df_schedule[schedule_cols], left_on='Location code', right_on='location', how='left')

df_water_wh = pd.read_csv(DOSYA_WATER_WH, encoding='utf-16', sep='\t')
df_water_wh.rename(columns={'Depo: Depo Adı': 'Location name', 'Product ID': 'Product code'}, inplace=True)
df_water_wh['Product code'] = df_water_wh['Product code'].astype(str).str.lower().str.strip()
df_water_wh = df_water_wh[df_water_wh['Product code'] != 'total']

su_sayisal_temizlenecekler = ['Warehouse Available Stock', 'Transfer Remaining Stock (9 Days)',
                              'water frc t', 'water frc t+1', 'water frc t+2', 'water frc t+3', 'Cover Day']
for col in su_sayisal_temizlenecekler:
    if col in df_water_wh.columns:
        df_water_wh[col] = df_water_wh[col].apply(clean_locale_number)

df_su_liste = sheet_tablo(GSHEET_SU_LISTE_URL, SU_LISTE_GID)
for _c in ('sıra', 'palet', 'transfer_coli_count', 'segments'):
    if _c in df_su_liste.columns: df_su_liste[_c] = pd.to_numeric(df_su_liste[_c].map(sheet_sayi), errors='coerce')
df_su_liste.rename(columns={'Product ID': 'Product code'}, inplace=True)
df_su_liste['Product code'] = df_su_liste['Product code'].astype(str).str.lower().str.strip()

df_palet_alani = sheet_tablo(GSHEET_SU_PALET_ALANI_URL, SU_PALET_ALANI_GID)
df_palet_alani.rename(columns={'Depo': 'Location name', 'Su/ Euro Palet Genişlik: 120 Derinlik: 80': 'Max_Su_Palet_Kapasitesi'}, inplace=True)
df_palet_alani['Location name'] = df_palet_alani['Location name'].astype(str).str.strip()
df_palet_alani['Max_Su_Palet_Kapasitesi'] = pd.to_numeric(df_palet_alani['Max_Su_Palet_Kapasitesi'].map(sheet_sayi), errors='coerce')
df_palet_alani = df_palet_alani.drop_duplicates(subset=['Location name'])
print(f"💧 Su palet bilgileri: {len(df_su_liste)} ürün · Su palet alanı: {len(df_palet_alani)} depo")

def buffer_sayi(x):
    """Buffer hücresi → oran: '110%' / '1.10' / '1,1' → 1.10; boş, 0 ya da okunamayan → NaN."""
    t = str(x).strip().replace(' ', '')
    if t in ('', '-', 'nan', 'None'): return np.nan
    yuzde = t.endswith('%')
    try: v = float(t.rstrip('%').replace(',', '.'))
    except ValueError: return np.nan
    if yuzde or v > 5: v = v / 100
    return v if v > 0 else np.nan

df_buffer_raw = sheet_tablo(GSHEET_BUFFER_URL, BUFFER_GID)
_buf_depo = next((c for c in df_buffer_raw.columns if 'depo' in c.lower()), df_buffer_raw.columns[0])
_buf_kol = next((c for c in df_buffer_raw.columns if 'ambient' in c.lower()), None)
if _buf_kol is None:
    raise ValueError(f"Buffer Rates sekmesinde 'Ambient Buffer' kolonu yok. Kolonlar: {df_buffer_raw.columns.tolist()}")
_buf = pd.DataFrame({'Location name': df_buffer_raw[_buf_depo].astype(str).str.strip(),
                     'Hard_Stop_Orani': df_buffer_raw[_buf_kol].map(buffer_sayi)}).dropna(subset=['Hard_Stop_Orani'])
_buf_cakisan = _buf.groupby('Location name')['Hard_Stop_Orani'].nunique()
if (_buf_cakisan > 1).any():
    print(f"   ⚠️  Buffer Rates'te farklı değerle tekrarlanan depolar (ilki alındı): {_buf_cakisan[_buf_cakisan > 1].index.tolist()}")
AMBIENT_BUFFER = _buf.drop_duplicates('Location name').set_index('Location name')['Hard_Stop_Orani'].to_dict()
print(f"📐 Ambient buffer (esnek hacim tavanı): {len(AMBIENT_BUFFER)} depo · sheet'te olmayan depolara %{HARD_STOP_CAPACITY * 100:g}")

df_su_liste['Is_Water'] = True

df = pd.merge(df, df_su_liste[['Product code', 'sıra', 'palet', 'Is_Water']], on='Product code', how='left')
df['Is_Water'] = df['Is_Water'] == True

# ==========================================
# 🔀 SU → AMBIENT GEÇİŞİ (7 DEPO, 2 ÜRÜN)
# ==========================================
_tum_depo_adlari = pd.Series(df_relex['Location name'].dropna().unique())
_ad_eslesen = _tum_depo_adlari[_tum_depo_adlari.map(_ad_eslesir)].tolist()
print(f"🔀 Ambient geçişi — ad ile eşleşen depolar: {_ad_eslesen if _ad_eslesen else 'YOK'}")
for _anh in AMBIENT_GECIS_DEPO_AD_ANAHTAR:
    if not any(_anh in _norm_ad(a) for a in _ad_eslesen):
        print(f"   ⚠️  '{_anh}' bu koşunun Relex dosyasında bulunamadı.")

df['Ambient_Gecis'] = _ambient_gecis_mask(df['Location name'], df['Location code'], df['Product code'])
df.loc[df['Ambient_Gecis'], 'Is_Water'] = False
print(f"🔀 Ambient'e geçirilen satır: {int(df['Ambient_Gecis'].sum())} "
      f"({df.loc[df['Ambient_Gecis'], 'Location name'].nunique()} depo) — Relex OBS ile devam")

su_sutunlari = ['Location name', 'Product code', 'Warehouse Available Stock',
                'Transfer Remaining Stock (9 Days)', 'water frc t',
                'water frc t+1', 'water frc t+2', 'water frc t+3', 'Cover Day']
su_sutunlari_mevcut = [c for c in su_sutunlari if c in df_water_wh.columns]
df = pd.merge(df, df_water_wh[su_sutunlari_mevcut], on=['Location name', 'Product code'], how='left')

# ==========================================
# 💧 EKSİK SU SATIRLARI — DEPO + ÜRÜN BAZLI
# ==========================================
_mevcut_su_cift = df.loc[df['Is_Water'] == True, ['Location name', 'Product code']].drop_duplicates()
_mevcut_su_cift['_zaten_var'] = 1

eksik_sular = df_water_wh.merge(_mevcut_su_cift, on=['Location name', 'Product code'], how='left')
eksik_sular = eksik_sular[eksik_sular['_zaten_var'].isna()].drop(columns=['_zaten_var']).copy()

_relex_depolari = set(df_relex['Location name'].dropna().unique())
_kapsam_disi = ~eksik_sular['Location name'].isin(_relex_depolari)
if _kapsam_disi.any():
    _kd = eksik_sular[_kapsam_disi]
    print(f"💧 Relex kapsamı dışındaki {_kd['Location name'].nunique()} depo için "
          f"{len(_kd)} Water WH satırı atlandı (bu koşuya dahil değil).")
eksik_sular = eksik_sular[~_kapsam_disi].copy()

_kod_map = (df_relex.dropna(subset=['Location name', 'Location code'])
            .drop_duplicates(subset=['Location name'])
            .set_index('Location name')['Location code']
            .astype(str).str.lower().str.strip().to_dict())

# Ambient'e geçen ürünler için su satırı üretilmez
_es_gecis = _ambient_gecis_mask(eksik_sular['Location name'],
                                eksik_sular['Location name'].map(_kod_map),
                                eksik_sular['Product code'])
if _es_gecis.any():
    print(f"🔀 Ambient'e geçen ürünler için {int(_es_gecis.sum())} Water WH satırı su olarak üretilmedi.")
eksik_sular = eksik_sular[~_es_gecis].copy()

_es_kod = eksik_sular['Location name'].map(_kod_map)
_es_prod = eksik_sular['Product code'].astype(str).str.lower().str.strip()
_test_satir = _es_kod.isin(DIKEY_TEST_DEPO_KODLARI)

_layout_uyumlu = pd.Series(
    [(_k in DIKEY_DEPO_SKU and _p in DIKEY_DEPO_SKU[_k]) if isinstance(_k, str) else False
     for _k, _p in zip(_es_kod, _es_prod)], index=eksik_sular.index)

_atilacak = _test_satir & ~_layout_uyumlu
if _atilacak.any():
    _a = eksik_sular[_atilacak]
    print(f"💧 Test depolarında layout listesinde OLMAYAN {len(_a)} Water WH satırı atlandı "
          f"({_a['Location name'].nunique()} depo) — bu ürünler o paletlere girmiyor.")

_uretilen = _test_satir & _layout_uyumlu
if _uretilen.any():
    _u = eksik_sular[_uretilen]
    print(f"💧 Test depolarında Relex'te satırı gelmeyen {len(_u)} LAYOUT ürünü için satır "
          f"üretildi ({_u['Location name'].nunique()} depo) — Water WH stok/forecast verisiyle.")

eksik_sular = eksik_sular[~_atilacak].copy()
eksik_sular['Layout_Sentetik'] = _uretilen.reindex(eksik_sular.index).fillna(False)

eksik_sular['Effective quantity'] = 0
eksik_sular['Is_Water'] = True
eksik_sular['Relex_Satiri_Yok'] = True
eksik_sular = pd.merge(eksik_sular, df_su_liste[['Product code', 'sıra', 'palet']], on='Product code', how='left')

_urun_ref = (df_relex.dropna(subset=['Product code'])
             .drop_duplicates(subset=['Product code']).set_index('Product code'))
for _kaynak_col in ['Product name', 'Custom category', 'Custom sub-category', 'ABC class',
                    'End Balance DC']:
    if _kaynak_col in _urun_ref.columns:
        eksik_sular[_kaynak_col] = eksik_sular['Product code'].map(_urun_ref[_kaynak_col])

if 'End Balance DC' in eksik_sular.columns:
    _dc_bos = eksik_sular['End Balance DC'].isna()
    if _dc_bos.any():
        print(f"   ⚠️  {int(_dc_bos.sum())} üretilen satırda 'End Balance DC' bulunamadı "
              f"(ürün ağın hiçbir deposunda Relex'te yok) → dikey dağıtımda pas geçilecek: "
              f"{eksik_sular.loc[_dc_bos, 'Product code'].unique().tolist()[:8]}")

if 'Order batch size' in _urun_ref.columns:
    eksik_sular['Order batch size'] = eksik_sular['Product code'].map(_urun_ref['Order batch size'])

eksik_sular = pd.merge(eksik_sular, df_palet[['SKUkodu', 'SON']],
                       left_on='Product code', right_on='SKUkodu', how='left', suffixes=('', '_y'))
if 'SON_y' in eksik_sular.columns:
    eksik_sular['SON'] = eksik_sular['SON'].fillna(eksik_sular['SON_y'])
    eksik_sular.drop(columns=['SON_y'], inplace=True)

print(f"💧 Eksik su satırı (depo+ürün bazlı): {len(eksik_sular)} satır / "
      f"{eksik_sular['Location name'].nunique()} depo")

df = pd.concat([df, eksik_sular], ignore_index=True)
df['Relex_Satiri_Yok'] = df['Relex_Satiri_Yok'] == True
df['Layout_Sentetik'] = df.get('Layout_Sentetik', False) == True
df['Ambient_Gecis'] = df['Ambient_Gecis'] == True

_depo_seviyesi_cols = [
    'Location code', 'Domain Type', 'location', 'delivery_all',
    'Dunun_Siparisi_Palet', 'Backlog_Palet_Sayisi',
    'Total Ambient Ratio (In Transit Included)', 'ambient_volume Litre',
    'ambient_volume Litre (Total Transit)', 'Avg. ambient_dolap_hacim',
    'today_forecast', 'next_day_forecast', 'next_2_days_forecast',
] + [f'order_{i}' for i in range(7)]

for _c in [c for c in _depo_seviyesi_cols if c in df.columns]:
    df[_c] = df[_c].fillna(df.groupby('Location name')[_c].transform('first'))

for _i in range(7):
    _oc = f'order_{_i}'
    if _oc in df.columns:
        df[_oc] = df[_oc] == True

_kodsuz = int(df.loc[df['Relex_Satiri_Yok'], 'Location code'].isna().sum())
if _kodsuz:
    print(f"   ⚠️  {_kodsuz} yeni satırın depo kodu eşleşmedi (o depoda hiç Relex satırı yok) "
          f"— layout hesabına giremez.")

for _ad_col in ['Product Name', 'Product_Name']:
    if _ad_col in df.columns and 'Product name' in df.columns:
        df['Product name'] = df['Product name'].fillna(df[_ad_col])
        df.drop(columns=[_ad_col], inplace=True)

# 📦 DİKEY DEPO SABİT BATCH UYGULAMASI (ambient'e geçen satırlar Relex OBS'de kalır)
_loc_kod = df['Location code'].astype(str).str.lower().str.strip()
_prod_kod = df['Product code'].astype(str).str.lower().str.strip()
_dikey_batch_mask = (_loc_kod.isin(DIKEY_TEST_DEPO_KODLARI) &
                     _prod_kod.isin(DIKEY_DEPO_BATCH.keys()) &
                     ~df['Ambient_Gecis'])

df['Batch_Kaynagi'] = 'Relex'
if _dikey_batch_mask.any():
    _eski_obs = df.loc[_dikey_batch_mask, 'Order batch size'].copy()
    df.loc[_dikey_batch_mask, 'Order batch size'] = _prod_kod[_dikey_batch_mask].map(DIKEY_DEPO_BATCH)
    df.loc[_dikey_batch_mask, 'Batch_Kaynagi'] = 'Dikey Sabit Tablo'

    _degisen = int((_eski_obs.notna() &
                    (_eski_obs != df.loc[_dikey_batch_mask, 'Order batch size'])).sum())
    _bostu = int(_eski_obs.isna().sum())
    print(f"📦 Dikey sabit batch uygulandı: {int(_dikey_batch_mask.sum())} satır "
          f"({_bostu} tanesi boştu, {_degisen} tanesinde Relex değeri ezildi)")

_batch_eksik = df.loc[_loc_kod.isin(DIKEY_TEST_DEPO_KODLARI) & (df['Is_Water'] == True) &
                      ~_prod_kod.isin(DIKEY_DEPO_BATCH.keys()), 'Product code'].unique().tolist()
if _batch_eksik:
    print(f"   ⚠️  Dikey depolarda sabit batch tablosunda OLMAYAN su ürünleri: {_batch_eksik}")

su_sayisal_sutunlar = ['Warehouse Available Stock', 'Transfer Remaining Stock (9 Days)',
                       'water frc t', 'water frc t+1', 'water frc t+2', 'water frc t+3']
su_sayisal_sutunlar_mevcut = [c for c in su_sayisal_sutunlar if c in df.columns]
df[su_sayisal_sutunlar_mevcut] = df[su_sayisal_sutunlar_mevcut].fillna(0)
df = pd.merge(df, df_palet_alani[['Location name', 'Max_Su_Palet_Kapasitesi']], on='Location name', how='left')

# ==========================================
# 🥚 YUMURTA ABC SINIFI DÜZELTMESİ
# ==========================================
yumurta_mask = (
    df['Custom sub-category'].astype(str).str.strip().str.lower() == 'yumurta'
) & (
    df['ABC class'].astype(str).str.upper().str.strip().isin(['C', 'D'])
)
df.loc[yumurta_mask, 'ABC class'] = 'B'
print(f"🥚 Yumurta ABC düzeltmesi: {int(yumurta_mask.sum())} satır C/D → B'ye yükseltildi")

# ==========================================
# ⚡ 1. SU ÜRÜNLERİ HACİM SIFIRLAMA
# ==========================================
if 'hacim2' in df.columns:
    df.loc[df['Is_Water'] == True, 'hacim2'] = 0.0

_gecis_hacimsiz = df['Ambient_Gecis'] & pd.to_numeric(df['hacim2'], errors='coerce').isna()
if _gecis_hacimsiz.any():
    print(f"   ⚠️  Ambient'e geçen {int(_gecis_hacimsiz.sum())} satırda hacim2 boş → 0.5 L varsayılacak.")

mask_su = (df['Is_Water'] == True)
mask_demirbas = (df['Custom category'].astype(str).str.lower().str.contains('demirbaş|demirbas', na=False)) | \
                (df['Custom sub-category'].astype(str).str.lower().str.contains('demirbaş|demirbas', na=False))

# ==========================================
# 🧮 3. LOJİSTİK MATEMATİKSEL HESAPLAMALAR
# ==========================================
df['Domain Type'] = df['Domain Type'].fillna('GB')

for col in ['Daily FC', 'End balance', 'End Balance DC', 'Open purchase orders']:
    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

temp_fc = df['Daily FC'].replace(0, np.nan)
df['Calculated Cover Day'] = ((df['End balance'] + df['Open purchase orders']) / temp_fc).fillna(0)

df['SON_calculated'] = np.where(df['SON'].astype(str).str.lower() == 'batch eşitle',
                                df['Order batch size'], pd.to_numeric(df['SON'], errors='coerce'))
df['SON_calculated'] = df['SON_calculated'].fillna(df['Order batch size']).replace(0, 1)

_son_bos = df['SON_calculated'].isna()
if _son_bos.any():
    _bos_urun = df.loc[_son_bos, 'Product code'].dropna().unique().tolist()
    print(f"⚠️  SON/OBS bulunamayan {int(_son_bos.sum())} satır 1'e sabitlendi "
          f"({len(_bos_urun)} ürün) → {_bos_urun[:10]}")
    df['SON_calculated'] = df['SON_calculated'].fillna(1)

df['palet'] = pd.to_numeric(df['palet'], errors='coerce').fillna(9999)
df['sıra'] = pd.to_numeric(df['sıra'], errors='coerce').fillna(9999)

df['Mevcut_Palet'] = np.where(
    df['Is_Water'] == True,
    df['Effective quantity'] / df['palet'],
    df['Effective quantity'] / (df['SON_calculated'] * 50)
)
df['Mevcut_Palet'] = pd.Series(df['Mevcut_Palet']).fillna(0)

bugun = pd.Timestamp.now().normalize()
bugun_no = bugun.weekday()

if 'delivery_all' not in df.columns:
    df['delivery_all'] = 1
df['delivery_all'] = pd.to_numeric(df['delivery_all'], errors='coerce').fillna(1)

lead_time_sartlar = [
    (bugun_no == 4) & (df['delivery_all'] == 2),
    (bugun_no == 5) & (df['delivery_all'] == 2),
    (bugun_no == 5) & (df['delivery_all'] == 1)
]
lead_time_eklemeler = [1, 1, 1]

kayma_bugun = np.select(lead_time_sartlar, lead_time_eklemeler, default=0)
df['Bugün_Tirinin_Varis_Tarihi'] = df['delivery_all'] + kayma_bugun
df['Lead_Time_Days'] = df['Bugün_Tirinin_Varis_Tarihi']

conditions = []
choices = []
for i in range(1, 8):
    check_day = (bugun_no - i) % 7
    col_name = f'order_{int(check_day)}'
    if col_name in df.columns:
        conditions.append(df[col_name] == True)
        choices.append(i)

df['Kac_Gun_Once'] = np.select(conditions, choices, default=99)
onceki_siparis_gun_no = (bugun_no - df['Kac_Gun_Once']) % 7

onceki_lead_time_sartlar = [
    (onceki_siparis_gun_no == 4) & (df['delivery_all'] == 2),
    (onceki_siparis_gun_no == 5) & (df['delivery_all'] == 2),
    (onceki_siparis_gun_no == 5) & (df['delivery_all'] == 1)
]
kayma_onceki = np.select(onceki_lead_time_sartlar, lead_time_eklemeler, default=0)
df['Onceki_Tirin_Varis_Tarihi'] = -df['Kac_Gun_Once'] + df['delivery_all'] + kayma_onceki

for fc_col in ['today_forecast', 'next_day_forecast', 'next_2_days_forecast']:
    if fc_col not in df.columns:
        df[fc_col] = 0

df['Bosalacak_Hacim_Litre'] = np.select(
    [
        df['Lead_Time_Days'] == 0,
        df['Lead_Time_Days'] == 1,
        df['Lead_Time_Days'] == 2,
        df['Lead_Time_Days'] >= 3
    ],
    [
        df['today_forecast'] * 0.3,
        df['today_forecast'] + df['next_day_forecast'] * 0.3,
        df['today_forecast'] + df['next_day_forecast'] + df['next_2_days_forecast'] * 0.3,
        df['today_forecast'] + df['next_day_forecast'] + df['next_2_days_forecast']
    ],
    default=0
)

df['Kalan_Net_Hacim_Litre'] = df['Avg. ambient_dolap_hacim'] - (
    df['ambient_volume Litre'] +
    df['ambient_volume Litre (Total Transit)'] -
    df['Bosalacak_Hacim_Litre']
)

# Depo bazlı esnek hacim tavanı (Buffer Rates → Ambient Buffer); sheet'te olmayan depo → HARD_STOP_CAPACITY
df['Hard_Stop_Orani'] = df['Location name'].astype(str).str.strip().map(AMBIENT_BUFFER).fillna(HARD_STOP_CAPACITY).astype(float)
_buf_yok = sorted(set(df.loc[~df['Location name'].astype(str).str.strip().isin(AMBIENT_BUFFER.keys()), 'Location name'].dropna()))
if _buf_yok:
    print(f"   ⚠️  {len(_buf_yok)} depo Buffer Rates sekmesinde yok → %{HARD_STOP_CAPACITY * 100:g}: {_buf_yok[:10]}")

df['hacim2'] = pd.to_numeric(df['hacim2'], errors='coerce')
df['Satir_Onerilen_Hacim'] = df['Effective quantity'] * df['hacim2'].fillna(0.5)
df['Orijinal_Miktar'] = df['Effective quantity']
df['Final_Miktar'] = df['Effective quantity']
df['Kesinti_Nedeni'] = 'Islem Gormedi'

# 🧪 Sadece A testi işaretleri (uygulama _sayim_kisiti_uygula içinde, her çağrıda yeniden)
df['Sadece_A_Test'] = df['Location name'].map(_norm_ad).isin({_norm_ad(x) for x in SADECE_A_TEST_DEPOLARI})
df['WAva_Depo'] = df['Location name'].map(_norm_ad).isin({_norm_ad(x) for x in WEIGHTED_AVA_DEPOLARI})
if df['WAva_Depo'].any():
    print(f"🎯 Weighted ava depoları (99 koruması yok): {sorted(df.loc[df['WAva_Depo'], 'Location name'].unique())}")
df['Sadece_A_Iptal'] = df['Sadece_A_Test'] & (df['ABC class'].astype(str).str.upper().str.strip() != 'A')
if df['Sadece_A_Test'].any():
    print(f"🧪 Sadece A testi: {sorted(df.loc[df['Sadece_A_Test'], 'Location name'].unique())} → "
          f"{int(df['Sadece_A_Iptal'].sum())} A dışı satır sıfırlanacak, "
          f"{int((df['Sadece_A_Test'] & ~df['Sadece_A_Iptal']).sum())} satır değerlendirmede")

# ==========================================
# 📋 SAYIM KISITI — teslimat günü sayım yasağına denk gelen depoya hiçbir şey gitmez
# ==========================================
# Teslimat tarihi: Relex 'Delivery date' (depo bazında en erken); yoksa bugün + lead time
_tes = pd.to_datetime(df['Delivery date'], dayfirst=True, errors='coerce').dt.normalize()
df['Teslimat_Tarihi'] = _tes.groupby(df['Location name']).transform('min')
_tes_farkli = _tes.groupby(df['Location name']).nunique()
if (_tes_farkli > 1).any():
    print(f"   ⚠️  Birden fazla teslimat tarihi olan {int((_tes_farkli > 1).sum())} depo → en erken tarih alındı: "
          f"{_tes_farkli[_tes_farkli > 1].index.tolist()[:10]}")
_tes_bos = df['Teslimat_Tarihi'].isna()
if _tes_bos.any():
    df.loc[_tes_bos, 'Teslimat_Tarihi'] = bugun + pd.to_timedelta(df.loc[_tes_bos, 'Lead_Time_Days'], unit='D')
    print(f"   ⚠️  Relex teslimat tarihi boş olan {df.loc[_tes_bos, 'Location name'].nunique()} depo → "
          f"bugün + lead time kullanıldı.")

df['Sayim_Kisiti'] = False
df['Sayim_Bilgisi'] = ''
_sayim_rapor = []
_bir_gun = pd.Timedelta(days=1)

for _depo, _g in df.groupby('Location name'):
    _kod = str(_g['Location code'].dropna().iloc[0]).lower().strip() if _g['Location code'].notna().any() else ''
    _sayimlar = SAYIM_KAYITLARI.get(_kod, [])
    if not _sayimlar: continue
    _tt = _g['Teslimat_Tarihi'].iloc[0]
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
                'Teslimat Tarihi': _tt.strftime('%d.%m.%Y') if pd.notna(_tt) else '-',
                'Durum': 'KISILDI - SAYIM' if _kapsar else 'Teslimat yasak aralık dışında',
            })
    if _engel is not None:
        df.loc[_g.index, 'Sayim_Kisiti'] = True
        df.loc[_g.index, 'Sayim_Bilgisi'] = (f"{_engel['T'].strftime('%d.%m')} {_engel['aciklama']} "
                                             f"({_engel['tip']} {_engel['tur']})")

def _sayim_kisiti_uygula():
    """Sayım kısıtlı depolarda tüm satırları sıfırlar. Arada miktar yazan adımlardan
    (dikey elleçleme vb.) sonra tekrar çağrılır ki kısıt ezilmesin. Önce sadece A testinin
    A dışı satırlarını sıfırlar; sayım sonra gelir, sayımlı depoda neden 'Sayım' kalır."""
    _a = df['Sadece_A_Iptal'] == True
    if _a.any():
        df.loc[_a, 'Final_Miktar'] = 0
        df.loc[_a, 'Kesinti_Nedeni'] = SADECE_A_REASON
    _m = df['Sayim_Kisiti'] == True
    if _m.any():
        df.loc[_m, 'Final_Miktar'] = 0
        df.loc[_m, 'Kesinti_Nedeni'] = _NEDEN_SAYIM

_sayim_kisiti_uygula()
print(f"📋 Sayım kısıtı: {df.loc[df['Sayim_Kisiti'], 'Location name'].nunique()} depo / "
      f"{int(df['Sayim_Kisiti'].sum())} satır tamamen kesildi")

# TIR limiti: Gunluk sheet → kod ici default (G10=12 / GB=25)
df['Gunluk_Palet_Limiti'] = df['Location name'].map(
    lambda a: GUNLUK_PALET_LIMIT.get(_norm_ad(a), np.nan))

_default_limit = np.where(df['Domain Type'] == 'G10', 12, 25)

df['Tir_Limiti'] = np.where(
    df['Gunluk_Palet_Limiti'].notna(),
    df['Gunluk_Palet_Limiti'],
    _default_limit
)

df['Tir_Limiti_Kaynagi'] = np.where(
    df['Gunluk_Palet_Limiti'].notna(), f'Gunluk Sheet ({_BUGUN_ADI})',
    'Kod Ici Default (12/25)'
)

_tl_ozet = (df.drop_duplicates(subset=['Location name'])
              .groupby('Tir_Limiti_Kaynagi')['Location name'].count().to_dict())
print(f"🚚 TIR limiti kaynak dagilimi (depo): {_tl_ozet}")

_gunluk_eslesmeyen = sorted(set(GUNLUK_PALET_LIMIT.keys()) -
                            set(df['Location name'].dropna().map(_norm_ad)))
if _gunluk_eslesmeyen:
    print(f"   ⚠️  Günlük sheet'te olup bu koşuda bulunmayan {len(_gunluk_eslesmeyen)} depo: "
          f"{_gunluk_eslesmeyen[:10]}")

toplam_kapidaki_yuk = df['Backlog_Palet_Sayisi'] + df['Dunun_Siparisi_Palet']
asan_backlog = toplam_kapidaki_yuk - df['Tir_Limiti']
araya_tir_girdi_mi = df['Onceki_Tirin_Varis_Tarihi'] < df['Bugün_Tirinin_Varis_Tarihi']

# Önceki siparişin tırı bugün (ya da daha önce) geliyorsa arada tır yoktur: backlog bizim tıra biner.
# (Ör. N+1 depoda Cumartesi: Cuma siparişi bugün iner, bizim sipariş Pazartesi gider. Bugünkü teslimat
#  ara tır sayılırsa backlog yanlışlıkla sıfırlanır.) "Ara tır" hesabı yalnız önceki tır bugünden sonra,
#  bizimkinden önce geliyorsa yapılır (N+2 depolar).
df['Etkili_Backlog_Palet'] = np.where(
    (df['Bugün_Tirinin_Varis_Tarihi'] <= 1) | (df['Onceki_Tirin_Varis_Tarihi'] <= 0),
    df['Backlog_Palet_Sayisi'],
    np.where(
        araya_tir_girdi_mi,
        np.where(asan_backlog > 0, asan_backlog, 0),
        toplam_kapidaki_yuk
    )
)

df['Backlog_Limiti_Asildi'] = np.where(
    ((df['Domain Type'] == 'G10') & (df['Etkili_Backlog_Palet'] > 6)) |
    ((df['Domain Type'] == 'GB') & (df['Etkili_Backlog_Palet'] > 20)),
    'Asildi (Kritik)', 'Uygun'
)

df.loc[mask_demirbas, 'Mevcut_Palet'] = 0
df.loc[mask_demirbas, 'Satir_Onerilen_Hacim'] = 0
df.loc[mask_su, 'Satir_Onerilen_Hacim'] = 0

df['Su_Lead_Time_Satis'] = np.select(
    [
        df['Lead_Time_Days'] == 0,
        df['Lead_Time_Days'] == 1,
        df['Lead_Time_Days'] == 2,
        df['Lead_Time_Days'] == 3,
        df['Lead_Time_Days'] >= 4
    ],
    [
        df['water frc t'] * 0.3,
        df['water frc t'] + df['water frc t+1'] * 0.3,
        df['water frc t'] + df['water frc t+1'] + df['water frc t+2'] * 0.3,
        df['water frc t'] + df['water frc t+1'] + df['water frc t+2'] + df['water frc t+3'] * 0.3,
        df['water frc t'] + df['water frc t+1'] + df['water frc t+2'] + df['water frc t+3']
    ],
    default=0
)

df['Net_Su_Stok'] = df['Warehouse Available Stock'] + df['Transfer Remaining Stock (9 Days)'] - df['Su_Lead_Time_Satis']
df['Net_Su_Stok'] = df['Net_Su_Stok'].clip(lower=0)

df['Mevcut_Kaplanan_Su_Paleti'] = np.where(
    df['Is_Water'] == True,
    (df['Net_Su_Stok'] // df['palet']) + np.where((df['Net_Su_Stok'] % df['palet']) >= (df['palet'] * PALETIN_YUZDE_KACI), 1, 0),
    0
)

# ==========================================
# 🛑 4. ÖNCELİKLENDİRME SKORLAMASI
# ==========================================
print("4. Öncelik skorları hesaplanıyor...")

DOKUNULMAYACAK_G10_TEMIZ = [str(x).lower().strip() for x in DOKUNULMAYACAK_URUNLER_G10]
DOKUNULMAYACAK_GB_TEMIZ = [str(x).lower().strip() for x in DOKUNULMAYACAK_URUNLER_GB]

# 🎯 Dokunulmazlık nedeni: Kampanya (sheet, T / T-1) > Waste (elle girilen liste)
_pc_dok = df['Product code'].astype(str).str.lower().str.strip()
_dom_dok = df['Domain Type'].astype(str).str.strip()
_persembe = bugun.weekday() == 3
_n1 = (pd.to_datetime(df['Teslimat_Tarihi']) - bugun).dt.days <= 1          # teslimat ertesi gün (ya da bugün) → N+1
df['Kampanya_Listesi'] = np.where(_persembe & _n1, 'T-1', 'T')
_kampanya = pd.Series([pc in KAMPANYA_LISTELERI.get((d, h), ()) for pc, d, h in zip(_pc_dok, _dom_dok, df['Kampanya_Listesi'])], index=df.index)
_waste = ((_dom_dok == 'G10') & _pc_dok.isin(DOKUNULMAYACAK_G10_TEMIZ)) | ((_dom_dok == 'GB') & _pc_dok.isin(DOKUNULMAYACAK_GB_TEMIZ))
_kampanya = _kampanya & ~df['Sadece_A_Test']   # sadece A test depolarında dokunulmazlık yok
_waste = _waste & ~df['Sadece_A_Test']
df['Dokunulmazlik_Nedeni'] = np.select([_kampanya, _waste], ['Kampanya', 'Waste'], default='')
df.loc[df['Dokunulmazlik_Nedeni'] != 'Kampanya', 'Kampanya_Listesi'] = ''
if _persembe:
    _dep_n1 = df.loc[_n1, 'Location name'].nunique()
    print(f"🎯 Perşembe: teslimatı cuma olan {_dep_n1} depo (N+1) T-1, diğer {df['Location name'].nunique() - _dep_n1} depo T kampanya listesini kullanır")
print(f"🎯 Dokunulmazlık: Kampanya {int(_kampanya.sum())} satır, Waste {int((df['Dokunulmazlik_Nedeni'] == 'Waste').sum())} satır "
      f"(ikisinde de olan {int((_kampanya & _waste).sum())} satır Kampanya sayıldı)")

def priority_score(row):
    prod_code = str(row['Product code']).lower()
    domain_type = row['Domain Type']
    is_water = bool(row.get('Is_Water', False))
    _loc_kod = str(row.get('Location code', '')).lower().strip()
    _dikey_depo = _loc_kod in DIKEY_TEST_DEPO_KODLARI

    if not (is_water and _dikey_depo):
        if row['Dokunulmazlik_Nedeni'] in ('Kampanya', 'Waste'):    # kampanya (sheet) + waste (elle) listeleri
            return 100

    cat = str(row.get('Custom category', '')).lower() + " " + str(row.get('Custom sub-category', '')).lower()
    if 'demirbaş' in cat or 'demirbas' in cat:
        return 101

    abc, cd = row['ABC class'], row['Calculated Cover Day']
    bulunurluk = row.get('Son 14 Günlük Bulunurluk', 1.0)
    end_bal = row['End balance']
    segment = str(row.get('Segment', '')).strip()

    if domain_type == 'G10':
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
        else:
            if abc == 'E': return 8
            if abc == 'D': return 9
            if abc == 'C': return 81 if cd < C_MIN_COVER else 10
        return 10

    if domain_type == 'GB':
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
        else:
            if abc == 'E': return 17
            if abc == 'D': return 18
            if abc == 'C': return 81 if cd < C_MIN_COVER else 19
        return 10

    return 10

df['Cut_Priority'] = df.apply(priority_score, axis=1)
df.drop(columns=['WAva_Depo'], inplace=True)   # yalnız puanlama için; çıktıya girmez

# ==========================================
# 🔧 DİKEY ELLEÇLEME YARDIMCI FONKSİYONLARI
# ==========================================
df['Layout_Tipi'] = '-'
df['Layout_Listesinde'] = '-'

def _layout_isaretle(mask, layout_adi, sku_listeleri):
    tum = set()
    for L in sku_listeleri:
        tum.update([str(x).lower().strip() for x in L])

    df.loc[mask, 'Layout_Tipi'] = layout_adi
    _kod = df.loc[mask, 'Product code'].astype(str).str.lower().str.strip()
    _listede = _kod.isin(tum)
    _sentetik = df.loc[mask, 'Layout_Sentetik'] == True
    _relex_yok = (df.loc[mask, 'Relex_Satiri_Yok'] == True) & ~_sentetik

    df.loc[mask, 'Layout_Listesinde'] = np.select(
        [_listede & _sentetik, _listede & ~_relex_yok,
         _listede & _relex_yok, ~_listede],
        ['Var - Utilization Kaynakli', 'Var',
         'Var - Relex Tanimsiz', 'YOK - Layout Disi (FAZLA)'],
        default='YOK - Layout Disi (FAZLA)')

def _dikey_normalize(sku_listesi, esik, get_fn, set_fn, flt_fn, etiket):
    _rows = {s: get_fn(s) for s in sku_listesi}
    _gecerli = [s for s in sku_listesi if _rows[s] is not None]
    if not _gecerli: return

    def _tanimli(s):
        r = _rows[s]
        if r is None: return False
        try:
            if bool(r.get('Layout_Sentetik', False)): return True
            return not bool(r.get('Relex_Satiri_Yok', False))
        except: return True

    def _dc_var(s):
        _dc = flt_fn(_rows[s], 'End Balance DC')
        _o = flt_fn(_rows[s], 'Order batch size')
        return _dc >= (_o if _o > 0 else 1.0)

    _dagitim = [s for s in _gecerli if _tanimli(s) and _dc_var(s)]
    if not _dagitim: return

    def _pk(s):
        v = flt_fn(_rows[s], 'palet')
        return v if v > 0 else 1.0

    def _ob(s):
        v = flt_fn(_rows[s], 'Order batch size')
        return v if v > 0 else 1.0

    def _ns(s): return flt_fn(_rows[s], 'Net_Su_Stok')

    _eff = {s: flt_fn(_rows[s], 'Effective quantity') for s in _dagitim}
    if not any(v > 0 for v in _eff.values()): return
    if sum(_ns(s) / _pk(s) for s in _gecerli) >= esik: return

    n = len(_dagitim)
    taban = min(DIKEY_MIN_PAY, 1.0 / n)
    serbest = 1.0 - taban * n

    _eff_norm = {s: _eff[s] / _pk(s) for s in _dagitim}
    _toplam = sum(_eff_norm.values())

    if _toplam > 0:
        _pay = {s: taban + serbest * (_eff_norm[s] / _toplam) for s in _dagitim}
    else:
        _pay = {s: 1.0 / n for s in _dagitim}

    _qty = {}
    for s in _dagitim:
        _ham = _pay[s] * _pk(s)
        _o = int(_ob(s))
        _qty[s] = int(_ham // _o) * _o

    _EPS = 1e-9
    _bos = 1.0 - sum(_qty[s] / _pk(s) for s in _dagitim)

    while True:
        _uygun = [s for s in _dagitim if (_ob(s) / _pk(s)) <= _bos + _EPS]
        if not _uygun: break
        _hedef = max(_uygun, key=lambda x: (_pay[x] * _pk(x) - _qty[x]) / _pk(x))
        _qty[_hedef] += int(_ob(_hedef))
        _bos -= _ob(_hedef) / _pk(_hedef)

    for s in _dagitim:
        if _qty[s] > 0:
            set_fn(s, _qty[s], etiket)

def _paylasimli(sku_listesi, palet_adi, get_fn, set_fn, flt_fn):
    _rows = {s: get_fn(s) for s in sku_listesi}
    _gecerli = [s for s in sku_listesi if _rows[s] is not None]
    if not _gecerli: return

    def _tanimli(s):
        r = _rows[s]
        if r is None: return False
        try:
            if bool(r.get('Layout_Sentetik', False)): return True
            return not bool(r.get('Relex_Satiri_Yok', False))
        except: return True

    def _pk(s):
        v = flt_fn(_rows[s], 'palet')
        return v if v > 0 else 9999.0

    def _ok(s):
        v = flt_fn(_rows[s], 'Order batch size')
        return v if v > 0 else 1.0

    def _ns(s): return flt_fn(_rows[s], 'Net_Su_Stok')

    def _fc(s):
        v = flt_fn(_rows[s], 'Daily FC')
        if v <= 0: v = flt_fn(_rows[s], 'water frc t')
        return v

    _aktif = {}
    for s in _gecerli:
        if not _tanimli(s): continue
        _dc = flt_fn(_rows[s], 'End Balance DC')
        if _dc < _ok(s): continue
        e = flt_fn(_rows[s], 'Effective quantity')
        if e > 0:
            _aktif[s] = min(e, _dc)
    if not _aktif: return

    _bos_yer = max(0.0, 1.0 - sum(_ns(s) / _pk(s) for s in _gecerli))
    if _bos_yer <= 0: return

    for _ in range(100000):
        if sum(_aktif[s] / _pk(s) for s in _aktif) <= _bos_yer: break
        _cover = {}
        for s in _aktif:
            fc = _fc(s)
            _cover[s] = float('inf') if fc <= 0 else (_ns(s) + _aktif[s]) / fc
        _hedef = max(_cover, key=_cover.get)
        _obs = _ok(_hedef)
        _aktif[_hedef] = _aktif[_hedef] - _obs if _aktif[_hedef] >= _obs else 0
        if _aktif[_hedef] <= 0:
            del _aktif[_hedef]
        if not _aktif: break

    for s, qty in _aktif.items():
        if qty > 0:
            set_fn(s, qty, f'Dikey Elleçleme - {palet_adi}')

def _std_flt(row, col, default=0.0):
    if row is None: return default
    v = row.get(col, default)
    try: return float(v) if not pd.isna(v) else default
    except: return default

def _dikey_layout_calistir(depo_kodlari, layout_adi, adimlar):
    """Genel layout çalıştırıcı (V2 layout'lar için).
    adimlar: [(tip, sku_listesi, etiket)] — tip: 'dikey_tek' | 'dikey' | 'paylasimli'"""
    for _kod in depo_kodlari:
        _mask = (df['Location code'].astype(str).str.lower().str.strip() == str(_kod).lower().strip()) & (df['Is_Water'] == True)
        _d = df[_mask].copy()
        if _d.empty: continue
        df.loc[_mask, 'Final_Miktar'] = 0
        df.loc[_mask, 'Dikey_Elleçleme_Su'] = True
        df.loc[_mask, 'Kesinti_Nedeni'] = f'Dikey Elleçleme - {layout_adi}'
        _layout_isaretle(_mask, layout_adi, [a[1] for a in adimlar])

        def _get(pc, _d=_d):
            r = _d[_d['Product code'] == pc.lower()]
            return r.iloc[0] if not r.empty else None

        def _set(pc, qty, neden, _d=_d):
            r = _d[_d['Product code'] == pc.lower()]
            if not r.empty:
                df.at[r.index[0], 'Final_Miktar'] = qty
                df.at[r.index[0], 'Kesinti_Nedeni'] = neden

        for _tip, _skular, _etiket in adimlar:
            if _tip == 'dikey_tek':
                for _pid in _skular:
                    _dikey_normalize([_pid], 0.25, _get, _set, _std_flt, _etiket)
            elif _tip == 'dikey':
                _dikey_normalize(_skular, 0.25, _get, _set, _std_flt, _etiket)
            else:
                _paylasimli(_skular, _etiket, _get, _set, _std_flt)

# ==========================================
# 🏭 5.0 DİKEY ELLEÇLEME SU HESAPLAMALARI
# ==========================================
print("5.0 Dikey Elleçleme su hesabı çalışıyor...")
df['Dikey_Elleçleme_Su'] = False

# Midi Layout 1
MIDI_5L_URUNLER = {'5981ec31e97e8b000484eb96': 160, '5a7b21f69ccf1d00040084bf': 160}
MIDI_PAIR_A_SKUS = ['6304b87e6c7c1a0eea79e01e', '6811ea8c1f692e53caa0fb7d']
MIDI_PAIR_B_SKUS = ['5a7b20fd8e19da0004bb27f8', '5981eac3ffae51000428afc9']
MIDI_1L_PAIR = ['5fbce44d7d580fc3304aee67', '5bdaa8ae13fd4900121665c3']
MIDI_KUCUKLER = ['66ab86deeee276842220d0d9', '6304c187a3a9db67ff436dd2', '5a7b1f608e19da0004bb2706', '5b30d3c4cebeab0004808a00']
midi_su_mask = (df['Location code'].astype(str).str.lower().str.strip() == MIDI_L1_DEPO_KODU.lower()) & (df['Is_Water'] == True)
midi_df = df[midi_su_mask].copy()

if not midi_df.empty:
    df.loc[midi_su_mask, 'Final_Miktar'] = 0
    df.loc[midi_su_mask, 'Dikey_Elleçleme_Su'] = True
    df.loc[midi_su_mask, 'Kesinti_Nedeni'] = 'Dikey Elleçleme - Midi Layout 1'
    _layout_isaretle(midi_su_mask, 'Midi Layout 1', [list(MIDI_5L_URUNLER.keys()), MIDI_PAIR_A_SKUS, MIDI_PAIR_B_SKUS, MIDI_1L_PAIR, MIDI_KUCUKLER])
    def midi_get(prod_code):
        rows = midi_df[midi_df['Product code'] == prod_code.lower()]
        return rows.iloc[0] if not rows.empty else None
    def midi_set(prod_code, qty, neden):
        rows = midi_df[midi_df['Product code'] == prod_code.lower()]
        if not rows.empty:
            df.at[rows.index[0], 'Final_Miktar'] = qty
            df.at[rows.index[0], 'Kesinti_Nedeni'] = neden
    for pid in MIDI_5L_URUNLER.keys(): _dikey_normalize([pid], 0.25, midi_get, midi_set, _std_flt, 'Dikey Elleçleme - 5L Tek Palet (Dikey)')
    _dikey_normalize(MIDI_PAIR_A_SKUS, 0.25, midi_get, midi_set, _std_flt, 'Dikey Elleçleme - 1.5L Dikey Palet')
    _dikey_normalize(MIDI_PAIR_B_SKUS, 0.25, midi_get, midi_set, _std_flt, 'Dikey Elleçleme - 1.5L Dikey Palet')
    _paylasimli(MIDI_1L_PAIR, '1L Palet', midi_get, midi_set, _std_flt)
    _paylasimli(MIDI_KUCUKLER, 'Kucukler Paleti', midi_get, midi_set, _std_flt)

# Mini Layout 1
MINI_L1_5L_URUNLER = {'5981ec31e97e8b000484eb96': 160, '5a7b21f69ccf1d00040084bf': 160}
MINI_L1_DIKEY_1_5L = ['6304b87e6c7c1a0eea79e01e', '5a7b20fd8e19da0004bb27f8']
MINI_L1_1L_PAIR = ['5fbce44d7d580fc3304aee67', '5bdaa8ae13fd4900121665c3']
MINI_L1_KUCUKLER = ['5a7b1f608e19da0004bb2706', '5b30d3c4cebeab0004808a00']
for _ml1_kod in MINI_L1_DEPO_KODLARI:
    _ml1_mask = (df['Location code'].astype(str).str.lower().str.strip() == _ml1_kod.lower()) & (df['Is_Water'] == True)
    _ml1_df = df[_ml1_mask].copy()
    if _ml1_df.empty: continue
    df.loc[_ml1_mask, 'Final_Miktar'] = 0
    df.loc[_ml1_mask, 'Dikey_Elleçleme_Su'] = True
    df.loc[_ml1_mask, 'Kesinti_Nedeni'] = 'Dikey Elleçleme - Mini Layout 1'
    _layout_isaretle(_ml1_mask, 'Mini Layout 1', [list(MINI_L1_5L_URUNLER.keys()), MINI_L1_DIKEY_1_5L, MINI_L1_1L_PAIR, MINI_L1_KUCUKLER])
    def _ml1_get(pc, _d=_ml1_df):
        r = _d[_d['Product code'] == pc.lower()]
        return r.iloc[0] if not r.empty else None
    def _ml1_set(pc, qty, neden, _d=_ml1_df):
        r = _d[_d['Product code'] == pc.lower()]
        if not r.empty:
            df.at[r.index[0], 'Final_Miktar'] = qty
            df.at[r.index[0], 'Kesinti_Nedeni'] = neden
    for _pid in MINI_L1_5L_URUNLER.keys(): _dikey_normalize([_pid], 0.25, _ml1_get, _ml1_set, _std_flt, 'Dikey Elleçleme - 5L Tek Palet (Mini)')
    _dikey_normalize(MINI_L1_DIKEY_1_5L, 0.25, _ml1_get, _ml1_set, _std_flt, 'Dikey Elleçleme - 1.5L Dikey Palet (Mini)')
    _paylasimli(MINI_L1_1L_PAIR, '1L Palet (Mini)', _ml1_get, _ml1_set, _std_flt)
    _paylasimli(MINI_L1_KUCUKLER, 'Kucukler Paleti (Mini)', _ml1_get, _ml1_set, _std_flt)

# Mini Layout 2
MINI_L2_5L_URUNLER = {'5981ec31e97e8b000484eb96': 160, '5a7b21f69ccf1d00040084bf': 160}
MINI_L2_DIKEY_1_5L = ['6304b87e6c7c1a0eea79e01e', '5a7b20fd8e19da0004bb27f8']
MINI_L2_KUCUKLER = ['5fbce44d7d580fc3304aee67', '5bdaa8ae13fd4900121665c3', '5a7b1f608e19da0004bb2706', '5b30d3c4cebeab0004808a00']
for _ml2_kod in MINI_L2_DEPO_KODLARI:
    _ml2_mask = (df['Location code'].astype(str).str.lower().str.strip() == _ml2_kod.lower()) & (df['Is_Water'] == True)
    _ml2_df = df[_ml2_mask].copy()
    if _ml2_df.empty: continue
    df.loc[_ml2_mask, 'Final_Miktar'] = 0
    df.loc[_ml2_mask, 'Dikey_Elleçleme_Su'] = True
    df.loc[_ml2_mask, 'Kesinti_Nedeni'] = 'Dikey Elleçleme - Mini Layout 2'
    _layout_isaretle(_ml2_mask, 'Mini Layout 2', [list(MINI_L2_5L_URUNLER.keys()), MINI_L2_DIKEY_1_5L, MINI_L2_KUCUKLER])
    def _ml2_get(pc, _d=_ml2_df):
        r = _d[_d['Product code'] == pc.lower()]
        return r.iloc[0] if not r.empty else None
    def _ml2_set(pc, qty, neden, _d=_ml2_df):
        r = _d[_d['Product code'] == pc.lower()]
        if not r.empty:
            df.at[r.index[0], 'Final_Miktar'] = qty
            df.at[r.index[0], 'Kesinti_Nedeni'] = neden
    for _pid in MINI_L2_5L_URUNLER.keys(): _dikey_normalize([_pid], 0.25, _ml2_get, _ml2_set, _std_flt, 'Dikey Elleçleme - 5L Tek Palet (Mini)')
    _dikey_normalize(MINI_L2_DIKEY_1_5L, 0.25, _ml2_get, _ml2_set, _std_flt, 'Dikey Elleçleme - 1.5L Dikey Palet (Mini)')
    _paylasimli(MINI_L2_KUCUKLER, 'Kucukler Paleti (Mini L2)', _ml2_get, _ml2_set, _std_flt)

# XS Layout 1
XS_L1_5L_DIKEY = ['5981ec31e97e8b000484eb96', '5a7b21f69ccf1d00040084bf']
XS_L1_DIKEY_1_5L = ['6304b87e6c7c1a0eea79e01e', '5a7b20fd8e19da0004bb27f8']
XS_L1_KUCUKLER = ['5bdaa8ae13fd4900121665c3', '5a7b1f608e19da0004bb2706', '5b30d3c4cebeab0004808a00']
for _xl1_kod in XS_L1_DEPO_KODLARI:
    _xl1_mask = (df['Location code'].astype(str).str.lower().str.strip() == _xl1_kod.lower()) & (df['Is_Water'] == True)
    _xl1_df = df[_xl1_mask].copy()
    if _xl1_df.empty: continue
    df.loc[_xl1_mask, 'Final_Miktar'] = 0
    df.loc[_xl1_mask, 'Dikey_Elleçleme_Su'] = True
    df.loc[_xl1_mask, 'Kesinti_Nedeni'] = 'Dikey Elleçleme - XS Layout 1'
    _layout_isaretle(_xl1_mask, 'XS Layout 1', [XS_L1_5L_DIKEY, XS_L1_DIKEY_1_5L, XS_L1_KUCUKLER])
    def _xl1_get(pc, _d=_xl1_df):
        r = _d[_d['Product code'] == pc.lower()]
        return r.iloc[0] if not r.empty else None
    def _xl1_set(pc, qty, neden, _d=_xl1_df):
        r = _d[_d['Product code'] == pc.lower()]
        if not r.empty:
            df.at[r.index[0], 'Final_Miktar'] = qty
            df.at[r.index[0], 'Kesinti_Nedeni'] = neden
    _dikey_normalize(XS_L1_5L_DIKEY, 0.25, _xl1_get, _xl1_set, _std_flt, 'Dikey Elleçleme - 5L Dikey Palet (XS)')
    _dikey_normalize(XS_L1_DIKEY_1_5L, 0.25, _xl1_get, _xl1_set, _std_flt, 'Dikey Elleçleme - 1.5L Dikey Palet (XS)')
    _paylasimli(XS_L1_KUCUKLER, 'Kucukler Paleti (XS L1)', _xl1_get, _xl1_set, _std_flt)

# XS Layout 2
XS_L2_5L_URUNLER = {'5981ec31e97e8b000484eb96': 160, '5a7b21f69ccf1d00040084bf': 160}
XS_L2_DIKEY_1_5L = ['6304b87e6c7c1a0eea79e01e', '5a7b20fd8e19da0004bb27f8']
XS_L2_KUCUKLER = ['5bdaa8ae13fd4900121665c3', '5a7b1f608e19da0004bb2706', '5b30d3c4cebeab0004808a00']
for _xl2_kod in XS_L2_DEPO_KODLARI:
    _xl2_mask = (df['Location code'].astype(str).str.lower().str.strip() == _xl2_kod.lower()) & (df['Is_Water'] == True)
    _xl2_df = df[_xl2_mask].copy()
    if _xl2_df.empty: continue
    df.loc[_xl2_mask, 'Final_Miktar'] = 0
    df.loc[_xl2_mask, 'Dikey_Elleçleme_Su'] = True
    df.loc[_xl2_mask, 'Kesinti_Nedeni'] = 'Dikey Elleçleme - XS Layout 2'
    _layout_isaretle(_xl2_mask, 'XS Layout 2', [list(XS_L2_5L_URUNLER.keys()), XS_L2_DIKEY_1_5L, XS_L2_KUCUKLER])
    def _xl2_get(pc, _d=_xl2_df):
        r = _d[_d['Product code'] == pc.lower()]
        return r.iloc[0] if not r.empty else None
    def _xl2_set(pc, qty, neden, _d=_xl2_df):
        r = _d[_d['Product code'] == pc.lower()]
        if not r.empty:
            df.at[r.index[0], 'Final_Miktar'] = qty
            df.at[r.index[0], 'Kesinti_Nedeni'] = neden
    for _pid in XS_L2_5L_URUNLER.keys(): _dikey_normalize([_pid], 0.25, _xl2_get, _xl2_set, _std_flt, 'Dikey Elleçleme - 5L Tek Palet (XS L2)')
    _dikey_normalize(XS_L2_DIKEY_1_5L, 0.25, _xl2_get, _xl2_set, _std_flt, 'Dikey Elleçleme - 1.5L Dikey Palet (XS L2)')
    _paylasimli(XS_L2_KUCUKLER, 'Kucukler Paleti (XS L2)', _xl2_get, _xl2_set, _std_flt)

# XS Layout 3
XS_L3_5L_DIKEY = ['5981ec31e97e8b000484eb96', '5a7b21f69ccf1d00040084bf']
XS_L3_KALAN_PAYLASIMLI = ['6304b87e6c7c1a0eea79e01e', '5a7b20fd8e19da0004bb27f8', '5bdaa8ae13fd4900121665c3', '5a7b1f608e19da0004bb2706', '5b30d3c4cebeab0004808a00']
for _xl3_kod in XS_L3_DEPO_KODLARI:
    _xl3_mask = (df['Location code'].astype(str).str.lower().str.strip() == _xl3_kod.lower()) & (df['Is_Water'] == True)
    _xl3_df = df[_xl3_mask].copy()
    if _xl3_df.empty: continue
    df.loc[_xl3_mask, 'Final_Miktar'] = 0
    df.loc[_xl3_mask, 'Dikey_Elleçleme_Su'] = True
    df.loc[_xl3_mask, 'Kesinti_Nedeni'] = 'Dikey Elleçleme - XS Layout 3'
    _layout_isaretle(_xl3_mask, 'XS Layout 3', [XS_L3_5L_DIKEY, XS_L3_KALAN_PAYLASIMLI])
    def _xl3_get(pc, _d=_xl3_df):
        r = _d[_d['Product code'] == pc.lower()]
        return r.iloc[0] if not r.empty else None
    def _xl3_set(pc, qty, neden, _d=_xl3_df):
        r = _d[_d['Product code'] == pc.lower()]
        if not r.empty:
            df.at[r.index[0], 'Final_Miktar'] = qty
            df.at[r.index[0], 'Kesinti_Nedeni'] = neden
    _dikey_normalize(XS_L3_5L_DIKEY, 0.25, _xl3_get, _xl3_set, _std_flt, 'Dikey Elleçleme - 5L Dikey Palet (XS L3)')
    _paylasimli(XS_L3_KALAN_PAYLASIMLI, 'Kalan Palet (XS L3)', _xl3_get, _xl3_set, _std_flt)

# ---------- V2 LAYOUT'LAR ----------
_5L = ['5981ec31e97e8b000484eb96', '5a7b21f69ccf1d00040084bf']
_15L = ['6304b87e6c7c1a0eea79e01e', '5a7b20fd8e19da0004bb27f8']
_KUCUKLER_V2 = ['5bdaa8ae13fd4900121665c3', '6304c187a3a9db67ff436dd2', '5fbce44d7d580fc3304aee67']

# XS Layout 1 V2 — Guzelyali
_dikey_layout_calistir(XS_L1_V2_DEPO_KODLARI, 'XS Layout 1 V2', [
    ('dikey', _5L, 'Dikey Elleçleme - 5L Dikey Palet (XS L1 V2)'),
    ('dikey', _15L, 'Dikey Elleçleme - 1.5L Dikey Palet (XS L1 V2)'),
    ('paylasimli', _KUCUKLER_V2, 'Kucukler Paleti (XS L1 V2)'),
])

# XS Layout 2 V2 — TEM Avrupa Konutlari
_dikey_layout_calistir(XS_L2_V2_DEPO_KODLARI, 'XS Layout 2 V2', [
    ('dikey_tek', _5L, 'Dikey Elleçleme - 5L Tek Palet (XS L2 V2)'),
    ('dikey', _15L, 'Dikey Elleçleme - 1.5L Dikey Palet (XS L2 V2)'),
    ('paylasimli', _KUCUKLER_V2, 'Kucukler Paleti (XS L2 V2)'),
])

# XS Layout 3 V2 — Meydankavagi
_dikey_layout_calistir(XS_L3_V2_DEPO_KODLARI, 'XS Layout 3 V2', [
    ('dikey', _5L, 'Dikey Elleçleme - 5L Dikey Palet (XS L3 V2)'),
    ('paylasimli', _15L + _KUCUKLER_V2, 'Kalan Palet (XS L3 V2)'),
])

# Mini Layout 2 V2 — Kuzguncuk
_dikey_layout_calistir(MINI_L2_V2_DEPO_KODLARI, 'Mini Layout 2 V2', [
    ('dikey_tek', _5L, 'Dikey Elleçleme - 5L Tek Palet (Mini L2 V2)'),
    ('dikey', _15L, 'Dikey Elleçleme - 1.5L Dikey Palet (Mini L2 V2)'),
    ('paylasimli', ['5fbce44d7d580fc3304aee67', '5bdaa8ae13fd4900121665c3', '6304c187a3a9db67ff436dd2'], 'Kucukler Paleti (Mini L2 V2)'),
])

# ==========================================
# 🏷️ DİKEY PALET NUMARALANDIRMASI
# ==========================================
df['Dikey_Palet_No'] = '-'
df['Dikey_Palet_Tipi'] = '-'

_pc_norm = df['Product code'].astype(str).str.lower().str.strip()
for _lay, _map in _DIKEY_PALET_MAP.items():
    _lay_mask = (df['Layout_Tipi'] == _lay) & (df['Dikey_Elleçleme_Su'] == True)
    if not _lay_mask.any(): continue
    for _sku, (_pno, _ptip) in _map.items():
        _m = _lay_mask & (_pc_norm == str(_sku).lower().strip())
        if _m.any():
            df.loc[_m, 'Dikey_Palet_No'] = f'Palet {_pno}'
            df.loc[_m, 'Dikey_Palet_Tipi'] = _ptip

df['Dikey_Palet_Iptal'] = False

# Dikey elleçleme su miktarlarını yeniden yazdı → sayım kısıtı tekrar uygulanır
_sayim_kisiti_uygula()

# ==========================================
# 🎯 COVER SIRALI KESİM MOTORU (v6)
# ==========================================
# Priority grubu icinde kesim sirasi COVER'a gore belirlenir.
# Her batch kesiminden sonra o satirin cover'i yeniden hesaplanir ve sira guncellenir.
# Cover = (mevcut stok + o anki Final_Miktar) / gunluk satis
#   - su satirlari:      Net_Su_Stok  / (Daily FC, yoksa water frc t)
#   - ambient satirlari: End balance + Open purchase orders / Daily FC
# FC = 0 ise cover sonsuz kabul edilir ve once kesilir.

_WFRC_VAR = 'water frc t' in df.columns

df['Kesim_Cover_Basi'] = np.nan
df['Kesim_Cover_Sonu'] = np.nan
df['Kesim_Adedi'] = 0

def _kesim_fc(idx):
    fc = float(pd.to_numeric(df.at[idx, 'Daily FC'], errors='coerce') or 0)
    if fc <= 0 and _WFRC_VAR:
        fc = float(pd.to_numeric(df.at[idx, 'water frc t'], errors='coerce') or 0)
    return fc

def _kesim_stok(idx):
    if bool(df.at[idx, 'Is_Water']):
        return float(pd.to_numeric(df.at[idx, 'Net_Su_Stok'], errors='coerce') or 0)
    return (float(pd.to_numeric(df.at[idx, 'End balance'], errors='coerce') or 0) +
            float(pd.to_numeric(df.at[idx, 'Open purchase orders'], errors='coerce') or 0))

def _kesim_cover(idx):
    """Siparis dahil guncel cover — her kesimden sonra yeniden cagrilir."""
    fc = _kesim_fc(idx)
    fin = float(df.at[idx, 'Final_Miktar'] or 0)
    if fc <= 0: return float('inf')
    return (_kesim_stok(idx) + fin) / fc

def _std_batch(idx):
    b = df.at[idx, 'Order batch size']
    b = 0.0 if pd.isna(b) else float(b)
    if b > 0: return b
    s = float(df.at[idx, 'SON_calculated'] or 1)
    return s if s > 0 else 1.0

def _su_batch(idx):
    b = df.at[idx, 'Order batch size']
    b = 0.0 if pd.isna(b) else float(b)
    return b if b > 0 else 1.0

_KESIM_IZ = None   # palet limiti adımında her batch kesimini backlog hesabına bildirir

def _prio_grup_kes(idx_listesi, kalan, birim_fn, neden, batch_fn=_std_batch):
    """Bir priority grubu icinde cover'i en yuksek satirdan baslayarak 1 batch keser.
    Kesim sonrasi satirin cover'i yeniden hesaplanip heap'e geri konur.
    birim_fn(idx, dus) -> kesimin hedef birimi cinsinden katkisi (litre / palet / koli)
    Donus: bu grupta kesilen toplam (birim)."""
    if kalan <= 0: return 0.0
    _h = []
    for i in idx_listesi:
        if float(df.at[i, 'Final_Miktar'] or 0) <= 0: continue
        _cov = _kesim_cover(i)
        if pd.isna(df.at[i, 'Kesim_Cover_Basi']):
            df.at[i, 'Kesim_Cover_Basi'] = _cov if _cov != float('inf') else np.inf
        heapq.heappush(_h, (-_cov, i))

    kesilen = 0.0
    while _h and kesilen < kalan:
        _negcov, i = heapq.heappop(_h)
        fin = float(df.at[i, 'Final_Miktar'] or 0)
        if fin <= 0: continue
        dus = min(batch_fn(i), fin)
        if dus <= 0: continue
        katki = birim_fn(i, dus)
        if katki <= 0: continue          # bu satir hedefe katki yapmiyor → listeden dusur

        df.at[i, 'Final_Miktar'] = fin - dus
        df.at[i, 'Kesinti_Nedeni'] = neden
        df.at[i, 'Kesim_Adedi'] = int(df.at[i, 'Kesim_Adedi'] or 0) + 1
        kesilen += katki
        if _KESIM_IZ is not None: _KESIM_IZ(i, dus, katki)

        _yeni_cov = _kesim_cover(i)
        df.at[i, 'Kesim_Cover_Sonu'] = _yeni_cov if _yeni_cov != float('inf') else np.inf
        if df.at[i, 'Final_Miktar'] > 0:
            heapq.heappush(_h, (-_yeni_cov, i))   # cover dustu → sirasi guncellendi
    return kesilen

# ==========================================
# ⚡ 5. OPTİMİZASYON (SİPARİŞ KISMA ADIMLARI)
# ==========================================
print("Optimizasyon hesaplanıyor... (kesim sirasi: priority → cover)")

# 5.1 HACİM KISMA (cover sirali)
depo_hacim = df[~df['Sadece_A_Iptal']].groupby('Location name').agg({   # sadece A testinde A dışı öneri hacme sayılmaz
    'Satir_Onerilen_Hacim': 'sum',
    'Kalan_Net_Hacim_Litre': 'first',
    'Avg. ambient_dolap_hacim': 'first',
    'Hard_Stop_Orani': 'first'
}).reset_index()

def _neden_hacim(oran):
    return f"Kapasite Zorlamasi ({round(oran * 100):g}% Limit) - Hacim Icin Kisildi"

def _birim_hacim(idx, dus):
    bh = df.at[idx, 'hacim2']
    if pd.isna(bh) or float(bh) <= 0: return 0.0
    return dus * float(bh)

for _, r in depo_hacim.iterrows():
    esnek_limit = r['Kalan_Net_Hacim_Litre'] + (r['Avg. ambient_dolap_hacim'] * (r['Hard_Stop_Orani'] - 1))
    if r['Satir_Onerilen_Hacim'] > esnek_limit:
        kesilecek_hacim = r['Satir_Onerilen_Hacim'] - esnek_limit
        loc_mask = (df['Location name'] == r['Location name']) & (df['Cut_Priority'] < 101) & (df['Final_Miktar'] > 0)
        hedef = df.loc[loc_mask, ['Cut_Priority']]
        if hedef.empty: continue
        kesilen_hacim = 0.0
        for current_prio in sorted(hedef['Cut_Priority'].unique()):
            if kesilen_hacim >= kesilecek_hacim: break
            _idxler = hedef.index[hedef['Cut_Priority'] == current_prio].tolist()
            kesilen_hacim += _prio_grup_kes(_idxler, kesilecek_hacim - kesilen_hacim,
                                            _birim_hacim, _neden_hacim(r['Hard_Stop_Orani']))

# 5.1.5 SU PALET KISMA (cover sirali)
su_depo_listesi = df[df['Is_Water'] == True]['Location name'].unique()
for depo_adi in su_depo_listesi:
    d_rows = df[(df['Location name'] == depo_adi) & (df['Is_Water'] == True) & (df['Dikey_Elleçleme_Su'] != True)]
    if d_rows.empty or pd.isna(d_rows['Max_Su_Palet_Kapasitesi'].iloc[0]): continue
    su_limit = d_rows['Max_Su_Palet_Kapasitesi'].iloc[0]
    mevcut_su_paleti = d_rows['Mevcut_Kaplanan_Su_Paleti'].sum()
    gelecek_su_paleti = (d_rows['Final_Miktar'] / d_rows['palet']).sum()
    toplam_su_yuku = mevcut_su_paleti + gelecek_su_paleti
    if toplam_su_yuku > su_limit:
        kesilecek_su_paleti = toplam_su_yuku - su_limit
        loc_mask = (df['Location name'] == depo_adi) & (df['Is_Water'] == True) & (df['Dikey_Elleçleme_Su'] != True) & (df['Cut_Priority'] < 101) & (df['Final_Miktar'] > 0)
        hedef = df.loc[loc_mask, ['Cut_Priority']]
        if hedef.empty: continue
        _neden_su = f"Su Depo Kapasitesi ({su_limit} Palet) Asildi"

        def _birim_su_palet(idx, dus):
            pk = float(df.at[idx, 'palet'] or 0)
            return (dus / pk) if pk > 0 else 0.0

        kesilen_palet = 0.0
        for current_prio in sorted(hedef['Cut_Priority'].unique()):
            if kesilen_palet >= kesilecek_su_paleti: break
            _idxler = hedef.index[hedef['Cut_Priority'] == current_prio].tolist()
            kesilen_palet += _prio_grup_kes(_idxler, kesilecek_su_paleti - kesilen_palet,
                                            _birim_su_palet, _neden_su, batch_fn=_su_batch)

# 5.2 PALET KISMA (cover sirali)
def _birim_tir_palet(idx, dus):
    if bool(df.at[idx, 'Is_Water']):
        pk = float(df.at[idx, 'palet'] or 0)
        return (dus / pk) if pk > 0 else 0.0
    son = float(df.at[idx, 'SON_calculated'] or 1)
    return dus / (son * 50) if son > 0 else 0.0

# Backlog payı: depoda kesim cover sırasıyla ilerler. Backlog olmasaydı da kesilecek kadar palet (sipariş − limit)
# ilk kesilenlerdir; ondan sonra kesilen her palet backlog yüzünden kesilmiş sayılır ve satırına adet olarak yazılır.
df['Backlog_Kesilen_Miktar'] = 0.0
depo_listesi = df['Location name'].unique()
for depo_adi in depo_listesi:
    d_rows = df[df['Location name'] == depo_adi]
    if d_rows['Sadece_A_Test'].any(): continue      # sadece A testi: TIR palet limiti uygulanmaz
    domain = d_rows['Domain Type'].iloc[0]
    etkili_backlog = d_rows['Etkili_Backlog_Palet'].iloc[0]
    limit = d_rows['Tir_Limiti'].iloc[0]
    def _depo_palet_toplami():
        _d = df[df['Location name'] == depo_adi]
        return np.where(_d['Is_Water'] == True, _d['Final_Miktar'] / _d['palet'], _d['Final_Miktar'] / (_d['SON_calculated'] * 50)).sum()
    current_palets = _depo_palet_toplami()
    if (current_palets + etkili_backlog) <= limit: continue
    kesilecek_palet = (current_palets + etkili_backlog) - limit
    kesilen_palet = 0.0
    _neden_palet = f"{domain} Palet Limiti Asildi"
    _iz = {'esik': max(current_palets - limit, 0.0), 'top': 0.0}
    def _backlog_iz(i, dus, katki, _iz=_iz):
        bas = _iz['top']; _iz['top'] = son = bas + katki
        pay = max(0.0, son - max(_iz['esik'], bas))
        if katki > 0 and pay > 0:
            df.at[i, 'Backlog_Kesilen_Miktar'] = float(df.at[i, 'Backlog_Kesilen_Miktar'] or 0) + dus * min(pay / katki, 1.0)
    _KESIM_IZ = _backlog_iz

    for _faz, _faz_mask in [(1, (df['Is_Water'] != True)), (2, (df['Is_Water'] == True) & (df['Dikey_Elleçleme_Su'] != True))]:
        if kesilen_palet >= kesilecek_palet: break
        loc_mask = ((df['Location name'] == depo_adi) & _faz_mask & (df['Cut_Priority'] < 101) & (df['Final_Miktar'] > 0))
        hedef = df.loc[loc_mask, ['Cut_Priority']]
        if hedef.empty: continue
        for current_prio in sorted(hedef['Cut_Priority'].unique()):
            if kesilen_palet >= kesilecek_palet: break
            _idxler = hedef.index[hedef['Cut_Priority'] == current_prio].tolist()
            kesilen_palet += _prio_grup_kes(_idxler, kesilecek_palet - kesilen_palet,
                                            _birim_tir_palet, _neden_palet)

    if kesilen_palet < kesilecek_palet:
        _dikey_mask = ((df['Location name'] == depo_adi) & (df['Dikey_Elleçleme_Su'] == True) & (df['Final_Miktar'] > 0))
        _dikey_rows = df[_dikey_mask]
        if not _dikey_rows.empty:
            _paletler = []
            for _pno, _pg in _dikey_rows.groupby('Dikey_Palet_No'):
                _yuk = float((_pg['Final_Miktar'] / _pg['palet']).sum())
                if _yuk <= 0: continue
                _net_top = float(_pg['Net_Su_Stok'].fillna(0).sum())
                _fc_top = float(pd.to_numeric(_pg['Daily FC'], errors='coerce').fillna(0).sum())
                if _fc_top <= 0: _fc_top = float(pd.to_numeric(_pg.get('water frc t', 0), errors='coerce').fillna(0).sum())
                _cover = (_net_top + _pg['Final_Miktar'].sum()) / _fc_top if _fc_top > 0 else float('inf')
                _paletler.append((_cover, _pno, _yuk, list(_pg.index)))
            _paletler.sort(key=lambda x: -(x[0] if x[0] != float('inf') else 1e18))
            for _cover, _pno, _yuk, _idxler in _paletler:
                if kesilen_palet >= kesilecek_palet: break
                for _ix in _idxler:
                    _f0, _pk = float(df.at[_ix, 'Final_Miktar'] or 0), float(df.at[_ix, 'palet'] or 0)
                    if _f0 > 0 and _pk > 0: _backlog_iz(_ix, _f0, _f0 / _pk)
                    df.at[_ix, 'Final_Miktar'] = 0
                    df.at[_ix, 'Dikey_Palet_Iptal'] = True
                    df.at[_ix, 'Kesinti_Nedeni'] = f"{domain} Palet Limiti Asildi - DİKEY PALET IPTAL ({_pno})"
                kesilen_palet += _yuk

_KESIM_IZ = None

# 5.3 MERKEZ SATIR LİMİTİ
aktif_satirlar = df[df['Final_Miktar'] > 0]
if len(aktif_satirlar) > MAX_SATIR_LIMITI:
    sil_sayisi = len(aktif_satirlar) - MAX_SATIR_LIMITI
    _aday = aktif_satirlar[(aktif_satirlar['Cut_Priority'] < 101) & (aktif_satirlar['Is_Water'] != True) &
                           ~aktif_satirlar['Sadece_A_Test']].copy()
    _aday['_cover_sirasi'] = [(-1) * (_kesim_cover(i) if _kesim_cover(i) != float('inf') else 1e18) for i in _aday.index]
    sil_idx = _aday.sort_values(['Cut_Priority', '_cover_sirasi']).head(sil_sayisi).index
    df.loc[sil_idx, 'Final_Miktar'] = 0
    df.loc[sil_idx, 'Kesinti_Nedeni'] = "Merkez Depo Satir Limiti Asildi"

# 5.4 MERKEZ KOLİ LİMİTİ (cover sirali)
def _birim_koli(idx, dus):
    son = float(df.at[idx, 'SON_calculated'] or 1)
    return dus / son if son > 0 else 0.0

mevcut_koli = (df['Final_Miktar'] / df['SON_calculated']).sum()
if mevcut_koli > MAX_KOLI_LIMITI:
    kesilecek_koli = mevcut_koli - MAX_KOLI_LIMITI
    kesilen_koli = 0.0
    for _faz_mask in [(df['Is_Water'] != True), ((df['Is_Water'] == True) & (df['Dikey_Elleçleme_Su'] != True))]:
        if kesilen_koli >= kesilecek_koli: break
        loc_mask = _faz_mask & (df['Cut_Priority'] < 101) & (df['Final_Miktar'] > 0) & ~df['Sadece_A_Test']
        hedef = df.loc[loc_mask, ['Cut_Priority']]
        if hedef.empty: continue
        for current_prio in sorted(hedef['Cut_Priority'].unique()):
            if kesilen_koli >= kesilecek_koli: break
            _idxler = hedef.index[hedef['Cut_Priority'] == current_prio].tolist()
            kesilen_koli += _prio_grup_kes(_idxler, kesilecek_koli - kesilen_koli,
                                           _birim_koli, "Merkez Koli Limiti Asildi")
    _kalan_asim = kesilecek_koli - kesilen_koli
    if _kalan_asim > 0.5:
        print(f"  ⚠️  Merkez koli limiti {round(_kalan_asim):,} koli asili kaldi — kesilebilecek satir tukendi (dikey paletler muaf).")

# ==========================================
# ⚡ 5.5. DİNAMİK KAPASİTE TABANLI GERİ YÜKLEME (RESTORATION)
# ==========================================
print("5.5. Geri yükleme (Çoklu Kısıt - Boşluk Doldurma) çalışıyor...")
df['Final_Palet'] = np.where(df['Is_Water'] == True, df['Final_Miktar'] / df['palet'], df['Final_Miktar'] / (df['SON_calculated'] * 50))
df['Final_Palet'] = pd.Series(df['Final_Palet']).fillna(0)

df['temp_hacim'] = np.where(mask_su | mask_demirbas, 0, df['Final_Miktar'] * df['hacim2'].fillna(0.5))   # hacimsiz ürün 0,5 L (kısma ve raporla aynı)
df['temp_palet'] = np.where(mask_demirbas, 0, np.where(mask_su, df['Final_Miktar'] / df['palet'], df['Final_Miktar'] / (df['SON_calculated'] * 50)))
df['temp_su_palet'] = np.where(mask_su, df['Final_Miktar'] / df['palet'], 0)
df['temp_koli'] = df['Final_Miktar'] / df['SON_calculated']

total_center_koli = df['temp_koli'].sum()
free_center_koli = max(0.0, MAX_KOLI_LIMITI - total_center_koli)

depo_groups = df.groupby('Location name').agg({
    'Kalan_Net_Hacim_Litre': 'first',
    'Avg. ambient_dolap_hacim': 'first',
    'Hard_Stop_Orani': 'first',
    'Tir_Limiti': 'first',
    'Etkili_Backlog_Palet': 'first',
    'Max_Su_Palet_Kapasitesi': 'first',
    'Mevcut_Kaplanan_Su_Paleti': 'sum',
    'temp_hacim': 'sum',
    'temp_palet': 'sum',
    'temp_su_palet': 'sum'
})

depo_limits = {}
for depo, row in depo_groups.iterrows():
    esnek_limit = row['Kalan_Net_Hacim_Litre'] + (row['Avg. ambient_dolap_hacim'] * (row['Hard_Stop_Orani'] - 1))
    free_vol = max(0.0, esnek_limit - row['temp_hacim'])
    free_truck = max(0.0, row['Tir_Limiti'] - (row['temp_palet'] + row['Etkili_Backlog_Palet']))
    max_su_cap = row['Max_Su_Palet_Kapasitesi']
    if pd.isna(max_su_cap): free_su = 99999.0
    else: free_su = max(0.0, max_su_cap - (row['Mevcut_Kaplanan_Su_Paleti'] + row['temp_su_palet']))
    depo_limits[depo] = {'free_vol': free_vol, 'free_truck': free_truck, 'free_su': free_su}

# Geri yuklemede de cover mantigi: once yuksek priority, esitlikte DUSUK cover
aday_mask = (df['Final_Miktar'] > 0) & (df['Final_Miktar'] < df['Orijinal_Miktar']) & (df['Is_Water'] != True)
adaylar = df[aday_mask].copy()
if not adaylar.empty:
    adaylar['_cover_geri'] = [(_kesim_cover(i) if _kesim_cover(i) != float('inf') else 1e18) for i in adaylar.index]
    adaylar = adaylar.sort_values(['Cut_Priority', '_cover_geri'], ascending=[False, True])

df['Geri_Eklenen_Miktar'] = 0
df['Geri_Yukleme_Yapildi'] = False
df['Geri_Yukleme_Notu'] = ''

for idx in adaylar.index:
    depo = df.at[idx, 'Location name']
    is_d = bool(mask_demirbas.at[idx])
    urun_hacmi = df.at[idx, 'hacim2']
    if pd.isna(urun_hacmi): urun_hacmi = 0.5   # kısma ve raporla aynı varsayım
    batch = df.at[idx, 'Order batch size']
    if pd.isna(batch) or batch <= 0: batch = df.at[idx, 'SON_calculated']
    son = df.at[idx, 'SON_calculated']
    eksik = df.at[idx, 'Orijinal_Miktar'] - df.at[idx, 'Final_Miktar']
    is_t = bool(df.at[idx, 'Sadece_A_Test'])   # sadece A testi: yalnız hacim bakılır (koli/TIR yok)

    while eksik > 0:
        eklenecek = min(batch, eksik)
        req_koli = eklenecek / son
        if is_d:
            req_hacim = 0.0; req_truck_palet = 0.0
        else:
            req_hacim = eklenecek * urun_hacmi
            req_truck_palet = eklenecek / (son * 50) if son > 0 else 0.0

        if (not is_t) and req_koli > free_center_koli: break
        if (not is_t) and req_truck_palet > depo_limits[depo]['free_truck']: break
        if (not is_d) and req_hacim > depo_limits[depo]['free_vol']: break

        df.at[idx, 'Final_Miktar'] += eklenecek
        df.at[idx, 'Geri_Eklenen_Miktar'] += eklenecek
        df.at[idx, 'Geri_Yukleme_Yapildi'] = True
        df.at[idx, 'Geri_Yukleme_Notu'] = 'Kapasite Limitleri Dahilinde Dinamik Geri Kazanım'

        free_center_koli -= req_koli
        depo_limits[depo]['free_truck'] -= req_truck_palet
        if not is_d: depo_limits[depo]['free_vol'] -= req_hacim
        eksik -= eklenecek
        if df.at[idx, 'Final_Miktar'] >= df.at[idx, 'Orijinal_Miktar']: break

df.drop(columns=['temp_hacim', 'temp_palet', 'temp_su_palet', 'temp_koli'], inplace=True, errors='ignore')

# ==========================================
# 💧 5.6. MERKEZ DEPO SU STOK MUTABAKATI (End Balance DC)
# ==========================================
print("5.6. Merkez depo su stok mutabakati (End Balance DC) calisiyor...")

_ABC_KESIM_SIRASI = {'E': 0, 'D': 1, 'C': 2, 'B': 3, 'A': 4}
_ABC_BILINMEYEN = -1
_su_mutabakat = []
# Ambient'e geçen satırlar da aynı merkez su stoğundan düştüğü için toplama dahil
_su_mask_glob = (df['Is_Water'] == True) | (df['Ambient_Gecis'] == True)

for _pcode, _pgrup in df[_su_mask_glob].groupby('Product code'):
    _dc = pd.to_numeric(_pgrup['End Balance DC'], errors='coerce').max()
    _once = float(_pgrup['Final_Miktar'].sum())
    if pd.isna(_dc):
        _su_mutabakat.append({
            'Product code': _pcode, 'Urun Adi': str(_pgrup['Product name'].dropna().iloc[0]) if _pgrup['Product name'].notna().any() else '-',
            'End Balance DC': None, 'Toplam Final (Once)': round(_once, 1), 'Toplam Final (Sonra)': round(_once, 1), 'Kesilen': 0.0,
            'Kalan Merkez Stok': None, 'Durum': 'DC VERISI YOK - kontrol edilemedi',
        })
        continue
    _dc = float(_dc)
    _kesilen_top = 0.0
    if _once > _dc:
        _fazla = _once - _dc
        _adaylar = _pgrup[_pgrup['Final_Miktar'] > 0]
        _heap = []
        for _idx, _r in _adaylar.iterrows():
            _abc = str(_r.get('ABC class', '')).strip().upper()
            _rank = _ABC_KESIM_SIRASI.get(_abc, _ABC_BILINMEYEN)
            _fc = float(pd.to_numeric(_r.get('Daily FC', 0), errors='coerce') or 0)
            if _fc <= 0: _fc = float(pd.to_numeric(_r.get('water frc t', 0), errors='coerce') or 0)
            _net = float(_r.get('Net_Su_Stok', 0) or 0)
            _fin = float(_r['Final_Miktar'])
            _obs = float(pd.to_numeric(_r.get('Order batch size', 0), errors='coerce') or 0)
            if _obs <= 0: _obs = 1.0
            _cov = float('inf') if _fc <= 0 else (_net + _fin) / _fc
            heapq.heappush(_heap, (_rank, -_cov if _cov != float('inf') else -1e18, _idx, _net, _fc, _obs))
        while _fazla > 0 and _heap:
            _rank, _negcov, _idx, _net, _fc, _obs = heapq.heappop(_heap)
            _fin = float(df.at[_idx, 'Final_Miktar'])
            if _fin <= 0: continue
            _dus = _obs if _fin >= _obs else _fin
            df.at[_idx, 'Final_Miktar'] = _fin - _dus
            _yeni_neden = "Merkez Depo Su Stogu (End Balance DC) Asildi"
            if df.at[_idx, 'Dikey_Elleçleme_Su'] == True: _yeni_neden += " - DİKEY PALET BOZULDU"
            df.at[_idx, 'Kesinti_Nedeni'] = _yeni_neden
            _fazla -= _dus
            _kesilen_top += _dus
            _kalan = _fin - _dus
            if _kalan > 0:
                _cov = float('inf') if _fc <= 0 else (_net + _kalan) / _fc
                heapq.heappush(_heap, (_rank, -_cov if _cov != float('inf') else -1e18, _idx, _net, _fc, _obs))
    _sonra = float(df.loc[_pgrup.index, 'Final_Miktar'].sum())
    _su_mutabakat.append({
        'Product code': _pcode, 'Urun Adi': str(_pgrup['Product name'].dropna().iloc[0]) if _pgrup['Product name'].notna().any() else '-',
        'End Balance DC': round(_dc, 1), 'Toplam Final (Once)': round(_once, 1), 'Toplam Final (Sonra)': round(_sonra, 1),
        'Kesilen': round(_kesilen_top, 1), 'Kalan Merkez Stok': round(_dc - _sonra, 1),
        'Durum': 'OK' if _sonra <= _dc + 0.001 else f'HALA ASIYOR ({round(_sonra - _dc, 1)})',
    })

_df_su_mutabakat = pd.DataFrame(_su_mutabakat)

_dc_map = _df_su_mutabakat.set_index('Product code')['End Balance DC'].to_dict() if not _df_su_mutabakat.empty else {}
_tf_map = _df_su_mutabakat.set_index('Product code')['Toplam Final (Sonra)'].to_dict() if not _df_su_mutabakat.empty else {}
df['End_Balance_DC_Urun'] = df['Product code'].map(_dc_map)
df['Toplam_Final_Tum_Depolar'] = df['Product code'].map(_tf_map)

# Son güvenlik: hiçbir adım sayım kısıtlı depoya miktar yazmamış olmalı
_sayim_kisiti_uygula()

# ==========================================
# 📊 6. ANALİTİK RAPORLAMA VE HAZIRLIK
# ==========================================
print("Raporlar ve çıktılar hazırlanıyor...")

# Final cover (siparis dahil) — kesim sonrasi nihai durum
df['Final_Cover_Gun'] = [
    (lambda c: np.nan if c == float('inf') else round(c, 2))(_kesim_cover(i)) for i in df.index
]

df['Fark (Kesilen Miktar)'] = df['Orijinal_Miktar'] - df['Final_Miktar']
df['Satir_Kesinti_Orani (%)'] = np.where(df['Orijinal_Miktar'] > 0, round((df['Fark (Kesilen Miktar)'] / df['Orijinal_Miktar']) * 100, 1), 0)
df['Final_Palet'] = np.where(df['Is_Water'] == True, df['Final_Miktar'] / df['palet'], df['Final_Miktar'] / (df['SON_calculated'] * 50))
df['Final_Palet'] = pd.Series(df['Final_Palet']).fillna(0)
df['Final_Hacim_Litre'] = df['Final_Miktar'] * df['hacim2'].fillna(0.5)
df['Kesilen_Hacim_Litre'] = df['Fark (Kesilen Miktar)'] * df['hacim2'].fillna(0.5)

df.loc[mask_su, 'Final_Hacim_Litre'] = 0
df.loc[mask_su, 'Kesilen_Hacim_Litre'] = 0
df.loc[mask_demirbas, 'Final_Palet'] = 0
df.loc[mask_demirbas, 'Final_Hacim_Litre'] = 0
df.loc[mask_demirbas, 'Kesilen_Hacim_Litre'] = 0

depo_final_ozet = df.groupby('Location name').agg(
    Domain_Type=('Domain Type', 'first'),
    Tir_Limiti=('Tir_Limiti', 'first'),
    Tir_Limiti_Kaynagi=('Tir_Limiti_Kaynagi', 'first'),
    Maksimum_Hacim_Litre=('Avg. ambient_dolap_hacim', 'first'),
    Net_Hacim_Boslugu_Litre=('Kalan_Net_Hacim_Litre', 'first'),
    Onerilen_Toplam_Hacim_Litre=('Satir_Onerilen_Hacim', 'sum'),
    Final_Toplam_Hacim_Litre=('Final_Hacim_Litre', 'sum'),
    Depo_Orijinal_Palet_Toplami=('Mevcut_Palet', 'sum'),
    Depo_Final_Palet_Toplami=('Final_Palet', 'sum'),
    Mevcut_Gercek_Backlog=('Backlog_Palet_Sayisi', 'first'),
    Etkili_Sarkan_Backlog=('Etkili_Backlog_Palet', 'first'),
    Esnek_Hacim_Orani=('Hard_Stop_Orani', 'first')
).reset_index()

depo_final_ozet['Depo_Total_Gelecek_Yuk_Palet'] = depo_final_ozet['Depo_Final_Palet_Toplami'] + depo_final_ozet['Etkili_Sarkan_Backlog']
depo_final_ozet['Hacim_Doluluk_Verimi (%)'] = (depo_final_ozet['Final_Toplam_Hacim_Litre'] / depo_final_ozet['Net_Hacim_Boslugu_Litre'] * 100).replace([np.inf, -np.inf], 0).fillna(0).round(1)

depo_final_ozet['Teslimat_Anindaki_Dolu_Hacim'] = depo_final_ozet['Maksimum_Hacim_Litre'] - depo_final_ozet['Net_Hacim_Boslugu_Litre']
depo_final_ozet['Gelecek_Teslimat_Sonrasi_Doluluk (%)'] = (((depo_final_ozet['Teslimat_Anindaki_Dolu_Hacim'] + depo_final_ozet['Final_Toplam_Hacim_Litre']) / depo_final_ozet['Maksimum_Hacim_Litre']) * 100).replace([np.inf, -np.inf], 0).fillna(0).round(1)
depo_final_ozet['Orijinal_Teslimat_Sonrasi_Doluluk (%)'] = (((depo_final_ozet['Teslimat_Anindaki_Dolu_Hacim'] + depo_final_ozet['Onerilen_Toplam_Hacim_Litre']) / depo_final_ozet['Maksimum_Hacim_Litre']) * 100).replace([np.inf, -np.inf], 0).fillna(0).round(1)

cols_to_drop = ['Depo_Orijinal_Palet_Toplami', 'Depo_Final_Palet_Toplami', 'Depo_Total_Gelecek_Yuk_Palet', 'Gelecek_Teslimat_Sonrasi_Doluluk (%)', 'Orijinal_Teslimat_Sonrasi_Doluluk (%)']
df = df.drop(columns=[c for c in cols_to_drop if c in df.columns])
df = pd.merge(df, depo_final_ozet[['Location name', 'Depo_Orijinal_Palet_Toplami', 'Depo_Final_Palet_Toplami', 'Depo_Total_Gelecek_Yuk_Palet', 'Gelecek_Teslimat_Sonrasi_Doluluk (%)', 'Orijinal_Teslimat_Sonrasi_Doluluk (%)']], on='Location name', how='left')

_layout_cols = [c for c in ['Layout_Tipi', 'Layout_Listesinde'] if c in df.columns]
df = df[[c for c in df.columns if c not in _layout_cols] + _layout_cols]

# ==========================================
# ⚡ FAST ACCAPTENCE KOLONU
# ==========================================
df['Fast Accaptence'] = np.where(
    df['Location name'].astype(str).str.strip().str.lower().isin(FAST_ACC_DEPOLAR), 1, 0
)

# ----------------- RAPOR HAZIRLIKLARI (ESKİDEN AYRI EXCEL'Dİ) -----------------
islem_gorenler = df[df['Fark (Kesilen Miktar)'] > 0][
    ['Location name', 'Product code', 'Product name', 'Domain Type', 'Backlog_Limiti_Asildi',
     'Orijinal_Miktar', 'Final_Miktar', 'Fark (Kesilen Miktar)', 'Satir_Kesinti_Orani (%)',
     'Satir_Onerilen_Hacim', 'Kesilen_Hacim_Litre', 'Final_Hacim_Litre',
     'Calculated Cover Day', 'Kesim_Cover_Basi', 'Kesim_Cover_Sonu', 'Final_Cover_Gun', 'Kesim_Adedi',
     'Gelecek_Teslimat_Sonrasi_Doluluk (%)',
     'Depo_Final_Palet_Toplami', 'Kesinti_Nedeni', 'Sayim_Bilgisi', 'Cut_Priority', 'Dokunulmazlik_Nedeni',
     'Layout_Tipi', 'Layout_Listesinde']
]

# Sayım kısıtı raporu
_df_sayim_rapor = pd.DataFrame(_sayim_rapor)
if not _df_sayim_rapor.empty:
    _sk_ozet = (df[df['Sayim_Kisiti'] == True].groupby('Location name')
                .agg(_satir=('Orijinal_Miktar', lambda x: int((x > 0).sum())), _miktar=('Orijinal_Miktar', 'sum')))
    _kisildi = _df_sayim_rapor['Durum'].str.startswith('KISILDI')
    _df_sayim_rapor['Kesilen Satır'] = np.where(_kisildi, _df_sayim_rapor['Depo'].map(_sk_ozet['_satir']), 0)
    _df_sayim_rapor['Kesilen Miktar'] = np.where(_kisildi, _df_sayim_rapor['Depo'].map(_sk_ozet['_miktar']), 0)
    _df_sayim_rapor = _df_sayim_rapor.sort_values(['Durum', 'Depo', 'Sayım Tarihi'])

# Ambient geçiş raporu
_df_ambient_gecis = df[df['Ambient_Gecis'] == True][
    ['Location name', 'Product code', 'Product name', 'Domain Type', 'Order batch size', 'Batch_Kaynagi',
     'hacim2', 'Orijinal_Miktar', 'Final_Miktar', 'Final_Hacim_Litre', 'Final_Palet',
     'Final_Cover_Gun', 'Cut_Priority', 'Kesinti_Nedeni']
].sort_values(['Location name', 'Product code'])

# Dikey özet hazırlıkları
_dikey_df = df[df['Dikey_Elleçleme_Su'] == True].copy() if 'Dikey_Elleçleme_Su' in df.columns else pd.DataFrame()
_df_dikey_ozet = pd.DataFrame()
_df_uyum = pd.DataFrame()
_df_dikey_kontrol = pd.DataFrame()

if not _dikey_df.empty:
    def _safe(v, d=0.0):
        try: return float(v) if not pd.isna(v) else d
        except: return d
    def _tanimli_mi(r):
        try: return not bool(r.get('Relex_Satiri_Yok', False))
        except: return True

    _ozet, _uyum_satirlari = [], []
    for _depo, _g in _dikey_df.groupby('Location name'):
        _layout = str(_g['Layout_Tipi'].iloc[0])
        _beklenen = _DIKEY_PALET_MAP.get(_layout, {})
        _mevcut = {str(r['Product code']).lower().strip(): r for _, r in _g.iterrows()}
        _tanimli_kodlar = {k for k, r in _mevcut.items() if _tanimli_mi(r)}
        _beklenen_kodlar = set(_beklenen.keys())
        _eksik = sorted(_beklenen_kodlar - _tanimli_kodlar)
        _fazla = sorted(_tanimli_kodlar - _beklenen_kodlar)

        _uyum_satirlari.append({
            'Depo': _depo, 'Layout': _layout, 'Beklenen SKU': len(_beklenen_kodlar),
            'Relex Tanimli SKU': len(_tanimli_kodlar), 'Eksik SKU Sayisi': len(_eksik), 'Fazla SKU Sayisi': len(_fazla),
            'Eksik SKU Kodlari': ', '.join(_eksik) if _eksik else '-', 'Fazla SKU Kodlari': ', '.join(_fazla) if _fazla else '-',
            'Durum': 'OK' if not _eksik and not _fazla else ' | '.join(([f'EKSIK ({len(_eksik)})'] if _eksik else []) + ([f'FAZLA ({len(_fazla)})'] if _fazla else [])),
        })

        _islenecek = [(k, _beklenen[k][0], _beklenen[k][1]) for k in _beklenen_kodlar]
        _islenecek += [(k, 'FAZLA', 'Layout Disi') for k in _fazla]

        for _pc, _pno, _ptyp in _islenecek:
            _r = _mevcut.get(_pc)
            _var = _r is not None
            _tanimli = _tanimli_mi(_r) if _var else False
            _p_kap = _safe(_r.get('palet', 0)) if _var else 0.0
            _p_kap = _p_kap if _p_kap > 0 else 0.0
            _net = _safe(_r.get('Net_Su_Stok', 0)) if _var else 0.0
            _orig = _safe(_r.get('Orijinal_Miktar', 0)) if _var else 0.0
            _final = _safe(_r.get('Final_Miktar', 0)) if _var else 0.0
            _fc = _safe(_r.get('Daily FC', 0)) if _var else 0.0
            if _fc <= 0 and _var: _fc = _safe(_r.get('water frc t', 0))
            _stok_pal = round(_net / _p_kap, 3) if _p_kap > 0 else 0.0
            _final_pay = round(_final / _p_kap * 100, 1) if _p_kap > 0 else 0.0
            def _cvr(stok, fc=_fc): return round(stok / fc, 1) if fc > 0 else '-'

            if not _var: _durum = 'SATIR YOK'
            elif _pno == 'FAZLA': _durum = 'FAZLA - Layout Disi'
            elif bool(_r.get('Layout_Sentetik', False)): _durum = 'Relex\'te Yok - Utilization\'dan Uretildi'
            elif not _tanimli: _durum = 'Relex Tanimsiz - Sadece Stok'
            else: _durum = 'OK'

            _ozet.append({
                'Depo': _depo, 'Layout': _layout, 'Palet No': f'Palet {_pno}' if _pno != 'FAZLA' else 'FAZLA', 'Palet Tipi': _ptyp,
                'Palet Iptal': ('EVET' if (_var and bool(_r.get('Dikey_Palet_Iptal', False))) else 'Hayir'),
                'Urun Adi': str(_r.get('Product name', '')) if _var else '(satir yok)', 'Product Code': _pc, 'Durum': _durum,
                'Relex Tanimli': 'Evet' if _tanimli else 'Hayir',
                'Satir Kaynagi': ('Water WH (uretildi)' if (_var and bool(_r.get('Layout_Sentetik', False))) else ('Relex' if _var else '-')),
                'OBS': _safe(_r.get('Order batch size', 0)) if _var else 0, 'Batch Kaynagi': str(_r.get('Batch_Kaynagi', '-')) if _var else '-',
                'Palet Kapasitesi': _p_kap, 'Cep Stok': _safe(_r.get('Warehouse Available Stock', 0)) if _var else 0,
                'Yoldaki Stok': _safe(_r.get('Transfer Remaining Stock (9 Days)', 0)) if _var else 0, 'LT Satis Tahmini': round(_safe(_r.get('Su_Lead_Time_Satis', 0)), 1) if _var else 0,
                'Net Stok': round(_net, 1), 'Net Stok (Palet)': _stok_pal, 'Palet Dolulugu (%)': round(_stok_pal * 100, 1), 'Gunluk Satis (FC)': round(_fc, 2),
                'Relex Onerisi': _orig, 'Cover (Mevcut)': _cvr(_net), 'Cover (Oneri Sonrasi)': _cvr(_net + _orig), 'Final Miktar': _final, 'Final Palet Payi (%)': _final_pay,
                'Fark (Final - Oneri)': _final - _orig, 'Siparis Sonrasi Stok': round(_net + _final, 1), 'Cover (Final)': _cvr(_net + _final),
                'End Balance DC': _safe(_r.get('End_Balance_DC_Urun', 0)) if _var else 0, 'Toplam Final (Tum Depolar)': _safe(_r.get('Toplam_Final_Tum_Depolar', 0)) if _var else 0,
                'Cut Priority': _safe(_r.get('Cut_Priority', 0)) if _var else 0, 'Kesinti Nedeni': str(_r.get('Kesinti_Nedeni', '')) if _var else '-',
            })
    _df_dikey_ozet = pd.DataFrame(_ozet).sort_values(['Depo', 'Palet No', 'Urun Adi'])
    _df_uyum = pd.DataFrame(_uyum_satirlari).sort_values(['Durum', 'Depo'], ascending=[False, True])

    _kontrol_satirlari = []
    for (_dep, _pno), _g in _df_dikey_ozet.groupby(['Depo', 'Palet No']):
        _tip = _g['Palet Tipi'].iloc[0]
        _toplam_pay = round(_g['Final Palet Payi (%)'].sum(), 1)
        _dagitima_giren = _g[_g['Relex Tanimli'] == 'Evet']
        _siparisli = _g[_g['Final Miktar'] > 0]
        _min_pay = round(_siparisli['Final Palet Payi (%)'].min(), 1) if not _siparisli.empty else 0.0
        _iptal = (_g['Palet Iptal'] == 'EVET').any()

        _uyarilar = []
        if _iptal: _uyarilar.append('TIR LIMITI - PALET IPTAL EDILDI')
        if (_g['Durum'] == 'SATIR YOK').any(): _uyarilar.append('SATIRI OLMAYAN SKU')
        if (_g['Durum'] == 'FAZLA - Layout Disi').any(): _uyarilar.append('LAYOUT DISI SKU')
        if (_g['Durum'] == 'Relex Tanimsiz - Sadece Stok').any(): _uyarilar.append('RELEX TANIMSIZ SKU (siparis yok)')
        if _g['Durum'].astype(str).str.contains('Utilization').any(): _uyarilar.append('SATIR URETILDI (Relex\'te yoktu)')
        if _toplam_pay > 100.5: _uyarilar.append('PALET TASTI')
        if str(_tip).startswith('Dikey') and _toplam_pay > 0.5 and not _iptal:
            if len(_siparisli) < len(_dagitima_giren): _uyarilar.append('DIKEY PALETTE SIPARISSIZ SKU')
            if _min_pay < 23.0: _uyarilar.append(f'MIN %25 IHLALI ({_min_pay}%)')
            if _toplam_pay < 95.0: _uyarilar.append('DIKEY PALET EKSIK DOLDU')
        if _g['Kesinti Nedeni'].astype(str).str.contains('DİKEY PALET BOZULDU').any(): _uyarilar.append('KISMI KESILDI (palet bozuldu)')

        _kontrol_satirlari.append({
            'Depo': _dep, 'Palet No': _pno, 'Palet Tipi': _tip, 'Beklenen SKU': len(_g),
            'Relex Tanimli SKU': len(_dagitima_giren), 'Siparis Verilen SKU': len(_siparisli), 'Palet Iptal': 'EVET' if _iptal else 'Hayir',
            'Toplam Palet Payi (%)': _toplam_pay, 'Min SKU Payi (%)': _min_pay,
            'Mevcut Stok Payi (%)': round(_g['Palet Dolulugu (%)'].sum(), 1), 'Uyari': ' | '.join(_uyarilar) if _uyarilar else 'OK',
        })
    _df_dikey_kontrol = pd.DataFrame(_kontrol_satirlari).sort_values(['Depo', 'Palet No'])

# Eksik Su raporu hazırlıkları
_df_eksik_su = pd.DataFrame()
_eks_ozet = pd.DataFrame()
if 'Relex_Satiri_Yok' in df.columns and (df['Relex_Satiri_Yok'] == True).any():
    _eks = df[df['Relex_Satiri_Yok'] == True].copy()
    def _sf(v, d=0.0):
        try: return float(v) if not pd.isna(v) else d
        except: return d
    _eks_satir = []
    for _, _r in _eks.iterrows():
        _p_kap = _sf(_r.get('palet', 0))
        _net = _sf(_r.get('Net_Su_Stok', 0))
        _fc = _sf(_r.get('Daily FC', 0))
        if _fc <= 0: _fc = _sf(_r.get('water frc t', 0))
        _stok_pal = round(_net / _p_kap, 3) if _p_kap > 0 else 0.0
        _lay = str(_r.get('Layout_Tipi', '-'))
        _lst = str(_r.get('Layout_Listesinde', '-'))

        if _lay == '-': _rol = 'Test disi depo - kapasite hesabi'
        else: _rol = 'BEKLENMEYEN - test deposunda eksik su satiri'

        _eks_satir.append({
            'Depo': _r.get('Location name', '-'), 'Layout': _lay, 'Palet No': str(_r.get('Dikey_Palet_No', '-')),
            'Urun Adi': str(_r.get('Product name', '')), 'Product Code': str(_r.get('Product code', '')),
            'Rol': _rol, 'Layout Durumu': _lst, 'Palet Kapasitesi': _p_kap, 'Cep Stok': _sf(_r.get('Warehouse Available Stock', 0)),
            'Yoldaki Stok': _sf(_r.get('Transfer Remaining Stock (9 Days)', 0)), 'LT Satis Tahmini': round(_sf(_r.get('Su_Lead_Time_Satis', 0)), 1),
            'Net Stok': round(_net, 1), 'Net Stok (Palet)': _stok_pal, 'Palet Dolulugu (%)': round(_stok_pal * 100, 1),
            'Kapladigi Palet': _sf(_r.get('Mevcut_Kaplanan_Su_Paleti', 0)), 'Gunluk Satis (FC)': round(_fc, 2),
            'Cover (Mevcut)': round(_net / _fc, 1) if _fc > 0 else '-', 'OBS': _sf(_r.get('Order batch size', 0)), 'Final Miktar': _sf(_r.get('Final_Miktar', 0)),
        })
    _df_eksik_su = pd.DataFrame(_eks_satir).sort_values(['Layout', 'Depo', 'Palet No', 'Urun Adi'])
    _eks_ozet = (_df_eksik_su.groupby(['Depo', 'Layout']).agg(Satir_Sayisi=('Product Code', 'count'), Toplam_Net_Stok=('Net Stok', 'sum'),
                 Kapladigi_Palet=('Kapladigi Palet', 'sum'), Beklenmeyen=('Rol', lambda x: int((x.str.startswith('BEKLENMEYEN')).sum())))
                 .reset_index().sort_values('Kapladigi_Palet', ascending=False))

# ==========================================
# 📁 ÇIKTI YAZIMI (yerel klasör — Drive'a kayıt yok)
# ==========================================
# Excel, parquet ve All PL sürücü (surucu.py) tarafından çalışma klasörünün out/ ve allpl/ altına yazılır.
# Eskiden burada Google Drive'a yükleme vardı; kaldırıldı.
__EXCEL_YAZ__(globals())

print("\n" + "="*40 + "\n--- GENEL RAPOR ÖZETİ ---\n" + "="*40)
print(f"Toplam Sevk Hacmi:       {round(df['Final_Hacim_Litre'].sum()):,} Litre")
print(f"Kesilen Toplam Hacim:    {round(df['Kesilen_Hacim_Litre'].sum()):,} Litre")
print(f"Toplam Sevk Paleti:      {round(df['Final_Palet'].sum(), 1):,} Palet")
_hacim_kesildi = df['Kesinti_Nedeni'].astype(str).str.endswith('Hacim Icin Kisildi')
print(f"Hacim Kesintisi:         {int(_hacim_kesildi.sum()):,} Satır")
print(f"Palet/Koli Kesintisi:    {len(df[(df['Fark (Kesilen Miktar)'] > 0) & ~_hacim_kesildi]):,} Satır")
_kesilen_satir = df[df['Kesim_Adedi'] > 0]
print(f"Cover Sirali Kesim:      {len(_kesilen_satir):,} Satır / {int(df['Kesim_Adedi'].sum()):,} batch kesimi")
_bozulan = df[df['Kesinti_Nedeni'].astype(str).str.contains('DİKEY PALET BOZULDU', na=False)]
print(f"Dikey Palet Bozulan:     {len(_bozulan):,} Satır ({_bozulan['Location name'].nunique()} depo)")
print(f"Sayım Kısıtı:            {int((df['Sayim_Kisiti'] & (df['Orijinal_Miktar'] > 0)).sum()):,} Satır ({df.loc[df['Sayim_Kisiti'], 'Location name'].nunique()} depo)")
print(f"Su→Ambient Geçiş:        {int(df['Ambient_Gecis'].sum()):,} Satır ({df.loc[df['Ambient_Gecis'], 'Location name'].nunique()} depo)")
print(f"Toplam Çalışma Süresi:   {round(time.time() - start_time, 2)} saniye")
print("="*40)