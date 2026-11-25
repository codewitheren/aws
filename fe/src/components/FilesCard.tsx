import { useState } from 'react';
import { downloadRunFile } from '../agent/agentcore';
import { config } from '../config';
import type { CsvFile } from '../data/exports';
import { downloadBlob, toCsvBlob } from '../lib/download';
import { nf } from '../lib/format';

interface Props {
  sentLines: number;
  anomalyFile: CsvFile;
  alertsFile: CsvFile;
}

const live = config.agentMode === 'agentcore';

/** İndirilecek dosyalar. Agent hiçbir sisteme yazmaz; kullanıcı dosyayı indirip kendisi uygular. */
export function FilesCard({ sentLines, anomalyFile, alertsFile }: Props) {
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  /** Canlı modda dosyalar koşunun S3 alanından imzalı bağlantıyla iner; mock modda CSV'ler tarayıcıda üretilir. */
  const get = async (name: 'transfer.xlsx' | 'uyarilar.csv' | 'anomaliler.csv', csv?: CsvFile) => {
    setMessage(null);
    if (!live) {
      if (csv) downloadBlob(csv.filename, toCsvBlob(csv.header, csv.rows));
      else setMessage('Transfer çıktısı (.xlsx) kesim motoru tarafından üretilir. Örnek (mock) modda bu dosya indirilemez.');
      return;
    }
    setBusy(true);
    try {
      await downloadRunFile(name);
    } catch (err) {
      setMessage('Dosya alınamadı: ' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card" aria-labelledby="i1">
      <div className="stack-s">
        <h2 id="i1">Dosyalar</h2>
        <span className="sub">Agent hiçbir sisteme yazmaz. Uygulamak için dosyaları indirin.</span>
      </div>
      <div className="grid-auto" style={{ gap: 10, ['--min' as string]: '220px' }}>
        <button type="button" className="btn btn-p btn-file" onClick={() => void get('transfer.xlsx')} disabled={busy} aria-describedby="xlsx-msg">
          <span>Transfer çıktısı</span>
          <small>.xlsx · {nf(sentLines)} satır · sevkiyata gider</small>
        </button>
        <button type="button" className="btn btn-file" onClick={() => void get('anomaliler.csv', anomalyFile)} disabled={busy}>
          <span>Relex anomali listesi</span>
          <small>{live ? '.csv · Relex\'e gider' : `.csv · örnek dosyada ${nf(anomalyFile.rows.length)} satır · Relex'e gider`}</small>
        </button>
        <button type="button" className="btn btn-file" onClick={() => void get('uyarilar.csv', alertsFile)} disabled={busy}>
          <span>Uyarı listesi</span>
          <small>.csv · {nf(alertsFile.rows.length)} uyarı</small>
        </button>
      </div>
      <p id="xlsx-msg" className="sub" role="status">{busy ? 'Dosya hazırlanıyor…' : message}</p>
    </section>
  );
}
