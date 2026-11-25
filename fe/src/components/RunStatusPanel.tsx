import type { ApprovalResponse, RunRevision } from '../agent/types';
import { nf } from '../lib/format';
import type { RunState } from '../run/reducer';
import { correctionSentence } from '../run/selectors';
import { Link, paths } from '../router/router';
import { useState } from 'react';
import { ApprovalCard } from './ApprovalCard';
import { DecisionsDialog } from './DecisionsDialog';
import { RuntimeConsole } from './RuntimeConsole';

interface Props {
  run: RunState | null;
  title: string;
  mock: boolean;
  announcement: string;
  responding: boolean;
  responseError: string | null;
  onRespond: (response: ApprovalResponse) => void;
}

function ReviewProgress({ decided, total, approved, onOpen }: { decided: number; total: number; approved: number; onOpen: () => void }) {
  const pct = total > 0 ? (decided / total) * 100 : 0;
  return (
    <div className="review-progress">
      <div className="split" style={{ alignItems: 'center' }}>
        <span style={{ fontSize: 13 }}>
          <strong>{decided} / {total}</strong> <span className="sub">karar · {approved} değişiklik onayı</span>
        </span>
        <button type="button" className="btn btn-sm" onClick={onOpen} disabled={decided === 0}>
          Kararları gör{decided > 0 ? ` (${decided})` : ''}
        </button>
      </div>
      <div className="track" role="progressbar" aria-label="Karar ilerlemesi" aria-valuemin={0} aria-valuemax={total} aria-valuenow={decided}>
        <div style={{ width: pct + '%', background: 'var(--brand)', transition: 'width .25s ease' }} />
      </div>
    </div>
  );
}

const amount = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 8 });

function AppliedRevisions({ revisions }: { revisions: RunRevision[] }) {
  return (
    <details className="run-revisions">
      <summary>Uygulanan satır değişiklikleri <span>{nf(revisions.length)}</span></summary>
      <div className="tw" tabIndex={0} role="region" aria-label="Uygulanan satır değişiklikleri">
        <table className="t">
          <thead>
            <tr><th scope="col">Depo ve ürün</th><th scope="col" className="n">Özgün</th><th scope="col" className="n">Revize</th><th scope="col" className="n">Motor finali</th></tr>
          </thead>
          <tbody>
            {revisions.map(({ depot, product, unit, original, revised, final }, index) => (
              <tr key={index}>
                <th scope="row">{product}<br /><span className="sub">{depot} · {unit}</span></th>
                <td className="n">{amount.format(original)}</td>
                <td className="n">{amount.format(revised)}</td>
                <td className="n">{final === null ? '—' : amount.format(final)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export function RunStatusPanel({ run, title, mock, announcement, responding, responseError, onRespond }: Props) {
  const [showDecisions, setShowDecisions] = useState(false);
  const decisions = (run?.resolutions ?? []).filter((r) => r.findingKey !== 'official');
  const approval = run?.pendingApproval;
  const total = approval && approval.findingKey !== 'official' ? approval.total : decisions.length;
  const revisions = run?.summary?.revisions ?? [];

  return (
    <section className="card run-status" aria-labelledby="s4">
      <div className="stack-s">
        <h2 id="s4">Optimizasyon durumu</h2>
        <span className="sub">{title}</span>
      </div>
      <p className="sr-only" role="status" aria-live="polite">{announcement}</p>
      <RuntimeConsole key={run?.context?.runId ?? 'idle'} run={run} mock={mock} responding={responding} />
      {approval && total > 0 && (
        <ReviewProgress decided={decisions.length} total={total}
          approved={decisions.filter((r) => r.outcome.kind === 'applied').length}
          onOpen={() => setShowDecisions(true)} />
      )}
      {approval && (
        <ApprovalCard key={approval.approvalId} approval={approval} responding={responding}
          error={responseError} onRespond={onRespond} />
      )}
      {run?.status === 'completed' && run.summary && (
        <div className="ok-box">
          <span className="ok-title">{run.summary.headline}</span>
          {decisions.length > 0 && (
            <span style={{ fontSize: 13 }}>
              {correctionSentence(decisions)}{' '}
              <button type="button" className="linkish" onClick={() => setShowDecisions(true)}>Kararları gör</button>
            </span>
          )}
          {!run.summary.resultsAvailable && (
            <span style={{ fontSize: 13 }}>
              Sonuç ekranları şu an Maltepe · Ambient &amp; Su örnek optimizasyonunu gösteriyor.
            </span>
          )}
          <Link className="btn btn-p" to={paths.sonuclar}>Sonuçları aç</Link>
        </div>
      )}
      {revisions.length > 0 && <AppliedRevisions revisions={revisions} />}
      <DecisionsDialog open={showDecisions} onClose={() => setShowDecisions(false)} resolutions={decisions} />
      {run?.status === 'failed' && run.error?.code === 'no_data' && (
        <div className="info-box" role="status">
          <strong>Depo verisi bulunamadı</strong>
          <span>{run.error.message}</span>
        </div>
      )}
      {run?.status === 'failed' && run.error && run.error.code !== 'no_data' && (
        <div className="err-box" role="alert">
          <strong>Optimizasyon tamamlanamadı.</strong>
          <span>{run.error.message}</span>
        </div>
      )}
    </section>
  );
}
