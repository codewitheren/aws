/**
 * Örnek veri. Backend bağlanana kadar tüm sonuç ekranları buradan beslenir.
 * Sabit rakamlar tasarımda verilen değerlerdir; `rng` ile üretilen seriler yalnızca
 * görsel örnektir (README'de "örnek / verilen veri" listesine bakın).
 */
import { slugify } from '../lib/slug';
import { rng } from '../lib/rng';
import type {
  AnomalyData, DepotDetail, DepotsData, MerkezOption, ResultsData, SampleContext, TopCutDepot, TrendData,
} from './types';
import type { TransferTypeId } from '../agent/types';

export const SAMPLE_CONTEXT: SampleContext = {
  merkez: 'Maltepe',
  transferType: 'amb',
  transferTypeLabel: 'Ambient & Su',
  dateLabel: '23.11.2026 Pazartesi',
  isoDate: '2026-11-23',
};

const N_DAYS = 30;
const DAY0 = new Date(2026, 9, 25);

function dayLabel(i: number): string {
  const d = new Date(DAY0.getFullYear(), DAY0.getMonth(), DAY0.getDate() + i);
  return String(d.getDate()).padStart(2, '0') + '.' + String(d.getMonth() + 1).padStart(2, '0');
}

const DAYS = Array.from({ length: N_DAYS }, (_, i) => dayLabel(i));

// ---- Koşu ekranı ----

function tip(id: TransferTypeId, ad: string, relexAt: string | null, lineCount: number | null, ranAt: string | null) {
  return { id, ad, relexAt, lineCount, ranAt };
}

export const MERKEZLER: MerkezOption[] = [
  { ad: 'Maltepe', tipler: [tip('amb', 'Ambient & Su', '06:10', 52872, null), tip('c4', '+4 (Soğuk)', '06:25', 31460, '07:02'), tip('ms', 'Meyve-Sebze', null, null, null)] },
  { ad: 'İzmir', tipler: [tip('amb', 'Ambient & Su', '06:12', 21340, null), tip('c4', '+4 (Soğuk)', '06:31', 12885, null), tip('ms', 'Meyve-Sebze', '05:48', 6120, '06:20')] },
  { ad: 'Adana', tipler: [tip('amb', 'Ambient & Su', '06:14', 9870, null), tip('c4', '+4 (Soğuk)', '06:33', 5410, null), tip('ms', 'Meyve-Sebze', '05:50', 2960, null)] },
  { ad: 'Arnavutköy', tipler: [tip('amb', 'Ambient & Su', '06:11', 48215, '06:55'), tip('c4', '+4 (Soğuk)', '06:27', 28730, null), tip('ms', 'Meyve-Sebze', '05:46', 14390, null)] },
  { ad: 'Ankara', tipler: [tip('amb', 'Ambient & Su', '06:13', 26480, null), tip('c4', '+4 (Soğuk)', '06:30', 14975, null), tip('ms', 'Meyve-Sebze', null, null, null)] },
  { ad: 'Diyarbakır', tipler: [tip('amb', 'Ambient & Su', '06:16', 4320, null), tip('c4', '+4 (Soğuk)', '06:35', 2180, null)], note: "Diyarbakır'da Meyve-Sebze transferi yok." },
];

// ---- Agent'ın koşu sırasında bulduğu aykırı PL önerileri (mock agent kullanır) ----

export interface SampleOutlier {
  findingKey: string;
  depotId: string;
  title: string;
  metric: 'oneri' | 'tahmin';
  currentValue: number;
  mean: number;
  median: number;
  found: string;
  proposal: string;
  impact: string;
}

