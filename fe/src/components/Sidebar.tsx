import { Link, paths, type Route } from '../router/router';
import type { Theme } from '../theme/theme';

const NAV: { key: string; label: string; to: string; match: Route['name'][] }[] = [
  { key: 'kosu', label: 'Koşu', to: paths.kosu, match: ['kosu'] },
  { key: 'sonuclar', label: 'Sonuçlar', to: paths.sonuclar, match: ['sonuclar', 'anomaliler'] },
  { key: 'trend', label: 'Trend', to: paths.trend, match: ['trend'] },
  { key: 'depolar', label: 'Depolar', to: paths.depolar, match: ['depolar', 'depo'] },
];

interface Props {
  route: Route;
  theme: Theme;
  onToggleTheme: () => void;
  mode: 'mock' | 'http';
}

export function Sidebar({ route, theme, onToggleTheme, mode }: Props) {
  return (
    <nav className="sidebar" aria-label="Ana menü">
      <div className="brand">
        <strong>Transfer Kontrol</strong>
        <span className="sub">Getir · Transfer ekibi</span>
      </div>
      <ul className="navlist">
        {NAV.map((item) => {
          const on = item.match.includes(route.name);
          return (
            <li key={item.key}>
              <Link to={item.to} className={'navl' + (on ? ' on' : '')} aria-current={on ? 'page' : undefined}>
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
      <div className="side-foot">
        <button type="button" className="btn btn-sm" onClick={onToggleTheme} aria-pressed={theme === 'dark'}>
          Koyu tema
        </button>
        <span className="sub">
          {mode === 'mock' ? 'Örnek veri · mock agent' : 'Agent: canlı · ekran verisi örnek'}
        </span>
      </div>
    </nav>
  );
}
