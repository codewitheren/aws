import type { ApprovalResolution } from '../agent/types';
import { nf } from '../lib/format';
import { LEVEL_LABEL } from '../components/Chip';
import { SAMPLE_OUTLIERS } from './sample';
import { slugify } from '../lib/slug';
import type { AnomalyData, ResultsData, SampleContext } from './types';

export interface CsvFile {
  filename: string;
  header: string[];
  rows: string[][];
}

const slugCtx = (c: SampleContext) => `${slugify(c.merkez)}-${c.transferType}-${c.isoDate}`;

function runStatus(r: ApprovalResolution | undefined): string {
  if (!r) return 'Bu oturumda koşu çalıştırılmadı';
  return (r.outcome.kind === 'applied' ? 'Koşuda düzeltildi: ' : 'Düzeltilmedi: ') + r.summary + (r.note ? ` (not: ${r.note})` : '');
}

/**
 * Relex anomali listesi. Örnek veride yalnızca ekranda görünen satırlar vardır
 * (Coca-Cola Zero aykırı depoları + agent'ın koşuda sorduğu bulgular); 2.032 satırın tamamı backend'den gelir.
 */
export function anomalyCsv(data: AnomalyData, resolutions: readonly ApprovalResolution[]): CsvFile {
  const header = ['Tür', 'Depo', 'Ürün', 'Alan', 'Değer', 'Medyan', 'Medyanın katı', 'Agent notu', 'Koşu durumu'];
  const stock = data.outliers
    .slice()
    .sort((a, b) => b.value - a.value)
    .map((o) => ['Fazla stok şüphesi', o.ad, data.product, 'Stok + açık + öneri', nf(o.value), nf(data.median), nf(o.value / data.median, 1), o.note, '']);
  const findings = SAMPLE_OUTLIERS.map((f) => {
    const [depot, product] = f.title.split(' · ');
    return [
      'Aykırı PL önerisi', depot, product, f.metric === 'tahmin' ? 'Tahmin' : 'Öneri', nf(f.currentValue), nf(f.median),
      nf(f.currentValue / f.median, 1), f.found, runStatus(resolutions.find((r) => r.findingKey === f.findingKey)),
    ];
  });
  return { filename: `relex-anomalileri-${slugCtx(data.context)}.csv`, header, rows: [...stock, ...findings] };
}

export function alertsCsv(data: ResultsData): CsvFile {
  return {
    filename: `uyarilar-${slugCtx(data.context)}.csv`,
    header: ['Seviye', 'Uyarı', 'Kapsam', 'Kanıt', 'Önerilen aksiyon'],
    rows: data.alerts.map((a) => [LEVEL_LABEL[a.level], a.title, a.scope, a.evidence, a.action]),
  };
}
