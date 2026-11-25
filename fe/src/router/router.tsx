import { useSyncExternalStore, type AnchorHTMLAttributes } from 'react';

/**
 * Hash tabanlı küçük yönlendirici. "#/depolar/goztepe" gibi adresler S3 + CloudFront üzerinde
 * yeniden yazma kuralı olmadan çalışır; uygulama alt klasörden sunulsa da bozulmaz.
 */
export type Route =
  | { name: 'kosu' }
  | { name: 'sonuclar' }
  | { name: 'anomaliler' }
  | { name: 'trend' }
  | { name: 'depolar' }
  | { name: 'depo'; id: string }
  | { name: 'notFound'; path: string };

export const paths = {
  kosu: '/kosu',
  sonuclar: '/sonuclar',
  anomaliler: '/sonuclar/anomaliler',
  trend: '/trend',
  depolar: '/depolar',
  depo: (id: string) => '/depolar/' + encodeURIComponent(id),
} as const;

export const DEFAULT_PATH = paths.kosu;

function safeDecode(s: string): string {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
}

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#/, '').split('?')[0].replace(/\/+$/, '') || '/';
  const parts = path.split('/').filter(Boolean);
  if (parts.length === 1) {
    switch (parts[0]) {
      case 'kosu': return { name: 'kosu' };
      case 'sonuclar': return { name: 'sonuclar' };
      case 'trend': return { name: 'trend' };
      case 'depolar': return { name: 'depolar' };
    }
  }
  if (parts.length === 2 && parts[0] === 'sonuclar' && parts[1] === 'anomaliler') return { name: 'anomaliler' };
  if (parts.length === 2 && parts[0] === 'depolar') return { name: 'depo', id: safeDecode(parts[1]) };
  return { name: 'notFound', path };
}

/** Adres boşsa varsayılan rotaya yönlendirir (geçmişe kayıt eklemeden). */
export function ensureDefaultRoute(): void {
  const h = window.location.hash;
  if (h === '' || h === '#' || h === '#/') {
    window.history.replaceState(null, '', '#' + DEFAULT_PATH);
  }
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange);
  return () => window.removeEventListener('hashchange', onChange);
}

export function useHash(): string {
  return useSyncExternalStore(subscribe, () => window.location.hash);
}

type LinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & { to: string };

/** Uygulama içi bağlantı. `to` "/depolar" gibi bir yoldur. */
export function Link({ to, ...rest }: LinkProps) {
  return <a href={'#' + to} {...rest} />;
}
