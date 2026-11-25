import { dataApi } from '../data/api';
import { anomalyCsv } from '../data/exports';
import { downloadRunFile } from '../agent/agentcore';
import type { AnomalyCard, AnomalyData } from '../data/types';
import { downloadBlob, toCsvBlob } from '../lib/download';
import { nf } from '../lib/format';
import { useResource } from '../lib/useResource';
import { AnomalyDotChart } from '../charts/AnomalyDotChart';
import { Legend } from '../components/Legend';
import { Loadable } from '../components/Loadable';
import { ResultsHeader } from '../components/ResultsHeader';
import { Link, paths } from '../router/router';
import { useRunStore } from '../run/RunProvider';
import { runMatches } from '../run/selectors';

export function AnomaliPage() {
  const res = useResource(dataApi.getAnomalies, 'anomalies');
  return (
    <div className="stack">
      <Loadable resource={res}>{(data) => <Anomalies data={data} />}</Loadable>
    </div>
  );
}

const cell = (v: string | number | null) => (typeof v === 'number' ? nf(v, v % 1 ? 1 : 0) : v ?? '');

/** Canlı optimizasyon: motorun öneri kontrol kartları, her biri kendi tablosuyla. */
function LiveAnomalies({ data, cards }: { data: AnomalyData; cards: AnomalyCard[] }) {
  const download = () => void downloadRunFile('anomaliler.csv').catch(() => undefined);
  return (
    <>
      <ResultsHeader context={data.context} active="anomaliler" anomalyTotal={data.total}
        action={<button type="button" className="btn" onClick={download}>Anomali listesini indir (.csv)</button>} />
      <section aria-label="Anomali türleri" className="grid-auto" style={{ ['--min' as string]: '240px' }}>
        {data.categories.map((c) => (
          <div className="card kpi" key={c.label}>
            <span className="lbl">{c.label}</span>
            <span className="big">{nf(c.count)} satır</span>
          </div>
        ))}
        {cards.length === 0 && <p className="sub">Bu optimizasyonda öneri kontrolü bulgusu yok.</p>}
      </section>
      {cards.map((c, i) => {
        const depot = c.columns.indexOf('Depo');
        return (
          <section className="card" key={c.title} aria-labelledby={'ac' + i}>
            <div className="stack-s">
              <h2 id={'ac' + i}>{c.title}</h2>
              {c.subtitle && <span className="sub">{c.subtitle}</span>}
            </div>
            <div className="tw">
              <table className="t">
                <thead><tr>{c.columns.map((h) => <th scope="col" key={h}>{h}</th>)}</tr></thead>
                <tbody>
                  {c.rows.slice(0, 200).map((r, j) => (
                    <tr key={j}>
                      {r.map((v, k) => (
                        <td key={k} className={typeof v === 'number' ? 'n' : undefined}>
                          {k === depot && v ? <Link to={paths.depo(String(v))}>{String(v)}</Link> : cell(v)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {c.rows.length > 200 && <p className="sub">İlk 200 satır gösteriliyor; tamamı anomali CSV'sinde.</p>}
          </section>
        );
      })}
    </>
  );
}

function Anomalies({ data }: { data: AnomalyData }) {
  if (data.cards) return <LiveAnomalies data={data} cards={data.cards} />;
  return <SampleAnomalies data={data} />;
}

function SampleAnomalies({ data }: { data: AnomalyData }) {
  const { state } = useRunStore();
  const resolutions = runMatches(state.run, data.context.merkez, data.context.transferType) ? state.run?.resolutions ?? [] : [];
  const download = () => {
    const f = anomalyCsv(data, resolutions);
    downloadBlob(f.filename, toCsvBlob(f.header, f.rows));
  };
  const rows = data.outliers.slice().sort((a, b) => b.value - a.value);

  return (
    <>
      <ResultsHeader context={data.context} active="anomaliler" anomalyTotal={data.total}
        action={<button type="button" className="btn" onClick={download}>Anomali listesini indir (.csv)</button>} />

      <section aria-label="Anomali türleri" className="grid-auto" style={{ ['--min' as string]: '240px' }}>
        {data.categories.map((c) => (
          <div className="card kpi" key={c.label}>
            <span className="lbl">{c.label}</span>
            <span className="big">{nf(c.count)} satır</span>
            <span className="sub">{c.description}</span>
          </div>
        ))}
      </section>

      <section className="card" aria-labelledby="a1">
        <div className="split-end">
          <div className="stack-s">
            <h2 id="a1">{data.product}: depoların stok + açık + öneri dağılımı</h2>
            <span className="sub">Her nokta bir depo, küçükten büyüğe sıralı.</span>
          </div>
          <div className="stack-s" style={{ gap: 4 }}>
            <label className="lbl" htmlFor="urun">Ürün</label>
            <select id="urun" className="input" defaultValue={data.product}>
              <option>{data.product}</option>
            </select>
          </div>
        </div>
        <AnomalyDotChart data={data} />
        <Legend items={[
          { label: 'Sınır içinde', swatch: { background: 'var(--brand)', opacity: 0.5, borderRadius: '50%' } },
          { label: 'Üst sınırı aşan depo', swatch: { background: 'var(--uyari-mark)', borderRadius: '50%' } },
        ]} />
      </section>

      <section className="card" aria-labelledby="a2">
        <h2 id="a2">Aykırı depolar: {data.product}</h2>
        <div className="tw">
          <table className="t" style={{ minWidth: 680 }}>
            <thead>
              <tr><th scope="col">Depo</th><th scope="col" className="n">Stok + açık + öneri</th><th scope="col" className="n">Medyan</th><th scope="col" className="n">Medyanın katı</th><th scope="col">Agent notu</th></tr>
            </thead>
            <tbody>
              {rows.map((o) => (
                <tr key={o.depotId}>
                  <th scope="row">
                    <Link to={paths.depo(o.depotId)}>{o.ad}</Link>
                  </th>
                  <td className="n">{nf(o.value)}</td>
                  <td className="n">{nf(data.median)}</td>
                  <td className="n">{nf(o.value / data.median, 1)}×</td>
                  <td>{o.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
