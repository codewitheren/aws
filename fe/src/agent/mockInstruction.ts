import { nf } from '../lib/format';
import type { ApprovalOutcome } from './types';

interface Finding {
  currentValue: number;
  mean: number;
  median: number;
}

export interface Interpretation {
  outcome: ApprovalOutcome;
  summary: string;
}

/** "1.000" (binlik) ya da "12,5" (ondalık) biçimindeki ilk sayıyı bulur. */
function firstNumber(text: string): number | null {
  const m = text.match(/\d{1,3}(?:\.\d{3})+(?!\d)|\d+(?:,\d+)?/);
  if (!m) return null;
  return Number(m[0].replace(/\./g, '').replace(',', '.'));
}

export function medianSummary(f: Finding): string {
  return `Medyana çekildi (${nf(f.currentValue)} → ${nf(f.median)})`;
}

export function unchangedSummary(f: Finding): string {
  return `Olduğu gibi bırakıldı (${nf(f.currentValue)})`;
}

/**
 * Mock agent'ın serbest metin talimatını yorumlaması:
 * - bir sayı → değeri o sayıyla sınırlar (yalnızca mevcut değerden küçükse değişiklik olur),
 * - "ortalama" → G10 ortalamasına çeker, "medyan" → medyana çeker,
 * - diğer her şey → not olarak kaydedilir ve öneri değiştirilmez.
 */
export function interpretInstruction(text: string, f: Finding): Interpretation {
  const t = text.toLocaleLowerCase('tr-TR');
  const n = firstNumber(t);
  if (n !== null) {
    const value = Math.round(n);
    if (value < f.currentValue) {
      return {
        outcome: { kind: 'applied', value, method: 'instruction' },
        summary: `Talimatla ${nf(value)} ile sınırlandı (${nf(f.currentValue)} → ${nf(value)})`,
      };
    }
    return {
      outcome: { kind: 'unchanged', reason: 'instruction_not_lower' },
      summary: `Değiştirilmedi: ${nf(value)}, mevcut değerin (${nf(f.currentValue)}) altında değil`,
    };
  }
  if (t.includes('ortalama')) {
    return {
      outcome: { kind: 'applied', value: f.mean, method: 'mean' },
      summary: `Ortalamaya çekildi (${nf(f.currentValue)} → ${nf(f.mean)})`,
    };
  }
  if (t.includes('medyan')) {
    return { outcome: { kind: 'applied', value: f.median, method: 'median' }, summary: medianSummary(f) };
  }
  return { outcome: { kind: 'unchanged', reason: 'instruction_note' }, summary: unchangedSummary(f) + ' · not alındı' };
}
