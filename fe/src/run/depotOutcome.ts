import type { DepotDetail, WaterfallCut } from '../data/types';
import type { FindingState } from './selectors';

export interface DepotFigures {
  /** Optimizasyonda kullanılan toplam öneri (düzeltme uygulandıysa düşmüş hali). */
  total: number;
  cuts: WaterfallCut[];
  sent: number;
  /** Düzeltmenin toplam öneriden düşürdüğü adet (yoksa 0). */
  delta: number;
}

/**
 * Bulgu kararını depo rakamlarına uygular. Varsayım (agent açıklamasındaki gibi): düşülen miktar
 * zaten `absorbedByCut` kaleminden kesilecekti, bu yüzden gönderilen miktar değişmez.
 */
export function depotFigures(detail: DepotDetail, state: FindingState): DepotFigures {
  const f = detail.finding;
  const applied = f && state.kind === 'resolved' && state.resolution.outcome.kind === 'applied' ? state.resolution.outcome.value : null;
  const delta = f && applied !== null ? Math.max(0, Math.min(f.relexValue - applied, cutAmount(detail.waterfall.cuts, f.absorbedByCut))) : 0;
  const cuts = detail.waterfall.cuts.map((c) => (f && c.key === f.absorbedByCut ? { ...c, amount: c.amount - delta } : c));
  const total = detail.waterfall.relexTotal - delta;
  const sent = total - cuts.reduce((s, c) => s + c.amount, 0);
  return { total, cuts, sent, delta };
}

function cutAmount(cuts: readonly WaterfallCut[], key: string): number {
  return cuts.find((c) => c.key === key)?.amount ?? 0;
}
