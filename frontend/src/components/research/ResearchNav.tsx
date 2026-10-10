import type { ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router';
import { research, type StudyIndexEntry } from '@/api/research';
import { useResource } from '@/api/hooks';
import { ExternalLink, PRISM_SPACE } from '@/components/shell';
import { BLOCKS, BLOCK_NAMES, researchNav as N } from '@/copy/research';

/** The research section's left menu: overview, case studies, evaluation pipeline, methodology. The section being read opens
 *  to its pages (the studies, or the ten blocks); the study list comes from the same index the case-studies page loads. */
export function ResearchNav() {
  const { pathname } = useLocation();
  const idx = useResource<{ studies: StudyIndexEntry[] }>('studies', (s) => research.studies(s));
  const inStudies = pathname.startsWith('/studies');
  const inPipeline = pathname.startsWith('/pipeline');
  const studies = [...(idx.data?.studies ?? [])].sort((a, b) => a.order - b.order);
  return (
    <nav className="research-nav" aria-label={N.label}>
      <div className="micro">{N.label}</div>
      <ul>
        <li><NavLink to="/research" end>{N.overview}</NavLink></li>
        <li className={inStudies ? 'open' : undefined}>
          <NavLink to="/studies" end>{N.studies}</NavLink>
          {inStudies && studies.length > 0 && (
            <ul>{studies.map((s) => <li key={s.id}><NavLink to={`/studies/${s.id}`}>{s.title}</NavLink></li>)}</ul>
          )}
        </li>
        <li className={inPipeline ? 'open' : undefined}>
          <NavLink to="/pipeline" end>{N.pipeline}</NavLink>
          {inPipeline && (
            <ul>{BLOCKS.map((b) => <li key={b}><NavLink to={`/pipeline/${b}`}><span className="mono">{b}</span> {BLOCK_NAMES[b]}</NavLink></li>)}</ul>
          )}
        </li>
        <li><NavLink to="/method" end>{N.method}</NavLink></li>
      </ul>
      <div className="research-nav-foot"><ExternalLink href={PRISM_SPACE}>{N.prism} ↗</ExternalLink></div>
    </nav>
  );
}

/** A research page: the menu on the left, the page's own content beside it at the width it had before. */
export function ResearchLayout({ children }: { children: ReactNode }) {
  return (
    <div className="wrap-narrow wrap-research research-layout">
      <ResearchNav />
      <main className="page research-main" id="main">{children}</main>
    </div>
  );
}
