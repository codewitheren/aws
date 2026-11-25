import { pct } from '../lib/format';
import { dayAxis } from './timeAxis';

interface Props {
  depotName: string;
  depot: number[];
  merkez: number[];
  days: string[];
}

const X0 = 40;
const X1 = 590;
const y = (p: number) => 190 - p * 1.8;

/** Depo kısma oranı (turuncu) ve merkez ortalaması (kesikli). */
export function DepotTrendChart({ depotName, depot, merkez, days }: Props) {
  const { xc } = dayAxis(X0, X1, depot.length);
  const path = (s: number[]) => s.map((p, i) => (i ? 'L' : 'M') + xc(i).toFixed(1) + ' ' + y(p).toFixed(1)).join('');
  const last = depot.length - 1;
  const min = Math.min(...depot.slice(0, last));
  const max = Math.max(...depot.slice(0, last));
  const label = `${depotName} son ${depot.length} gündür yüzde ${Math.floor(min)} ile ${Math.ceil(max)} arasında kısılıyor, bugün ${pct(depot[last])}; merkez ortalaması bugün ${pct(merkez[last], 1)}.`;
  const ticks = [0, 14, last];

  return (
    <div className="chart-box">
      <svg className="chart small" viewBox="0 0 600 220" role="img" aria-label={label}>
        <path d="M40 190H590M40 145H590M40 100H590M40 55H590M40 10H590" stroke="var(--grid)" strokeWidth={1} fill="none" />
        <text x={32} y={194} textAnchor="end">%0</text>
        <text x={32} y={104} textAnchor="end">%50</text>
        <text x={32} y={14} textAnchor="end">%100</text>
        {ticks.map((i) => <text key={i} x={Math.min(xc(i), 572)} y={212} textAnchor="middle">{days[i]}</text>)}
        <path d={path(merkez)} fill="none" stroke="var(--muted)" strokeWidth={1.5} strokeDasharray="4 4" />
        <path d={path(depot)} fill="none" stroke="var(--kap)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {depot.map((p, i) => (
          <circle key={i} cx={xc(i)} cy={y(p)} r={i === last ? 5 : 6} fill={i === last ? 'var(--kap)' : 'transparent'}
            stroke={i === last ? 'var(--surface)' : 'none'} strokeWidth={2}>
            <title>{`${days[i]} · ${depotName} ${pct(p, 1)} · merkez ${pct(merkez[i], 1)}`}</title>
          </circle>
        ))}
        <text className="em" x={572} y={42} textAnchor="end">{depotName} {pct(depot[last])}</text>
        <text x={572} y={y(merkez[last]) + 17.6} textAnchor="end">Merkez {pct(merkez[last], 1)}</text>
      </svg>
    </div>
  );
}
