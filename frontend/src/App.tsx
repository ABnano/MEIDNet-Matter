import { Suspense, lazy, useEffect, type ReactElement } from 'react';
import { Navigate, Route, Routes, useLocation, useParams } from 'react-router';
import { AppShell } from '@/components/shell';
import { Spinner } from '@/components/ui';
import { STATIC_MIRROR } from '@/lib/mirror';

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
const LiveOnlyPage = lazy(() => import('@/pages/LiveOnlyPage'));

/** In the static mirror a page that computes live becomes a pointer to the live app (lib/mirror.ts). */
const live = (el: ReactElement, title: string, what: string, path?: string) =>
  (STATIC_MIRROR ? <LiveOnlyPage title={title} what={what} path={path} /> : el);
const GENERATE = 'Ask for a band gap and get crystal structures back, judged by two independent models; the generator runs on the live server.';
const DEMO = 'The Perov-5 demo: set a goal, check the readiness of the data and the model, search, and export candidates with their evidence; the search runs on the live server.';

/** A link to a section of a page (/studies/mp20#accepted): scroll to it once it is there (it arrives with the page's data).
 *  The browser does this by itself only on a full load, never inside the app, nor in the mirror, whose routes follow '#'. */
function ScrollToSection() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (!hash) return;
    const id = decodeURIComponent(hash.slice(1));
    let tries = 0;
    let timer = 0;
    const seek = () => {
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({ block: 'start' });
      else if (tries++ < 50) timer = window.setTimeout(seek, 100);
    };
    seek();
    return () => window.clearTimeout(timer);
  }, [pathname, hash]);
  return null;
}

function ProjectRedirect() { const { projectId } = useParams(); return <Navigate to={`/p/${projectId}/goal`} replace />; }

export default function App() {
  return (
    <Suspense fallback={<div className="wrap page"><Spinner /></div>}>
      <ScrollToSection />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/demo" element={<Landing />} />
        <Route path="/pipeline" element={<Pipeline />} />
        <Route path="/pipeline/:block" element={<PipelineBlock />} />
        <Route path="/studies" element={<Studies />} />
        <Route path="/studies/:id" element={<Study />} />
        <Route path="/play" element={live(<Play />, 'Generate for a band gap', GENERATE, '/play')} />
        <Route path="/play/:jobId" element={live(<PlayJob />, 'Generate for a band gap', GENERATE, '/play')} />
        <Route path="/method" element={<Method />} />
        <Route path="/new" element={live(<CreateProject />, 'A new project', DEMO, '/new')} />
        <Route path="/start-with-my-data" element={<ComingNext />} />
        <Route path="/privacy" element={<Privacy />} />
        {STATIC_MIRROR ? <Route path="/p/*" element={<LiveOnlyPage title="The Perov-5 demo" what={DEMO} path="/p/perov5-demo/goal" />} /> : <>
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
        </>}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
}
