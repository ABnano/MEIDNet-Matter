import { useMemo } from 'react';
import { Link } from 'react-router';
import type { Accepted } from '@/api/research';
import { CellViewer } from '@/components/structure/CellViewer';
import { explicitStructure } from '@/lib/lattice';

export const cellOfAccepted = (a: Accepted) => (a.structure ? explicitStructure(a.structure.sites, a.structure.lattice) : null);
export const shortClass = (c: string) =>
  c.startsWith('new composition') ? 'new composition' : c.startsWith('new polymorph') ? 'new polymorph' : c.startsWith('rediscovered') ? 'known structure found again' : c;

function Card({ a, decorative }: { a: Accepted; decorative?: boolean }) {
  const cell = useMemo(() => cellOfAccepted(a), [a]);
  return (
    <Link to={`/studies/${a.study ?? 'mp20'}#accepted`} className="card card-tight disc-card" aria-hidden={decorative} tabIndex={decorative ? -1 : 0}>
      <div className="thumb">{cell && <CellViewer structure={cell} size={84} title={a.formula} interactive={false} />}</div>
      <div>
        <b>{a.formula}</b>
        <div className="small muted">asked {a.requested.toFixed(1)} eV · got <span className="num">{a.judge_gap.toFixed(2)}</span> eV</div>
        <div className="small faint">{shortClass(a.class)}{a.flag ? ` · ${a.flag}` : ''}</div>
      </div>
    </Link>
  );
}

/** The accepted structures of the MP-20 study rolling from right to left; pauses on hover or focus, and becomes a
 *  plain scrollable row when the visitor prefers reduced motion. The list is drawn twice so the loop has no seam;
 *  the second copy is decorative. */
export function DiscoveryStrip({ items }: { items: Accepted[] }) {
  if (items.length === 0) return null;
  return (
    <div className="disc-strip" aria-label="Structures the generator delivered">
      <div className="disc-track">
        {items.map((a) => <Card key={`${a.study}-${a.file}`} a={a} />)}
        {items.map((a) => <Card key={`${a.study}-${a.file}-copy`} a={a} decorative />)}
      </div>
    </div>
  );
}
