import { Link } from 'react-router';
import { ExternalLink, MarketingHeader, PRISM_LIMITS, SiteFooter } from '@/components/shell';
import { ResearchLayout } from '@/components/research/ResearchNav';
import { method as M } from '@/copy/research';
import { landing as L } from '@/copy/landing';
import { FlowDiagram, type DiagramBox } from '@/components/research/Diagrams';

/** The generation workflow of the live site (MP-20, without a family), in the order the Mechanism cards describe it. */
const FLOW: DiagramBox[] = [
  { title: 'Target', sub: 'The requested band gap is encoded as an anchor in the shared latent space', color: 'var(--c-targets)' },
  { title: 'Decode', sub: 'The symmetry decoder predicts a space group and the independent sites', color: 'var(--c-model)' },
  { title: 'Read back', sub: 'The cell is encoded again and its label is read from the structure', color: 'var(--c-data)' },
  { title: 'Judge', sub: 'An independent model reads the same cell; both readings must fall inside the window', color: 'var(--c-rules)' },
  { title: 'Relax', sub: 'Two machine-learning potentials relax the cell, and both readings are repeated', color: 'var(--c-search)' },
  { title: 'Proposal', sub: 'An accepted structure, to be confirmed by DFT', color: 'var(--c-candidates)' },
];

