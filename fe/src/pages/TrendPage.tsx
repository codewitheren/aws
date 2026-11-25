import { dataApi } from '../data/api';
import type { TrendData } from '../data/types';
import { pct } from '../lib/format';
import { useResource } from '../lib/useResource';
import { CutReasonsChart } from '../charts/CutReasonsChart';
import { HeatMap, heatColor } from '../charts/HeatMap';
import { LimitUsage } from '../charts/LimitUsage';
import { TopCutBars } from '../charts/TopCutBars';
import { TrendLineChart } from '../charts/TrendLineChart';
import { Legend, reasonLegend } from '../components/Legend';
import { Loadable } from '../components/Loadable';

export function TrendPage() {
  const res = useResource(dataApi.getTrend, 'trend');
  return (
    <div className="stack">
      <Loadable resource={res}>{(data) => <Trend data={data} />}</Loadable>
    </div>
  );
}

function Trend({ data }: { data: TrendData }) {
  return (
    <>
      <header className="page-head">
        <h1 tabIndex={-1}>Kısma trendi</h1>
        <p className="sub">{data.context.merkez} · {data.context.transferTypeLabel} · {data.rangeLabel}</p>
      </header>

      <section className="card" aria-labelledby="t1">
        <div className="split">
          <h2 id="t1">Merkez kısma oranı</h2>
          <Legend items={[
            { label: `Normal bant ${pct(data.band.low)}–${data.band.high}`, swatch: { background: 'var(--band)', border: '1px solid var(--line)' } },
            { label: 'Bant dışı gün', swatch: { background: 'var(--uyari-mark)', borderRadius: '50%' } },
          ]} />
        </div>
        <TrendLineChart days={data.days} values={data.cutRatio} band={data.band} />
      </section>

      <section className="card" aria-labelledby="t2">
        <div className="split">
          <h2 id="t2">Kesinti nedenleri, gün bazında</h2>
          <Legend items={reasonLegend(['kap', 'backlog', 'limit', 'yok'])} />
        </div>
        <CutReasonsChart days={data.days} reasons={data.reasons} />
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
        <HeatMap rows={data.heat} days={data.days} />
      </section>

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
