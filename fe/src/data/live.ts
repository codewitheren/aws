/**
 * Canlı koşu verisini ekran tiplerine çevirir. Kaynak: backend `status` özeti, `view` (depo tablosu,
 * kesinti nedenleri, öneri kontrol kartları, tam gönderim doluluğu) ve `depot` (tek depo kanıtı).
 * Geçmiş koşu arşivi olmadığı için trend, düne göre fark ve kaldıraçlar boş bırakılır; örnek rakam gösterilmez.
 */
import { fetchDepot, fetchView, liveRun, restored, TYPE_LABEL, type LiveRun } from '../agent/agentcore';
import { formatDateWithWeekday, forecastName as fx, nf } from '../lib/format';
import { paths } from '../router/router';
import type {
  AlertLevel, AnomalyData, CutReason, CutTone, DepotDetail, DepotsData, MerkezOption, MetricBar, ResultsData,
  SampleContext, TopCutDepot, TrendData,
} from './types';

type Cell = string | number | null;
interface Table { kolonlar: string[]; satirlar: Cell[][] }
interface View {
  tablo: Table;
  nedenler: { ad: string; depo: number; kes: number; pay: number }[];
  kartlar: { baslik: string; alt?: string; ozet?: string; tablo: Table }[];
  sayi: number;
  doluluk: Record<string, number>;
}
interface DepotEntry {
  depo: string;
  rozetler?: { metin: string; tur?: string }[];
  defter?: ({ bolum: string } | { op?: string; ad: string; not?: string; deger: Cell; sinif?: string })[];
  doluluk?: { ad: string; birim: string; doluAd: string; dolu: number | null; fin: number | null; kes: number | null; tavan: number | null }[];
  kpi?: [string, Cell, string, boolean?][];
  nedenler?: { ad: string; kes: number }[];
  urunler?: { urun: string; oneri: number; final: number; kesilen: number; neden: string }[];
}

const NO_RUN = 'Henüz tamamlanmış bir koşu yok. Koşu ekranında merkez ve transfer tipini seçip Hesapla\'ya basın.';

async function requireRun(): Promise<LiveRun> {
  await restored();
  const run = liveRun();
  if (!run) throw new Error(NO_RUN);
  return run;
}

function contextOf(run: LiveRun): SampleContext {
  return {
    merkez: run.summary?.center ?? run.merkez, transferType: run.transferType, transferTypeLabel: TYPE_LABEL[run.transferType],
    dateLabel: formatDateWithWeekday(new Date(run.runDate + 'T12:00:00')), isoDate: run.runDate,
  };
}

/** Motorun neden etiketini dört sabit renk grubundan birine eşler. */
export function reasonGroup(label: string): CutReason {
  const t = label.toLocaleLowerCase('tr-TR');
  if (!t) return 'yok';
  if (t.includes('backlog')) return 'backlog';
  if (t.includes('satır limiti') || t.includes('koli limiti')) return 'limit';
  return 'kap';
}

let viewCache: { session: string; view: Promise<View> } | null = null;
function view(run: LiveRun): Promise<View> {
  if (viewCache?.session !== run.session) {
    const p = fetchView<View>();
    viewCache = { session: run.session, view: p };
    p.catch(() => { viewCache = null; });
  }
  return viewCache.view;
}

interface DepotRow { ad: string; tip: string | null; oneri: number; final: number; kesilen: number; pct: number; neden: string }
function depotRows(v: View): DepotRow[] {
  const c = v.tablo.kolonlar;
  const at = (r: Cell[], name: string) => r[c.indexOf(name)];
  return v.tablo.satirlar.map((r) => ({
    ad: String(at(r, 'Depo')), tip: c.includes('Tip') ? (at(r, 'Tip') as string | null) : null,
    oneri: Number(at(r, 'Öneri') ?? 0), final: Number(at(r, 'Final') ?? 0), kesilen: Number(at(r, 'Kesilen') ?? 0),
    pct: Number(at(r, 'Kesinti %') ?? 0), neden: String(at(r, 'Ana neden') ?? ''),
  }));
}

const LEVEL: Record<string, AlertLevel> = { hata: 'kritik', uyari: 'uyari', bilgi: 'bilgi' };

export const MERKEZLER: MerkezOption[] = ['Maltepe', 'İzmir', 'Adana', 'Arnavutköy', 'Ankara', 'Diyarbakır'].map((ad) => ({
  ad,
  tipler: (['amb', 'c4', 'ms'] as const)
    .filter((id) => !(ad === 'Diyarbakır' && id === 'ms'))
    .map((id) => ({ id, ad: TYPE_LABEL[id], relexAt: null, relexNote: 'Koşuda Google Sheet\'ten okunur', lineCount: null, ranAt: null })),
  note: ad === 'Diyarbakır' ? "Diyarbakır'da Meyve-Sebze transferi yok." : undefined,
}));

