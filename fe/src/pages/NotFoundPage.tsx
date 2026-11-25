import { Link, paths } from '../router/router';

export function NotFoundPage({ path }: { path: string }) {
  return (
    <div className="stack">
      <header className="page-head">
        <h1 tabIndex={-1}>Sayfa bulunamadı</h1>
        <p className="sub">“{path}” adresinde bir ekran yok.</p>
      </header>
      <div className="inline">
        <Link className="btn btn-p" to={paths.kosu}>Koşu ekranına git</Link>
        <Link className="btn" to={paths.sonuclar}>Sonuçlar</Link>
      </div>
    </div>
  );
}
