import { useState } from 'react';
import type { AlertLevel, ResultAlert } from '../data/types';
import { nf } from '../lib/format';
import { Link } from '../router/router';
import { LEVEL_LABEL, LevelChip } from './Chip';

const LEVELS: AlertLevel[] = ['kritik', 'uyari', 'bilgi'];
const PAGE = 6;

/** Uyarılar seviyeye göre sekmelere ayrılır; her sekme sayfalıdır, kart boyu sabit kalır. */
export function AlertList({ alerts }: { alerts: ResultAlert[] }) {
  const counts = Object.fromEntries(LEVELS.map((l) => [l, alerts.filter((a) => a.level === l).length])) as Record<AlertLevel, number>;
  const [level, setLevel] = useState<AlertLevel>(() => LEVELS.find((l) => counts[l] > 0) ?? 'kritik');
  const [page, setPage] = useState(0);
  const list = alerts.filter((a) => a.level === level);
  const pages = Math.max(1, Math.ceil(list.length / PAGE));
  const current = Math.min(page, pages - 1);
  const shown = list.slice(current * PAGE, current * PAGE + PAGE);
  const pick = (l: AlertLevel) => { setLevel(l); setPage(0); };

  return (
    <section className="card" aria-labelledby="u1">
      <div className="split" style={{ alignItems: 'center' }}>
        <h2 id="u1">Uyarılar</h2>
        <span className="sub">{nf(alerts.length)} uyarı</span>
      </div>
      <div className="seg seg-flush" role="tablist" aria-label="Uyarı seviyesi">
        {LEVELS.map((l) => (
          <button key={l} type="button" role="tab" id={'ut-' + l} aria-selected={level === l} aria-controls="u-panel"
            className={level === l ? 'on' : ''} disabled={counts[l] === 0} onClick={() => pick(l)}>
            <i className={'seg-dot d-' + l} aria-hidden="true" />{LEVEL_LABEL[l]} <span className="seg-n">{counts[l]}</span>
          </button>
        ))}
      </div>
      <div id="u-panel" role="tabpanel" aria-labelledby={'ut-' + level}>
        {list.length === 0 ? (
          <p className="sub">Bu optimizasyonda uyarı yok.</p>
        ) : (
          <ul className="alerts" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {shown.map((a, i) => (
              <li key={current * PAGE + i}>
                <Link to={a.link.route} className="alert-row">
                  <span className="lvl"><LevelChip level={a.level} /></span>
                  <span className="a-title">
                    <strong>{a.title}</strong>
                    <span className="sub">{a.scope}</span>
                  </span>
                  <span className="a-ev"><span className="lbl">Kanıt</span><span>{a.evidence}</span></span>
                  <span className="a-act"><span className="lbl">Önerilen aksiyon</span><span>{a.action}</span></span>
                  <span className="go">{a.link.label}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
      {pages > 1 && (
        <nav className="pager" aria-label="Uyarı sayfaları">
          <span className="sub">{current * PAGE + 1}–{Math.min(list.length, current * PAGE + PAGE)} / {list.length}</span>
          <div className="inline" style={{ gap: 6 }}>
            <button type="button" className="btn btn-sm" disabled={current === 0} onClick={() => setPage(current - 1)} aria-label="Önceki sayfa">‹ Önceki</button>
            <span className="sub" aria-current="page">{current + 1} / {pages}</span>
            <button type="button" className="btn btn-sm" disabled={current >= pages - 1} onClick={() => setPage(current + 1)} aria-label="Sonraki sayfa">Sonraki ›</button>
          </div>
        </nav>
      )}
    </section>
  );
}
