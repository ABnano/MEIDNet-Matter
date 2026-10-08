import { Link } from 'react-router';
import { MarketingHeader, SiteFooter } from '@/components/shell';
import { method as M } from '@/copy/research';

const MECHANISM: Array<[string, string]> = [
  ['Two encoders, one latent space', 'A structure encoder (an equivariant graph network over the cell) and a property encoder map a crystal and its property vector to points on the same unit sphere; a contrastive objective pulls matching pairs together. A decoder reads a point back into a cell, and a property head reads properties from a point.'],
  ['Two geometry paths in one decoder', 'The free path places every atom and failed on general chemistry (overlapping atoms, zero volume). The symmetry path predicts a space group and the few sites that symmetry does not relate; the symmetry operations build the rest. The lattice is projected onto the crystal system the space group demands and symmetry images are merged by distance (0.8 Å). Both heads live in one model, so a latent can be decoded either way.'],
  ['Sampling at the target\'s anchor', 'The requested property is encoded to a point; cells are decoded from points near it. Gradient steps that push the point until the property head reads the target were removed after measurement: they made the model report the request while drifting towards zero-gap metals.'],
  ['The label is read from the returned structure', 'The decoded cell is encoded again and its properties read there. A label read from the search point reports the request back by construction; that defect was found in the published application and is excluded everywhere.'],
  ['An independent, qualified judge', 'A second model of a different lineage reads the same cell. It is measured on the dataset\'s own test split first, and which of its heads matches the dataset is decided by that measurement. A candidate counts only when both labels lie inside the window.'],
  ['Relax, then judge again', 'Two machine-learning potentials of different architecture relax the cell. The judges run again on the relaxed structure, which is what a user receives.'],
  ['Two modes, chosen by a measurement', 'Whether a dataset can generate or must screen an enumerated design space is decided before training from the number of compositions per element (12 → 0.1%, 30 → 0.7%, 80 → 5.4%, 218 → 64% decoder recovery on Perov-5 subsets).'],
];
const STRENGTHS: Array<[string, string]> = [
  ['Every claim has a verdict against a band', 'Ten blocks, each with metrics and PASS/WARN/FAIL thresholds validated on configurations of known quality; a proxy becomes context once the quantity it predicts is measured.'],
  ['Target following was shown three ways', 'Against a DFT grid (Perov-5: Spearman 0.90–0.98); by screening with the user\'s own qualified judge (Spearman 0.68); and family-free with two judges on relaxed cells (MP-20: delivered = 0.09 + 0.86 × requested).'],
  ['Known compounds come back at their recorded gaps', 'Asked for 1.5, 2.5 and 3.0 eV on MP-20, the generator returned CaTe, SrO and CaO, whose recorded gaps are 1.60, 2.57 and 3.12 eV. On Perov-5, eight compounds with a literature record were returned unprompted.'],
  ['The encoder works on small data', 'The best property model of all four datasets was trained on 166 structures (0.19 spreads, r 0.97): what it needs is a well-posed property, not volume.'],
  ['Every step reports what it rejected', 'Funnels, per-stage counts and the reason for each rejection are part of every result; a step that removes nothing when it should is flagged.'],
];
const LIMITS: Array<[string, string]> = [
  ['Serviceable range and resolution', 'On MP-20 the generator serves 0.5–3 eV; above 3 eV it saturates. Requests 0.5 eV apart are not reliably distinct: the usable step is about 1 eV, the precision about ±0.7 eV per structure.'],
  ['The generated cell is a starting point', 'Relaxation lowers the energy by 1.3–8.7 eV/atom and moves atoms 1.4–2.3 Å. Coordinate accuracy is the open defect (RMSE 0.24 in fractional units; a discrete coordinate grid did not fix it). A Wyckoff-position head is the identified next change.'],
  ['Nothing here is called stable', 'Hull energies were computed for Perov-5 and the user upload, not for MP-20. "Relaxes to a minimum with the requested gap" is the strongest statement made.'],
  ['Discovery with a family is perovskite-shaped', 'Blocks S5–S7 of the screening mode assume ABX₃-like chemistry; family-free generation needs roughly 200 compositions per element, which only MP-20 reached.'],
  ['Judges are models', 'Both labels come from machine-learned models with stated errors (0.10 and 0.27 eV on their test splits). No result is DFT or experiment.'],
  ['Elements are a user control', 'The pipeline optimises the target, not practicality: on one dataset seven of thirteen shortlisted candidates contained thallium. Radioactive elements are excluded by default; toxic ones are a switch.'],
];

