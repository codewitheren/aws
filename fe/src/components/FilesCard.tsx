import { useState } from 'react';
import { fetchTransferOutput } from '../data/api';
import type { CsvFile } from '../data/exports';
import { downloadBlob, toCsvBlob } from '../lib/download';
import { nf } from '../lib/format';

interface Props {
  runId: string | null;
  sentLines: number;
  anomalyFile: CsvFile;
  alertsFile: CsvFile;
}

/** İndirilecek dosyalar. Agent hiçbir sisteme yazmaz; kullanıcı dosyayı indirip kendisi uygular. */
export function FilesCard({ runId, sentLines, anomalyFile, alertsFile }: Props) {
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const downloadCsv = (f: CsvFile) => {
    setMessage(null);
    downloadBlob(f.filename, toCsvBlob(f.header, f.rows));
  };

  const downloadXlsx = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetchTransferOutput(runId);
      if (res.kind === 'file') downloadBlob(res.filename, res.blob);
      else setMessage(res.message);
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
        <button type="button" className="btn btn-p btn-file" onClick={() => void downloadXlsx()} disabled={busy} aria-describedby="xlsx-msg">
          <span>Transfer çıktısı</span>
          <small>.xlsx · {nf(sentLines)} satır · sevkiyata gider</small>
        </button>
        <button type="button" className="btn btn-file" onClick={() => downloadCsv(anomalyFile)}>
          <span>Relex anomali listesi</span>
          <small>.csv · örnek dosyada {nf(anomalyFile.rows.length)} satır · Relex'e gider</small>
        </button>
        <button type="button" className="btn btn-file" onClick={() => downloadCsv(alertsFile)}>
          <span>Uyarı listesi</span>
          <small>.csv · {nf(alertsFile.rows.length)} uyarı</small>
        </button>
      </div>
      <p id="xlsx-msg" className="sub" role="status">{message}</p>
    </section>
  );
}
