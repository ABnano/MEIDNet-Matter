// Prose for the research pages. Numbers come from the API; this file holds the sentences around them.

/** The executed studies, in reading order, with the short name a table column uses. */
export const STUDY_DATASETS: Array<[string, string]> = [['perov5', 'Perov-5'], ['mp-perovskites', 'MP perovskites'], ['user-246', 'Upload (246)'], ['mp20', 'MP-20'], ['jarvis-dp', 'JARVIS DP']];
export const home = {
  eyebrow: 'MEIDNet Matter · multimodal inverse design for materials',
  h1: 'From a target property to candidate crystal structures.',
  lead: 'Set a band-gap target, inspect the generated structures, and see which checks each candidate has passed. Model predictions, reference DFT values and further validation are shown separately, never merged into one score.',
  ctaExplore: 'Explore a completed result',
  ctaPlay: 'Run a band-gap search',
  ctaDemo: 'Try the Perov-5 demo',
  scope: 'Live MP-20 band-gap generation · Perov-5 demo search · own-data workflow available locally',
  prism: 'Matter is the application half of MEIDNet. The method itself, its benchmarks and the documentation live in MEIDNet Prism.',
  prismCta: 'Open MEIDNet Prism',
  plain: 'New to the field? A band gap is the energy a material needs before its electrons can move freely. It decides whether a material behaves as a metal, a semiconductor or an insulator, so asking for a band gap is asking for a kind of behaviour. The app proposes crystal structures that two machine-learning models of different lineage expect to have the gap you asked for, at the level of theory the data was computed with (PBE).',
  discoveriesTitle: 'What the generator has delivered',
  discoveriesLead: 'Structures accepted after relaxation by two models of different lineage, both estimating the PBE band gap the data records: generated for a band gap on MP-20, and screened or generated within the double-perovskite family on public JARVIS-DFT data. Hover to pause; click a card to open its study.',
  choicesTitle: 'Three ways in',
  choices: [
    ['Explore a result', 'The MP-20 study: 175 generated cells, 4 accepted by two judges on relaxed cells that passed the contact and bulk tests, the response curve, every structure and its evidence.', '/studies/mp20', 'Open the study'],
    ['Set my target', 'Ask for one to three band gaps and get cells within minutes, each with a label read from its own structure, a second model\'s reading and three statuses kept apart. Or walk the Perov-5 demo: goal, readiness, candidates, export.', '/play', 'Run a band-gap search'],
    ['Use my data locally', 'Nothing is uploaded on this site. Eight commands take a folder of structures and a property table through the same stages, with the same bands, on your computer; the code of every block is here to read and change.', '/method#run', 'The steps'],
  ],
  featuredTitle: 'The MP-20 study: requested in, delivered out',
  featuredLead: 'Relaxed, retrospective results: seven requested gaps between 0.5 and 4 eV, 25 cells each. A live search returns unrelaxed cells; its plot is drawn the same way.',
  howTitle: 'How a request becomes a structure',
  how: [
    ['Request', 'A band gap in electron-volts. The property vector is encoded to a point in the shared latent space; no gradient refinement follows, because on MP-20 that step made the model report the target while drifting towards metals.'],
    ['Generate', 'The symmetry decoder predicts a space group and the few sites that symmetry does not relate; the symmetry operations build the cell. One anion is required and radioactive elements are excluded.'],
    ['Label from the structure', 'The returned cell is encoded again and its properties read from that encoding, never from the search latent. Cells the encoder cannot read are not reported.'],
    ['Judge with a second model', 'A second model of different lineage, qualified on the dataset\'s own test split, reads the same cell. A candidate counts only when both agree within the window. Both estimate the PBE gap the data records.'],
    ['Relax and re-judge', 'Two machine-learning potentials relax the cell; both judges are run again on the relaxed structure. That is the structure a user receives.'],
  ],
  pipelineTitle: 'Ten blocks, each with a question and a reference band',
  pipelineLead: 'The staged evaluation grades a dataset and a model block by block, against bands validated on configurations of known quality. Open a block to read its metrics, what each value means, the remedy when it fails, and the code that computes it.',
  studiesTitle: 'The studies',
  studiesLead: 'Four datasets, from a complete 11,356-structure grid to 45,229 structures of general inorganic chemistry. Each study lists its block verdicts, its target-following result and the checkpoints to download.',
  tryTitle: 'Try it',
  tryLead: 'Generate structures for a band gap with the MP-20 model, judged twice, in a few minutes. Or walk through the Perov-5 demo project: goal, readiness, candidates, export.',
};

export const pipeline = {
  h1: 'The staged pipeline',
  lead: 'Ten blocks, S0 to S9. Each asks one question of a dataset and a model and answers PASS, WARN or FAIL against a band validated on configurations of known quality. A block\'s verdict is the worst grade of its graded metrics; a metric that only predicts a quantity becomes context once that quantity is measured.',
  howToRead: 'How to read a band: PASS and WARN are thresholds on the metric; the reference columns give the value each known configuration reached, with its grade. "control" is the recipe without the structure losses, "fixed" the repaired model and search, "final" the best configuration, "mp" the Materials Project perovskites.',
  flowLead: 'Left to right: what the block receives, the programs that compute it (click one to read its code), the metrics it grades, and its verdict on each dataset. Metric boxes jump to their definition below.',
  codeLead: 'The code behind each block is served read-only from the installed engine. Download a component, change the column names or thresholds for your data, and run it with the command in its docstring.',
  historyTitle: 'What each dataset changed',
  historyLead: 'Every entry is a change a specific test forced. Read it as the record of how the pipeline became general.',
};

export const studies = {
  h1: 'Executed studies',
  lead: 'Four datasets, in the order they were run. Each page gives the facts of the dataset, the verdict of every block, how target following was measured and what it returned, the checkpoints to download and the commands that reproduce the result.',
  verdictNote: 'Verdicts are results against the reference bands, written as text. "documented" marks a FAIL that is the finding itself, with its reason recorded.',
  checkpointsTitle: 'Checkpoints',
  checkpointsLead: 'Trained models you can download and run with the engine. Each entry carries its checksum, size and training configuration; the download verifies the checksum.',
};

export const play = {
  familyPointer: 'Need a specific family (double perovskites, a halide variant, your own chemistry)? This generator is family-free and trained on MP-20. Train on your own data instead: Method › Run it on your data, which also has a screening command for small datasets.',
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
