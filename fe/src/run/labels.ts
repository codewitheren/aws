import type { CheckId, StepId } from '../agent/types';

export const STEP_LABELS: Record<StepId, string> = {
  relex_read: 'Relex girdisi okunuyor',
  cutting_engine: 'Kesim motoru çalışıyor',
  agent_checks: 'Agent kontrol ediyor',
  ready: 'Hazır',
};

export const CHECK_LABELS: Record<CheckId, string> = {
  run_integrity: 'Koşu bütünlüğü',
  faulty_output: 'Hatalı çıktı',
  relex_anomalies: 'Relex anomalileri',
  depot_cuts: 'Depo kısmaları',
};
