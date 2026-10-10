// Prose for the research pages. Numbers come from the API; this file holds the sentences around them.

/** The executed studies, in reading order, with the short name a table column uses. */
export const STUDY_DATASETS: Array<[string, string]> = [['perov5', 'Perov-5'], ['mp-perovskites', 'MP perovskites'], ['user-246', 'Upload (246)'], ['mp20', 'MP-20'], ['jarvis-dp', 'JARVIS DP']];
export const home = {
  eyebrow: 'MEIDNet Matter · inverse materials design, hands on',
  h1: 'Explore materials. Train a small model. Discover candidates.',
  lead: 'Inverse design on a real dataset, in the browser, with nothing to install: see what a materials dataset holds, watch a MEIDNet model learn from it, and ask the full model for crystal structures with a requested band gap. Every number comes with its evidence and its limits.',
  ctaExplore: 'Start exploring',
  ctaGenerate: 'Run a band-gap search',
  ctaDemo: 'Search within the Perov-5 family',
  example: 'Example dataset: Perov-5, 18,928 cubic perovskites with two DFT properties. No setup required.',
  stages: [
    ['01', 'Explore', 'Understand the data', 'The band-gap distribution, a map of the learned representation, and any material\'s cell and nearest neighbours.', '/explore'],
    ['02', 'Train', 'Try a small experiment', 'A real MEIDNet training on 1,500 materials, about a minute at the default 20 epochs: the curves, the predictions against the reference values, the map forming, and the full model to compare with.', '/train'],
    ['03', 'Generate', 'Inspect candidates', 'Ask for a band gap and get cells read by two models, with their checks, their limits and the files to take further.', '/generate'],
  ] as Array<[string, string, string, string, string]>,
  after: 'Satisfied with the small run? The same recipe at full size runs on your own computer with one command, on your own data too.',
  researchTitle: 'The evidence behind it',
  researchLead: 'The studies this site is built on, the ten-block pipeline with its bands and code, and the method with its limits. Kept whole, one step away.',
  prism: 'Matter is the application half of MEIDNet. The method itself, its benchmarks, the documentation and the Studio for your own tables live in MEIDNet Prism.',
  prismCta: 'Open MEIDNet Prism',
  plain: 'New to the field? A band gap is the energy a material needs before its electrons can move freely. It decides whether a material behaves as a metal, a semiconductor or an insulator, so asking for a band gap is asking for a kind of behaviour. The app proposes crystal structures that two machine-learning models of different lineage expect to have the gap you asked for, at the level of theory the data was computed with (PBE).',
  discoveriesTitle: 'What the generator has delivered',
  discoveriesLead: 'Structures accepted after relaxation by two models of different lineage, both estimating the PBE band gap the data records: generated for a band gap on MP-20, and screened or generated within the double-perovskite family on public JARVIS-DFT data. Hover to pause; click a card to open its study.',
  walkthroughTitle: 'How a request becomes a structure, in six steps',
  walkthroughLead: 'An animated walkthrough on a real result: press play, or step through it. One sentence for a newcomer, one for a researcher.',
  featuredTitle: 'The MP-20 study: requested in, delivered out',
  featuredLead: 'Relaxed, retrospective results: seven requested gaps between 0.5 and 4 eV, 25 cells each. A live search returns unrelaxed cells; its plot is drawn the same way.',
  pipelineTitle: 'Ten blocks, each with a question and a reference band',
  pipelineLead: 'The staged evaluation reads a dataset and a model block by block, against bands validated on configurations of known quality. Open a block to read its metrics, what each value means, the remedy when a measurement falls outside its band, and the code that computes it; each study shows how its dataset went through the blocks.',
  studiesTitle: 'The studies',
  studiesLead: 'Datasets from a complete 11,356-structure grid to 45,229 structures of general inorganic chemistry, and an independent user\'s double perovskites. Each study shows how its dataset went through the blocks, its target-following result and the checkpoints to download.',
};

export const explore = {
  h1: 'Explore the data',
  lead: 'Perov-5: 18,928 cubic ABX₃ perovskites (Castelli et al. 2012, the CDVAE split), each with a direct band gap and a formation enthalpy from DFT. The map places the 11,356 training materials by what the demo\'s model learned about their structures; click a point to see the material.',
  mapNote: 'Two principal components of a 128-dimensional learned space: a projection for looking, not a measure of similarity. The nearest neighbours on the card are computed in the full space.',
  histNote: '96% of the band gaps are exactly zero (metals at the PBE level), so the histogram draws the zero count apart; the readiness checks grade the band gap on the materials with a non-zero gap.',
  next: 'Seen enough of the data? Train a small model on 1,500 of these materials and watch it learn.',
};

