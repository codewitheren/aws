import { useState, useSyncExternalStore, type FormEvent, type ReactNode } from 'react';
import { auth, login, logout } from '../agent/agentcore';

export { logout };

/** AgentCore modunda Cognito girişi; giriş yapılmadan uygulama (ve koşu durumu) kurulmaz. */
export function LoginGate({ children }: { children: ReactNode }) {
  const user = useSyncExternalStore(auth.subscribe, auth.user);
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (user) return <>{children}</>;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(name.trim(), password);
      setPassword('');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="main" style={{ maxWidth: 420, margin: '10vh auto' }}>
      <div className="stack">
        <header className="page-head">
          <h1>Transfer Kontrol</h1>
          <p className="sub">Çalışma alanına giriş</p>
        </header>
        <form className="card stack-m" onSubmit={(e) => void submit(e)}>
          <label className="stack-s"><span className="lbl">Kullanıcı adı</span>
            <input className="input" autoComplete="username" required value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="stack-s"><span className="lbl">Parola</span>
            <input className="input" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          <button className="btn btn-p" disabled={busy}>{busy ? 'Giriş yapılıyor…' : 'Giriş yap'}</button>
          {error && <p role="alert" style={{ color: 'var(--krit)' }}>{error}</p>}
        </form>
      </div>
    </main>
  );
}