export const SAMPLE_OUTLIERS: SampleOutlier[] = [
  {
    findingKey: 'goztepe:bulasik-sungeri-5li', depotId: 'goztepe', title: "Göztepe · Bulaşık süngeri 5'li",
    metric: 'oneri', currentValue: 100, mean: 14, median: 16,
    found: "Relex bu ürün için Göztepe'ye 100 adet öneriyor. Diğer G10 depolarda aynı ürünün önerisi ortalama 14, medyan 16. Bu değer medyanın yaklaşık 6 katı.",
    proposal: 'Öneriyi G10 medyanına çekmek: 100 → 16 (−84 adet).',
    impact: 'Göztepe toplam önerisi 25.605 → 25.521 adet.',
  },
  {
    findingKey: 'bostanci:kedi-mamasi-400g', depotId: 'bostanci', title: 'Bostancı · Kedi maması 400 g',
    metric: 'tahmin', currentValue: 86, mean: 11, median: 9,
    found: "Relex tahmini Bostancı'da 86. Diğer G10 depolarda aynı ürünün tahmini ortalama 11, medyan 9. Bu değer medyanın yaklaşık 10 katı.",
    proposal: 'Tahmini G10 medyanına çekip öneriyi buna göre yeniden hesaplamak: tahmin 86 → 9.',
    impact: 'Bu satırın önerisi düşer; depo toplamı buna göre güncellenir.',
  },
  {
    findingKey: 'acibadem:pirinc-1kg', depotId: 'acibadem', title: 'Acıbadem · Pirinç 1 kg',
    metric: 'oneri', currentValue: 120, mean: 19, median: 18,
    found: "Relex bu ürün için Acıbadem'e 120 adet öneriyor. Diğer G10 depolarda aynı ürünün önerisi ortalama 19, medyan 18. Bu değer medyanın yaklaşık 7 katı.",
    proposal: 'Öneriyi G10 medyanına çekmek: 120 → 18 (−102 adet).',
    impact: 'Acıbadem toplam önerisi 102 adet azalır.',
  },
];

// ---- Sonuçlar ----

export const RESULTS: ResultsData = {
  context: SAMPLE_CONTEXT,
  headline: 'Maltepe Ambient & Su koşusu hazır: 52.872 öneri satırı, 29.688 satır gönderiliyor, kısma oranı %44. 1 kritik, 3 uyarı var.',
  suggestedLines: 52872,
  sentLines: 29688,
  cpPct: 56.2,
  cutPct: 44.2,
  cutDelta: { vsYesterday: 1.8, vsLastWeekday: 3.1 },
  lineLimit: { used: 9412, limit: 10000 },
  anomalyTotal: 2032,
  alerts: [
    {
      level: 'kritik', title: '4 koşu dosyası günün All PL kaydında yok',
      scope: '+4 Maltepe · +4 Arnavutköy · MS Maltepe · MS Adana', evidence: '4 dosya var, 0 kayıt',
      action: 'Sevkiyattan önce All PL kaydını tamamlayın.', link: { route: '/kosu', label: 'Koşu ekranı →' },
    },
    {
      level: 'uyari', title: 'Göztepe %93 kısıldı, dolapta yer var', scope: 'Göztepe · kısıt: TIR limiti',
      evidence: 'TIR limiti 4 palet, öneri 41,8', action: 'TIR limitini gözden geçirin (G10 medyanı 12 palet).',
      link: { route: '/depolar/goztepe', label: 'Depo detayı →' },
    },
    {
      level: 'uyari', title: 'Kavacık %73 kısıldı, dolap dolu', scope: 'Kavacık · kısıt: dolap hacmi',
      evidence: "Tam gönderimde doluluk %144; son 24 sipariş gününün 24'ünde hacim kısması",
      action: 'Kronik: ek dolap ihtiyacını değerlendirin.', link: { route: '/depolar/kavacik', label: 'Depo detayı →' },
    },
    {
      level: 'uyari', title: 'Relex önerisinde 2.032 şüpheli satır', scope: 'Tüm depolar · Relex',
      evidence: '682 fazla stok şüphesi · 942 "tahmin 0 ama öneri var" · 408 "öneri 14 günlük satışı aşıyor"',
      action: 'Anomali listesini indirip Relex ekibine iletin.', link: { route: '/sonuclar/anomaliler', label: 'Anomalileri aç →' },
    },
    {
      level: 'bilgi', title: "Buyaka'da demirbaş poşet 1.000 → 0", scope: 'Buyaka · depo sayımda',
      evidence: 'Öneri 1.000, gönderilen 0', action: 'Beklenen davranış; izleyin.', link: { route: '/depolar', label: 'Depolarda aç →' },
    },
  ],
  chatSuggestions: ["Göztepe'de neden bu kadar kıstık?", 'Kavacık neden kronik?', 'Kritik uyarıyı açıkla'],
};

