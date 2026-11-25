import { useEffect, useRef, useState } from 'react';
import type { ApprovalResolution } from '../agent/types';
import { Chip } from './Chip';

type Filter = 'all' | 'applied' | 'unchanged';

/** Verilen kararların listesi; yerel <dialog> ile açılır (odak tuzağı ve Esc tarayıcıdan gelir). */
export function DecisionsDialog({ open, onClose, resolutions }: { open: boolean; onClose: () => void; resolutions: ApprovalResolution[] }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [filter, setFilter] = useState<Filter>('all');

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  const applied = resolutions.filter((r) => r.outcome.kind === 'applied').length;
  const rows = resolutions.filter((r) => filter === 'all' || (filter === 'applied') === (r.outcome.kind === 'applied'));
  const tabs: [Filter, string][] = [['all', `Tümü ${resolutions.length}`], ['applied', `Düzeltilen ${applied}`], ['unchanged', `Bırakılan ${resolutions.length - applied}`]];

  return (
    <dialog ref={ref} className="dlg" aria-labelledby="dlg-t" onClose={onClose}
      onClick={(e) => { if (e.target === ref.current) onClose(); }}>
      <div className="dlg-head">
        <div className="stack-s">
          <h2 id="dlg-t">Verdiğiniz kararlar</h2>
          <span className="sub">Yalnızca bu optimizasyonun girdisine uygulanır; Forecast'ta kayıt değişmez.</span>
        </div>
        <button type="button" className="btn btn-sm" onClick={onClose} aria-label="Kapat">✕</button>
      </div>
      <div className="seg" role="tablist" aria-label="Kararları süz">
        {tabs.map(([id, label]) => (
          <button key={id} type="button" role="tab" aria-selected={filter === id} className={filter === id ? 'on' : ''} onClick={() => setFilter(id)}>
            {label}
          </button>
        ))}
      </div>
      <ul className="dlg-list">
        {rows.map((r) => (
          <li key={r.approvalId}>
            <div className="stack-s" style={{ gap: 2, minWidth: 0 }}>
              <strong className="ellipsis">{r.title}</strong>
              <span className="sub">{r.summary}{r.note ? ` · “${r.note}”` : ''}</span>
            </div>
            <Chip tone={r.outcome.kind === 'applied' ? 'iyi' : 'notr'}>
              {r.outcome.kind === 'applied' ? 'Düzeltildi' : 'Bırakıldı'}{r.decidedBy === 'bulk' ? ' · toplu' : ''}
            </Chip>
          </li>
        ))}
        {rows.length === 0 && <li className="sub">Bu filtrede karar yok.</li>}
      </ul>
    </dialog>
  );
}