export const train = {
  h1: 'Train a small model',
  lead: 'A real MEIDNet training, small and fixed, on this server: 1,500 Perov-5 materials, the demo\'s own recipe, 10 to 50 epochs. Watch the training loss and the validation error fall epoch by epoch, then read the model\'s predictions against the reference values of 500 materials it never saw, next to the full model measured on the same ones.',
  what: 'What this is: a model trained from scratch on a small subset, to show how the method learns. What it is not: the demo\'s model, which trained on 11,356 materials for 200 epochs; the small model does not drive generation on this server.',
  sampling: 'The subset keeps the band gaps visible: 30% of its materials have a non-zero gap, against 4% in Perov-5. Its validation materials come from the validation split; the test split is untouched.',
  after: 'The same recipe at full size, on your computer: download the configuration, point it at the Perov-5 CSVs (or your own table in the same layout) and run one command. The Method page has every step.',
};

export const pipeline = {
  gradeLegend: 'Meets: inside the reference band · Borderline: near its edge · Not met: outside it · Context: measured, not graded. S0 shows the route each dataset supports: generation, screening, or a set of candidates per target; a measurement outside a band is a finding about the data or the model, with its remedy on the block\'s page.',
  h1: 'The staged pipeline',
  lead: 'Ten blocks, S0 to S9. Each asks one question of a dataset and a model and reads the answer against a reference band validated on configurations of known quality: meets, borderline or not met. S0, the gate before training, answers with the route the data supports instead: generation, screening, or a set of candidates per target. A block\'s verdict is the weakest grade of its graded metrics; a metric that only predicts a quantity becomes context once that quantity is measured.',
  howToRead: 'How to read a band: the meets and borderline columns are thresholds on the metric; the reference columns give the value each known configuration reached, with its grade. "control" is the recipe without the structure losses, "fixed" the repaired model and search, "final" the best configuration, "mp" the Materials Project perovskites.',
  flowLead: 'Left to right: what the block receives, the programs that compute it (click one to read its code), the metrics it grades, and its verdict on each dataset. Metric boxes jump to their definition below.',
  codeLead: 'The code behind each block is served read-only from the installed engine. Download a component, change the column names or thresholds for your data, and run it with the command in its docstring.',
  historyTitle: 'What each dataset changed',
  historyLead: 'Every entry is a change a specific test forced. Read it as the record of how the pipeline became general.',
};

export const studies = {
  h1: 'Executed studies',
  lead: 'Four datasets, in the order they were run. Each page gives the facts of the dataset, the verdict of every block, how target following was measured and what it returned, the checkpoints to download and the commands that reproduce the result.',
  verdictNote: 'Verdicts are results against the reference bands, written as text. "documented" marks a "not met" that is the finding itself, with its reason recorded.',
  checkpointsTitle: 'Checkpoints',
  checkpointsLead: 'Trained models you can download and run with the engine. Each entry carries its checksum, size and training configuration; the download verifies the checksum.',
};

export const play = {
  familyPointer: 'Need a specific family (double perovskites, a halide variant, your own chemistry)? This generator is family-free and trained on MP-20. Train on your own data instead: Method › Run it on your data, which also has a screening command for small datasets.',
  familyLink: 'Method › Run it on your data',   // the part of familyPointer the page turns into a link
  h1: 'Generate structures for a band gap',
  lead: 'Family-free generation with the MP-20 symmetry decoder. You ask for one to three band gaps; the server generates cells, reads each cell\'s label from its own structure, asks a second model that played no part in generation, and returns the ones both place inside your window. Both are machine-learning estimates of the PBE band gap MP-20 records, and PBE gaps are usually smaller than measured ones. Relaxation is not run here: download the cells and relax them locally with the command the result gives you.',
  rangeNote: 'Measured on MP-20: accepted structures came back for 0.5–3 eV requests, with a slope of 0.71 and a precision of about ±0.7 eV per structure; it saturates above 3 eV. Expect few or no accepted structures there.',
  stabilityNote: 'Nothing here is called stable. The generated cell is a starting point; two potentials lower its energy by whole electron-volts per atom and move atoms by bond lengths. The relaxed cell is the product.',
  sharedHost: 'On this shared server a session runs one job at a time, up to three targets and ten structures each, within eight minutes. Results are removed after an hour.',
};

export const method = {
  h1: 'Mechanism, strengths and limits',
  lead: 'What the engine does, what the measurements showed it does well, and where it stops.',
};
