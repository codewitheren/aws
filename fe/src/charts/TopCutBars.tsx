import { pct } from '../lib/format';
import type { TopCutDepot } from '../data/types';
import { REASON_COLOR, REASON_LABEL } from '../components/Legend';
import { Link, paths } from '../router/router';

/** En çok kısılan depolar; çubuk rengi ana kesinti nedeni, nedenin adı bağlantı metninde de var. */
export function TopCutBars({ items }: { items: TopCutDepot[] }) {
  return (
    <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
      {items.map((d) => (
        <li key={d.depotId}>
          <Link to={paths.depo(d.depotId)} className="hbar">
            <span className="h-name">{d.ad}</span>
            <span className="h-area" aria-hidden="true">
              <span title={`${d.ad} · ${pct(d.pct)} · ${REASON_LABEL[d.reason]}`} style={{ width: d.pct + '%', background: REASON_COLOR[d.reason] }} />
            </span>
            <span className="sr-only">{`, ana neden ${REASON_LABEL[d.reason]}, kısma`}</span>
            <span className="h-val">{pct(d.pct)}</span>
          </Link>
        </li>
      ))}
    </ol>
  );
}
