import { pct } from '../lib/format';
import { dayAxis, tickIndices } from './timeAxis';

interface Props {
  days: string[];
  values: number[];
  band: { low: number; high: number };
}

const X0 = 40;
const X1 = 890;
const y = (p: number) => 220 - ((p - 25) / 35) * 200;
const GRID = [30, 40, 50, 60];

/** Merkez kısma oranı, normal bant ve bant dışı günler. */
export function TrendLineChart({ days, values, band }: Props) {
  const { xc } = dayAxis(X0, X1, values.length);
  const last = values.length - 1;
  const today = values[last];
  const outside = (p: number) => p > band.high || p < band.low;
  const outCount = values.filter(outside).length;
  const line = values.map((p, i) => (i ? 'L' : 'M') + xc(i).toFixed(1) + ' ' + y(p).toFixed(1)).join(' ');
  const label = `Son ${values.length} günün kısma oranı; bugün ${pct(today, 1)}, `
    + `${outside(today) ? 'normal bandın dışında' : 'normal bandın içinde'}. ${outCount} gün bant dışında.`;

  return (
    <div className="chart-box">
      <svg className="chart" viewBox="0 0 900 260" role="img" aria-label={label}>
        <rect x={X0} y={y(band.high)} width={X1 - X0} height={y(band.low) - y(band.high)} fill="var(--band)">
          <title>{`Normal bant ${pct(band.low)}–${pct(band.high)}`}</title>
        </rect>
        {GRID.map((g) => (
          <g key={g}>
            <path d={`M${X0} ${y(g).toFixed(1)}H${X1}`} stroke="var(--grid)" strokeWidth={1} fill="none" />
            <text x={32} y={y(g) + 4} textAnchor="end">{pct(g)}</text>
          </g>
        ))}
        {tickIndices(days.length).map((i) => (
          <text key={i} x={Math.min(xc(i), 872)} y={252} textAnchor="middle">{days[i]}</text>
        ))}
        <path d={line} fill="none" stroke="var(--brand)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {values.map((p, i) => {
          const isOut = outside(p);
          const isToday = i === last;
          return (
            <circle
              key={i}
              cx={xc(i)}
              cy={y(p)}
              r={isOut || isToday ? 5 : 7}
              fill={isToday ? 'var(--brand)' : isOut ? 'var(--uyari-mark)' : 'transparent'}
              stroke={isOut || isToday ? 'var(--surface)' : 'none'}
              strokeWidth={2}
            >
              <title>{`${days[i]} · ${pct(p, 1)}${isOut ? ' · bant dışı' : ''}`}</title>
            </circle>
          );
        })}
        <text className="em" x={884} y={96} textAnchor="end">Bugün {pct(today, 1)}</text>
      </svg>
    </div>
  );
}
