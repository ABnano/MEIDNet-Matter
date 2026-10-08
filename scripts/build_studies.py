"""Build the research artefacts the application serves: the pipeline blocks, the four studies, the checkpoint manifest
and the support files the live generator needs.  Deterministic: the same inputs give byte-identical outputs.

    python scripts/build_studies.py --fix <meidnet_fix> --journey <meidnet_journey> --data <meidnet_data> \
        --checkpoints checkpoints --out examples/research --manifest checkpoints/manifest.json

What is written
  examples/research/pipeline/blocks.json            the ten blocks, metrics, bands, components (from meidnet_eval.stages)
  examples/research/studies/index.json              the four studies in reading order
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
         description="The published Perov-5 model behind the demo project (Goal → Readiness → Candidates → Export).",
         urls=["https://github.com/ABnano/MEIDNet/raw/main/checkpoints/" + PEROV5_2K,
               "https://huggingface.co/Babu09/MEIDNet/resolve/main/checkpoints/" + PEROV5_2K]),
    dict(id="mp20-wyck", file="mp20_wyck.pt", dataset="mp20", study="mp20", role="generation", ship=True, loadable=True,
         description="MP-20, symmetry decoder (space group and symmetry-distinct sites), 100 epochs: the model behind the target-following result and the live generator."),
    dict(id="mp20-main", file="mp20_main.pt", dataset="mp20", study="mp20", role="baseline", ship=True, loadable=True,
         description="MP-20, free-coordinate decoder, 100 epochs: the baseline the symmetry decoder is compared with."),
    dict(id="desc-full", file="desc_full.pt", dataset="perov5", study="perov5", role="final", ship=True, loadable=True,
         description="Perov-5, the final configuration of round 1 (descriptors, structure-read labels, unit-sphere search)."),
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
    "S4": ("PASS", "label read from the returned cell; agrees with the independent judge within 0.5 eV for 19 of 22"),
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
def build_blocks(a, out: str, verdicts: dict) -> None:
    from meidnet_eval import stages
    payload = stages.export_blocks()
    payload["dataset_verdicts"] = verdicts
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
        "checkpoints": ["desc-full", "control", "perov5-2k", "desc-full-s1", "grounded", "prop-only", "recon-only", "cgcnn-p5"],
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


def classify(known: bool, amd):
    if known and amd is not None and amd < 0.3:
        return "rediscovered known structure"
    if known and amd is not None and amd < 0.35:
        return "rediscovered (borderline)"
    if known:
        return "new polymorph of known formula"
    return "new composition, new structure"


def build_mp20(a, out: str) -> dict:
    from meidnet_eval import stages
    from meidnet_eval.metrics_sun import amd as amd_vector
    R = os.path.join(a.fix, "eval", "results"); D = os.path.join(a.data, "mp20", "intake")
    sd = os.path.join(out, "studies", "mp20"); files = {}
    sup = os.path.join(out, "support", "mp20"); os.makedirs(sup, exist_ok=True)
    audit = json.load(open(os.path.join(D, "audit.json"))); prev = json.load(open(os.path.join(D, "preview.json")))
    inst = json.load(open(os.path.join(R, "d1_instrument", "instrument.json")))
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
    sun = pd.read_csv(os.path.join(R, "d1_relaxed", "sun_relaxed_strict_per_candidate.csv"))
    amd_by_formula = dict(zip(sun["formula"], sun["amd_nearest"]))
    accepted = []
    for _, r in rel.iterrows():
        c = rcal.get(r["file"], {}); lab, jud = c.get("reencoded_gap"), c.get("independent_gap")
        if lab is None or jud is None or not (abs(lab - r["target"]) <= 0.5 and abs(jud - r["target"]) <= 0.5) or (r["target"] > 0 and jud < 0.1):
            continue
        base = os.path.basename(r["file"]); m = ml.get(base, {}); d = amd_by_formula.get(r["formula"])
        d = None if d is None or d != d else float(d)
        is_known = r["formula"] in known
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
                         "recorded_gaps": known.get(r["formula"], []), "class": classify(is_known, d), "charge_balanced": balanced,
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
    verdicts = {}
    for blk, (grade, note) in MP20_VERDICT_NOTES.items():
        g = grade
        if blk in MP20_MEASURED:
            st = stages.BY_ID[blk]
            g2, _ = st.verdict(MP20_MEASURED[blk])
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
        "headline": "Requested band gap in, relaxed structures out: 13 accepted from 175 generated, 6 new compositions, and known compounds returned at their recorded gaps.",
        "verdicts": verdicts,
        "calibration": inst,
        "accepted": accepted, "accepted_classes": classes,
        "pool": {"generated": int(len(pool)), "both_judges_generated": int(inst["funnel"]["both_judges"]), "relaxed": int(inst["funnel"]["relaxed"]), "accepted": len(accepted)},
        "judge": finite(pool_cal["judge_qualification"]),
        "checkpoints": ["mp20-wyck", "mp20-main", "mp20-wyck-long", "mp20-wyck-bins"],
        "reproduce": [{"step": "one command", "command": "python -m meidnet_eval.generate_to_target --ckpt mp20_wyck.pt --intake <mp20 intake> --gap band_gap --targets 1.5 2.0 2.5 3.0 --per-target 25 --tag <tag>"},
                      {"step": "calibration", "command": "python -m meidnet_eval.instrument_sheet --pool <tag> --relaxed <tag>/relaxed --consensus <tag>/relax --out <tag>/instrument"}],
        "limits": ["Serviceable range 1–3 eV; above 3 eV the generator saturates.", "Resolution about 1 eV; precision ±0.7 eV per structure.",
                   "The generated cell is a starting point: relaxation lowers the energy by 1.3–8.7 eV/atom and moves atoms 1.4–2.3 Å; the relaxed cell is the product.",
                   "No hull energy is computed: nothing here is called stable.", "Coordinate accuracy (RMSE 0.24) is the open defect; a Wyckoff-letter head is the identified fix."],
        "files": files, "sources": ["eval/results/d1_pool", "eval/results/d1_consensus", "eval/results/d1_relaxed", "eval/results/d1_instrument", "journal entries 53–64"],
    }
    write_json(os.path.join(sd, "study.json"), scrub_paths(finite(study)))
    return {"id": "mp20", "verdicts": {k: v["grade"] for k, v in verdicts.items()}}


# ───────────────────────── checkpoints manifest ─────────────────────────
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", required=True); ap.add_argument("--journey", required=True); ap.add_argument("--data", required=True)
    ap.add_argument("--checkpoints", default=os.path.join(ROOT, "checkpoints"))
    ap.add_argument("--out", default=os.path.join(ROOT, "examples", "research"))
    ap.add_argument("--manifest", default=os.path.join(ROOT, "checkpoints", "manifest.json"))
    ap.add_argument("--reference-sample", type=int, default=4000)
    a = ap.parse_args()
    if os.path.isdir(a.out):
        shutil.rmtree(a.out)
    results = [build_perov5(a, a.out), build_mp_perovskites(a, a.out), build_user246(a, a.out), build_mp20(a, a.out)]
    verdicts = {r["id"]: r["verdicts"] for r in results}
    build_blocks(a, a.out, verdicts)
    index = []
    for sid in ("perov5", "mp-perovskites", "user-246", "mp20"):
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
