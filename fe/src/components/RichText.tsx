import type { ReactNode } from 'react';

/**
 * Agent yanıtındaki Markdown alt kümesini güvenli biçimde gösterir (HTML yorumlanmaz, yalnız React öğeleri):
 * başlık (#), madde (-, *, •), numaralı liste (1.), tablo (| a | b |), yatay çizgi (---), alıntı (>),
 * satır içinde **kalın**, *italik*, `kod`.
 */

function inline(text: string, key = 0): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*\s][^*]*\*)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    const k = `${key}-${m.index}`;
    if (t.startsWith('**') || t.startsWith('__')) out.push(<strong key={k}>{t.slice(2, -2)}</strong>);
    else if (t.startsWith('`')) out.push(<code key={k} className="md-code">{t.slice(1, -1)}</code>);
    else out.push(<em key={k}>{t.slice(1, -1)}</em>);
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const cells = (row: string) => row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
const isNum = (s: string) => /^[%−+-]?[\d.,]+\s*(%|adet|palet|L|kg|satır)?$/.test(s);

type Block =
  | { kind: 'h'; level: number; text: string }
  | { kind: 'p'; text: string }
  | { kind: 'ul' | 'ol'; items: string[] }
  | { kind: 'table'; head: string[]; rows: string[][] }
  | { kind: 'quote'; text: string }
  | { kind: 'hr' };

function parse(src: string): Block[] {
  const lines = src.replace(/\r\n?/g, '\n').split('\n');
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();
    if (!t) { i++; continue; }
    let m: RegExpMatchArray | null;
    if ((m = t.match(/^(#{1,6})\s+(.*)$/))) { blocks.push({ kind: 'h', level: m[1].length, text: m[2] }); i++; continue; }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(t)) { blocks.push({ kind: 'hr' }); i++; continue; }
    if (t.startsWith('|') && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const head = cells(t);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(cells(lines[i++]));
      blocks.push({ kind: 'table', head, rows });
      continue;
    }
    if (/^([-*•])\s+/.test(t) || /^\d+[.)]\s+/.test(t)) {
      const ordered = /^\d+[.)]\s+/.test(t);
      const re = ordered ? /^\d+[.)]\s+/ : /^[-*•]\s+/;
      const items: string[] = [];
      while (i < lines.length && re.test(lines[i].trim())) {
        let item = lines[i++].trim().replace(re, '');
        // Girintili devam satırları aynı maddeye eklenir.
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !re.test(lines[i].trim())) item += ' ' + lines[i++].trim();
        items.push(item);
      }
      blocks.push({ kind: ordered ? 'ol' : 'ul', items });
      continue;
    }
    if (t.startsWith('>')) {
      const parts: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('>')) parts.push(lines[i++].trim().replace(/^>\s?/, ''));
      blocks.push({ kind: 'quote', text: parts.join(' ') });
      continue;
    }
    const parts: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|[-*•]\s|\d+[.)]\s|\||>|-{3,}$)/.test(lines[i].trim())) parts.push(lines[i++].trim());
    if (parts.length === 0) parts.push(lines[i++].trim());
    blocks.push({ kind: 'p', text: parts.join('\n') });
  }
  return blocks;
}

function withBreaks(text: string, key: number): ReactNode[] {
  return text.split('\n').flatMap((l, j) => (j ? [<br key={`br${key}-${j}`} />, ...inline(l, key * 100 + j)] : inline(l, key * 100 + j)));
}

export function RichText({ text }: { text: string }) {
  return (
    <div className="md">
      {parse(text).map((b, i) => {
        switch (b.kind) {
          case 'h': return <p key={i} className={'md-h' + Math.min(b.level, 3)}>{inline(b.text, i)}</p>;
          case 'p': return <p key={i}>{withBreaks(b.text, i)}</p>;
          case 'ul': return <ul key={i}>{b.items.map((it, j) => <li key={j}>{inline(it, i * 100 + j)}</li>)}</ul>;
          case 'ol': return <ol key={i}>{b.items.map((it, j) => <li key={j}>{inline(it, i * 100 + j)}</li>)}</ol>;
          case 'quote': return <blockquote key={i}>{inline(b.text, i)}</blockquote>;
          case 'hr': return <hr key={i} />;
          case 'table':
            return (
              <div key={i} className="tw md-table">
                <table className="t">
                  <thead><tr>{b.head.map((h, j) => <th key={j} scope="col">{inline(h, j)}</th>)}</tr></thead>
                  <tbody>
                    {b.rows.map((r, j) => (
                      <tr key={j}>{b.head.map((_, k) => <td key={k} className={isNum(r[k] ?? '') ? 'n' : undefined}>{inline(r[k] ?? '', k)}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
        }
      })}
    </div>
  );
}
