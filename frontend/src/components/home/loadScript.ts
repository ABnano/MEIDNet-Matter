/** Loads a plain script of the MEIDNet Prism animations (served from /tour/) once per page. A second call for the same
 *  file waits for the first one; a file that failed to load is removed again, so the next call tries it afresh. The
 *  scripts run in the order they are asked for (async = false), so the toolkit (prism3d.js) runs before a scene. */
export function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[data-tour="${src}"]`);
    if (existing) {
      if (existing.dataset.loaded) { resolve(); return; }
      existing.addEventListener('load', () => resolve(), { once: true });
      existing.addEventListener('error', () => reject(new Error(`${src} did not load`)), { once: true });
      return;
    }
    const s = document.createElement('script');
    s.src = src; s.async = false; s.dataset.tour = src;
    s.onload = () => { s.dataset.loaded = '1'; resolve(); };
    s.onerror = () => { s.remove(); reject(new Error(`${src} did not load`)); };
    document.head.appendChild(s);
  });
}
