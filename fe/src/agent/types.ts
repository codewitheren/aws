/**
 * Agent olay protokolü. Arayüz ile agent (mock ya da gerçek backend) arasındaki tek sözleşme budur.
 * Backend bu olayları SSE `data:` satırlarında JSON olarak gönderir (bkz. README).
 */

export type TransferTypeId = 'amb' | 'c4' | 'ms';

export type ActivityKind = 'command' | 'data' | 'check' | 'decision' | 'output' | 'error';

export interface RunActivity {
  id: string;
  at: string;
  kind: ActivityKind;
  title: string;
  detail?: string;
  code?: string;
}

export interface RunRevision {
  depot: string;
  product: string;
  unit: string;
  original: number;
  revised: number;
  final: number | null;
}

export interface RunContext {
  runId: string;
  merkez: string;
  transferType: TransferTypeId;
  transferTypeLabel: string;
  /** Optimizasyonun iş tarihi, "YYYY-MM-DD". */
  runDate: string;
}

export type ApprovalOptionId = 'accept' | 'accept_all_remaining' | 'reject' | 'reject_all_remaining';

export interface ApprovalOption {
  id: ApprovalOptionId;
  label: string;
}

/** Agent'ın bulduğu aykırı bir PL önerisi ve kullanıcıya sorduğu düzeltme. */
export interface ApprovalRequest {
  approvalId: string;
  /** 1'den başlar. */
  index: number;
  total: number;
  /** Aynı bulguyu farklı ekranlarda eşlemek için kararlı anahtar, ör. "goztepe:bulasik-sungeri-5li". */
  findingKey: string;
  depotId: string;
  title: string;
  found: string;
  proposal: string;
  howApplied: string;
  impact: string;
  question: string;
  /** Düzeltilen alan: öneri miktarı ya da satış tahmini. */
  metric: 'oneri' | 'tahmin';
  currentValue: number;
  proposedValue: number;
  reference: { group: string; mean: number; median: number };
  options: ApprovalOption[];
  instruction: { allowed: boolean; placeholder: string };
}

export type ApprovalOutcome =
  | { kind: 'applied'; value: number; method: 'median' | 'mean' | 'instruction' }
  | { kind: 'unchanged'; reason: 'rejected' | 'instruction_note' | 'instruction_not_lower' };

export interface ApprovalResolution {
  approvalId: string;
  findingKey: string;
  title: string;
  originalValue: number;
  outcome: ApprovalOutcome;
  /** Kısa insan okunur sonuç, ör. "Medyana çekildi (100 → 16)". */
  summary: string;
  /** Kullanıcının serbest metin talimatı, varsa. */
  note?: string;
  decidedBy: 'user' | 'bulk';
}

export interface RunSummary {
  headline: string;
  counts: { kritik: number; uyari: number; bilgi: number };
  corrections: { applied: number; unchanged: number };
  revisions?: RunRevision[];
  /** ISO 8601 */
  finishedAt: string;
  /** Sonuç ekranlarındaki veri bu optimizasyona mı ait? Mock modda yalnızca örnek kombinasyon için true. */
  resultsAvailable: boolean;
}

export interface AgentError {
  code: string;
  message: string;
}

export type RunEvent =
  | { type: 'run_started'; run: RunContext }
  | { type: 'run_activity'; runId: string; activity: RunActivity }
  | { type: 'approval_requested'; runId: string; approval: ApprovalRequest }
  | { type: 'approval_resolved'; runId: string; resolution: ApprovalResolution }
  | { type: 'review_reset'; runId: string }
  | { type: 'run_completed'; runId: string; summary: RunSummary }
  | { type: 'run_failed'; runId: string | null; error: AgentError };

/** Yanıttaki bağlantı; `route` uygulama içi yol, ör. "/depolar/goztepe". */
export interface ChatLink {
  label: string;
  route: string;
}

export type ChatEvent =
  | { type: 'chat_message_started'; messageId: string }
  | { type: 'chat_delta'; messageId: string; delta: string; replace?: boolean }
  | { type: 'chat_message_completed'; messageId: string; text?: string; links: ChatLink[] }
  | { type: 'chat_failed'; messageId: string | null; error: AgentError };

export type AgentEvent = RunEvent | ChatEvent;

// ---- Arayüzün gönderdiği komutlar ----

export interface StartRunCommand {
  type: 'start_run';
  /** İş tarihi "YYYY-MM-DD"; verilmezse bugün (İstanbul). Sayım, teslimat ve girdi güncelliği buna göre denetlenir. */
  date?: string;
  merkez: string;
  transferType: TransferTypeId;
}

export type ApprovalResponse =
  | { kind: 'accept' }
  | { kind: 'reject' }
  | { kind: 'accept_all_remaining' }
  | { kind: 'reject_all_remaining' }
  | { kind: 'instruction'; text: string };

export interface RespondToApprovalCommand {
  type: 'respond_to_approval';
  runId: string;
  approvalId: string;
  response: ApprovalResponse;
}

export interface AskCommand {
  type: 'ask';
  question: string;
  /** Soru bir optimizasyon bağlamında soruluyorsa onun kimliği. */
  runId: string | null;
}

export type AgentCommand = StartRunCommand | RespondToApprovalCommand | AskCommand;

// ---- Çalışma zamanı doğrulaması (ağdan gelen JSON için) ----

const RUN_EVENT_TYPES: ReadonlySet<string> = new Set<RunEvent['type']>([
  'run_started', 'run_activity', 'approval_requested', 'approval_resolved', 'review_reset', 'run_completed', 'run_failed',
]);
const CHAT_EVENT_TYPES: ReadonlySet<string> = new Set<ChatEvent['type']>([
  'chat_message_started', 'chat_delta', 'chat_message_completed', 'chat_failed',
]);

function typeOf(value: unknown): string | null {
  if (typeof value !== 'object' || value === null || !('type' in value)) return null;
  const t = (value as { type: unknown }).type;
  return typeof t === 'string' ? t : null;
}

/**
 * Yüzeysel doğrulama: yalnızca `type` alanını kontrol eder. Backend sözleşmeye uymazsa
 * alt alanlar eksik olabilir; tam şema doğrulaması backend bağlanınca eklenmelidir.
 */
export function isRunEvent(value: unknown): value is RunEvent {
  const t = typeOf(value);
  return t !== null && RUN_EVENT_TYPES.has(t);
}

export function isRunActivity(value: unknown): value is RunActivity {
  if (typeof value !== 'object' || value === null) return false;
  const { id, at, kind, title, code, detail } = value as Partial<RunActivity>;
  return typeof id === 'string' && typeof at === 'string' && Number.isFinite(Date.parse(at))
    && typeof kind === 'string' && ['command', 'data', 'check', 'decision', 'output', 'error'].includes(kind)
    && typeof title === 'string' && (code === undefined || typeof code === 'string')
    && (detail === undefined || typeof detail === 'string');
}

export function isChatEvent(value: unknown): value is ChatEvent {
  const t = typeOf(value);
  return t !== null && CHAT_EVENT_TYPES.has(t);
}
