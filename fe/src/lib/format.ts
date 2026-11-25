/** tr-TR sayı biçimi: binlik ayırıcı ".", ondalık ",". */
export function nf(n: number, digits = 0): string {
  return n.toLocaleString('tr-TR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** "%44,2" biçiminde yüzde. */
export function pct(n: number, digits = 0): string {
  return '%' + nf(n, digits);
}

const dateFmt = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric' });
const weekdayFmt = new Intl.DateTimeFormat('tr-TR', { weekday: 'long' });
const timeFmt = new Intl.DateTimeFormat('tr-TR', { hour: '2-digit', minute: '2-digit' });

/** "25.11.2026" */
export function formatDate(d: Date): string {
  return dateFmt.format(d);
}

/** "25.11.2026 Çarşamba" */
export function formatDateWithWeekday(d: Date): string {
  return formatDate(d) + ' ' + weekdayFmt.format(d);
}

/** "07:02" */
export function formatTime(d: Date): string {
  return timeFmt.format(d);
}

/** Yerel saate göre "YYYY-MM-DD". */
export function isoDay(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
}

/** Motor ve agent metinlerinde talep tahmini kaynağı "Relex" geçer; arayüzde adı Forecast. */
export function forecastName<T>(v: T): T {
  if (typeof v !== 'string') return v;
  return v.replace(/Relex['’]te/g, "Forecast'ta").replace(/Relex['’]e\b/g, "Forecast'a").replace(/Relex['’]in\b/g, "Forecast'un")
    .replace(/Relex/g, 'Forecast') as T;
}
