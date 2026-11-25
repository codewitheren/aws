import {
  CHECK_ORDER, STEP_ORDER,
  type AgentError, type ApprovalRequest, type ApprovalResolution, type ChatEvent, type ChatLink, type CheckId,
  type RunContext, type RunEvent, type RunSummary, type StepId, type TransferTypeId,
} from '../agent/types';
import { config } from '../config';
import { STEP_LABELS } from './labels';

export type StepStatus = 'pending' | 'active' | 'done';

export interface StepState {
  status: StepStatus;
  detail: string | null;
}

export type RunStatus = 'starting' | 'running' | 'awaiting_approval' | 'completed' | 'failed';

export interface Selection {
  merkez: string;
  transferType: TransferTypeId;
}

export interface RunState {
  status: RunStatus;
  request: Selection;
  context: RunContext | null;
  steps: Record<StepId, StepState>;
  checks: Record<CheckId, StepState>;
  pendingApproval: ApprovalRequest | null;
  resolutions: ApprovalResolution[];
  summary: RunSummary | null;
  error: AgentError | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'agent';
  text: string;
  status: 'streaming' | 'done' | 'failed';
  links: ChatLink[];
}

export interface StoreState {
  selection: Selection;
  run: RunState | null;
  /** Onaya verilen yanıt agent'a iletiliyor. */
  responding: boolean;
  responseError: string | null;
  chat: ChatMessage[];
  chatBusy: boolean;
  /** Ekran okuyucular için son önemli durum (aria-live). */
  announcement: string;
}

export type StoreAction =
  | { type: 'select'; selection: Selection }
  | { type: 'run_requested'; selection?: Selection }
  | { type: 'run_event'; event: RunEvent }
  | { type: 'respond_started' }
  | { type: 'respond_failed'; message: string }
  | { type: 'chat_asked'; id: string; question: string }
  | { type: 'chat_event'; event: ChatEvent };

export const initialState: StoreState = {
  selection: { merkez: config.agentMode === 'agentcore' ? 'İzmir' : 'Maltepe', transferType: 'amb' },
  run: null,
  responding: false,
  responseError: null,
  chat: [],
  chatBusy: false,
  announcement: '',
};

export function isActive(run: RunState | null): boolean {
  return run !== null && (run.status === 'starting' || run.status === 'running' || run.status === 'awaiting_approval');
}

function pendingRecord<K extends string>(keys: readonly K[]): Record<K, StepState> {
  return Object.fromEntries(keys.map((k) => [k, { status: 'pending', detail: null }])) as Record<K, StepState>;
}

function newRun(request: Selection): RunState {
  return {
    status: 'starting',
    request,
    context: null,
    steps: pendingRecord(STEP_ORDER),
    checks: pendingRecord(CHECK_ORDER),
    pendingApproval: null,
    resolutions: [],
    summary: null,
    error: null,
  };
}

function eventRunId(event: RunEvent): string | null {
  return event.type === 'run_started' ? event.run.runId : event.runId;
}

