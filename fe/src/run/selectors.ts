import type { ApprovalResolution, TransferTypeId } from '../agent/types';
import { isActive, type RunState } from './reducer';

export function correctionCounts(resolutions: readonly ApprovalResolution[]): { applied: number; unchanged: number } {
  const applied = resolutions.filter((r) => r.outcome.kind === 'applied').length;
  return { applied, unchanged: resolutions.length - applied };
}

export function correctionSentence(resolutions: readonly ApprovalResolution[]): string {
  const { applied, unchanged } = correctionCounts(resolutions);
  return `${applied} düzeltme uygulandı, ${unchanged} öneri olduğu gibi bırakıldı.`;
}

export function runMatches(run: RunState | null, merkez: string, transferType: TransferTypeId): boolean {
  return run !== null && run.request.merkez === merkez && run.request.transferType === transferType;
}

export type FindingState =
  | { kind: 'not_asked' }
  | { kind: 'pending'; awaitingNow: boolean }
  | { kind: 'resolved'; resolution: ApprovalResolution; runCompleted: boolean };

/**
 * Bir bulgunun bu oturumdaki son koşudaki durumu. Yalnızca bulgunun ait olduğu
 * merkez ve transfer tipiyle yapılan koşu dikkate alınır; başarısız koşu sayılmaz.
 */
export function findingState(
  run: RunState | null,
  finding: { findingKey: string; merkez: string; transferType: TransferTypeId },
): FindingState {
  if (!run || !runMatches(run, finding.merkez, finding.transferType) || run.status === 'failed') return { kind: 'not_asked' };
  const resolution = run.resolutions.find((r) => r.findingKey === finding.findingKey);
  if (resolution) return { kind: 'resolved', resolution, runCompleted: run.status === 'completed' };
  if (isActive(run)) return { kind: 'pending', awaitingNow: run.pendingApproval?.findingKey === finding.findingKey };
  return { kind: 'not_asked' };
}
