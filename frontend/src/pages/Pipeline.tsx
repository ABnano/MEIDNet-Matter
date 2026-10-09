import { Link } from 'react-router';
import { STUDY_DATASETS } from '@/copy/research';
import { research, type BlocksPayload } from '@/api/research';
import { useResource } from '@/api/hooks';
import { MarketingHeader, SiteFooter } from '@/components/shell';
import { ErrorNote, Spinner } from '@/components/ui';
import { VerdictText } from '@/components/research';
import { PipelineOverview } from '@/components/pipeline/Flow';
import { pipeline as P } from '@/copy/research';

const DATASETS = STUDY_DATASETS;

export default function Pipeline() {
  const { data, error, loading, reload } = useResource<BlocksPayload>('pipeline/blocks', (s) => research.blocks(s));
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow page" id="main">
        <div className="page-head"><h1>{P.h1}</h1><p>{P.lead}</p><p className="small muted">Each block page shows its metrics, bands, meaning and the code that computes it. To run the blocks on your own data, follow <Link to="/method#run">the steps on the Method page</Link>.</p></div>
        {error && <ErrorNote error={error} retry={reload} />}
        {loading && <Spinner label="Loading the blocks" />}
        {data && (
          <>
            <PipelineOverview blocks={data.blocks} verdicts={data.dataset_verdicts} />
            <h2>The ten blocks</h2>
            <div className="block-list">
              {data.blocks.map((b) => (
                <div className="card block-row" key={b.id}>
                  <div className="bid">{b.id}</div>
                  <div>
                    <h3 style={{ marginBottom: 4 }}><Link to={`/pipeline/${b.id}`}>{b.name}</Link></h3>
                    <p className="muted small" style={{ margin: 0 }}>{b.question}</p>
                    <p className="small" style={{ margin: '6px 0 0' }}>{b.purpose}</p>
                    <div className="small faint" style={{ marginTop: 6 }}>
                      runs: {b.when} · {b.metrics.length} metrics · code: {b.components.map((c) => c.file).join(', ') || '—'}
                    </div>
                  </div>
                  <div className="small block-verdicts">
                    <div className="micro muted">verdict on each dataset</div>
                    {DATASETS.map(([id, label]) => (
                      <div key={id} className="block-verdict">{label} <VerdictText grade={data.dataset_verdicts?.[id]?.[b.id] ?? '—'} route={b.id === 'S0' ? data.dataset_routes?.[id] : null} /></div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <p className="note" style={{ marginTop: 20 }}>{P.howToRead}</p>
            <p className="small muted" style={{ marginTop: 8 }}>{P.gradeLegend}</p>

            <section className="section" id="history">
              <h2>{P.historyTitle}</h2>
              <p className="muted">{P.historyLead}</p>
              <div className="stack" style={{ gap: 20 }}>
                {data.dataset_history.map((h) => (
                  <div className="card" key={h.dataset}>
                    <h3>{h.dataset}</h3>
                    <p className="small muted">{h.description}</p>
                    <div className="table-wrap">
                      <table className="table">
                        <thead><tr><th scope="col">block</th><th scope="col">what this dataset forced</th></tr></thead>
                        <tbody>{h.items.map((it, i) => <tr key={i}><td className="mono">{it.blocks}</td><td className="small">{it.text}</td></tr>)}</tbody>
                      </table>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </>
        )}
      </main>
      <SiteFooter />
    </>
  );
}
