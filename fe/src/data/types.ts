import type { TransferTypeId } from '../agent/types';

export type AlertLevel = 'kritik' | 'uyari' | 'bilgi';
/** Sabit kesinti nedeni renkleri; her grafikte aynıdır. */
export type CutReason = 'kap' | 'backlog' | 'limit' | 'yok';
/** Depo kapasitesi alt kırılımları için turuncu tonları. */
export type CutTone = 'kap' | 'kap2' | 'kap3';

/** Örnek sonuç verisinin ait olduğu optimizasyon. */
export interface SampleContext {
  merkez: string;
  transferType: TransferTypeId;
  transferTypeLabel: string;
  /** "23.11.2026 Pazartesi" */
  dateLabel: string;
  isoDate: string;
}

// ---- Optimizasyon ekranı ----

export interface TransferTypeOption {
  id: TransferTypeId;
  ad: string;
  /** Forecast girdisinin geldiği saat; gelmediyse null (tip seçilemez). */
  relexAt: string | null;
  lineCount: number | null;
  /** Saat bilinmiyorsa gösterilecek açıklama; varsa tip seçilebilir. */
  relexNote?: string;
  /** Bugün daha önce çalıştırıldıysa saati. */
  ranAt: string | null;
}

export interface MerkezOption {
  ad: string;
  tipler: TransferTypeOption[];
  note?: string;
}

// ---- Sonuçlar ----

export interface ResultAlert {
  level: AlertLevel;
  title: string;
  scope: string;
  evidence: string;
  action: string;
  link: { route: string; label: string };
}

export interface ResultsData {
  context: SampleContext;
  headline: string;
  suggestedLines: number;
  sentLines: number;
  cpPct: number;
  cutPct: number;
  /** Geçmiş optimizasyon verisi yoksa null. */
  cutDelta: { vsYesterday: number; vsLastWeekday: number } | null;
  lineLimit: { used: number; limit: number } | null;
  alerts: ResultAlert[];
  anomalyTotal: number;
  chatSuggestions: string[];
}

// ---- Forecast anomalileri ----

export interface AnomalyCategory {
  label: string;
  count: number;
  description: string;
}

export interface AnomalyOutlier {
  depotId: string;
  ad: string;
  value: number;
  note: string;
}

/** Motorun öneri kontrol kartı (canlı optimizasyon). */
export interface AnomalyCard {
  title: string;
  subtitle: string;
  columns: string[];
  rows: (string | number | null)[][];
}

export interface AnomalyData {
  context: SampleContext;
  total: number;
  categories: AnomalyCategory[];
  /** Canlı optimizasyonda motorun kontrol tabloları; varsa tek ürün grafiği yerine gösterilir. */
  cards?: AnomalyCard[];
  product: string;
  median: number;
  upperBound: number;
  /** Sınır içindeki depoların değerleri, küçükten büyüğe (örnek seri). */
  inliers: number[];
  /** Üst sınırı aşan depolar, küçükten büyüğe. */
  outliers: AnomalyOutlier[];
}

// ---- Trend ----

export interface DayReasons {
  kap: number;
  backlog: number;
  limit: number;
  yok: number;
}

export interface HeatRow {
  depotId: string;
  ad: string;
  values: number[];
}

export interface TopCutDepot {
  depotId: string;
  ad: string;
  pct: number;
  reason: Exclude<CutReason, 'yok'>;
}

export interface LimitUsageRow {
  merkez: string;
  amb: number | null;
  c4: number | null;
  ms: number | null;
}

export interface TrendHistory {
  /** "25.10" biçiminde 30 gün. */
  days: string[];
  cutRatio: number[];
  band: { low: number; high: number };
  reasons: DayReasons[];
  heat: HeatRow[];
}

export interface TrendData {
  context: SampleContext;
  rangeLabel: string;
  /** Geçmiş optimizasyon arşivi yoksa null; ekran yalnızca bugünü gösterir. */
  history: TrendHistory | null;
  /** Bugünkü optimizasyonun kesinti nedenleri (kesilen miktarın payı). */
  todayReasons?: { label: string; pct: number; reason: CutReason }[];
  topCut: TopCutDepot[];
  limitNote: string;
  limits: LimitUsageRow[];
}

// ---- Depolar ----

export interface ScatterHighlight {
  depotId: string;
  ad: string;
  fillPct: number;
  cutPct: number;
}

export interface DepotListRow {
  depotId: string;
  ad: string;
  level: AlertLevel | null;
  cutPct: number | null;
  reason: string;
}

export interface DepotsData {
  context: SampleContext;
  /** [tam gönderimde doluluk %, kısma %] örnek noktalar. */
  points: [number, number][];
  highlights: ScatterHighlight[];
  rows: DepotListRow[];
  /** Sağdaki özet kartında gösterilen depo. */
  featuredDepotId: string;
  /** Sol üst bölgenin adı: dolap boşken kısmanın kaynağı (Ambient'te TIR/palet). */
  constraintLabel?: string;
}

// ---- Depo detayı ----

export interface WaterfallCut {
  key: string;
  label: string;
  legend: string;
  /** Cümle içinde kullanım, ör. "palet limitinden". */
  source: string;
  amount: number;
  tone: CutTone;
}

export interface OutlierFinding {
  findingKey: string;
  merkez: string;
  transferType: TransferTypeId;
  product: string;
  group: string;
  relexValue: number;
  mean: number;
  median: number;
  found: string;
  proposed: string;
  /** Düzeltmenin düştüğü kesim kalemi (WaterfallCut.key). */
  absorbedByCut: string;
}

export interface MetricBar {
  label: string;
  value: number;
  unit: 'palet' | 'yuzde';
  /** Çubuğun %100 genişliğe göre oranı (0–100). */
  barPct: number;
  tone: 'yok' | 'kap' | 'brand';
}

export interface LeverRow {
  lever: string;
  effect: string;
  assessment: string;
  result: { kind: 'chip'; tone: 'iyi' | 'notr' | 'bilgi'; label: string } | { kind: 'text'; label: string };
}

export interface TopCutProduct {
  product: string;
  cls: string;
  suggested: number;
  sent: number;
  reason: string;
}

export interface DepotDetail {
  depotId: string;
  ad: string;
  group: string | null;
  level: AlertLevel;
  levelNote: string | null;
  context: SampleContext;
  cutPct: number;
  explanation: {
    headline: string;
    /** `{kesim:<key>}` yer tutucuları güncel kesim miktarıyla doldurulur. */
    body: string;
    recommendation: string;
  };
  waterfall: { relexTotal: number; cuts: WaterfallCut[]; note: string };
  finding: OutlierFinding | null;
  tir: { bars: MetricBar[]; note: string } | null;
  fill: { bars: MetricBar[]; note: string } | null;
  metrics: { title: string; items: { label: string; value: string }[]; note: string } | null;
  chronic: { days: number; of: number } | null;
  aClassCut: number | null;
  topProducts: TopCutProduct[] | null;
  trend: { depot: number[]; merkez: number[]; days: string[] } | null;
  levers: LeverRow[] | null;
  /** Motorun hesap defteri: limit, mevcut, kesilen adımları. */
  ledger?: { section: string; rows: { op: string; label: string; note: string; value: string }[] }[];
}
