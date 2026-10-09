import type { ReactNode } from 'react';
import { STUDY_DATASETS } from '@/copy/research';
import { Link } from 'react-router';
import type { BlockDef, Grade } from '@/api/research';
import { VerdictText } from '@/components/research';

export type FlowNode = { id: string; kind: 'input' | 'code' | 'metric' | 'verdict'; label: string; sub?: ReactNode; onClick?: () => void; href?: string; active?: boolean; muted?: boolean; title?: string };

/** A left-to-right flow of boxes joined by arrows; it becomes a top-to-bottom flow on narrow screens. */
export function Flow({ nodes, ariaLabel }: { nodes: FlowNode[]; ariaLabel: string }) {
  return (
    <ol className="flow" aria-label={ariaLabel}>
      {nodes.map((n, i) => {
        const body = <><span className="flow-kind">{n.kind}</span><b>{n.label}</b>{n.sub && <span className="flow-sub">{n.sub}</span>}</>;
        const cls = `flow-node kind-${n.kind}${n.active ? ' active' : ''}${n.muted ? ' muted-node' : ''}`;
        return (
          <li key={n.id} className="flow-item">
            {i > 0 && <span className="flow-arrow" aria-hidden="true" />}
            {n.onClick ? <button type="button" className={cls} onClick={n.onClick} aria-pressed={n.active} title={n.title}>{body}</button>
              : n.href ? <Link to={n.href} className={cls} title={n.title}>{body}</Link>
              : <div className={cls} title={n.title}>{body}</div>}
          </li>
        );
      })}
    </ol>
  );
}

const INPUT_BY_WHEN: Record<string, string> = {
  preview: 'uploaded structures and property table', 'after training': 'trained model and its test split', 'after a run': 'generated structures and the run record',
};

/** The flow of one block: its input, the programs that compute it (click one to read the code), its metrics, its verdict. */
export function BlockFlow({ b, verdicts, routes, open, onOpen }: { b: BlockDef; verdicts: Record<string, Record<string, Grade>> | undefined; routes?: Record<string, string>; open: string | null; onOpen: (file: string | null) => void }) {
  const nodes: FlowNode[] = [
    { id: 'in', kind: 'input', label: INPUT_BY_WHEN[b.when] ?? b.when, sub: `runs ${b.when}` },
    ...b.components.map((c) => ({
      id: c.file, kind: 'code' as const, label: c.file, sub: c.runnable === 'web' ? 'runs here and locally' : c.runnable === 'hpc' ? 'cluster job' : 'runs locally',
      onClick: c.viewable ? () => onOpen(open === c.file ? null : c.file) : undefined, active: open === c.file, muted: !c.viewable,
      title: c.viewable ? `${c.note} — click to read the code` : `${c.note} — source not served`,
    })),
    ...b.metrics.filter((m) => !m.info_only).map((m) => ({ id: m.id, kind: 'metric' as const, label: m.name, sub: `meets ${m.band.pass}`, href: `#m-${m.id}`, title: m.definition })),
    { id: 'verdict', kind: 'verdict', label: 'verdict', sub: <>{STUDY_DATASETS.map(([id, l]) => <span key={id} className="flow-grade">{l} <VerdictText grade={verdicts?.[id]?.[b.id] ?? '—'} route={b.id === 'S0' ? routes?.[id] : null} /></span>)}</>, title: b.verdict_rule },
  ];
  return <Flow nodes={nodes} ariaLabel={`Workflow of block ${b.id}`} />;
}

/** The ten blocks as a workflow in three phases, each box opening its block page. */
export function PipelineOverview({ blocks, verdicts }: { blocks: BlockDef[]; verdicts: Record<string, Record<string, Grade>> | undefined }) {
  const phases: Array<[string, string, string]> = [['preview', 'Before training', 'Is the data usable?'], ['after training', 'After training', 'Does the model read, align, decode and judge correctly?'], ['after a run', 'After a run', 'Did the search follow the target, and what survives validation?']];
  const worst = (id: string) => { const g = STUDY_DATASETS.map(([d]) => verdicts?.[d]?.[id]).filter(Boolean) as Grade[]; return g.includes('FAIL') ? 'FAIL' : g.includes('WARN') ? 'WARN' : g.includes('PASS') ? 'PASS' : null; };
  return (
    <div className="overview" role="list" aria-label="The pipeline in three phases">
      {phases.map(([when, title, q], i) => (
        <div className="overview-phase" key={when} role="listitem">
          <div className="overview-head"><span className="mono" style={{ color: 'var(--p1)' }}>{i + 1}</span> <b>{title}</b><div className="small muted">{q}</div></div>
          <div className="overview-blocks">
            {blocks.filter((b) => b.when === when).map((b) => {
              const w = worst(b.id);
              return <Link key={b.id} to={`/pipeline/${b.id}`} className="overview-block" title={b.question}><span className="mono">{b.id}</span><span>{b.name}</span>{b.id === 'S0' ? <span className="small faint">decides the route the data supports: generation, screening or candidate sets</span> : w && <span className="small faint">weakest across datasets: <VerdictText grade={w} /></span>}</Link>;
            })}
          </div>
          {i < phases.length - 1 && <span className="overview-arrow" aria-hidden="true" />}
        </div>
      ))}
    </div>
  );
}
