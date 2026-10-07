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
const Home = lazy(() => import('@/pages/Home'));
const Pipeline = lazy(() => import('@/pages/Pipeline'));
const PipelineBlock = lazy(() => import('@/pages/PipelineBlock'));
const Studies = lazy(() => import('@/pages/Studies'));
const Study = lazy(() => import('@/pages/Study'));
const Play = lazy(() => import('@/pages/Play'));
const PlayJob = lazy(() => import('@/pages/PlayJob'));
const Method = lazy(() => import('@/pages/Method'));

function ProjectRedirect() { const { projectId } = useParams(); return <Navigate to={`/p/${projectId}/goal`} replace />; }

export default function App() {
  return (
    <Suspense fallback={<div className="wrap page"><Spinner /></div>}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/demo" element={<Landing />} />
        <Route path="/pipeline" element={<Pipeline />} />
        <Route path="/pipeline/:block" element={<PipelineBlock />} />
        <Route path="/studies" element={<Studies />} />
        <Route path="/studies/:id" element={<Study />} />
        <Route path="/play" element={<Play />} />
        <Route path="/play/:jobId" element={<PlayJob />} />
        <Route path="/method" element={<Method />} />
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
