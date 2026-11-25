import { nf, pct } from '../lib/format';
import type { ScatterHighlight } from '../data/types';
import { paths } from '../router/router';

const x = (fill: number) => 60 + fill * 5.125;
const y = (cut: number) => 410 - cut * 3.9;

/** Etiket noktanın soluna yazılır; grafiğin tepesine yakınsa altına, değilse üstüne. */
function labelY(cy: number): number {
  return cy < 60 ? cy + 14.7 : cy - 13.3;
}

interface Props {
  points: [number, number][];
  highlights: ScatterHighlight[];
}

/** Tam gönderimde doluluk × kısma oranı. İşaretli depolar detay sayfasına bağlantıdır. */
export function DepotScatter({ points, highlights }: Props) {
  const describe = (h: ScatterHighlight) => `${h.ad} · ${pct(h.fillPct, h.fillPct % 1 ? 1 : 0)} dolu, ${pct(h.cutPct)} kısma`;
  const label = 'Depoların tam gönderimde doluluğu ve kısma oranı. '
    + highlights.map((h) => `${h.ad}: doluluk yüzde ${nf(h.fillPct, h.fillPct % 1 ? 1 : 0)}, kısma yüzde ${nf(h.cutPct)}.`).join(' ');

  return (
    <div className="chart-box">
      <svg className="chart" viewBox="0 0 900 470" role="group" aria-label={label}>
        <g aria-hidden="true">
          <path d="M60 410H880M60 312.5H880M60 215H880M60 117.5H880M60 20H880" stroke="var(--grid)" strokeWidth={1} fill="none" />
          <path d="M572.5 20V410M60 215H880" stroke="var(--muted)" strokeWidth={1} strokeDasharray="4 4" fill="none" />
          <text x={52} y={414} textAnchor="end">%0</text>
          <text x={52} y={219} textAnchor="end">%50</text>
          <text x={52} y={24} textAnchor="end">%100</text>
          {[0, 50, 100, 150].map((v) => <text key={v} x={x(v)} y={430} textAnchor="middle">{pct(v)}</text>)}
          <text x={470} y={458} textAnchor="middle">Tam gönderimde doluluk</text>
          <text x={14} y={215} textAnchor="middle" transform="rotate(-90 14 215)">Kısma oranı</text>
          <text className="em" x={70} y={38}>Dolap boş ama kısılıyor: TIR/palet kısıtı</text>
          <text className="em" x={870} y={38} textAnchor="end">Dolap dolu</text>
          <text className="em" x={70} y={400}>Sağlıklı</text>
          <text className="em" x={870} y={400} textAnchor="end">Doluya yakın</text>
          {points.map(([f, k], i) => (
            <circle key={i} cx={x(f)} cy={y(k)} r={4} fill="var(--brand)" fillOpacity={0.45}>
              <title>{`Depo · ${pct(f)} dolu, ${pct(k)} kısma`}</title>
            </circle>
          ))}
        </g>
        {highlights.map((h) => {
          const cx = x(h.fillPct);
          const cy = y(h.cutPct);
          return (
            <a key={h.depotId} href={'#' + paths.depo(h.depotId)} aria-label={`${describe(h)}. Depo detayını aç`}>
              <circle cx={cx} cy={cy} r={12} fill="transparent" />
              <circle cx={cx} cy={cy} r={7} fill="var(--kap)" stroke="var(--surface)" strokeWidth={2}>
                <title>{describe(h) + ' · detay için tıklayın'}</title>
              </circle>
              <text className="em" x={cx - 12.6} y={labelY(cy)} textAnchor="end">{describe(h)}</text>
            </a>
          );
        })}
      </svg>
    </div>
  );
}
