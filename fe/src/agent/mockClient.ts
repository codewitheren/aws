/**
 * Mock agent: tasarımdaki akışı zamanlayıcılarla canlandırır. Hiçbir sisteme yazmaz,
 * ağ isteği yapmaz. Bulgular yalnızca örnek kombinasyon (Maltepe · Ambient & Su) için vardır.
 */
import { isoDay, nf } from '../lib/format';
import { MERKEZLER, RESULTS, SAMPLE_CONTEXT, SAMPLE_OUTLIERS, type SampleOutlier } from '../data/sample';
import type { AgentClient, StreamHandle } from './client';
import { cannedAnswer } from './mockChat';
import { interpretInstruction, medianSummary, unchangedSummary } from './mockInstruction';
import type {
  ApprovalRequest, ApprovalResolution, ApprovalResponse, CheckId, ChatEvent, RunContext, RunEvent, StartRunCommand,
} from './types';
import { CHECK_ORDER } from './types';

type Timer = ReturnType<typeof setTimeout>;

const HOW_APPLIED =
  'Yalnızca bu koşuda, kesim motorundan önce. Relex kaydı değişmez; satır anomali listesine "koşuda düzeltildi" notuyla girer.';

function newId(prefix: string): string {
  return prefix + '-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
}

function toApproval(o: SampleOutlier, index: number, total: number): ApprovalRequest {
  const remainingAfter = total - index;
  return {
    approvalId: o.findingKey,
    index,
    total,
    findingKey: o.findingKey,
    depotId: o.depotId,
    title: o.title,
    found: o.found,
    proposal: o.proposal,
    howApplied: HOW_APPLIED,
    impact: o.impact,
    question: `Medyana (${nf(o.median)}) çekeyim mi?`,
    metric: o.metric,
    currentValue: o.currentValue,
    proposedValue: o.median,
    reference: { group: 'G10', mean: o.mean, median: o.median },
    options: [
      { id: 'accept', label: `Evet, medyana çek (${nf(o.median)})` },
      ...(remainingAfter > 0
        ? [{ id: 'accept_all_remaining' as const, label: `Evet, kalan ${remainingAfter} bulguyu da sormadan medyana çek` }]
        : []),
      { id: 'reject', label: `Hayır, olduğu gibi bırak (${nf(o.currentValue)})` },
    ],
    instruction: { allowed: true, placeholder: 'ör. ortalamaya çek, 20 ile sınırla' },
  };
}

function resolve(o: SampleOutlier, response: ApprovalResponse, decidedBy: ApprovalResolution['decidedBy']): ApprovalResolution {
  const base = { approvalId: o.findingKey, findingKey: o.findingKey, title: o.title, originalValue: o.currentValue, decidedBy };
  switch (response.kind) {
    case 'accept':
    case 'accept_all_remaining':
      return { ...base, outcome: { kind: 'applied', value: o.median, method: 'median' }, summary: medianSummary(o) };
    case 'reject':
      return { ...base, outcome: { kind: 'unchanged', reason: 'rejected' }, summary: unchangedSummary(o) };
    case 'instruction': {
      const { outcome, summary } = interpretInstruction(response.text, o);
      return { ...base, outcome, summary, note: response.text };
    }
  }
}

class MockRun {
  private timers: Timer[] = [];
  private pending: SampleOutlier[];
  private index = 0;
  private stopped = false;
  readonly resolutions: ApprovalResolution[] = [];

  constructor(
    readonly context: RunContext,
    private readonly lineCount: number | null,
    private readonly sample: boolean,
    private readonly emit: (event: RunEvent) => void,
  ) {
    this.pending = sample ? [...SAMPLE_OUTLIERS] : [];
  }

  private at(ms: number, fn: () => void): void {
    this.timers.push(setTimeout(() => !this.stopped && fn(), ms));
  }

  private send(event: RunEvent): void {
    if (!this.stopped) this.emit(event);
  }

  start(): void {
    const runId = this.context.runId;
    this.at(0, () => {
      this.send({ type: 'run_started', run: this.context });
      this.send({ type: 'step_started', runId, step: 'relex_read' });
    });
    this.at(900, () => {
      const detail = this.lineCount !== null ? `${nf(this.lineCount)} öneri satırı okundu` : undefined;
      this.send({ type: 'step_completed', runId, step: 'relex_read', detail });
      this.send({ type: 'step_started', runId, step: 'outlier_review' });
      if (this.pending.length === 0) {
        this.finishReview('Örnek veride bu merkez ve tip için aykırı öneri yok.');
        return;
      }
      this.send({ type: 'step_progress', runId, step: 'outlier_review', detail: `${this.pending.length} aykırı öneri buldum. Onayınız bekleniyor` });
      this.askNext();
    });
  }

  private total(): number {
    return this.index + this.pending.length;
  }

  private askNext(): void {
    const next = this.pending[0];
    if (!next) {
      const applied = this.resolutions.filter((r) => r.outcome.kind === 'applied').length;
      this.finishReview(`${applied} düzeltme uygulandı, ${this.resolutions.length - applied} öneri olduğu gibi bırakıldı.`);
      return;
    }
    this.send({ type: 'approval_requested', runId: this.context.runId, approval: toApproval(next, this.index + 1, this.total()) });
  }

