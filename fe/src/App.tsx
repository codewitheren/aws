import { useEffect, useRef } from 'react';
import { Sidebar } from './components/Sidebar';
import { AnomaliPage } from './pages/AnomaliPage';
import { DepoPage } from './pages/DepoPage';
import { DepolarPage } from './pages/DepolarPage';
import { KosuPage } from './pages/KosuPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { SonuclarPage } from './pages/SonuclarPage';
import { TrendPage } from './pages/TrendPage';
import { parseRoute, useHash, type Route } from './router/router';
import { useRunStore } from './run/RunProvider';
import { useTheme } from './theme/theme';

const TITLES: Record<Route['name'], string> = {
  kosu: 'Optimizasyon başlat',
  sonuclar: 'Sonuçlar',
  anomaliler: 'Forecast anomalileri',
  trend: 'Kısma trendi',
  depolar: 'Depolar',
  depo: 'Depo detayı',
  notFound: 'Sayfa bulunamadı',
};

function Page({ route }: { route: Route }) {
  switch (route.name) {
    case 'kosu': return <KosuPage />;
    case 'sonuclar': return <SonuclarPage />;
    case 'anomaliler': return <AnomaliPage />;
    case 'trend': return <TrendPage />;
    case 'depolar': return <DepolarPage />;
    case 'depo': return <DepoPage key={route.id} id={route.id} />;
    case 'notFound': return <NotFoundPage path={route.path} />;
  }
}

export function App() {
  const hash = useHash();
  const route = parseRoute(hash);
  const { theme, toggle } = useTheme();
  const { mode } = useRunStore();
  const mainRef = useRef<HTMLElement>(null);
  const first = useRef(true);

  useEffect(() => {
    document.title = TITLES[route.name] + ' · Transfer Kontrol';
    if (first.current) {
      first.current = false;
      return;
    }
    // Ekran değişince başa dön ve odağı yeni sayfanın başlığına taşı (ekran okuyucular için).
    window.scrollTo(0, 0);
    const raf = requestAnimationFrame(() => {
      const h1 = mainRef.current?.querySelector<HTMLElement>('h1');
      (h1 ?? mainRef.current)?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(raf);
  }, [hash, route.name]);

  return (
    <div className="app">
      <a className="skip" href="#ana-icerik" onClick={(e) => { e.preventDefault(); mainRef.current?.focus(); }}>İçeriğe geç</a>
      <Sidebar route={route} theme={theme} onToggleTheme={toggle} mode={mode} />
      <main id="ana-icerik" className="main" ref={mainRef} tabIndex={-1}>
        <Page route={route} />
      </main>
    </div>
  );
}