// ---- Relex anomalileri ----

function anomalyInliers(): number[] {
  const r = rng(448);
  const v: number[] = [];
  for (let i = 0; i < 70; i++) v.push(68 * Math.exp((r() - 0.5) * 1.1));
  return v.sort((a, b) => a - b);
}

export const ANOMALIES: AnomalyData = {
  context: SAMPLE_CONTEXT,
  total: 2032,
  categories: [
    { label: 'Fazla stok şüphesi', count: 682, description: 'Stok + açık + öneri, ürünün depolar arası üst sınırını aşıyor.' },
    { label: 'Tahmin 0 ama öneri var', count: 942, description: 'Satış tahmini sıfır olan ürüne miktar önerilmiş.' },
    { label: 'Öneri 14 günlük satışı aşıyor', count: 408, description: 'Tek seferde iki haftadan fazla stok isteniyor.' },
  ],
  product: 'Coca-Cola Zero',
  median: 68,
  upperBound: 170,
  inliers: anomalyInliers(),
  outliers: [
    { depotId: 'moda', ad: 'Moda', value: 196, note: 'Üst sınırın üzerinde; izleyin.' },
    { depotId: 'kozyatagi', ad: 'Kozyatağı', value: 212, note: 'Üst sınırın üzerinde; GB depo, izleyin.' },
    { depotId: 'suadiyebuyuk', ad: 'SuadiyeBüyük', value: 448, note: 'Fazla stok şüphesi. Öneriyi Relex ekibiyle doğrulayın.' },
  ],
};

// ---- Trend ----

function buildTrend(): TrendData {
  // Tasarımdaki sırayla tek bir üreteçten çekilir; sıra değişirse seriler de değişir.
  const r = rng(2311);
  const ratio: number[] = [];
  for (let i = 0; i < N_DAYS; i++) ratio.push(41 + Math.sin(i / 3.1) * 2.6 + (r() - 0.5) * 4);
  ratio[6] = 49.3; ratio[13] = 33.8; ratio[20] = 51.6; ratio[28] = 42.4; ratio[29] = 44.2;

  const reasons = ratio.map((p) => {
    const backlog = 3 + r() * 4;
    const limit = 4 + r() * 5;
    return { kap: p - backlog - limit, backlog, limit, yok: 100 - p };
  });

  const base: [string, number, number][] = [
    ['Göztepe', 91, 4], ['Kavacık', 72, 5], ['Ortaçeşme', 58, 14], ['Kozyatağı', 47, 16], ['SuadiyeBüyük', 44, 12],
    ['Buyaka', 38, 18], ['Ataşehir', 36, 14], ['Bostancı', 33, 16], ['Acıbadem', 30, 14], ['Çekmeköy', 27, 16],
    ['Kartal', 22, 14], ['Pendik', 18, 12],
  ];
  const today: Record<string, number> = { 'Göztepe': 93, 'Kavacık': 73 };
  const heat = base.map(([ad, mid, spread]) => {
    const values: number[] = [];
    for (let i = 0; i < N_DAYS; i++) {
      let p = Math.max(2, Math.min(98, mid + (r() - 0.5) * 2 * spread));
      if (i === N_DAYS - 1 && today[ad] !== undefined) p = today[ad];
      values.push(p);
    }
    return { depotId: slugify(ad), ad, values };
  });

  const top: [string, number, TopCutDepot['reason']][] = [
    ['Göztepe', 93, 'kap'], ['Kavacık', 73, 'kap'], ['Ortaçeşme', 68, 'kap'], ['Kozyatağı', 64, 'backlog'], ['Moda', 61, 'kap'],
    ['Fenerbahçe', 59, 'kap'], ['Altunizade', 57, 'limit'], ['SuadiyeBüyük', 55, 'kap'], ['Ümraniye', 54, 'backlog'], ['Beykoz', 52, 'kap'],
    ['Çengelköy', 51, 'kap'], ['Maltepe Sahil', 50, 'limit'], ['Ataşehir', 49, 'kap'], ['Küçükyalı', 48, 'backlog'], ['Bostancı', 47, 'kap'],
  ];

  return {
    context: SAMPLE_CONTEXT,
    rangeLabel: 'son 30 gün (25.10 – 23.11.2026)',
    days: DAYS,
    cutRatio: ratio,
    band: { low: 36, high: 46 },
    reasons,
    heat,
    topCut: top.map(([ad, pct, reason]) => ({ depotId: slugify(ad), ad, pct, reason })),
    limitNote: 'Created satır / limit · Ambient 10.000 · +4 6.900 · Meyve-Sebze 10.000',
    limits: [
      { merkez: 'Maltepe', amb: 94, c4: 88, ms: 71 },
      { merkez: 'İzmir', amb: 76, c4: 69, ms: 58 },
      { merkez: 'Adana', amb: 52, c4: 47, ms: 39 },
      { merkez: 'Arnavutköy', amb: 91, c4: 97, ms: 74 },
      { merkez: 'Ankara', amb: 81, c4: 72, ms: 55 },
      { merkez: 'Diyarbakır', amb: 34, c4: 29, ms: null },
    ],
  };
}

