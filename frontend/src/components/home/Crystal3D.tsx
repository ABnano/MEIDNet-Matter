import { useEffect, useRef, useState } from 'react';
import { home as H } from '@/copy/research';
import { loadScript } from './loadScript';

/** MEIDNet Prism's crystal: a cubic ABX3 perovskite turning slowly, with its crystal graph, the shared latent space and a
 *  band-gap curve behind it; a drag turns it by hand. Drawn by prism-hero.js (served from /tour/, after prism3d.js), the
 *  scene of the Prism landing page, so the two sites show the method with one picture. */
const SCRIPTS = ['/tour/prism3d.js', '/tour/prism-hero.js'];

type Scene = { redraw: () => void; destroy: () => void };

declare global {
  interface Window { PrismHero?: { mount: (canvas: HTMLCanvasElement) => Scene | null } }
}

export function Crystal3D() {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    let scene: Scene | null = null;
    (async () => {
      try {
        for (const src of SCRIPTS) await loadScript(src);
        if (alive && canvas.current) scene = window.PrismHero?.mount(canvas.current) ?? null;
      } catch { if (alive) setFailed(true); }
    })();
    const obs = new MutationObserver(() => { scene?.redraw(); });   // this app's theme switch
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => { alive = false; obs.disconnect(); scene?.destroy(); };
  }, []);
  return (
    <figure className="scene">
      <canvas id="hero3d" ref={canvas} role="img" aria-label={H.crystalAria}></canvas>
      <figcaption>{failed ? H.crystalFallback : H.crystalCaption}</figcaption>
    </figure>
  );
}
