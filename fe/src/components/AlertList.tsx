import type { AlertLevel, ResultAlert } from '../data/types';
import { Link } from '../router/router';
import { LEVEL_LABEL, LevelChip } from './Chip';

const LEVELS: AlertLevel[] = ['kritik', 'uyari', 'bilgi'];

export function AlertList({ alerts }: { alerts: ResultAlert[] }) {
  return (
    <section className="card" aria-labelledby="u1">
      <div className="split" style={{ alignItems: 'center' }}>
        <h2 id="u1">Uyarılar</h2>
        <div className="inline" style={{ gap: 6 }}>
          {LEVELS.map((l) => {
            const n = alerts.filter((a) => a.level === l).length;
            return n > 0 ? <LevelChip key={l} level={l}>{n} {LEVEL_LABEL[l]}</LevelChip> : null;
          })}
        </div>
      </div>
      <ul className="alerts" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {alerts.map((a, i) => (
          <li key={i}>
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
    </section>
  );
}