export async function getResults(): Promise<ResultsData> {
  const run = await requireRun();
  const s = run.summary!;
  const v = await view(run);
  const line = s.limits.find((l) => l.birim === 'satır');
  const top = depotRows(v).filter((r) => r.oneri > 0).sort((a, b) => b.pct - a.pct)[0];
  return {
    context: contextOf(run),
    headline: `${s.center} ${TYPE_LABEL[run.transferType]} koşusu hazır: ${nf(s.suggested)} öneri satırı, ${nf(s.sent)} satır gönderiliyor.`
      + (s.cut.kg !== undefined ? ` Dökmede (kg) kısma %${nf(s.cut.kg, 1)}.` : ''),
    suggestedLines: s.suggested,
    sentLines: s.sent,
    cpPct: s.cp ?? 0,
    cutPct: s.cut.adet ?? Object.values(s.cut)[0] ?? 0,
    cutDelta: null,
    lineLimit: line ? { used: line.deger, limit: line.limit } : null,
    alerts: s.alerts.map((a) => ({
      level: LEVEL[a.level] ?? 'bilgi', title: fx(a.name), scope: `${s.center} · ${TYPE_LABEL[run.transferType]}`,
      evidence: fx(a.evidence), action: a.level === 'hata' ? 'Sevkiyattan önce kontrol edin' : a.level === 'uyari' ? 'Bugün bakın' : 'İzleyin',
      link: { route: paths.anomaliler, label: 'Kontroller →' },
    })),
    anomalyTotal: v.sayi,
    chatSuggestions: [
      ...(top ? [`${top.ad} neden bu kadar kısıldı?`] : []),
      'Kritik uyarıları açıkla',
      'En büyük kesinti nedeni ne?',
    ],
  };
}

export async function getAnomalies(): Promise<AnomalyData> {
  const run = await requireRun();
  const v = await view(run);
  const reviewed = run.findings.map((f) => [
    f.depot, f.product, f.domain, f.current, f.median, f.proposed,
    run.changes[String(f.row)] !== undefined ? `Koşuda ${nf(run.changes[String(f.row)])} olarak uygulandı` : 'Olduğu gibi bırakıldı',
  ]);
  const cards = [
    ...(reviewed.length ? [{
      title: 'Aykırı PL önerileri (agent incelemesi)',
      subtitle: 'Aynı ürün, aynı depo tipinde IQR üst sınırını aşan öneriler ve koşudaki kararınız.',
      columns: ['Depo', 'Ürün', 'Depo tipi', 'Öneri', 'Medyan', 'Agent önerisi', 'Koşu durumu'],
      rows: reviewed,
    }] : []),
    ...v.kartlar.map((k) => ({ title: fx(k.baslik), subtitle: fx(k.alt ?? ''), columns: k.tablo.kolonlar.map(fx), rows: k.tablo.satirlar })),
  ];
  return {
    context: contextOf(run),
    total: v.sayi,
    categories: cards.map((c) => ({ label: c.title, count: c.rows.length, description: c.subtitle })),
    cards,
    product: '', median: 0, upperBound: 0, inliers: [], outliers: [],
  };
}

export async function getTrend(): Promise<TrendData> {
  const run = await requireRun();
  const s = run.summary!;
  const v = await view(run);
  const topCut: TopCutDepot[] = depotRows(v).filter((r) => r.kesilen > 0).sort((a, b) => b.pct - a.pct).slice(0, 15)
    .map((r) => ({ depotId: r.ad, ad: r.ad, pct: r.pct, reason: reasonGroup(r.neden) as TopCutDepot['reason'] }));
  const line = s.limits.find((l) => l.birim === 'satır');
  const usage = line ? Math.round((line.deger / line.limit) * 100) : null;
  return {
    context: contextOf(run),
    rangeLabel: `bugünkü koşu (${contextOf(run).dateLabel})`,
    history: null,
    todayReasons: v.nedenler.map((n) => ({ label: fx(n.ad), pct: n.pay, reason: reasonGroup(n.ad) })),
    topCut,
    limitNote: s.limits.map((l) => `${l.ad}: ${nf(l.deger)} / ${nf(l.limit)} ${l.birim}`).join(' · ') + ' · diğer merkez ve tipler için o koşuyu çalıştırın',
    limits: [{ merkez: run.merkez, amb: null, c4: null, ms: null, [run.transferType]: usage }],
  };
}

