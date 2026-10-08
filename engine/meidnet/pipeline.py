"""
The three things a user does, as plain functions: check → train → generate.

Each function reads a ``MEIDNetConfig``, does its job, writes its outputs into
``output_dir`` and finishes by writing an HTML report that explains, in plain
language, what happened and what to do next.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

import torch

from meidnet.checkpoint import build_model, describe, load_checkpoint, property_ranges, save_checkpoint
from meidnet.config import MEIDNetConfig, dump_config
from meidnet.data import (DataReport, MaterialsDataset, compute_stats, load_records, read_table, split_records)
from meidnet.family import load_family


def _log_to(path):
    f = open(path, "a", encoding="utf-8")

    def log(*args):
        msg = " ".join(str(a) for a in args)
        try:
            print(msg, flush=True)
        except UnicodeEncodeError:  # Windows consoles with a legacy code page
            enc = sys.stdout.encoding or "ascii"
            print(msg.encode(enc, errors="replace").decode(enc), flush=True)
        f.write(msg + "\n")
        f.flush()
    return log


def load_plugins(paths: list[str], base_resolve) -> None:
    """Import user plugin files so their @CONSTRAINTS / @SEARCH_TERMS registrations take effect."""
    for p in paths or []:
        path = base_resolve(p)
        spec = importlib.util.spec_from_file_location(os.path.splitext(os.path.basename(path))[0], path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)


def family_for(cfg: MEIDNetConfig, need_variant=False):
    """
    The configured family with the user's variant, filters, overrides and extra constraints applied.
    For generation (``need_variant=True``) the family named in ``generation`` wins; the top-level
    ``family`` only says which prototype the training data were aligned to.
    """
    from meidnet.constraints import assign_rule_ids, check_rule_spec
    g = cfg.generation
    name = (g.family if (need_variant and g and g.family) else None) or cfg.family_name
    if not name:
        return None
    extras = [dict(c) for c in (g.extra_constraints if g else [])]   # rules added on top of the family's own
    try:
        fam = load_family(cfg.resolve(name) if name.endswith((".yaml", ".yml")) else name,
                          variant=g.variant if g else None,
                          exclude=g.exclude_elements if g else None, only=g.only_elements if g else None,
                          overrides=g.overrides if g else None, default_variant=not need_variant)
        for spec in extras:
            check_rule_spec(spec)
    except ValueError as e:
        raise SystemExit(str(e)) from None
    if extras:
        fam.constraints = assign_rule_ids(list(fam.constraints) + extras)
    off = set(g.disabled_rules) if g else set()
    if off:                                           # rules the user switched off for this run
        from meidnet.constraints import rule_key
        known = {rule_key(c) for c in fam.constraints} | {c["name"] for c in fam.constraints}
        unknown = sorted(off - known)
        if unknown:
            raise SystemExit(f"disabled_rules: {', '.join(unknown)} is not a rule of {fam.name}. "
                             f"Its rules: {', '.join(rule_key(c) for c in fam.constraints)}")
        fam.constraints = [c for c in fam.constraints if rule_key(c) not in off and c["name"] not in off]
    return fam


# ───────────────────────── check ─────────────────────────
def check(cfg: MEIDNetConfig, write_report: bool = True, keep_structures: bool = False) -> dict:
    """Read the data exactly as training would and report what is usable."""
    from meidnet.report import check_report
    if cfg.data is None:
        raise SystemExit("This config has no 'data' section, so there is nothing to check.")
    os.makedirs(cfg.out_dir, exist_ok=True)
    family = family_for(cfg)
    d = cfg.data
    df = read_table(cfg.resolve(d.table))
    records, rep = load_records(df, d, cfg.resolve, family, source=os.path.basename(d.table),
                                keep_structures=keep_structures)
    val_records = []
    if d.val_table:
        val_records, rep_val = load_records(read_table(cfg.resolve(d.val_table)), d, cfg.resolve, family,
                                            source=os.path.basename(d.val_table))
    else:
        rep_val = None
    result = {"report": rep, "val_report": rep_val, "records": records, "val_records": val_records,
              "columns": list(df.columns), "family": family, "config": cfg}
    if write_report:
        path = check_report(result, os.path.join(cfg.out_dir, "check_report.html"))
        result["report_path"] = path
    return result


# ───────────────────────── train ─────────────────────────
def train(cfg: MEIDNetConfig, epochs: int | None = None) -> str:
    from meidnet.report import training_report
    from meidnet.train import estimate_epoch_seconds, fit, human_time, pick_device, seed_everything
    if epochs:
        cfg.training.epochs = epochs
    os.makedirs(cfg.out_dir, exist_ok=True)
    log = _log_to(os.path.join(cfg.out_dir, "train.log"))
    info = check(cfg, write_report=True)
    rep: DataReport = info["report"]
    records = info["records"]
    if len(records) < cfg.training.batch_size:
        raise SystemExit(f"Only {len(records)} usable materials - fix the problems in check_report.html first.")
    if info["val_records"]:
        train_recs, val_recs = records, info["val_records"]
    else:
        train_recs, val_recs = split_records(records, cfg.data.val_fraction, cfg.training.seed)
    props = cfg.data.properties
    stats = compute_stats(train_recs, [p.column for p in props], [p.normalize for p in props],
                          [p.display for p in props], [p.unit for p in props])
    train_set = MaterialsDataset(train_recs, stats)
    val_set = MaterialsDataset(val_recs, stats) if val_recs else None
    device = pick_device(cfg.training.device)
    family = info["family"]
    mode = cfg.model.decoder_coordinate_input
    proto = None
    if mode == "prototype":
        if family is None:
            raise SystemExit("decoder_coordinate_input: prototype needs a family.")
        proto = torch.zeros(cfg.data.max_sites, 3)
        proto[:family.n_sites] = torch.tensor(family.frac_coords, dtype=torch.float32)
    est = estimate_epoch_seconds(len(train_set), device) * cfg.training.epochs
    log(f"MEIDNet training '{cfg.name}': {len(train_set)} train / {len(val_recs)} validation materials, "
        f"{len(props)} properties, device {device}. Rough time: {human_time(est)}.")
    seed_everything(cfg.training.seed)
    model_cfg = cfg.model.model_dump()
    model = build_model(len(props), model_cfg, cfg.data.max_sites)
    if cfg.model.decoder_geometry == "wyckoff":
        from meidnet.symmetry import MAX_ORBITS, N_SPACEGROUPS, load_targets
        model.crystal_decoder.add_symmetry_head(N_SPACEGROUPS, MAX_ORBITS, cfg.model.latent_dim)
        if cfg.model.coordinate_bins:
            model.crystal_decoder.add_coordinate_bins(cfg.model.coordinate_bins)
        intake = os.path.dirname(os.path.abspath(cfg.data.table))
        if not os.path.exists(os.path.join(intake, "wyckoff_train.json.gz")):
            # the symmetry decoder trains on a side-car of space groups and symmetry-distinct sites; build it here so
            # a user who followed the guide is not sent to a command the guide never listed
            import subprocess
            import sys as _sys
            log(f"symmetry targets missing in {intake}: building them (python -m meidnet_eval.wyckoff_targets, a few minutes) ...")
            splits = ["train"] + (["val"] if cfg.data.val_table else [])
            r = subprocess.run([_sys.executable, "-m", "meidnet_eval.wyckoff_targets", intake, "--splits", *splits,
                                "--max-sites", str(min(16, cfg.data.max_sites))], capture_output=True, text=True)
            for line in (r.stdout or "").splitlines()[-4:]:
                log("  " + line)
            if r.returncode != 0:
                raise SystemExit("the symmetry targets could not be built:\n" + (r.stderr or "")[-1500:])
        cfg.training._sym_targets = load_targets(intake, "train")
        log(f"D1 symmetry decoder: {len(cfg.training._sym_targets)} training structures carry usable targets")
    ckpt = cfg.checkpoint_path
    # Continue from an existing checkpoint when asked.  Queues that cap a job at an hour would otherwise cap how long a
    # model can train, and "it failed" could not be told apart from "it ran out of wall clock".
    if cfg.training.resume_from:
        src = cfg.training.resume_from if cfg.training.resume_from != "auto" else ckpt
        if os.path.exists(src):
            prev = load_checkpoint(src, device="cpu")
            if cfg.model.decoder_geometry == "wyckoff":
                # A checkpoint trained on the free path carries no symmetry head, so those tensors must be allowed to
                # start fresh - and must be named, so a warm start cannot be mistaken for a fully trained D1.
                missing, unexpected = model.load_state_dict(prev.model.state_dict(), strict=False)
                fresh = sorted({".".join(k.split(".")[:3]) for k in missing})
                log(f"resumed the weights from {src}; starting fresh: {', '.join(fresh) or 'nothing'}"
                    + (f"; {len(unexpected)} tensor(s) in the checkpoint went unused" if unexpected else ""))
            else:
                model.load_state_dict(prev.model.state_dict())
                log(f"resumed the weights from {src}")
        elif cfg.training.resume_from != "auto":
            raise SystemExit(f"resume_from: {src} does not exist")
    extra_base = {"config": json.loads(json.dumps(cfg.model_dump(mode="json"))),
                  "data_report": {"rows": rep.rows, "kept": rep.kept, "skipped": dict(rep.skipped)},
                  "train_formulas": sorted({r.formula for r in train_recs})}

    def save(history):
        save_checkpoint(ckpt, model, stats, model_cfg, cfg.data.max_sites,
                        family.name if family else cfg.family_name, dict(extra_base, history=history))

    history = fit(model, train_set, val_set, cfg.training, mode, proto, device, checkpoint_fn=save, log=log)
    save(history)
    lm = load_checkpoint(ckpt)
    path = training_report(cfg, lm, history, train_set, val_set, os.path.join(cfg.out_dir, "training_report.html"))
    log(f"\nmodel saved to {ckpt}\nreport: {path}")
    return ckpt


# ───────────────────────── generate ─────────────────────────
def generate(cfg: MEIDNetConfig, model_path: str | None = None):
    from meidnet.generate import Designer
    from meidnet.report import generation_report
    from meidnet.train import pick_device
    if cfg.generation is None:
        raise SystemExit("This config has no 'generation' section.")
    os.makedirs(cfg.out_dir, exist_ok=True)
    log = _log_to(os.path.join(cfg.out_dir, "generate.log"))
    device = pick_device(cfg.training.device)
    lm = load_checkpoint(model_path or cfg.checkpoint_path, device=device)
    family = family_for(cfg, need_variant=True)
    log(describe(lm))
    log(family.describe())
    out = os.path.join(cfg.out_dir, "generation")
    res = Designer(lm, family, cfg.generation, device=device, log=log).run(out, ranges=property_ranges(lm))
    with open(os.path.join(out, "meidnet.yaml"), "w", encoding="utf-8") as f:
        f.write(dump_config(cfg))
    path = generation_report(cfg, lm, family, res, os.path.join(cfg.out_dir, "generation_report.html"))
    log(f"\n{len(res.saved)} candidate(s) written to {out}\nreport: {path}")
    return res


__all__ = ["check", "train", "generate", "load_plugins", "family_for"]
