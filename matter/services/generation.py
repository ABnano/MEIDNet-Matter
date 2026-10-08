"""Generation jobs: a band-gap request in, structures with two judgements out, as a background thread.

    <RUN_ROOT>/generate/<job_id>/
      job.json          the record (request, model, judge, progress, log tail, funnel, candidates, provenance)
      candidates.csv    one row per candidate
      cifs/             the generated cells
      RELAX.md          the command that relaxes them locally (not run on this server)

The loop itself is `meidnet_eval.conditional_generate.generate_pool`, the same code the research runs used, called
in-process with progress and stop callbacks.  Public hosts cap the request (see GEN_PUBLIC_LIMITS) and keep the
JobManager's rule of one running job per session.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import secrets
import time
import traceback

import numpy as np

from matter.api.errors import ApiError
from matter.jsonsafe import finite
from matter.schemas.generation import GENERATION_SCHEMA_ID, GenerateRequest
from matter.services.runs import LOG_TAIL, RunStore, now_iso
from matter.version import build_info

GEN_PUBLIC_LIMITS = {"targets": 3, "per_target": 10, "oversample": 40, "window_min": 0.25, "window_max": 1.0, "seconds": 480,
                     "exclude_elements": 30}
TARGET_RANGE = (0.05, 6.0)
RELAX_COMMAND = ("python -m meidnet_eval.d1_mlip_check . --cifs-dir . --steps 150 --potentials tensornet chgnet   "
                 "# relaxes every cell with two potentials (needs matgl + ase); then re-run the judges on relaxed_tensornet/")


def validate_request(body: GenerateRequest, public: bool, catalog) -> tuple[dict, list[str]]:
    """Clamp a request to the host's limits, noting every clamp, and check the elements and the model."""
    from meidnet.chem import ELEMENT_INDEX
    req = body.model_dump()
    notes = []
    lim = GEN_PUBLIC_LIMITS
    if public:
        if len(req["targets"]) > lim["targets"]:
            req["targets"] = req["targets"][: lim["targets"]]; notes.append(f"at most {lim['targets']} targets on this shared server")
        if req["per_target"] > lim["per_target"]:
            req["per_target"] = lim["per_target"]; notes.append(f"at most {lim['per_target']} structures per target on this shared server")
        if req["oversample"] > lim["oversample"]:
            req["oversample"] = lim["oversample"]; notes.append(f"oversampling capped at {lim['oversample']}")
        if req["window_eV"] < lim["window_min"] or req["window_eV"] > lim["window_max"]:
            req["window_eV"] = min(max(req["window_eV"], lim["window_min"]), lim["window_max"])
            notes.append(f"window kept between {lim['window_min']} and {lim['window_max']} eV")
        if len(req["exclude_elements"]) > lim["exclude_elements"]:
            raise ApiError("validation_error", f"at most {lim['exclude_elements']} excluded elements", status=422)
    bad = [e for e in req["exclude_elements"] if e not in ELEMENT_INDEX]
    if bad:
        raise ApiError("validation_error", f"unknown element symbol(s): {', '.join(bad)}", status=422,
                       fields=[{"loc": "exclude_elements", "msg": "unknown element symbol"}])
    out_of_range = [t for t in req["targets"] if not (TARGET_RANGE[0] <= t <= TARGET_RANGE[1])]
    if out_of_range:
        raise ApiError("validation_error", f"targets must lie between {TARGET_RANGE[0]} and {TARGET_RANGE[1]} eV", status=422,
                       fields=[{"loc": "targets", "msg": "out of range"}])
    entry = catalog.entry(req["model_id"])
    if entry.get("geometry") != "wyckoff":
        raise ApiError("validation_error", f"{req['model_id']} has no symmetry decoder; choose a checkpoint with geometry 'wyckoff'",
                       status=422, fields=[{"loc": "model_id", "msg": "needs a symmetry decoder"}])
    if "band_gap" not in (entry.get("properties") or ["band_gap"]):
        raise ApiError("validation_error", f"{req['model_id']} does not predict band_gap", status=422)
    if any(t > 3.0 for t in req["targets"]):
        notes.append("above 3 eV the generator saturates on MP-20: expect few or no accepted structures")
    return req, notes


