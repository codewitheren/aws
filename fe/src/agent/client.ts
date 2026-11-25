import type { AskCommand, ChatEvent, RespondToApprovalCommand, RunEvent, StartRunCommand } from './types';

/** Süren bir akışı (koşu ya da sohbet yanıtı) durdurur; sonrasında olay gelmez. */
export interface StreamHandle {
  abort(): void;
}

/**
 * Arayüzün agent ile konuştuğu tek arayüz. Mock ve HTTP uygulamaları birbirinin yerine geçer.
 * Taşıma hataları istisna olarak değil `run_failed` / `chat_failed` olayı olarak bildirilir.
 */
export interface AgentClient {
  readonly mode: 'mock' | 'http';
  /** Koşuyu başlatır; olaylar `onEvent` ile akar. İlk olay `run_started`'dır. */
  startRun(command: StartRunCommand, onEvent: (event: RunEvent) => void): StreamHandle;
  /** Bekleyen onaya yanıt verir. Sonuç, koşu akışında `approval_resolved` olarak gelir. */
  respondToApproval(command: RespondToApprovalCommand): Promise<void>;
  /** "Agent'a sor": yanıt parça parça `chat_delta` olarak akar. */
  ask(command: AskCommand, onEvent: (event: ChatEvent) => void): StreamHandle;
}
