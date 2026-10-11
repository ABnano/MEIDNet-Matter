import { Link } from 'react-router';
import { ExternalLink, MarketingHeader, PRISM_LIMITS, SiteFooter } from '@/components/shell';
import { ResearchLayout } from '@/components/research/ResearchNav';
import { STUDY_DATASETS } from '@/copy/research';
import { limits as L, STUDY_EVIDENCE } from '@/copy/limits';

/** One statement of scope and limits: how to read a result, what a dataset needs, what each study checked, which crystal
 *  structures the routes produce, what the measurements support, the pipeline's known open issues, and what the site
 *  itself does not do. The study pages show their own row of the studies table. */
export default function Limits() {
  return (
    <>
      <MarketingHeader wide />
      <ResearchLayout>
        <div className="page-head"><h1>{L.h1}</h1><p>{L.lead}</p></div>

        <section id="evidence">
          <h2>{L.evidenceTitle}</h2>
          <p className="muted">{L.evidenceLead}</p>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th scope="col">evidence</th><th scope="col">what it means</th><th scope="col">for example</th></tr></thead>
              <tbody>{L.evidence.map(([k, d, e]) => <tr key={k}><td><b>{k}</b></td><td className="small">{d}</td><td className="small muted">{e}</td></tr>)}</tbody>
            </table>
          </div>
          <p className="small muted" style={{ marginTop: 8 }}>{L.scales}</p>
        </section>

        <section className="section" id="data">
          <h2>{L.dataTitle}</h2>
          <p className="muted">{L.dataLead}</p>
          <div className="table-wrap">
            <table className="table">
              <thead><tr>{L.dataHead.map((h) => <th scope="col" key={h}>{h}</th>)}</tr></thead>
              <tbody>{L.data.map(([goal, ...rest]) => <tr key={goal}><td><b>{goal}</b></td>{rest.map((c, i) => <td className="small" key={i}>{c}</td>)}</tr>)}</tbody>
            </table>
          </div>
          <div className="note" style={{ marginTop: 16 }} data-testid="small-data">
            <b>{L.smallTitle}.</b> {L.small} <Link to="/studies/user-246">The upload's study →</Link>
          </div>
          <p className="small muted" style={{ marginTop: 12 }}>{L.thresholdNote} <Link to="/pipeline/S0">Block S0 →</Link></p>
          <p className="small" style={{ marginTop: 8 }}>{L.ownData} <Link to="/start-with-my-data">How to start →</Link> · <Link to="/method#run">The commands →</Link></p>
        </section>

        <section className="section" id="studies">
          <h2>{L.studiesTitle}</h2>
          <p className="muted">{L.studiesLead}</p>
          <div className="table-wrap">
            <table className="table">
              <thead><tr>{L.studiesHead.map((h) => <th scope="col" key={h}>{h}</th>)}</tr></thead>
              <tbody>
                {STUDY_DATASETS.map(([id, name]) => STUDY_EVIDENCE[id] && (
                  <tr key={id}>
                    <td><Link to={`/studies/${id}`}><b>{name}</b></Link></td>
                    <td className="small">{STUDY_EVIDENCE[id].data}</td>
                    <td className="small">{STUDY_EVIDENCE[id].route}</td>
                    <td className="small">{STUDY_EVIDENCE[id].checked}</td>
                    <td className="small">{STUDY_EVIDENCE[id].notChecked}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="section" id="structures">
          <h2>{L.structuresTitle}</h2>
          <div className="cards-3">{L.structures.map(([t, d]) => <div className="card" key={t}><h3>{t}</h3><p className="muted small" style={{ margin: 0 }}>{d}</p></div>)}</div>
        </section>

        <section className="section" id="strengths">
          <h2>{L.strengthsTitle}</h2>
          <ul>{L.strengths.map((s) => <li key={s}>{s}</li>)}</ul>
        </section>

        <section className="section" id="open">
          <h2>{L.openTitle}</h2>
          <p className="muted">{L.openLead}</p>
          <ul>{L.open.map((s) => <li key={s}>{s}</li>)}</ul>
        </section>

        <section className="section" id="site">
          <h2>{L.siteTitle}</h2>
          <ul>{L.site.map((s) => <li key={s}>{s}</li>)}</ul>
          <p className="small muted">{L.engine} <ExternalLink href={PRISM_LIMITS}>{L.engineLink}</ExternalLink></p>
        </section>
      </ResearchLayout>
      <SiteFooter wide />
    </>
  );
}
