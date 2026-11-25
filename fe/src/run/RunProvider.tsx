import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, type ReactNode } from 'react';
import type { AgentClient, StreamHandle } from '../agent/client';
import type { ApprovalResponse } from '../agent/types';
import { initialState, reducer, type Selection, type StoreState } from './reducer';

interface RunActions {
  select(selection: Selection): void;
  startRun(): void;
  respond(response: ApprovalResponse): Promise<void>;
  ask(question: string): void;
}

interface RunStore {
  state: StoreState;
  actions: RunActions;
  mode: AgentClient['mode'];
}

const RunContext = createContext<RunStore | null>(null);

/** Optimizasyon ve sohbet durumunun tek kaynağı. Agent olaylarını reducer'a aktarır. */
export function RunProvider({ client, children }: { client: AgentClient; children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const stateRef = useRef(state);
  const runHandle = useRef<StreamHandle | null>(null);
  const chatHandle = useRef<StreamHandle | null>(null);
  const runToken = useRef(0);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => () => {
    runHandle.current?.abort();
    chatHandle.current?.abort();
  }, []);

  // Sayfa yenilenince bu sekmedeki son optimizasyonu geri yükle (yalnızca AgentCore istemcisinde var).
  useEffect(() => {
    if (!client.resume) return;
    const token = ++runToken.current;
    let requested = false;
    const handle = client.resume((event) => {
      if (token !== runToken.current) return;
      if (event.type === 'run_started' && !requested) {
        requested = true;
        dispatch({ type: 'run_requested', selection: { merkez: event.run.merkez, transferType: event.run.transferType } });
      }
      if (requested) dispatch({ type: 'run_event', event });
    });
    runHandle.current = handle;
    return () => handle?.abort();
  }, [client]);

  const select = useCallback((selection: Selection) => dispatch({ type: 'select', selection }), []);

  const startRun = useCallback(() => {
    runHandle.current?.abort();
    const token = ++runToken.current;
    const { selection } = stateRef.current;
    dispatch({ type: 'run_requested' });
    runHandle.current = client.startRun(
      { type: 'start_run', merkez: selection.merkez, transferType: selection.transferType },
      (event) => {
        if (token === runToken.current) dispatch({ type: 'run_event', event });
      },
    );
  }, [client]);

  const respond = useCallback(async (response: ApprovalResponse) => {
    const run = stateRef.current.run;
    if (!run?.context || !run.pendingApproval || stateRef.current.responding) return;
    dispatch({ type: 'respond_started' });
    stateRef.current = { ...stateRef.current, responding: true };
    try {
      await client.respondToApproval({
        type: 'respond_to_approval',
        runId: run.context.runId,
        approvalId: run.pendingApproval.approvalId,
        response,
      });
    } catch (err) {
      dispatch({ type: 'respond_failed', message: err instanceof Error ? err.message : 'Yanıt gönderilemedi.' });
    }
  }, [client]);

  const ask = useCallback((question: string) => {
    const q = question.trim();
    if (!q || stateRef.current.chatBusy) return;
    chatHandle.current?.abort();
    dispatch({ type: 'chat_asked', id: 'q-' + Date.now().toString(36), question: q });
    // Aynı tıklamada ikinci soruyu engellemek için ref'i hemen güncelle.
    stateRef.current = { ...stateRef.current, chatBusy: true };
    chatHandle.current = client.ask(
      { type: 'ask', question: q, runId: stateRef.current.run?.context?.runId ?? null },
      (event) => dispatch({ type: 'chat_event', event }),
    );
  }, [client]);

  const actions = useMemo(() => ({ select, startRun, respond, ask }), [select, startRun, respond, ask]);
  const value = useMemo(() => ({ state, actions, mode: client.mode }), [state, actions, client.mode]);
  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useRunStore(): RunStore {
  const ctx = useContext(RunContext);
  if (!ctx) throw new Error('useRunStore yalnızca RunProvider içinde kullanılabilir.');
  return ctx;
}
