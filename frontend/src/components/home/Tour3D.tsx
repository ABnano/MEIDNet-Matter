import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { currentTheme } from '@/lib/theme';
import { home as H } from '@/copy/research';

/** The one-minute animated tour of MEIDNet (data → model → family → rules → targets → search → candidates), drawn live on
 *  a canvas by two plain scripts served from /tour/ (prism3d.js, the small 3D toolkit; prism-tour.js, the scenes and the
 *  player). They came from the MEIDNet Prism landing page and keep their own controls: play, chapters, a seek bar, the
 *  keyboard. The scripts find this markup by its ids and classes, so those names are fixed. */
const SCRIPTS = ['/tour/prism3d.js', '/tour/prism-tour.js'];

declare global {
  interface Window { prismTour?: { play: () => void; pause: () => void; go: (i: number) => void; seek: (ms: number) => void }; PrismScenes?: unknown }
}

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[data-tour="${src}"]`);
    if (existing) { existing.dataset.loaded ? resolve() : existing.addEventListener('load', () => resolve(), { once: true }); return; }
    const s = document.createElement('script');
    s.src = src; s.async = false; s.dataset.tour = src;
    s.onload = () => { s.dataset.loaded = '1'; resolve(); };
    s.onerror = () => reject(new Error(`${src} did not load`));
    document.head.appendChild(s);
  });
}

export function Tour3D() {
  const root = useRef<HTMLElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    // the scripts attach to #tour3d once, on load; a later render of this component keeps the same element
    (async () => {
      try {
        if (!window.prismTour) { for (const src of SCRIPTS) await loadScript(src); }
      } catch { if (alive) setFailed(true); }
    })();
    return () => { alive = false; window.prismTour?.pause(); };
  }, []);
  // the player redraws itself when the site's theme switch is clicked (#theme); this app's toggle has no id, so a
  // theme change is forwarded by redrawing through the player's own API
  useEffect(() => {
    const el = document.documentElement;
    const obs = new MutationObserver(() => { const t = window.prismTour; if (t) t.seek(((t as unknown as { _ms?: number })._ms ?? 0)); });
    obs.observe(el, { attributes: true, attributeFilter: ['data-theme'] });
    return () => obs.disconnect();
  }, []);
  const theme = currentTheme();
  return (
    <section className="tour3d" id="tour3d" aria-labelledby="t3-title" data-theme-seen={theme}>
      <div className="micro" id="t3-title">{H.tourTitle}</div>
      <ol className="t3-strip" aria-label="Chapters"></ol>
      <div className="t3-stage">
        <canvas tabIndex={0} role="img" aria-label={H.tourAria}></canvas>
        {failed && <div className="t3-fallback small muted">{H.tourFallback}</div>}
      </div>
      <p className="t3-cap" aria-live="polite"></p>
      <div className="t3-bar">
        <button type="button" className="t3-b primary" data-t3="play" aria-label="Play the tour">▶ Play</button>
        <button type="button" className="t3-b" data-t3="prev" aria-label="Previous chapter">◀</button>
        <button type="button" className="t3-b" data-t3="next" aria-label="Next chapter">▶</button>
        <div className="t3-prog" role="slider" tabIndex={0} aria-label="Position in the tour, in seconds" aria-valuemin={0} aria-valuemax={63} aria-valuenow={0}><i></i></div>
        <span className="t3-time">0:00</span>
        <Link className="t3-open" to="/explore">{H.tourOpen}</Link>
      </div>
    </section>
  );
}
