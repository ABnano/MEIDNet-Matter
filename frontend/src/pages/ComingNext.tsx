import { Link } from 'react-router';
import { MarketingHeader, SiteFooter } from '@/components/shell';

export default function ComingNext() {
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow page">
        <div className="page-head"><h1>Start with my data</h1><p>Available now on your computer; a browser upload is planned.</p></div>
        <div className="card" style={{ maxWidth: 720 }}>
          <p>Nothing is uploaded on this site. The same stages the site shows run locally on a folder of structures and a property table: one table, intake and split, the S0 gate (is the data usable, generation or screening?), training with a template that matches your route, the scorecard, then generation with two independent readings or screening of a family with the independent judge, and the report. Every command is on the Method page, with the code of every block one click away.</p>
          <p className="muted">Planned: the upload of a property table with CIF files, a data-quality report in the browser, training with progress, and readiness measured on your own held-out data, so the Data → Goal → Readiness → Candidates → Export flow runs here as the Perov-5 project does.</p>
          <div className="row">
            <Link to="/method#run" className="btn btn-primary">The commands, step by step</Link>
            <Link to="/p/perov5-demo/goal" className="btn">Try the Perov-5 demo</Link>
            <Link to="/" className="btn btn-ghost">Back to the start</Link>
          </div>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
