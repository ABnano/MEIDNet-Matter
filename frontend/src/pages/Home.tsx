import { Link } from 'react-router';
import { research, type Accepted, type BlocksPayload, type Study, type StudyIndexEntry } from '@/api/research';
import { useResource } from '@/api/hooks';
import { ExternalLink, GITHUB, MarketingHeader, SiteFooter } from '@/components/shell';
import { ErrorNote, Spinner } from '@/components/ui';
import { Funnel, Num, VerdictText } from '@/components/research';
import { DiscoveryStrip } from '@/components/home/DiscoveryStrip';
import { HeroExample } from '@/components/home/HeroExample';
import { Explainer } from '@/components/home/Explainer';
import { home as H } from '@/copy/research';
import { landing as L } from '@/copy/landing';

/** Which accepted structure to show first: a new composition, charge balanced, asked for a gap between 1 and 3 eV. */
const score = (a: Accepted) => (a.class.startsWith('new composition') ? 4 : 0) + (a.charge_balanced ? 2 : 0) + (a.requested >= 1 && a.requested <= 3 ? 3 : 0) + (a.flag ? -2 : 0);

export default function Home() {
  const mp20 = useResource<Study>('studies/mp20', (s) => research.study('mp20', s));
  const perov5 = useResource<Study>('studies/perov5', (s) => research.study('perov5', s));
  const idx = useResource<{ studies: StudyIndexEntry[] }>('studies', (s) => research.studies(s));
  const blocks = useResource<BlocksPayload>('pipeline/blocks', (s) => research.blocks(s));
  const cal = mp20.data?.calibration;
  const accepted = mp20.data?.accepted ?? [];
  const newComp = accepted.filter((a) => a.class.startsWith('new composition')).length;
  const redisc = accepted.filter((a) => a.class.startsWith('rediscovered'));
  const example = [...accepted].sort((a, b) => score(b) - score(a)).find((a) => a.structure) ?? null;
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow" id="main">
        <section className="hero">
          <div>
            <div className="eyebrow">{H.eyebrow}</div>
            <h1>{H.h1}</h1>
            <p className="lead">{H.lead}</p>
            <div className="ctas">
              <Link to="/studies/mp20" className="btn btn-primary btn-lg">{H.ctaExplore}</Link>
              <Link to="/play" className="btn btn-lg">{H.ctaPlay}</Link>
              <Link to="/p/perov5-demo/goal" className="btn btn-lg btn-ghost" data-testid="cta-demo">{H.ctaDemo}</Link>
            </div>
            <div className="scope-line">{H.scope}</div>
            <p className="plain">{H.plain}</p>
          </div>
          {mp20.data ? <HeroExample study={mp20.data} example={example} /> : <div className="hero-example">{mp20.loading && <Spinner label="Loading a result" />}{mp20.error && <ErrorNote error={mp20.error} />}</div>}
        </section>

        <section className="section" id="walkthrough">
          <h2>How it works, in six steps</h2>
          <p className="muted">An animated walkthrough on a real result: press play, or step through it. One sentence for a newcomer, one for a researcher.</p>
          {example && <Explainer example={example} />}
        </section>

        <section className="section" id="discoveries">
          <h2>{H.discoveriesTitle}</h2>
          <p className="muted">{H.discoveriesLead}</p>
          {perov5.error && <ErrorNote error={perov5.error} />}
          <DiscoveryStrip items={accepted} />
          {cal && <p className="small muted" style={{ marginTop: 10 }}>{cal.funnel.final} of {cal.funnel.generated} generated cells accepted · {newComp} new compositions · {redisc.length} known compounds returned at their recorded gaps ({redisc.map((r) => r.formula).join(', ')}){perov5.data ? ` · Perov-5 target following ρ ${(perov5.data.target_following.rho_range as number[])[0]}–${(perov5.data.target_following.rho_range as number[])[1]}` : ''}. <Link to="/studies/mp20#accepted">Every accepted structure, with its evidence.</Link></p>}
        </section>

        <section className="section" id="choices">
          <h2>{H.choicesTitle}</h2>
          <div className="choices">
            {H.choices.map(([t, d, to, cta]) => <div className="card" key={t}><h3>{t}</h3><p className="muted small">{d}</p><Link to={to} className="btn btn-sm">{cta}</Link></div>)}
          </div>
        </section>

        <section className="section" id="featured">
          <h2>{H.featuredTitle}</h2>
          <p className="muted">{H.featuredLead}</p>
          {cal && (
            <div className="featured">
              <div className="card">
                <Funnel stages={[['generated', cal.funnel.generated], ['both judges, generated cell', cal.funnel.both_judges], ['relaxed by two potentials', cal.funnel.relaxed], ['both judges, relaxed cell', cal.funnel.final]]} />
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
          {blocks.data && (
            <>
              <div className="block-strip">{blocks.data.blocks.map((b) => <Link key={b.id} to={`/pipeline/${b.id}`} title={b.question}>{b.id}</Link>)}</div>
              <div className="table-wrap" style={{ marginTop: 16 }}>
                <table className="table">
                  <caption className="sr-only">Block verdicts per dataset</caption>
                  <thead><tr><th scope="col">block</th><th scope="col">question</th><th scope="col">Perov-5</th><th scope="col">MP perovskites</th><th scope="col">Upload (246)</th><th scope="col">MP-20</th></tr></thead>
                  <tbody>
                    {blocks.data.blocks.map((b) => (
                      <tr key={b.id}>
                        <td className="mono"><Link to={`/pipeline/${b.id}`}>{b.id}</Link></td><td className="small">{b.question}</td>
                        {['perov5', 'mp-perovskites', 'user-246', 'mp20'].map((d) => <td key={d}><VerdictText grade={blocks.data!.dataset_verdicts?.[d]?.[b.id] ?? '—'} /></td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
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
        </section>

        <section className="section" id="try">
          <h2>{H.tryTitle}</h2>
          <p className="muted">{H.tryLead}</p>
          <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
            <Link to="/play" className="btn btn-primary">{H.ctaPlay}</Link>
            <Link to="/p/perov5-demo/goal" className="btn">{H.ctaDemo}</Link>
            <Link to="/method" className="btn btn-ghost">Mechanism, strengths and limits</Link>
          </div>
        </section>

        <section className="section">
          <div className="cards-2">
            <div className="card"><h3>Open source</h3><p className="muted">The code of Matter is on GitHub under the MIT licence; the engine is the MEIDNet package, vendored here as a snapshot with its provenance recorded.</p><ExternalLink href={GITHUB} className="btn">GitHub ↗</ExternalLink></div>
            <div className="card"><h3>Citation</h3><p className="small muted">{L.citation}</p><ExternalLink href={`https://doi.org/${L.doi}`} className="small">doi:{L.doi}</ExternalLink></div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
