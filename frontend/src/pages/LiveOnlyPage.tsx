import { MarketingHeader, SiteFooter } from '@/components/shell';
import { LiveOnly } from '@/components/shell/Mirror';

/** The mirror's stand-in for a page that computes live (see lib/mirror.ts). */
export default function LiveOnlyPage({ title, what, path }: { title: string; what: string; path?: string }) {
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow page" id="main"><LiveOnly title={title} what={what} path={path} /></main>
      <SiteFooter />
    </>
  );
}
