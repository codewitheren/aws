import { config } from '../config';
import { dataApi } from '../data/api';
import type { DepotDetail, LeverRow } from '../data/types';
import { nf, pct } from '../lib/format';
import { useResource } from '../lib/useResource';
import { DepotTrendChart } from '../charts/DepotTrendChart';
import { MetricBars } from '../charts/MetricBars';
import { Waterfall } from '../charts/Waterfall';
import { Chip, LEVEL_LABEL, LevelChip } from '../components/Chip';
import { FindingCard } from '../components/FindingCard';
import { Loadable } from '../components/Loadable';
import { Link, paths } from '../router/router';
import { useRunStore } from '../run/RunProvider';
import { depotFigures } from '../run/depotOutcome';
import { findingState, type FindingState } from '../run/selectors';

export function DepoPage({ id }: { id: string }) {
  const res = useResource(() => dataApi.getDepotDetail(id), 'depot:' + id);
  return (
    <div className="stack">
      <Loadable resource={res}>
        {({ detail, name }) => (detail ? <Detail d={detail} /> : <NoData name={name} />)}
      </Loadable>
    </div>
  );
}

function BackLink() {
  return <Link to={paths.depolar} style={{ fontSize: 13, textDecoration: 'none', padding: '6px 0', alignSelf: 'flex-start' }}>← Depolar</Link>;
}

function NoData({ name }: { name: string | null }) {
  return (
    <>
      <header className="page-head" style={{ gap: 8 }}>
        <BackLink />
        <h1 tabIndex={-1}>{name ?? 'Bilinmeyen depo'}</h1>
      </header>
      <section className="card" aria-labelledby="nd">
        <h2 id="nd">Bu depo için detay verisi yok</h2>
        <p className="measure">
          {name ? `${name} için` : 'Bu adres için'} gösterilecek depo detayı bulunmuyor.{' '}
          {config.agentMode === 'agentcore' ? 'Depo bu optimizasyonun öneri listesinde yok.' : 'Örnek veride yalnızca Göztepe ve Kavacık için detay var; başka bir deponun verisini bu adla göstermiyoruz.'}
        </p>
        <div className="inline">
          <Link className="btn btn-p" to={paths.depolar}>Depo listesine dön</Link>
          {config.agentMode !== 'agentcore' && <Link className="btn" to={paths.depo('goztepe')}>Göztepe detayı</Link>}
          {config.agentMode !== 'agentcore' && <Link className="btn" to={paths.depo('kavacik')}>Kavacık detayı</Link>}
        </div>
      </section>
    </>
  );
}

function fillTemplate(text: string, values: Record<string, string>): string {
  return text.replace(/\{([^}]+)\}/g, (m, key: string) => values[key] ?? m);
}

function correctionSummary(d: DepotDetail, state: FindingState, total: number): string | null {
  const f = d.finding;
  if (!f) return null;
  const lead = `${f.product} önerisi ${f.group} medyanından çok uzaktı (${nf(f.relexValue)}; medyan ${nf(f.median)}).`;
  if (state.kind === 'not_asked') return `${lead} Bu oturumda ${f.merkez} optimizasyonu yapılmadı; agent bunu optimizasyon sırasında onayınıza sunar. Şu an Forecast değerleri gösteriliyor.`;
  if (state.kind === 'pending') return `${lead} Optimizasyon sürüyor; bu öneri için kararınız bekleniyor.`;
  const o = state.resolution.outcome;
  if (o.kind === 'applied') {
    const what = o.method === 'median' ? `Onayınızla ${nf(o.value)} adede çekildi`
      : o.method === 'mean' ? `Talimatınızla ${f.group} ortalamasına (${nf(o.value)} adet) çekildi`
      : `Talimatınızla ${nf(o.value)} adetle sınırlandı`;
    return `${lead} ${what}; depo önerisi ${nf(total)} oldu, gönderilen miktar değişmedi.`;
  }
  return `${lead} ${o.reason === 'rejected' ? 'Düzeltmeyi reddettiniz' : 'Düzeltme uygulanmadı'}; öneri ${nf(f.relexValue)} olarak kaldı.`;
}

