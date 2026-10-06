import { Link } from 'react-router';
import { ExternalLink, GITHUB, MarketingHeader, PRISM, SiteFooter } from '@/components/shell';
import { CellViewer } from '@/components/structure/CellViewer';
import { Site } from '@/components/ui';
import { landing as L, previewCandidates, previewRequest } from '@/copy/landing';
import { prototypeStructure } from '@/lib/lattice';

const SITES: Array<{ group: string; frac: [number, number, number] }> = [
  { group: 'A', frac: [0, 0, 0] }, { group: 'B', frac: [0.5, 0.5, 0.5] }, { group: 'X', frac: [0.5, 0.5, 0] }, { group: 'X', frac: [0.5, 0, 0.5] }, { group: 'X', frac: [0, 0.5, 0.5] },
];

export default function Landing() {
  const hero = prototypeStructure(SITES, { A: 'La', B: 'Mn', X: 'O' }, { lattice: 'cubic' }, 3.9);
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow">
        <section className="hero">
          <div>
            <div className="eyebrow">{L.eyebrow} · {L.descriptor}</div>
            <h1>{L.h1}</h1>
            <p className="lead">{L.lead}</p>
            <div className="promise">{L.promise}</div>
            <div className="ctas">
              <Link to="/p/perov5-demo/goal" className="btn btn-primary btn-lg" data-testid="cta-demo">{L.ctaPrimary}</Link>
              <Link to="/start-with-my-data" className="btn btn-lg">{L.ctaSecondary}</Link>
            </div>
            <div className="trust">{L.trust}</div>
          </div>
          <figure className="hero-art">
            <div style={{ width: 260 }}><CellViewer structure={hero} size={260} title="LaMnO3" labels /></div>
            <figcaption>cubic ABX₃ perovskite · drag to rotate</figcaption>
          </figure>
        </section>

        <section className="section" id="preview">
          <h2>{L.previewTitle}</h2>
          <p className="muted">{L.previewLead}</p>
          <div className="preview">
            <div className="card">
              <div className="micro" style={{ marginBottom: 8 }}>Design request</div>
              <div className="stack" style={{ gap: 6 }}>
                <div><b>Direct band gap</b> <span className="num">{previewRequest.gap}</span></div>
                <div><b>Formation enthalpy</b> <span className="num">{previewRequest.dhf}</span></div>
                <div><b>Excluded</b> <span className="num">{previewRequest.excluded}</span></div>
                <div><b>Family</b> {previewRequest.family}</div>
              </div>
            </div>
            <div className="arrow" aria-hidden="true">→</div>
            <div className="stack">
              <span className="ribbon">Demonstration data from a run of this request</span>
              <div className="cards-3">
                {previewCandidates.map((c) => (
                  <div className="card card-tight ccard" key={c.formula}>
                    <div className="thumb"><CellViewer structure={prototypeStructure(SITES, c.elements, { lattice: 'cubic' }, c.a)} size={96} title={c.formula} interactive={false} /></div>
                    <div>
                      <h3>{c.formula}</h3>
                      <div className="row" style={{ gap: 6 }}>{Object.entries(c.elements).map(([g, e]) => <Site key={g} group={g} element={e} />)}</div>
                      <div className="lines" style={{ marginTop: 6 }}>
                        <div>Band gap <b className="num">{c.gap} eV</b> · ΔHf <b className="num">{c.dhf} eV/atom</b> <span className="faint">Predicted</span></div>
                        <div>{c.domain} · Rule passed {c.rules} · encoder and search {c.agreement}</div>
                        <div className="faint">{c.novelty} · Not screened</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="section" id="how">
          <h2>How it works</h2>
          <div className="cards-4">
            {L.how.map(([t, d], i) => <div className="card step-card" key={t}><div className="n">{i + 1}</div><h3>{t}</h3><p className="muted small">{d}</p></div>)}
          </div>
        </section>

        <section className="section" id="why">
          <h2>Why Matter</h2>
          <div className="cards-2">
            {L.why.map(([t, d]) => <div className="card" key={t}><h3>{t}</h3><p className="muted">{d}</p></div>)}
          </div>
        </section>

        <section className="section" id="applications">
          <h2>Example applications</h2>
          <div className="cards-3">
            {L.applications.map(([t, d]) => <div className="card" key={t}><h3>{t}</h3><p className="muted small">{d}</p><Link to="/p/perov5-demo/goal" className="small">Open the demo project →</Link></div>)}
          </div>
          <p className="note" style={{ marginTop: 20 }}>{L.scope}</p>
        </section>

        <section className="section" id="ecosystem">
          <h2>The MEIDNet ecosystem</h2>
          <div className="cards-2">
            {L.ecosystem.map(([name, sub, d]) => (
              <div className="card" key={name}>
                <div className="micro">{sub}</div>
                <h3>{name}</h3>
                <p className="muted">{d}</p>
                {name.endsWith('Prism') ? <ExternalLink href={PRISM}>Open MEIDNet Prism ↗</ExternalLink> : <span className="small faint">You are here.</span>}
              </div>
            ))}
          </div>
        </section>

        <section className="section">
          <div className="cards-2">
            <div className="card">
              <h3>Open source</h3>
              <p className="muted">The code of Matter is on GitHub under the MIT licence; the engine, MEIDNet, is a Python package.</p>
              <ExternalLink href={GITHUB} className="btn">GitHub ↗</ExternalLink>
            </div>
            <div className="card">
              <h3>Citation</h3>
              <p className="small muted">{L.citation}</p>
              <ExternalLink href={`https://doi.org/${L.doi}`} className="small">doi:{L.doi}</ExternalLink>
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
