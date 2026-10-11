import { Link } from 'react-router';
import { ExternalLink, PRISM_PEROV5 } from '@/components/shell';
import { datasets as D } from '@/copy/research';

const CDVAE_DATA = 'https://github.com/txie-93/cdvae/tree/main/data';
const CMR_PEROVSKITES = 'https://cmr.fysik.dtu.dk/cubic_perovskites/cubic_perovskites.html';

/** The two datasets behind the three stages in plain words, with where to look at them in the app and where they come
 *  from. The home page's "What is Perov-5?" opens it at #perov5. */
export function DatasetPrimer() {
  return (
    <section className="section" id="data">
      <h2>{D.title}</h2>
      <p className="muted">{D.lead}</p>
      <div className="cards-2" style={{ alignItems: 'start' }}>
        <div className="card" id="perov5" data-testid="primer-perov5">
          <h3>{D.perov5Title}</h3>
          {D.perov5.map((p) => <p className="small" key={p.slice(0, 32)}>{p}</p>)}
          <p className="small"><Link to="/explore">Browse it in Explore →</Link> · <Link to="/studies/perov5">The Perov-5 case study →</Link></p>
          <p className="small">
            <ExternalLink href={`${CDVAE_DATA}/perov_5`}>The split files (CDVAE) ↗</ExternalLink> · <ExternalLink href={CMR_PEROVSKITES}>The original database (CMR, DTU) ↗</ExternalLink> · <ExternalLink href={PRISM_PEROV5}>Benchmarks on Perov-5 (MEIDNet Prism) ↗</ExternalLink>
          </p>
          <p className="small faint" style={{ marginBottom: 0 }}>{D.perov5Sources}</p>
        </div>
        <div className="card" id="mp20">
          <h3>{D.mp20Title}</h3>
          <p className="small">{D.mp20}</p>
          <p className="small"><Link to="/generate">Generate for a band gap →</Link> · <Link to="/studies/mp20">The MP-20 case study →</Link> · <ExternalLink href={`${CDVAE_DATA}/mp_20`}>The split files (CDVAE) ↗</ExternalLink></p>
          <p className="small muted" style={{ marginBottom: 0 }}>{D.others}</p>
        </div>
      </div>
    </section>
  );
}
