import { Link, useParams } from 'react-router';
import { research, type Calibration, type CheckpointInfo, type Study as StudyT, type StudyRoute, type StudyStability } from '@/api/research';
import { useResource } from '@/api/hooks';
import { MarketingHeader, SiteFooter } from '@/components/shell';
import { ErrorNote, Spinner } from '@/components/ui';
import { Funnel, KV, Num, ResponseCurve, VerdictText } from '@/components/research';
import { studies as S } from '@/copy/research';

const BLOCKS = ['S0', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9'];
const BLOCK_NAMES: Record<string, string> = { S0: 'Data gate', S1: 'Encoder', S2: 'Alignment', S3: 'Decoder', S4: 'Labels', S5: 'Search', S6: 'End to end', S7: 'Validation', S8: 'Judges', S9: 'Readiness' };
const str = (v: unknown) => (v === null || v === undefined ? '—' : typeof v === 'number' ? (Number.isInteger(v) ? String(v) : v.toFixed(2)) : Array.isArray(v) ? v.join(', ') : String(v));

function CalibrationPanel({ cal, study }: { cal: Calibration; study: StudyT }) {
  const bands = cal.per_target.filter((p) => p.delivered_mean !== null).map((p) => ({ requested: p.requested, mean: p.delivered_mean as number, sd: p.delivered_sd }));
  const points = (study.accepted ?? []).map((a) => ({ requested: a.requested, delivered: a.judge_gap, accepted: true, label: a.formula }));
  return (
    <section className="section" id="calibration">
      <h2>Calibration: requested in, delivered out</h2>
      <div className="stat-tiles">
        <div className="card"><div className="k">Accuracy</div><div className="v"><Num v={cal.accuracy.mae_relaxed_cells} /> eV</div><div className="n">MAE against the request on relaxed cells; 95% CI {cal.accuracy.mae_relaxed_ci95[0].toFixed(2)}–{cal.accuracy.mae_relaxed_ci95[1].toFixed(2)}; {cal.accuracy.mae_generated_cells.toFixed(2)} eV before relaxation</div></div>
        <div className="card"><div className="k">Response</div><div className="v">{cal.linearity.intercept.toFixed(2)} + {cal.linearity.slope.toFixed(2)}·x</div><div className="n">ideal {cal.linearity.ideal}; Spearman {cal.linearity.spearman.toFixed(2)}</div></div>
        <div className="card"><div className="k">Precision</div><div className="v">± <Num v={cal.precision.within_target_sd_median} /> eV</div><div className="n">within-request standard deviation, median</div></div>
        <div className="card"><div className="k">Range served</div><div className="v">{cal.range.served[0]}–{cal.range.served[cal.range.served.length - 1]} eV</div><div className="n">{cal.range.served.length} of {cal.range.requested.length} requested values returned an accepted structure</div></div>
        <div className="card"><div className="k">Resolution</div><div className="v">≈ 1 eV</div><div className="n">adjacent requests separate at {cal.resolution.filter((r) => r.separable).map((r) => `${r.pair[0]}→${r.pair[1]}`).join(', ') || 'no pair'}</div></div>
        {cal.novelty && <div className="card"><div className="k">Novelty</div><div className="v">AMD {cal.novelty.amd_median.toFixed(2)}</div><div className="n">median distance to the nearest training structure (new above 0.3); {Math.round(100 * cal.novelty.novel_share)}% new</div></div>}
      </div>
      <div className="cards-2" style={{ marginTop: 20, alignItems: 'start' }}>
        <div className="card"><ResponseCurve points={points} bands={bands} fit={{ slope: cal.linearity.slope, intercept: cal.linearity.intercept }} /></div>
        <div className="card">
          <h3>Funnel</h3>
          <Funnel stages={[['generated', cal.funnel.generated], ['both judges, generated cell', cal.funnel.both_judges], ['relaxed by two potentials', cal.funnel.relaxed], ['both judges, relaxed cell', cal.funnel.final]]} />
          <p className="small muted" style={{ marginTop: 12 }}>{cal.stability_note}.</p>
        </div>
      </div>
      <div className="table-wrap" style={{ marginTop: 20 }}>
        <table className="table">
          <caption className="sr-only">Per request</caption>
          <thead><tr><th scope="col">requested</th><th scope="col">generated</th><th scope="col">both judges</th><th scope="col">relaxed</th><th scope="col">accepted</th><th scope="col">delivered mean</th><th scope="col">sd</th><th scope="col">bias</th><th scope="col">relaxation drop</th><th scope="col">space group kept</th></tr></thead>
          <tbody>
            {cal.per_target.map((p) => (
              <tr key={p.requested}>
                <td className="num">{p.requested.toFixed(1)}</td><td className="num">{p.generated}</td><td className="num">{p.both_judges}</td><td className="num">{p.relaxed}</td><td className="num">{p.final}</td>
                <td className="num"><Num v={p.delivered_mean} /></td><td className="num"><Num v={p.delivered_sd} /></td><td className="num">{p.bias === null ? '—' : (p.bias >= 0 ? '+' : '') + p.bias.toFixed(2)}</td>
                <td className="num"><Num v={p.drop_median} /></td><td className="num">{p.spacegroup_kept === null ? '—' : `${Math.round(100 * p.spacegroup_kept)}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="small muted" style={{ marginTop: 8 }}>Delivered = the independent judge on the relaxed cell; drop = energy lowered by relaxation, eV/atom (sound structures: under 0.1). Counts above 1 eV are small, so quote the pooled statistics.</p>
      </div>
    </section>
  );
}

/** A study with several routes to its candidates: the same check for each, one funnel each. */
function RoutesPanel({ routes, stability }: { routes: StudyRoute[]; stability?: StudyStability }) {
  return (
    <section className="section" id="routes">
      <h2>Routes: one check for every route</h2>
      <p className="muted">Each route ends with the same check: the label read from each cell, the qualified judge, both readings in the window, relaxation by two potentials, both readings again on the relaxed cell, the energy above the hull, novelty against the data and the reference set.</p>
      <div className="cards-2" style={{ alignItems: 'start' }}>
        {routes.map((r) => (
          <div className="card" key={r.id}>
            <h3>{r.title}</h3>
            <p className="small muted">{r.how}</p>
            <Funnel stages={r.funnel} unit="structures" />
            <p className="small" style={{ marginTop: 10 }}>
              {Object.keys(r.classes).length ? Object.entries(r.classes).map(([k, v]) => `${v} ${k}`).join('; ') : 'nothing accepted'}.
              {r.stable_share !== null && <> Within 0.1 eV/atom of the hull: {Math.round(100 * r.stable_share)}% of the relaxed cells{r.not_assessed ? ` (${r.not_assessed} not assessed)` : ''}.</>}
            </p>
            {r.collapsed.length > 0 && <p className="small faint">Collapsed on relaxation and set aside: {r.collapsed.map((c) => `${c.formula} (${c.contact_ratio.toFixed(2)})`).join(', ')}.</p>}
          </div>
        ))}
      </div>
      {stability && (
        <div className="stat-tiles" style={{ marginTop: 20 }}>
          <div className="card"><div className="k">Stability</div><div className="v">{stability.potential}</div><div className="n">one potential for every phase; competing phases from {stability.reference}</div></div>
          <div className="card"><div className="k">Checked on</div><div className="v">{stability.n} known</div><div className="n">materials of the data with a DFT hull value</div></div>
          <div className="card"><div className="k">Median error</div><div className="v"><Num v={stability.median_abs_error_eV} d={3} /> eV/atom</div><div className="n">mean <Num v={stability.mae_eV} d={3} />{stability.outliers.length ? <>; <Num v={stability.mae_without_outliers} d={3} /> without {stability.outliers.join(', ')}</> : null}</div></div>
          <div className="card"><div className="k">Agreement</div><div className="v">{Math.round(100 * (stability.agreement_without_outliers ?? stability.agreement))}%</div><div className="n">on &ldquo;within 0.1 eV/atom of the hull&rdquo;{stability.outliers.length ? `, without the implausible reference value (${Math.round(100 * stability.agreement)}% with it)` : ''}</div></div>
        </div>
      )}
    </section>
  );
}

export default function Study() {
  const { id = 'mp20' } = useParams();
  const { data: s, error, loading, reload } = useResource<StudyT>(`studies/${id}`, (sig) => research.study(id, sig));
  const ck = useResource<{ checkpoints: CheckpointInfo[] }>('checkpoints', (sig) => research.checkpoints(sig));
  const mine = ck.data?.checkpoints.filter((c) => s?.checkpoints.includes(c.id)) ?? [];
  const tf = (s?.target_following ?? {}) as Record<string, unknown>;
  return (
    <>
      <MarketingHeader />
      <main className="wrap-narrow page" id="main">
        {error && <ErrorNote error={error} retry={reload} />}
        {loading && <Spinner label="Loading the study" />}
        {s && (
          <>
            <div className="page-head study-head">
              <div>
                <div className="micro"><Link to="/studies">Studies</Link> · {s.dataset.name} · {s.mode}</div>
                <h1>{s.title}</h1>
                <p>{s.headline}</p>
              </div>
            </div>

            <div className="cards-2" style={{ alignItems: 'start' }}>
              <div className="card">
                <h3>The dataset</h3>
                <KV rows={Object.entries(s.dataset).filter(([k]) => k !== 'name').map(([k, v]) => [k.replace(/_/g, ' '), str(v)])} />
              </div>
              <div className="card">
                <h3>Block verdicts</h3>
                <div className="table-wrap">
                  <table className="table">
                    <caption className="sr-only">Block verdicts</caption>
                    <thead><tr><th scope="col">block</th><th scope="col">verdict</th><th scope="col">the deciding number</th></tr></thead>
                    <tbody>
                      {BLOCKS.filter((b) => s.verdicts[b]).map((b) => (
                        <tr key={b}><td className="mono"><Link to={`/pipeline/${b}`}>{b}</Link> <span className="small muted">{BLOCK_NAMES[b]}</span></td><td><VerdictText grade={s.verdicts[b].grade} /></td><td className="small">{s.verdicts[b].note}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="small muted" style={{ marginTop: 8 }}>{S.verdictNote}</p>
              </div>
            </div>

            <section className="section" id="target-following">
              <h2>Target following</h2>
              <div className="card">
                <KV rows={Object.entries(tf).filter(([k]) => !['funnel', 'screen_funnel'].includes(k)).map(([k, v]) => [k.replace(/_/g, ' '), typeof v === 'object' && v !== null && !Array.isArray(v) ? JSON.stringify(v) : str(v)])} />
                {Array.isArray(tf.funnel) && (
                  <div style={{ marginTop: 16, maxWidth: 560 }}><Funnel stages={(tf.funnel as Array<[string, number]>)} unit="candidates" /></div>
                )}
              </div>
              {s.rediscoveries && s.rediscoveries.length > 0 && (
                <div className="table-wrap" style={{ marginTop: 16 }}>
                  <h3>Known compounds returned unprompted</h3>
                  <table className="table">
                    <thead><tr><th scope="col">formula</th><th scope="col">label</th><th scope="col">judge (GLLB-SC)</th><th scope="col">E above hull</th><th scope="col">literature</th></tr></thead>
                    <tbody>{s.rediscoveries.map((r) => <tr key={r.formula}><td><b>{r.formula}</b></td><td className="num"><Num v={r.label_gap} /></td><td className="num"><Num v={r.judge_gap} /></td><td className="num"><Num v={r.e_hull} d={3} /></td><td className="small">{r.literature}</td></tr>)}</tbody>
                  </table>
                </div>
              )}
              {s.ablation && (
                <details style={{ marginTop: 16 }}>
                  <summary>Ablation table ({s.ablation.rows.length} configurations)</summary>
                  <p className="small muted">{s.ablation.note}</p>
                  <div className="table-wrap">
                    <table className="table">
                      <thead><tr>{s.ablation.columns.map((c) => <th scope="col" key={c} className="small-head">{c}</th>)}</tr></thead>
                      <tbody>{s.ablation.rows.map((r, i) => <tr key={i}>{s.ablation!.columns.map((c) => <td key={c} className="small num">{str(r[c])}</td>)}</tr>)}</tbody>
                    </table>
                  </div>
                </details>
              )}
              {s.checks && (
                <details style={{ marginTop: 16 }}>
                  <summary>Checkup ({s.checks.length} checks)</summary>
                  <div className="table-wrap"><table className="table"><thead><tr><th scope="col">stage</th><th scope="col">check</th><th scope="col">status</th><th scope="col">detail</th></tr></thead>
                    <tbody>{s.checks.map((c, i) => <tr key={i}><td className="small">{c.stage}</td><td className="small">{c.check}</td><td><VerdictText grade={c.status} /></td><td className="small">{c.detail}</td></tr>)}</tbody></table></div>
                </details>
              )}
              {s.lessons && <div className="note" style={{ marginTop: 16 }}><b>What this study taught the pipeline.</b><ul className="small" style={{ margin: '6px 0 0 18px' }}>{s.lessons.map((l) => <li key={l}>{l}</li>)}</ul></div>}
            </section>

            {s.calibration && <CalibrationPanel cal={s.calibration} study={s} />}

            {s.routes && s.routes.length > 0 && <RoutesPanel routes={s.routes} stability={s.stability} />}

            {s.accepted && s.accepted.length > 0 && (
              <section className="section" id="accepted">
                <h2>Accepted structures</h2>
                <p className="muted">Both judges within {s.calibration?.window_eV ?? s.window_eV} eV of the request on the relaxed cell; a judged metal never satisfies a non-zero request. Classes: {Object.entries(s.accepted_classes ?? {}).map(([k, v]) => `${v} ${k}`).join('; ')}.</p>
                <div className="table-wrap">
                  <table className="table">
                    <thead><tr><th scope="col">requested</th><th scope="col">formula</th>{s.routes && <th scope="col">route</th>}<th scope="col">label from the structure</th><th scope="col">judge</th>{s.stability && <th scope="col">above the hull (eV/atom)</th>}<th scope="col">AMD</th><th scope="col">class</th><th scope="col">recorded gaps</th><th scope="col">charge balance</th><th scope="col">relaxation drop</th><th scope="col">space group</th><th scope="col">cell</th></tr></thead>
                    <tbody>
                      {s.accepted.map((a) => (
                        <tr key={a.file}>
                          <td className="num">{a.requested.toFixed(1)}</td><td><b>{a.formula}</b>{a.flag && <div className="small faint">{a.flag}</div>}</td>
                          {s.routes && <td className="small">{a.route}</td>}
                          <td className="num"><Num v={a.label_structure_gap} /></td><td className="num"><Num v={a.judge_gap} /></td>
                          {s.stability && <td className="num"><Num v={a.e_hull} d={3} />{a.e_hull_note ? ' †' : ''}</td>}
                          <td className="num"><Num v={a.amd_nearest} d={3} /></td>
                          <td className="small">{a.class}</td><td className="small num">{a.recorded_gaps.length ? a.recorded_gaps.map((g) => g.toFixed(2)).join(', ') : '—'}</td>
                          <td className="small">{a.charge_balanced === null ? '—' : a.charge_balanced ? 'yes' : 'no'}</td><td className="num"><Num v={a.relaxation_drop_eV_atom} /></td>
                          <td className="small mono">{a.spacegroup_designed}→{a.spacegroup_relaxed}</td>
                          <td><a className="small" href={research.studyFileUrl(s.id, a.file)} download>CIF</a></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {s.accepted.some((a) => a.e_hull_note) && <ul className="small muted" style={{ marginTop: 8 }}>{s.accepted.filter((a) => a.e_hull_note).map((a) => <li key={a.file}>† {a.formula}: {a.e_hull_note}</li>)}</ul>}
                {s.cross_checks && s.cross_checks.length > 0 && <div className="note" style={{ marginTop: 12 }}><b>Checked against other sources.</b><ul className="small" style={{ margin: '6px 0 0 18px' }}>{s.cross_checks.map((c) => <li key={c}>{c}</li>)}</ul></div>}
              </section>
            )}

            <section className="section" id="checkpoints">
              <h2>Checkpoints and reproduction</h2>
              {mine.length > 0 ? (
                <div className="table-wrap"><table className="table"><thead><tr><th scope="col">id</th><th scope="col">role</th><th scope="col">what it is</th><th scope="col">download</th></tr></thead>
                  <tbody>{mine.map((c) => <tr key={c.id}><td className="mono">{c.id}</td><td className="small">{c.role}</td><td className="small">{c.description}</td><td className="small">{c.download_url ? <a href={c.download_url} download={c.file}>from this server</a> : null}{c.urls?.map((u) => <span key={u}> · <a href={u} target="_blank" rel="noopener">{u.includes('github') ? 'release asset' : 'mirror'}</a></span>)}</td></tr>)}</tbody></table></div>
              ) : <p className="muted small">No checkpoint of this dataset is published{s.id === 'user-246' ? ': the data belong to their owner' : s.id === 'jarvis-dp' ? ': the two models were trained by the independent user, and the Method page\'s commands train the same ones' : ''}.</p>}
              <h3 style={{ marginTop: 20 }}>Reproduce</h3>
              <div className="stack" style={{ gap: 8 }}>{s.reproduce.map((r) => <div key={r.step}><div className="small muted">{r.step}</div><div className="cmd">{r.command}</div></div>)}</div>
              {Object.keys(s.files).length > 0 && <><h3 style={{ marginTop: 20 }}>Files</h3><ul className="small">{Object.entries(s.files).filter(([n]) => !n.includes('/')).map(([n, f]) => <li key={n}><a href={research.studyFileUrl(s.id, n)} download>{n}</a> <span className="faint">({(f.bytes / 1024).toFixed(0)} KB)</span></li>)}</ul></>}
            </section>

            <section className="section" id="limits">
              <h2>Limits of this study</h2>
              <ul>{s.limits.map((l) => <li key={l}>{l}</li>)}</ul>
              <p className="small faint">Sources: {s.sources.join('; ')}</p>
            </section>
          </>
        )}
      </main>
      <SiteFooter />
    </>
  );
}
