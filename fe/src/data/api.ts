/**
 * Veri erişim katmanı. Mock modda örnek modülden, AgentCore modunda son tamamlanan optimizasyondan okur (data/live.ts).
 */
import { config } from '../config';
import * as live from './live';
import { ANOMALIES, DEPOT_DETAILS, DEPOTS, KNOWN_DEPOTS, MERKEZLER, RESULTS, TREND } from './sample';
import type { AnomalyData, DepotDetail, DepotsData, MerkezOption, ResultsData, TrendData } from './types';

const resolved = <T>(value: T): Promise<T> => Promise.resolve(value);

const sampleApi = {
  getRunOptions: (): Promise<MerkezOption[]> => resolved(MERKEZLER),
  getResults: (): Promise<ResultsData> => resolved(RESULTS),
  getAnomalies: (): Promise<AnomalyData> => resolved(ANOMALIES),
  getTrend: (): Promise<TrendData> => resolved(TREND),
  getDepots: (): Promise<DepotsData> => resolved(DEPOTS),
  /** Detay verisi yoksa `detail: null`; depo adı biliniyorsa yine döner. */
  getDepotDetail: (id: string): Promise<{ detail: DepotDetail | null; name: string | null }> =>
    resolved({ detail: DEPOT_DETAILS[id] ?? null, name: KNOWN_DEPOTS[id] ?? null }),
};

const liveApi: typeof sampleApi = {
  getRunOptions: () => resolved(live.MERKEZLER),
  getResults: live.getResults,
  getAnomalies: live.getAnomalies,
  getTrend: live.getTrend,
  getDepots: live.getDepots,
  getDepotDetail: live.getDepotDetail,
};

export const dataApi = config.agentMode === 'agentcore' ? liveApi : sampleApi;
