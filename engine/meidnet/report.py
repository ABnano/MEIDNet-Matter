"""
Self-contained HTML reports that explain each step in plain language.

Every report opens with a one-sentence verdict (good / needs attention / blocked),
then shows the evidence behind it, and ends with what to do next.  The files have
no external dependencies and can be e-mailed or attached to a lab notebook.
"""
from __future__ import annotations

import datetime as _dt
import html
import json
import os

import numpy as np
import torch
from torch.utils.data import DataLoader

from meidnet import __version__
from meidnet import svg
from meidnet.constraints import explain, rule_key

CSS = """
:root{--bg:#f7f7f5;--card:#ffffff;--ink:#1d2327;--muted:#5d6670;--line:#dde1e5;--accent:#2457c5;--accent2:#d9822b;
--good:#1f8a4c;--warn:#b7791f;--bad:#c0392b;--goodbg:#e8f5ee;--warnbg:#fdf3e1;--badbg:#fbeaea;--track:#e4e8ee;--win:#2457c514}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#15181c;--card:#1d2126;--ink:#e6e9ec;--muted:#9aa4ae;
--line:#30363d;--accent:#7aa2ff;--accent2:#f0a35e;--good:#4cc38a;--warn:#e0b252;--bad:#ff7b72;--goodbg:#173326;--warnbg:#3a2f17;
--badbg:#3d1f1f;--track:#2b3138;--win:#7aa2ff22}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:28px 16px 8px;max-width:1040px;margin:auto}.brand{font-weight:700;letter-spacing:.08em;color:var(--accent);font-size:13px}
h1{margin:4px 0 2px;font-size:26px}h2{font-size:19px;margin:0 0 10px}h3{font-size:16px;margin:14px 0 6px}
.sub{color:var(--muted);margin:0}main{max-width:1040px;margin:auto;padding:8px 16px 40px}
section,.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px;margin:14px 0}
.verdict{border-radius:10px;padding:14px 16px;margin:14px 0;font-size:16px;border:1px solid var(--line)}
.verdict.good{background:var(--goodbg);border-color:var(--good)}.verdict.warn{background:var(--warnbg);border-color:var(--warn)}
.verdict.bad{background:var(--badbg);border-color:var(--bad)}.verdict b{display:block;font-size:17px;margin-bottom:2px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
.muted{color:var(--muted)}table{border-collapse:collapse;width:100%;font-size:14px}
td,th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{color:var(--muted);font-weight:600}
code,pre{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:13px}
pre{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px;overflow:auto}
details{margin:8px 0}summary{cursor:pointer;color:var(--accent)}
.chart{width:100%;max-width:520px;height:auto}.chart.wide{max-width:760px}.gauge{width:100%;max-width:300px;height:34px}
.ax{stroke:var(--muted);stroke-width:1}.grid{stroke:var(--line);stroke-width:.6}.tick,.val,.leg{fill:var(--muted);font-size:11px}
.lab{fill:var(--ink);font-size:12px}.bar{fill:var(--accent);opacity:.85}.ok{fill:var(--good)}.win{fill:var(--win)}
.mark{stroke:var(--accent2);stroke-width:2;stroke-dasharray:4 3}.marklab{fill:var(--accent2);font-size:11px}
.pt{fill:var(--accent);opacity:.45}.pt2{fill:var(--accent2);opacity:.55}.pt3{fill:var(--muted);opacity:.35}
.star{fill:var(--good);stroke:var(--card);stroke-width:1}.track{fill:var(--track)}.dot{fill:var(--accent)}
.s0{stroke:var(--accent);stroke-width:2}.s1{stroke:var(--accent2);stroke-width:2}.s2{stroke:var(--good);stroke-width:2}
.s3{stroke:var(--bad);stroke-width:2}.s4{stroke:var(--muted);stroke-width:2}.s0t{fill:var(--accent)}.s1t{fill:var(--accent2)}
.s2t{fill:var(--good)}.s3t{fill:var(--bad)}.s4t{fill:var(--muted)}
.cands{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.cand h3{margin:0 0 4px;font-size:18px}.chk{list-style:none;padding:0;margin:8px 0}.chk li{padding:2px 0}
.pass{color:var(--good);font-weight:700}.fail{color:var(--bad);font-weight:700}.flag{color:var(--warn)}
.pill{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:1px 9px;margin:2px;font-size:13px}
footer{max-width:1040px;margin:auto;padding:0 16px 30px;color:var(--muted);font-size:13px}
@media (max-width:600px){h1{font-size:22px}section,.card{padding:14px}}
"""