export const TREND: TrendData = buildTrend();

// ---- Depolar ----

function scatterPoints(): [number, number][] {
  const r = rng(513);
  const pts: [number, number][] = [];
  const add = (n: number, d0: number, d1: number, k0: number, k1: number) => {
    for (let i = 0; i < n; i++) {
      const fill = d0 + r() * (d1 - d0);
      const cut = k0 + r() * (k1 - k0);
      pts.push([fill, cut]);
    }
  };
  add(78, 38, 96, 4, 44); add(16, 100, 124, 18, 48); add(20, 101, 152, 52, 86); add(7, 42, 92, 54, 82);
  return pts;
}

export const DEPOTS: DepotsData = {
  context: SAMPLE_CONTEXT,
  points: scatterPoints(),
  highlights: [
    { depotId: 'goztepe', ad: 'Göztepe', fillPct: 84.6, cutPct: 93 },
    { depotId: 'kavacik', ad: 'Kavacık', fillPct: 144, cutPct: 73 },
  ],
  rows: [
    { depotId: 'goztepe', ad: 'Göztepe', level: 'uyari', cutPct: 93, reason: 'TIR limiti (4 palet), dolapta yer var' },
    { depotId: 'kavacik', ad: 'Kavacık', level: 'uyari', cutPct: 73, reason: 'Dolap hacmi, tam gönderimde doluluk %144' },
    { depotId: 'ortacesme', ad: 'Ortaçeşme', level: null, cutPct: 68, reason: 'Depo kapasitesi' },
    { depotId: 'kozyatagi', ad: 'Kozyatağı', level: null, cutPct: 64, reason: 'Backlog' },
    { depotId: 'moda', ad: 'Moda', level: null, cutPct: 61, reason: 'Depo kapasitesi' },
    { depotId: 'fenerbahce', ad: 'Fenerbahçe', level: null, cutPct: 59, reason: 'Depo kapasitesi' },
    { depotId: 'altunizade', ad: 'Altunizade', level: null, cutPct: 57, reason: 'Merkez satır limiti' },
    { depotId: 'buyaka', ad: 'Buyaka', level: 'bilgi', cutPct: null, reason: 'Sayım: demirbaş poşet 1.000 → 0, beklenen davranış' },
  ],
  featuredDepotId: 'kavacik',
};

// ---- Depo detayları ----

function goztepeTrend(): { depot: number[]; merkez: number[] } {
  const r = rng(93);
  const series = (f: (i: number) => number) => Array.from({ length: N_DAYS }, (_, i) => f(i));
  const depot = series((i) => (i === N_DAYS - 1 ? 93 : 90 + (r() - 0.5) * 9));
  const merkez = series((i) => (i === N_DAYS - 1 ? 44.2 : 41 + Math.sin(i / 3.1) * 2.6 + (r() - 0.5) * 3));
  return { depot, merkez };
}

