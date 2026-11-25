/**
 * Tasarımdaki tohumlu sözde rastgele üreteç (Park–Miller). Aynı tohum aynı seriyi verir;
 * örnek grafiklerin tasarımla birebir aynı görünmesi için kullanılır.
 */
export function rng(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}
