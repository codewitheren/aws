import { dataApi } from '../data/api';
import { alertsCsv, anomalyCsv } from '../data/exports';
import type { AnomalyData, ResultsData } from '../data/types';
import { nf, pct } from '../lib/format';
import { useResource } from '../lib/useResource';
import { AlertList } from '../components/AlertList';
import { ChatPanel } from '../components/ChatPanel';
import { FilesCard } from '../components/FilesCard';
import { Loadable } from '../components/Loadable';
import { ResultsHeader } from '../components/ResultsHeader';
import { Link, paths } from '../router/router';
import { useRunStore } from '../run/RunProvider';
import { isActive, type RunState } from '../run/reducer';
import { correctionSentence, runMatches } from '../run/selectors';

export function SonuclarPage() {
  const res = useResource(() => Promise.all([dataApi.getResults(), dataApi.getAnomalies()]), 'results');
  return (
    <div className="stack">
      <Loadable resource={res}>{([data, anomalies]) => <Summary data={data} anomalies={anomalies} />}</Loadable>
    </div>
  );
}

/** Bu oturumdaki koşunun, gösterilen örnek sonuçla ilişkisini açıkça söyler. */
function RunNote({ run, data }: { run: RunState | null; data: ResultsData }) {
  const ctx = data.context;
  if (!run) {
    return <p style={{ fontSize: 13 }}>Örnek sonuç gösteriliyor; bu oturumda henüz koşu yapılmadı.</p>;
  }
  if (isActive(run)) {
    return <p style={{ fontSize: 13 }}>Süren bir koşu var. <Link to={paths.kosu}>Koşu durumunu açın</Link>.</p>;
  }
  if (!runMatches(run, ctx.merkez, ctx.transferType)) {
    return (
      <p style={{ fontSize: 13 }}>
        Son koşunuz {run.request.merkez} için yapıldı; bu ekrandaki rakamlar {ctx.merkez} · {ctx.transferTypeLabel} örnek koşusuna aittir.
      </p>
    );
  }
  if (run.status === 'completed') {
    return (
      <p style={{ fontSize: 13 }}>
        Bu koşuda {run.resolutions.length > 0 ? correctionSentence(run.resolutions) : 'agent düzeltme önermedi.'} Düzeltmeler yalnızca bu koşunun çıktısına uygulandı; Relex'te kayıt değişmedi.
      </p>
    );
  }
  return <p style={{ fontSize: 13 }}>Son koşu tamamlanamadı. <Link to={paths.kosu}>Koşu ekranına dönün</Link>.</p>;
}

function Summary({ data, anomalies }: { data: ResultsData; anomalies: AnomalyData }) {
  const { state } = useRunStore();
  const run = state.run;
  const sampleRun = runMatches(run, data.context.merkez, data.context.transferType) ? run : null;
  const limitPct = Math.round((data.lineLimit.used / data.lineLimit.limit) * 100);
  const points = (n: number) => (n > 0 ? '+' : '') + nf(n, 1) + ' puan';

  return (
    <>
      <ResultsHeader context={data.context} active="ozet" anomalyTotal={data.anomalyTotal}
        action={<Link className="btn" to={paths.kosu}>Yeni koşu</Link>} />

      <section aria-label="Agent sonucu" className="hero">
        <span className="lbl">Agent sonucu</span>
        <p className="hero-text">{data.headline}</p>
        <RunNote run={run} data={data} />
      </section>

      <section aria-label="Göstergeler" className="grid-auto">
        <div className="card kpi"><span className="lbl">Önerilen satır</span><span className="big">{nf(data.suggestedLines)}</span><span className="sub">Relex önerisi</span></div>
        <div className="card kpi"><span className="lbl">Gönderilen satır</span><span className="big">{nf(data.sentLines)}</span><span className="sub">Kesim sonrası</span></div>
        <div className="card kpi"><span className="lbl">C/P</span><span className="big">{pct(data.cpPct, 1)}</span><span className="sub">Gönderilen / önerilen satır</span></div>
        <div className="card kpi">
          <span className="lbl">Kısma oranı</span><span className="big">{pct(data.cutPct, 1)}</span>
          <span className="sub">Düne göre <strong style={{ color: 'var(--text)' }}>{points(data.cutDelta.vsYesterday)}</strong></span>
          <span className="sub">Geçen pazartesiye göre <strong style={{ color: 'var(--text)' }}>{points(data.cutDelta.vsLastWeekday)}</strong></span>
        </div>
        <div className="card kpi">
          <span className="lbl">Merkez satır limiti kullanımı</span><span className="big">{pct(limitPct)}</span>
          <div className="track" role="img" aria-label={`Limitin yüzde ${limitPct}'ü kullanıldı`}>
            <div style={{ width: Math.min(limitPct, 100) + '%', background: limitPct >= 90 ? 'var(--uyari-mark)' : 'var(--brand)' }} />
          </div>
          <span className="sub">{nf(data.lineLimit.used)} / {nf(data.lineLimit.limit)} created satır</span>
        </div>
      </section>

      <div className="cols">
        <div className="stack" style={{ flex: '2 1 560px' }}>
          <AlertList alerts={data.alerts} />
          <FilesCard
            runId={run?.status === 'completed' ? run.context?.runId ?? null : null}
            sentLines={data.sentLines}
            anomalyFile={anomalyCsv(anomalies, sampleRun?.resolutions ?? [])}
            alertsFile={alertsCsv(data)}
          />
        </div>
        <ChatPanel suggestions={data.chatSuggestions} />
      </div>
    </>
  );
}
