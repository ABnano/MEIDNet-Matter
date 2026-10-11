// Scope and limits: one statement of what the pipeline measured, what it did not, and what a dataset needs. The study
// pages show their own row of STUDY_EVIDENCE, so both places say the same thing. Every number comes from the study files
// under examples/research/studies (limits.test.ts checks the ones it can).

export const limits = {
  h1: 'Scope and limits',
  lead: 'What the pipeline has measured, what it has not, and what your data needs. Every number comes from the five case studies on this site. No result here is a new DFT calculation or an experiment: a new structure is a proposal until DFT confirms it.',
  evidenceTitle: 'How to read a result',
  evidenceLead: 'Each number on this site carries one of four kinds of evidence.',
  evidence: [
    ['DFT value', 'Computed with density functional theory and recorded in the dataset or a public database (Perov-5, MP-20, JARVIS-DFT), at that database\'s level of theory. The strongest evidence on this site.', 'Ba₂MgWO₆ returned for a 3 eV request, recorded at 2.82 eV'],
    ['Model reading', 'A machine-learning estimate read from the structure, by the generator\'s own model or by a second model of a different lineage (the judge). Each has an error measured on its dataset\'s test split.', 'Judge error 0.10 eV on MP-20, 0.82 eV on the double perovskites'],
    ['ML hull', 'Energy above a convex hull computed with machine-learning potentials against a reference set of known crystals. A screen, calibrated on few known materials.', '12 known double perovskites: rank correlation 0.47 (0.77 without one outlier)'],
    ['Proposal', 'A candidate that passed the model readings and the checks but has no DFT value: a reason to compute, not a result.', 'Every new composition on this site'],
  ] as Array<[string, string, string]>,
  scales: 'Two scales appear. Readiness and Train call a model\'s error good below 0.25 of the property\'s spread and fair below 0.5; the pipeline\'s S1 band passes up to 0.7. The first describes the precision of one model, the second is a pass line.',
  dataTitle: 'What your data needs',
  dataLead: 'The number of rows matters less than what the rows contain. Each line gives what decided the outcome, the cases that worked and did not, and what to expect below the line.',
  dataHead: ['to do this', 'what decides it', 'worked', 'did not work', 'below it'],
  data: [
    ['Predict a property from structure', 'A well-posed property: continuous, few zeros, few materials sharing one property profile', '166 training structures (the upload: r 0.97, 0.65 eV on a 3.62 eV spread)', '897 (the double perovskites, 35% zero gaps: metals told from non-metals for 82% of test structures, below the 85% line)', 'Band-gap errors near 0.6–0.7 eV whatever the size; a property that is mostly zero leaves few rows to learn from (Perov-5: 441 non-zero gaps among 11,356 training rows)'],
    ['Screen a structural family', 'The data fit one family; the property model passes S1; a judge whose error is smaller than the target window', '166, 634 and 897 training structures', 'None so far', 'A shortlist in the family\'s structure type, with misreads near the metal/non-metal boundary'],
    ['Generate without a family', 'Hundreds of distinct compositions per element, and many structure types', 'MP-20: 817 per element, 6,282 structure types', 'The double perovskites (48.5 per element), MP perovskites (12), the upload (11.3): their decoders rebuilt 4.2%, 1.4% and 0% of the test compositions', 'The data gate (S0) sends the run to screening'],
    ['Trust a second model as judge', 'An error measured on the dataset\'s own test split, at its level of theory, smaller than the window', 'MP-20: 0.10 eV', 'Perov-5: MEGNet 1.71 eV (Perov-5 gaps are GLLB-SC)', 'Agreement with the judge adds little; DFT decides'],
    ['Estimate stability', 'A reference set of known crystals that covers the chemistry, and an ML potential', 'Perov-5 and the upload (Materials Project reference); the double perovskites (JARVIS-DFT reference)', 'Cs₂InFeBr₆: the JARVIS-DFT reference holds no cesium halide, so it is not assessed', 'A screen worth a DFT check'],
  ] as Array<[string, string, string, string, string]>,
  smallTitle: 'A few hundred structures train a property model, not a generator',
  small: 'The upload of 246 entries (236 matched; 166 for training, 36 for validation, 34 for testing) gave the best property model on this site and a decoder that rebuilt none of its test compositions, as the data gate had predicted before training. Its candidates came from screening known structure types, checked by a judge trained on the same data. Its numbers rest on 34 test structures: the 0.65 eV error could be about 0.48–0.81 eV. The test split is 15% of the rows; as a rule of thumb, about 80 test structures (about 530 rows) are needed before a verdict near a band edge means much.',
  thresholdNote: 'The generation threshold is provisional. The rule of about 200 compositions per element comes from a curve on Perov-5 subsets whose anchor, 218, is the full Perov-5 training split counted as rows per cation element, while the gate counts distinct compositions per element (549 on the same split). Every study\'s route stands, since each lies far on one side, but the threshold is being re-measured in the gate\'s own units.',
  ownData: 'Your own data runs on your computer; nothing is uploaded on this site.',
  studiesTitle: 'What each study checked',
  studiesLead: 'Against what each result was checked, and what remains unchecked. Each study page carries its own row and its limits.',
  studiesHead: ['study', 'data', 'route', 'checked against', 'not checked'],
  structuresTitle: 'Which crystal structures',
  structures: [
    ['Within a family', 'The Perov-5 demo, screening and family generation place a composition on the family\'s cell. Every family shipped is cubic: Pm-3m ABX₃ and its mixed-anion variants, Fm-3m A₂BB′X₆. Relaxation may lower the symmetry.'],
    ['Without a family', 'Generate (MP-20) builds each cell in a space group its decoder predicts. Valid cells covered 55 space groups, and the accepted structures came out monoclinic, tetragonal and orthorhombic before relaxation.'],
    ['Your own family', 'A family file may use a general cell (a, b, c, α, β, γ), scaled from one edge with its shape fixed. No non-cubic family ships or has been tested, and its rules must be written for it: the tolerance and octahedral factors are perovskite rules.'],
  ] as Array<[string, string]>,
  strengthsTitle: 'What the measurements support',
  strengths: [
    'The data gate (S0) chose a route for each of the five datasets before any training; on the three it sent to screening, the trained decoders then rebuilt 0–4.2% of the test compositions, as it predicted.',
    'A property model from 166 structures: band gap with r 0.97 (0.65 eV error) on a well-posed property.',
    'On Perov-5, target following against DFT values among compositions already in the grid: ρ 0.90–0.98, 57–83% of returns on target against 7.7% for random proposals.',
    'Family-free generation on MP-20: 4 of 175 cells accepted after relaxation by two independent readings; CaO returned in its recorded structure at 3.12 eV.',
    'An independent user ran the pipeline from the published packages on public data (the double perovskites): 7 new charge-balanced compositions await DFT, one known compound came back at its recorded gap, and the four failures are shown.',
    'Every step reports what it rejected: on MP-20, 20 of 37 relaxed cells collapsed and were set aside.',
  ],
  openTitle: 'Known open issues',
  openLead: 'Measured weaknesses of the pipeline itself. Each will be fixed with a measurement and noted in the changelog.',
  open: [
    'The generation threshold is being re-measured in the gate\'s own units (see above).',
    'A judge is qualified on up to 80 test structures, and the best of its heads is kept on those same structures, so its reported error is optimistic.',
    'Verdicts are shown without their sample size or an interval; several lie within sampling error of their band edge (the double perovskites: metal accuracy 0.82 against 0.85, judge 0.50 against 0.5 of the spread).',
    'Retrieval is graded against chance, and chance depends on the size of the test split, which caps small datasets.',
    'Metal/non-metal accuracy is graded even for data without metals, where it is uninformative (the upload: 1.0).',
    'The tolerance and octahedral factors use ionic radii averaged over every oxidation state, which shrinks every anion except oxygen: with the shipped bounds, CsPbBr₃ and CsPbCl₃ fail the octahedral factor.',
    'Two counts of the upload come from different stages of its run and are not reconciled on its page: 58 cells compared by two potentials against 42 relaxed in its funnel, 13 shortlisted against 10 within 1 eV.',
    'The checkup table of the MP perovskites was graded with earlier bands.',
  ],
  siteTitle: 'What this site does not do',
  site: [
    'No upload: your own data runs on your computer with the meidnet-matter package.',
    'No relaxation and no DFT on the server: Generate returns unrelaxed cells and the command to relax them locally.',
    'Generate is shared: one job per session, up to three targets and ten structures each, eight minutes; results are removed after an hour.',
    'Train fits a model to 1,500 Perov-5 materials for 10 to 50 epochs: it shows how the method learns and does not drive generation.',
  ],
  engine: 'This site runs a development snapshot of the engine (meidnet 2.4.0.dev4). The released package documented on MEIDNet Prism (2.3.1) has its own scope and limits:',
  engineLink: 'Prism: scope, limitations and roadmap ↗',
};

/** One row per study: the data, the route the data gate chose, what results were checked against, what was not. */
export const STUDY_EVIDENCE: Record<string, { data: string; route: string; checked: string; notChecked: string }> = {
  perov5: {
    data: '18,928 cubic ABX₃ perovskites (DFT; GLLB-SC gaps)',
    route: 'candidate sets',
    checked: 'Perov-5\'s own DFT values of the returned compositions; a CGCNN judge (0.59 eV on non-zero gaps); an ML hull against Materials Project phases; literature',
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