class GenerationStore(RunStore):
    """The RunStore's persistence (atomic saves, scan, cleanup, locks) with generation records."""

    def create(self, session_id: str, request: dict, notes: list[str], model_info: dict, judge_info: dict, estimated_seconds: int) -> dict:  # type: ignore[override]
        job_id = "gen-" + secrets.token_urlsafe(9)
        job = {"schema": GENERATION_SCHEMA_ID, "job_id": job_id, "run_id": job_id, "session_id": session_id, "status": "queued",
               "created": now_iso(), "created_ts": time.time(), "last_access": time.time(), "started": None, "finished": None, "error": None,
               "request": request, "notes": notes, "limits": GEN_PUBLIC_LIMITS if self.public else None, "estimated_seconds": estimated_seconds,
               "model": model_info, "judge": judge_info,
               "progress": {"target_index": 0, "targets": len(request["targets"]), "attempts": 0, "kept": 0, "phase": "queued", "seconds": 0.0},
               "log": [], "funnel": None, "rejected": None, "per_target": None, "candidates": [], "relax_command": RELAX_COMMAND,
               "provenance": None}
        with self.lock:
            self.runs[job_id] = job
            self.locks[job_id] = threading_lock()
        self.save(job)
        return job

    def list(self, session_id: str | None) -> list[dict]:  # type: ignore[override]
        jobs = [r for r in self.runs.values() if session_id is None or r.get("session_id") == session_id]
        return [summary(j) for j in sorted(jobs, key=lambda r: r["created"], reverse=True)]


def threading_lock():
    import threading
    return threading.Lock()


def summary(job: dict) -> dict:
    return {k: job.get(k) for k in ("job_id", "status", "created", "started", "finished", "error", "request", "notes", "limits",
                                    "estimated_seconds", "progress")} | {"n_candidates": len(job.get("candidates", [])),
                                                                         "n_consensus": sum(1 for c in job.get("candidates", []) if c.get("consensus"))}


def status_view(job: dict) -> dict:
    return summary(job) | {"log": job.get("log", [])[-80:], "candidates": job.get("candidates", []), "funnel": job.get("funnel"),
                           "per_target": job.get("per_target"), "judge": job.get("judge"), "model": job.get("model"),
                           "relax_command": job.get("relax_command")}


class Reference:
    """Support data for the evidence columns: known formulas of the training set and a reference set of AMD vectors."""

    def __init__(self, research_dir: str):
        base = os.path.join(research_dir, "support", "mp20")
        self.known: dict = {}
        self.amd = None
        p = os.path.join(base, "known_formulas.json.gz")
        if os.path.isfile(p):
            with gzip.open(p, "rt", encoding="utf-8") as f:
                self.known = json.load(f)
        p = os.path.join(base, "reference_amd.npz")
        if os.path.isfile(p):
            self.amd = np.load(p)["amd"].astype(np.float32)

    def nearest_amd(self, vec) -> float | None:
        if self.amd is None or vec is None:
            return None
        d = np.abs(self.amd - np.asarray(vec, dtype=np.float32)[None, :]).max(axis=1)
        return float(d.min())


