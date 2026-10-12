"""MEIDNet pipeline checkup: test every stage on its own so a failure is caught where it happens.

  python pipeline_checkup.py <tag> <checkpoint> [--label-source latent|structure] [--latent-space clip|sphere]
                             [--manifold-weight w] [--skip-search]

Stages and checks (thresholds in THRESHOLDS; every check reports PASS / WARN / FAIL with the measured numbers)
  0 data        zero-inflation of each property, how many materials share a property profile; design-space coverage:
                valid compositions of the family, how many the training data contain, which allowed elements the
                model has never seen (their encoder embeddings are untrained), whether each target is feasible
  1 encoder     structure -> z_c -> property decoder on the held-out test split (can the structure latent carry
                the properties?); latent 5-NN property error (is the latent organised by property?)
  2 alignment   z_c <-> z_p retrieval among distinct property profiles vs chance
  3 decoder     species recovered from z_c / z_joint / z_p in the GENERATION condition (the start coordinates the
                engine really gives: zeros or the prototype) and in the training condition; a large gap means the
                decoder depends on information generation does not have
  4 prop. head  sensitivity of the property decoder to the latent length (matters when the search leaves |z| = 1)
  5 search      a short search (3 targets, 1 round): final latent length, distance to the training manifold,
                agreement between the latent label and the decoded structure's own predicted properties
  6 end-to-end  do the returned structures follow the target? Spearman rho(target, DFT gap) for candidates found in
                Perov-5 and rho(target, structure-predicted gap) for all; distinct compositions
Outputs results/checkups/<tag>.json and <tag>.md.
"""
import argparse, csv, json, os, time
import numpy as np
import pandas as pd
import torch
from scipy.stats import spearmanr
from torch.utils.data import DataLoader

from meidnet.benchmark import evaluate_checkpoint, load_split
from meidnet.checkpoint import load_checkpoint, property_ranges
from meidnet.constraints import build_candidate
from meidnet.data import MaterialsDataset, split_dense, featurize
from meidnet.designspace import enumerate_space
from pymatgen.core import Composition
from meidnet.generate import Designer
from meidnet.pipeline import family_for

try:
    from meidnet_eval.eval_generate import goal, reference_latents
except ImportError:          # run as a plain script from eval/
    from eval_generate import goal, reference_latents

try:
    from meidnet_eval.eval_generate import COST, DATA, GAP
except ImportError:          # run as a plain script from eval/
    from eval_generate import COST, DATA, GAP
MATERIALS = os.environ.get("CHECKUP_MATERIALS",
                           os.environ.get("EVAL_MATERIALS", ""))


def reference_table():
    """The reference the checkup measures against, indexed by composition key.

    Perov-5 ships a complete table keyed by site_key (A|B|X), which also records the split; for any other dataset the
    reference is the dataset's own splits keyed by reduced formula, so stages 0 and 6 work on any intake directory.
    """
    if os.path.exists(MATERIALS):
        m = pd.read_csv(MATERIALS).dropna(subset=["site_key"])
        if GAP in m.columns:
            return m.drop_duplicates("site_key").set_index("site_key")
    frames = []
    for split in ("train", "val", "test"):
        path = f"{DATA}/{split}.csv"
        if os.path.exists(path):
            d = pd.read_csv(path, usecols=lambda c: c in ("formula", GAP, COST))
            d["split"] = split
            frames.append(d)
    m = pd.concat(frames, ignore_index=True)
    return m.drop_duplicates("formula").set_index("formula")
HERE = os.path.dirname(os.path.abspath(__file__))

# The bands live in ONE place: eval/stages.py (validated by `python stages.py --validate`).  This maps the local check keys
# onto the central metric ids, so a band can never be edited here and drift from the document or the app.
try:
    from meidnet_eval.stages import ALL_METRICS, BY_ID
except ImportError:          # run as a plain script from eval/
    from stages import ALL_METRICS, BY_ID