function LeverResult({ r }: { r: LeverRow['result'] }) {
  return r.kind === 'chip' ? <Chip tone={r.tone}>{r.label}</Chip> : <span className="sub">{r.label}</span>;
}

function Detail({ d }: { d: DepotDetail }) {
  const { state } = useRunStore();
  const fState: FindingState = d.finding ? findingState(state.run, d.finding) : { kind: 'not_asked' };
  const fig = depotFigures(d, fState);
  const tokens: Record<string, string> = { gonderilen: nf(fig.sent) };
  fig.cuts.forEach((c) => { tokens['kesim:' + c.key] = nf(c.amount); });
  const correction = correctionSummary(d, fState, fig.total);
  const absorbed = d.finding ? d.waterfall.cuts.find((c) => c.key === d.finding?.absorbedByCut)?.source ?? '' : '';
  const totalNote = fig.delta > 0
    ? `Öneri, onayladığınız düzeltmeden sonraki değerdir (Forecast: ${nf(d.waterfall.relexTotal)}).`
    : d.finding && fState.kind === 'resolved' ? 'Öneri, Forecast değeridir; düzeltme uygulanmadı.' : 'Öneri, Forecast değeridir.';

  return (
    <>
      <header className="page-head" style={{ gap: 8 }}>
        <BackLink />
        <div className="inline" style={{ gap: 10 }}>
          <h1 tabIndex={-1}>{d.ad}</h1>
          {d.group && <Chip tone="notr">{d.group}</Chip>}
          <LevelChip level={d.level}>{d.levelNote ? `${LEVEL_LABEL[d.level]} · ${d.levelNote}` : undefined}</LevelChip>
        </div>
        <p className="sub">{d.context.merkez} · {d.context.transferTypeLabel} · {d.context.dateLabel.split(' ')[0]} · kısma oranı {pct(d.cutPct)}</p>
        <div className="inline">
          <Link className="btn btn-sm" to={paths.sonuclar}>Optimizasyon sonuçları</Link>
          <Link className="btn btn-sm" to={paths.trend}>Merkez trendi</Link>
        </div>
      </header>

      <section aria-labelledby="g0" className="hero" style={{ gap: 10 }}>
        <span id="g0" className="lbl">Agent açıklaması</span>
        <p style={{ fontSize: 17, fontWeight: 600, lineHeight: 1.4, textWrap: 'pretty' }}>{d.explanation.headline}</p>
        <p className="measure">{fillTemplate(d.explanation.body, tokens)}</p>
        <p className="measure"><strong>Öneri:</strong> {d.explanation.recommendation}</p>
        {correction && <p className="measure"><strong>Optimizasyon sırasındaki düzeltme:</strong> {correction}</p>}
      </section>

      {d.finding && (
        <FindingCard finding={d.finding} state={fState} relexTotal={d.waterfall.relexTotal} total={fig.total} delta={fig.delta} absorbedLabel={absorbed} />
      )}

      <section className="card" aria-labelledby="g1">
        <h2 id="g1">Kesim şelalesi</h2>
        <Waterfall total={fig.total} cuts={fig.cuts} sent={fig.sent} />
        <p className="sub">Adet. {totalNote} {d.waterfall.note}</p>
      </section>

      {(d.tir || d.fill || d.aClassCut !== null || d.metrics || d.chronic) && (
        <div className="grid-auto" style={{ gap: 20, ['--min' as string]: '300px' }}>
          {d.tir && (
            <section className="card" aria-labelledby="g2">
              <h2 id="g2">TIR limiti</h2>
              <MetricBars bars={d.tir.bars} />
              <p className="sub">{d.tir.note}</p>
            </section>
          )}
          {d.fill && (
            <section className="card" aria-labelledby="g3">
              <h2 id="g3">Doluluk</h2>
              <MetricBars bars={d.fill.bars} />
              <p className="sub">{d.fill.note}</p>
            </section>
          )}
          {d.aClassCut !== null && (
            <section className="card" aria-labelledby="g4">
              <h2 id="g4">A sınıfından kesilen</h2>
              <span className="big">{nf(d.aClassCut)} adet</span>
              <p className="sub">En çok satan ürünlerde kesinti, stoksuzluk riskini doğrudan artırır.</p>
            </section>
          )}
          {d.metrics && (
            <section className="card" aria-labelledby="g8">
              <h2 id="g8">{d.metrics.title}</h2>
              <div className="grid-auto" style={{ ['--min' as string]: '130px' }}>
                {d.metrics.items.map((m) => (
                  <div className="kv" key={m.label}><span className="lbl">{m.label}</span><strong style={{ fontSize: 18 }}>{m.value}</strong></div>
                ))}
              </div>
              <p className="sub">{d.metrics.note}</p>
            </section>
          )}
          {d.chronic && (
            <section className="card" aria-labelledby="g9">
              <h2 id="g9">Kronik hacim kısması</h2>
              <span className="big">{d.chronic.days} / {d.chronic.of} gün</span>
              <p className="sub">Son {d.chronic.of} sipariş gününün {d.chronic.days}'ünde hacim kısması var.</p>
            </section>
          )}
        </div>
      )}

      {(d.topProducts || d.trend) && (
        <div className="cols">
          {d.topProducts && (
            <section className="card" aria-labelledby="g5" style={{ flex: '1 1 420px' }}>
              <h2 id="g5">En çok kesilen ürünler</h2>
              <div className="tw">
                <table className="t">
                  <thead>
                    <tr><th scope="col">Ürün</th><th scope="col">Sınıf</th><th scope="col" className="n">Öneri</th><th scope="col" className="n">Gönderilen</th><th scope="col" className="n">Kesilen</th><th scope="col">Neden</th></tr>
                  </thead>
                  <tbody>
                    {d.topProducts.map((p) => (
                      <tr key={p.product}>
                        <td>{p.product}</td><td>{p.cls}</td><td className="n">{nf(p.suggested)}</td><td className="n">{nf(p.sent)}</td>
                        <td className="n">{nf(p.suggested - p.sent)}</td><td>{p.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          {d.trend && (
            <section className="card" aria-labelledby="g6" style={{ flex: '1 1 420px' }}>
              <div className="stack-s">
                <h2 id="g6">Depo kısma trendi</h2>
                <span className="sub">Son {d.trend.depot.length} gün · kesikli çizgi: merkez ortalaması</span>
              </div>
              <DepotTrendChart depotName={d.ad} depot={d.trend.depot} merkez={d.trend.merkez} days={d.trend.days} />
            </section>
          )}
        </div>
      )}

      {d.ledger && d.ledger.length > 0 && (
        <section className="card" aria-labelledby="g10">
          <div className="stack-s">
            <h2 id="g10">Motorun hesabı</h2>
            <span className="sub">Kapasite, TIR ve limit adımları; kesimin hangi kısıttan geldiğini gösterir.</span>
          </div>
          <div className="grid-auto" style={{ gap: 20, ['--min' as string]: '300px' }}>
            {d.ledger.map((s) => (
              <div className="tw" key={s.section}>
                <table className="t">
                  <caption className="lbl" style={{ textAlign: 'left' }}>{s.section}</caption>
                  <tbody>
                    {s.rows.map((r, i) => (
                      <tr key={i}>
                        <td style={{ width: 20 }}>{r.op}</td>
                        <th scope="row" style={{ fontWeight: r.op === '=' ? 600 : 400 }}>{r.label}{r.note && <span className="sub"> · {r.note}</span>}</th>
                        <td className="n">{r.value}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        </section>
      )}

      {d.levers && (
        <section className="card" aria-labelledby="g7">
          <div className="stack-s">
            <h2 id="g7">Ne yapabiliriz?</h2>
            <span className="sub">Kaldıraçların bu depodaki etkisi</span>
          </div>
          <div className="tw">
            <table className="t" style={{ minWidth: 640 }}>
              <thead><tr><th scope="col">Kaldıraç</th><th scope="col">Etki</th><th scope="col">Değerlendirme</th><th scope="col">Sonuç</th></tr></thead>
              <tbody>
                {d.levers.map((l) => (
                  <tr key={l.lever}>
                    <th scope="row">{l.lever}</th><td>{l.effect}</td><td>{l.assessment}</td><td><LeverResult r={l.result} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
