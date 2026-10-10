import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { api } from '@/api/endpoints';
import { useResource } from '@/api/hooks';
import { lab, pointsOf, type ExplorePayload, type ExplorePoint, type MaterialDetail } from '@/api/lab';
import { Histogram } from '@/components/charts/Histogram';
import { Scatter } from '@/components/charts/Scatter';
import { ExternalLink, MarketingHeader, SiteFooter } from '@/components/shell';
import { CellViewer } from '@/components/structure/CellViewer';
import { ErrorNote, Segmented, Spinner } from '@/components/ui';
import { explore as C } from '@/copy/research';
import { explicitStructure } from '@/lib/lattice';
import { SPACE_APP, STATIC_MIRROR } from '@/lib/mirror';

const PROJECT = 'perov5-demo';
type Colour = 'dir_gap' | 'heat_all';
const LABEL: Record<Colour, [string, string]> = { dir_gap: ['direct band gap', 'eV'], heat_all: ['formation enthalpy', 'eV/atom'] };

interface DatasetProps { properties?: Record<string, { label: string; unit: string; n?: number; zero_share?: number; histogram?: { edges: number[]; counts: number[] } }> }

/** Stage 1: the dataset as a distribution and as a map of what the model learned; one material at a time with its cell. */
export default function Explore() {
  const map = useResource<ExplorePayload>(`explore:${PROJECT}`, (s) => lab.explore(PROJECT, s));
  const dataset = useResource<DatasetProps>(`dataset:${PROJECT}`, () => api.dataset(PROJECT) as Promise<DatasetProps>);
  const [colour, setColour] = useState<Colour>('dir_gap');
  const [onlyGapped, setOnlyGapped] = useState(false);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  // the static mirror has the map but not the server that reads a material's cell and finds its neighbours
  const detail = useResource<MaterialDetail>(selected && !STATIC_MIRROR ? `material:${PROJECT}:${selected}` : null, (s) => lab.material(PROJECT, selected!, s));
  const points = useMemo(() => (map.data ? pointsOf(map.data) : []), [map.data]);
  const picked = useMemo(() => (selected ? points.find((p) => p.material_id === selected) ?? null : null), [points, selected]);
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return points.filter((p) => (!onlyGapped || p.dir_gap > 0) && (!q || p.formula.toLowerCase().includes(q) || p.material_id.toLowerCase() === q));
  }, [points, onlyGapped, query]);
  const scatter = useMemo(() => shown.map((p: ExplorePoint) => ({ id: p.material_id, x: p.x, y: p.y, v: p[colour], label: p.formula })), [shown, colour]);
  const domain = useMemo(() => {
    const vs = points.map((p) => p[colour]);
    return { min: Math.min(...vs), max: Math.max(...vs) };
  }, [points, colour]);
  const hist = dataset.data?.properties?.dir_gap;
  const zero = hist && hist.zero_share != null && hist.n != null ? Math.round(hist.zero_share * hist.n) : null;
  // typing a formula (or an id) opens that material; a partial name only narrows the map
  const onQuery = (value: string) => {
    setQuery(value);
    const q = value.trim().toLowerCase();
    if (!q) return;
    const matches = points.filter((p) => (!onlyGapped || p.dir_gap > 0) && (p.formula.toLowerCase().includes(q) || p.material_id.toLowerCase() === q));
    const hit = matches.find((p) => p.formula.toLowerCase() === q || p.material_id.toLowerCase() === q) ?? (matches.length === 1 ? matches[0] : null);
    if (hit) setSelected(hit.material_id);
  };
  const d = detail.data;
  const cell = useMemo(() => (d?.cell ? explicitStructure(d.cell.sites, d.cell.lattice) : null), [d]);
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow page" id="main">
        <div className="page-head"><div className="micro">Stage 1 of 3 · Explore</div><h1>{C.h1}</h1><p>{C.lead}</p></div>
        {map.error && <ErrorNote error={map.error} retry={map.reload} />}
        {map.loading && <Spinner label="Loading the map" />}
        {map.data && (
          <div className="explore-grid">
            <div className="card">
              <div className="row" style={{ gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: 8 }}>
                <Segmented value={colour} label="Colour by" options={[{ value: 'dir_gap', label: 'Band gap' }, { value: 'heat_all', label: 'Formation enthalpy' }]} onChange={setColour} />
                <label className="small"><input type="checkbox" checked={onlyGapped} onChange={(e) => setOnlyGapped(e.target.checked)} /> only non-zero gaps</label>
                <input className="input" style={{ maxWidth: 180 }} placeholder="find a formula…" value={query} onChange={(e) => onQuery(e.target.value)} aria-label="Find a formula" />
              </div>
              <Scatter points={scatter} frame={points} colour={{ min: domain.min, max: domain.max, label: LABEL[colour][0], unit: LABEL[colour][1] }} selected={selected} onSelect={setSelected}
                xLabel="first principal component" yLabel="second principal component" width={620} height={460} equalAxes />
              <p className="small muted" style={{ marginTop: 8 }}>{C.mapNote} Model {map.data.model_id}; {Math.round(100 * (map.data.projection.explained_variance[0] + map.data.projection.explained_variance[1]))}% of the variance lies in these two axes.</p>
            </div>
            <div className="stack" style={{ gap: 16 }}>
              <div className="card" data-testid="material-card">
                {!selected && <><h3>A material</h3><p className="small muted">Click a point on the map, or type a formula, to see a material: its values, its cell and its nearest neighbours in the learned space.</p></>}
                {STATIC_MIRROR && picked && (
                  <>
                    <h3 style={{ margin: 0 }}>{picked.formula}</h3>
                    <div className="small muted">{picked.material_id} · training split{picked.site_key ? ` · sites ${picked.site_key.replace(/\|/g, ' · ')}` : ''}</div>
                    <dl className="kv small" style={{ marginTop: 8 }}>
                      <dt>direct band gap</dt><dd><span className="num">{picked.dir_gap.toFixed(3)}</span> eV (DFT, PBE)</dd>
                      <dt>formation enthalpy</dt><dd><span className="num">{picked.heat_all.toFixed(3)}</span> eV/atom (DFT)</dd>
                    </dl>
                    <p className="small muted" style={{ marginTop: 8 }}>The cell, the model's readings and the nearest neighbours are computed by the live server. <ExternalLink href={`${SPACE_APP}/explore`}>Open Explore there</ExternalLink></p>
                  </>
                )}
                {selected && detail.loading && <Spinner label="Loading the material" />}
                {detail.error && <ErrorNote error={detail.error} retry={detail.reload} />}
                {d && (
                  <>
                    <div className="row" style={{ justifyContent: 'space-between', alignItems: 'start' }}>
                      <div><h3 style={{ margin: 0 }}>{d.formula}</h3><div className="small muted">{d.material_id} · {d.split} split{d.site_key ? ` · sites ${d.site_key.replace(/\|/g, ' · ')}` : ''}</div></div>
                      {cell && <CellViewer structure={cell} size={120} title={d.formula} />}
                    </div>
                    <dl className="kv small" style={{ marginTop: 8 }}>
                      <dt>direct band gap</dt><dd><span className="num">{d.properties.dir_gap.toFixed(3)}</span> eV (DFT, PBE){d.encoder_prediction && <span className="faint"> · model reads {d.encoder_prediction.dir_gap.toFixed(2)}</span>}</dd>
                      <dt>formation enthalpy</dt><dd><span className="num">{d.properties.heat_all.toFixed(3)}</span> eV/atom (DFT){d.encoder_prediction && <span className="faint"> · model reads {d.encoder_prediction.heat_all.toFixed(2)}</span>}</dd>
                      {cell && <><dt>cell</dt><dd className="num">cubic, a = {d.cell!.lattice[0][0].toFixed(3)} Å, {d.cell!.sites.length} sites</dd></>}
                    </dl>
                    {d.neighbours.length > 0 && (
                      <>
                        <div className="micro" style={{ marginTop: 10 }}>nearest in the learned space</div>
                        <table className="table small" style={{ marginTop: 4 }}>
                          <thead><tr><th scope="col">material</th><th scope="col">cosine</th><th scope="col">gap (eV)</th><th scope="col">ΔH (eV/atom)</th></tr></thead>
                          <tbody>{d.neighbours.map((n) => <tr key={n.material_id}><td><button type="button" className="linklike" onClick={() => setSelected(n.material_id)}>{n.formula}</button></td><td className="num">{n.cosine.toFixed(3)}</td><td className="num">{n.properties.dir_gap?.toFixed(2)}</td><td className="num">{n.properties.heat_all?.toFixed(2)}</td></tr>)}</tbody>
                        </table>
                        <p className="small faint" style={{ marginTop: 4 }}>{d.note}</p>
                      </>
                    )}
                  </>
                )}
              </div>
              {hist?.histogram && (
                <div className="card">
                  <h3>Band gaps in the data</h3>
                  <Histogram edges={hist.histogram.edges} counts={hist.histogram.counts} unit={hist.unit} label={hist.label} zeroCount={zero} zeroShare={hist.zero_share ?? null} width={420} height={150} />
                  <p className="small muted" style={{ marginTop: 6 }}>{C.histNote}</p>
                </div>
              )}
            </div>
          </div>
        )}
        <div className="card" style={{ marginTop: 20 }}>
          <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
            <span className="muted">{C.next}</span>
            <Link to="/train" className="btn btn-primary">Train a small model →</Link>
          </div>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
