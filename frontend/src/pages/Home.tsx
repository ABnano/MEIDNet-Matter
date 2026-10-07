import { Link } from 'react-router';
import { research, type BlocksPayload, type Study, type StudyIndexEntry } from '@/api/research';
import { useResource } from '@/api/hooks';
import { ExternalLink, GITHUB, MarketingHeader, SiteFooter } from '@/components/shell';
import { ErrorNote, Spinner } from '@/components/ui';
import { Num, VerdictText } from '@/components/research';
import { home as H } from '@/copy/research';
import { landing as L } from '@/copy/landing';

export default function Home() {
  const mp20 = useResource<Study>('studies/mp20', (s) => research.study('mp20', s));
  const perov5 = useResource<Study>('studies/perov5', (s) => research.study('perov5', s));
  const idx = useResource<{ studies: StudyIndexEntry[] }>('studies', (s) => research.studies(s));
  const blocks = useResource<BlocksPayload>('pipeline/blocks', (s) => research.blocks(s));
  const cal = mp20.data?.calibration;
  const accepted = mp20.data?.accepted ?? [];
  const newComp = accepted.filter((a) => a.class.startsWith('new composition')).length;
  const redisc = accepted.filter((a) => a.class.startsWith('rediscovered'));
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow" id="main">
        <section className="hero" style={{ gridTemplateColumns: '1fr' }}>
          <div>
            <div className="eyebrow">{H.eyebrow}</div>
            <h1>{H.h1}</h1>
            <p className="lead">{H.lead}</p>
            <div className="ctas">
              <Link to="/play" className="btn btn-primary btn-lg">{H.ctaPlay}</Link>
              <Link to="/p/perov5-demo/goal" className="btn btn-lg" data-testid="cta-demo">{H.ctaDemo}</Link>
            </div>
            <div className="trust">Open source · Reproducible runs · Downloadable structures and checkpoints · Every verdict against a reference band</div>
          </div>
        </section>

        <section className="section" id="discoveries">
          <h2>{H.discoveriesTitle}</h2>
          <p className="muted">{H.discoveriesLead}</p>
          {(mp20.error || perov5.error) && <ErrorNote error={mp20.error || perov5.error} />}
          {(mp20.loading || perov5.loading) && <Spinner label="Loading the results" />}
          {cal && (
            <div className="stat-tiles">
              <div className="card"><div className="k">MP-20 · band-gap requests</div><div className="v">{cal.funnel.final} / {cal.funnel.generated}</div><div className="n">structures accepted by two judges after relaxation, from {cal.range.requested.length} requested values</div></div>
              <div className="card"><div className="k">New compositions</div><div className="v">{newComp}</div><div className="n">new composition and new structure, by the AMD distance to every training structure</div></div>
              <div className="card"><div className="k">Known compounds returned</div><div className="v">{redisc.length}</div><div className="n">{redisc.map((r) => r.formula).join(', ')} — at the gaps the dataset records for them</div></div>
              <div className="card"><div className="k">Response</div><div className="v">{cal.linearity.intercept.toFixed(2)} + {cal.linearity.slope.toFixed(2)}·x</div><div className="n">delivered against requested gap; MAE <Num v={cal.accuracy.mae_relaxed_cells} /> eV; serves {cal.range.served[0]}–{cal.range.served[cal.range.served.length - 1]} eV</div></div>
              {perov5.data && <div className="card"><div className="k">Perov-5 · target following</div><div className="v">ρ {(perov5.data.target_following.rho_range as number[])[0]}–{(perov5.data.target_following.rho_range as number[])[1]}</div><div className="n">against the DFT grid; {perov5.data.target_following.known_compounds_returned as number} known compounds returned at their measured gaps</div></div>}
            </div>
          )}
          {accepted.length > 0 && (
            <div className="table-wrap" style={{ marginTop: 20 }}>
              <table className="table">
                <caption className="sr-only">Accepted structures of the MP-20 study</caption>
                <thead><tr><th scope="col">requested</th><th scope="col">formula</th><th scope="col">label from the structure</th><th scope="col">independent judge</th><th scope="col">what it is</th><th scope="col">AMD</th><th scope="col">cell</th></tr></thead>
                <tbody>
                  {accepted.map((a) => (
                    <tr key={a.file}>
                      <td className="num">{a.requested.toFixed(1)} eV</td><td><b>{a.formula}</b>{a.flag && <span className="small faint"> · {a.flag}</span>}</td>
                      <td className="num"><Num v={a.label_structure_gap} /></td><td className="num"><Num v={a.judge_gap} /></td>
                      <td className="small">{a.class}{a.known_formula && a.recorded_gaps.length ? ` · recorded ${a.recorded_gaps.map((g) => g.toFixed(2)).join(', ')} eV` : ''}</td>
                      <td className="num"><Num v={a.amd_nearest} d={3} /></td>
                      <td><a className="small" href={research.studyFileUrl('mp20', a.file)} download>CIF</a></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="small muted" style={{ marginTop: 8 }}>Both gaps are read on the relaxed cell. Stability is not assessed: no hull energy was computed. <Link to="/studies/mp20">The full study, with the calibration.</Link></p>
            </div>
          )}
        </section>

        <section className="section" id="how">
          <h2>{H.howTitle}</h2>
          <div className="cards-3">
            {H.how.map(([t, d], i) => <div className="card step-card" key={t}><div className="n">{i + 1}</div><h3>{t}</h3><p className="muted small">{d}</p></div>)}
          </div>
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
