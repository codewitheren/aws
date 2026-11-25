import { nf } from '../lib/format';
import type { MetricBar } from '../data/types';

const TONE: Record<MetricBar['tone'], string> = { yok: 'var(--yok)', kap: 'var(--kap)', brand: 'var(--brand)' };

function value(b: MetricBar): string {
  const digits = b.value % 1 ? 1 : 0;
  return b.unit === 'palet' ? `${nf(b.value, digits)} palet` : `%${nf(b.value, digits)}`;
}

/** Etiket + değer + ilerleme çubuğu listesi (TIR limiti, doluluk). */
export function MetricBars({ bars }: { bars: MetricBar[] }) {
  return (
    <div className="stack-m">
      {bars.map((b) => (
        <div className="stack-s" key={b.label} style={{ gap: 4 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
            <span>{b.label}</span>
            <strong>{value(b)}</strong>
          </div>
          <div className="track" aria-hidden="true">
            <div style={{ width: Math.min(b.barPct, 100) + '%', background: TONE[b.tone] }} />
          </div>
        </div>
      ))}
    </div>
  );
}
