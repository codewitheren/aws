import { useState, type FormEvent } from 'react';
import { Link } from '../router/router';
import { useRunStore } from '../run/RunProvider';
import { RichText } from './RichText';

/** "Agent'a sor": yanıtlar parça parça akar; mock modda hazır yanıtlar kullanılır. */
export function ChatPanel({ suggestions }: { suggestions: string[] }) {
  const { state, actions } = useRunStore();
  const [text, setText] = useState('');
  const busy = state.chatBusy;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!text.trim() || busy) return;
    actions.ask(text);
    setText('');
  };

  return (
    <aside className="card" aria-labelledby="c1" style={{ flex: '1 1 320px' }}>
      <div className="stack-s">
        <h2 id="c1">Agent'a sor</h2>
        <span className="sub">Bu koşunun verisi üzerinden yanıtlar.</span>
      </div>
      {state.chat.length === 0 && (
        <p className="sub">Bir depo ya da uyarı hakkında sorun. Aşağıdaki sorulardan biriyle başlayabilirsiniz.</p>
      )}
      <ol className="chat-log" role="log" aria-live="polite" aria-busy={busy} aria-label="Sohbet">
          {state.chat.map((m) =>
            m.role === 'user' ? (
              <li key={m.id} className="msg-user"><span className="sr-only">Siz: </span>{m.text}</li>
            ) : (
              <li key={m.id} className={'msg-agent' + (m.status === 'failed' ? ' failed' : '')}>
                <span className="sr-only">Agent: </span>
                {m.text ? <RichText text={m.text} /> : <p className="sub">Yanıt hazırlanıyor…</p>}
                {m.links.filter((l) => l.route.startsWith('/')).map((l) => (
                  <Link key={l.route} to={l.route}>{l.label}</Link>
                ))}
              </li>
            ),
          )}
      </ol>
      <div className="inline" style={{ gap: 6 }}>
        {suggestions.map((s) => (
          <button key={s} type="button" className="btn chip-btn" disabled={busy} onClick={() => actions.ask(s)}>{s}</button>
        ))}
      </div>
      <form className="ask" onSubmit={submit}>
        <label htmlFor="soru" className="sr-only">Sorunuz</label>
        <input id="soru" className="input" type="text" placeholder="Bir depo ya da uyarı sorun" value={text} onChange={(e) => setText(e.target.value)} />
        <button type="submit" className="btn btn-p" disabled={busy || !text.trim()}>Sor</button>
      </form>
    </aside>
  );
}
