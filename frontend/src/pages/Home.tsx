import { Link } from 'react-router';
import { research, type Accepted, type Study } from '@/api/research';
import { useResource } from '@/api/hooks';
import { ExternalLink, MarketingHeader, PRISM_SPACE, SiteFooter } from '@/components/shell';
import { ErrorNote, Spinner } from '@/components/ui';
import { DiscoveryStrip } from '@/components/home/DiscoveryStrip';
import { HeroExample } from '@/components/home/HeroExample';
import { Tour3D } from '@/components/home/Tour3D';
import { Crystal3D } from '@/components/home/Crystal3D';
import { home as H, researchNav as RN } from '@/copy/research';

/** Which accepted structure to show first: a new composition, charge balanced, asked for a gap between 1 and 3 eV. */
const score = (a: Accepted) => (a.class.startsWith('new composition') ? 4 : 0) + (a.charge_balanced ? 2 : 0) + (a.requested >= 1 && a.requested <= 3 ? 3 : 0) + (a.flag ? -2 : 0);

/** The front door: the headline beside MEIDNet Prism's turning crystal, then the one-minute tour of how it works, then a
 *  real result, the three stages, and the research one step away. */
export default function Home() {
  const mp20 = useResource<Study>('studies/mp20', (s) => research.study('mp20', s));
  const dp = useResource<Study>('studies/jarvis-dp', (s) => research.study('jarvis-dp', s));
  const perov5 = useResource<Study>('studies/perov5', (s) => research.study('perov5', s));
  const cal = mp20.data?.calibration;
  const accepted = mp20.data?.accepted ?? [];
  const newComp = accepted.filter((a) => a.class.startsWith('new composition')).length;
  const redisc = accepted.filter((a) => a.class.startsWith('rediscovered'));
  const polymorphs = accepted.filter((a) => a.class.startsWith('new polymorph')).length;
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;
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
          <Crystal3D />
        </section>

        <section className="section how" id="how">
          <div className="how-head">
            <div className="micro">{H.tourTitle}</div>
            <h2>{H.ideaTitle}</h2>
            <p className="muted">{H.ideaText}</p>
            <p className="small muted">{H.ideaPrism} <ExternalLink href={PRISM_SPACE}>{H.prismCta} ↗</ExternalLink></p>
          </div>
          <Tour3D />
        </section>

        <section className="section hero-result" id="result">
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

        <section className="section" id="discoveries">
          <h2>{H.discoveriesTitle}</h2>
          <p className="muted">{H.discoveriesLead}</p>
          {perov5.error && <ErrorNote error={perov5.error} />}
          <DiscoveryStrip items={[...accepted.map((a) => ({ ...a, study: 'mp20' })), ...(dp.data?.accepted ?? []).filter((a) => a.class.startsWith('new composition')).map((a) => ({ ...a, study: 'jarvis-dp' }))]} />
          {cal && <p className="small muted" style={{ marginTop: 10 }}>{cal.funnel.final} of {cal.funnel.generated} generated cells accepted{cal.funnel.collapsed_on_relaxation || cal.funnel.not_bulk_on_relaxation ? ` (after relaxation ${cal.funnel.collapsed_on_relaxation ?? 0} cells collapsed and ${cal.funnel.not_bulk_on_relaxation ?? 0} were slabs or sparse cells; all set aside)` : ''} · {plural(newComp, 'new composition')} · {plural(polymorphs, 'new polymorph')} of known formulas{redisc.length > 0 ? ` · ${plural(redisc.length, 'known structure')} found again at its recorded gap (${redisc.map((r) => r.formula).join(', ')})` : ''}{perov5.data ? ` · Perov-5 target following ρ ${(perov5.data.target_following.rho_range as number[])[0]}–${(perov5.data.target_following.rho_range as number[])[1]}` : ''}. <Link to="/studies/mp20#accepted">Every accepted structure, with its evidence.</Link></p>}
          {dp.data?.accepted && <p className="small muted" style={{ marginTop: 4 }}>Double perovskites on public JARVIS-DFT data: {dp.data.accepted.length} accepted across {dp.data.routes?.length ?? 0} routes, {dp.data.accepted.filter((a) => a.class.startsWith('new composition')).length} of them compositions absent from the data and from JARVIS-DFT. <Link to="/studies/jarvis-dp#accepted">The case study →</Link></p>}
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
          <div className="card"><h3>Open source</h3><p className="muted">The code of Matter is on GitHub under the MIT licence; the engine is the MEIDNet package, vendored here as a snapshot with its provenance recorded. The same three stages run from Python against this server (Method › Python).</p><ExternalLink href="https://github.com/ABnano/MEIDNet-Matter" className="btn">GitHub ↗</ExternalLink></div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
