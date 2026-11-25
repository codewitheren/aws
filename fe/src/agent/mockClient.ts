/**
 * Mock agent: tasarımdaki akışı zamanlayıcılarla canlandırır. Hiçbir sisteme yazmaz,
 * ağ isteği yapmaz. Bulgular yalnızca örnek kombinasyon (Maltepe · Ambient & Su) için vardır.
 */
import { isoDay, nf } from '../lib/format';
import { MERKEZLER, RESULTS, SAMPLE_CONTEXT } from '../data/sample';
import type { AgentClient, StreamHandle } from './client';
import { cannedAnswer } from './mockChat';
import type {
  ApprovalResolution, CheckId, ChatEvent, RunContext, RunEvent, StartRunCommand,
} from './types';
import { CHECK_ORDER } from './types';

type Timer = ReturnType<typeof setTimeout>;

function newId(prefix: string): string {
  return prefix + '-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
}

class MockRun {
  private timers: Timer[] = [];
  private stopped = false;
  readonly resolutions: ApprovalResolution[] = [];

  constructor(
    readonly context: RunContext,
    private readonly lineCount: number | null,
    private readonly sample: boolean,
    private readonly emit: (event: RunEvent) => void,
  ) {
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
      this.finishReview();
    });
  }

  private finishReview(): void {
    const runId = this.context.runId;
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

    async respondToApproval() {
      throw new Error('Koşu sırasında onay istenmez.');
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
