import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { MIRROR_URL, SPACE_APP, SPACE_PAGE, STATIC_MIRROR } from '@/lib/mirror';

type Reach = 'checking' | 'reachable' | 'blocked';

let probe: Promise<Reach> | null = null;

/** Can this browser reach the live Space?  An opaque request to its health route: it resolves when the address
 *  answers at all and fails when the network blocks or cannot resolve *.hf.space, which is the one fact needed here. */
function reachSpace(): Promise<Reach> {
  if (!probe) {
    probe = (async () => {
      const ctl = new AbortController();
      const timer = setTimeout(() => ctl.abort(), 8000);
      try {
        await fetch(`${SPACE_APP}/health`, { mode: 'no-cors', cache: 'no-store', signal: ctl.signal });
        return 'reachable' as const;
      } catch {
        return 'blocked' as const;
      } finally {
        clearTimeout(timer);
      }
    })();
  }
  return probe;
}

/** Only the mirror asks: on the Space itself the live server is the page's own origin. */
export function useSpaceReach(): Reach {
  const [reach, setReach] = useState<Reach>(STATIC_MIRROR ? 'checking' : 'reachable');
  useEffect(() => {
    if (!STATIC_MIRROR) return;
    let live = true;
    reachSpace().then((r) => { if (live) setReach(r); });
    return () => { live = false; };
  }, []);
  return reach;
}

const SECURE_DNS = 'turn on secure DNS in the browser (Chrome and Edge: Settings → Privacy and security → Security → Use secure DNS; Firefox: Settings → Privacy & Security → DNS over HTTPS), or use another network';

function ReachLine({ reach }: { reach: Reach }) {
  if (reach === 'checking') return <span className="muted">checking whether the live server is reachable from this network…</span>;
  if (reach === 'reachable') return <span>the live server is reachable from this network: <a href={SPACE_APP} target="_blank" rel="noopener">open the live app ↗</a></span>;
  return <span>this network does not reach the live server (*.hf.space); to use it, {SECURE_DNS}.</span>;
}

/** One line at the top of every page of the mirror: where the visitor is, and whether the live parts are reachable. */
export function MirrorBanner() {
  const reach = useSpaceReach();
  if (!STATIC_MIRROR) return null;
  return (
    <div className="banner banner-info mirror-banner" role="note">
      <b>Mirror on GitHub Pages.</b> Everything here can be read and explored on any network; live generation and the demo search run on the
      {' '}<a href={SPACE_PAGE} target="_blank" rel="noopener">Hugging Face Space</a>. <ReachLine reach={reach} />
    </div>
  );
}

/** In the mirror, a page that computes live: what it does, and the two ways to the live server. */
export function LiveOnly({ title, what, path = '/' }: { title: string; what: string; path?: string }) {
  const reach = useSpaceReach();
  return (
    <div className="stack" style={{ maxWidth: '72ch' }}>
      <div className="page-head"><h1>{title}</h1><p>{what}</p></div>
      <div className="card stack">
        <p style={{ margin: 0 }}>This page computes on the live server, which this mirror does not have. Everything else (the studies, the
          staged pipeline with its code, the method, the checkpoints) works here.</p>
        <div className="row">
          <a className="btn btn-primary" href={`${SPACE_APP}${path}`} target="_blank" rel="noopener">Open this page on the live app ↗</a>
          <a className="btn" href={SPACE_PAGE} target="_blank" rel="noopener">The Space on Hugging Face ↗</a>
          <Link className="btn btn-ghost" to="/studies">Explore the studies here</Link>
        </div>
        <p className="small" style={{ margin: 0 }}><ReachLine reach={reach} /></p>
        <p className="small muted" style={{ margin: 0 }}>To run everything on your own computer instead, see the Method page's guide; this mirror's address is {MIRROR_URL}.</p>
      </div>
    </div>
  );
}
