import { Link, useParams } from 'react-router';
import { isGone } from '@/api/client';
import { api } from '@/api/endpoints';
import { useResource } from '@/api/hooks';
import { ErrorNote, Spinner } from '@/components/ui';
import { CandidateDetail } from '@/features/candidates/CandidateDetail';
import { RunGone } from '@/features/lifecycle/Gone';

export default function CandidatePage() {
  const { projectId = 'perov5-demo', runId = '', candidateId = '' } = useParams();
  const { data, error, loading, reload } = useResource(`candidate:${runId}:${candidateId}`, () => api.candidate(runId, candidateId));
  if (loading) return <Spinner label="Loading the candidate" />;
  if (isGone(error)) return <RunGone projectId={projectId} runId={runId} error={error} />;
  if (error || !data) return <ErrorNote error={error} retry={reload} />;
  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}><Link to={`/p/${projectId}/runs/${runId}?c=${candidateId}`} className="btn btn-sm">← All candidates</Link></div>
      <div className="card"><CandidateDetail c={data} projectId={projectId} variant="page" /></div>
    </>
  );
}
