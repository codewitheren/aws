import { dataApi } from '../data/api';
import type { TrendData, TrendHistory } from '../data/types';
import { pct } from '../lib/format';
import { useResource } from '../lib/useResource';
import { CutReasonsChart } from '../charts/CutReasonsChart';
import { HeatMap, heatColor } from '../charts/HeatMap';
import { LimitUsage } from '../charts/LimitUsage';
import { TopCutBars } from '../charts/TopCutBars';
import { TrendLineChart } from '../charts/TrendLineChart';
import { Legend, REASON_COLOR, reasonLegend } from '../components/Legend';
import { Loadable } from '../components/Loadable';

export function TrendPage() {
  const res = useResource(dataApi.getTrend, 'trend');
  return (
    <div className="stack">
      <Loadable resource={res}>{(data) => <Trend data={data} />}</Loadable>
    </div>
  );
}

function History({ h }: { h: TrendHistory }) {
  return (
    <>
      <section className="card" aria-labelledby="t1">
        <div className="split">
          <h2 id="t1">Merkez kısma oranı</h2>
          <Legend items={[
            { label: `Normal bant ${pct(h.band.low)}–${h.band.high}`, swatch: { background: 'var(--band)', border: '1px solid var(--line)' } },
            { label: 'Bant dışı gün', swatch: { background: 'var(--uyari-mark)', borderRadius: '50%' } },
          ]} />
        </div>
        <TrendLineChart days={h.days} values={h.cutRatio} band={h.band} />
      </section>

      <section className="card" aria-labelledby="t2">
        <div className="split">
          <h2 id="t2">Kesinti nedenleri, gün bazında</h2>
          <Legend items={reasonLegend(['kap', 'backlog', 'limit', 'yok'])} />
        </div>
        <CutReasonsChart days={h.days} reasons={h.reasons} />
        <p className="sub">Önerilen miktarın payı. Sütunlar %100'e tamamlanır.</p>
      </section>

      <section className="card" aria-labelledby="t3">
        <div className="split">
          <h2 id="t3">Depo × gün kısma oranı</h2>
          <div className="lg" aria-hidden="true">
            <span>%0</span>
            <span style={{ gap: 2 }}>{[8, 30, 55, 78, 100].map((p) => <b key={p} style={{ background: heatColor(p) }} />)}</span>
            <span>%100</span>
          </div>
        </div>
        <p className="sub">Kronik sorunlu depolar koyu bir çizgi olarak görünür. Depo adına tıklayınca detay açılır.</p>
        <HeatMap rows={h.heat} days={h.days} />
      </section>
    </>
  );
}

function Trend({ data }: { data: TrendData }) {
  return (
    <>
      <header className="page-head">
        <h1 tabIndex={-1}>Kısma trendi</h1>
        <p className="sub">{data.context.merkez} · {data.context.transferTypeLabel} · {data.rangeLabel}</p>
      </header>

      {data.history ? <History h={data.history} /> : (
        <section className="card" aria-labelledby="t0">
          <h2 id="t0">Geçmiş koşular</h2>
          <p className="measure">Bu sürümde geçmiş koşu arşivi yok; 30 günlük trend, gün bazında nedenler ve depo × gün ısı haritası arşiv bağlanınca görünür. Aşağıdakiler bugünkü koşunun rakamlarıdır.</p>
        </section>
      )}

      {data.todayReasons && data.todayReasons.length > 0 && (
        <section className="card" aria-labelledby="t6">
          <div className="split">
            <h2 id="t6">Bugünkü kesinti nedenleri</h2>
            <Legend items={reasonLegend(['kap', 'backlog', 'limit'])} />
          </div>
          <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {data.todayReasons.map((r) => (
              <li key={r.label} className="hbar">
                <span className="h-name">{r.label}</span>
                <span className="h-area" aria-hidden="true"><span style={{ width: r.pct + '%', background: REASON_COLOR[r.reason] }} /></span>
                <span className="h-val">{pct(r.pct, 1)}</span>
              </li>
            ))}
          </ol>
          <p className="sub">Kesilen miktarın nedenlere göre payı.</p>
        </section>
      )}

      <div className="cols">
        <section className="card" aria-labelledby="t4" style={{ flex: '3 1 520px' }}>
          <div className="split">
            <h2 id="t4">En çok kısılan {data.topCut.length} depo</h2>
            <Legend items={reasonLegend(['kap', 'backlog', 'limit'])} />
          </div>
          <TopCutBars items={data.topCut} />
        </section>

        <section className="card" aria-labelledby="t5" style={{ flex: '2 1 380px' }}>
          <div className="stack-s">
            <h2 id="t5">Merkez satır limiti kullanımı</h2>
            <span className="sub">{data.limitNote}</span>
          </div>
          <LimitUsage rows={data.limits} />
          <Legend items={[
            { label: 'Limit altında', swatch: { background: 'var(--brand)' } },
            { label: '%90 ve üzeri (◆ işaretli)', swatch: { background: 'var(--uyari-mark)' } },
          ]} />
        </section>
      </div>
    </>
  );
}
