import { useEffect, useMemo, useState } from 'react';
import type { Accepted } from '@/api/research';
import { CellViewer } from '@/components/structure/CellViewer';
import { cellOfAccepted } from './DiscoveryStrip';

/** Six steps, each with a plain sentence for a visitor from another field and a precise one for a researcher. */
const STEPS: Array<{ title: string; plain: (a: Accepted) => string; precise: string }> = [
  { title: 'Ask', plain: (a) => `You name the property you want: here a band gap of ${a.requested.toFixed(1)} eV, the energy electrons need before they can move freely.`,
    precise: 'The property vector is encoded to a point on the shared unit sphere. No latent refinement follows: measured on MP-20, that step made the model repeat the request while drifting towards metals.' },
  { title: 'One map for structures and properties', plain: () => 'Crystals and their properties were learned into one shared map. Points that lie close are materials that behave alike.',
    precise: 'A structure encoder and a property encoder trained with a contrastive objective on a unit sphere; the request becomes a point on it.' },
  { title: 'Propose a crystal', plain: () => 'Near your point, the decoder proposes a crystal: a space group and a few distinct atom positions. Symmetry fills in the rest of the cell.',
    precise: 'Symmetry decoder: space group, up to 16 orbits, a lattice projected to the group; one anion required, radioactive elements excluded, cells capped at the encoder\'s size.' },
  { title: 'Read it back', plain: (a) => `The proposed crystal is read again by the model. Does it really have the gap you asked for? Here it reads ${a.label_structure_gap.toFixed(2)} eV.`,
    precise: 'The label is read from the returned structure, never from the search point. A label read from the search point reports the request back by construction.' },
  { title: 'Ask a second model', plain: (a) => `An independent model of a different lineage reads the same crystal: ${a.judge_gap.toFixed(2)} eV. Both readings must sit inside your window.`,
    precise: 'MEGNet band-gap model, qualified on the dataset\'s own test split before judging anything (MAE 0.10 eV, Spearman 0.82 on MP-20).' },
  { title: 'Relax, then check again', plain: () => 'Atoms are let go to their resting positions, and both readings are repeated on the relaxed crystal. That is the structure you download, with all its evidence.',
    precise: 'TensorNet and CHGNet relaxation, both judges re-run on the relaxed cell. No hull energy is computed, so stability is not claimed.' },
];

const DOTS = Array.from({ length: 26 }, (_, i) => { const t = i * 2.399; const r = 0.3 + 0.62 * ((i * 7919) % 100) / 100; return [60 + 46 * r * Math.cos(t), 60 + 46 * r * Math.sin(t)] as const; });

/** The shared map, drawn once: training points, the request, and the proposed crystal's point when it exists. */
function MapSketch({ step, inWindow }: { step: number; inWindow: boolean }) {
  return (
    <svg viewBox="0 0 120 120" width="100%" role="img" aria-label="The shared map of structures and properties">
      <circle cx={60} cy={60} r={52} fill="var(--tint)" stroke="var(--line)" />
      {step >= 1 && DOTS.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={2.2} fill="var(--seq-4)" opacity={0.7} />)}
      {step >= 0 && <circle cx={74} cy={44} r={step === 0 ? 5 : 4} fill="var(--c-targets)" stroke="var(--card)" strokeWidth={1.5}><title>your request</title></circle>}
      {step >= 2 && <circle cx={81} cy={51} r={4} fill={step >= 4 ? (inWindow ? 'var(--c-candidates)' : 'var(--warn)') : 'var(--card)'} stroke="var(--c-candidates)" strokeWidth={1.8}><title>the proposed crystal</title></circle>}
      {step >= 3 && <line x1={81} y1={51} x2={75.5} y2={45.5} stroke="var(--ink)" strokeWidth={1} strokeDasharray="2 2" />}
      <text x={60} y={114} textAnchor="middle" fontSize={7} fill="var(--muted)">{step < 2 ? 'shared map · pink = your request' : 'purple = the proposed crystal'}</text>
    </svg>
  );
}

/** An animated walkthrough of how a request becomes a structure, on a real accepted structure of the MP-20 study.
 *  Plays through six steps, pausing on hover; the viewer can also step by hand. Reduced motion disables autoplay. */
export function Explainer({ example }: { example: Accepted }) {
  const reduced = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(!reduced);
  const [hover, setHover] = useState(false);
  const cell = useMemo(() => cellOfAccepted(example), [example]);
  useEffect(() => {
    if (!playing || hover) return;
    const id = window.setInterval(() => setStep((s) => (s + 1) % STEPS.length), 5200);
    return () => window.clearInterval(id);
  }, [playing, hover]);
  const s = STEPS[step];
  const inWindow = Math.abs(example.label_structure_gap - example.requested) <= 0.5 && Math.abs(example.judge_gap - example.requested) <= 0.5;
  return (
    <div className="explainer card" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} aria-live="polite">
      <div className="explainer-stage">
        <div className="explainer-map"><MapSketch step={step} inWindow={inWindow} /></div>
        <div className={`explainer-cell step-${step}`}>
          {cell && step >= 2 && <CellViewer structure={cell} size={190} title={example.formula} autoSpin={!reduced} supercell={step >= 5 ? 1 : 1} labels={step >= 3} />}
          {step < 2 && <div className="explainer-ask"><div className="micro">band gap</div><div className="explainer-value">{example.requested.toFixed(1)} eV</div><div className="small muted">± 0.5 eV window</div></div>}
          {step >= 3 && (
            <div className="explainer-readings small">
              <div><span className="muted">read from the structure</span> <b className="num">{example.label_structure_gap.toFixed(2)}</b> eV</div>
              {step >= 4 && <div><span className="muted">independent model</span> <b className="num">{example.judge_gap.toFixed(2)}</b> eV</div>}
              {step >= 5 && <div><b>{inWindow ? 'accepted' : 'not accepted'}</b> · both readings within 0.5 eV of {example.requested.toFixed(1)} eV · relaxed cell</div>}
            </div>
          )}
        </div>
      </div>
      <div className="explainer-caption">
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8 }}>
          <h3 style={{ margin: 0 }}><span className="mono" style={{ color: 'var(--p1)' }}>{step + 1}/{STEPS.length}</span> · {s.title}</h3>
          <div className="row" style={{ gap: 4 }}>
            <button type="button" className="btn btn-sm" aria-label="Previous step" onClick={() => { setPlaying(false); setStep((step + STEPS.length - 1) % STEPS.length); }}>←</button>
            <button type="button" className="btn btn-sm" aria-pressed={playing} onClick={() => setPlaying((p) => !p)}>{playing ? 'Pause' : 'Play'}</button>
            <button type="button" className="btn btn-sm" aria-label="Next step" onClick={() => { setPlaying(false); setStep((step + 1) % STEPS.length); }}>→</button>
          </div>
        </div>
        <p style={{ margin: '6px 0 4px' }}>{s.plain(example)}</p>
        <p className="small muted" style={{ margin: 0 }}>{s.precise}</p>
        <div className="explainer-dots" role="tablist" aria-label="Steps">{STEPS.map((x, i) => <button key={x.title} type="button" role="tab" aria-selected={i === step} aria-label={`Step ${i + 1}: ${x.title}`} className={i === step ? 'on' : ''} onClick={() => { setPlaying(false); setStep(i); }} />)}</div>
      </div>
    </div>
  );
}
