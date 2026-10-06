import { Link } from 'react-router';
import { MarketingHeader, SiteFooter } from '@/components/shell';

export default function CreateProject() {
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow page">
        <div className="page-head"><h1>What are you trying to design?</h1><p>Start from an example project, or from your own data when that arrives.</p></div>
        <div className="cards-3">
          <div className="card">
            <span className="ribbon">Available now</span>
            <h3 style={{ marginTop: 10 }}>Use an example project</h3>
            <p className="muted small">Perov-5: cubic ABX₃ perovskites, direct band gap and formation enthalpy, the published MEIDNet model.</p>
            <Link to="/p/perov5-demo/goal" className="btn btn-primary">Open Perov-5</Link>
          </div>
          <div className="card">
            <span className="ribbon">Coming next</span>
            <h3 style={{ marginTop: 10 }}>Start from data</h3>
            <p className="muted small">Upload crystal structures and properties; Matter checks them, trains a model and reports its readiness.</p>
            <Link to="/start-with-my-data" className="btn">What arrives in Phase 1</Link>
          </div>
          <div className="card">
            <span className="ribbon">Planned</span>
            <h3 style={{ marginTop: 10 }}>Describe your goal</h3>
            <p className="muted small">Write the goal in words; Matter turns it into targets and rules. In this version, use the structured editor.</p>
            <button type="button" className="btn" disabled>Not in this version</button>
          </div>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