const GOZTEPE: DepotDetail = {
  depotId: 'goztepe',
  ad: 'Göztepe',
  group: 'G10',
  level: 'uyari',
  levelNote: null,
  context: SAMPLE_CONTEXT,
  cutPct: 93,
  explanation: {
    headline: "Göztepe'de önerinin %93'ü gönderilmiyor. Kısıt dolap değil, TIR limiti.",
    body: 'Relex 25.605 adet istiyor; bu 41,8 palet eder. Deponun TIR limiti 4 palet olduğu için {kesim:palet} adet palet limitinden, {kesim:su} adet su alanından kesildi ve {gonderilen} adet gönderiliyor. Dolap şu an %28,6 dolu; her şey gitseydi %84,6 olurdu. A sınıfı ürünlerden 6.620 adet kesildi.',
    recommendation: 'TIR limitini G10 medyanı olan 12 palete yaklaştırın. Buffer ya da ek dolap bu depoda sonucu değiştirmez.',
  },
  waterfall: {
    relexTotal: 25605,
    cuts: [
      { key: 'palet', label: 'Palet limiti', legend: 'Depo kapasitesi: palet limiti', source: 'palet limitinden', amount: 21328, tone: 'kap' },
      { key: 'su', label: 'Su alanı', legend: 'Depo kapasitesi: su alanı', source: 'su alanından', amount: 2472, tone: 'kap2' },
    ],
    note: 'Backlog ve merkez satır limiti kaynaklı kesinti yok.',
  },
  finding: {
    findingKey: 'goztepe:bulasik-sungeri-5li',
    merkez: 'Maltepe',
    transferType: 'amb',
    product: "Bulaşık süngeri 5'li",
    group: 'G10',
    relexValue: 100,
    mean: 14,
    median: 16,
    found: "Relex bu ürün için Göztepe'ye 100 adet öneriyordu. Diğer G10 depolarda aynı ürünün önerisi ortalama 14, medyan 16; değer medyanın yaklaşık 6 katı.",
    proposed: 'Öneriyi G10 medyanına çekmek: 100 → 16 (−84 adet). Yalnızca bu koşuda, kesim motorundan önce; Relex kaydına dokunmadan.',
    absorbedByCut: 'palet',
  },
  tir: {
    bars: [
      { label: 'Öneri', value: 41.8, unit: 'palet', barPct: 100, tone: 'yok' },
      { label: 'G10 medyanı', value: 12, unit: 'palet', barPct: 28.7, tone: 'yok' },
      { label: 'Göztepe TIR limiti', value: 4, unit: 'palet', barPct: 9.6, tone: 'kap' },
    ],
    note: 'Backlog: 0. Limit, benzer depoların üçte biri.',
  },
  fill: {
    bars: [
      { label: 'Şu an (teslimat sonrası)', value: 28.6, unit: 'yuzde', barPct: 28.6, tone: 'brand' },
      { label: 'Her şey gitseydi', value: 84.6, unit: 'yuzde', barPct: 84.6, tone: 'brand' },
    ],
    note: "Tam gönderimde bile dolap %100'ün altında kalır.",
  },
  metrics: null,
  chronic: null,
  aClassCut: 6620,
  topProducts: [
    { product: 'Su 5 L', cls: 'A', suggested: 1480, sent: 0, reason: 'Su alanı' },
    { product: "Su 1,5 L 6'lı", cls: 'A', suggested: 992, sent: 0, reason: 'Su alanı' },
    { product: "Kağıt havlu 12'li", cls: 'A', suggested: 640, sent: 24, reason: 'Palet limiti' },
    { product: "Tuvalet kağıdı 32'li", cls: 'A', suggested: 588, sent: 36, reason: 'Palet limiti' },
    { product: 'Gazlı içecek 1 L', cls: 'B', suggested: 510, sent: 48, reason: 'Palet limiti' },
    { product: 'Ayçiçek yağı 5 L', cls: 'A', suggested: 436, sent: 12, reason: 'Palet limiti' },
  ],
  trend: { ...goztepeTrend(), days: DAYS },
  levers: [
    { lever: 'TIR limiti', effect: '4 → 12 palet: önerinin yaklaşık %29\'u gider (bugün %7).', assessment: 'Asıl kısıt bu. Dolapta yer var, backlog 0.', result: { kind: 'chip', tone: 'iyi', label: 'Önerilir' } },
    { lever: 'Buffer', effect: 'Etkisiz.', assessment: 'Dolap %28,6 dolu; hacim kısıtına takılmıyor.', result: { kind: 'chip', tone: 'notr', label: 'Gerekmez' } },
    { lever: 'Sharing', effect: 'Bu koşuyu etkilemez; +4 dolabı için geçerli.', assessment: '+4\'te Other %117, MS %60: pay 0,77/0,23 → 0,84/0,16 önerisi ayrı.', result: { kind: 'text', label: 'Ayrı değerlendirilir' } },
    { lever: 'Case picking', effect: 'Günde 153,7 satır kazancı, 3.260 L ek stok.', assessment: 'Doluluk %72,8 → %81,2. Haftalık öneride.', result: { kind: 'text', label: 'Ayrı değerlendirilir' } },
    { lever: 'Ek dolap', effect: 'Etkisiz.', assessment: 'Tam gönderimde doluluk %84,6; dolap yetiyor.', result: { kind: 'chip', tone: 'notr', label: 'Gerekmez' } },
  ],
};

