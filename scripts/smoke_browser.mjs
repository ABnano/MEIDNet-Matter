// End-to-end smoke test of MEIDNet Matter in a headless browser, through the Chrome DevTools Protocol (no extra
// dependency): the landing page, the demo goal, a changed band-gap target, lead excluded, the readiness report,
// a real search, the candidates, one candidate's detail with its domain status, the CIF and the CSV export.
//
//   node scripts/smoke_browser.mjs http://127.0.0.1:8000 build/smoke
//
// Exit code 1 on any failed step, page error or failed request. Writes <out>/landing.png, readiness.png, candidates.png.
//
// On a network whose DNS blocks *.hf.space, pass the address from a public resolver to the browser only:
//   SMOKE_HOST_RESOLVER_RULES="MAP babu09-meidnet-matter.hf.space 54.72.207.44" node scripts/smoke_browser.mjs https://babu09-meidnet-matter.hf.space
// (TLS still verifies the real certificate.)
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = (process.argv[2] || 'http://127.0.0.1:8000').replace(/\/$/, '');
const OUT = process.argv[3] || 'build/smoke';
fs.mkdirSync(OUT, { recursive: true });
const CANDIDATES = [process.env.BROWSER, '/usr/bin/google-chrome', '/usr/bin/chromium-browser', '/usr/bin/chromium',
  'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'].filter(Boolean);
