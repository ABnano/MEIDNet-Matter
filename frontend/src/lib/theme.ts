export type Theme = 'light' | 'dark';

export function currentTheme(): Theme {
  const t = document.documentElement.dataset.theme;
  if (t === 'light' || t === 'dark') return t;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function setTheme(t: Theme) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem('matter_theme', t); } catch { /* storage blocked */ }
}

/** Inside the Hugging Face page the app runs in a frame; some sites refuse to load there. */
export function framed(): boolean {
  try { return window.self !== window.top; } catch { return true; }
}