const MECHANISM: Array<[string, string]> = [
  ['Two encoders, one latent space', 'A structure encoder (an equivariant graph network over the cell) and a property encoder map a crystal and its property vector to points on the same unit sphere; a contrastive objective pulls matching pairs together. A decoder reads a point back into a cell, and a property head reads properties from a point.'],
  ['Two geometry paths in one decoder', 'The free path places every atom and failed on general chemistry (overlapping atoms, zero volume). The symmetry path predicts a space group and the few sites that symmetry does not relate; the symmetry operations build the rest. The lattice is projected onto the crystal system the space group demands and symmetry images are merged by distance (0.8 Å). Both heads live in one model, so a latent can be decoded either way.'],
  ['Sampling at the target\'s anchor', 'The requested property is encoded to a point; cells are decoded from points near it. Gradient steps that push the point until the property head reads the target were removed after measurement: they made the model report the request while drifting towards zero-gap metals.'],
  ['The label is read from the returned structure', 'The decoded cell is encoded again and its properties read there. A label read from the search point reports the request back by construction; that defect was found in the published application and is excluded everywhere.'],
  ['A qualified second model as judge', 'A second model of a different lineage, which played no part in generation, reads the same cell. It is measured on the dataset\'s own test split first, and which of its heads matches the dataset is decided by that measurement. A candidate counts only when both labels lie inside the window. Both models estimate the band gap at the level of theory the data was computed with (PBE for MP-20), so their agreement checks the generator, not the level of theory: PBE gaps are usually smaller than measured ones.'],
  ['Relax, then judge again', 'Two machine-learning potentials of different architecture relax the cell. The judges run again on the relaxed structure, which is what a user receives.'],
  ['Two modes, chosen by a measurement', 'Whether a dataset can generate or must screen an enumerated design space is decided before training from the number of compositions per element (12 → 0.1%, 30 → 0.7%, 80 → 5.4%, 218 → 64% decoder recovery on Perov-5 subsets). The curve\'s anchor, 218, is the full Perov-5 training split counted as rows per cation element, while the gate counts distinct compositions per element (549 on the same split): the threshold of 200 is provisional and is being re-measured in the gate\'s units.'],
];
const STRENGTHS: Array<[string, string]> = [
  ['Every claim has a verdict against a band', 'Ten blocks, each with metrics and thresholds (meets, borderline, not met) validated on configurations of known quality; the first, S0, chooses the route the data supports; a proxy becomes context once the quantity it predicts is measured.'],
  ['Target following was shown three ways', 'Against a DFT grid (Perov-5: Spearman 0.90–0.98, among compositions already in the grid; random proposals with the same label filter reach 0.98, so most of the gain comes from the filter); by screening with the user\'s own qualified judge (Spearman 0.68); and family-free with two judges on relaxed cells (MP-20: delivered = 0.34 + 0.71 × requested, on the relaxed cells that passed the contact and bulk tests).'],
  ['A known structure came back at its recorded gap', 'Asked for 3.0 eV on MP-20, the generator returned CaO in the structure of the MP-20 entry mp-545512, recorded at 3.12 eV (StructureMatcher against every CaO entry). Na₂O₂ and SrO came back too, as new polymorphs that match no MP-20 entry of their formula, so the recorded gaps of those formulas belong to other structures. On Perov-5, eight compounds with a literature record were returned unprompted; all carry an A-site lanthanide absent from Perov-5, so their readings are extrapolations.'],
  ['The encoder works on small data', 'The best property model of the five datasets was trained on 166 structures: 0.19 of the gap spread, r 0.97, which is 0.65 eV on 34 test structures. What it needed was a well-posed property (continuous, no metals), not volume; a generator from the same data rebuilt none of its test compositions.'],
  ['Every step reports what it rejected', 'Funnels, per-stage counts and the reason for each rejection are part of every result; a step that removes nothing when it should is flagged.'],
];
const LIMITS: Array<[string, string]> = [
  ['Serviceable range and resolution', 'On MP-20 accepted structures came back for requests of 0.5, 1.5, 2.5 and 3 eV; above 3 eV the generator saturates. With one to four sound relaxed cells per request, adjacent requests cannot yet be told apart reliably; the precision is about ±0.7 eV per structure.'],
  ['The generated cell is a starting point', 'Relaxation lowered the energy of the 13 sound cells by 1.2–17 eV/atom (median 5.4) and moved atoms by up to 0.4–9.7 Å, and on MP-20 more than half of the relaxed cells (20 of 37) collapsed, atoms pushed into each other, and are set aside by the contact test; 4 more were slabs or sparse cells (an empty layer over 6 Å or a packing fraction under 0.12) and are set aside by the bulk test, which the live generator now applies to every cell it draws. Coordinate accuracy is the open defect (RMSE 0.24 in fractional units; a discrete coordinate grid did not fix it). A Wyckoff-position head is the identified next change.'],
  ['Stability is a machine-learning screen', 'Where it is given (Perov-5, the user upload, the JARVIS double perovskites) stability is the energy above a convex hull computed with machine-learning potentials, never DFT; on the double perovskites it was calibrated on 12 known materials (rank correlation 0.47, 0.77 without one outlier). MP-20 has no hull: there "relaxes to a minimum with the requested gap" is the strongest statement made.'],
  ['Discovery with a family is perovskite-shaped', 'The screening command accepts any family file, but blocks S5–S7 were validated only on perovskite families (ABX₃, A₂BB′X₆), every family shipped is cubic, and the tolerance and octahedral factors are perovskite rules. Family-free generation needs hundreds of compositions per element (the 200 line is being re-measured), which only MP-20 reached.'],
  ['Judges are models', 'Both labels come from machine-learned models, qualified on each dataset\'s test split: on MP-20 the judge errs by 0.10 eV and the generator\'s label by 0.27 eV; on the JARVIS double perovskites the judge errs by 0.82 eV, wider than the ±0.5 eV window; on the upload the judge was trained on the same data (0.59 eV). Qualification uses up to 80 test structures and keeps the best of the judge\'s heads on them, so these errors are optimistic. No result is DFT or experiment.'],
  ['Elements are a user control', 'The pipeline optimises the target, not practicality: on one dataset seven of thirteen shortlisted candidates contained thallium. Radioactive elements are excluded by default; toxic ones are a switch.'],
];