const BIN = CANDIDATES.find((p) => fs.existsSync(p));
if (!BIN) { console.error('no Chrome or Edge found; set BROWSER=<path>'); process.exit(2); }
const PORT = 9300 + Math.floor(Math.random() * 500);
const prof = fs.mkdtempSync(path.join(os.tmpdir(), 'matter-smoke-'));
const resolverRules = process.env.SMOKE_HOST_RESOLVER_RULES ? [`--host-resolver-rules=${process.env.SMOKE_HOST_RESOLVER_RULES}`] : [];
const browser = spawn(BIN, ['--headless=new', `--remote-debugging-port=${PORT}`, '--no-sandbox', '--disable-gpu', '--no-first-run', '--disable-extensions',
  `--user-data-dir=${prof}`, '--window-size=1366,900', ...resolverRules, 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const t0 = Date.now();
const errors = [];
const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}  ${String(detail).slice(0, 200)}`); };

let ws, id = 0; const pending = new Map();
async function connect() {
  let target = null;
  for (let i = 0; i < 100 && !target; i++) { try { target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: 'PUT' })).json(); } catch { await sleep(200); } }
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener('open', r, { once: true }));
  ws.addEventListener('message', (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); return; }
    const p = m.params || {};
    if (m.method === 'Runtime.exceptionThrown') errors.push('exception: ' + (p.exceptionDetails.exception?.description || p.exceptionDetails.text).slice(0, 300));
    if (m.method === 'Runtime.consoleAPICalled' && p.type === 'error') errors.push('console.error: ' + p.args.map((a) => a.value ?? a.description).join(' ').slice(0, 300));
    if (m.method === 'Network.responseReceived' && p.response.status >= 400 && !/\/api\/runs\/.*\/(manifest|export)/.test(p.response.url) && !/run-smoke-gone/.test(p.response.url)) errors.push(`${p.response.status} ${p.response.url}`);
  });
  for (const d of ['Runtime', 'Page', 'Network', 'Log']) await send(`${d}.enable`);
}
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
async function ev(expr) {
  const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true, userGesture: true });
  if (r.result?.exceptionDetails) throw new Error(r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text);
  return r.result?.result?.value;
}
async function waitFor(expr, ms = 30000, every = 300) { const s = Date.now(); while (Date.now() - s < ms) { try { const v = await ev(expr); if (v) return v; } catch { /* retry */ } await sleep(every); } return null; }
async function shot(name) { const r = await send('Page.captureScreenshot', { format: 'png' }); fs.writeFileSync(path.join(OUT, name), Buffer.from(r.result.data, 'base64')); }
async function goto(url) { await send('Page.navigate', { url }); await waitFor(`document.readyState === 'complete'`, 30000); await sleep(400); }
const click = (sel) => ev(`(() => { const el = document.querySelector(${JSON.stringify(sel)}); if (!el) return false; el.scrollIntoView({block: 'center'}); el.click(); return true; })()`);
// React controlled inputs: set through the native setter so React sees the change
const type = (sel, value) => ev(`(() => { const el = document.querySelector(${JSON.stringify(sel)}); if (!el) return false;
  const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; set.call(el, ${JSON.stringify(String(value))});
  el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`);
const text = (sel) => ev(`(document.querySelector(${JSON.stringify(sel)}) || {}).textContent || ''`);

try {
  await connect();
  // 0. landing
  await goto(`${BASE}/`);
  check('landing: headline', /Explore materials|From a target property/.test(await text('h1')), await text('h1'));   // 0.10.0 home (0.4.0 kept for older builds)
  await shot('landing.png');
  // 1. the demo goal
  check('landing: demo CTA', await click('[data-testid="cta-demo"]'));
  check('goal: summary rendered', await waitFor(`(document.querySelector('[data-testid="goal-summary"]')||{}).textContent?.includes('Eg')`, 30000), await text('[data-testid="goal-summary"]'));
  // 2. change the band-gap target to 1.5 eV, make sure Pb is excluded
  check('goal: set band gap 1.5', await type('[data-testid="target-dir_gap"]', '1.5'));
  const pb = await ev(`(document.querySelector('[data-testid="el-Pb"]')||{}).getAttribute?.('aria-pressed')`);
  if (pb !== 'true') await click('[data-testid="el-Pb"]');
  check('goal: Pb excluded', await waitFor(`document.querySelector('[data-testid="el-Pb"]').getAttribute('aria-pressed') === 'true'`, 5000));
  check('goal: summary updated', await waitFor(`document.querySelector('[data-testid="goal-summary"]').textContent.includes('1.5') && document.querySelector('[data-testid="goal-summary"]').textContent.includes('Pb-free')`, 10000), await text('[data-testid="goal-summary"]'));
  check('goal: readiness button enabled', await waitFor(`!document.querySelector('[data-testid="check-readiness"]').disabled`, 15000));
  await click('[data-testid="check-readiness"]');
  // 3. readiness
  const verdict = await waitFor(`(document.querySelector('[data-testid="verdict"]')||{}).dataset?.verdict`, 60000);
  check('readiness: verdict shown', !!verdict, verdict);
  check('readiness: six indicators', (await ev(`document.querySelectorAll('[data-testid^="indicator-"]').length`)) === 6);
  check('readiness: ambiguity panel', await ev(`!!document.querySelector('[data-testid="ambiguity"]')`));
  await shot('readiness.png');
  // 4. search
  check('readiness: search button', await click('[data-testid="run-search"]'));
  check('explorer: query bar', await waitFor(`!!document.querySelector('[data-testid="querybar"]')`, 30000));
  const t1 = Date.now();
  const count = await waitFor(`(() => { const h = document.querySelector('[data-testid="results-count"]'); if (!h) return 0; const n = parseInt(h.textContent); return (n > 0 && !h.textContent.includes('so far')) ? n : 0; })()`, 240000, 1000);
  check('explorer: candidates found and search finished', count > 0, `${count} candidates in ${Math.round((Date.now() - t1) / 1000)} s`);
  check('explorer: funnel', await waitFor(`!!document.querySelector('[data-testid="funnel"]')`, 20000));
  // 5. a candidate's detail
  check('explorer: open first candidate', await click('[data-testid="candidate-row"]'));
  check('candidate: detail with domain status', await waitFor(`/Interpolating|Boundary|Extrapolating/.test((document.querySelector('[data-testid="candidate-detail"]')||{}).textContent || '')`, 10000));
  check('candidate: validation ladder with a reached stage', await ev(`/Stage [01] · (Generated|Chemistry checked)/.test((document.querySelector('[data-testid="candidate-detail"]')||{}).textContent || '') && !!document.querySelector('[data-testid="ladder"]')`));
  check('explorer: prioritise control', await ev(`!!document.querySelector('[data-testid="prioritise"]') && document.querySelector('[data-testid="prioritise"]').options.length >= 6`));
  await shot('candidates.png');
  // 6. the CIF and the CSV
  const cifHref = await ev(`(document.querySelector('[data-testid="download-cif"]')||{}).getAttribute?.('href')`);
  const cif = await ev(`fetch(${JSON.stringify(cifHref)}).then(r => r.text().then(t => ({status: r.status, head: t.slice(0, 60)})))`);
  check('candidate: CIF downloads', cif && cif.status === 200 && /data_|^#/.test(cif.head), JSON.stringify(cif));
  const runId = await ev(`location.pathname.split('/runs/')[1].split('/')[0]`);
  const csv = await ev(`fetch('/api/runs/' + ${JSON.stringify(runId)} + '/export/candidates.csv').then(r => r.text().then(t => ({status: r.status, head: t.split('\\n')[0]})))`);
  check('export: CSV carries the domain status', csv && csv.status === 200 && csv.head.includes('domain_dir_gap') && csv.head.includes('flags'), csv && csv.head.slice(0, 120));
  const bundle = await ev(`fetch('/api/runs/' + ${JSON.stringify(runId)} + '/export/bundle.zip').then(r => ({status: r.status, type: r.headers.get('content-type')}))`);
  check('export: bundle', bundle && bundle.status === 200 && /zip/.test(bundle.type), JSON.stringify(bundle));
  const schema = await ev(`fetch('/api/schema/candidate-record').then(r => r.json().then(j => ({status: r.status, id: j.schema, stages: (j.validation_stages||[]).length})))`);
  check('export: candidate-record schema', schema && schema.status === 200 && schema.id === 'meidnet-matter/candidate-record/1' && schema.stages === 6, JSON.stringify(schema));
  const cands = await ev(`fetch('/api/runs/' + ${JSON.stringify(runId)} + '/candidates').then(r => r.json().then(cs => ({n: cs.length, clustered: cs.filter(c => c.cluster).length, schema: cs[0] && cs[0].schema})))`);
  check('candidates: every candidate is a versioned record with a cluster', cands && cands.n > 0 && cands.clustered === cands.n && cands.schema === 'meidnet-matter/candidate-record/1', JSON.stringify(cands));
  // 6b. the staged pipeline: a block's workflow diagram, and its code opening from a box (0.4.2: the viewer must render)
  await goto(`${BASE}/pipeline/S6`);
  check('pipeline: workflow diagram', await waitFor(`document.querySelectorAll('.flow-node').length >= 5`, 20000));
  check('pipeline: code viewer renders', (await click('.flow-node.kind-code')) && await waitFor(`!!document.querySelector('.code-viewer pre code')`, 20000));

  // 6b2. 0.10.0: the three stages. Explore draws the map and opens a material; Train describes the fixed experiment and
  // starts one (10 epochs, under a minute), whose page draws the curves and the result
  await goto(`${BASE}/explore`);
  check('explore: the map and a material', await waitFor(`!!document.querySelector('canvas[aria-label*="points coloured"]')`, 30000));
  await ev(`document.querySelector('input[aria-label="Find a formula"]').focus()`);
  check('explore: a material opens from its formula', (await type('input[aria-label="Find a formula"]', 'SrTiO3')) && await waitFor(`(document.querySelector('[data-testid="material-card"]')||{}).textContent?.includes('SrTiO3') && document.querySelector('[data-testid="material-card"]').textContent.includes('nearest in the learned space')`, 15000));
  await goto(`${BASE}/train`);
  check('train: the experiment is described', await waitFor(`/1,500 Perov-5 materials/.test(document.body.textContent || '')`, 20000));
  const t2 = Date.now();
  check('train: start 10 epochs', (await ev(`(() => { const b = [...document.querySelectorAll('button')].find(x => x.textContent === '10'); if (!b) return false; b.click(); return true; })()`)) && await click('[data-testid="train-start"]'));
  check('train: the job page draws the curves', await waitFor(`!!document.querySelector('figure.linechart svg path')`, 60000));
  check('train: the result arrives', await waitFor(`/of the spread/.test(document.body.textContent || '')`, 240000, 1000), `${Math.round((Date.now() - t2) / 1000)} s`);

  // 6c. 0.9.0: a run the server no longer has explains itself at once, with the way back; every page has its own title
  await goto(`${BASE}/p/perov5-demo/runs/run-smoke-gone`);
  check('lifecycle: a gone run explains itself', await waitFor(`!!document.querySelector('[data-testid="run-gone"]')`, 8000));
  check('shell: the page has its own title', /Candidates · Perov-5 demo/.test(await ev('document.title')), await ev('document.title'));

  // 7. the direct-app link is hidden outside a frame; no page errors
  check('shell: direct-app link hidden outside a frame', !(await ev(`!!document.querySelector('a[title*="outside the Hugging Face frame"]')`)));
  const unexpected = errors.filter((e) => !/favicon|og\.png/.test(e));
  check('no page errors or failed requests', unexpected.length === 0, unexpected.join(' | '));
} catch (e) {
  check('script', false, String(e));
} finally {
  const failed = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - failed}/${results.length} checks passed in ${Math.round((Date.now() - t0) / 1000)} s; screenshots in ${OUT}`);
  try { ws?.close(); } catch { /* closed */ }
  browser.kill();
  await sleep(500);
  try { fs.rmSync(prof, { recursive: true, force: true }); } catch { /* the browser may still hold its profile on Windows */ }
  process.exit(failed ? 1 : 0);
}
