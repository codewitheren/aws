/**
 * Gerçek agent backend'i için istemci iskeleti. Sözleşme README'de belgelidir.
 * DİKKAT: Bu dosya tür denetiminden geçer ama gerçek bir backend'e karşı test EDİLMEMİŞTİR.
 */
import type { AgentClient, StreamHandle } from './client';
import { readEventStream } from './sse';
import { isChatEvent, isRunEvent, type AgentError, type ChatEvent, type RunEvent } from './types';

function toError(err: unknown, fallback: string): AgentError {
  return { code: 'network_error', message: err instanceof Error ? err.message || fallback : fallback };
}

function parseJson(data: string): unknown {
  try {
    return JSON.parse(data) as unknown;
  } catch {
    return null;
  }
}

/** POST gövdesiyle bir SSE akışı açar; her geçerli olayı `onEvent`'e iletir. */
function postStream<E>(
  url: string,
  body: unknown,
  guard: (value: unknown) => value is E,
  onEvent: (event: E) => void,
  onFailure: (error: AgentError) => void,
  onClose: () => void,
): StreamHandle {
  const controller = new AbortController();
  (async () => {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!res.ok || !res.body) {
      onFailure({ code: `http_${res.status}`, message: `Agent servisi yanıt vermedi (HTTP ${res.status}).` });
      return;
    }
    await readEventStream(res.body, (data) => {
      const value = parseJson(data);
      if (guard(value)) onEvent(value);
    });
    onClose();
  })().catch((err: unknown) => {
    if (!controller.signal.aborted) onFailure(toError(err, 'Agent servisine ulaşılamadı.'));
  });
  return { abort: () => controller.abort() };
}

export function createHttpAgentClient(baseUrl: string): AgentClient {
  return {
    mode: 'http',

    startRun(command, onEvent: (event: RunEvent) => void): StreamHandle {
      let runId: string | null = null;
      let finished = false;
      return postStream(
        `${baseUrl}/runs`,
        command,
        isRunEvent,
        (event) => {
          if (event.type === 'run_started') runId = event.run.runId;
          if (event.type === 'run_completed' || event.type === 'run_failed') finished = true;
          onEvent(event);
        },
        (error) => {
          if (!finished) onEvent({ type: 'run_failed', runId, error });
        },
        () => {
          if (!finished) onEvent({ type: 'run_failed', runId, error: { code: 'stream_closed', message: 'Agent bağlantısı koşu bitmeden kapandı.' } });
        },
      );
    },

    async respondToApproval(command) {
      const res = await fetch(
        `${baseUrl}/runs/${encodeURIComponent(command.runId)}/approvals/${encodeURIComponent(command.approvalId)}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ response: command.response }),
        },
      );
      if (!res.ok) throw new Error(`Yanıt gönderilemedi (HTTP ${res.status}).`);
    },

    ask(command, onEvent: (event: ChatEvent) => void): StreamHandle {
      let messageId: string | null = null;
      let finished = false;
      return postStream(
        `${baseUrl}/chat`,
        { question: command.question, runId: command.runId },
        isChatEvent,
        (event) => {
          if (event.type === 'chat_message_started') messageId = event.messageId;
          if (event.type === 'chat_message_completed' || event.type === 'chat_failed') finished = true;
          onEvent(event);
        },
        (error) => {
          if (!finished) onEvent({ type: 'chat_failed', messageId, error });
        },
        () => {
          if (!finished) onEvent({ type: 'chat_failed', messageId, error: { code: 'stream_closed', message: 'Yanıt tamamlanmadan bağlantı kapandı.' } });
        },
      );
    },
  };
}
