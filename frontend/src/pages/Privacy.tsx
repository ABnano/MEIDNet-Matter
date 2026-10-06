import { MarketingHeader, SiteFooter } from '@/components/shell';
import { useProject } from '@/features/project/useProject';

export default function Privacy() {
  const { data } = useProject('perov5-demo');
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow page">
        <div className="page-head"><h1>What happens to your data</h1></div>
        <div className="card stack" style={{ maxWidth: 760 }}>
          <p><b>On the shared Space.</b> {data?.privacy.hosted ?? 'A search runs in the container; its run folder lives on the container\'s disk, is removed after an hour of inactivity and on every restart, and is never used to train anything. No account, no analytics beyond the Space\'s own metrics.'}</p>
          <p><b>In this version</b> nothing is uploaded: a run holds only the goal you set and the candidates found. Run folders are reachable through their unguessable run id.</p>
          <p><b>Logs.</b> The server's access log (paths and the client address as forwarded by Hugging Face) is visible to the owner of the Space in its logs panel.</p>
          <p><b>Run locally.</b> {data?.privacy.local ?? 'Run locally, nothing leaves your computer.'} The README on GitHub has the two commands.</p>
          <p className="muted small">Predictions are model estimates and are labelled as such; DFT values shown next to a candidate come from the Perov-5 dataset and are labelled "DFT-computed".</p>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
