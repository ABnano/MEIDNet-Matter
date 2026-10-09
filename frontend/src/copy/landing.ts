export const landing = {
  eyebrow: 'MEIDNet Matter',
  descriptor: 'Multimodal inverse design for materials discovery',
  h1: 'From your materials data to candidate structures.',
  lead: 'Upload crystal structures and properties. MEIDNet Matter learns the relationships in your dataset, tests whether your target is supported by the learned representation, and searches for candidate materials that satisfy your property goals and scientific constraints.',
  promise: 'Bring data → learn → assess → design → validate',
  ctaPrimary: 'Try the Perov-5 demo',
  ctaSecondary: 'Start with my data',
  trust: 'Open source · Reproducible runs · Downloadable structures · Powered initially by MEIDNet',
  previewTitle: 'A design request and what comes back',
  previewLead: 'The demo project: cubic ABX₃ perovskites of the Perov-5 dataset, two DFT properties and two MEIDNet models; the request below was run with the published model.',
  how: [
    ['Define the goal', 'Set a target value or range for each property and the chemistry rules a candidate must satisfy.'],
    ['Check readiness', 'Matter measures how well the model predicts each property on held-out data, where your target sits in the training distribution and how many structures share it.'],
    ['Search', 'A latent-space search proposes structures, decodes them and keeps those that satisfy the rules and the target.'],
    ['Validate', 'Each candidate carries its predictions, domain status, rule results, nearest training materials and its stage on a six-step validation ladder. Export CIFs and targets.csv for MLIP screening, DFT or experiment, and score them on Prism.'],
  ],
  why: [
    ['Know when not to trust the inverse', 'Before a search runs, the readiness report states whether the target lies inside the model\'s training range and how well each property is predicted on held-out data.'],
    ['One property target, many possible structures', 'When many training materials share the target value, Matter says so, groups the candidates into clusters of alternatives and lets you prioritise target accuracy, diversity, stability or novelty.'],
    ['Every candidate comes with evidence', 'Nearest training materials, latent distances, rule values, and the agreement between the encoder and the search are shown for every candidate.'],
    ['Reproducible by design', 'A run bundle holds the goal, the model identity, the seed, the search settings, the candidates and their CIFs, with file hashes.'],
  ],
  applications: [
    ['Oxide perovskites with a target band gap', 'The demo: a direct band gap near 2 eV with a bounded formation enthalpy, lead excluded.'],
    ['Lead-free halide perovskites', 'The same workflow on the halide variant; the readiness report shows which anions the training data cover.'],
    ['Double perovskites', 'A₂BB′X₆ cells with two B-site elements, with the same rules and evidence.'],
  ],
  scope: 'Matter currently searches property-conditioned candidates within supported structural families. Free-geometry crystal generation is planned as additional design backends mature.',
  ecosystem: [
    ['MEIDNet Prism', 'Learn · Benchmark · Develop', 'Learn the method, benchmark any model with the same metric families as LeMat-GenBench, develop with the meidnet package and the Studio.'],
    ['MEIDNet Matter', 'Design & Discover', 'Bring data, define targets, check readiness, search, compare, validate and export candidates as versioned records.'],
  ],
  citation: 'A. Babu, R. Almeida Gouvêa, P. Vandergheynst, G.-M. Rignanese, MEIDNet: Multimodal generative AI framework for inverse materials design, npj Computational Materials 12, 287 (2026).',
  doi: '10.1038/s41524-026-02153-3',
};

/** The request of the preview and the three candidates a real run of it returned (the published model, exploratory mode;
 * values as the API gave them: predicted, with their domain status and dataset check). */
export const previewRequest = { gap: '1.5 ± 0.3 eV', dhf: '≤ 1.0 eV/atom', excluded: 'Pb', family: 'oxide perovskite' };
export const previewCandidates = [
  { formula: 'SrVO3', elements: { A: 'Sr', B: 'V', X: 'O' }, a: 4.08, gap: 1.48, dhf: 0.99, domain: 'Interpolating', rules: '8/8', novelty: 'Found in the Perov-5 dataset', agreement: 'disagree' },
  { formula: 'CaTiO3', elements: { A: 'Ca', B: 'Ti', X: 'O' }, a: 4.22, gap: 1.5, dhf: -2.17, domain: 'Extrapolating', rules: '8/8', novelty: 'Found in the Perov-5 dataset', agreement: 'disagree' },
  { formula: 'NaTaO3', elements: { A: 'Na', B: 'Ta', X: 'O' }, a: 4.16, gap: 1.51, dhf: -5.45, domain: 'Extrapolating', rules: '8/8', novelty: 'Found in the Perov-5 dataset', agreement: 'disagree' },
];
