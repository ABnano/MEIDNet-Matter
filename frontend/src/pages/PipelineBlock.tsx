import { useState } from 'react';
import { Link, useParams } from 'react-router';
import { research, type BlocksPayload } from '@/api/research';
import { useResource } from '@/api/hooks';
import { MarketingHeader, SiteFooter } from '@/components/shell';
import { ResearchLayout } from '@/components/research/ResearchNav';
import { ErrorNote, Spinner } from '@/components/ui';
import { CodeViewer, VerdictText } from '@/components/research';
import { BlockFlow } from '@/components/pipeline/Flow';
import { pipeline as P, researchNav } from '@/copy/research';

const fmt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : Number.isInteger(v) ? String(v) : v.toFixed(v < 1 ? 3 : 2));

export default function PipelineBlock() {
  const { block = 'S0' } = useParams();
  const id = block.toUpperCase();
  const { data, error, loading, reload } = useResource<BlocksPayload>('pipeline/blocks', (s) => research.blocks(s));
  const [open, setOpen] = useState<string | null>(null);
  const b = data?.blocks.find((x) => x.id === id);
  const configs = data ? Object.keys(data.configs) : [];
  return (
    <>
      <MarketingHeader wide />
      <ResearchLayout>
        {error && <ErrorNote error={error} retry={reload} />}
        {loading && <Spinner label="Loading the block" />}
        {data && !b && <div className="page-head"><h1>No block {id}</h1><Link to="/pipeline">All blocks</Link></div>}
        {b && (
          <>
            <div className="page-head">
              <div className="micro"><Link to="/pipeline">{researchNav.pipeline}</Link> · block {b.id} · runs {b.when}</div>
              <h1>{b.id} · {b.name}</h1>
              <p><b>{b.question}</b> {b.purpose}</p>
              <p className="small muted">Verdict rule: {b.verdict_rule}.</p>
            </div>

            <h2>How this block works</h2>
            <p className="muted small">{P.flowLead}</p>
            <BlockFlow b={b} verdicts={data?.dataset_verdicts} routes={data?.dataset_routes} open={open} onOpen={setOpen} />
            {b.components.filter((c) => c.file === open).map((c) => (
              <div key={c.file} style={{ marginTop: 12 }}>
                <p className="small muted">{c.note}{c.needs.length ? ` · needs ${c.needs.join(', ')}` : ''}</p>
                <CodeViewer file={c.file} />
              </div>
            ))}

            <h2 style={{ marginTop: 32 }}>Metrics and bands</h2>
            <div className="table-wrap">
              <table className="table">
                <caption className="sr-only">Metrics of block {b.id}</caption>
                <thead><tr><th scope="col">metric</th><th scope="col">unit</th><th scope="col">meets</th><th scope="col">borderline</th><th scope="col">not met</th>{configs.map((c) => <th scope="col" key={c}>{c}</th>)}</tr></thead>
                <tbody>
                  {b.metrics.map((m) => (
                    <tr key={m.id}>
                      <td><b>{m.name}</b>{m.info_only && <span className="small faint"> · context only</span>}<div className="small muted">{m.definition}</div></td>
                      <td className="small">{m.unit}</td>
                      <td className="mono small">{m.band.pass}</td><td className="mono small">{m.band.warn}</td><td className="mono small">{m.band.fail}</td>
                      {configs.map((c) => (
                        <td key={c} className="num small">{m.reference[c] !== undefined ? <>{fmt(m.reference[c])} <VerdictText grade={m.reference_grades[c]} /></> : <span className="faint">—</span>}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h2 style={{ marginTop: 32 }}>What each metric means</h2>
            <div className="stack" style={{ gap: 12 }}>
              {b.metrics.map((m) => (
                <div className="card card-tight" key={m.id} id={`m-${m.id}`}>
                  <h3 style={{ marginBottom: 6 }}>{m.name} <span className="small faint mono">{m.id}</span></h3>
                  <dl className="kv">
                    <dt>when good</dt><dd>{m.meaning_good}</dd>
                    <dt>when bad</dt><dd>{m.meaning_bad}</dd>
                    <dt>remedy</dt><dd>{m.remedy}</dd>
                    <dt>computed by</dt><dd className="mono small">{m.computed_by}</dd>
                    {m.reference_note && <><dt>measured</dt><dd className="small">{m.reference_note}</dd></>}
                    {m.new_dataset_note && <><dt>on a new dataset</dt><dd className="small">{m.new_dataset_note}</dd></>}
                    {m.superseded_by && <><dt>superseded by</dt><dd className="small">{m.superseded_by} once it is measured</dd></>}
                    {m.cap && <><dt>worst grade</dt><dd className="small">{m.cap} (a scope limit, not a defect)</dd></>}
                  </dl>
                </div>
              ))}
            </div>
            {b.caveats.length > 0 && <div className="note" style={{ marginTop: 16 }}>{b.caveats.map((c, i) => <p key={i} style={{ margin: i ? '8px 0 0' : 0 }}>{c}</p>)}</div>}

            <h2 style={{ marginTop: 32 }}>The code</h2>
            <p className="muted">{P.codeLead}</p>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              {b.components.map((c) => (
                <button type="button" key={c.file} className={`btn btn-sm ${open === c.file ? 'btn-primary' : ''}`} disabled={!c.viewable} onClick={() => setOpen(open === c.file ? null : c.file)}
                  title={c.note}>{c.file}{c.runnable !== 'web' ? ` · ${c.runnable}` : ''}</button>
              ))}
            </div>
            {open && <p className="small muted">The source of {open} is open above, under the workflow diagram.</p>}
            <div style={{ marginTop: 24 }} className="row">
              {data?.blocks.map((x) => <Link key={x.id} to={`/pipeline/${x.id}`} className={`btn btn-sm ${x.id === b.id ? 'btn-primary' : ''}`}>{x.id}</Link>)}
            </div>
          </>
        )}
      </ResearchLayout>
      <SiteFooter wide />
    </>
  );
}
