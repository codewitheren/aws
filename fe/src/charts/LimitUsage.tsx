import { pct } from '../lib/format';
import type { LimitUsageRow } from '../data/types';

const COLS = [
  { key: 'amb', label: 'Ambient & Su' },
  { key: 'c4', label: '+4 (Soğuk)' },
  { key: 'ms', label: 'Meyve-Sebze' },
] as const;

function Cell({ value }: { value: number | null }) {
  if (value === null) return <div className="limit-cell"><span aria-label="Transfer yok">—</span></div>;
  const high = value >= 90;
  return (
    <div className="limit-cell">
      <span>
        {pct(value)}
        {high && <span className="mk-uyari" role="img" aria-label="yüzde 90 ve üzeri" />}
      </span>
      <div className="track" aria-hidden="true">
        <div style={{ width: Math.min(value, 100) + '%', background: high ? 'var(--uyari-mark)' : 'var(--brand)' }} />
      </div>
    </div>
  );
}

/** Merkez × transfer tipi satır limiti kullanımı. */
export function LimitUsage({ rows }: { rows: LimitUsageRow[] }) {
  return (
    <div role="table" aria-label="Merkez satır limiti kullanımı">
      <div role="row" className="limit-grid head lbl">
        <span role="columnheader">Merkez</span>
        {COLS.map((c) => <span role="columnheader" key={c.key}>{c.label}</span>)}
      </div>
      {rows.map((r) => (
        <div role="row" className="limit-grid" key={r.merkez}>
          <span role="rowheader" style={{ fontWeight: 500 }}>{r.merkez}</span>
          {COLS.map((c) => <div role="cell" key={c.key}><Cell value={r[c.key]} /></div>)}
        </div>
      ))}
    </div>
  );
}
