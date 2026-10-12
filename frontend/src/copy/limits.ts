// Scope and limits: one statement of what the pipeline measured, what it did not, and what a dataset needs. The study
// pages show their own row of STUDY_EVIDENCE, so both places say the same thing. Every number comes from the study files
// under examples/research/studies (limits.test.ts checks the ones it can).

export const limits = {
  h1: 'Scope and limits',
  lead: 'This page summarises the evidence behind the results reported on this site, the conditions under which the method has been shown to work, and its known limitations. All figures are taken from the five case studies.',
  leadDft: 'Before a candidate is considered for synthesis, it should pass a DFT calculation. For Perov-5, the MEIDNet paper carried out this validation: 140 candidates generated from property targets with the published model were screened for stability, uniqueness and novelty, 19 passed, and the candidates were checked by DFT.',
  leadSite: 'The candidates generated in the case studies on this site have not yet been calculated with DFT; they remain proposals until they are.',
  paperLink: 'The MEIDNet paper ↗',
  paperRecordLink: 'Its DFT-validated record on MEIDNet Prism ↗',
  evidenceTitle: 'Levels of evidence',
  evidenceLead: 'Each reported quantity rests on one of four levels of evidence, listed from the strongest to the weakest.',
  evidence: [
    ['DFT reference', 'A value computed with density functional theory and recorded in the dataset or in a public database (Perov-5, MP-20, JARVIS-DFT), at the level of theory of that database.', 'Ba₂MgWO₆, returned for a 3 eV request and recorded at 2.82 eV'],
    ['Model estimate', 'A machine-learning prediction made from the structure, either by the generating model or by an independent model of different lineage (the judge). The error of each model is measured on the test split of its dataset.', 'Judge error of 0.10 eV on MP-20 and 0.82 eV on the double perovskites'],
    ['Machine-learned hull', 'The energy above the convex hull, computed with a machine-learning interatomic potential against a reference set of known crystals. It serves as a screen and has been calibrated on few known materials.', 'Calibration on 12 known double perovskites: rank correlation 0.47 (0.77 without one outlier)'],
    ['Proposal', 'A candidate that satisfies the model estimates and the checks but has no DFT reference. It indicates a calculation worth performing rather than a result.', 'The new compositions from the case studies on this site'],
  ] as Array<[string, string, string]>,
  scales: 'Two scales are used for model error. The readiness report and the training page describe an error below 0.25 of the property\'s spread as good and below 0.5 as fair, whereas block S1 of the evaluation pipeline accepts errors up to 0.7. The former characterises the precision of a single model; the latter is an acceptance threshold.',
  dataTitle: 'Data requirements',
  dataLead: 'The content of a dataset predicts success better than its size. For each task, the table gives the deciding factor, the cases in which the method succeeded or failed, and the expected behaviour when the requirement is not met.',
  route: {
    input: { title: 'Your dataset', sub: 'Crystal structures with one or more computed or measured properties', color: 'var(--c-data)' },
    gate: { title: 'Data gate (block S0), before training', sub: 'Distinct compositions per element, share of zero values, shared property profiles and fit to a structural family', color: 'var(--c-rules)' },
    routes: [
      { title: 'Generation without a family', sub: 'Several hundred compositions per element and many structure types. Example: MP-20.', color: 'var(--c-model)' },
      { title: 'Screening within a family', sub: 'Fewer compositions per element; the data fit one structural family. Examples: the external upload, MP perovskites, the double perovskites.', color: 'var(--c-family)' },
      { title: 'Candidate sets', sub: 'A complete grid of one structure type, in which most materials share their property profile. Example: Perov-5.', color: 'var(--c-targets)' },
    ],
    check: { title: 'The same check on every route', sub: 'Label read from the structure, independent judge, relaxation by two potentials and both readings repeated; DFT confirmation remains to be done.', color: 'var(--c-candidates)' },
    caption: 'Which route a dataset supports. The data gate decides before any model is trained.',
  },
  dataHead: ['task', 'deciding factor', 'succeeded', 'failed', 'when the requirement is not met'],
  data: [
    ['Property prediction from structure', 'A well-posed property: continuous, with few zero values and few materials sharing the same property profile', '166 training structures (external upload: r = 0.97; MAE 0.65 eV on a spread of 3.62 eV)', '897 training structures (double perovskites, 35% zero gaps): metals and non-metals separated correctly for 82% of test structures, below the 85% threshold', 'Band-gap errors of about 0.6–0.7 eV, largely independent of dataset size. When most values are zero, few rows carry information (Perov-5: 441 non-zero band gaps among 11,356 training structures).'],
    ['Screening within a structural family', 'Data that fit one structural family, a property model that passes block S1, and a judge whose error is smaller than the target window', '166, 634 and 897 training structures', 'No failure observed so far', 'A shortlist within the structure type of the family, with misclassifications near the metal/non-metal boundary'],
    ['Generation without a structural family', 'Several hundred distinct compositions per element and a wide range of structure types', 'MP-20: 817 compositions per element and 6,282 structure types', 'Double perovskites (48.5 per element), MP perovskites (12) and the external upload (11.3): the decoders recovered 4.2%, 1.4% and 0% of the test compositions', 'The data gate (block S0) assigns the dataset to screening'],
    ['Use of an independent model as judge', 'An error measured on the test split of the dataset, at its level of theory, and smaller than the target window', 'MP-20: 0.10 eV', 'Perov-5: MEGNet error of 1.71 eV (the Perov-5 band gaps are computed with GLLB-SC)', 'Agreement with the judge adds little evidence; a DFT calculation is required'],
    ['Stability estimate', 'A reference set of known crystals covering the chemical system, and a machine-learning potential', 'Perov-5 and the external upload (Materials Project reference); double perovskites (JARVIS-DFT reference)', 'Cs₂InFeBr₆: the JARVIS-DFT reference set contains no cesium halide, so its stability was not assessed', 'The estimate serves as a screen ahead of a DFT calculation'],
  ] as Array<[string, string, string, string, string]>,
  smallTitle: 'Small datasets support property prediction, not generation',
  small: 'The external upload of 246 entries (236 matched; 166 for training, 36 for validation and 34 for testing) yielded the most accurate property model on this site, while its decoder recovered none of the test compositions, as the data gate had predicted before training. Its candidates were therefore obtained by screening known structure types and assessed by a judge trained on the same data. Because the evaluation rests on 34 test structures, the reported error of 0.65 eV carries a wide uncertainty (approximately 0.48–0.81 eV). With the default test fraction of 15%, roughly 80 test structures, or about 530 rows, are needed before a verdict close to a threshold can be considered reliable; this figure is a rule of thumb.',
  thresholdNote: 'The generation threshold is provisional. The rule of approximately 200 compositions per element derives from a curve measured on Perov-5 subsets, whose reference point (218) corresponds to the full training split counted as rows per cation element; the data gate itself counts distinct compositions per element, which gives 549 for the same split. The routes assigned in the five studies are unaffected, as each dataset lies well on one side of the threshold, but the threshold is being re-measured in the units used by the gate.',
  ownData: 'Analyses of your own data run locally; this site does not accept uploads.',
  studiesTitle: 'Validation by study',
  studiesLead: 'For each case study, the references against which the results were checked and what remains unverified. The same summary appears on each study page, together with its limitations.',
  studiesHead: ['study', 'data', 'route', 'checked against', 'not checked'],
  structuresTitle: 'Structural scope',
  structures: [
    ['Within a structural family', 'The Perov-5 demonstration, screening and family-based generation place each composition on the cell of the family. All families currently provided are cubic (Pm-3m ABX₃ and its mixed-anion variants; Fm-3m A₂BB′X₆). Relaxation may lower the symmetry.'],
    ['Without a structural family', 'The MP-20 generator constructs each cell in a space group predicted by its decoder. Valid cells spanned 55 space groups, and the accepted structures were monoclinic, tetragonal or orthorhombic before relaxation.'],
    ['User-defined families', 'A family file may specify a general cell (a, b, c, α, β, γ), which is scaled from one edge with its shape held fixed. No non-cubic family is provided or has been tested, and such a family requires its own rules, since the tolerance and octahedral factors apply to perovskites.'],
  ] as Array<[string, string]>,
  strengthsTitle: 'Demonstrated capabilities',
  strengths: [
    'The data gate (block S0) assigned a route to each of the five datasets before training. For the three datasets assigned to screening, the decoders subsequently recovered only 0–4.2% of the test compositions, consistent with that assignment.',
    'A property model trained on 166 structures predicted a well-posed band gap with r = 0.97 (MAE 0.65 eV).',
    'On Perov-5, the delivered band gaps followed the requested values against DFT references (ρ = 0.90–0.98), with 57–83% of the returned compositions within the target window, compared with 7.7% for random proposals; these compositions lie within the training grid.',
    'Without a structural family, the MP-20 generator produced 4 accepted structures out of 175 after relaxation and two independent estimates; CaO was recovered in its recorded structure, whose band gap is recorded at 3.12 eV.',
    'An independent user reproduced the pipeline from the published packages on public data (JARVIS-DFT double perovskites), obtaining seven new charge-balanced compositions that await DFT confirmation and one known compound at its recorded band gap; the four accepted structures that were contradicted by DFT or are not charge balanced are reported.',
    'Each step reports the candidates it rejects; on MP-20, for example, 20 of 37 relaxed cells collapsed and were excluded.',
  ],
};

