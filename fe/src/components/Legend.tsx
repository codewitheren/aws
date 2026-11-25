import type { CSSProperties, ReactNode } from 'react';

export interface LegendItem {
  label: ReactNode;
  swatch: CSSProperties;
}

export function Legend({ items, label }: { items: LegendItem[]; label?: string }) {
  return (
    <div className="lg" role="list" aria-label={label ?? 'Gösterim'}>
      {items.map((item, i) => (
        <span key={i} role="listitem">
          <b aria-hidden="true" style={item.swatch} />
          {item.label}
        </span>
      ))}
    </div>
  );
}

/** Kesinti nedenlerinin sabit renkleri; her grafikte aynı kalır. */
export const REASON_COLOR = {
  kap: 'var(--kap)',
  backlog: 'var(--backlog)',
  limit: 'var(--limit)',
  yok: 'var(--yok)',
} as const;

export const REASON_LABEL = {
  kap: 'Depo kapasitesi',
  backlog: 'Backlog',
  limit: 'Merkez satır limiti',
  yok: 'Kesinti yok',
} as const;

export function reasonLegend(keys: readonly (keyof typeof REASON_COLOR)[]): LegendItem[] {
  return keys.map((k) => ({ label: REASON_LABEL[k], swatch: { background: REASON_COLOR[k] } }));
}
