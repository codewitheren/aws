import { useMemo, useState } from 'react';
import { dataApi } from '../data/api';
import type { MerkezOption } from '../data/types';
import { formatDate, formatDateWithWeekday, formatTime, nf } from '../lib/format';
import { useResource } from '../lib/useResource';
import { RunStatusPanel } from '../components/RunStatusPanel';
import { Loadable } from '../components/Loadable';
import { useRunStore } from '../run/RunProvider';
import { isActive } from '../run/reducer';
import { runMatches } from '../run/selectors';

export function KosuPage() {
  const options = useResource(dataApi.getRunOptions, 'run-options');
  return (
    <div className="stack" data-focus-scope="kosu">
      <header className="page-head">
        <h1 tabIndex={-1}>Optimizasyon başlat</h1>
        <p className="sub">Merkez depo ve transfer tipini seçin. Sistem bugünün Forecast önerisini alır, kesim motorunu çalıştırır, agent sonucu kontrol eder.</p>
      </header>
      <Loadable resource={options}>{(merkezler) => <KosuForm merkezler={merkezler} />}</Loadable>
    </div>
  );
}

function KosuForm({ merkezler }: { merkezler: MerkezOption[] }) {
  const { state, actions } = useRunStore();
  const { selection, run } = state;
  const today = useMemo(() => new Date(), []);
  const [businessDay, setBusinessDay] = useState(() => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Istanbul' }).format(today));
  const dayValid = /^\d{4}-\d{2}-\d{2}$/.test(businessDay);
  const active = isActive(run);
  const merkez = merkezler.find((m) => m.ad === selection.merkez) ?? merkezler[0];
  const tip = merkez.tipler.find((t) => t.id === selection.transferType) ?? merkez.tipler[0];
  const sameAsRun = runMatches(run, selection.merkez, selection.transferType);

  const pickMerkez = (m: MerkezOption) => {
    const first = m.tipler.find((t) => t.relexAt || t.relexNote) ?? m.tipler[0];
    actions.select({ merkez: m.ad, transferType: first.id });
  };

  const buttonText = run?.status === 'awaiting_approval' ? 'Onay bekleniyor'
    : active ? 'Hesaplanıyor…'
    : sameAsRun && run?.status === 'completed' ? 'Yeniden hesapla'
    : sameAsRun && run?.status === 'failed' ? 'Yeniden dene'
    : 'Hesapla';

  const typeLabel = (merkezAd: string, tipId: string) =>
    merkezler.find((m) => m.ad === merkezAd)?.tipler.find((t) => t.id === tipId)?.ad ?? tipId;
  const runLabel = run
    ? `${run.request.merkez} · ${typeLabel(run.request.merkez, run.request.transferType)}`
    : `${merkez.ad} · ${tip.ad}`;
  const runDate = run?.context ? formatDate(new Date(run.context.runDate + 'T00:00:00')) : formatDate(today);

  const ranToday = (merkezAd: string, tipId: string, fallback: string | null) => {
    if (run?.status === 'completed' && run.summary && run.request.merkez === merkezAd && run.request.transferType === tipId) {
      return formatTime(new Date(run.summary.finishedAt));
    }
    return fallback;
  };

  return (
    <div className="cols">
      <div className="stack" style={{ flex: '3 1 480px' }}>
        <section className="card" aria-labelledby="s1">
          <h2 id="s1">1 · Merkez depo</h2>
          <div className="grid-auto" style={{ gap: 10, ['--min' as string]: '150px' }}>
            {merkezler.map((m) => (
              <button key={m.ad} type="button" className="pick pick-merkez" aria-pressed={m.ad === merkez.ad}
                disabled={active && m.ad !== merkez.ad} onClick={() => pickMerkez(m)}>
                <strong>{m.ad}</strong>
                <span className="sub">{m.tipler.length} transfer tipi</span>
              </button>
            ))}
          </div>
        </section>

        <section className="card" aria-labelledby="s2">
          <div className="split">
            <h2 id="s2">2 · Transfer tipi</h2>
            <span className="sub">{merkez.ad} için veritabanındaki tipler</span>
          </div>
          <div className="stack-m">
            {merkez.tipler.map((t) => {
              const ran = ranToday(merkez.ad, t.id, t.ranAt);
              return (
                <button key={t.id} type="button" className="pick pick-tip" aria-pressed={t.id === tip.id}
                  disabled={!(t.relexAt || t.relexNote) || (active && t.id !== tip.id)}
                  onClick={() => actions.select({ merkez: merkez.ad, transferType: t.id })}>
                  <span className="tip-name">{t.ad}</span>
                  <span style={{ flex: '1 1 150px' }}><span className="lbl">Forecast girdisi</span><span>{t.relexAt ? 'Geldi · ' + t.relexAt : t.relexNote ?? 'Bekleniyor'}</span></span>
                  <span style={{ flex: '1 1 110px' }}><span className="lbl">Öneri satırı</span><span>{t.lineCount !== null ? nf(t.lineCount) : '—'}</span></span>
                  <span style={{ flex: '1 1 150px' }}><span className="lbl">Bugün</span><span>{ran ? ran + "'de çalıştırıldı" : 'Çalıştırılmadı'}</span></span>
                </button>
              );
            })}
          </div>
          {merkez.note && <p className="sub">{merkez.note}</p>}
        </section>

        <section className="card" aria-labelledby="s3">
          <h2 id="s3">3 · Çalıştır</h2>
          <div className="split" style={{ alignItems: 'center', gap: 16 }}>
            <label className="kv">
              <span className="lbl">İş tarihi</span>
              <input className="input" type="date" value={businessDay} required disabled={active}
                onChange={(e) => setBusinessDay(e.target.value)} aria-describedby="day-note" />
              {dayValid && <span className="sub">{formatDateWithWeekday(new Date(businessDay + 'T12:00:00'))}</span>}
            </label>
            <button type="button" className="btn btn-p" style={{ minWidth: 160 }} disabled={active || !dayValid || !(tip.relexAt || tip.relexNote)} onClick={() => actions.startRun(businessDay)}>
              {buttonText}
            </button>
          </div>
          {run && !active && !sameAsRun && (
            <p className="sub" role="note">Son optimizasyon {runLabel} içindi. Yeni seçiminiz için Hesapla'ya basın.</p>
          )}
          <p className="sub" id="day-note">İş tarihi sayım, teslimat ve girdi güncelliği kontrollerinde kullanılır; Forecast ve kapasite girdileri bu güne ait olmalıdır. Girdiler her zaman Google Sheet'in güncel halinden okunur.</p>
          <p className="sub"> Agent aykırı bir PL bulursa ne bulduğunu ve ne önerdiğini anlatır, onayınızı ister; onayladıklarınız yalnızca bu optimizasyonun çıktısına uygulanır. Forecast'a ya da başka bir sisteme yazmaz.</p>
        </section>
      </div>

      <RunStatusPanel
        run={run}
        title={`${runLabel} · ${runDate}`}
        announcement={state.announcement}
        responding={state.responding}
        responseError={state.responseError}
        onRespond={(r) => void actions.respond(r)}
      />
    </div>
  );
}
