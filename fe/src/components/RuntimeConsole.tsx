import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import type { ActivityKind } from '../agent/types';
import { nf } from '../lib/format';
import type { RunState, RunStatus } from '../run/reducer';

const labels: Record<ActivityKind, string> = {
  command: 'KOMUT',
  data: 'VERİ',
  check: 'KONTROL',
  decision: 'KARAR',
  output: 'ÇIKTI',
  error: 'HATA',
};

const statuses: Record<RunStatus | 'idle', string> = {
  idle: 'Beklemede',
  starting: 'Bağlanıyor',
  running: 'Çalışıyor',
  awaiting_approval: 'Onay bekliyor',
  completed: 'Tamamlandı',
  failed: 'Durdu',
};

const clock = new Intl.DateTimeFormat('tr-TR', {
  timeZone: 'Europe/Istanbul', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
});

export function RuntimeConsole({ run, mock, responding }: { run: RunState | null; mock: boolean; responding: boolean }) {
  const logRef = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const [atEnd, setAtEnd] = useState(true);
  const status = run?.status ?? 'idle';
  const running = responding || status === 'starting' || status === 'running';
  const activity = run?.activity ?? [];

  const trackScroll = () => {
    const log = logRef.current;
    if (!log) return;
    following.current = log.scrollHeight - log.clientHeight - log.scrollTop < 24;
    setAtEnd(following.current);
  };

  const jumpToEnd = useCallback(() => {
    const log = logRef.current;
    if (!log) return;
    log.scrollTop = log.scrollHeight;
    following.current = true;
    setAtEnd(true);
  }, []);

  useLayoutEffect(() => {
    if (following.current) jumpToEnd();
  }, [activity.length, jumpToEnd]);

  useLayoutEffect(() => {
    const log = logRef.current;
    if (!log) return;
    const observer = new ResizeObserver(() => {
      if (following.current) jumpToEnd();
    });
    observer.observe(log);
    return () => observer.disconnect();
  }, [jumpToEnd]);

  return (
    <div className="runtime-console" data-state={status} data-running={running}>
      <div className="runtime-head">
        <div className="runtime-identity">
          <span className="runtime-symbol" aria-hidden="true">&gt;_</span>
          <div className="stack-s">
            <strong>Runtime Agent</strong>
            <span>{mock ? 'Örnek akış' : 'AWS Bedrock AgentCore'}</span>
          </div>
        </div>
        <span className="runtime-state"><i aria-hidden="true" />{responding ? 'Karar işleniyor' : statuses[status]}</span>
      </div>
      <div className="runtime-signal" aria-hidden="true" />
      <div className="runtime-log" ref={logRef} onScroll={trackScroll} tabIndex={0} role="region" aria-label="Koşu günlüğü">
        {activity.length === 0 ? (
          <div className="runtime-empty">
            <span aria-hidden="true">$</span>
            <span>{status === 'starting' || status === 'running'
              ? 'İlk olay bekleniyor…'
              : 'Koşu başladığında komutlar ve sonuçlar burada akacak.'}</span>
          </div>
        ) : (
          <ol className="runtime-events">
            {activity.map((event) => (
              <li className="runtime-event" data-kind={event.kind} key={event.id}>
                <time dateTime={event.at} title="İstanbul saati">{clock.format(new Date(event.at))}</time>
                <span className="runtime-kind">{labels[event.kind]}</span>
                <div className="runtime-event-body">
                  <strong>{event.title}</strong>
                  {event.code && <code>{event.code}</code>}
                  {event.detail && <span>{event.detail}</span>}
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
      <div className="runtime-foot">
        <span>{nf(activity.length)} olay</span>
        {!atEnd && (
          <button type="button" onClick={() => {
            jumpToEnd();
            logRef.current?.focus({ preventScroll: true });
          }}>Son olaya git ↓</button>
        )}
      </div>
    </div>
  );
}
