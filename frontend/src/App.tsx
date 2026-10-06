import { Suspense, lazy } from 'react';
import { Navigate, Route, Routes, useParams } from 'react-router';
import { AppShell } from '@/components/shell';
import { Spinner } from '@/components/ui';

const Landing = lazy(() => import('@/pages/Landing'));
const CreateProject = lazy(() => import('@/pages/CreateProject'));
const ComingNext = lazy(() => import('@/pages/ComingNext'));
const Privacy = lazy(() => import('@/pages/Privacy'));
const Goal = lazy(() => import('@/pages/Goal'));
const Readiness = lazy(() => import('@/pages/Readiness'));
const Runs = lazy(() => import('@/pages/Runs'));
const Explorer = lazy(() => import('@/pages/Explorer'));
const CandidatePage = lazy(() => import('@/pages/CandidatePage'));
const Compare = lazy(() => import('@/pages/Compare'));
const Validate = lazy(() => import('@/pages/Validate'));
const NotFound = lazy(() => import('@/pages/NotFound'));

function ProjectRedirect() { const { projectId } = useParams(); return <Navigate to={`/p/${projectId}/goal`} replace />; }

export default function App() {
  return (
    <Suspense fallback={<div className="wrap page"><Spinner /></div>}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/new" element={<CreateProject />} />
        <Route path="/start-with-my-data" element={<ComingNext />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/p/:projectId" element={<ProjectRedirect />} />
        <Route path="/p/:projectId/data" element={<ComingNext />} />
        <Route path="/p/:projectId/goal" element={<AppShell step="goal" />}><Route index element={<Goal />} /></Route>
        <Route path="/p/:projectId/readiness" element={<AppShell step="readiness" />}><Route index element={<Readiness />} /></Route>
        <Route path="/p/:projectId/runs" element={<AppShell step="candidates" />}><Route index element={<Runs />} /></Route>
        <Route path="/p/:projectId/runs/:runId" element={<AppShell step="candidates" />}>
          <Route index element={<Explorer />} />
          <Route path="c/:candidateId" element={<CandidatePage />} />
          <Route path="compare" element={<Compare />} />
        </Route>
        <Route path="/p/:projectId/runs/:runId/export" element={<AppShell step="export" />}><Route index element={<Validate />} /></Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
}
