const TR: Record<string, string> = { ç: 'c', ğ: 'g', ı: 'i', i: 'i', ö: 'o', ş: 's', ü: 'u' };

/** "Maltepe Sahil" → "maltepe-sahil", "SuadiyeBüyük" → "suadiyebuyuk" */
export function slugify(name: string): string {
  return name
    .toLocaleLowerCase('tr-TR')
    .replace(/[çğıiöşü]/g, (ch) => TR[ch] ?? ch)
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}
