import { nf } from '../lib/format';
import type { OutlierFinding } from '../data/types';
import type { FindingState } from '../run/selectors';
import { Link, paths } from '../router/router';
import { Chip } from './Chip';

interface Props {
  finding: OutlierFinding;
  state: FindingState;
  relexTotal: number;
  total: number;
  delta: number;
  absorbedLabel: string;
}

function StateChip({ state }: { state: FindingState }) {
  switch (state.kind) {
    case 'not_asked':
      return <Chip tone="notr">Bu oturumda sorulmadı</Chip>;
    case 'pending':
      return <Chip tone="bilgi">{state.awaitingNow ? 'Onayınız bekleniyor' : 'Koşu sürüyor'}</Chip>;
    case 'resolved': {
      const o = state.resolution.outcome;
      if (o.kind === 'applied') return <Chip tone="iyi">{o.method === 'median' ? 'Onayladınız · uygulandı' : 'Talimatınızla uygulandı'}</Chip>;
      return <Chip tone="notr">{o.reason === 'rejected' ? 'Reddettiniz · değiştirilmedi' : 'Değiştirilmedi · notunuz kaydedildi'}</Chip>;
    }
  }
}

/** Sonuç paragrafı: karar durumuna göre ne olduğunu düz bir dille anlatır. */
function Outcome({ finding, state, relexTotal, total, delta, absorbedLabel }: Props) {
  const relex = nf(finding.relexValue);
  if (state.kind === 'not_asked') {
    return (
      <p className="measure">
        Bu oturumda {finding.merkez} koşusu henüz yapılmadı; rakamlar Relex değerleriyle gösteriliyor (depo önerisi {nf(relexTotal)}).
        Koşu başlatıldığında agent aykırı önerileri onayınıza sunar. <Link to={paths.kosu}>Koşu ekranına git</Link>
      </p>
    );
  }
  if (state.kind === 'pending') {
    return (
      <p className="measure">
        {state.awaitingNow ? 'Agent şu an bu öneri için onayınızı bekliyor.' : 'Koşu sürüyor; bu öneri için henüz karar verilmedi.'}{' '}
        Karar verilene kadar rakamlar Relex değerleriyle gösteriliyor. <Link to={paths.kosu}>Koşu ekranına git</Link>
      </p>
    );
  }
  const { outcome, note } = state.resolution;
  const pendingRun = state.runCompleted ? '' : ' Koşu tamamlanınca çıktıya yansır.';
  if (outcome.kind === 'applied') {
    const how = outcome.method === 'median' ? 'Öneri medyana çekildi'
      : outcome.method === 'mean' ? `Öneri ${finding.group} ortalamasına çekildi`
      : `Öneri talimatınızla (“${note ?? ''}”) sınırlandı`;
    return (
      <p className="measure">
        {how} ve kesim {nf(outcome.value)} adet üzerinden yapıldı (−{nf(finding.relexValue - outcome.value)} adet).
        Deponun toplam önerisi {nf(relexTotal)} adetten {nf(total)} adede indi.
        Gönderilen miktar değişmedi: bu {nf(delta)} adet zaten {absorbedLabel} kesilecekti.
        Relex'teki kayıt değişmedi; satır anomali listesinde "koşuda düzeltildi" notuyla duruyor.{pendingRun}
      </p>
    );
  }
  const why = outcome.reason === 'rejected' ? 'Öneri olduğu gibi bırakıldı'
    : outcome.reason === 'instruction_not_lower' ? `Talimatınızdaki değer (“${note ?? ''}”) mevcut öneriden küçük olmadığı için öneri değiştirilmedi`
    : `Talimatınız (“${note ?? ''}”) bir düzeltme olarak yorumlanmadı; öneri olduğu gibi bırakıldı ve notunuz koşu kaydına eklendi`;
  return (
    <p className="measure">
      {why}; kesim {relex} adet üzerinden yapıldı. Deponun toplam önerisi {nf(relexTotal)} olarak kaldı.
      Satır Relex anomali listesinde "düzeltilmedi" notuyla duruyor; Relex ekibiyle doğrulamanız önerilir.{pendingRun}
    </p>
  );
}

/** Depo detayında agent'ın koşu sırasında sorduğu aykırı PL önerisi ve sonucu. */
export function FindingCard(props: Props) {
  const { finding, state } = props;
  const used = state.kind === 'resolved'
    ? nf(state.resolution.outcome.kind === 'applied' ? state.resolution.outcome.value : finding.relexValue) + ' adet'
    : '—';
  const kv = (label: string, value: string, brand = false) => (
    <div className="kv">
      <span className="lbl">{label}</span>
      <strong style={{ fontSize: 18, color: brand ? 'var(--brand)' : undefined }}>{value}</strong>
    </div>
  );

  return (
    <section className="card" aria-labelledby="gd">
      <div className="split" style={{ alignItems: 'center' }}>
        <div className="stack-s">
          <h2 id="gd">Aykırı PL önerisi: {finding.product}</h2>
          <span className="sub">
            {state.kind === 'resolved' ? 'Agent koşu sırasında bulup size sordu' : 'Agent koşu sırasında soracak'}: "Medyana ({nf(finding.median)}) çekeyim mi?"
          </span>
        </div>
        <StateChip state={state} />
      </div>
      <div className="grid-auto" style={{ gap: 16, ['--min' as string]: '150px' }}>
        {kv('Relex önerisi', `${nf(finding.relexValue)} adet`)}
        {kv(`${finding.group} ortalaması`, nf(finding.mean))}
        {kv(`${finding.group} medyanı`, nf(finding.median))}
        {kv('Agent önerisi', `${nf(finding.relexValue)} → ${nf(finding.median)}`)}
        {kv('Koşuda kullanılan', used, true)}
      </div>
      <div className="stack-m measure">
        <div className="stack-s"><span className="lbl">Agent ne buldu</span><span>{finding.found}</span></div>
        <div className="stack-s"><span className="lbl">Agent ne önerdi</span><span>{finding.proposed}</span></div>
        <span className="lbl">Sonuç</span>
      </div>
      <Outcome {...props} />
    </section>
  );
}