/** Kavacık: yalnızca Depolar ekranında verilen rakamlardan kurulur; verisi olmayan bölümler boştur. */
const KAVACIK: DepotDetail = {
  depotId: 'kavacik',
  ad: 'Kavacık',
  group: null,
  level: 'uyari',
  levelNote: 'Kronik hacim kısması',
  context: SAMPLE_CONTEXT,
  cutPct: 73,
  explanation: {
    headline: "Kavacık'ta önerinin %73'ü gönderilmiyor. Kısıt dolap hacmi.",
    body: "Relex 15.753 adet istiyor; {kesim:hacim} adet hacimden, {kesim:su} adet su alanından, {kesim:palet} adet palet limitinden kesildi ve {gonderilen} adet gönderiliyor. Ortalama doluluk %128; her şey gitseydi %144 olurdu. Son 24 sipariş gününün 24'ünde hacim kısması var.",
    recommendation: 'Buffer zaten üst sınırda (1,10). Kalan kaldıraç ek dolap: ek dolap ihtiyacını değerlendirin.',
  },
  waterfall: {
    relexTotal: 15753,
    cuts: [
      { key: 'hacim', label: 'Hacim', legend: 'Depo kapasitesi: hacim', source: 'hacimden', amount: 9089, tone: 'kap' },
      { key: 'su', label: 'Su alanı', legend: 'Depo kapasitesi: su alanı', source: 'su alanından', amount: 1636, tone: 'kap2' },
      { key: 'palet', label: 'Palet limiti', legend: 'Depo kapasitesi: palet limiti', source: 'palet limitinden', amount: 838, tone: 'kap3' },
    ],
    note: '',
  },
  finding: null,
  tir: null,
  fill: null,
  metrics: {
    title: 'Doluluk ve oda kullanımı',
    items: [
      { label: 'Ortalama doluluk', value: '%128' },
      { label: 'Tam gönderimde doluluk', value: '%144' },
      { label: 'Buffer', value: '1,10' },
      { label: 'ETB odası', value: '%124' },
      { label: '+4 odası Other', value: '%78' },
      { label: '+4 odası MS', value: '%41' },
    ],
    note: 'Buffer zaten üst sınırda (%110). Kalan kaldıraç ek dolap.',
  },
  chronic: { days: 24, of: 24 },
  aClassCut: null,
  topProducts: null,
  trend: null,
  levers: [
    { lever: 'Buffer', effect: 'Zaten üst sınırda (1,10).', assessment: 'Artırma payı yok.', result: { kind: 'chip', tone: 'notr', label: 'Üst sınırda' } },
    { lever: 'Ek dolap', effect: 'Kalan kaldıraç.', assessment: "Tam gönderimde doluluk %144; son 24 sipariş gününün 24'ünde hacim kısması.", result: { kind: 'chip', tone: 'bilgi', label: 'Değerlendirin' } },
  ],
};

export const DEPOT_DETAILS: Record<string, DepotDetail> = { goztepe: GOZTEPE, kavacik: KAVACIK };

/** Örnek verinin bilinen tüm depo adları (detay verisi olmasa da adı gösterebilmek için). */
export const KNOWN_DEPOTS: Record<string, string> = Object.fromEntries(
  [
    ...DEPOTS.rows.map((r) => r.ad),
    ...TREND.heat.map((r) => r.ad),
    ...TREND.topCut.map((r) => r.ad),
    ...ANOMALIES.outliers.map((r) => r.ad),
  ].map((ad) => [slugify(ad), ad]),
);
