import { nf } from '../lib/format';
import type { AnomalyData } from '../data/types';

const X0 = 60;
const X1 = 880;
const Y0 = 320;
const SCALE = 0.625; // 1 adet = 0,625 birim; 400 adet = 250 birim
const TICKS = [0, 100, 200, 300, 400];

/** Bir ürün için depoların stok + açık + öneri değerleri; küçükten büyüğe sıralı noktalar. */
export function AnomalyDotChart({ data }: { data: AnomalyData }) {
  const slots = data.inliers.length + data.outliers.length;
  const xc = (i: number) => X0 + ((i + 0.5) * (X1 - X0)) / slots;
  const y = (q: number) => Y0 - q * SCALE;
  const top = data.outliers[data.outliers.length - 1];
  const ratio = (v: number) => nf(v / data.median, 1);
  const summary = top
    ? `Depoların çoğu medyan ${nf(data.median)} çevresinde. ${top.ad} ${nf(top.value)} ile üst sınırın (${nf(data.upperBound)}) çok üzerinde.`
    : `Depoların çoğu medyan ${nf(data.median)} çevresinde.`;

  return (
    <div className="chart-box">
      <svg className="chart" viewBox="0 0 900 360" role="img" aria-label={summary}>
        {TICKS.map((t) => (
          <g key={t}>
            <path d={`M${X0} ${y(t)}H${X1}`} stroke="var(--grid)" strokeWidth={1} fill="none" />
            <text x={52} y={y(t) + 4} textAnchor="end">{nf(t)}</text>
          </g>
        ))}
        <path d={`M${X0} ${y(data.median)}H${X1}`} stroke="var(--muted)" strokeWidth={1.5} fill="none" />
        <text x={64} y={y(data.median) + 14.5}>Medyan {nf(data.median)}</text>
        <path d={`M${X0} ${y(data.upperBound).toFixed(1)}H${X1}`} stroke="var(--uyari-mark)" strokeWidth={1.5} strokeDasharray="5 4" fill="none" />
        <text x={64} y={y(data.upperBound) - 7.8}>Üst sınır {nf(data.upperBound)}</text>
        {data.inliers.map((q, i) => (
          <circle key={i} cx={xc(i)} cy={y(q)} r={4} fill="var(--brand)" fillOpacity={0.5}>
            <title>{`Sınır içinde · ${nf(Math.round(q))} adet`}</title>
          </circle>
        ))}
        {data.outliers.map((o, j) => {
          const isTop = o === top;
          const cx = xc(data.inliers.length + j);
          return (
            <g key={o.depotId}>
              <circle cx={cx} cy={y(o.value)} r={isTop ? 7 : 5} fill="var(--uyari-mark)" stroke="var(--surface)" strokeWidth={2}>
                <title>{`${o.ad} · ${nf(o.value)} adet · medyanın ${ratio(o.value)} katı`}</title>
              </circle>
              {isTop && <text className="em" x={cx - 12.4} y={y(o.value) + 4} textAnchor="end">{`${o.ad} · ${nf(o.value)}`}</text>}
            </g>
          );
        })}
        <text x={470} y={348} textAnchor="middle">Depolar (stok + açık + öneri, adet)</text>
      </svg>
    </div>
  );
}
