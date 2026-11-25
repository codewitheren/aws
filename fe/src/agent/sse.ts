/**
 * `fetch` yanıt gövdesinden Server-Sent Events okur. EventSource yalnızca GET desteklediği için
 * POST ile başlatılan akışlarda bu ayrıştırıcı kullanılır. Yalnızca `data:` alanları kullanılır;
 * `event:`, `id:` ve `retry:` yok sayılır, ":" ile başlayan satırlar yorumdur (keep-alive).
 */
export async function readEventStream(
  body: ReadableStream<Uint8Array>,
  onData: (data: string) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let dataLines: string[] = [];

  const dispatch = () => {
    if (dataLines.length > 0) onData(dataLines.join('\n'));
    dataLines = [];
  };

  const processLine = (line: string) => {
    if (line === '') return dispatch();
    if (line.startsWith(':')) return;
    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'data') dataLines.push(value);
  };

  for (;;) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    // Yalnızca LF / CRLF satır sonları desteklenir (tek başına CR desteklenmez).
    const lines = buffer.split(/\r?\n/);
    // Son parça yarım bir satır olabilir; bir sonraki okumaya bırak.
    buffer = done ? '' : lines.pop() ?? '';
    lines.forEach(processLine);
    if (done) {
      dispatch();
      return;
    }
  }
}
