import { CHECK_ORDER, STEP_ORDER, type StepId } from '../agent/types';
import { CHECK_LABELS, STEP_LABELS } from '../run/labels';
import type { RunState, StepState } from '../run/reducer';
import { Link, paths } from '../router/router';

interface Props {
  run: RunState | null;
  title: string;
  announcement: string;
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

export function RunStatusPanel({ run, title, announcement }: Props) {
  const step = (id: StepId) => run?.steps[id] ?? IDLE;

  return (
    <section className="card" aria-labelledby="s4" style={{ flex: '2 1 380px' }}>
      <div className="stack-s">
        <h2 id="s4">Koşu durumu</h2>
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
          <span style={{ fontSize: 13 }}>
            Aykırı Relex önerileri koşuyu değiştirmez; Sonuçlar → Relex anomalileri sayfasında listelenir. Agent hiçbir sisteme yazmaz.
          </span>
          {!run.summary.resultsAvailable && (
            <span style={{ fontSize: 13 }}>
              Sonuç ekranları şu an Maltepe · Ambient &amp; Su örnek koşusunu gösteriyor.
            </span>
          )}
          <Link className="btn btn-p" to={paths.sonuclar}>Sonuçları aç</Link>
        </div>
      )}
      {run?.status === 'failed' && run.error && (
        <div className="err-box" role="alert">
          <strong>Koşu tamamlanamadı.</strong>
          <span>{run.error.message}</span>
        </div>
      )}
    </section>
  );
}