const RUN_STEPS: Array<[string, string, string]> = [
  ['Install the engine', 'The engine folder of the repository is the exact snapshot this site runs. Its model, decoder and symmetry code are in meidnet/; every block\'s component is in meidnet_eval/.', 'git clone https://github.com/ABnano/MEIDNet-Matter && cd MEIDNet-Matter\npip install ./engine && pip install -e ".[judge]"'],
  ['Turn what you have into one table', 'A folder of CIF or POSCAR files plus a spreadsheet of properties becomes one CSV with a structure column. Names are matched and every ambiguity is reported, not resolved silently.', 'python -m meidnet_eval.ingest_upload structures/ properties.xlsx data/ --props "Band gap" --header-rows 2'],
  ['Audit, detect prototypes, split', 'The intake writes the audit (rows, elements, zeros, shared property profiles), the dominant structural prototypes and a fair train/validation/test split.', 'python -m meidnet_eval.intake data/table.csv data/intake --id material_id --cif cif --props band_gap'],
  ['Block S0: can this dataset support what you want?', 'The preview grades the data before any training: compositions per element decides generation versus screening, and the property\'s zeros and shared profiles decide whether it is well posed.', 'python -m meidnet_eval.preview data/intake --gap band_gap --targets 1 2 3'],
  ['Train', 'A meidnet.yaml selects the architecture: decoder geometry (free or symmetry), latent size, loss weights, element features, cell size. Change it, or change the code in engine/meidnet, and train.', 'meidnet init && meidnet train meidnet.yaml'],
  ['Blocks S1–S4, S8, S9: the scorecard', 'The trained model is graded against the same bands as the studies on this site; the output is the block table with verdicts and the reason for each.', 'python -m meidnet_eval.scorecard data/intake --models mine=model.pt --gap band_gap --out scorecard/'],
  ['Blocks S5–S7: generate for a target and check it independently', 'Family-free generation with the symmetry decoder, labels read from the returned cells, then the independent judge; the instrument sheet turns the result into the requested-in, delivered-out table.', 'python -m meidnet_eval.conditional_generate --ckpt model.pt --geometry wyckoff --targets 1 2 3 --out results/pool\npython -m meidnet_eval.target_calibration results/pool --judge megnet --test-csv data/intake/test.csv --select 0.5\npython -m meidnet_eval.instrument_sheet --pool results/pool --out results/instrument'],
  ['Read the result the way this site does', 'The bands are defined once, in stages.py; the markdown report lists every block, metric, value and verdict. The validate command proves the bands still grade the reference configurations correctly after you change them.', 'python -m meidnet_eval.stages --validate\npython -m meidnet_eval.stages --markdown --out STAGES.md'],
];

export default function Method() {
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow page" id="main">
        <div className="page-head"><h1>{M.h1}</h1><p>{M.lead}</p></div>
        <section id="mechanism">
          <h2>Mechanism</h2>
          <div className="stack" style={{ gap: 12 }}>{MECHANISM.map(([t, d], i) => <div className="card card-tight step-card" key={t}><div className="n">{i + 1}</div><h3>{t}</h3><p className="muted small" style={{ margin: 0 }}>{d}</p></div>)}</div>
        </section>
        <section className="section" id="strengths">
          <h2>What the measurements support</h2>
          <div className="cards-2">{STRENGTHS.map(([t, d]) => <div className="card" key={t}><h3>{t}</h3><p className="muted small">{d}</p></div>)}</div>
        </section>
        <section className="section" id="limits">
          <h2>Where it stops</h2>
          <div className="cards-2">{LIMITS.map(([t, d]) => <div className="card" key={t}><h3>{t}</h3><p className="muted small">{d}</p></div>)}</div>
        </section>
        <section className="section" id="run">
          <h2>Run it on your data</h2>
          <p className="muted">Every block on this site is a program you can download and change. The sequence below takes a folder of structures and a property table through the same stages, with the same bands, on your computer. Each block page shows the code behind its metrics; the <Link to="/pipeline">pipeline</Link> lists which component computes what.</p>
          <ol className="run-steps">
            {RUN_STEPS.map(([t, d, cmd]) => (
              <li key={t}>
                <h3>{t}</h3>
                <p className="muted small">{d}</p>
                <pre className="cmd">{cmd}</pre>
              </li>
            ))}
          </ol>
          <p className="small muted">Checkpoints trained for the studies are on the <Link to="/studies">studies pages</Link>, each with its training configuration, so a run can start from one of them instead of from scratch. Relaxation and hull energies need the local extras named in the result of a generation job.</p>
        </section>
        <section className="section" id="requirements">
          <h2>What a dataset needs</h2>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th scope="col">to do this</th><th scope="col">the data needs</th><th scope="col">measured on</th></tr></thead>
              <tbody>
                <tr><td>predict properties from structures</td><td className="small">a well-posed property: few materials sharing one property profile, few zeros; a few hundred structures suffice</td><td className="small">166 training structures → 0.19 spreads</td></tr>
                <tr><td>screen an enumerated design space</td><td className="small">a structural family the data fit, and a property the encoder predicts</td><td className="small">634 and 166 training structures</td></tr>
                <tr><td>generate structures without a family</td><td className="small">about 200 distinct compositions per element, so the decoder can recover compositions</td><td className="small">MP-20: 817 per element</td></tr>
                <tr><td>trust an independent judge</td><td className="small">a held-out split the judge can be measured on before it judges anything</td><td className="small">every study</td></tr>
              </tbody>
            </table>
          </div>
          <p className="small muted" style={{ marginTop: 12 }}>The S.U.N. vocabulary (stable, unique, novel) follows LeMat-GenBench; novelty here is the AMD distance to the nearest training structure, uniqueness a structure match. <Link to="/pipeline">The blocks and their bands</Link> · <Link to="/studies">the studies</Link>.</p>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
