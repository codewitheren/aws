import {
  type AgentError, type ApprovalRequest, type ApprovalResolution, type ChatEvent, type ChatLink,
  type RunActivity, type RunContext, type RunEvent, type RunSummary, type TransferTypeId,
} from '../agent/types';
import { config } from '../config';

export type RunStatus = 'starting' | 'running' | 'awaiting_approval' | 'completed' | 'failed';

export interface Selection {
  merkez: string;
  transferType: TransferTypeId;
}

export interface RunState {
  status: RunStatus;
  request: Selection;
  context: RunContext | null;
  activity: RunActivity[];
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
  | { type: 'run_event'; event: RunEvent; at: string }
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

function newRun(request: Selection): RunState {
  return {
    status: 'starting',
    request,
    context: null,
    activity: [],
    pendingApproval: null,
    resolutions: [],
    summary: null,
    error: null,
  };
}

function eventRunId(event: RunEvent): string | null {
  return event.type === 'run_started' ? event.run.runId : event.runId;
}

function applyRunEvent(run: RunState, event: RunEvent, at: string): { run: RunState; announcement?: string } {
  const log = (title: string, detail?: string, kind: RunActivity['kind'] = 'decision'): RunActivity[] =>
    [...run.activity, { id: 'ui-' + run.activity.length, at, kind, title, detail }];
  switch (event.type) {
    case 'run_started':
      return { run: { ...run, status: 'running', context: event.run } };
    case 'run_activity':
      if (run.activity.some((item) => item.id === event.activity.id)) return { run };
      return { run: { ...run, activity: [...run.activity, event.activity] } };
    case 'approval_requested': {
      const a = event.approval;
      return {
        run: { ...run, status: 'awaiting_approval', pendingApproval: a,
          activity: log(a.findingKey === 'official' ? 'Resmi koşu onayı bekleniyor' : a.title, a.found) },
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
          activity: log(r.title, r.summary),
        },
        announcement: `${r.title}: ${r.summary}`,
      };
    }
    case 'review_reset':
      return { run: { ...run, resolutions: [] } };
    case 'run_completed':
      return {
        run: { ...run, status: 'completed', pendingApproval: null, summary: event.summary },
        announcement: event.summary.headline,
      };
    case 'run_failed':
      return {
        run: { ...run, status: 'failed', pendingApproval: null, error: event.error,
          activity: log(event.error.code === 'no_data' ? 'Depo verisi bulunamadı' : 'Koşu durdu', undefined, 'error') },
        announcement: (event.error.code === 'no_data' ? '' : 'Optimizasyon tamamlanamadı: ') + event.error.message,
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
        chat: state.chat.map((m) => (m.id === event.messageId ? { ...m, text: event.replace ? event.delta : m.text + event.delta } : m)),
      };
    case 'chat_message_completed':
      return {
        ...state,
        chatBusy: false,
        chat: state.chat.map((m) => (m.id === event.messageId ? { ...m, status: 'done', text: event.text ?? m.text, links: event.links } : m)),
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
      const next = applyRunEvent(run, action.event, action.at);
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
