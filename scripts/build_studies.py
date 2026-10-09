"""Build the research artefacts the application serves: the pipeline blocks, the four studies, the checkpoint manifest
and the support files the live generator needs.  Deterministic: the same inputs give byte-identical outputs.

    python scripts/build_studies.py --fix <meidnet_fix> --journey <meidnet_journey> --data <meidnet_data> \
        --checkpoints checkpoints --out examples/research --manifest checkpoints/manifest.json

What is written
  examples/research/pipeline/blocks.json            the ten blocks, metrics, bands, components (from meidnet_eval.stages)
  examples/research/studies/index.json              the five studies in reading order
  examples/research/studies/<id>/study.json          facts, block verdicts, target following, candidates, checkpoints
  examples/research/studies/<id>/files/...           the small tables and CIFs a study links to
  examples/research/support/mp20/...                 judge qualification, test sample, reference AMD, known formulas
  checkpoints/manifest.json                          every checkpoint with its sha256, size and download URLs

The user-246 study carries aggregates only: no structure, no property row, no formula and no checkpoint of that dataset.
"""
from __future__ import annotations

import argparse
import glob
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if os.path.isdir(os.path.join(ROOT, "engine")):
    sys.path.insert(0, os.path.join(ROOT, "engine"))

RELEASE = "v0.3.0"
GITHUB_ASSET = "https://github.com/ABnano/MEIDNet-Matter/releases/download/{release}/{file}"
SPACE_FILE = "https://huggingface.co/spaces/Babu09/MEIDNet-Matter/resolve/main/checkpoints/{file}"
PEROV5_2K = "dual_autoencoder_clip_earlyfusion_propertyaware_2k.pth"

# which checkpoints ship in the Space bundle, which only as release assets, and what each one is for
CHECKPOINTS = [
    dict(id="perov5-2k", file=PEROV5_2K, config=None, dataset="perov5", study="perov5", role="demo", ship=True, loadable=True,
         description="The published Perov-5 model; selectable in the demo project (Goal → Readiness → Candidates → Export).",
         urls=["https://github.com/ABnano/MEIDNet/raw/main/checkpoints/" + PEROV5_2K,
               "https://huggingface.co/Babu09/MEIDNet/resolve/main/checkpoints/" + PEROV5_2K]),
    dict(id="mp20-wyck", file="mp20_wyck.pt", dataset="mp20", study="mp20", role="generation", ship=True, loadable=True,
         description="MP-20, symmetry decoder (space group and symmetry-distinct sites), 100 epochs: the model behind the target-following result and the live generator."),
    dict(id="mp20-main", file="mp20_main.pt", dataset="mp20", study="mp20", role="baseline", ship=True, loadable=True,
         description="MP-20, free-coordinate decoder, 100 epochs: the baseline the symmetry decoder is compared with."),
    dict(id="desc-full", file="desc_full.pt", dataset="perov5", study="perov5", role="final", ship=True, loadable=True,
         description="Perov-5, the final configuration of round 1 (descriptors, structure-read labels, unit-sphere search)."),
    dict(id="desc-full-sp4", file="desc_full_sp4.pt", dataset="perov5", study="perov5", role="demo", ship=True, loadable=True,
         description="Perov-5, the desc-full recipe with four times the weight on reading the properties from the structure: the "
                     "demo project's default: the best band-gap reading on the validation split of the 15 checkpoints trained on the training "
                     "split (six new desc-full variants and nine existing models)."),
    dict(id="control", file="control.pt", dataset="perov5", study="perov5", role="control", ship=True, loadable=True,
         description="Perov-5 control: the same recipe without the structure losses; the configuration the bands were validated against."),
    dict(id="mp-grounded", file="mp_grounded.pt", dataset="mp-perovskites", study="mp-perovskites", role="screening", ship=True, loadable=True,
         description="Materials Project perovskites, grounded recipe: the screening model of round 2."),
    dict(id="mp20-wyck-long", file="mp20_wyck_long.pt", dataset="mp20", study="mp20", role="replicate", ship=False, loadable=True,
         description="mp20-wyck continued to about 350 epochs: shows the alignment recovering to the baseline's value."),
    dict(id="mp20-wyck-bins", file="mp20_wyck_bins.pt", dataset="mp20", study="mp20", role="negative-result", ship=False, loadable=True,
         description="mp20-wyck with a 48-point discrete coordinate grid: kept as a negative result (structure-level accuracy unchanged)."),
    dict(id="desc-full-s1", file="desc_full_s1.pt", dataset="perov5", study="perov5", role="replicate", ship=False, loadable=True,
         description="Seed replicate of desc-full."),
    dict(id="grounded", file="grounded.pt", dataset="perov5", study="perov5", role="ablation", ship=False, loadable=True,
         description="Perov-5 grounded recipe before descriptors."),
    dict(id="prop-only", file="prop_only.pt", dataset="perov5", study="perov5", role="ablation", ship=False, loadable=True,
         description="Perov-5 ablation: property losses only."),
    dict(id="recon-only", file="recon_only.pt", dataset="perov5", study="perov5", role="ablation", ship=False, loadable=True,
         description="Perov-5 ablation: reconstruction losses only."),
    dict(id="mp-control", file="mp_control.pt", dataset="mp-perovskites", study="mp-perovskites", role="control", ship=False, loadable=True,
         description="Materials Project perovskites control."),
]
JUDGES = [dict(id="cgcnn-p5", files=[f"judges/cgcnn_p5_seed{i}.pt" for i in range(3)] + ["judges/cgcnn_p5_test_metrics.json"],
               dataset="perov5", study="perov5", role="judge", ship=False, loadable=False, needs="cgcnn_repo",
               description="Three-seed CGCNN band-gap judge trained on Perov-5 (needs the CGCNN code to run)."),
          dict(id="cgcnn-mpperov", files=[f"judges/cgcnn_mpperov_seed{i}.pt" for i in range(3)] + ["judges/cgcnn_mpperov_test_metrics.json"],
               dataset="mp-perovskites", study="mp-perovskites", role="judge", ship=False, loadable=False, needs="cgcnn_repo",
               description="Three-seed CGCNN band-gap judge trained on the Materials Project perovskites.")]

# the MP-20 generation path, graded through the central bands (values measured in journal entries 60-64)
MP20_MEASURED = {"S6": {"judge_mae_request": 0.68, "consensus_yield": 37 / 175}, "S8": {"judge_qualification": 0.102 / 1.41}}
MP20_VERDICT_NOTES = {
    "S0": ("PASS", "817 compositions per element (rule: 200); mode decided as generation; 68% of gaps are zero"),
    "S1": ("PASS", "held-out band-gap MAE 0.27 eV, formation energy 0.054 eV/atom (baseline 0.26 / 0.047)"),
    "S2": ("PASS", "alignment cosine 0.48 at 100 epochs, 0.64 at 350 (baseline 0.63)"),
    "S3": ("WARN", "template-free valid cells 63% (free decoder 2%), 55 space groups, space group exact 68%; composition exact 12%; coordinate RMSE 0.24"),
    "S4": ("PASS", "label read from the returned cell; agrees with the judge (a second model) within 0.5 eV for 19 of 22"),
    "S5": ("PASS", "target anchor only (latent refinement removed: semiconductor share 20% → 42–62%); one anion required; cell capped"),
    "S6": ("PASS", "independent judge against the request: 1.10 eV on generated cells, 0.68 eV on relaxed cells; two-judge consensus yield 0.21"),
    "S7": ("PARTIAL", "two potentials relax all 37 consensus cells; designed space group kept 50–100%; unique 100%, novel 95%; no hull energy computed"),
    "S8": ("PASS", "MEGNet qualified on this dataset: MAE 0.102 eV = 0.073 of the gap spread (pass ≤ 0.5); PBE head chosen by measurement"),
    "S9": ("WARN", "the support proxy calls 0–6 eV servable; the measured range 0.5–3.0 eV supersedes it"),
}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=1, sort_keys=True, ensure_ascii=False, allow_nan=False)
        f.write("\n")