const RUN_STEPS: Array<[string, string, string]> = [
  ['Install', 'One command from PyPI: the engine and the application with the judge, with CPU torch (the default Linux build pulls about 2.5 GB of GPU libraries), pinned to the versions this release was tested with (Linux, Python 3.12; on another Python drop the -c line). Linux, macOS and Windows through WSL are supported; Windows 11 with Smart App Control blocks unsigned wheels, so use WSL there. The last line proves the install. On a slow or flaky network, scripts/install.sh in the repository does the same with retries and a fresh environment; the wheels are also attached to every release, for an index mirror or an offline machine (second command).', 'pip install --extra-index-url https://download.pytorch.org/whl/cpu \\\n  -c https://github.com/ABnano/MEIDNet-Matter/releases/latest/download/constraints.txt "meidnet-matter[judge]"\npython -c "import meidnet, matter, matgl; print(meidnet.__version__, matter.__version__)" && meidnet --version\n# without PyPI: the same from the release\x27s wheels\npip install --extra-index-url https://download.pytorch.org/whl/cpu \\\n  "meidnet @ https://github.com/ABnano/MEIDNet-Matter/releases/latest/download/meidnet-2.4.0.dev4-py3-none-any.whl" \\\n  "meidnet-matter[judge] @ https://github.com/ABnano/MEIDNet-Matter/releases/latest/download/meidnet_matter-0.10.2-py3-none-any.whl"'],
  ['Turn what you have into one table', 'A folder of CIF or POSCAR files plus a spreadsheet of properties becomes one CSV with a structure column. The name column may hold the file names (JVASP-123, mp-456) or compositions; a -<space group> tag picks a polymorph; every ambiguity is reported and nothing matched is an error.', 'python -m meidnet_eval.ingest_upload structures/ properties.xlsx data/ --props "Band gap" --id-col "JARVIS id"'],
  ['Audit, detect prototypes, split', 'The intake writes the audit (rows, elements, zeros, shared property profiles), the dominant structural prototypes and a fair train/validation/test split.', 'python -m meidnet_eval.intake data/table.csv data/intake --id material_id --cif cif --props band_gap'],
  ['Block S0: can this dataset support what you want?', 'The preview grades the data before any training: compositions per element decides generation versus screening, the property\'s zeros and shared profiles decide whether it is well posed. With a family it also measures the novelty frontier and how many structures have the family\'s prototype. The verdict names the next command.', 'python -m meidnet_eval.preview data/intake --gap band_gap --targets 1 2 3 --family double_perovskite_a2bbx6:halide'],
  ['Train', 'Two templates. generation: the symmetry decoder for family-free generation (what the live generator runs; the symmetry side-car is built for you). custom: a family model for screening and family generation. Training uses 4 CPU threads unless OMP_NUM_THREADS says otherwise and prints the measured pace after two epochs.', 'meidnet init --template generation --name mine --table data/intake/train.csv --properties band_gap\nmeidnet check meidnet.yaml && meidnet train meidnet.yaml'],
  ['Blocks S1–S4, S8, S9: the scorecard', 'The trained model is graded against the same bands as the studies on this site; the output is the block table with verdicts, the reason for each, and a remedy that knows your configuration. --judge megnet qualifies the judge (a second model) on your test split first (block S8): a judge is believed only after it has been measured.', 'python -m meidnet_eval.scorecard data/intake --models main=runs/mine/out/model.pt --gap band_gap --out scorecard/ --judge megnet'],
  ['Blocks S5–S7 when S0 said generation', 'One command runs the chain: generate with the symmetry decoder, labels read from the returned cells, the judge (a second model) qualified on your test split, two-judge consensus, relaxation by two potentials, re-judging, a report. The instrument sheet turns it into requested-in, delivered-out. If S0 graded the data for screening, the command says so and points to the next step.', 'python -m meidnet_eval.generate_to_target --ckpt runs/mine/out/model.pt --intake data/intake --gap band_gap --targets 1 2 3 --tag mine --out results\npython -m meidnet_eval.instrument_sheet --pool results/mine --relaxed results/mine/relaxed --consensus results/mine/relax --out results/mine/instrument'],
  ['Blocks S5–S7 when S0 said screening', 'Screening on a laptop: every composition the family allows is built on its prototype cell and labelled by the model from that structure; the ones inside the window go through the same check as generated cells (the qualified judge, two-model consensus, relaxation by two potentials, both readings again on the relaxed cells, novelty), and every accepted structure is classed as new, a rediscovery, or contradicted by a DFT value, from your data first and then from the reference set of the stability step. Any family file, any number of cation groups, any anion. A family model\'s own search (meidnet generate) prints the same check for its candidates.', 'python -m meidnet_eval.screen_local data/intake --ckpt runs/mine/out/model.pt --family double_perovskite_a2bbx6:halide --gap band_gap --targets 1 2 3 --check --out screening/'],
  ['Stability, for any route (optional)', 'The energy above the convex hull with one potential for every phase: the accepted cells and every competing phase of their chemical systems, taken from a reference set of known crystals (the public JARVIS-DFT 3D file, jdft_3d-12-12-2022.json.zip from figshare, doi:10.6084/m9.figshare.6815699, unzipped; or the Materials Project with an API key), are relaxed by the same potential, and the relaxations are cached. Known materials of your data with a DFT hull value calibrate the estimate, and implausible reference values are named. The same option, --hull-reference, works on screen_local, generate_to_target and check_candidates.', 'python -m meidnet_eval.hull_mlip screening/relaxed --reference jarvis:jdft_3d-12-12-2022.json --validate data/intake --stability-col e_above_hull'],
  ['Read the result the way this site does', 'The bands are defined once, in stages.py; the markdown report lists every block, metric, value and verdict. The validate command proves the bands still grade the reference configurations correctly after you change them.', 'python -m meidnet_eval.stages --validate\npython -m meidnet_eval.stages --markdown --out STAGES.md'],
];

