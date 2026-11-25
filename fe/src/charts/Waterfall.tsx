import { nf } from '../lib/format';
import type { CutTone, WaterfallCut } from '../data/types';
import { Legend } from '../components/Legend';

export interface WaterfallInput {
  total: number;
  cuts: WaterfallCut[];
  sent: number;
}

const TONE: Record<CutTone, string> = { kap: 'var(--kap)', kap2: 'var(--kap2)', kap3: 'var(--kap3)' };
const w = (n: number, total: number) => (total > 0 ? (n / total) * 100 : 0).toFixed(2) + '%';

/** Kesim şelalesi: öneriden her kesim kalemi düşülür, kalan gönderilen miktardır. */
export function Waterfall({ total, cuts, sent }: WaterfallInput) {
  let right = total;
  const rows = cuts.map((c) => {
    right -= c.amount;
    return { ...c, left: right };
  });

  return (
    <>
      <Legend
        items={[
          { label: 'Öneri', swatch: { background: 'var(--yok)' } },
          ...cuts.map((c) => ({ label: c.legend, swatch: { background: TONE[c.tone] } })),
          { label: 'Gönderilen', swatch: { background: 'var(--iyi-mark)' } },
        ]}
      />
      <div className="stack-m" role="list" aria-label="Kesim şelalesi, adet">
        <div className="bar-row" role="listitem">
          <span className="bar-label">Öneri</span>
          <span className="bar-area" aria-hidden="true"><span title={`Öneri ${nf(total)}`} style={{ width: '100%', background: 'var(--yok)' }} /></span>
          <span className="bar-val">{nf(total)}</span>
        </div>
        {rows.map((c) => (
          <div className="bar-row" role="listitem" key={c.key}>
            <span className="bar-label">{c.label}</span>
            <span className="bar-area" aria-hidden="true">
              <span title={`${c.legend} −${nf(c.amount)}`} style={{ marginLeft: w(c.left, total), width: w(c.amount, total), background: TONE[c.tone] }} />
            </span>
            <span className="bar-val">−{nf(c.amount)}</span>
          </div>
        ))}
        <div className="bar-row" role="listitem">
          <span className="bar-label">Gönderilen</span>
          <span className="bar-area" aria-hidden="true"><span title={`Gönderilen ${nf(sent)}`} style={{ width: w(sent, total), background: 'var(--iyi-mark)' }} /></span>
          <span className="bar-val">{nf(sent)}</span>
        </div>
      </div>
    </>
  );
}
