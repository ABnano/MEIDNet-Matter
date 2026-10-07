import { Link } from 'react-router';
import { research, type CheckpointInfo, type StudyIndexEntry } from '@/api/research';
import { useResource } from '@/api/hooks';
import { MarketingHeader, SiteFooter } from '@/components/shell';
import { ErrorNote, Spinner } from '@/components/ui';
import { studies as S } from '@/copy/research';

const mb = (b: number | null) => (b ? `${(b / 1048576).toFixed(1)} MB` : '—');

export default function Studies() {
  const idx = useResource<{ studies: StudyIndexEntry[] }>('studies', (s) => research.studies(s));
  const ck = useResource<{ release: string; checkpoints: CheckpointInfo[] }>('checkpoints', (s) => research.checkpoints(s));
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow page" id="main">
        <div className="page-head"><h1>{S.h1}</h1><p>{S.lead}</p></div>
        {idx.error && <ErrorNote error={idx.error} retry={idx.reload} />}
        {idx.loading && <Spinner label="Loading the studies" />}
        {idx.data && (
          <div className="stack" style={{ gap: 12 }}>
            {idx.data.studies.sort((a, b) => a.order - b.order).map((s) => (
              <div className="card block-row" key={s.id}>
                <div className="bid">{s.order}</div>
                <div>
                  <div className="micro">{s.dataset} · {s.mode}</div>
                  <h3><Link to={`/studies/${s.id}`}>{s.title}</Link></h3>
                  <p className="muted small" style={{ margin: 0 }}>{s.headline}</p>
                </div>
                <Link to={`/studies/${s.id}`} className="btn btn-sm">Open</Link>
              </div>
            ))}
          </div>
        )}
        <section className="section" id="checkpoints">
          <h2>{S.checkpointsTitle}</h2>
          <p className="muted">{S.checkpointsLead}</p>
          {ck.error && <ErrorNote error={ck.error} retry={ck.reload} />}
          {ck.data && (
            <div className="table-wrap">
              <table className="table">
                <caption className="sr-only">Checkpoints</caption>
                <thead><tr><th scope="col">id</th><th scope="col">study</th><th scope="col">role</th><th scope="col">what it is</th><th scope="col">size</th><th scope="col">sha256</th><th scope="col">download</th></tr></thead>
                <tbody>
                  {ck.data.checkpoints.map((c) => (
                    <tr key={c.id}>
                      <td className="mono">{c.id}</td><td className="small"><Link to={`/studies/${c.study}`}>{c.study}</Link></td><td className="small">{c.role}</td>
                      <td className="small">{c.description}</td><td className="num small">{mb(c.bytes)}</td>
                      <td className="mono small" title={c.sha256 ?? ''}>{c.sha256 ? `${c.sha256.slice(0, 12)}…` : '—'}</td>
                      <td className="small">
                        {c.download_url && <a href={c.download_url} download={c.file}>from this server</a>}
                        {c.urls?.map((u, i) => <span key={u}>{c.download_url || i ? ' · ' : ''}<a href={u} target="_blank" rel="noopener">{u.includes('github') ? 'GitHub release' : u.includes('huggingface') ? 'Hugging Face' : 'link'}</a></span>)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="small muted" style={{ marginTop: 8 }}>Release {ck.data.release}. Load a file with <code>meidnet.checkpoint.load_checkpoint(path)</code> from the vendored engine (engine/ in the repository); the training configuration travels with it under checkpoints/configs/.</p>
            </div>
          )}
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
