/**
 * Veri erişim katmanı. Bugün tüm ekran verisi örnek modülden gelir (her iki agent modunda da);
 * backend'de karşılık gelen uç noktalar olunca yalnızca bu dosyanın değişmesi yeterli olmalıdır.
 */
import { config } from '../config';
import { ANOMALIES, DEPOT_DETAILS, DEPOTS, KNOWN_DEPOTS, MERKEZLER, RESULTS, TREND } from './sample';
import type { AnomalyData, DepotDetail, DepotsData, MerkezOption, ResultsData, TrendData } from './types';

const resolved = <T>(value: T): Promise<T> => Promise.resolve(value);

export const dataApi = {
  getRunOptions: (): Promise<MerkezOption[]> => resolved(MERKEZLER),
  getResults: (): Promise<ResultsData> => resolved(RESULTS),
  getAnomalies: (): Promise<AnomalyData> => resolved(ANOMALIES),
  getTrend: (): Promise<TrendData> => resolved(TREND),
  getDepots: (): Promise<DepotsData> => resolved(DEPOTS),
  /** Detay verisi yoksa `detail: null`; depo adı biliniyorsa yine döner. */
  getDepotDetail: (id: string): Promise<{ detail: DepotDetail | null; name: string | null }> =>
    resolved({ detail: DEPOT_DETAILS[id] ?? null, name: KNOWN_DEPOTS[id] ?? null }),
};

export type FileResult =
  | { kind: 'file'; blob: Blob; filename: string }
  | { kind: 'unavailable'; message: string };

/**
 * Transfer çıktısı (.xlsx) backend tarafından üretilir; istemcide sahte tablo üretilmez.
 * Mock modda dosya yoktur ve bunu açıkça söyleriz.
 */
export async function fetchTransferOutput(runId: string | null): Promise<FileResult> {
  if (config.agentMode === 'mock') {
    return {
      kind: 'unavailable',
      message: 'Transfer çıktısı (.xlsx) agent backend\'i tarafından üretilir. Örnek (mock) modda bu dosya indirilemez.',
    };
  }
  if (!runId) {
    return { kind: 'unavailable', message: 'Transfer çıktısı için önce bu oturumda bir koşu tamamlanmalı.' };
  }
  const res = await fetch(`${config.apiBaseUrl}/runs/${encodeURIComponent(runId)}/files/transfer-output.xlsx`);
  if (!res.ok) {
    return { kind: 'unavailable', message: `Dosya alınamadı (HTTP ${res.status}).` };
  }
  return { kind: 'file', blob: await res.blob(), filename: `transfer-ciktisi-${runId}.xlsx` };
}
