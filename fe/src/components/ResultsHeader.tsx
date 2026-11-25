import type { ReactNode } from 'react';
import { nf } from '../lib/format';
import type { SampleContext } from '../data/types';
import { Link, paths } from '../router/router';

interface Props {
  context: SampleContext;
  active: 'ozet' | 'anomaliler';
  anomalyTotal: number;
  action: ReactNode;
}

/** Sonuçlar ekranlarının ortak başlığı ve sekmeleri. */
export function ResultsHeader({ context, active, anomalyTotal, action }: Props) {
  return (
    <>
      <header className="split-end">
        <div className="page-head">
          <h1 tabIndex={-1}>Sonuçlar</h1>
          <p className="sub">{context.merkez} · {context.transferTypeLabel} · {context.dateLabel}</p>
        </div>
        {action}
      </header>
      <nav aria-label="Sonuç bölümleri" className="tabs">
        <Link to={paths.sonuclar} className={'tab' + (active === 'ozet' ? ' on' : '')} aria-current={active === 'ozet' ? 'page' : undefined}>
          Özet
        </Link>
        <Link to={paths.anomaliler} className={'tab' + (active === 'anomaliler' ? ' on' : '')} aria-current={active === 'anomaliler' ? 'page' : undefined}>
          Relex anomalileri
          <span className="chip c-uyari" aria-label={`${nf(anomalyTotal)} şüpheli satır`}>{nf(anomalyTotal)}</span>
        </Link>
      </nav>
    </>
  );
}
