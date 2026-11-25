import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import type { ApprovalRequest, ApprovalResponse } from '../agent/types';

interface Props {
  approval: ApprovalRequest;
  responding: boolean;
  error: string | null;
  onRespond: (response: ApprovalResponse) => void;
}

function Field({ label, children }: { label: string; children: string }) {
  return (
    <div className="stack-s">
      <span className="lbl">{label}</span>
      <span>{children}</span>
    </div>
  );
}

/** Agent'ın tek bir bulgu için onay istediği kart. Ebeveyn `key={approvalId}` ile yeniden kurar. */
export function ApprovalCard({ approval, responding, error, onRespond }: Props) {
  const [text, setText] = useState('');
  const titleRef = useRef<HTMLHeadingElement>(null);
  const inputId = useId();

  useEffect(() => {
    // Yeni öneri geldiğinde odağı başlığa taşı; kullanıcı başka bir bölgedeyse dokunma.
    const active = document.activeElement;
    if (!active || active === document.body || active.closest('[data-focus-scope="kosu"]')) {
      titleRef.current?.focus();
    }
  }, []);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (t) onRespond({ kind: 'instruction', text: t });
  };

  return (
    <section className="approval" aria-labelledby={inputId + '-t'}>
      <div className="split">
        <span className="lbl brand">Agent önerisi</span>
        <span className="sub">{approval.index} / {approval.total}</span>
      </div>
      <h3 id={inputId + '-t'} ref={titleRef} tabIndex={-1} className="approval-title" style={{ margin: 0 }}>
        {approval.title}
      </h3>
      <Field label="Ne buldum">{approval.found}</Field>
      <Field label="Önerim">{approval.proposal}</Field>
      <Field label="Nasıl uygularım">{approval.howApplied}</Field>
      <Field label="Etkisi">{approval.impact}</Field>
      <p style={{ fontWeight: 600 }}>{approval.question}</p>
      <div className="stack-m" style={{ gap: 8 }}>
        {approval.options.map((o) => (
          <button
            key={o.id}
            type="button"
            className={'btn' + (o.id === 'accept' ? ' btn-p' : '')}
            disabled={responding}
            onClick={() => onRespond({ kind: o.id })}
          >
            {o.label}
          </button>
        ))}
      </div>
      {approval.instruction.allowed && (
        <form className="stack-s" style={{ gap: 4 }} onSubmit={submit}>
          <label className="lbl" htmlFor={inputId}>Ya da agent'a ne yapmasını istediğinizi yazın</label>
          <div className="instruction">
            <input
              id={inputId}
              className="input"
              type="text"
              value={text}
              placeholder={approval.instruction.placeholder}
              onChange={(e) => setText(e.target.value)}
              disabled={responding}
            />
            <button type="submit" className="btn" disabled={responding || text.trim() === ''}>Gönder</button>
          </div>
        </form>
      )}
      {responding && <p className="sub">Yanıtınız agent'a iletiliyor…</p>}
      {error && <p role="alert" style={{ color: 'var(--krit)' }}>{error}</p>}
    </section>
  );
}
