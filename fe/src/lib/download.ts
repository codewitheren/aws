/** Tarayıcıda dosya indirmesi başlatır. */
export function downloadBlob(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function csvCell(value: string): string {
  return /[";\n\r]/.test(value) ? '"' + value.replace(/"/g, '""') + '"' : value;
}

/**
 * Türkçe Excel'in doğrudan açabileceği CSV: ";" ayırıcı, UTF-8 BOM, CRLF satır sonu.
 * Sayılar çağıran tarafından tr-TR biçiminde metne çevrilmiş olmalıdır.
 */
export function toCsvBlob(header: readonly string[], rows: readonly (readonly string[])[]): Blob {
  const lines = [header, ...rows].map((r) => r.map(csvCell).join(';'));
  return new Blob(['﻿' + lines.join('\r\n') + '\r\n'], { type: 'text/csv;charset=utf-8' });
}
