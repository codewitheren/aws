import { useCallback, useEffect, useState } from 'react';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'tk-theme';
const query = '(prefers-color-scheme: dark)';

function readStored(): Theme | null {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return v === 'light' || v === 'dark' ? v : null;
  } catch {
    return null;
  }
}

function writeStored(theme: Theme): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Depolama kapalı olabilir (gizli mod vb.); tema yine de bu oturumda çalışır.
  }
}

function systemTheme(): Theme {
  return window.matchMedia?.(query).matches ? 'dark' : 'light';
}

export function initialTheme(): Theme {
  return readStored() ?? systemTheme();
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
}

/** Tema: kayıtlı tercih yoksa işletim sistemini izler; değiştirince kaydedilir. */
export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [explicit, setExplicit] = useState(() => readStored() !== null);

  useEffect(() => applyTheme(theme), [theme]);

  useEffect(() => {
    if (explicit || !window.matchMedia) return;
    const mq = window.matchMedia(query);
    const onChange = () => setTheme(mq.matches ? 'dark' : 'light');
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [explicit]);

  const toggle = useCallback(() => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark';
    writeStored(next);
    setTheme(next);
    setExplicit(true);
  }, [theme]);

  return { theme, toggle };
}