function applyRunEvent(run: RunState, event: RunEvent): { run: RunState; announcement?: string } {
  switch (event.type) {
    case 'run_started':
      return { run: { ...run, status: 'running', context: event.run } };
    case 'step_started':
      return {
        run: { ...run, steps: { ...run.steps, [event.step]: { status: 'active', detail: null } } },
        announcement: event.step === 'ready' ? undefined : STEP_LABELS[event.step],
      };
    case 'step_progress':
      return { run: { ...run, steps: { ...run.steps, [event.step]: { ...run.steps[event.step], detail: event.detail } } } };
    case 'step_completed':
      return { run: { ...run, steps: { ...run.steps, [event.step]: { status: 'done', detail: event.detail ?? null } } } };
    case 'check_progress':
      return {
        run: {
          ...run,
          checks: { ...run.checks, [event.check]: { status: event.status === 'done' ? 'done' : 'active', detail: event.detail ?? null } },
        },
      };
    case 'approval_requested': {
      const a = event.approval;
      return {
        run: { ...run, status: 'awaiting_approval', pendingApproval: a },
        announcement: `Agent önerisi ${a.index} / ${a.total}: ${a.title}. ${a.question}`,
      };
    }
    case 'approval_resolved': {
      const r = event.resolution;
      const resolutions = [...run.resolutions.filter((x) => x.approvalId !== r.approvalId), r];
      const cleared = run.pendingApproval?.approvalId === r.approvalId;
      return {
        run: {
          ...run,
          resolutions,
          pendingApproval: cleared ? null : run.pendingApproval,
          status: cleared ? 'running' : run.status,
        },
        announcement: `${r.title}: ${r.summary}`,
      };
    }
    case 'run_completed':
      return {
        run: { ...run, status: 'completed', pendingApproval: null, summary: event.summary },
        announcement: event.summary.headline,
      };
    case 'run_failed':
      return {
        run: { ...run, status: 'failed', pendingApproval: null, error: event.error },
        announcement: 'Optimizasyon tamamlanamadı: ' + event.error.message,
      };
  }
}

function applyChatEvent(state: StoreState, event: ChatEvent): StoreState {
  switch (event.type) {
    case 'chat_message_started':
      return { ...state, chat: [...state.chat, { id: event.messageId, role: 'agent', text: '', status: 'streaming', links: [] }] };
    case 'chat_delta':
      return {
        ...state,
        chat: state.chat.map((m) => (m.id === event.messageId ? { ...m, text: m.text + event.delta } : m)),
      };
    case 'chat_message_completed':
      return {
        ...state,
        chatBusy: false,
        chat: state.chat.map((m) => (m.id === event.messageId ? { ...m, status: 'done', links: event.links } : m)),
      };
    case 'chat_failed': {
      const text = 'Yanıt alınamadı: ' + event.error.message;
      const exists = event.messageId !== null && state.chat.some((m) => m.id === event.messageId);
      const chat: ChatMessage[] = exists
        ? state.chat.map((m) => (m.id === event.messageId ? { ...m, status: 'failed', text: m.text ? m.text + '\n\n' + text : text } : m))
        : [...state.chat, { id: 'err-' + state.chat.length, role: 'agent', text, status: 'failed', links: [] }];
      return { ...state, chatBusy: false, chat };
    }
  }
}

export function reducer(state: StoreState, action: StoreAction): StoreState {
  switch (action.type) {
    case 'select':
      return isActive(state.run) ? state : { ...state, selection: action.selection };
    case 'run_requested':
      if (action.selection) {
        return { ...state, selection: action.selection, run: newRun(action.selection), responding: false, responseError: null };
      }
      return { ...state, run: newRun(state.selection), responding: false, responseError: null, announcement: 'Optimizasyon başlatılıyor' };
    case 'run_event': {
      const run = state.run;
      if (!run) return state;
      const id = eventRunId(action.event);
      // Başka (eski) bir optimizasyona ait olayları yok say.
      if (run.context && id !== null && id !== run.context.runId) return state;
      const next = applyRunEvent(run, action.event);
      const settled = action.event.type === 'approval_requested' || action.event.type === 'approval_resolved'
        || action.event.type === 'run_failed';
      return {
        ...state,
        run: next.run,
        responding: settled ? false : state.responding,
        responseError: settled ? null : state.responseError,
        announcement: next.announcement ?? state.announcement,
      };
    }
    case 'respond_started':
      return { ...state, responding: true, responseError: null };
    case 'respond_failed':
      return { ...state, responding: false, responseError: action.message };
    case 'chat_asked':
      return {
        ...state,
        chatBusy: true,
        chat: [...state.chat, { id: action.id, role: 'user', text: action.question, status: 'done', links: [] }],
      };
    case 'chat_event':
      return applyChatEvent(state, action.event);
  }
}
