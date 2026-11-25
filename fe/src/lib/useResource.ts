import { useEffect, useState } from 'react';

export type Resource<T> =
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string };

/** Bir Promise döndüren yükleyiciyi çalıştırır; `key` değişince yeniden yükler. */
export function useResource<T>(load: () => Promise<T>, key: string): Resource<T> {
  const [state, setState] = useState<{ key: string; res: Resource<T> }>({ key, res: { status: 'loading' } });

  useEffect(() => {
    let active = true;
    load().then(
      (data) => active && setState({ key, res: { status: 'ready', data } }),
      (err: unknown) => active && setState({ key, res: { status: 'error', message: err instanceof Error ? err.message : String(err) } }),
    );
    return () => {
      active = false;
    };
    // `load` her render'da yeni olabilir; yeniden yükleme bilerek yalnızca `key` ile tetiklenir.
  }, [key]);

  return state.key === key ? state.res : { status: 'loading' };
}
