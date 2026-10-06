import { Link } from 'react-router';
import { MarketingHeader, SiteFooter } from '@/components/shell';

export default function NotFound() {
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow page"><h1>Not found</h1><p className="muted">There is no page at this address.</p><Link to="/" className="btn">Back to the start</Link></main>
      <SiteFooter />
    </>
  );
}
