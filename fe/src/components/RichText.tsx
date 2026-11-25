import { Fragment } from 'react';

/**
 * Agent metnini güvenli biçimde gösterir: boş satır paragraf ayırır, **kalın** desteklenir.
 * HTML yorumlanmaz.
 */
export function RichText({ text }: { text: string }) {
  const paragraphs = text.split(/\n{2,}/).filter((p) => p.trim() !== '');
  return (
    <>
      {paragraphs.map((p, i) => (
        <p key={i}>
          {p.split(/(\*\*[^*]+\*\*)/g).map((part, j) =>
            part.startsWith('**') && part.endsWith('**') && part.length > 4
              ? <strong key={j}>{part.slice(2, -2)}</strong>
              : <Fragment key={j}>{part}</Fragment>,
          )}
        </p>
      ))}
    </>
  );
}