CHECK_METRIC = {
    "encoder_rel_mae": "gap_rel_mae",           # also used for the second property (same band family)
    "cost_rel_mae": "cost_rel_mae",
    "metal_accuracy": "metal_accuracy",
    "knn_rel_mae": "knn_rel_mae",
    "retrieval_vs_chance": "retrieval_vs_chance",
    "decoder_comp_exact_gen": "comp_exact_gen",
    "decoder_condition_gap": "condition_drop",
    "head_length_sensitivity": "head_length_sensitivity",
    "search_length_ratio": "search_length_ratio",
    "search_manifold_cos": "search_manifold_cos",
    "label_rel_mae": "label_rel_mae",
    "rho_target": "rho_target",
}
THRESHOLDS = {k: (ALL_METRICS[v][1].pass_at, ALL_METRICS[v][1].warn_at) for k, v in CHECK_METRIC.items()}


def grade(value, key, higher_is_better, context=None):
    """Grade through the central definition, so conditional metrics (e.g. latent-length sensitivity, which only matters
    when the search drifts) behave here exactly as they do in the report and in the app."""
    if value is None or not np.isfinite(value):
        return "N/A"
    m = ALL_METRICS[CHECK_METRIC[key]][1]
    assert (m.better == "higher") == higher_is_better, f"direction of {key} disagrees with stages.py"
    return m.grade(value, context=context)


def gen_coords(lm, fam, n):
    ms = lm.model.max_sites
    if lm.decoder_coordinate_input == "prototype":
        c = torch.zeros(ms, 3); c[:fam.n_sites] = torch.tensor(fam.frac_coords, dtype=torch.float32)
        return c.unsqueeze(0).expand(n, -1, -1).contiguous()
    return torch.zeros(n, ms, 3)


def recover(lm, test, fam):
    model, ms = lm.model.eval(), lm.model.max_sites
    acc = {}
    with torch.no_grad():
        for b in DataLoader(MaterialsDataset(test, lm.stats), batch_size=512, shuffle=False):
            cv, props = b["crystal_vec"], b["props"]
            true = split_dense(cv, ms); n_sites = (true["species"].sum(-1) > 0).sum(1).numpy()
            zc, zp, zj, enc_center, _, data_coords = model.encode_modalities(cv, props)
            gen_c, c0 = gen_coords(lm, fam, len(cv)), torch.zeros(len(cv), 3)
            for name, z in (("structure", zc), ("joint", zj), ("property", zp)):
                for cond, coords, center in (("generation", gen_c, c0), ("training", data_coords, enc_center)):
                    _, _, spc, _ = model.crystal_decoder(z, input_coords=coords, center=center)
                    r = acc.setdefault(f"{name}|{cond}", [0, 0, 0, 0])
                    for i in range(len(cv)):
                        n = int(n_sites[i]); t = true["species"][i].argmax(-1).numpy()[:n]; p = spc[i].argmax(-1).numpy()[:n]
                        r[0] += 1; r[1] += int(np.array_equal(np.sort(t), np.sort(p))); r[2] += int((t == p).sum()); r[3] += n
    return {k: {"composition_exact_pct": 100 * r[1] / r[0], "site_accuracy_pct": 100 * r[2] / r[3]} for k, r in acc.items()}