export default function Method() {
  return (
    <>
      <MarketingHeader wide />
      <ResearchLayout>
        <div className="page-head"><h1>{M.h1}</h1><p>{M.lead}</p></div>
        <section id="mechanism">
          <h2>Mechanism</h2>
          <p className="note" data-testid="engine-version" style={{ marginBottom: 12 }}><b>Which engine this page describes.</b> Matter runs a development snapshot of the MEIDNet engine, meidnet 2.4.0.dev4, vendored in its repository: it adds the symmetry decoder trained on MP-20 and samples at the target&apos;s anchor. The released MEIDNet package that MEIDNet Prism documents (2.3) searches differently: it moves latent points towards the target by gradient descent and places each decoded composition on a family prototype, so it creates no new arrangement of atoms. Prism&apos;s scope page states that version&apos;s limits: <ExternalLink href={PRISM_LIMITS}>scope and limits of the released package ↗</ExternalLink></p>
          <FlowDiagram steps={FLOW} caption="From a requested property to an accepted structure (generation without a family, MP-20). Cells that collapse or are not bulk-like after relaxation are set aside." testId="generation-flow" />
          <div className="stack" style={{ gap: 12 }}>{MECHANISM.map(([t, d], i) => <div className="card card-tight step-card" key={t}><div className="n">{i + 1}</div><h3>{t}</h3><p className="muted small" style={{ margin: 0 }}>{d}</p></div>)}</div>
        </section>
        <section className="section" id="strengths">
          <h2>What the measurements support</h2>
          <div className="cards-2">{STRENGTHS.map(([t, d]) => <div className="card" key={t}><h3>{t}</h3><p className="muted small">{d}</p></div>)}</div>
        </section>
        <section className="section" id="limits">
          <h2>Where it stops</h2>
          <p className="muted">The full statement, with what your data needs and what each study checked: <Link to="/limits">Scope and limits →</Link></p>
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
        <section className="section" id="python">
          <h2>The same three stages from Python</h2>
          <p className="muted">Everything the site does is one HTTP API; <code>matter.client.Matter</code>, part of the <code>meidnet-matter</code> package, is a thin client for it: plain dicts in and out, nothing beyond the standard library, one session per client. The Explore map, a Train Lite run followed to the end with its curves and predictions, generation with both readings, the Perov-5 readiness report and search, every download.</p>
          <pre className="mono small" style={{ background: 'var(--tint)', border: '1px solid var(--line)', padding: 10, overflowX: 'auto' }}>{`from matter.client import Matter
m = Matter("https://babu09-meidnet-matter.hf.space")

points = m.explore()                                  # every training material on the latent map
sro = m.material("mp-5229")                           # its values, its cell, its nearest neighbours

job = m.wait(m.train(epochs=20, seed=0), every=1)     # a small MEIDNet training, followed to the end
job["result"]["against_spread"]                       # its error against the spread, next to the full model's
m.download(m.urls.train_model(job["job_id"]), "lite.pt")

gen = m.wait(m.generate(targets=[2.0], per_target=4)) # cells for a band gap, read by two models
m.download(m.urls.generate_zip(gen["job_id"]), "cells.zip")`}</pre>
          <p className="small muted">The full reference, with the Perov-5 project, errors and sessions: <ExternalLink href="https://github.com/ABnano/MEIDNet-Matter/blob/main/docs/python-api.md">docs/python-api.md ↗</ExternalLink>. The server's own route list: <code>/docs</code>.</p>
        </section>
        <section className="section" id="requirements">
          <h2>What a dataset needs</h2>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th scope="col">to do this</th><th scope="col">the data needs</th><th scope="col">measured on</th></tr></thead>
              <tbody>
                <tr><td>predict properties from structures</td><td className="small">a well-posed property: continuous, few zeros, few materials sharing one property profile; a few hundred structures can be enough</td><td className="small">166 training structures → 0.19 spreads (0.65 eV on 34 test structures); 897 with 35% zero gaps fell short on telling metals from non-metals</td></tr>
                <tr><td>screen an enumerated design space</td><td className="small">a structural family the data fit, a property the encoder predicts, and a judge whose error is smaller than the window</td><td className="small">166, 634 and 897 training structures</td></tr>
                <tr><td>generate structures without a family</td><td className="small">hundreds of distinct compositions per element (the 200 line is being re-measured) and many structure types</td><td className="small">MP-20: 817 per element; 11.3, 12 and 48.5 per element went to screening</td></tr>
                <tr><td>trust a second model as judge</td><td className="small">a held-out split the judge can be measured on before it judges anything, at the data&apos;s level of theory</td><td className="small">every study; MEGNet failed on Perov-5 (1.71 eV)</td></tr>
                <tr><td>estimate stability</td><td className="small">a reference set of known crystals that covers the chemistry, and a machine-learning potential</td><td className="small">Perov-5, the upload, the double perovskites (calibrated on 12 known materials)</td></tr>
              </tbody>
            </table>
          </div>
          <p className="small" style={{ marginTop: 12 }}>What each goal needs, what worked and what did not, and why a few hundred structures train a property model but not a generator: <Link to="/limits#data">Scope and limits →</Link></p>
          <p className="small muted" style={{ marginTop: 12 }}>The S.U.N. vocabulary (stable, unique, novel) follows LeMat-GenBench; stable here means within 0.1 eV/atom of the convex hull of competing phases, computed with a machine-learning potential (what LeMat-GenBench calls metastable), never a formation energy against the elements alone; novelty is the AMD distance to the nearest training structure, uniqueness a structure match. <Link to="/pipeline">The blocks and their bands</Link> · <Link to="/studies">the studies</Link>.</p>
        </section>
        <section className="section" id="cite">
          <h2>How to cite</h2>
          <div className="card" data-testid="citation"><p className="small muted">{L.citation}</p><ExternalLink href={`https://doi.org/${L.doi}`} className="small">doi:{L.doi}</ExternalLink></div>
        </section>
      </ResearchLayout>
      <SiteFooter wide />
    </>
  );
}
