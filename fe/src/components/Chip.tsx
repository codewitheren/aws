import type { ReactNode } from 'react';
import type { AlertLevel } from '../data/types';

export const LEVEL_LABEL: Record<AlertLevel, string> = { kritik: 'Kritik', uyari: 'Uyarı', bilgi: 'Bilgi' };

export type ChipTone = AlertLevel | 'iyi' | 'notr';

const TONE_CLASS: Record<ChipTone, string> = {
  kritik: 'c-krit', uyari: 'c-uyari', bilgi: 'c-bilgi', iyi: 'c-iyi', notr: 'c-notr',
};

/** Seviye çipi: renk + metin + farklı işaret şekli (daire / elmas / halka). */
export function Chip({ tone, children }: { tone: ChipTone; children: ReactNode }) {
  return (
    <span className={'chip ' + TONE_CLASS[tone]}>
      {tone !== 'notr' && <i aria-hidden="true" />}
      {children}
    </span>
  );
}

export function LevelChip({ level, children }: { level: AlertLevel; children?: ReactNode }) {
  return <Chip tone={level}>{children ?? LEVEL_LABEL[level]}</Chip>;
}
