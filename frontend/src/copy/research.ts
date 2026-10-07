// Prose for the research pages. Numbers come from the API; this file holds the sentences around them.
export const home = {
  eyebrow: 'MEIDNet Matter · multimodal inverse design for materials',
  h1: 'Ask for a property. Get structures, with the evidence attached.',
  lead: 'MEIDNet Matter learns the relation between crystal structures and their properties, checks whether a target is supported, and returns candidate structures with their labels, an independent judgement, and a record of every stage they passed.',
  ctaPlay: 'Generate for a band gap',
  ctaDemo: 'Try the Perov-5 demo',
  discoveriesTitle: 'What the pipeline has found',
  discoveriesLead: 'Results from four datasets. Every number traces to a block of the staged evaluation, a component, and a journal entry.',
  howTitle: 'How a request becomes a structure',
  how: [
    ['Request', 'A band gap in electron-volts. The property vector is encoded to a point in the shared latent space; no gradient refinement follows, because on MP-20 that step made the model report the target while drifting towards metals.'],
    ['Generate', 'The symmetry decoder predicts a space group and the few sites that symmetry does not relate; the symmetry operations build the cell. One anion is required and radioactive elements are excluded.'],
    ['Label from the structure', 'The returned cell is encoded again and its properties read from that encoding, never from the search latent. Cells the encoder cannot read are not reported.'],
    ['Judge independently', 'A second model of different lineage, qualified on the dataset\'s own test split, reads the same cell. A candidate counts only when both agree within the window.'],
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
  h1: 'Generate structures for a band gap',
  lead: 'Family-free generation with the MP-20 symmetry decoder. You ask for one to three band gaps; the server generates cells, reads each cell\'s label from its own structure, asks an independent judge, and returns the ones both place inside your window. Relaxation is not run here: download the cells and relax them locally with the command the result gives you.',
  rangeNote: 'Measured on MP-20: the generator serves 0.5–3 eV with a slope of 0.86 and a precision of about ±0.7 eV per structure; it saturates above 3 eV. Expect few or no accepted structures there.',
  stabilityNote: 'Nothing here is called stable. The generated cell is a starting point; two potentials lower its energy by whole electron-volts per atom and move atoms by bond lengths. The relaxed cell is the product.',
  sharedHost: 'On this shared server a session runs one job at a time, up to three targets and ten structures each, within eight minutes. Results are removed after an hour.',
};

export const method = {
  h1: 'Mechanism, strengths and limits',
  lead: 'What the engine does, what the measurements showed it does well, and where it stops.',
};