def design_space_checks(a, fam_kw, trn, fam, add, data):
    """Stage-0 checks that need a family: how the design space relates to the data (coverage, unseen elements,
    target feasibility).  Skipped with --family none."""
    seen = set(e.symbol for f in trn.formula for e in Composition(f).elements)
    pool = sorted({e for g in fam.groups.values() for e in g.sample})
    unseen = [e for e in pool if e not in seen]
    fam_rules = family_for(goal(2.0, 1, 6, **fam_kw), need_variant=bool(a.variant))
    fam_rules.constraints = [c for c in fam_rules.constraints if c["name"] != "property_window"]
    space = enumerate_space(fam_rules, None)
    valid = [r for r in space["rows"] if all(r["ok"].values())]
    mats = reference_table()
    by_site_key = any("|" in str(i) for i in list(mats.index)[:5])      # Perov-5's table is keyed A|B|X, others by formula
    vkeys = ["|".join(r["e"][g] for g in ("A", "B", "X")) for r in valid] \
        if by_site_key and {"A", "B", "X"} <= set(fam_rules.groups) else [r["f"] for r in valid]
    known = [k for k in vkeys if k in mats.index]
    in_train = [k for k in known if mats.loc[k, "split"] == "train"] if "split" in mats.columns else known
    with_unseen = sum(1 for r in valid if any(e in unseen for e in r["e"].values()))
    data["design_space"] = dict(compositions=len(space["rows"]), valid=len(valid), known=len(known), in_train=len(in_train),
                                novel=len(valid) - len(known), with_unseen_elements=with_unseen, unseen_elements=unseen)
    add("0 data", "design-space coverage", "WARN" if with_unseen else "PASS",
        f"{len(valid)} of {len(space['rows'])} compositions pass the rules; {len(known)} are in Perov-5 ({len(in_train)} in training); "
        f"{with_unseen} of the {len(valid) - len(known)} new ones contain elements never seen in training "
        f"({', '.join(unseen) if unseen else 'none'}) whose encoder embeddings are untrained", value=with_unseen)
    feas = {}
    for tgt in a.targets:
        feas[tgt] = int(sum(1 for k in known if abs(mats.loc[k, GAP] - tgt) <= 0.3 + 1e-9))
    add("0 data", "target feasibility (known valid compositions in window)", "INFO",
        "; ".join(f"{t:g} eV: {n}" for t, n in feas.items()) + " — a target with 0 can only be met by new (unverified) compositions",
        value=None, feasible=feas)
    return unseen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag"); ap.add_argument("ckpt")
    ap.add_argument("--label-source", default="latent"); ap.add_argument("--latent-space", default="clip")
    ap.add_argument("--manifold-weight", type=float, default=0.0); ap.add_argument("--skip-search", action="store_true")
    ap.add_argument("--search-mode", default="optimise", choices=["optimise", "neighbours"])   # 'neighbours' = Option A
    ap.add_argument("--targets", type=float, nargs="+", default=[0.0, 3.0, 5.0])   # each has known valid compositions in window
    ap.add_argument("--family", default=None, help="family for the design-space checks of stage 0 (default: the Perov-5 demo "
                    "family); 'none' skips them, e.g. when discover.py checks the design space in its own stage")
    ap.add_argument("--variant", default="oxide")
    ap.add_argument("--out-dir", default=None, help="where <tag>.json and <tag>.md go (default: results/checkups beside this file)")
    a = ap.parse_args()
    torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "4")))
    t0 = time.time()
    try:
        from meidnet_eval.stages import announce_dataset
    except ImportError:          # run as a plain script from eval/
        from stages import announce_dataset
    announce_dataset("pipeline_checkup", DATA, target=GAP, second=COST)
    lm = load_checkpoint(a.ckpt, device="cpu"); M = lm.model.eval()
    cols = list(lm.stats.columns); gi, hi = cols.index(GAP), cols.index(COST)
    fam_kw = {} if a.family in (None, "none") else dict(family=a.family, variant=a.variant)
    fam = None if a.family == "none" else family_for(goal(2.0, 1, 6, **fam_kw), need_variant=bool(a.variant))
    checks, data = [], {}

    def add(stage, name, status, detail, **numbers):
        checks.append(dict(stage=stage, check=name, status=status, detail=detail, **numbers))
        print(f"[{status:4s}] {stage:11s} {name}: {detail}", flush=True)

    # 0 data
    tr = pd.read_csv(f"{DATA}/train.csv", usecols=[COST, GAP])
    zero_gap = float((tr[GAP] == 0).mean()); prof = tr.round(8).value_counts()
    shared = float((tr.round(8).apply(tuple, axis=1).map(prof.to_dict()) >= 10).mean())
    add("0 data", "zero-inflation", "WARN" if zero_gap > 0.5 else "PASS",
        f"{100 * zero_gap:.0f}% of training band gaps are exactly 0; {100 * shared:.0f}% of materials share their property "
        f"profile with >= 9 others (property -> structure is one-to-many)", zero_gap=zero_gap, shared_profile=shared)

    trn = pd.read_csv(f"{DATA}/train.csv", usecols=["formula"])
    if fam is not None:
        unseen = design_space_checks(a, fam_kw, trn, fam, add, data)
    else:
        unseen = []

    # 1 encoder + 2 alignment
    ev = evaluate_checkpoint(lm, DATA)
    pred = pd.DataFrame(ev.predictions)
    y, q = pred[f"true_{GAP}"].values, pred[f"pred_{GAP}"].values; nz = y > 0
    gap_spread = float(y[nz].std()); dhf_spread = float(pred[f"true_{COST}"].std())
    rel_gap = float(np.abs(q[nz] - y[nz]).mean() / gap_spread)
    rel_dhf = float(np.abs(pred[f"pred_{COST}"] - pred[f"true_{COST}"]).mean() / dhf_spread)
    metal_acc = float(((q < 0.5) == (y == 0)).mean())
    add("1 encoder", "structure -> band gap", grade(rel_gap, "encoder_rel_mae", False),
        f"MAE on gap>0 {np.abs(q[nz] - y[nz]).mean():.2f} eV = {rel_gap:.2f} spreads; r {np.corrcoef(y[nz], q[nz])[0, 1]:+.2f}",
        value=rel_gap)
    add("1 encoder", "structure -> metal or not", grade(metal_acc, "metal_accuracy", True),
        f"{100 * metal_acc:.0f}% correct metal/non-metal calls (gap < 0.5 eV = metal)", value=metal_acc)
    mae_cost = float(np.abs(pred[f"pred_{COST}"] - pred[f"true_{COST}"]).mean())
    add("1 encoder", f"structure -> {COST}", grade(rel_dhf, "encoder_rel_mae", False),
        f"MAE {mae_cost:.3f} = {rel_dhf:.2f} spreads", value=rel_dhf)
    rp = ev.representation
    knn_gap = rp[f"knn_mae_{GAP}"] / float(y.std()); knn_dhf = rp[f"knn_mae_{COST}"] / dhf_spread
    add("1 encoder", "latent organised by property (5-NN)", grade(max(knn_gap, knn_dhf), "knn_rel_mae", False),
        f"5-NN in z_c predicts gap with MAE {rp[f'knn_mae_{GAP}']:.3f} eV ({knn_gap:.2f} spreads), dHf {rp[f'knn_mae_{COST}']:.3f} ({knn_dhf:.2f})",
        value=max(knn_gap, knn_dhf))
    ratio = rp["retrieval_top1"] / (1.0 / rp["n_profiles"])
    add("2 alignment", "structure <-> property retrieval", grade(ratio, "retrieval_vs_chance", True),
        f"top-1 {100 * rp['retrieval_top1']:.0f}% (top-5 {100 * rp['retrieval_top5']:.0f}%) among {rp['n_profiles']:.0f} profiles "
        f"= {ratio:.0f}x chance; matched cosine {rp['cosine_matched']:.2f}", value=ratio)

    # 3 decoder
    test, _ = load_split(DATA, "test", cols, M.max_sites)
    rec = recover(lm, test, fam); data["recoverability"] = rec
    g, t = rec["structure|generation"]["composition_exact_pct"], rec["structure|training"]["composition_exact_pct"]
    add("3 decoder", "structure latent -> structure (generation condition)", grade(g, "decoder_comp_exact_gen", True),
        f"{g:.0f}% exact compositions, {rec['structure|generation']['site_accuracy_pct']:.0f}% sites "
        f"(start coordinates: {lm.decoder_coordinate_input if lm.decoder_coordinate_input == 'prototype' else 'zeros'})", value=g)
    jg, jt = rec["joint|generation"]["composition_exact_pct"], rec["joint|training"]["composition_exact_pct"]
    add("3 decoder", "train/generation mismatch", grade(max(jt - jg, t - g), "decoder_condition_gap", False),
        f"joint latent: {jt:.0f}% with the training inputs vs {jg:.0f}% with the generation inputs "
        f"(decoder trained with '{lm.decoder_coordinate_input}' coordinates)", value=max(jt - jg, t - g))
    pg = rec["property|generation"]
    add("3 decoder", "property latent -> structure (inverse path)", "INFO",
        f"{pg['composition_exact_pct']:.0f}% exact compositions, {pg['site_accuracy_pct']:.0f}% sites from z_p alone "
        f"(one-to-many: low values are expected, the search must do the work)", value=pg["composition_exact_pct"])

    # 4 property head length sensitivity (on test structure latents)
    with torch.no_grad():
        X = next(iter(DataLoader(MaterialsDataset(test[:2000], lm.stats), batch_size=2000, shuffle=False)))["crystal_vec"]
        zc, _ = M.encode_crystal(X)
        P1 = lm.stats.denormalize_tensor(M.property_decoder(zc)).numpy()
        P4 = lm.stats.denormalize_tensor(M.property_decoder(zc * 4.0)).numpy()
    sens = float(max(np.abs(P4[:, gi] - P1[:, gi]).mean() / float(y.std()), np.abs(P4[:, hi] - P1[:, hi]).mean() / dhf_spread))
    sens_detail = (f"stretching z_c from |z|=1 to 4 moves predictions by {sens:.2f} spreads "
                   f"(gap {np.abs(P4[:, gi] - P1[:, gi]).mean():.2f} eV, "
                   f"dHf {np.abs(P4[:, hi] - P1[:, hi]).mean():.2f} eV/atom)")

    def emit_head_sensitivity(length_ratio=None):
        """Graded only when the search actually drifts (stages.py makes this conditional on search_length_ratio):
        at |z| = 1 the behaviour at |z| = 4 is irrelevant, so it is reported as context instead of as a failure."""
        ctx = {"search_length_ratio": length_ratio} if length_ratio is not None else None
        g = grade(sens, "head_length_sensitivity", False, context=ctx)
        extra = ("" if length_ratio is None else
                 f"; the search runs at |z| ratio {length_ratio:.2f}, so this "
                 f"{'is a real risk' if length_ratio > 1.25 else 'hazard cannot arise'}")
        add("4 prop. head", "sensitivity to latent length", g, sens_detail + extra, value=sens)

    # 5 search + 6 end-to-end
    if a.skip_search:
        emit_head_sensitivity(None)
    if not a.skip_search:
        ref = reference_latents(lm, a.ckpt)
        Rn = ref / np.linalg.norm(ref, axis=1, keepdims=True)
        mats = reference_table()
        dft = dict(zip(mats.index, mats[GAP]))             # DFT reference, keyed the same way as the design space above
        rows, Zall = [], []
        for tgt in a.targets:
            cfg = goal(tgt, 7, 6, label_source=a.label_source, latent_space=a.latent_space, manifold_weight=a.manifold_weight,
                       search_mode=a.search_mode)
            cfg.generation.rounds = 1
            fam_t = family_for(cfg, need_variant=True)
            pops = []

            class D(Designer):
                def decode(self, Z, *x, **k):
                    pops.append(Z.clone()); return super().decode(Z, *x, **k)
            d = D(lm, fam_t, cfg.generation, device=torch.device("cpu"), log=lambda *x: None, reference_latents=ref)
            res = d.run(os.path.join(a.out_dir or os.path.join(HERE, "results", "checkups"), f"{a.tag}_search", f"T{tgt:g}"), ranges=property_ranges(lm))
            Zall.append(torch.cat(pops).numpy())
            for c in res.saved:
                cand = build_candidate(fam_t, c.elements)
                sp = d._structure_predictions(cand)
                rows.append(dict(target=tgt, formula=c.formula, label_gap=c.predictions[GAP], struct_gap=sp[GAP],
                                 # Perov-5 is looked up by site key, any other dataset by the candidate's formula
                                 dft_gap=dft.get("|".join(c.elements.get(g, "") for g in ("A", "B", "X")),
                                                 dft.get(c.formula)),
                                 unseen=any(e in unseen for e in c.elements.values())))
        Z = np.concatenate(Zall); L = np.linalg.norm(Z, axis=1)
        train_len = float(np.median(np.linalg.norm(ref, axis=1)))
        emit_head_sensitivity(float(np.median(L)) / train_len)
        ratio_len = float(np.median(L) / train_len)
        add("5 search", "latent length", grade(ratio_len, "search_length_ratio", False),
            f"final search latents |z| median {np.median(L):.2f} (training structure latents {train_len:.2f}) -> ratio {ratio_len:.2f}",
            value=ratio_len)
        mcos = float(np.median(((Z / L[:, None]) @ Rn.T).max(1)))
        add("5 search", "distance to the data manifold", grade(mcos, "search_manifold_cos", True),
            f"median max-cosine of final latents to a training structure latent: {mcos:.3f}", value=mcos)
        df = pd.DataFrame(rows); data["search_candidates"] = rows
        if len(df):
            lab = float((df.label_gap - df.struct_gap).abs().mean() / gap_spread)
            add("5 search", "labels describe the returned structure", grade(lab, "label_rel_mae", False),
                f"|shown label - decoded structure's own prediction| = {(df.label_gap - df.struct_gap).abs().mean():.2f} eV "
                f"({lab:.2f} spreads) over {len(df)} candidates (label source: {a.label_source})", value=lab)
            known = df.dropna(subset=["dft_gap"])
            rho_dft = spearmanr(known.target, known.dft_gap)[0] if known.target.nunique() > 1 and len(known) > 3 else float("nan")
            rho_str = spearmanr(df.target, df.struct_gap)[0] if df.target.nunique() > 1 and len(df) > 3 else float("nan")
            add("6 end-to-end", "returned structures follow the target (DFT)", grade(rho_dft, "rho_target", True),
                f"Spearman rho(target, DFT gap) = {rho_dft:+.2f} over {len(known)} candidates found in Perov-5; "
                f"rho(target, structure-predicted gap) = {rho_str:+.2f} over {len(df)}; {df.formula.nunique()} distinct compositions; "
                f"returned per target: {df.groupby('target').size().to_dict()}", value=rho_dft, rho_structure=rho_str)
            n_un = int(df.unseen.sum())
            add("6 end-to-end", "candidates built from unseen elements", "WARN" if n_un else "PASS",
                f"{n_un} of {len(df)} returned candidates contain elements the model never saw in training "
                f"(their predicted properties rest on untrained embeddings)", value=n_un)
        else:
            add("6 end-to-end", "returned structures follow the target (DFT)", "FAIL", "no candidate returned for any target", value=None)

    out_dir = a.out_dir or os.path.join(HERE, "results", "checkups"); os.makedirs(out_dir, exist_ok=True)
    json.dump(dict(tag=a.tag, ckpt=a.ckpt, switches=dict(label_source=a.label_source, latent_space=a.latent_space,
                   manifold_weight=a.manifold_weight), thresholds=THRESHOLDS, checks=checks, data=data,
                   seconds=time.time() - t0), open(f"{out_dir}/{a.tag}.json", "w"), indent=1, default=float)
    with open(f"{out_dir}/{a.tag}.md", "w") as f:
        f.write(f"# Pipeline checkup — {a.tag}\n\ncheckpoint `{a.ckpt}`; search: label {a.label_source}, latent {a.latent_space}, "
                f"manifold {a.manifold_weight}\n\n| stage | check | status | detail |\n|---|---|---|---|\n")
        for c in checks:
            f.write(f"| {c['stage']} | {c['check']} | **{c['status']}** | {c['detail']} |\n")
    print(f"checkup {a.tag} done in {time.time() - t0:.0f}s -> {out_dir}/{a.tag}.md")


if __name__ == "__main__":
    main()
