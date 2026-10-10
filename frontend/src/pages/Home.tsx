import { Link } from 'react-router';
import { research, type Accepted, type Study } from '@/api/research';
import { useResource } from '@/api/hooks';
import { ExternalLink, MarketingHeader, PRISM_SPACE, SiteFooter } from '@/components/shell';
import { ErrorNote, Spinner } from '@/components/ui';
import { HeroExample } from '@/components/home/HeroExample';
import { home as H, researchNav as RN } from '@/copy/research';
import { landing as L } from '@/copy/landing';

/** Which accepted structure to show first: a new composition, charge balanced, asked for a gap between 1 and 3 eV. */
const score = (a: Accepted) => (a.class.startsWith('new composition') ? 4 : 0) + (a.charge_balanced ? 2 : 0) + (a.requested >= 1 && a.requested <= 3 ? 3 : 0) + (a.flag ? -2 : 0);

/** The front door: one headline, one example, the three stages, and the research one step away. */
export default function Home() {
  const mp20 = useResource<Study>('studies/mp20', (s) => research.study('mp20', s));
  const accepted = mp20.data?.accepted ?? [];
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
              <Link to="/explore" className="btn btn-primary btn-lg" data-testid="cta-explore">{H.ctaExplore}</Link>
              <Link to="/generate" className="btn btn-lg">{H.ctaGenerate}</Link>
            </div>
            <div className="scope-line">{H.example} <Link to="/p/perov5-demo/goal" data-testid="cta-demo">{H.ctaDemo} →</Link></div>
            <p className="plain">{H.plain}</p>
          </div>
          {mp20.data ? <HeroExample study={mp20.data} example={example} /> : <div className="hero-example">{mp20.loading && <Spinner label="Loading a result" />}{mp20.error && <ErrorNote error={mp20.error} />}</div>}
        </section>

        <section className="section" id="stages">
          <div className="cards-3 stages">
            {H.stages.map(([n, title, sub, text, to]) => (
              <Link to={to} className="card stage" key={n} data-testid={`stage-${title.toLowerCase()}`}>
                <div className="micro">{n}</div>
                <h2 style={{ margin: '4px 0 2px' }}>{title}</h2>
                <div className="muted">{sub}</div>
                <p className="small muted" style={{ marginTop: 8 }}>{text}</p>
                <span className="small">{title === 'Explore' ? 'Open the data →' : title === 'Train' ? 'Train a small model →' : 'Generate structures →'}</span>
              </Link>
            ))}
          </div>
          <p className="small muted" style={{ marginTop: 12 }}>{H.after} <Link to="/method#run">The commands →</Link></p>
        </section>

        <section className="section" id="research">
          <h2>{H.researchTitle}</h2>
          <p className="muted">{H.researchLead}</p>
          <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
            <Link to="/research" className="btn btn-primary">{RN.overview}</Link>
            <Link to="/studies" className="btn">{RN.studies}</Link>
            <Link to="/pipeline" className="btn">{RN.pipeline}</Link>
            <Link to="/method" className="btn">{RN.method}</Link>
          </div>
          <p className="small muted" style={{ marginTop: 12 }}>{H.prism} <ExternalLink href={PRISM_SPACE}>{H.prismCta} ↗</ExternalLink></p>
        </section>

        <section className="section">
          <div className="cards-2">
            <div className="card"><h3>Open source</h3><p className="muted">The code of Matter is on GitHub under the MIT licence; the engine is the MEIDNet package, vendored here as a snapshot with its provenance recorded. The same three stages run from Python against this server (Method › Python).</p><ExternalLink href="https://github.com/ABnano/MEIDNet-Matter" className="btn">GitHub ↗</ExternalLink></div>
            <div className="card"><h3>Citation</h3><p className="small muted">{L.citation}</p><ExternalLink href={`https://doi.org/${L.doi}`} className="small">doi:{L.doi}</ExternalLink></div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
