import type { ReactNode } from 'react';
import type { Resource } from '../lib/useResource';

/** Veri yüklenirken ve hata durumunda tutarlı bir görünüm verir. */
export function Loadable<T>({ resource, children }: { resource: Resource<T>; children: (data: T) => ReactNode }) {
  if (resource.status === 'loading') {
    return <p className="sub" aria-busy="true">Yükleniyor…</p>;
  }
  if (resource.status === 'error') {
    return (
      <div className="err-box" role="alert">
        <strong>Veri yüklenemedi.</strong>
        <span>{resource.message}</span>
      </div>
    );
  }
  return <>{children(resource.data)}</>;
}
