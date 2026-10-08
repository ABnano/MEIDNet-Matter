/** The static mirror: the same site built with `npm run build:mirror` (Vite mode "mirror") and served by GitHub Pages,
 *  an address public and institutional networks rarely block, unlike *.hf.space.  It reads the read-only API from
 *  files pre-rendered next to index.html (scripts/build_mirror.py), keeps its routes after '#', so any static host
 *  serves every page, and hands what computes live (generation, the demo search) to the Hugging Face Space. */
export const STATIC_MIRROR = import.meta.env.MODE === 'mirror';

export const SPACE_PAGE = 'https://huggingface.co/spaces/Babu09/MEIDNet-Matter';
export const SPACE_APP = 'https://babu09-meidnet-matter.hf.space';
export const MIRROR_URL = 'https://abnano.github.io/MEIDNet-Matter/';
/** Prism's documentation: the Space serves it under /docs, its own GitHub Pages mirror at the root. */
export const PRISM_MIRROR = 'https://abnano.github.io/MEIDNet/';

/** Where a pre-rendered response lives in the mirror, relative to the page:
 *  '/api/studies/mp20' -> 'static-api/api/studies/mp20.json', '/api/runs/x?view=full' -> 'static-api/api/runs/x@view=full.json';
 *  a raw file (a component's source, a study file) keeps its own name: '/api/studies/mp20/files/a.cif' -> 'static-api/api/studies/mp20/files/a.cif'. */
export function staticPath(path: string, kind: 'json' | 'raw' = 'json'): string {
  const [route, query] = path.replace(/^\/+/, '').split('?', 2);
  const name = query ? `${route}@${query}` : route;
  return `static-api/${name}${kind === 'json' ? '.json' : ''}`;
}

/** The address of an API resource for a link (download, open in a new tab): the server's path, or the mirror's file. */
export const apiUrl = (path: string, kind: 'json' | 'raw' = 'raw') => (STATIC_MIRROR ? staticPath(path, kind) : path);
