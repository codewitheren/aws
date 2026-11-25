import { CHECK_ORDER, STEP_ORDER, type ApprovalResponse, type StepId } from '../agent/types';
import { CHECK_LABELS, STEP_LABELS } from '../run/labels';
import type { RunState, StepState } from '../run/reducer';
import { correctionSentence } from '../run/selectors';
import { Link, paths } from '../router/router';
import { useState } from 'react';
import { ApprovalCard } from './ApprovalCard';
import { DecisionsDialog } from './DecisionsDialog';

interface Props {
  run: RunState | null;
  title: string;
  announcement: string;
  responding: boolean;
  responseError: string | null;
  onRespond: (response: ApprovalResponse) => void;
}

const IDLE: StepState = { status: 'pending', detail: null };

function statusText(s: StepState): string {
  if (s.detail) return s.detail;
  return s.status === 'done' ? 'Tamamlandı' : s.status === 'active' ? 'Çalışıyor…' : 'Bekliyor';
}

function Marker({ status, small }: { status: StepState['status']; small?: boolean }) {
  return (
    <span aria-hidden="true" className={'dot ' + status + (small ? ' dot-s' : '')}>
      {status === 'done' && !small && (
        <svg width="12" height="12" viewBox="0 0 12 12"><path d="M2.5 6.2l2.3 2.3 4.7-4.9" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
      )}
    </span>
  );
}

/** Karar ilerlemesi: sabit yükseklikte; kartın yerini değiştirmez. Kararlar dialogda. */
function ReviewProgress({ decided, total, applied, onOpen }: { decided: number; total: number; applied: number; onOpen: () => void }) {
  const pct = total > 0 ? (decided / total) * 100 : 0;
  return (
    <div className="review-progress">
      <div className="split" style={{ alignItems: 'center' }}>
        <span style={{ fontSize: 13 }}>
          <strong>{decided} / {total}</strong> <span className="sub">karar · {applied} düzeltme</span>
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

export function RunStatusPanel({ run, title, announcement, responding, responseError, onRespond }: Props) {
  const step = (id: StepId) => run?.steps[id] ?? IDLE;
  const [showDecisions, setShowDecisions] = useState(false);
  // Resmi optimizasyon onayı bir bulgu kararı değil; sayaçta ve listede gösterilmez.
  const decisions = (run?.resolutions ?? []).filter((r) => r.findingKey !== 'official');

  return (
    <section className="card" aria-labelledby="s4" style={{ flex: '2 1 380px' }}>
      <div className="stack-s">
        <h2 id="s4">Optimizasyon durumu</h2>
        <span className="sub">{title}</span>
      </div>
      <p className="sr-only" role="status" aria-live="polite">{announcement}</p>
      <ol className="steps">
        {STEP_ORDER.map((id) => {
          const s = step(id);
          return (
            <li key={id} className={'step ' + s.status}>
              <Marker status={s.status} />
              <div className="step-body">
                <span className="step-name">{STEP_LABELS[id]}</span>
                <span className="sub">{statusText(s)}</span>
                {id === 'outlier_review' && run && (run.pendingApproval || decisions.length > 0) && (
                  <ReviewProgress
                    decided={decisions.length}
                    total={run.pendingApproval?.findingKey === 'official' ? decisions.length : run.pendingApproval?.total ?? decisions.length}
                    applied={decisions.filter((r) => r.outcome.kind === 'applied').length}
                    onOpen={() => setShowDecisions(true)}
                  />
                )}
                {id === 'outlier_review' && run?.pendingApproval && (
                  <ApprovalCard
                    key={run.pendingApproval.approvalId}
                    approval={run.pendingApproval}
                    responding={responding}
                    error={responseError}
                    onRespond={onRespond}
                  />
                )}
                {id === 'agent_checks' && (
                  <ul className="mini-list" style={{ gap: 8 }}>
                    {CHECK_ORDER.map((c) => {
                      const cs = run?.checks[c] ?? IDLE;
                      return (
                        <li key={c} className={'check ' + cs.status}>
                          <Marker status={cs.status} small />
                          <span>{CHECK_LABELS[c]}</span>
                          <span className="sub">{statusText(cs)}</span>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      {run?.status === 'completed' && run.summary && (
        <div className="ok-box">
          <span className="ok-title">{run.summary.headline}</span>
          {decisions.length > 0 && (
            <span style={{ fontSize: 13 }}>
              {correctionSentence(decisions)}{' '}
              <button type="button" className="linkish" onClick={() => setShowDecisions(true)}>Kararları gör</button>
            </span>
          )}
          <span style={{ fontSize: 13 }}>
            Düzeltmeler yalnızca bu optimizasyonun çıktısına uygulandı; Forecast'a ya da başka bir sisteme yazılmadı.
          </span>
          {!run.summary.resultsAvailable && (
            <span style={{ fontSize: 13 }}>
              Sonuç ekranları şu an Maltepe · Ambient &amp; Su örnek optimizasyonunu gösteriyor.
            </span>
          )}
          <Link className="btn btn-p" to={paths.sonuclar}>Sonuçları aç</Link>
        </div>
      )}
      <DecisionsDialog open={showDecisions} onClose={() => setShowDecisions(false)} resolutions={decisions} />
      {run?.status === 'failed' && run.error && (
        <div className="err-box" role="alert">
          <strong>Optimizasyon tamamlanamadı.</strong>
          <span>{run.error.message}</span>
        </div>
      )}
    </section>
  );
}
