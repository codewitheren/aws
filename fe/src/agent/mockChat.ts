import { nf } from '../lib/format';
import type { ApprovalResolution, ChatLink } from './types';

export interface CannedAnswer {
  text: string;
  links: ChatLink[];
}

const GOZTEPE_KEY = 'goztepe:bulasik-sungeri-5li';

function has(q: string, ...words: string[]): boolean {
  return words.some((w) => q.includes(w));
}

function goztepe(resolutions: readonly ApprovalResolution[]): CannedAnswer {
  const r = resolutions.find((x) => x.findingKey === GOZTEPE_KEY);
  const delta = r && r.outcome.kind === 'applied' ? r.originalValue - r.outcome.value : 0;
  const proposal = delta > 0
    ? `Forecast önerisi 25.605 adet, yani 41,8 palet; onayladığınız düzeltmeyle bu optimizasyonda ${nf(25605 - delta)} adet.`
    : 'Öneri 25.605 adet, yani 41,8 palet.';
  return {
    text:
      '**Kısıt dolap değil, TIR limiti.**\n\n' +
      `${proposal} Göztepe'nin TIR limiti 4 palet; ${nf(21328 - delta)} adet palet limitinden, 2.472 adet su alanından kesildi. Gönderilen 1.805.\n\n` +
      'Dolap şu an %28,6 dolu; her şey gitseydi %84,6 olurdu. TIR limitini G10 medyanı olan 12 palete yaklaştırmak ilk bakılacak kaldıraç.',
    links: [{ label: 'Göztepe detayını aç', route: '/depolar/goztepe' }],
  };
}

const KAVACIK: CannedAnswer = {
  text:
    '**Kısıt dolap hacmi ve her gün tekrarlıyor.**\n\n' +
    "Son 24 sipariş gününün 24'ünde hacim kısması var. Bugün öneri 15.753 adet; 9.089 adet hacimden, 1.636 adet su alanından, 838 adet palet limitinden kesildi, 4.190 adet gönderiliyor.\n\n" +
    'Tam gönderimde doluluk %144, ortalama doluluk %128. Buffer zaten üst sınırda (1,10); kalan kaldıraç ek dolap.',
  links: [{ label: 'Kavacık detayını aç', route: '/depolar/kavacik' }],
};

const KRITIK: CannedAnswer = {
  text:
    '**4 optimizasyon dosyası günün All PL kaydında yok.**\n\n' +
    "+4 Maltepe, +4 Arnavutköy, MS Maltepe ve MS Adana için optimizasyon dosyası var ama All PL'de kayıt yok: 4 dosya, 0 kayıt.\n\n" +
    'Sevkiyattan önce All PL kaydını tamamlayın. Ben hiçbir sisteme yazmam; kaydı sizin oluşturmanız gerekiyor.',
  links: [{ label: 'Optimizasyon ekranını aç', route: '/kosu' }],
};

const FALLBACK: CannedAnswer = {
  text:
    'Bu soruya örnek (mock) modda hazır bir yanıtım yok. Gerçek agent bağlandığında bu optimizasyonun verisi üzerinden yanıt verecek.\n\n' +
    'Şimdilik Göztepe, Kavacık ya da kritik uyarı hakkında sorabilirsiniz.',
  links: [],
};

export function cannedAnswer(question: string, resolutions: readonly ApprovalResolution[]): CannedAnswer {
  const q = question.toLocaleLowerCase('tr-TR');
  if (has(q, 'göztepe', 'goztepe')) return goztepe(resolutions);
  if (has(q, 'kavacık', 'kavacik')) return KAVACIK;
  if (has(q, 'kritik', 'all pl')) return KRITIK;
  return FALLBACK;
}