def esc(s) -> str:
    return html.escape(str(s))


def page(title: str, subtitle: str, body: str, name: str = "") -> str:
    when = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{esc(title)}</title><style>{CSS}</style></head><body>"
            f"<header><div class='brand'>MEIDNet</div><h1>{esc(title)}</h1><p class='sub'>{subtitle}</p></header>"
            f"<main>{body}</main><footer>MEIDNet {__version__} · {esc(name)} · {when}</footer></body></html>")


def verdict(kind: str, headline: str, text: str = "") -> str:
    icon = {"good": "✅", "warn": "⚠️", "bad": "⛔"}[kind]
    return f"<div class='verdict {kind}'><b>{icon} {esc(headline)}</b>{text}</div>"


def write(path: str, content: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def explain_box(summary: str, text: str) -> str:
    return f"<details><summary>{esc(summary)}</summary><p>{text}</p></details>"


# ───────────────────────── check report ─────────────────────────
def _property_notes(values: np.ndarray, label: str) -> list[str]:
    notes = []
    if len(values) == 0:
        return notes
    mode_share = np.mean(np.isclose(values, np.median(values)))
    if mode_share > 0.5:
        notes.append(f"{mode_share:.0%} of the {esc(label)} values equal {np.median(values):.3g}. The model sees few "
                     "examples of other values, so targets far from it will be harder to hit.")
    q1, q99 = np.percentile(values, [1, 99])
    if (values.max() - q99) > 3 * (q99 - q1 + 1e-12):
        notes.append(f"{esc(label)} has extreme outliers (max {values.max():.3g}). Check them for unit or typing errors.")
    return notes


def check_report(info: dict, path: str) -> str:
    cfg = info["config"]
    rep = info["report"]
    recs = info["records"]
    fam = info["family"]
    d = cfg.data
    n, k = rep.rows, rep.kept
    top_reason = rep.skipped.most_common(1)[0][0] if rep.skipped else ""
    if k == 0:
        v = verdict("bad", f"None of your {n} rows can be used yet.",
                    f"<p>The most common problem: <b>{esc(top_reason)}</b>. See “Rows that were skipped” below.</p>")
    elif k < 200:
        v = verdict("warn", f"{k} of {n} materials are usable — enough to try MEIDNet, but small.",
                    "<p>Training will run, but with only a few hundred examples predictions will be rough. "
                    "Datasets of a few thousand materials are typical.</p>")
    elif rep.skipped and sum(rep.skipped.values()) > 0.2 * n:
        v = verdict("warn", f"{k} of {n} materials are usable; {sum(rep.skipped.values())} were skipped.",
                    f"<p>Most skipped rows: <b>{esc(top_reason)}</b>. If those materials matter, fix them and re-run "
                    "<code>meidnet check</code>.</p>")
    else:
        v = verdict("good", f"{k} of {n} materials are ready for training.",
                    "<p>Your table, structures and properties were read without serious problems.</p>")

    props = d.properties
    rows = [("Table", esc(d.table)), ("Identifier column", f"<code>{esc(d.id_column)}</code>"),
            ("Structures from", f"column <code>{esc(d.cif_column)}</code>" if d.cif_column in info["columns"]
             else f"folder <code>{esc(d.structures_dir)}</code>"),
            ("Properties", ", ".join(f"<code>{esc(p.column)}</code>{' [' + esc(p.unit) + ']' if p.unit else ''}" for p in props)),
            ("Atoms per cell allowed", f"up to {d.max_sites}")]
    if fam is not None:
        rows.append(("Family / prototype", f"{esc(fam.title)} — {fam.n_sites} sites"
                     + (f"; {rep.aligned} structures re-ordered to the prototype" if d.align_to_prototype else
                        "; atoms are used in file order (align_to_prototype: false)")))
    read = "<table>" + "".join(f"<tr><th>{a}</th><td>{b}</td></tr>" for a, b in rows) + "</table>"

    skipped = "<p class='muted'>No rows were skipped.</p>"
    if rep.skipped:
        skipped = svg.hbars(list(rep.skipped.items()), "Why rows were skipped") + "<table><tr><th>Reason</th><th>Rows</th><th>Examples (ids)</th></tr>"
        for reason, c in rep.skipped.most_common():
            skipped += f"<tr><td>{esc(reason)}</td><td>{c}</td><td>{esc(', '.join(rep.examples.get(reason, [])))}</td></tr>"
        skipped += "</table>" + explain_box(
            "How do I fix these?",
            "<b>CIF could not be read</b>: open the file in VESTA or pymatgen to find the syntax error. "
            "<b>more than max_sites atoms</b>: raise <code>data.max_sites</code> (slower) or use primitive cells. "
            "<b>does not match the prototype</b>: atoms sit too far from the family's ideal sites (distorted cell, a "
            "different crystal type, or another cell setting). Raise <code>data.prototype_tolerance</code> (default 0.15 "
            "of a cell edge) to accept distorted structures, or set <code>align_to_prototype: false</code> to train on "
            "atoms in file order. <b>missing property value</b>: fill or drop empty cells in your table.")

    hists = []
    for i, p in enumerate(props):
        vals = np.array([r.properties[i] for r in recs]) if recs else np.array([])
        stats = (f"<p class='muted'>min {vals.min():.3g} · median {np.median(vals):.3g} · max {vals.max():.3g}</p>"
                 if len(vals) else "")
        notes = "".join(f"<p class='flag'>⚠ {n_}</p>" for n_ in _property_notes(vals, p.display))
        hists.append(f"<div><h3>{esc(p.display)}{' [' + esc(p.unit) + ']' if p.unit else ''}</h3>"
                     f"{svg.histogram(vals, p.display, p.unit or p.display)}{stats}{notes}</div>")

    sites = svg.hbars([(f"{s} atoms", c) for s, c in sorted(rep.site_counts.items())], "Atoms per cell")
    elements = svg.hbars(list(rep.elements.items()), "Most common elements", max_items=20)
    body = v + f"<section><h2>What MEIDNet read</h2>{read}</section>"
    body += f"<section><h2>Rows that were skipped</h2>{skipped}</section>"
    body += f"<section><h2>Your properties</h2><div class='grid2'>{''.join(hists)}</div>" + explain_box(
        "Why does the spread of values matter?",
        "MEIDNet learns how structures relate to these numbers. It can only design for values it has seen enough "
        "examples of; asking for a band gap that almost no training material has is extrapolation, and the "
        "generation report will flag it.") + "</section>"
    body += f"<section><h2>Your structures</h2><div class='grid2'><div><h3>Atoms per cell</h3>{sites}</div>" \
            f"<div><h3>Elements (number of materials containing each)</h3>{elements}</div></div></section>"
    if info.get("val_report"):
        vr = info["val_report"]
        body += f"<section><h2>Validation table</h2><p>{vr.kept} of {vr.rows} rows usable.</p></section>"
    body += ("<section><h2>Next step</h2><p>Train the model:</p><pre>meidnet train meidnet.yaml</pre>"
             "<p class='muted'>Training writes <code>model.pt</code> and a training report that tells you how accurate "
             "the model is.</p></section>")
    return write(path, page("Data check", f"Can MEIDNet learn from <b>{esc(cfg.name)}</b>?", body, cfg.name))


# ───────────────────────── training report ─────────────────────────
@torch.no_grad()
def _predictions(lm, dataset):
    model = lm.model
    dev = next(model.parameters()).device
    P, Y = [], []
    for b in DataLoader(dataset, batch_size=64):
        zc, _ = model.encode_crystal(b["crystal_vec"].to(dev))
        P.append(lm.stats.denormalize_tensor(model.property_decoder(zc)).cpu().numpy())
        Y.append(lm.stats.denormalize_tensor(b["props"].to(dev)).cpu().numpy())
    return np.concatenate(P), np.concatenate(Y)


def quality_word(mae, std):
    if not std > 1e-12:              # every value the same: an error cannot be compared with a spread
        return "not judged", None
    r = mae / std
    if r < 0.25:
        return "good", r
    if r < 0.5:
        return "fair", r
    return "weak", r


def training_report(cfg, lm, history, train_set, val_set, path) -> str:
    stats = lm.stats
    eval_set = val_set if val_set is not None and len(val_set) else train_set
    which = "validation" if eval_set is val_set else "training (no validation set!)"
    P, Y = _predictions(lm, eval_set)
    words = []
    rows = []
    parity = []
    for j, c in enumerate(stats.columns):
        mae = float(np.abs(P[:, j] - Y[:, j]).mean())
        std = float(Y[:, j].std())
        ss = float(((Y[:, j] - Y[:, j].mean()) ** 2).sum())
        r2 = 1 - float(((P[:, j] - Y[:, j]) ** 2).sum()) / ss if ss > 0 else float("nan")
        word, ratio = quality_word(mae, std)
        words.append(word)
        unit = stats.units[j]
        u = f" [{unit}]" if unit else ""
        css = {"good": "pass", "fair": "flag", "weak": "fail"}.get(word, "muted")
        shown = word if word != "not judged" else f"not judged (all {which.split()[0]} values are equal)"
        rows.append(f"<tr><td>{esc(stats.labels[j])}</td><td>{mae:.3g} {esc(unit)}</td><td>{std:.3g} {esc(unit)}</td>"
                    f"<td>{'–' if r2 != r2 else f'{r2:.2f}'}</td><td class='{css}'>{esc(shown)}</td></tr>")
        parity.append(f"<div><h3>{esc(stats.labels[j])}</h3>" + svg.scatter(
            Y[:, j], P[:, j], f"Predicted vs true {stats.labels[j]}", f"true{u}", f"predicted{u}",
            diagonal=True) + "</div>")
    last_val = history["val"][-1] if history.get("val") else None
    judged = [w for w in words if w != "not judged"]
    if len(judged) < len(words):
        v = verdict("warn", "Some properties cannot be judged on this validation set.",
                    "<p>Every validation material has the same value for at least one property, so its error cannot "
                    "be compared with a spread. Use more data (or a larger <code>val_fraction</code>) to judge the "
                    "model.</p>")
    elif all(w == "good" for w in words):
        v = verdict("good", "The model predicts every property well from structure alone.",
                    "<p>Typical errors are under a quarter of the natural spread of each property.</p>")
    elif "weak" in words:
        v = verdict("warn", "Some properties are predicted poorly.",
                    "<p>Generation will still run, but targets for the weak properties are unreliable. More data, more "
                    "epochs or checking the data for errors usually helps.</p>")
    else:
        v = verdict("warn", "The model is usable; some predictions are only fair.",
                    "<p>Treat predicted values as rough guides and confirm promising candidates with DFT.</p>")
    table = ("<table><tr><th>Property</th><th>Typical error (MAE)</th><th>Natural spread (std)</th><th>R²</th>"
             "<th>Verdict</th></tr>" + "".join(rows) + "</table>")
    table += explain_box("How are these judged?",
                         "The error is compared with how much the property varies in your data. Error below 25% of the "
                         "spread is <b>good</b>, below 50% is <b>fair</b>, otherwise <b>weak</b>. Predictions here use the "
                         "structure alone — the same situation as judging a new candidate.")
    tr = history["train"]
    ep = [r["epoch"] for r in tr]
    loss_series = {k: (ep, [r[k] for r in tr]) for k in ("total", "recon_joint", "recon_from_prop", "prop_joint", "contrastive")}
    curves = svg.lines(loss_series, "Training losses", "epoch", "loss", log=True)
    align = svg.lines({"cosine(z_c, z_p)": (ep, [r["cosine"] for r in tr]),
                       "alignment strength / max": (ep, [r["contrastive_strength"] / max(cfg.training.contrastive_weight, 1e-9) for r in tr])},
                      "Alignment", "epoch", "value")
    align_text = ""
    if last_val:
        n = last_val["n"]
        align_text = (f"<p>On {n} {which} materials, a structure's own property vector is its nearest match "
                      f"<b>{last_val['retrieval_top1']:.0%}</b> of the time (top-5: {last_val['retrieval_top5']:.0%}); "
                      f"random guessing would give {1 / max(n, 1):.1%}.</p>")
    notes = []
    if cfg.training.warmup() > cfg.training.epochs:
        notes.append(f"The alignment ramp ({cfg.training.warmup()} epochs) is longer than training "
                     f"({cfg.training.epochs} epochs), so alignment never reached full strength.")
    if len(train_set) < 500:
        notes.append("Fewer than 500 training materials: expect large errors.")
    body = v + f"<section><h2>How accurate is the model?</h2><p class='muted'>Measured on the {which} set.</p>{table}" \
               f"<div class='grid2'>{''.join(parity)}</div></section>"
    body += (f"<section><h2>Did the two modalities align?</h2>{align_text}{align}" + explain_box(
        "What is alignment and why does it matter?",
        "MEIDNet has one encoder for structures and one for properties. Training pulls the two latents of the same "
        "material together (cosine → 1). Inverse design relies on this: it starts from the latent of your target "
        "properties and decodes a structure from it.") + "</section>")
    body += f"<section><h2>Training curves</h2>{curves}" + "".join(f"<p class='flag'>⚠ {esc(n_)}</p>" for n_ in notes) + "</section>"
    from meidnet.train import human_time
    body += (f"<section><h2>Run details</h2><table><tr><th>Training materials</th><td>{len(train_set)}</td></tr>"
             f"<tr><th>Validation materials</th><td>{0 if val_set is None else len(val_set)}</td></tr>"
             f"<tr><th>Epochs</th><td>{cfg.training.epochs}</td></tr><tr><th>Time</th><td>{human_time(history.get('seconds', 0))}</td></tr>"
             f"<tr><th>Model file</th><td><code>{esc(os.path.basename(str(lm.path)))}</code></td></tr></table></section>")
    body += ("<section><h2>Next step</h2><p>Design candidates for your targets:</p><pre>meidnet generate meidnet.yaml</pre>"
             "<p class='muted'>Or explore the design space interactively: <code>meidnet studio meidnet.yaml</code>.</p></section>")
    return write(path, page("Training report", f"How good is the model trained for <b>{esc(cfg.name)}</b>?", body, cfg.name))


# ───────────────────────── generation report ─────────────────────────
PRE_STAGES = ["no charge-balancing element", "same element on two sites"]


def _funnel_for(t, family):
    order = PRE_STAGES + [rule_key(c) for c in family.constraints if c["name"] == "min_distance"] + \
        (["symmetry_refinement"] if family.refine_symmetry else []) + \
        [rule_key(c) for c in family.constraints if c["name"] != "min_distance"]
    stages = [("element choices tried", t.attempts, "")]
    left = t.attempts
    for name in order:
        lost = t.first_failure.get(name, 0)
        if lost == 0:
            continue
        left -= lost
        title = explain(name, family.constraint_params(name) or {})[0] if name not in PRE_STAGES else name
        stages.append((f"passed: {title}"[:30], left, f"−{lost:,}"))
    stages.append(("saved (new, unique)", len(t.saved), ""))
    return stages


def _candidate_card(c, objectives, stats, ranges, family, target_values):
    gauges = []
    for o in objectives:
        p = o.property
        j = stats.index(p)
        lo, hi = ranges.get(p, (min(target_values[p], c.predictions[p]), max(target_values[p], c.predictions[p])))
        unit = stats.units[j]
        gauges.append(f"<div><span class='muted'>{esc(stats.labels[j])}:</span> predicted <b>{c.predictions[p]:.3g}</b> "
                      f"vs target {target_values[p]:.3g} {esc(unit)}{svg.target_bar(p, c.predictions[p], target_values[p], lo, hi, unit=unit)}</div>")
    chk = []
    for r in c.constraint_results:
        params = family.constraint_params(r["name"]) or {}
        title, text = explain(r["name"], params)
        rule = params.get("name", r["name"])            # the registered rule (r["name"] may be a rule id)
        val = f" = {r['value']:.3g}" if r["value"] is not None and rule != "charge_neutrality" else ""
        win = ""
        if r["window"] and rule != "charge_neutrality":
            lo, hi = r["window"]
            win = f" (allowed {'' if lo is None else f'{lo:g}'}–{'' if hi is None else f'{hi:g}'})"
        chk.append(f"<li title='{esc(text)}'><span class='pass'>✓</span> {esc(title)}{esc(val)}{esc(win)}"
                   f"{' — ' + esc(r['detail']) if rule == 'charge_neutrality' else ''}</li>")
    flags = "".join(f"<p class='flag'>⚠ {esc(f)}</p>" for f in c.flags)
    sites = " ".join(f"<span class='pill'>{esc(g)} = {esc(e)}</span>" for g, e in c.elements.items())
    return (f"<div class='card cand'><h3>{esc(c.formula)}</h3><div>{sites}</div>"
            f"<p class='muted'>cell edge {c.lattice_a:.3f} Å · found in round {c.round} · "
            f"<a href='{esc(os.path.join('generation', c.file))}'>CIF file</a></p>{''.join(gauges)}"
            f"<ul class='chk'>{''.join(chk)}</ul>{flags}</div>")


def _latent_map(res):
    Z0 = [np.concatenate(t.latent_start) for t in res.targets if t.latent_start]
    Zf = [np.concatenate(t.latent_final) for t in res.targets if t.latent_final]
    if not Z0:
        return ""
    Z0 = np.concatenate(Z0)
    Zf = np.concatenate(Zf)
    X = np.vstack([Z0, Zf])
    X = np.nan_to_num(X)
    Xc = X - X.mean(0)
    _, _, Vt = np.linalg.svd(Xc, full_matrices=False)
    P = Xc @ Vt[:2].T
    n0 = len(Z0)
    classes = ["pt3"] * n0 + ["pt2"] * len(Zf)
    return svg.scatter(P[:, 0], P[:, 1], "Latent search map", "principal direction 1", "principal direction 2",
                       classes=classes, labels=["start"] * n0 + ["after optimisation"] * len(Zf))


def generation_report(cfg, lm, family, res, path) -> str:
    g = cfg.generation
    stats = lm.stats
    saved = res.saved
    n_rules = len(family.constraints)
    flagged = [c for c in saved if c.flags]
    if not saved:
        v = verdict("bad", "No candidate passed every rule.",
                    "<p>Look at the funnel below to see which rule removed the most attempts, then try more rounds, a "
                    "different variant, or relax that rule in <code>generation.overrides</code>.</p>")
    elif flagged:
        v = verdict("warn", f"{len(saved)} candidate(s) saved; {len(flagged)} rely on extrapolated predictions.",
                    "<p>All saved candidates obey every rule applied in this run. For the flagged ones (⚠ on the card) a "
                    "predicted property value lies outside what the model saw in training — treat those numbers with "
                    "caution.</p>")
    else:
        v = verdict("good", f"{len(saved)} candidate(s) saved for {len(res.targets)} target(s).",
                    f"<p>Each one passed all {n_rules} rules of the {esc(family.title)} family.</p>")
    intro = ("<p>MEIDNet started from the latent point that your target properties map to, searched nearby latents "
             "for ones that decode into chemically sensible crystals, and kept the candidates whose predicted "
             "properties are closest to the target. <b>Predicted values come from the model and must be confirmed by "
             "calculation or experiment.</b></p>")
    if saved:
        norms = [c.latent_norm for c in saved]
        span = f"{min(norms):.1f}" if max(norms) - min(norms) < 0.05 else f"{min(norms):.1f}–{max(norms):.1f}"
        intro += (f"<p class='muted'>The model was trained on latents of length 1; the search moves them further out "
                  f"(here length {span}), so every predicted value below is the model's extrapolation along that "
                  f"direction. This is how MEIDNet searches, not a fault of one candidate.</p>")
    off = ""
    if g.disabled_rules:   # say plainly which of the family's rules this run did not apply
        off = (f"<p class='flag'>⚠ Switched off for this run (<code>disabled_rules</code>): "
               f"{esc(', '.join(g.disabled_rules))}. Candidates were not checked against these rules.</p>")
    body = v + f"<section><h2>What happened</h2>{intro}{off}<p class='muted'>Family: {esc(family.describe()).replace(chr(10), '<br>')}</p></section>"
    for t in res.targets:
        tv = ", ".join(f"{stats.labels[stats.index(o.property)]} {t.values[o.property]:g} {stats.units[stats.index(o.property)]}"
                       for o in g.objectives)
        lead = (f"<p>{t.rounds_used} search round(s), {t.latents_decoded:,} latents decoded, {t.attempts:,} element "
                f"choices tried; {t.latents_passing:,} latents gave a composition that passed every rule; "
                f"<b>{len(t.saved)}</b> saved (skipped {t.skipped_duplicate} repeats and {t.skipped_similar} near-duplicates).</p>")
        fun = svg.funnel(_funnel_for(t, family), "Where attempts were rejected")
        cards = "".join(_candidate_card(c, g.objectives, stats, res.property_ranges, family, t.values) for c in t.saved)
        rej = ""
        if t.rejected_examples:
            rej = "<table><tr><th>Composition</th><th>Rejected by</th><th>Measured</th></tr>"
            for ex in t.rejected_examples[:8]:
                bad = next((r for r in ex["results"] if not r["passed"]), None)
                meas = (f"{bad['value']:.3g} (allowed {bad['window'][0]}–{bad['window'][1]})"
                        if bad and bad["value"] is not None and bad["window"] else (bad or {}).get("detail", ""))
                title = explain(ex["first_failure"], family.constraint_params(ex["first_failure"]) or {})[0]
                rej += f"<tr><td>{esc(ex['formula'])}</td><td>{esc(title)}</td><td>{esc(meas)}</td></tr>"
            rej += "</table>"
        body += (f"<section><h2>Target {t.index}: {esc(tv)}</h2>{lead}<h3>The funnel</h3>{fun}"
                 f"{explain_box('How to read the funnel', 'Each bar is how many element choices were still alive after a rule. The biggest drop shows which rule limits this target most; relaxing it (if chemically justified) gives more candidates.')}"
                 f"<h3>Saved candidates</h3><div class='cands'>{cards or '<p class=muted>none</p>'}</div>"
                 + (f"<details><summary>Examples of rejected compositions</summary>{rej}</details>" if rej else "")
                 + "</section>")
    lm_map = _latent_map(res)
    if lm_map:
        body += (f"<section><h2>Where the search went</h2>{lm_map}" + explain_box(
            "What is this picture?",
            "Each dot is one latent vector, projected onto the two directions in which they vary most. Grey dots are "
            "starting points (near the latent of the target properties); orange dots are where the optimisation ended. "
            "Searches spread out on purpose (diversity) so that different compositions are found.") + "</section>")
    body += ("<section><h2>Next steps</h2><ol><li>Open the CIF files in VESTA or any structure viewer.</li>"
             "<li>Check stability with a machine-learned potential: <code>meidnet screen</code> (needs the "
             "<code>stability</code> extra).</li><li>Confirm the best candidates with DFT before drawing conclusions.</li>"
             "<li>Change targets, rules or elements in <code>meidnet.yaml</code> (or in MEIDNet Studio) and run again.</li></ol>"
             f"<details><summary>Settings used</summary><pre>{esc(json.dumps(g.model_dump(), indent=1))}</pre></details></section>")
    return write(path, page("Generation report", f"Candidates designed for <b>{esc(cfg.name)}</b>", body, cfg.name))
