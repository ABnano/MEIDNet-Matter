import { useEffect, useRef, useState, type MouseEvent } from 'react';
import { useNavigate } from 'react-router';
import { home as H } from '@/copy/research';
import { loadScript } from './loadScript';

/** The one-minute animated tour of MEIDNet (data → model → family → rules → targets → search → candidates), drawn live on
 *  a canvas by two plain scripts served from /tour/ (prism3d.js, the small 3D toolkit; prism-tour.js, the scenes and the
 *  player). They came from the MEIDNet Prism landing page and keep their own controls: play, chapters, a seek bar, the
 *  keyboard. The player finds its parts in this markup by their classes, so those names are fixed. */
const SCRIPTS = ['/tour/prism3d.js', '/tour/prism-tour.js'];

/** The handle PrismTour.mount returns for one #tour3d element. */
export type TourPlayer = { play: () => void; pause: () => void; go: (i: number) => void; seek: (ms: number) => void; redraw?: () => void; destroy?: () => void };

declare global {
  interface Window { PrismTour?: { mount: (root: HTMLElement) => TourPlayer | null }; prismTour?: TourPlayer; PrismScenes?: unknown }
}

export function Tour3D() {
  const root = useRef<HTMLElement>(null);
  const [failed, setFailed] = useState(false);
  const navigate = useNavigate();
  useEffect(() => {
    // the page renders a new section each time it opens: the player is mounted on it, and stopped when the page closes
    let alive = true;
    let player: TourPlayer | null = null;
    (async () => {
      try {
        for (const src of SCRIPTS) await loadScript(src);
        if (alive && root.current) player = window.PrismTour?.mount(root.current) ?? null;
      } catch { if (alive) setFailed(true); }
    })();
    // the player redraws itself for the Prism page's own theme button only; this app's theme switch is forwarded to it
    const obs = new MutationObserver(() => { player?.redraw?.(); });
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => { alive = false; obs.disconnect(); player?.destroy?.(); };
  }, []);
  // the player points this link at the page of the chapter on screen; a plain click follows it inside the app
  const follow = (e: MouseEvent<HTMLAnchorElement>) => {
    const href = e.currentTarget.getAttribute('href') ?? '/explore';
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || !href.startsWith('/')) return;
    e.preventDefault();
    navigate(href);
  };
  return (
    <section className="tour3d" id="tour3d" ref={root} aria-labelledby="t3-title">
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
        <a className="t3-open" href="/explore" onClick={follow}>{H.tourOpen}</a>
      </div>
    </section>
  );
}
