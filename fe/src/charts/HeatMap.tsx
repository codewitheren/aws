import { pct } from '../lib/format';
import type { HeatRow } from '../data/types';
import { Link, paths } from '../router/router';
import { tickIndices } from './timeAxis';

export const heatColor = (p: number) => `color-mix(in oklab, var(--heat) ${Math.round(p)}%, var(--surface2))`;

/** Depo × gün kısma oranı ısı haritası. Her hücrenin değeri araç ipucunda ve satır özetinde yazılıdır. */
export function HeatMap({ rows, days }: { rows: HeatRow[]; days: string[] }) {
  return (
    <div className="tw">
      <div className="heat">
        {rows.map((row) => {
          const last = row.values[row.values.length - 1];
          const avg = row.values.reduce((s, v) => s + v, 0) / row.values.length;
          return (
            <div className="heat-row" key={row.depotId}>
              <Link to={paths.depo(row.depotId)} className="h-name">{row.ad}</Link>
              <div className="heat-cells" aria-hidden="true">
                {row.values.map((p, i) => (
                  <span key={i} title={`${row.ad} · ${days[i]} · ${pct(p)}`} style={{ background: heatColor(p) }} />
                ))}
              </div>
              <span className="sr-only">{`${row.ad}: son ${row.values.length} gün ortalama ${pct(avg)}, bugün`}</span>
              <span className="h-last">{pct(last)}</span>
            </div>
          );
        })}
        <div className="heat-row" aria-hidden="true">
          <span className="h-name" />
          <div className="sub" style={{ flex: 1, display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
            {tickIndices(days.length).map((i) => <span key={i}>{days[i]}</span>)}
          </div>
          <span className="sub h-last" style={{ fontSize: 11 }}>Bugün</span>
        </div>
      </div>
    </div>
  );
}
