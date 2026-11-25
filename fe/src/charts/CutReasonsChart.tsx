import { pct } from '../lib/format';
import type { DayReasons } from '../data/types';
import { REASON_COLOR, REASON_LABEL } from '../components/Legend';
import { dayAxis, tickIndices } from './timeAxis';

const X0 = 40;
const X1 = 890;
const sy = (p: number) => 210 - p * 2;
const ORDER = ['kap', 'backlog', 'limit', 'yok'] as const;

/** Önerilen miktarın kesinti nedenlerine göre günlük payı (%100'e tamamlanan sütunlar). */
export function CutReasonsChart({ days, reasons }: { days: string[]; reasons: DayReasons[] }) {
  const { xc } = dayAxis(X0, X1, reasons.length);
  const avg = (k: (typeof ORDER)[number]) => reasons.reduce((s, d) => s + d[k], 0) / reasons.length;
  const label = 'Önerilen miktarın kesinti nedenlerine göre günlük dağılımı. Ortalama: '
    + ORDER.map((k) => `${REASON_LABEL[k]} ${pct(avg(k))}`).join(', ') + '.';

  return (
    <div className="chart-box">
      <svg className="chart" viewBox="0 0 900 240" role="img" aria-label={label}>
        {[0, 50, 100].map((g) => (
          <g key={g}>
            <path d={`M${X0} ${sy(g)}H${X1}`} stroke="var(--grid)" strokeWidth={1} fill="none" />
            <text x={32} y={sy(g) + 4} textAnchor="end">{pct(g)}</text>
          </g>
        ))}
        {reasons.map((d, i) => {
          let acc = 0;
          return (
            <g key={i}>
              {ORDER.map((k) => {
                const q = d[k];
                const top = sy(acc + q) + 1;
                acc += q;
                return (
                  <rect key={k} x={xc(i) - 10} y={top} width={20} height={Math.max(q * 2 - 2, 1)} fill={REASON_COLOR[k]}>
                    <title>{`${days[i]} · ${REASON_LABEL[k]} ${pct(q, 1)}`}</title>
                  </rect>
                );
              })}
            </g>
          );
        })}
        {tickIndices(days.length).map((i) => (
          <text key={i} x={Math.min(xc(i), 872)} y={232} textAnchor="middle">{days[i]}</text>
        ))}
      </svg>
    </div>
  );
}