  respond(approvalId: string, response: ApprovalResponse): void {
    const current = this.pending[0];
    if (!current || current.findingKey !== approvalId) throw new Error('Bu öneri artık onay beklemiyor.');
    if (response.kind === 'instruction' && response.text.trim() === '') throw new Error('Talimat boş olamaz.');
    const batch = response.kind === 'accept_all_remaining' ? this.pending.splice(0) : this.pending.splice(0, 1);
    // Agent'ın yanıtı işlemesi için kısa bir gecikme.
    this.at(300, () => {
      batch.forEach((o, i) => {
        const resolution = resolve(o, response, i === 0 ? 'user' : 'bulk');
        this.resolutions.push(resolution);
        this.index += 1;
        this.send({ type: 'approval_resolved', runId: this.context.runId, resolution });
      });
      this.askNext();
    });
  }

  private finishReview(detail: string): void {
    const runId = this.context.runId;
    this.send({ type: 'step_completed', runId, step: 'outlier_review', detail });
    this.send({ type: 'step_started', runId, step: 'cutting_engine' });
    const check = (c: CheckId, status: 'running' | 'done') => this.send({ type: 'check_progress', runId, check: c, status });
    this.at(1400, () => {
      this.send({ type: 'step_completed', runId, step: 'cutting_engine' });
      this.send({ type: 'step_started', runId, step: 'agent_checks' });
      check(CHECK_ORDER[0], 'running');
    });
    CHECK_ORDER.slice(1).forEach((c, i) => {
      this.at(2100 + i * 700, () => {
        check(CHECK_ORDER[i], 'done');
        check(c, 'running');
      });
    });
    this.at(4300, () => {
      check(CHECK_ORDER[CHECK_ORDER.length - 1], 'done');
      this.send({ type: 'step_completed', runId, step: 'agent_checks' });
      this.send({ type: 'step_started', runId, step: 'ready' });
      this.send({ type: 'step_completed', runId, step: 'ready' });
      const applied = this.resolutions.filter((r) => r.outcome.kind === 'applied').length;
      const levels = RESULTS.alerts.map((a) => a.level);
      const count = (l: string) => (this.sample ? levels.filter((x) => x === l).length : 0);
      this.send({
        type: 'run_completed',
        runId,
        summary: {
          headline: this.sample
            ? `Koşu hazır. ${count('kritik')} kritik, ${count('uyari')} uyarı var.`
            : 'Koşu tamamlandı (örnek akış). Bu merkez ve tip için örnek sonuç verisi yok.',
          counts: { kritik: count('kritik'), uyari: count('uyari'), bilgi: count('bilgi') },
          corrections: { applied, unchanged: this.resolutions.length - applied },
          finishedAt: new Date().toISOString(),
          resultsAvailable: this.sample,
        },
      });
      this.stopped = true;
    });
  }

  abort(): void {
    this.stopped = true;
    this.timers.forEach(clearTimeout);
    this.timers = [];
  }
}

function streamText(text: string, onChunk: (s: string) => void, onDone: () => void): StreamHandle {
  const chunks = text.match(/\S+\s*/g) ?? [text];
  const timers = chunks.map((c, i) => setTimeout(() => onChunk(c), 120 + i * 28));
  timers.push(setTimeout(onDone, 120 + chunks.length * 28 + 40));
  return { abort: () => timers.forEach(clearTimeout) };
}

export function createMockAgentClient(): AgentClient {
  const runs = new Map<string, MockRun>();
  let lastRun: MockRun | null = null;

  return {
    mode: 'mock',

    startRun(command: StartRunCommand, onEvent: (event: RunEvent) => void): StreamHandle {
      const merkez = MERKEZLER.find((m) => m.ad === command.merkez);
      const tip = merkez?.tipler.find((t) => t.id === command.transferType);
      const context: RunContext = {
        runId: newId('mock'),
        merkez: command.merkez,
        transferType: command.transferType,
        transferTypeLabel: tip?.ad ?? command.transferType,
        runDate: isoDay(new Date()),
      };
      if (!merkez || !tip || !tip.relexAt) {
        const t = setTimeout(() => onEvent({
          type: 'run_failed', runId: null,
          error: { code: 'relex_input_missing', message: 'Bu merkez ve transfer tipi için bugünün Relex girdisi yok.' },
        }), 0);
        return { abort: () => clearTimeout(t) };
      }
      const sample = command.merkez === SAMPLE_CONTEXT.merkez && command.transferType === SAMPLE_CONTEXT.transferType;
      const run = new MockRun(context, tip.lineCount, sample, onEvent);
      runs.set(context.runId, run);
      lastRun = run;
      run.start();
      return {
        abort: () => {
          run.abort();
          runs.delete(context.runId);
        },
      };
    },

    async respondToApproval(command) {
      const run = runs.get(command.runId);
      if (!run) throw new Error('Koşu bulunamadı.');
      run.respond(command.approvalId, command.response);
    },

    ask(command, onEvent: (event: ChatEvent) => void): StreamHandle {
      const source = (command.runId && runs.get(command.runId)) || lastRun;
      const answer = cannedAnswer(command.question, source?.resolutions ?? []);
      const messageId = newId('msg');
      onEvent({ type: 'chat_message_started', messageId });
      return streamText(
        answer.text,
        (delta) => onEvent({ type: 'chat_delta', messageId, delta }),
        () => onEvent({ type: 'chat_message_completed', messageId, links: answer.links }),
      );
    },
  };
}