/** One row per study: the data, the route the data gate chose, what results were checked against, what was not. */
export const STUDY_EVIDENCE: Record<string, { data: string; route: string; checked: string; notChecked: string }> = {
  perov5: {
    data: '18,928 cubic ABX₃ perovskites (DFT; GLLB-SC gaps)',
    route: 'candidate sets',
    checked: 'Perov-5\'s own DFT values of the returned compositions; a CGCNN judge (0.59 eV on non-zero gaps); an ML hull against Materials Project phases; literature. The candidates of the MEIDNet paper, generated with the published Perov-5 model, were checked by DFT',
    notChecked: 'The novel candidates: all contain a lanthanide absent from Perov-5, so their readings are extrapolations; no DFT',
  },
  'mp-perovskites': {
    data: '919 Materials Project perovskites (634 for training)',
    route: 'screening',
    checked: 'The property model on 146 held-out materials (0.94 eV on non-zero gaps); two potentials agree on 16 of 16 relaxed space groups',
    notChecked: 'The 19 oxide candidates beyond relaxation: no judge, no hull, no DFT; they include Ac, Tl, Hg, Cd and As compounds',
  },
  'user-246': {
    data: '236 matched of 246 uploaded (166 / 36 / 34)',
    route: 'screening',
    checked: 'The property model on 34 test structures; a CGCNN judge trained on the same data (0.59 eV); two potentials; an ML hull against Materials Project phases',
    notChecked: 'The 13 shortlisted candidates (7 with thallium): no DFT; the judge shares the data\'s blind spots',
  },
  mp20: {
    data: '45,229 Materials Project crystals (27,136 for training)',
    route: 'generation',
    checked: 'A pretrained judge (0.10 eV on 80 test structures); relaxation by two potentials; MP-20 entries (CaO)',
    notChecked: 'No hull and no DFT; 20 of 37 relaxed cells collapsed',
  },
  'jarvis-dp': {
    data: '1,282 double perovskites from JARVIS-DFT (897 for training)',
    route: 'screening, with two generation routes beside it',
    checked: 'DFT values of JARVIS-DFT (1 confirmed, 3 contradicted); a judge (0.82 eV, wider than the window); an ML hull calibrated on 12 known materials; novelty against JARVIS-DFT and the Materials Project',
    notChecked: 'The 7 new compositions: no DFT; the judge reads PBE gaps while the data record OptB88vdW',
  },
};