export async function getDepots(): Promise<DepotsData> {
  const run = await requireRun();
  const v = await view(run);
  const rows = depotRows(v).filter((r) => r.oneri > 0).sort((a, b) => b.pct - a.pct);
  const withFill = rows.filter((r) => v.doluluk[r.ad] !== undefined);
  return {
    context: contextOf(run),
    points: withFill.map((r) => [v.doluluk[r.ad], r.pct]),
    highlights: withFill.slice(0, 3).map((r) => ({ depotId: r.ad, ad: r.ad, fillPct: v.doluluk[r.ad], cutPct: r.pct })),
    rows: rows.map((r) => ({ depotId: r.ad, ad: r.ad, level: null, cutPct: r.pct, reason: r.neden || 'Kesinti yok' })),
    featuredDepotId: rows[0]?.ad ?? '',
    constraintLabel: run.transferType === 'amb' ? 'TIR/palet kısıtı' : 'backlog ya da merkez limiti',
  };
}

const TONES: CutTone[] = ['kap', 'kap2', 'kap3'];
const fmt = (v: Cell) => (typeof v === 'number' ? nf(v, v % 1 ? 1 : 0) : v ?? '—');

export async function getDepotDetail(id: string): Promise<{ detail: DepotDetail | null; name: string | null }> {
  const run = await requireRun();
  const v = await view(run);
  const row = depotRows(v).find((r) => r.ad === id);
  if (!row) return { detail: null, name: null };
  const e = await fetchDepot<DepotEntry>(id);
  const reasons = e.nedenler ?? [];
  const cutSum = reasons.reduce((s, n) => s + n.kes, 0);
  // Ürün satırları yuvarlanmış olabilir; şelale depo toplamına göre ölçeklenir.
  const scale = cutSum > 0 ? row.kesilen / cutSum : 0;
  const cuts = reasons.map((n, i) => ({
    key: 'k' + i, label: n.ad, legend: n.ad, source: n.ad.toLocaleLowerCase('tr-TR') + ' nedeniyle',
    amount: Math.round(n.kes * scale), tone: TONES[Math.min(i, 2)],
  }));
  const fillBars: MetricBar[] = (e.doluluk ?? []).filter((d) => d.tavan).flatMap((d) => {
    const now = (100 * ((d.dolu ?? 0) + (d.fin ?? 0))) / d.tavan!;
    const full = (100 * ((d.dolu ?? 0) + (d.fin ?? 0) + (d.kes ?? 0))) / d.tavan!;
    return [
      { label: `${d.ad} · gönderilenle`, value: now, unit: 'yuzde' as const, barPct: now, tone: 'brand' as const },
      { label: `${d.ad} · her şey gitseydi`, value: full, unit: 'yuzde' as const, barPct: full, tone: 'kap' as const },
    ];
  });
  const main = reasons[0];
  const kpi = e.kpi ?? [];
  const ledger: NonNullable<DepotDetail['ledger']> = [];
  for (const x of e.defter ?? []) {
    if ('bolum' in x) ledger.push({ section: x.bolum, rows: [] });
    else ledger[ledger.length - 1]?.rows.push({ op: x.op ?? '', label: x.ad, note: x.not ?? '', value: fmt(x.deger) });
  }
  return {
    name: id,
    detail: {
      depotId: id, ad: id, group: row.tip, level: 'bilgi', levelNote: null,
      context: contextOf(run), cutPct: row.pct,
      explanation: {
        headline: main
          ? `${id} önerinin %${nf(row.pct, 1)} kadarını alamadı. En büyük kesinti nedeni: ${main.ad}.`
          : `${id} için bu koşuda kesinti yok.`,
        body: `Öneri ${nf(row.oneri)}, gönderilen ${nf(row.final)}, kesilen ${nf(row.kesilen)} adet.`
          + (e.rozetler?.length ? ' ' + e.rozetler.map((r) => r.metin).join(' · ') + '.' : ''),
        recommendation: 'Nedeni ve ne yapılabileceğini Sonuçlar ekranında agent\'a sorabilirsiniz; agent bu deponun motor kanıtıyla yanıtlar.',
      },
      waterfall: { relexTotal: row.oneri, cuts, note: 'Kesim kalemleri ürün satırlarındaki nedenlerden toplanır.' },
      finding: null,
      tir: null,
      fill: fillBars.length ? { bars: fillBars, note: 'Teslim sonrası doluluk; kapasite buffer dahil.' } : null,
      metrics: kpi.length ? { title: 'Motor göstergeleri', items: kpi.map(([label, value, unit]) => ({ label, value: unit === '%' ? '%' + fmt(value) : `${fmt(value)}${unit ? ' ' + unit : ''}` })), note: 'Kaynak: motorun depo KPI\'ları.' } : null,
      chronic: null,
      aClassCut: null,
      topProducts: e.urunler?.length ? e.urunler.map((u) => ({ product: u.urun, cls: '', suggested: u.oneri, sent: u.final, reason: u.neden })) : null,
      trend: null,
      levers: null,
      ledger,
    },
  };
}
