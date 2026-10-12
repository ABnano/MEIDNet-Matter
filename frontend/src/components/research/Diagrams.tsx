import type { CSSProperties } from 'react';

/** One box of a diagram: a title, a line of explanation and its colour (a CSS colour or a token such as var(--c-data)). */
export type DiagramBox = { title: string; sub: string; color: string };

const tint = (color: string) => ({ '--k': color }) as CSSProperties;

/** A workflow as coloured steps joined by arrows, in the palette of MEIDNet Prism's diagrams: a row on wide screens, a
 *  column on narrow ones. The steps are an ordered list, so a screen reader reads them in order. */
export function FlowDiagram({ steps, caption, testId }: { steps: DiagramBox[]; caption: string; testId?: string }) {
  return (
    <figure className="flow" data-testid={testId}>
      <ol className="flow-steps" style={{ '--n': steps.length } as CSSProperties}>
        {steps.map((s, i) => (
          <li className="flow-step" key={s.title} style={tint(s.color)}>
            <span className="flow-n">{String(i + 1).padStart(2, '0')}</span>
            <b>{s.title}</b>
            <span className="flow-sub">{s.sub}</span>
          </li>
        ))}
      </ol>
      <figcaption className="small muted">{caption}</figcaption>
    </figure>
  );
}

/** A decision taken once: an input, the gate that decides, the routes it can choose (side by side), and the check every
 *  route ends with. */
export function RouteDiagram({ input, gate, routes, check, caption, testId }: {
  input: DiagramBox; gate: DiagramBox; routes: DiagramBox[]; check: DiagramBox; caption: string; testId?: string;
}) {
  const box = (b: DiagramBox, cls: string) => <div className={`route-box ${cls}`} style={tint(b.color)}><b>{b.title}</b><span>{b.sub}</span></div>;
  return (
    <figure className="route" data-testid={testId}>
      {box(input, 'route-in')}
      {box(gate, 'route-gate')}
      <div className="route-outs">{routes.map((r) => <div className="route-box" key={r.title} style={tint(r.color)}><b>{r.title}</b><span>{r.sub}</span></div>)}</div>
      {box(check, 'route-check')}
      <figcaption className="small muted">{caption}</figcaption>
    </figure>
  );
}
