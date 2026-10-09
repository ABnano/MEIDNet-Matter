import { Suspense, lazy, useEffect, type ReactElement } from 'react';
import { Navigate, Route, Routes, useLocation, useParams } from 'react-router';
import { AppShell } from '@/components/shell';
import { Spinner } from '@/components/ui';
import { STATIC_MIRROR } from '@/lib/mirror';
import { STUDY_DATASETS } from '@/copy/research';

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
const Research = lazy(() => import('@/pages/Research'));
const Explore = lazy(() => import('@/pages/Explore'));
const Train = lazy(() => import('@/pages/Train'));
const TrainJob = lazy(() => import('@/pages/TrainJob'));
const LiveOnlyPage = lazy(() => import('@/pages/LiveOnlyPage'));

/** In the static mirror a page that computes live becomes a pointer to the live app (lib/mirror.ts). */
const live = (el: ReactElement, title: string, what: string, path?: string) =>
  (STATIC_MIRROR ? <LiveOnlyPage title={title} what={what} path={path} /> : el);
const GENERATE = 'Ask for a band gap and get crystal structures back, read by two models of different lineage; the generator runs on the live server.';
const TRAIN = 'Train a small MEIDNet model on 1,500 Perov-5 materials and watch it learn; the training runs on the live server.';
const DEMO = 'The Perov-5 demo: set a goal, check the readiness of the data and the model, search, and export candidates with their evidence; the search runs on the live server.';

/** Every page's own title, so tabs, history and bookmarks say where they lead. */
const STUDY_TITLE = Object.fromEntries(STUDY_DATASETS) as Record<string, string>;
const TITLES: Array<[RegExp, (m: RegExpMatchArray) => string]> = [
  [/^\/pipeline\/(S\d)$/, (m) => `Block ${m[1]} · Pipeline`], [/^\/pipeline$/, () => 'Pipeline'],
  [/^\/studies\/([\w-]+)$/, (m) => `${STUDY_TITLE[m[1]] ?? m[1]} study`], [/^\/studies$/, () => 'Studies'],
  [/^\/(play|generate)\/[\w-]+$/, () => 'Generation job'], [/^\/(play|generate)$/, () => 'Generate for a band gap'],
  [/^\/explore$/, () => 'Explore the data'], [/^\/train\/[\w-]+$/, () => 'Training job'], [/^\/train$/, () => 'Train a small model'], [/^\/research$/, () => 'Research'],
  [/^\/method$/, () => 'Method'], [/^\/privacy$/, () => 'Privacy'], [/^\/new$/, () => 'A new project'],
  [/^\/start-with-my-data$/, () => 'Start with my data'],
  [/^\/p\/[\w-]+\/goal$/, () => 'Goal · Perov-5 demo'], [/^\/p\/[\w-]+\/readiness$/, () => 'Readiness · Perov-5 demo'],
  [/^\/p\/[\w-]+\/runs$/, () => 'Searches · Perov-5 demo'], [/^\/p\/[\w-]+\/runs\/[\w-]+\/export$/, () => 'Validate and export · Perov-5 demo'],
  [/^\/p\/[\w-]+\/runs\/[\w-]+\/compare$/, () => 'Compare · Perov-5 demo'], [/^\/p\/[\w-]+\/runs\/[\w-]+\/c\/[\w-]+$/, () => 'Candidate · Perov-5 demo'],
  [/^\/p\/[\w-]+\/runs\/[\w-]+$/, () => 'Candidates · Perov-5 demo'],
];

/** The home page's title: the same words as index.html's <title>, which the page loads with. */
export const HOME_TITLE = 'MEIDNet Matter — crystal structures for a requested band gap, with the evidence';

export function pageTitle(pathname: string): string {
  if (pathname === '/') return HOME_TITLE;
  for (const [re, f] of TITLES) {
    const m = pathname.match(re);
    if (m) return `${f(m)} · MEIDNet Matter`;
  }
  return 'MEIDNet Matter';
}

function TitleSync() {
  const { pathname } = useLocation();
  useEffect(() => { document.title = pageTitle(pathname); }, [pathname]);
  return null;
}

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
      <TitleSync />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/demo" element={<Navigate to={STATIC_MIRROR ? '/' : '/p/perov5-demo/goal'} replace />} />
        <Route path="/pipeline" element={<Pipeline />} />
        <Route path="/pipeline/:block" element={<PipelineBlock />} />
        <Route path="/studies" element={<Studies />} />
        <Route path="/studies/:id" element={<Study />} />
        <Route path="/explore" element={<Explore />} />
        <Route path="/train" element={live(<Train />, 'Train a small model', TRAIN, '/train')} />
        <Route path="/train/:jobId" element={live(<TrainJob />, 'Train a small model', TRAIN, '/train')} />
        <Route path="/generate" element={live(<Play />, 'Generate for a band gap', GENERATE, '/generate')} />
        <Route path="/generate/:jobId" element={live(<PlayJob />, 'Generate for a band gap', GENERATE, '/generate')} />
        <Route path="/play" element={<Navigate to="/generate" replace />} />
        <Route path="/play/:jobId" element={live(<PlayJob />, 'Generate for a band gap', GENERATE, '/generate')} />
        <Route path="/research" element={<Research />} />
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
