import { useEffect, useState, type ReactNode } from 'react';
import { Link, NavLink, Outlet, useParams } from 'react-router';
import { MatterMark, Wordmark } from '@/components/brand/MatterMark';
import { currentTheme, framed, setTheme } from '@/lib/theme';
import { useProject } from '@/features/project/useProject';
import { MIRROR_URL, PRISM_MIRROR, SPACE_PAGE, STATIC_MIRROR } from '@/lib/mirror';
import { MirrorBanner } from './Mirror';

// Prism on its Space, or, from the mirror, Prism's own GitHub Pages mirror (the same pages, without the /docs prefix)
export const PRISM = STATIC_MIRROR ? PRISM_MIRROR : 'https://babu09-meidnet.hf.space';
export const PRISM_SPACE = STATIC_MIRROR ? PRISM_MIRROR : 'https://huggingface.co/spaces/Babu09/MEIDNet';
const PRISM_DOCS = STATIC_MIRROR ? PRISM_MIRROR.replace(/\/$/, '') : `${PRISM}/docs`;
export const PRISM_METHOD = `${PRISM_DOCS}/understand/how-it-works.html`;
export const PRISM_SCORE = `${PRISM_DOCS}/benchmarks/compatibility.html`;
export const PRISM_ECOSYSTEM = `${PRISM_DOCS}/ecosystem.html`;
export const GITHUB = 'https://github.com/ABnano/MEIDNet-Matter';
export const ENGINE = 'https://github.com/ABnano/MEIDNet';

export function ExternalLink({ href, children, className }: { href: string; children: ReactNode; className?: string }) {
  return <a href={href} target="_blank" rel="noopener" className={className}>{children}</a>;
}

export function ThemeToggle() {
  const [theme, set] = useState<'light' | 'dark'>(() => (typeof document === 'undefined' ? 'light' : currentTheme()));
  return (
    <button type="button" className="btn btn-ghost btn-sm" aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
      onClick={() => { const t = theme === 'dark' ? 'light' : 'dark'; setTheme(t); set(t); }}>
      {theme === 'dark' ? '☀' : '☾'}
    </button>
  );
}

/** Inside the Hugging Face page: the same page at its own address. */
export function DirectAppLink() {
  const [show, setShow] = useState(false);
  useEffect(() => { setShow(framed()); }, []);
  if (!show) return null;
  return <a className="btn btn-ghost btn-sm" href={window.location.href} target="_blank" rel="noopener" title="The same page, outside the Hugging Face frame">Open the direct app ↗</a>;
}

export function MarketingHeader() {
  return (
    <>
    <MirrorBanner />
    <header className="mhead">
      <div className="wrap-narrow">
        <Link to="/" className="brand"><MatterMark /><Wordmark /></Link>
        <nav aria-label="Sections">
          <NavLink to="/pipeline">Pipeline</NavLink><NavLink to="/studies">Studies</NavLink><NavLink to="/play">Generate</NavLink><NavLink to="/method">Method</NavLink>
          <ExternalLink href={PRISM_SPACE}>Prism</ExternalLink>
          <ExternalLink href={GITHUB}>GitHub</ExternalLink>
        </nav>
        <Link to="/p/perov5-demo/goal" className="btn btn-primary btn-sm">Try the Perov-5 demo</Link>
        <ThemeToggle /><DirectAppLink />
      </div>
    </header>
    </>
  );
}

export function SiteFooter() {
  return (
    <footer className="site">
      <div className="wrap-narrow">
        <span>MEIDNet Matter: from your materials data to candidate structures. MEIDNet is the engine.</span>
        <Link to="/pipeline">Pipeline</Link>
        <Link to="/studies">Studies</Link>
        <Link to="/play">Generate</Link>
        <Link to="/method">Method</Link>
        <ExternalLink href={GITHUB}>Code</ExternalLink>
        {STATIC_MIRROR ? <ExternalLink href={SPACE_PAGE}>Live app (Hugging Face)</ExternalLink> : <ExternalLink href={MIRROR_URL}>Mirror for restricted networks</ExternalLink>}
        <ExternalLink href={PRISM}>MEIDNet Prism</ExternalLink>
        <ExternalLink href={ENGINE}>MEIDNet engine</ExternalLink>
        <ExternalLink href="https://doi.org/10.1038/s41524-026-02153-3">Paper</ExternalLink>
        <Link to="/privacy">What happens to your data</Link>
      </div>
    </footer>
  );
}

const STEPS = [
  { key: 'goal', label: 'Goal', to: (p: string) => `/p/${p}/goal` },
  { key: 'readiness', label: 'Readiness', to: (p: string) => `/p/${p}/readiness` },
  { key: 'candidates', label: 'Candidates', to: (p: string, r?: string) => (r ? `/p/${p}/runs/${r}` : `/p/${p}/runs`) },
  { key: 'export', label: 'Export', to: (p: string, r?: string) => (r ? `/p/${p}/runs/${r}/export` : `/p/${p}/runs`) },
];

export function StepIndicator({ current }: { current: string }) {
  const { projectId = 'perov5-demo', runId } = useParams();
  const idx = STEPS.findIndex((s) => s.key === current);
  return (
    <nav className="steps" aria-label="Workflow">
      {STEPS.map((s, i) => {
        const disabled = (s.key === 'candidates' || s.key === 'export') && !runId && i > idx;
        const el = disabled ? <span key={s.key}>{s.label}</span> : (
          <NavLink key={s.key} to={s.to(projectId, runId)} aria-current={s.key === current ? 'step' : undefined} className={i < idx ? 'done' : ''}>
            {i < idx ? '✓ ' : ''}{s.label}
          </NavLink>);
        return <span key={`w${s.key}`} className="row" style={{ gap: 4 }}>{el}{i < STEPS.length - 1 && <span className="sep" aria-hidden="true">→</span>}</span>;
      })}
    </nav>
  );
}

export function TopBar({ step }: { step: string }) {
  const { projectId = 'perov5-demo' } = useParams();
  const { data: project } = useProject(projectId);
  return (
    <div className="topbar">
      <div className="wrap">
        <Link to="/" className="brand"><MatterMark /><Wordmark /></Link>
        {project && <span className="small muted" style={{ whiteSpace: 'nowrap' }}>{project.title} · <span className="mono">{project.default_goal.variant} {project.default_goal.family === 'perovskite_abx3' ? 'perovskite' : project.default_goal.family}</span></span>}
        <StepIndicator current={step} />
        <div className="topbar-right">
          <ExternalLink href={PRISM_METHOD} className="btn btn-ghost btn-sm">How does this work? → Prism</ExternalLink>
          <ThemeToggle /><DirectAppLink />
        </div>
      </div>
    </div>
  );
}

export function AppShell({ step }: { step: string }) {
  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <TopBar step={step} />
      <main id="main" className="wrap page"><Outlet /></main>
      <SiteFooter />
    </>
  );
}
