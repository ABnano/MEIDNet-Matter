import { Link } from 'react-router';
import { MarketingHeader, SiteFooter } from '@/components/shell';

export default function ComingNext() {
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow page">
        <div className="page-head"><h1>Start with my data — coming next</h1></div>
        <div className="card" style={{ maxWidth: 720 }}>
          <p>Phase 1 of MEIDNet Matter adds the upload of a property table with CIF files (CSV or Excel, or a ZIP with a <code>structures/</code> folder), a data-quality report that names every excluded row and why, training in the browser with progress, a readiness report measured on your own held-out data, and the same search and evidence with your model.</p>
          <p className="muted">The workflow is already in place: Data → Goal → Readiness → Candidates → Export. Until then, the Perov-5 project shows every step on a real dataset and model.</p>
          <div className="row">
            <Link to="/p/perov5-demo/goal" className="btn btn-primary">Try the Perov-5 demo</Link>
            <Link to="/" className="btn">Back to the start</Link>
          </div>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
