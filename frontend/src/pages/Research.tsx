import { Link } from 'react-router';
import { research, type Accepted, type BlocksPayload, type Study, type StudyIndexEntry } from '@/api/research';
import { useResource } from '@/api/hooks';
import { MarketingHeader, SiteFooter } from '@/components/shell';
import { ResearchLayout } from '@/components/research/ResearchNav';
import { ErrorNote, Spinner } from '@/components/ui';
import { Funnel, Num } from '@/components/research';
import { Explainer } from '@/components/home/Explainer';
import { home as H } from '@/copy/research';

const score = (a: Accepted) => (a.class.startsWith('new composition') ? 4 : 0) + (a.charge_balanced ? 2 : 0) + (a.requested >= 1 && a.requested <= 3 ? 3 : 0) + (a.flag ? -2 : 0);

/** The research hub: what the journey rests on, kept whole and one step away from the front door. */
export default function Research() {
  const mp20 = useResource<Study>('studies/mp20', (s) => research.study('mp20', s));
  const idx = useResource<{ studies: StudyIndexEntry[] }>('studies', (s) => research.studies(s));
  const blocks = useResource<BlocksPayload>('pipeline/blocks', (s) => research.blocks(s));
  const cal = mp20.data?.calibration;
  const accepted = mp20.data?.accepted ?? [];
  const example = [...accepted].sort((a, b) => score(b) - score(a)).find((a) => a.structure) ?? null;
  return (
    <>
      <MarketingHeader wide />
      <ResearchLayout>
        <div className="page-head"><h1>{H.overviewTitle}</h1><p>{H.researchLead}</p></div>
        {mp20.error && <ErrorNote error={mp20.error} retry={mp20.reload} />}
        {mp20.loading && <Spinner label="Loading the studies" />}

        <section className="section" id="walkthrough">
          <h2>{H.walkthroughTitle}</h2>
          <p className="muted">{H.walkthroughLead}</p>
          {example && <Explainer example={example} />}
        </section>

        <section className="section" id="featured">
          <h2>{H.featuredTitle}</h2>
          <p className="muted">{H.featuredLead}</p>
          {cal && (
            <div className="featured">
              <div className="card">
                <Funnel stages={[['generated', cal.funnel.generated], ['both judges, generated cell', cal.funnel.both_judges], ['relaxed, sound and bulk-like', cal.funnel.relaxed], ['both judges, relaxed cell', cal.funnel.final]]} />
                <div className="table-wrap" style={{ marginTop: 12 }}>
                  <table className="table small">
                    <caption className="sr-only">Per requested band gap</caption>
                    <thead><tr><th scope="col">requested</th><th scope="col">generated</th><th scope="col">accepted</th><th scope="col">delivered mean</th><th scope="col">sd</th></tr></thead>
                    <tbody>{cal.per_target.map((p) => <tr key={p.requested}><td className="num">{p.requested.toFixed(1)} eV</td><td className="num">{p.generated}</td><td className="num">{p.final}</td><td className="num"><Num v={p.delivered_mean} /></td><td className="num"><Num v={p.delivered_sd} /></td></tr>)}</tbody>
                  </table>
                </div>
              </div>
              <div className="card">
                <h3>What this does and does not show</h3>
                <ul className="small muted" style={{ margin: '0 0 0 18px' }}>
                  <li>Response: delivered = {cal.linearity.intercept.toFixed(2)} + {cal.linearity.slope.toFixed(2)}·requested; MAE <Num v={cal.accuracy.mae_relaxed_cells} /> eV on relaxed cells; served range {cal.range.served[0]}–{cal.range.served[cal.range.served.length - 1]} eV.</li>
                  {(mp20.data?.limits ?? []).slice(0, 4).map((l) => <li key={l}>{l}</li>)}
                </ul>
                <p style={{ marginTop: 10 }}><Link to="/studies/mp20">The full study →</Link></p>
              </div>
            </div>
          )}
        </section>

        <section className="section" id="pipeline">
          <h2>{H.pipelineTitle}</h2>
          <p className="muted">{H.pipelineLead}</p>
          {blocks.data && <div className="block-strip">{blocks.data.blocks.map((b) => <Link key={b.id} to={`/pipeline/${b.id}`} title={b.question}>{b.id}</Link>)}</div>}
          <p style={{ marginTop: 12 }}><Link to="/pipeline">Open the pipeline →</Link></p>
        </section>

        <section className="section" id="studies">
          <h2>{H.studiesTitle}</h2>
          <p className="muted">{H.studiesLead}</p>
          {idx.data && (
            <div className="cards-2">
              {idx.data.studies.sort((a, b) => a.order - b.order).map((s) => (
                <div className="card" key={s.id}>
                  <div className="micro">{s.dataset} · {s.mode}</div>
                  <h3>{s.title}</h3>
                  <p className="muted small">{s.headline}</p>
                  <Link to={`/studies/${s.id}`} className="small">Open the study →</Link>
                </div>
              ))}
            </div>
          )}
          <p style={{ marginTop: 12 }}><Link to="/method">Methodology: mechanism, strengths and limits →</Link></p>
        </section>
      </ResearchLayout>
      <SiteFooter wide />
    </>
  );
}
