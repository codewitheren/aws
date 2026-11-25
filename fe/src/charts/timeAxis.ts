/** 30 günlük grafiklerde ortak yatay eksen: sütun merkezleri ve tarih etiketleri. */
export function dayAxis(x0: number, x1: number, n: number) {
  const step = (x1 - x0) / n;
  return { step, xc: (i: number) => x0 + step * (i + 0.5) };
}

/** Eksende gösterilen gün indeksleri (ilk gün, haftalık, bugün). */
export function tickIndices(n: number): number[] {
  return [0, 7, 14, 21, n - 1].filter((i) => i < n);
}
