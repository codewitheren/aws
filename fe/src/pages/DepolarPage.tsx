import { useState } from 'react';
import { dataApi } from '../data/api';
import type { DepotDetail, DepotsData } from '../data/types';
import { nf, pct } from '../lib/format';
import { useResource } from '../lib/useResource';
import { DepotScatter } from '../charts/DepotScatter';
import { LevelChip } from '../components/Chip';
import { Legend } from '../components/Legend';
import { Loadable } from '../components/Loadable';
import { Link, paths } from '../router/router';

async function load(): Promise<[DepotsData, DepotDetail | null]> {
  const depots = await dataApi.getDepots();
  const featured = await dataApi.getDepotDetail(depots.featuredDepotId);
  return [depots, featured.detail];
}

export function DepolarPage() {
  const res = useResource(load, 'depots');
  return (
    <div className="stack">
      <Loadable resource={res}>{([data, featured]) => <Depots data={data} featured={featured} />}</Loadable>
    </div>
  );
}

const TONE = { kap: 'var(--kap)', kap2: 'var(--kap2)', kap3: 'var(--kap3)' } as const;

function FeaturedCard({ d }: { d: DepotDetail }) {
  const cuts = d.waterfall.cuts;
  const sent = d.waterfall.relexTotal - cuts.reduce((s, c) => s + c.amount, 0);
  const cutText = cuts.map((c) => `${nf(c.amount)} ${c.source}`);
  return (
    <section className="card" aria-labelledby="d3" style={{ flex: '2 1 360px' }}>
      <div className="inline">
        <h2 id="d3">{d.ad}</h2>
        {d.levelNote && <LevelChip level={d.level}>{d.levelNote}</LevelChip>}
        <Link to={paths.depo(d.depotId)} style={{ marginLeft: 'auto', fontWeight: 600, padding: '6px 0' }}>Depo detayı →</Link>
      </div>
      <p>
        Öneri {nf(d.waterfall.relexTotal)}; {cutText.join(', ')} kesildi.
        {d.chronic && ` Son ${d.chronic.of} sipariş gününün ${d.chronic.days}'ünde hacim kısması var.`}
      </p>
      <div className="stackbar" aria-hidden="true">
        <span style={{ flex: sent, background: 'var(--iyi-mark)' }} title={`Gönderilen ${nf(sent)}`} />
        {cuts.map((c) => <span key={c.key} style={{ flex: c.amount, background: TONE[c.tone] }} title={`${c.label} ${nf(c.amount)}`} />)}
      </div>
      <Legend items={[
        { label: `Gönderilen ${nf(sent)}`, swatch: { background: 'var(--iyi-mark)' } },
        ...cuts.map((c) => ({ label: `${c.label} ${nf(c.amount)}`, swatch: { background: TONE[c.tone] } })),
      ]} />
      {d.metrics && (
        <>
          <div className="grid-auto" style={{ ['--min' as string]: '130px' }}>
            {d.metrics.items.map((m) => (
              <div className="kv" key={m.label}><span className="lbl">{m.label}</span><strong>{m.value}</strong></div>
            ))}
          </div>
          <p className="sub">{d.metrics.note}</p>
        </>
      )}
    </section>
  );
}

function Depots({ data, featured }: { data: DepotsData; featured: DepotDetail | null }) {
  const [query, setQuery] = useState('');
  const q = query.trim().toLocaleLowerCase('tr-TR');
  const rows = q ? data.rows.filter((r) => r.ad.toLocaleLowerCase('tr-TR').includes(q)) : data.rows;

  return (
    <>
      <header className="page-head">
        <h1 tabIndex={-1}>Depolar</h1>
        <p className="sub">{data.context.merkez} · {data.context.transferTypeLabel} · {data.context.dateLabel.split(' ')[0]} · her nokta bir cep depo</p>
      </header>

      <section className="card" aria-labelledby="d1">
        <div className="stack-s">
          <h2 id="d1">Doluluk – kısma dağılımı</h2>
          <span className="sub">Sol üstteki depolar dolap boşken kısılıyor: sorun hacim değil, TIR/palet kısıtı.</span>
        </div>
        <DepotScatter points={data.points} highlights={data.highlights} />
        <div className="inline">
          <span className="sub">İşaretli depolar:</span>
          {data.highlights.map((h) => (
            <Link key={h.depotId} className="btn btn-sm" to={paths.depo(h.depotId)}>{h.ad} detayı →</Link>
          ))}
        </div>
      </section>

      <div className="cols">
        <section className="card" aria-labelledby="d2" style={{ flex: '3 1 520px' }}>
          <div className="split-end">
            <div className="stack-s">
              <h2 id="d2">Depo listesi</h2>
              <span className="sub">Kısma oranına göre sıralı. Depo adına ya da "Detay"a tıklayınca depo detayı açılır.</span>
            </div>
            <div className="stack-s" style={{ gap: 4 }}>
              <label className="lbl" htmlFor="ara">Depo ara</label>
              <input id="ara" className="input" type="search" placeholder="Depo adı" value={query} onChange={(e) => setQuery(e.target.value)} />
            </div>
          </div>
          <div className="tw">
            <table className="t" style={{ minWidth: 520 }}>
              <thead>
                <tr><th scope="col">Depo</th><th scope="col">Seviye</th><th scope="col" className="n">Kısma</th><th scope="col">Ana neden</th><th scope="col"><span className="sr-only">Bağlantı</span></th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.depotId}>
                    <th scope="row"><Link to={paths.depo(r.depotId)}>{r.ad}</Link></th>
                    <td>{r.level ? <LevelChip level={r.level} /> : <span className="sub" aria-label="Seviye yok">—</span>}</td>
                    <td className="n">{r.cutPct !== null ? pct(r.cutPct) : '—'}</td>
                    <td>{r.reason}</td>
                    <td className="n">
                      <Link to={paths.depo(r.depotId)} style={{ fontWeight: 600, whiteSpace: 'nowrap' }} aria-label={`${r.ad} detayı`}>Detay →</Link>
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={5} className="sub">“{query}” ile eşleşen depo yok.</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <p className="sr-only" role="status">{q ? `${rows.length} depo listeleniyor` : ''}</p>
        </section>

        {featured && <FeaturedCard d={featured} />}
      </div>
    </>
  );
}