def finite(x):
    if isinstance(x, float):
        return None if x != x or x in (float("inf"), float("-inf")) else x
    if isinstance(x, dict):
        return {k: finite(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [finite(v) for v in x]
    if isinstance(x, (np.floating,)):
        return finite(float(x))
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


LOCAL_ROOTS = ("/gpfs/", "/home/", "/Users/", "/scratch/")


def scrub_paths(obj):
    """Replace absolute local paths in a payload by their last two components, so no machine layout is published."""
    if isinstance(obj, dict):
        return {k: scrub_paths(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub_paths(v) for v in obj]
    if isinstance(obj, str) and obj.startswith(LOCAL_ROOTS):
        parts = [x for x in obj.split("/") if x]
        return "/".join(parts[-2:])
    return obj


def copy_file(src: str, study_dir: str, name: str, files: dict, media: str) -> None:
    dst = os.path.join(study_dir, "files", name)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if media.startswith("text/") or media.endswith("json"):      # LF only: the checksum must match the committed blob (.gitattributes eol=lf)
        with open(src, "rb") as f:
            data = f.read().replace(b"\r\n", b"\n")
        with open(dst, "wb") as f:
            f.write(data)
    else:
        shutil.copyfile(src, dst)
    files[name] = {"bytes": os.path.getsize(dst), "sha256": sha256_file(dst), "media": media}


def formula_of_cif(cif: str):
    from pymatgen.core import Composition
    m = re.search(r"_chemical_formula_sum\s+'?([^\n']+)", cif)
    if not m:
        return None
    try:
        return Composition(m.group(1)).reduced_formula
    except Exception:
        return None


# ───────────────────────── pipeline blocks ─────────────────────────
# What S0 decided for each study. S0 is a gate before training, not a score: a dataset with too few compositions per element
# to teach a decoder goes to screening, one whose materials mostly share their property values returns a set of candidates
# per target, and one that meets both rules goes to generation. The site shows this route in S0's place.
S0_ROUTES = {"perov5": "candidate sets", "mp-perovskites": "screening", "user-246": "screening", "mp20": "generation",
             "jarvis-dp": "screening"}


def build_blocks(a, out: str, verdicts: dict) -> None:
    from meidnet_eval import stages
    payload = stages.export_blocks()
    payload["dataset_verdicts"] = verdicts
    assert set(verdicts) <= set(S0_ROUTES), f"no S0 route for {set(verdicts) - set(S0_ROUTES)}"
    for d, v in verdicts.items():                      # only a dataset that meets S0 goes to generation
        assert (v.get("S0") == "PASS") == (S0_ROUTES[d] == "generation"), d
    payload["dataset_routes"] = {d: S0_ROUTES[d] for d in verdicts}
    payload["generated_from"] = {"module": "meidnet_eval.stages", "sha256": sha256_file(stages.__file__)}
    text = json.dumps(payload)
    assert not re.search(r"honest", text, re.I), "a forbidden word reached the blocks payload"
    assert "published" not in payload["configs"]
    write_json(os.path.join(out, "pipeline", "blocks.json"), finite(payload))


# ───────────────────────── Perov-5 ─────────────────────────
def build_perov5(a, out: str) -> dict:
    from meidnet_eval import stages
    R = os.path.join(a.fix, "eval", "results")
    sd = os.path.join(out, "studies", "perov5"); files = {}
    ab = json.load(open(os.path.join(R, "ablation_summary.json")))
    published_tags = {"G0", "G7", "G7a", "S0"}            # the original application's configurations are not a result to show
    keep = ["tag", "model", "labels", "latent", "manifold", "returned", "yield_pct", "distinct", "novel_pct", "rho_dft",
            "hit_dft_pct", "label_mae_dft", "label_r_dft", "metal_pct", "passing_latents_pct"]
    table = [{k: finite(r.get(k)) for k in keep} for r in ab["table"] if r.get("tag") not in published_tags]
    dr = pd.read_csv(os.path.join(R, "discovery_report.csv"))
    lit = dr[dr["literature"].notna()]
    redisc = [{"formula": r["formula"], "label_gap": finite(r["label_gap"]), "judge_gap": finite(r["megnet_gllbsc_gap"]),
               "e_hull": finite(r["e_hull"]), "literature": r["literature"], "spacegroup": finite(r.get("spacegroup"))}
              for _, r in lit.iterrows()]
    grades = stages.grade_config("final")
    verdicts = {blk: {"grade": v[0], "note": ""} for blk, v in grades.items() if v is not None}
    verdicts["S0"]["note"] = "documented: 93% of materials share a property profile on a complete grid; density passes"
    verdicts["S5"]["note"] = "documented: seed spread"
    judges = json.load(open(os.path.join(a.checkpoints, "judges", "cgcnn_p5_test_metrics.json")))
    abl = pd.read_csv(os.path.join(R, "ablation_table.csv"), dtype=str, keep_default_na=False)
    abl = abl[~abl.iloc[:, 0].isin(published_tags)]
    abl = abl.map(lambda v: v.replace("honest labels", "labels read from the structure") if isinstance(v, str) else v)
    os.makedirs(sd, exist_ok=True)
    tmp = os.path.join(sd, "ablation_table.tmp.csv"); abl.to_csv(tmp, index=False, lineterminator="\n")
    copy_file(tmp, sd, "ablation_table.csv", files, "text/csv"); os.remove(tmp)
    copy_file(os.path.join(R, "discovery_report.csv"), sd, "discovery_report.csv", files, "text/csv")
    study = {
        "schema": "meidnet-matter/study/1", "id": "perov5", "title": "Perov-5", "order": 1,
        "dataset": {"name": "Perov-5", "train": 11356, "val": 1419, "test": 3785, "elements": 56, "prototypes": 1,
                    "compositions_per_element": 218, "shared_profile_share": 0.93, "zero_share": 0.96,
                    "source": "Castelli et al. 2012; CDVAE split", "properties": ["heat_all", "dir_gap"]},
        "mode": "generation (family: cubic ABX3)",
        "headline": "Target following rho 0.90–0.98 against the DFT grid; 21 stable, unique and novel candidates; known compounds returned at their measured gaps.",
        "verdicts": verdicts,
        "target_following": {"method": "DFT of the whole grid as truth", "rho_range": [0.90, 0.98], "hit_rate_pct_range": [57, 83],
                             "random_hit_pct": 7.7, "label_error_eV_range": [0.18, 0.49], "sun_count": int(dr["SUN"].sum()),
                             "known_compounds_returned": len(redisc)},
        "ablation": {"columns": keep, "rows": table,
                     "note": "Each row is one configuration of the pipeline; rho and hit rate are against the DFT values of what was returned."},
        "rediscoveries": redisc,
        "judges": {"cgcnn_p5": judges},
        "checkpoints": ["desc-full", "desc-full-sp4", "control", "perov5-2k", "desc-full-s1", "grounded", "prop-only", "recon-only", "cgcnn-p5"],
        "reproduce": [{"step": "scorecard", "command": "python -m meidnet_eval.scorecard <intake> --models final=desc_full.pt --gap dir_gap --out scorecard/"},
                      {"step": "generation and ablation", "command": "python -m meidnet_eval.eval_generate ... ; python -m meidnet_eval.eval_analyse"}],
        "limits": ["A complete grid: novelty and staying inside the training chemistry are mutually exclusive here.",
                   "96% of gaps are exactly zero, so the non-zero region is sparse."],
        "files": files, "sources": ["eval/results/ablation_summary.json", "eval/results/discovery_report.csv", "journal entries 1–35"],
    }
    write_json(os.path.join(sd, "study.json"), scrub_paths(finite(study)))
    return {"id": "perov5", "verdicts": {k: v["grade"] for k, v in verdicts.items()}}


# ───────────────────────── Materials Project perovskites ─────────────────────────
def build_mp_perovskites(a, out: str) -> dict:
    from meidnet_eval import stages
    R = os.path.join(a.fix, "eval", "results"); D = os.path.join(a.data, "mp_perovskites", "intake")
    sd = os.path.join(out, "studies", "mp-perovskites"); files = {}
    audit = json.load(open(os.path.join(D, "audit.json")))
    chk = json.load(open(os.path.join(R, "checkups", "MP_checkup.json")))
    checks = [{"stage": c.get("stage"), "check": c.get("check"), "status": c.get("status"), "detail": c.get("detail")} for c in chk["checks"]]
    mm = json.load(open(os.path.join(R, "model_metrics", "mp_grounded.json")))
    ri = json.load(open(os.path.join(R, "MP_screen_novel", "run_info.json")))
    grades = stages.grade_config("mp")
    verdicts = {blk: {"grade": v[0], "note": ""} for blk, v in grades.items() if v is not None}
    verdicts["S0"]["note"] = "12 compositions per element: below the density rule, so screening"
    verdicts["S3"]["note"] = "composition recovery 1.4%"
    judges = json.load(open(os.path.join(a.checkpoints, "judges", "cgcnn_mpperov_test_metrics.json")))
    copy_file(os.path.join(R, "MP_screen_novel", "candidates.csv"), sd, "screen_novel_candidates.csv", files, "text/csv")
    study = {
        "schema": "meidnet-matter/study/1", "id": "mp-perovskites", "title": "Materials Project perovskites", "order": 2,
        "dataset": {"name": "Materials Project perovskites", "train": audit["split_sizes"].get("train"), "val": audit["split_sizes"].get("val"),
                    "test": audit["split_sizes"].get("test"), "rows": audit["rows"], "elements": audit["elements"], "prototypes": audit["prototypes"],
                    "compositions_per_element": 12, "shared_profile_share": finite(audit.get("materials_sharing_profile_with_>=10")),
                    "source": "Materials Project, corner-sharing perovskites", "properties": list(audit["properties"]) if isinstance(audit["properties"], dict) else None},
        "mode": "screening",
        "headline": "The encoder and the alignment transfer; the decoder does not (64% → 1.4% composition recovery). This dataset gave the density rule that picks the mode before training.",
        "verdicts": verdicts, "checks": checks, "model_metrics": finite(mm),
        "target_following": {"method": "screening of an enumerated design space; two potentials agree on 16 of 16 relaxed space groups",
                             "screen_funnel": ri.get("funnel"), "targets": ri.get("targets")},
        "judges": {"cgcnn_mpperov": judges},
        "checkpoints": ["mp-grounded", "mp-control", "cgcnn-mpperov"],
        "reproduce": [{"step": "checkup", "command": "python -m meidnet_eval.pipeline_checkup --ckpt mp_grounded.pt (EVAL_DATA=<intake>)"},
                      {"step": "screening", "command": "python -m meidnet_eval.screen_polymorphs ..."}],
        "limits": ["634 training structures, 73 prototypes: too sparse for the decoder; screening is the measured mode."],
        "files": files, "sources": ["eval/results/checkups/MP_checkup.json", "eval/results/MP_screen_novel/", "journal entries 36–44"],
    }
    write_json(os.path.join(sd, "study.json"), scrub_paths(finite(study)))
    return {"id": "mp-perovskites", "verdicts": {k: v["grade"] for k, v in verdicts.items()}}


# ───────────────────────── user upload (aggregates only) ─────────────────────────
def build_user246(a, out: str) -> dict:
    D = os.path.join(a.data, "user_246")
    sd = os.path.join(out, "studies", "user-246")
    prev = json.load(open(os.path.join(D, "intake", "preview.json")))
    sc = json.load(open(os.path.join(D, "intake", "scorecard", "scorecard.json")))
    audit = json.load(open(os.path.join(D, "intake", "audit.json")))
    verdicts = {"S0": {"grade": prev["verdict"], "note": f"density {prev['values']['density']:.1f} compositions per element (rule 200): {prev['mode']}"}}
    for blk, rep in sc["report"]["main"].items():
        verdicts[blk] = {"grade": rep["verdict"], "note": "; ".join(f"{m['metric']} {m['value']:.3g} {m['unit']}" for m in rep.get("metrics", [])[:3] if m.get("value") is not None)}
    verdicts["S7"] = {"grade": "PASS", "note": "two potentials agree on 53 of 58 relaxed cells"}
    study = {
        "schema": "meidnet-matter/study/1", "id": "user-246", "title": "An external upload (246 structures)", "order": 3,
        "dataset": {"name": "User upload", "rows": audit["rows"], "train": audit["split_sizes"].get("train"), "val": audit["split_sizes"].get("val"),
                    "test": audit["split_sizes"].get("test"), "elements": audit["elements"], "prototypes": audit["prototypes"],
                    "compositions_per_element": finite(prev["values"]["density"]), "shared_profile_share": finite(prev["values"]["shared_profile"]),
                    "zero_share": finite(prev["values"]["zero_share"]), "source": "a colleague's dataset of perovskite-type compounds (ABX\u2083, A\u2082BB\u2032X\u2086 double perovskites and elpasolites): hybrid-functional gaps and dielectric constants; aggregates only are published",
                    "properties": ["band gap (hybrid functional)", "dielectric constant"]},
        "mode": "screening",
        "headline": "The best encoder of any dataset on the smallest training set (0.19 spreads, r 0.97); the decoder cannot generate (0%), as the preview predicted; screening returned 13 metastable, formula-novel candidates in known structure types.",
        "verdicts": verdicts,
        "target_following": {"method": "screening; the user's own three-seed CGCNN judge (MAE 0.59 eV) and two potentials; Materials Project hull",
                             "rho_judge": 0.68, "judge_minus_target_mae_eV": 0.90, "validated": 58,
                             "funnel": [["enumerated", 979], ["novel (not in the data)", 875], ["screened in the window, returned", 58],
                                        ["relaxed by two potentials", 42], ["stable by the hull", 37], ["formable", 15], ["judge within 1 eV", 10]],
                             "shortlist": 13, "shortlist_note": "13 metastable, formula-novel candidates in known structure types; 7 contain thallium, so an element exclusion list is needed for practical use"},
        "lessons": ["Uploads arrive as a structure folder plus a spreadsheet; the join is on composition, not on names.",
                    "The preview gate (block S0, no model) predicted screening, not generation; the trained decoder measured 0.00%.",
                    "A proxy becomes context once the quantity it predicts is measured: the held-out label error decides S9.",
                    "Novelty is judged on the reduced composition, which is layout independent."],
        "checkpoints": [], "reproduce": [{"step": "upload adapter", "command": "python -m meidnet_eval.ingest_upload <structures/> <table.xlsx> <out> --props gap dielectric"},
                                        {"step": "preview", "command": "python -m meidnet_eval.preview <intake> --gap <column>"}],
        "limits": ["Aggregates only: the structures, the property table and the trained checkpoint are the data owner's and are not published."],
        "files": {}, "sources": ["meidnet_data/user_246/REPORT.md", "intake/preview.json", "intake/scorecard/scorecard.json", "journal entries 45–52"],
    }
    text = json.dumps(study).lower()
    for forbidden in ('"cif"', '"formula"', '"candidates"'):
        assert forbidden not in text, f"user-246 study must not carry {forbidden}"
    write_json(os.path.join(sd, "study.json"), scrub_paths(finite(study)))
    return {"id": "user-246", "verdicts": {k: v["grade"] for k, v in verdicts.items()}}


# ───────────────────────── MP-20 ─────────────────────────
def known_formulas(intake: str) -> dict:
    """reduced formula -> sorted recorded gaps, over train/val/test of the intake."""
    known: dict[str, list] = {}
    for split in ("train", "val", "test"):
        p = os.path.join(intake, f"{split}.csv")
        if not os.path.exists(p):
            continue
        t = pd.read_csv(p, usecols=["cif", "band_gap"])
        for cif, g in zip(t["cif"], t["band_gap"]):
            f = formula_of_cif(cif)
            if f:
                known.setdefault(f, []).append(round(float(g), 4))
    return {k: sorted(v) for k, v in sorted(known.items())}


def build_mp20(a, out: str) -> dict:
    from meidnet_eval import stages
    from meidnet_eval.metrics_sun import amd as amd_vector
    R = os.path.join(a.fix, "eval", "results"); D = os.path.join(a.data, "mp20", "intake")
    sd = os.path.join(out, "studies", "mp20"); files = {}
    sup = os.path.join(out, "support", "mp20"); os.makedirs(sup, exist_ok=True)
    audit = json.load(open(os.path.join(D, "audit.json"))); prev = json.load(open(os.path.join(D, "preview.json")))
    # the calibration without the relaxed cells that collapsed or are slabs or sparse cells (d1_instrument_bulk; the sheets
    # before those tests, d1_instrument and d1_instrument_physical, are kept as they were)
    inst = json.load(open(os.path.join(R, "d1_instrument_bulk", "instrument.json")))
    pool_cal = json.load(open(os.path.join(R, "d1_pool", "calibration.json")))
    # support: judge qualification (precomputed), the exact test rows it used, known formulas, a reference AMD set
    write_json(os.path.join(sup, "judge_qualification.json"), finite(pool_cal["judge_qualification"]))
    test = pd.read_csv(os.path.join(D, "test.csv"), usecols=["material_id", "cif", "band_gap"]).head(80)
    with gzip.GzipFile(os.path.join(sup, "test_sample.csv.gz"), "wb", compresslevel=9, mtime=0) as gz, io.TextIOWrapper(gz, encoding="utf-8", newline="") as f:
        test.to_csv(f, index=False)
    kf_path = os.path.join(sup, "known_formulas.json.gz")
    known = known_formulas(D)
    with gzip.GzipFile(kf_path, "wb", compresslevel=9, mtime=0) as gz, io.TextIOWrapper(gz, encoding="utf-8") as f:
        json.dump(known, f, separators=(",", ":"), sort_keys=True)
    from pymatgen.core import Structure
    frames = [pd.read_csv(os.path.join(D, f"{s}.csv"), usecols=["material_id", "cif"]) for s in ("train", "val", "test")]
    if not os.path.exists(os.path.join(sup, "reference_amd.npz")):       # deterministic and slow: rebuilt only when missing
        ref = pd.concat(frames).sample(n=min(a.reference_sample, sum(len(f) for f in frames)), random_state=0)
        vecs, ids = [], []
        for mid, cif in zip(ref["material_id"], ref["cif"]):
            try:
                vecs.append(amd_vector(Structure.from_str(cif, fmt="cif"), k=10)); ids.append(str(mid))
            except Exception:
                pass
        np.savez_compressed(os.path.join(sup, "reference_amd.npz"), amd=np.asarray(vecs, dtype=np.float32), material_id=np.asarray(ids))
    # the accepted materials: both judges on the relaxed cell within 0.5 eV, judged metals excluded for non-zero requests
    rel = pd.read_csv(os.path.join(R, "d1_relaxed", "candidates.csv"))
    rcal = json.load(open(os.path.join(R, "d1_relaxed", "calibration.json")))["per_candidate"]
    mlip = [r for f in sorted(glob.glob(os.path.join(R, "d1_consensus", "mlip_shard*.json"))) for r in json.load(open(f))]
    ml = {os.path.basename(r["file"]): r for r in mlip}
    sun = pd.read_csv(os.path.join(R, "d1_relaxed_bulk", "sun_relaxed_strict_per_candidate.csv"))
    amd_by_formula = dict(zip(sun["formula"], sun["amd_nearest"]))
    from meidnet_eval.d1_mlip_check import COLLAPSED, bulk_problem, contact_ratio
    from meidnet_eval.instrument_sheet import classify, same_formula_match
    shutil.rmtree(os.path.join(sd, "files", "accepted"), ignore_errors=True)     # only this build's accepted cells
    accepted, match_cache = [], {}
    for _, r in rel.iterrows():
        c = rcal.get(r["file"], {}); lab, jud = c.get("reencoded_gap"), c.get("independent_gap")
        if lab is None or jud is None or not (abs(lab - r["target"]) <= 0.5 and abs(jud - r["target"]) <= 0.5) or (r["target"] > 0 and jud < 0.1):
            continue
        base = os.path.basename(r["file"]); m = ml.get(base, {}); d = amd_by_formula.get(r["formula"])
        cell = Structure.from_file(os.path.join(R, "d1_consensus", "relaxed_tensornet", base))
        if contact_ratio(cell) < COLLAPSED or bulk_problem(cell):
            continue                                          # collapsed, a slab or a sparse cell: not a bulk crystal, not accepted
        d = None if d is None or d != d else float(d)
        is_known = r["formula"] in known
        match = same_formula_match(cell, D, match_cache) if is_known else None     # every MP-20 entry of that formula
        from pymatgen.core import Composition
        try:
            balanced = bool(Composition(r["formula"]).oxi_state_guesses(max_sites=-1))
        except Exception:
            balanced = None
        name = f"{r['formula']}_{base}"
        relaxed_cif = os.path.join(R, "d1_consensus", "relaxed_tensornet", base)
        copy_file(relaxed_cif, sd, f"accepted/{name}", files, "chemical/x-cif")
        try:                                                  # the relaxed cell as sites + lattice, for the 3D cards
            st = Structure.from_file(relaxed_cif)
            structure = {"lattice": [[round(float(x), 4) for x in row] for row in st.lattice.matrix],
                         "sites": [{"element": str(site.specie.symbol), "frac": [round(float(x), 4) for x in site.frac_coords]} for site in st]}
        except Exception:
            structure = None
        accepted.append({"requested": float(r["target"]), "formula": r["formula"], "label_structure_gap": round(float(lab), 3), "structure": structure,
                         "judge_gap": round(float(jud), 3), "amd_nearest": None if d is None else round(d, 3), "known_formula": is_known,
                         "recorded_gaps": known.get(r["formula"], []), "class": classify(is_known, match), "reference_id": match,
                         "charge_balanced": balanced,
                         "relaxation_drop_eV_atom": m.get("tensornet_drop_per_atom"), "spacegroup_designed": m.get("spacegroup_designed"),
                         "spacegroup_relaxed": m.get("tensornet_spacegroup_relaxed"), "natoms": int(r["natoms"]), "file": f"accepted/{name}",
                         "flag": "judges disagree" if abs(lab - jud) > 0.5 else ""})
    accepted.sort(key=lambda x: (x["requested"], x["formula"]))
    # the pool and the relaxed set as tables
    pool = pd.read_csv(os.path.join(R, "d1_pool", "candidates.csv"))
    pool["independent_gap"] = pool["file"].map(lambda f: pool_cal["per_candidate"].get(f, {}).get("independent_gap"))
    pool.to_csv(os.path.join(sd, "files", "pool_candidates.csv"), index=False) if os.makedirs(os.path.join(sd, "files"), exist_ok=True) is None else None
    files["pool_candidates.csv"] = {"bytes": os.path.getsize(os.path.join(sd, "files", "pool_candidates.csv")), "sha256": sha256_file(os.path.join(sd, "files", "pool_candidates.csv")), "media": "text/csv"}
    rel["label_structure_gap"] = rel["file"].map(lambda f: rcal.get(f, {}).get("reencoded_gap"))
    rel["independent_gap"] = rel["file"].map(lambda f: rcal.get(f, {}).get("independent_gap"))
    rel.to_csv(os.path.join(sd, "files", "relaxed_candidates.csv"), index=False)
    files["relaxed_candidates.csv"] = {"bytes": os.path.getsize(os.path.join(sd, "files", "relaxed_candidates.csv")), "sha256": sha256_file(os.path.join(sd, "files", "relaxed_candidates.csv")), "media": "text/csv"}
    write_json(os.path.join(sd, "files", "mlip.json"), finite(mlip)); files["mlip.json"] = {"bytes": os.path.getsize(os.path.join(sd, "files", "mlip.json")), "sha256": sha256_file(os.path.join(sd, "files", "mlip.json")), "media": "application/json"}
    for f in sorted(glob.glob(os.path.join(R, "d1_pool", "cifs", "*.cif"))):
        copy_file(f, sd, f"pool/{os.path.basename(f)}", files, "chemical/x-cif")
    # verdicts through the central bands where measured values exist
    f_ = inst["funnel"]; acc_ = inst["accuracy"]; n_col = int(f_.get("collapsed_on_relaxation", 0)); n_nb = int(f_.get("not_bulk_on_relaxation", 0))
    n_rel_all = int(f_["relaxed"]) + n_col + n_nb
    measured = dict(MP20_MEASURED, S6=dict(MP20_MEASURED["S6"], judge_mae_request=acc_["mae_relaxed_cells"]))
    notes = dict(MP20_VERDICT_NOTES)
    notes["S6"] = (notes["S6"][0], f"judge against the request: {acc_['mae_generated_cells']:.2f} eV on all {f_['generated']} generated cells; on the same "
                                   f"{acc_['same_cells']} cells {acc_['mae_same_cells_before_relaxation']:.2f} eV before relaxation and {acc_['mae_relaxed_cells']:.2f} eV after it; "
                                   f"two-judge consensus yield {f_['both_judges'] / f_['generated']:.2f}")
    notes["S7"] = (notes["S7"][0], f"two potentials relax all {n_rel_all} consensus cells; {n_col} collapse (closest atoms under 0.6 of their radii) and {n_nb} are "
                                   f"slabs or sparse cells (an empty layer over 6 Å or a packing fraction under 0.12), all set aside; "
                                   f"novel {100 * inst['novelty']['novel_share']:.0f}% of the accepted-window cells; no hull energy computed")
    verdicts = {}
    for blk, (grade, note) in notes.items():
        g = grade
        if blk in measured:
            st = stages.BY_ID[blk]
            g2, _ = st.verdict(measured[blk])
            g = g2 if g2 != "INFO" else grade
        verdicts[blk] = {"grade": g, "note": note}
    classes = {}
    for x in accepted:
        classes[x["class"]] = classes.get(x["class"], 0) + 1
    study = {
        "schema": "meidnet-matter/study/1", "id": "mp20", "title": "MP-20", "order": 4,
        "dataset": {"name": "MP-20", "rows": audit["rows"], "train": audit["split_sizes"]["train"], "val": audit["split_sizes"]["val"], "test": audit["split_sizes"]["test"],
                    "elements": audit["elements"], "prototypes": audit["prototypes"], "compositions_per_element": 817,
                    "shared_profile_share": finite(audit.get("materials_sharing_profile_with_>=10")), "zero_share": 0.68,
                    "source": "Materials Project, structures of at most 20 atoms (the MP-20 benchmark split)", "properties": ["formation_energy_per_atom", "band_gap"]},
        "mode": "generation, family-free (symmetry decoder)",
        "headline": (f"Requested band gap in, relaxed structures out: {len(accepted)} accepted from {len(pool)} generated ("
                     + ", ".join(f"{n} {word}{'s' if n != 1 else ''}{tail}" for n, word, tail in (
                         (classes.get("new composition, new structure", 0), "new composition", ""),
                         (classes.get("new polymorph of known formula", 0), "new polymorph", " of a known formula"),
                         (classes.get("rediscovered known structure", 0), "known structure", " found again")) if n)
                     + f"); of the {n_rel_all} relaxed cells, {n_col} collapsed and {n_nb} were slabs or sparse cells, all set aside."),
        "verdicts": verdicts,
        "calibration": inst,
        "accepted": accepted, "accepted_classes": classes,
        "pool": {"generated": int(len(pool)), "both_judges_generated": int(inst["funnel"]["both_judges"]), "relaxed": int(inst["funnel"]["relaxed"]),
                 "collapsed_on_relaxation": n_col, "not_bulk_on_relaxation": n_nb, "accepted": len(accepted)},
        "judge": finite(pool_cal["judge_qualification"]),
        "checkpoints": ["mp20-wyck", "mp20-main", "mp20-wyck-long", "mp20-wyck-bins"],
        "reproduce": [{"step": "one command", "command": "python -m meidnet_eval.generate_to_target --ckpt mp20_wyck.pt --intake <mp20 intake> --gap band_gap --targets 1.5 2.0 2.5 3.0 --per-target 25 --tag <tag>"},
                      {"step": "calibration", "command": "python -m meidnet_eval.instrument_sheet --pool <tag> --relaxed <tag>/relaxed --consensus <tag>/relax --out <tag>/instrument"}],
        "limits": [f"Served {', '.join(f'{x:g}' for x in inst['range']['served'])} eV of the requested {', '.join(f'{x:g}' for x in inst['range']['requested'])} eV; "
                   f"delivered = {inst['linearity']['intercept']:.2f} + {inst['linearity']['slope']:.2f} × requested (R² {inst['linearity']['r2']:.2f}).",
                   f"Precision ±{inst['precision']['within_target_sd_median']:.1f} eV per structure (the median spread of the delivered gaps for one request).",
                   "Both readings are machine-learning estimates of the PBE band gap MP-20 records; PBE gaps are usually smaller than measured ones.",
                   "The generated cell is a starting point: relaxation lowers the energy by 1.3–8.7 eV/atom and moves atoms 1.4–2.3 Å; the relaxed cell is the product.",
                   f"Of the {n_rel_all} relaxed cells, {n_col} collapsed (closest atoms under 0.6 of their radii; a sound crystal is near 1) and {n_nb} are slabs or sparse cells "
                   f"(an empty layer over 6 Å or a packing fraction under 0.12, lines that 98.7% of the 45,229 known MP-20 crystals meet): all are set aside, and the accepted "
                   f"structures and every calibration number come from the {f_['relaxed']} that remain.",
                   f"Relaxation moves the cells away from what the judge expected: on the same {acc_['same_cells']} cells its error against the request is "
                   f"{acc_['mae_same_cells_before_relaxation']:.2f} eV before relaxation and {acc_['mae_relaxed_cells']:.2f} eV after.",
                   "A known formula counts as rediscovered only when its relaxed cell matches an MP-20 entry of that formula (StructureMatcher, every entry compared).",
                   "No hull energy is computed: nothing here is called stable.", "Coordinate accuracy (RMSE 0.24) is the open defect; a Wyckoff-letter head is the identified fix."],
        "files": files, "sources": ["eval/results/d1_pool", "eval/results/d1_consensus", "eval/results/d1_relaxed", "eval/results/d1_relaxed_bulk", "eval/results/d1_instrument_bulk", "journal entries 53–64, 70, 71"],
    }
    write_json(os.path.join(sd, "study.json"), scrub_paths(finite(study)))
    return {"id": "mp20", "verdicts": {k: v["grade"] for k, v in verdicts.items()}}


# ───────────────────────── checkpoints manifest ─────────────────────────
# ───────────────────────── JARVIS double perovskites (an independent user's journey) ─────────────────────────
DP_ROUTES = [  # run folder, id, title, how it proposes candidates
    ("06_screen_halide", "screen-halide", "Screening, halide variant",
     "Every composition of the halide double-perovskite family on its prototype cell, labelled by the family model; the best per target kept."),
    ("06_screen_halide_nontoxic", "screen-halide-nontoxic", "Screening, halide, without Tl Pb Cd Hg As Be",
     "The same screening without the elements a practical shortlist excludes."),
    ("06_screen_oxide", "screen-oxide", "Screening, oxide variant", "The oxide variant of the same family, screened the same way."),
    ("07_family/check", "family-generation", "Family generation",
     "meidnet generate with the family model: compositions decoded inside the family, then built on its prototype cell."),
    ("08_routeA/routeA", "family-free", "Family-free generation",
     "The symmetry decoder proposes cells of any composition (generate_to_target), although S0 had said screening."),
]
DP_GAP = "Band_gap_OptB88vdW_eV"


def build_jarvis_dp(a, out: str) -> dict:
    """The double-perovskite study from the run of the published packages (meidnet_data/jarvis_dp/retest_pypi): the
    independent user's data (public JARVIS-DFT), the two models they trained, every route through the same check."""
    from meidnet_eval import stages
    from pymatgen.core import Composition, Structure
    D = os.path.join(a.data, "jarvis_dp"); W = os.path.join(D, "retest_pypi")
    sd = os.path.join(out, "studies", "jarvis-dp"); files = {}
    audit = json.load(open(os.path.join(W, "02_intake", "audit.json")))
    prev = json.load(open(os.path.join(W, "03_preview", "preview.json")))
    sc = json.load(open(os.path.join(W, "05_scorecard", "scorecard.json")))
    judge = sc.get("judge") or {}
    # the data's own gaps, by reduced formula, over every split of the intake the models were trained on
    known = {}
    for split in ("train", "val", "test"):
        t = pd.read_csv(os.path.join(D, "tester_intake", f"{split}.csv"), usecols=["formula", DP_GAP])
        for f, g in zip(t["formula"], t[DP_GAP]):
            known.setdefault(Composition(f).reduced_formula, []).append(round(float(g), 3))
    verdicts = {"S0": {"grade": prev["verdict"], "note": f"{prev['values']['density']:.1f} compositions per element (rule 200): {prev['mode']}; "
                                                         f"family conformance {prev['values']['family_conformance']:.2f}"}}
    for blk, rep in sc["report"]["main"].items():
        verdicts[blk] = {"grade": rep["verdict"], "note": "; ".join(f"{m['metric']} {m['value']:.3g} {m['unit']}" for m in rep.get("metrics", [])[:2]
                                                                   if m.get("value") is not None)}
    routes, accepted, seen, pooled = [], [], set(), {"judge_err": [], "candidates": 0, "consensus": 0, "assessed": 0, "stable": 0}
    stability = None
    for folder, rid, title, how in DP_ROUTES:
        R = os.path.join(W, folder)
        rep = json.load(open(os.path.join(R, "report.json")))
        st = rep["stages"]
        funnel = []
        if os.path.exists(os.path.join(R, "summary.json")):                     # screening: the enumeration before the shortlist
            sm = json.load(open(os.path.join(R, "summary.json")))
            funnel.append(["compositions enumerated", int(sm["enumerated"])])
        funnel += [["candidates", st["1_candidates"]], ["both models in the window", st["2_two_model_consensus"]],
                   ["relaxed, still a crystal", st.get("3_relaxed", 0)], ["both again on the relaxed cell", st.get("4_consensus_after_relaxation", 0)]]
        h = rep.get("hull") or {}
        if stability is None and h.get("validation"):
            v = h["validation"]
            stability = {"potential": "TensorNet" if h.get("potential") == "tensornet" else h.get("potential"), "reference": "JARVIS-DFT 3D (12-12-2022)",
                         "n": v["n"], "mae_eV": v["mae_eV"], "median_abs_error_eV": v["median_abs_error_eV"], "agreement": v["agreement_within_stable_line"],
                         "spearman": v.get("spearman"), "outliers": [o.split(" (")[0] for o in v.get("reference_outliers", [])],
                         "mae_without_outliers": v.get("mae_eV_without_outliers"), "spearman_without_outliers": v.get("spearman_without_outliers"),
                         "agreement_without_outliers": v.get("agreement_without_outliers")}
        routes.append({"id": rid, "title": title, "how": how, "funnel": funnel, "classes": rep.get("classes", {}),
                       "collapsed": [{"formula": c["formula"], "target": c["target"], "contact_ratio": c["contact_ratio"]} for c in rep.get("collapsed_on_relaxation", [])],
                       "stable_share": h.get("stable_share"), "not_assessed": int(h.get("not_assessed", 0))})
        pooled["candidates"] += st["1_candidates"]; pooled["consensus"] += st["2_two_model_consensus"]
        rel = os.path.join(R, "relaxed")
        rcal = json.load(open(os.path.join(rel, "calibration.json")))["per_candidate"] if os.path.exists(os.path.join(rel, "calibration.json")) else {}
        rtab = pd.read_csv(os.path.join(rel, "candidates.csv")) if os.path.exists(os.path.join(rel, "candidates.csv")) else pd.DataFrame()
        for _, r in rtab.iterrows():
            jg = rcal.get(r["file"], {}).get("independent_gap")
            if jg is not None:
                pooled["judge_err"].append(abs(float(jg) - float(r["target"])))
            if "e_hull" in r and r["e_hull"] == r["e_hull"] and bool(r.get("e_hull_assessed", True)):
                pooled["assessed"] += 1; pooled["stable"] += int(float(r["e_hull"]) <= 0.1)
        cons = pd.read_csv(os.path.join(rel, "candidates_consensus.csv")) if os.path.exists(os.path.join(rel, "candidates_consensus.csv")) else pd.DataFrame()
        mlip = {os.path.basename(m["file"]): m for f in sorted(glob.glob(os.path.join(R, "relax", "mlip_shard*.json"))) for m in json.load(open(f))}
        for x in rep.get("final", []):
            k = Composition(x["formula"]).reduced_formula
            if k in seen:
                continue
            seen.add(k)
            row = cons[(cons["formula"] == x["formula"]) & (abs(cons["target"] - x["target"]) < 1e-9)].iloc[0]
            src = os.path.join(rel, row["file"])
            shown = x["formula"]                                          # as the pipeline wrote it (A2BB'X6 order)
            name = f"accepted/{shown}_{rid}.cif"
            copy_file(src, sd, name, files, "chemical/x-cif")
            stc = Structure.from_file(src)
            m = mlip.get(os.path.basename(row["file"]), {})
            gaps = known.get(k) or ([round(float(row["reference_gap"]), 3)] if "reference_gap" in row and row["reference_gap"] == row["reference_gap"] else [])
            note = x.get("e_hull_note") or ""
            accepted.append({
                "requested": float(x["target"]), "formula": shown, "label_structure_gap": round(float(x["label"]), 3), "judge_gap": round(float(x["judge"]), 3),
                "amd_nearest": None if x.get("amd_nearest") is None else round(float(x["amd_nearest"]), 3), "known_formula": k in known,
                "recorded_gaps": sorted(gaps), "class": x["cls"], "charge_balanced": x.get("charge_balanced"),
                "relaxation_drop_eV_atom": m.get("tensornet_drop_per_atom"), "spacegroup_designed": m.get("spacegroup_designed"),
                "spacegroup_relaxed": m.get("tensornet_spacegroup_relaxed"), "natoms": len(stc), "file": name,
                "structure": {"lattice": [[round(float(v), 4) for v in row_] for row_ in stc.lattice.matrix],
                              "sites": [{"element": str(site.specie.symbol), "frac": [round(float(v), 4) for v in site.frac_coords]} for site in stc]},
                "flag": "judges disagree" if abs(float(x["label"]) - float(x["judge"])) > 0.5 else "",
                "route": title, "e_hull": None if x.get("e_hull") is None or x["e_hull"] != x["e_hull"] else round(float(x["e_hull"]), 4),
                "e_hull_note": note, "reference_id": x.get("reference_id")})
    accepted.sort(key=lambda r: (r["requested"], r["formula"]))
    classes = {}
    for r in accepted:
        classes[r["class"]] = classes.get(r["class"], 0) + 1
    measured = {"S6": {"judge_mae_request": float(np.mean(pooled["judge_err"])), "consensus_yield": pooled["consensus"] / max(1, pooled["candidates"])},
                "S7": {"stable_share": pooled["stable"] / max(1, pooled["assessed"])}}
    for blk, vals in measured.items():
        g, _ = stages.BY_ID[blk].verdict(vals)
        verdicts[blk] = {"grade": g, "note": "; ".join(f"{k.replace('_', ' ')} {v:.2f}" for k, v in vals.items()) + " (all routes, relaxed cells)"}
    new = [r for r in accepted if r["class"].startswith("new composition")]
    dp_re = re.compile(r"^[A-Z][a-z]?2[A-Z][a-z]?[A-Z][a-z]?[A-Z][a-z]?6$")
    new_dp = [r for r in new if dp_re.match(r["formula"])]
    stable_dp = [r for r in new_dp if r["e_hull"] is not None and r["e_hull"] <= 0.1 and not r["e_hull_note"]]
    xc_path = os.path.join(D, "crosscheck.json")                      # written and verified by hand: other databases, Prism scoring
    cross = json.load(open(xc_path))["lines"] if os.path.exists(xc_path) else []
    tab = pd.DataFrame([{k: v for k, v in r.items() if k not in ("structure",)} for r in accepted])
    os.makedirs(os.path.join(sd, "files"), exist_ok=True)
    tab.to_csv(os.path.join(sd, "files", "accepted.csv"), index=False)
    files["accepted.csv"] = {"bytes": os.path.getsize(os.path.join(sd, "files", "accepted.csv")), "sha256": sha256_file(os.path.join(sd, "files", "accepted.csv")), "media": "text/csv"}
    hv = os.path.join(W, DP_ROUTES[0][0], "relaxed", "hull_validation.csv")
    if os.path.exists(hv):
        copy_file(hv, sd, "hull_validation.csv", files, "text/csv")
    study = {
        "schema": "meidnet-matter/study/1", "id": "jarvis-dp", "title": "Double perovskites from public JARVIS-DFT data", "order": 5,
        "dataset": {"name": "JARVIS-DFT double perovskites", "rows": audit["rows"], "train": audit["split_sizes"]["train"], "val": audit["split_sizes"]["val"],
                    "test": audit["split_sizes"]["test"], "elements": audit["elements"], "prototypes": audit["prototypes"],
                    "compositions_per_element": finite(prev["values"]["density"]), "family_conformance": finite(prev["values"]["family_conformance"]),
                    "zero_share": finite(prev["values"]["zero_share"]),
                    "source": "JARVIS-DFT 3D (release 12-12-2022), A₂BB′X₆ compounds after a structural filter; chosen, prepared and modelled by an independent user who followed the Method page",
                    "properties": ["band gap (OptB88vdW)", "formation energy", "energy above the hull"]},
        "mode": "screening (as S0 said), with family and family-free generation beside it",
        "headline": (f"An independent user's journey on public data: S0 said screen, not generate, and the trained decoder agreed. Screening and family generation "
                     f"returned {len(new_dp)} A₂BB′X₆ compositions absent from the data and from JARVIS-DFT inside the requested gap window, "
                     f"{len(stable_dp)} of them within 0.1 eV/atom of the hull with one potential for every phase."),
        "verdicts": verdicts,
        "target_following": {"targets_eV": [1.0, 2.0, 3.0], "window_eV": 0.5,
                             "judge": (f"{judge['name']}, qualified on the test split: MAE {judge['mae_all']:.2f} eV ({judge['mae_nonzero']:.2f} on non-zero gaps), "
                                       f"{judge.get('corr_name', 'Spearman')} {judge['corr']:.2f} (n = {judge['n']})") if judge else None,
                             "routes": len(routes), "accepted": len(accepted), "new_compositions": len(new), "new_double_perovskites": len(new_dp),
                             "installed_from": "PyPI (meidnet-matter 0.6.1) and the release's engine wheel, in a fresh environment"},
        "routes": routes, "stability": stability, "accepted": accepted, "accepted_classes": classes, "window_eV": 0.5, "cross_checks": cross,
        "lessons": ["S0 predicted screening before any training (48.5 compositions per element against a rule of 200); the trained decoder confirmed it (S3).",
                    "A known compound's own DFT value outranks two machine-learned readings: Rb₂InSbCl₆ and Rb₂InSbI₆ are in the data at 0.58 and 0.00 eV, and both models were wrong about them.",
                    "Collapsed cells: some relaxed cells had atoms pushed into each other (Te–Te 1.2 Å); the check now sets aside any cell whose closest atoms sit nearer than 0.6 of their radii.",
                    "A reference set can be incomplete: JARVIS-DFT holds no cesium halide, so Cs₂InFeBr₆ came out far below every known phase; such a value is now reported as not assessed, with the missing element pairs named.",
                    "The whole journey ran from the published packages in a fresh environment."],
        "checkpoints": [],
        "reproduce": [{"step": "install", "command": "pip install --extra-index-url https://download.pytorch.org/whl/cpu \"meidnet-matter[judge]\""},
                      {"step": "one table from a folder of structures and a spreadsheet", "command": "python -m meidnet_eval.ingest_upload structures/ properties.xlsx data/ --props \"Band gap OptB88vdW\" \"E above hull\" --id-col \"JARVIS id\""},
                      {"step": "intake and S0", "command": "python -m meidnet_eval.intake data/table.csv data/intake --id material_id --cif cif --props Band_gap_OptB88vdW_eV E_above_hull_eV_atom && python -m meidnet_eval.preview data/intake --gap Band_gap_OptB88vdW_eV --targets 1 2 3 --stability E_above_hull_eV_atom --family double_perovskite_a2bbx6"},
                      {"step": "train, then the scorecard with S8", "command": "meidnet train meidnet.yaml && python -m meidnet_eval.scorecard data/intake --models mine=out/model.pt --gap Band_gap_OptB88vdW_eV --judge megnet --out scorecard/"},
                      {"step": "screen with the full check and the hull", "command": "python -m meidnet_eval.screen_local data/intake --ckpt out/model.pt --family double_perovskite_a2bbx6:halide --gap Band_gap_OptB88vdW_eV --targets 1 2 3 --check --hull-reference jarvis:jdft_3d-12-12-2022.json --stability-col E_above_hull_eV_atom --out screening/"}],
        "limits": ["The judge (MEGNet, fidelity 0) qualifies on this data at 0.50 of the gap spread, the edge of its band; its error, 0.82 eV, is wider than the ±0.5 eV window, so agreement of the two models supports a candidate without proving it.",
                   "Stability is the energy above the hull from one machine-learning potential (TensorNet) for every phase, calibrated on known materials of the data; it is a screen, not a DFT result.",
                   "Cs₂InFeBr₆: the reference set has no cesium halide, so its stability is not assessed; the Materials Project reference (--hull-reference mp) would give it.",
                   "The iron compounds' gaps depend on magnetism and on the functional; the data's OptB88vdW gaps are the reference here.",
                   "Thallium compounds are toxic; the screening without Tl, Pb, Cd, Hg, As and Be is the practical shortlist.",
                   "No new composition has been checked by DFT yet: that is the next step for any of them.",
                   "The two models were trained by the independent user (200 epochs each) and are not published; the Method page's commands train the same ones."],
        "files": files, "sources": ["meidnet_data/jarvis_dp/retest_pypi (the run of the published packages)", "the independent user's package (journey and feedback)", "journal entries 68–70"],
    }
    write_json(os.path.join(sd, "study.json"), scrub_paths(finite(study)))
    return {"id": "jarvis-dp", "verdicts": {k: v["grade"] for k, v in verdicts.items()}}


def build_manifest(a) -> None:
    entries = []
    for c in CHECKPOINTS:
        path = os.path.join(a.checkpoints, c["file"])
        e = dict(c)
        e.setdefault("config", f"configs/{os.path.splitext(c['file'])[0]}.yaml" if c["file"].endswith(".pt") else None)
        e["urls"] = c.get("urls") or [GITHUB_ASSET.format(release=RELEASE, file=c["file"]), SPACE_FILE.format(file=c["file"])]
        if os.path.exists(path):
            e["sha256"], e["bytes"] = sha256_file(path), os.path.getsize(path)
        elif c.get("ship"):
            raise SystemExit(f"{path} is marked for shipping but is not in --checkpoints {a.checkpoints}")
        else:
            e["sha256"], e["bytes"] = None, None
        if e["config"] and os.path.exists(os.path.join(a.checkpoints, e["config"])):
            import yaml
            cfg = yaml.safe_load(open(os.path.join(a.checkpoints, e["config"])))
            e["properties"] = [p["column"] for p in cfg.get("data", {}).get("properties", [])]
            e["max_sites"] = cfg.get("data", {}).get("max_sites")
            e["geometry"] = cfg.get("model", {}).get("decoder_geometry", "free")
            e["epochs"] = cfg.get("training", {}).get("epochs"); e["seed"] = cfg.get("training", {}).get("seed")
            e["element_features"] = cfg.get("model", {}).get("element_features")
        entries.append(e)
    for j in JUDGES:
        e = dict(j); e["files"] = [{"file": f, "sha256": sha256_file(os.path.join(a.checkpoints, f)) if os.path.exists(os.path.join(a.checkpoints, f)) else None,
                                   "bytes": os.path.getsize(os.path.join(a.checkpoints, f)) if os.path.exists(os.path.join(a.checkpoints, f)) else None,
                                   "urls": [GITHUB_ASSET.format(release=RELEASE, file=os.path.basename(f))]} for f in j["files"]]
        entries.append(e)
    write_json(a.manifest, {"schema": "meidnet-matter/checkpoints/1", "release": RELEASE, "checkpoints": entries})


BUILDERS = {"perov5": build_perov5, "mp-perovskites": build_mp_perovskites, "user-246": build_user246, "mp20": build_mp20,
            "jarvis-dp": build_jarvis_dp}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", required=True); ap.add_argument("--journey", required=True); ap.add_argument("--data", required=True)
    ap.add_argument("--checkpoints", default=os.path.join(ROOT, "checkpoints"))
    ap.add_argument("--out", default=os.path.join(ROOT, "examples", "research"))
    ap.add_argument("--manifest", default=os.path.join(ROOT, "checkpoints", "manifest.json"))
    ap.add_argument("--reference-sample", type=int, default=4000)
    ap.add_argument("--only", choices=list(BUILDERS), default=None,
                    help="rebuild one study (and the listings) and keep the others as they are; the full build takes ~10 min")
    a = ap.parse_args()
    if a.only:
        old = json.load(open(os.path.join(a.out, "pipeline", "blocks.json")))
        shutil.rmtree(os.path.join(a.out, "studies", a.only), ignore_errors=True)
        r = BUILDERS[a.only](a, a.out)
        verdicts = {k: v for k, v in (old.get("dataset_verdicts") or {}).items()}
        verdicts[r["id"]] = r["verdicts"]
    else:
        if os.path.isdir(a.out):
            shutil.rmtree(a.out)
        results = [b(a, a.out) for b in BUILDERS.values()]
        verdicts = {r["id"]: r["verdicts"] for r in results}
    build_blocks(a, a.out, verdicts)
    index = []
    for sid in BUILDERS:
        s = json.load(open(os.path.join(a.out, "studies", sid, "study.json")))
        index.append({"id": sid, "title": s["title"], "dataset": s["dataset"]["name"], "mode": s["mode"], "headline": s["headline"], "order": s["order"]})
    write_json(os.path.join(a.out, "studies", "index.json"), {"schema": "meidnet-matter/studies/1", "studies": index})
    build_manifest(a)
    text = "".join(open(p, encoding="utf-8").read() for p in glob.glob(os.path.join(a.out, "**", "*.json"), recursive=True))
    assert not re.search(r"honest", text, re.I), "a forbidden word reached the artefacts"
    total = sum(os.path.getsize(p) for p in glob.glob(os.path.join(a.out, "**", "*"), recursive=True) if os.path.isfile(p))
    bad = []
    for d, _, fs in os.walk(a.out):
        for f in fs:
            if f.endswith((".json", ".csv", ".md", ".txt", ".cif")):
                txt = open(os.path.join(d, f), encoding="utf-8", errors="replace").read()
                if "/gpfs/" in txt or re.search(r"\bhonest\b", txt, re.I):
                    bad.append(os.path.relpath(os.path.join(d, f), a.out))
    if bad:
        raise SystemExit("machine paths or excluded wording in: " + ", ".join(bad))
    print(f"research artefacts: {total / 1e6:.2f} MB in {a.out}; manifest: {a.manifest}")


if __name__ == "__main__":
    main()