def execute_generation(job_obj, job: dict, services) -> None:
    """The thread body: generate, label from the returned structure, judge independently, attach the evidence."""
    from pymatgen.core import Composition, Structure
    from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
    from meidnet.chem import ELEMENT_INDEX, ELEMENTS
    from meidnet.data import ANION_ELEMENTS
    from meidnet_eval.conditional_generate import generate_pool
    from meidnet_eval.metrics_sun import amd as amd_vector

    store = services.generations
    lock = store.lock_of(job["job_id"])
    job_dir = store.path(job["job_id"])
    req = job["request"]
    t0 = time.time()

    def log(*a):
        msg = " ".join(str(x) for x in a)
        with lock:
            job["log"].append(msg)
            if len(job["log"]) > LOG_TAIL:
                del job["log"][: len(job["log"]) - LOG_TAIL]

    def on_progress(p):
        with lock:
            job["progress"].update({k: p[k] for k in ("target_index", "attempts", "kept", "phase") if k in p})
            job["progress"]["seconds"] = round(time.time() - t0, 1)
        store.save(job)

    try:
        with lock:
            job["status"], job["started"] = "running", now_iso(); job["progress"]["phase"] = "loading model"
        store.save(job)
        lm = services.catalog.load(req["model_id"])
        import torch
        mask = torch.ones(len(ELEMENTS), dtype=torch.bool)
        for e in req["exclude_elements"]:
            mask[ELEMENT_INDEX[e]] = False
        anions = list(ANION_ELEMENTS) if req["require_anion"] else None
        rows, rejected = generate_pool(lm, "band_gap", req["targets"], per_target=req["per_target"], oversample=req["oversample"],
                                       sigma=0.3, seed=req["seed"], steps=0, geometry="wyckoff", species_mask=mask, anions=anions,
                                       min_orbits=2, max_atoms=lm.model.max_sites, label_source="structure", target_window=req["window_eV"],
                                       cifs_dir=os.path.join(job_dir, "cifs"), tag=job["job_id"], on_progress=on_progress,
                                       should_stop=lambda: services.jobs.should_stop(job_obj, log), log=log)
        with lock:                                   # the engine reports every ten draws; the final counts are set here
            job["progress"].update({"phase": "judging", "attempts": sum(rejected.values()) + len(rows), "kept": len(rows),
                                    "target_index": max(0, len(req["targets"]) - 1), "seconds": round(time.time() - t0, 1)})
        store.save(job)
        structs = [Structure.from_file(os.path.join(job_dir, r["file"])) for r in rows]
        judged = services.judge.gaps(structs) if rows else []
        ref = services.reference
        cands = []
        for i, (r, s, g) in enumerate(zip(rows, structs, judged), start=1):
            label = float(r["label_gap"]) if r.get("label_gap") == r.get("label_gap") else None
            t = float(r["target"])
            in_label = label is not None and abs(label - t) <= req["window_eV"]
            in_judge = g is not None and abs(g - t) <= req["window_eV"]
            metal = None if g is None else bool(g < 0.1)
            consensus = bool(in_label and in_judge and not (t > 0 and metal))
            try:
                balanced = bool(Composition(r["formula"]).oxi_state_guesses(max_sites=-1))
            except Exception:
                balanced = None
            try:
                vec = amd_vector(s, 10); near = ref.nearest_amd(vec)
            except Exception:
                near = None
            try:
                sg = int(SpacegroupAnalyzer(s, symprec=0.1).get_space_group_number())
            except Exception:
                sg = int(r.get("spacegroup") or 0)
            with open(os.path.join(job_dir, r["file"]), "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
            known = (r["formula"] in ref.known) if ref.known else None
            cands.append({"candidate_id": f"{job['job_id']}-{i:03d}", "target_eV": t, "formula": r["formula"], "natoms": int(r["natoms"]),
                          "n_orbits": int(r.get("n_orbits") or 0), "spacegroup": sg,
                          "label_structure_eV": None if label is None else round(label, 3),
                          "label_formation_energy_eV_atom": round(float(r["label_dhf"]), 3) if r.get("label_dhf") == r.get("label_dhf") else None,
                          "judge_eV": None if g is None else round(float(g), 3), "within_window": {"label": in_label, "judge": in_judge},
                          "metal_by_judge": metal, "consensus": consensus, "charge_balanced": balanced, "known_formula": known,
                          "recorded_gaps_eV": ref.known.get(r["formula"], []) if ref.known else [],
                          "amd_nearest_reference": None if near is None else round(near, 3),
                          "novel_by_amd": None if near is None else bool(near > 0.3),
                          "lattice": {k: round(float(v), 3) for k, v in zip(("a", "b", "c", "alpha", "beta", "gamma"), (*s.lattice.abc, *s.lattice.angles))},
                          "volume_per_atom": round(float(s.volume / len(s)), 2), "file": r["file"], "sha256": digest,
                          "evidence": {"label": "read from the returned structure by the model's own property head",
                                       "judge": services.judge.describe()["name"] if g is not None else "independent judge unavailable",
                                       "novelty": "AMD distance to the nearest of the reference training structures; new above 0.3",
                                       "stability": "not assessed on this server"},
                          "stability": {"status": "not assessed", "note": "relax locally with the command in relax_command"}})
        per_target = []
        for t in req["targets"]:
            cs = [c for c in cands if c["target_eV"] == t]
            per_target.append({"requested": t, "kept": len(cs), "consensus": sum(1 for c in cs if c["consensus"]),
                               "label_mean_eV": round(float(np.mean([c["label_structure_eV"] for c in cs if c["label_structure_eV"] is not None])), 3) if cs else None,
                               "judge_mean_eV": round(float(np.mean([c["judge_eV"] for c in cs if c["judge_eV"] is not None])), 3) if any(c["judge_eV"] is not None for c in cs) else None})
        info = build_info(services.settings.build_info, services.settings.public)
        entry = services.catalog.entry(req["model_id"])
        with lock:
            job["candidates"] = cands
            job["funnel"] = {"attempted": sum(rejected.values()) + len(rows), "kept": len(rows), "judged": sum(1 for g in judged if g is not None),
                             "consensus": sum(1 for c in cands if c["consensus"])}
            job["rejected"] = rejected
            job["per_target"] = per_target
            job["judge"] = services.judge.describe()
            job["provenance"] = {"matter_version": info["matter"], "meidnet_version": info["meidnet"], "git_commit": info["git_sha"],
                                 "model_sha256": entry.get("sha256"), "judge_weights": services.judge.describe()["weights"], "space_id": info.get("space_id")}
            job["progress"]["phase"] = "done"; job["progress"]["seconds"] = round(time.time() - t0, 1)
        write_tables(job_dir, job)
        final = "stopped" if job_obj.stop_flag else "done"
        with lock:
            job["finished"], job["status"] = now_iso(), final
        store.save(job)
    except Exception as e:
        with lock:
            job["status"], job["finished"] = "error", now_iso()
            job["error"] = "the generation failed" if services.settings.public else "".join(traceback.format_exception(type(e), e, e.__traceback__))
        store.save(job)
    except SystemExit as e:
        with lock:
            job["status"], job["finished"], job["error"] = "error", now_iso(), str(e.code if e.code is not None else e)
        store.save(job)


def write_tables(job_dir: str, job: dict) -> None:
    import csv
    cols = ["candidate_id", "target_eV", "formula", "natoms", "spacegroup", "label_structure_eV", "label_formation_energy_eV_atom", "judge_eV",
            "consensus", "metal_by_judge", "charge_balanced", "known_formula", "amd_nearest_reference", "novel_by_amd", "volume_per_atom", "file", "sha256"]
    with open(os.path.join(job_dir, "candidates.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for c in job["candidates"]:
            w.writerow(c)
    with open(os.path.join(job_dir, "RELAX.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# Relax these cells locally\n\nThe server does not run relaxation. From this folder:\n\n    " + job["relax_command"] +
                "\n\nThen re-run both judges on `relaxed_tensornet/` (target_calibration.py --judge reencode / --judge megnet) before "
                "quoting a band gap for the relaxed structure.\n")
    with open(os.path.join(job_dir, "job.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(finite(job), f, indent=1, allow_nan=False, ensure_ascii=False)
