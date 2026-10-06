"""Runs: a search and everything it produced, on disk as one folder and in memory while it runs.

    <RUN_ROOT>/<run_id>/
      run.json          the Run (goal, settings, readiness snapshot, progress, log tail, funnel, candidates, manifest)
      config.yaml       the meidnet configuration that reproduces the engine part of the run
      metrics.json      funnel, rejections and timings per target
      readiness.json    the readiness report the run was started from
      candidates.csv    Matter's candidate table
      generation/       the engine's own output, untouched (cifs/, candidates.csv, generation.json)
      validation/       empty in Phase 0

The run id is unguessable and is the capability to read the run. Writes to run.json are atomic, so a crash keeps
what was found. On a shared host, finished runs of idle sessions are removed after an hour.
"""
from __future__ import annotations

import copy
import datetime as _dt
import json
import os
import secrets
import shutil
import threading
import time
import traceback

from matter.api.errors import ApiError
from matter.jsonsafe import finite
from matter.services import goals as G
from matter.services.enrichment import EvidenceContext, assign_clusters, enrich, funnel_for, rule_map
from matter.version import build_info

SESSION_TTL = 3600
LOG_TAIL = 400
STATUSES = ("queued", "running", "done", "stopped", "error", "interrupted")


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


class RunStore:
    def __init__(self, root: str, public: bool):
        self.root = root
        self.public = public
        self.runs: dict[str, dict] = {}
        self.locks: dict[str, threading.Lock] = {}
        self.lock = threading.Lock()
        os.makedirs(root, exist_ok=True)
        self.scan()

    # ── persistence ──
    def path(self, run_id: str) -> str:
        return os.path.join(self.root, run_id)

    def scan(self) -> None:
        """Load every run.json under the root; a run that was running when the server stopped is 'interrupted'."""
        for name in sorted(os.listdir(self.root)) if os.path.isdir(self.root) else []:
            p = os.path.join(self.root, name, "run.json")
            if not os.path.isfile(p):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    run = json.load(f)
            except (OSError, ValueError):
                continue
            if run.get("status") in ("queued", "running"):
                run["status"] = "interrupted"
                run["error"] = "the server stopped while this search was running"
            self.runs[run["run_id"]] = run
            self.locks[run["run_id"]] = threading.Lock()
        if self.public:                     # a shared host starts clean
            for run_id in list(self.runs):
                self.remove(run_id)

    def save(self, run: dict) -> None:
        folder = self.path(run["run_id"])
        os.makedirs(folder, exist_ok=True)
        tmp = os.path.join(folder, "run.json.tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(finite(run), f, indent=1, allow_nan=False, ensure_ascii=False)
        os.replace(tmp, os.path.join(folder, "run.json"))

    def get(self, run_id: str) -> dict:
        run = self.runs.get(run_id)
        if run is None:
            raise ApiError("not_found", f"no run {run_id}", status=404)
        run["last_access"] = time.time()
        return run

    def lock_of(self, run_id: str) -> threading.Lock:
        with self.lock:
            return self.locks.setdefault(run_id, threading.Lock())

    def list(self, session_id: str | None) -> list[dict]:
        runs = [r for r in self.runs.values() if session_id is None or r.get("session_id") == session_id]
        return [summary(r) for r in sorted(runs, key=lambda r: r["created"], reverse=True)]

    def remove(self, run_id: str) -> None:
        self.runs.pop(run_id, None)
        self.locks.pop(run_id, None)
        shutil.rmtree(self.path(run_id), ignore_errors=True)

    def cleanup(self, ttl: int = SESSION_TTL) -> int:
        """Remove finished runs nobody has touched for `ttl` seconds (public hosts)."""
        cutoff = time.time() - ttl
        gone = 0
        for run_id, run in list(self.runs.items()):
            if run.get("status") in ("queued", "running"):
                continue
            if run.get("last_access", run.get("created_ts", 0)) < cutoff:
                self.remove(run_id)
                gone += 1
        return gone

    # ── creation ──
    def create(self, session_id: str, validated: G.ValidatedGoal, readiness: dict, model_id: str, mode: str, summary_text: str) -> dict:
        run_id = "run-" + secrets.token_urlsafe(9)
        run = {"run_id": run_id, "project_id": validated.goal.project_id, "model_id": model_id, "session_id": session_id,
               "status": "queued", "mode": mode, "created": now_iso(), "created_ts": time.time(), "last_access": time.time(),
               "started": None, "finished": None, "error": None,
               "goal": validated.goal.model_dump(mode="json"), "generation": validated.generation, "summary": summary_text,
               "notes": validated.notes, "explained": validated.explained, "estimated_seconds": validated.estimated_seconds,
               "family": {"name": validated.family.name, "variant": validated.family.variant, "title": validated.family.title},
               "readiness": {k: readiness.get(k) for k in ("verdict", "exploratory_required", "reasons", "goal_hash", "caveats", "search_advice",
                                                           "windows", "ambiguity", "summary")},
               "progress": {"target": 0, "targets": len(validated.generation["targets"]), "round": 0, "rounds": validated.generation["rounds"],
                            "step": 0, "steps": validated.generation["steps"], "loss": None, "seconds": 0.0},
               "log": [], "candidates": [], "funnel": None, "clusters": None, "timings": {}, "manifest": None}
        with self.lock:
            self.runs[run_id] = run
            self.locks[run_id] = threading.Lock()
        os.makedirs(os.path.join(self.path(run_id), "validation"), exist_ok=True)
        with open(os.path.join(self.path(run_id), "validation", "README.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write("The validation ladder: 0 Generated, 1 Chemistry checked, 2 MLIP screened, 3 DFT relaxed, 4 DFT property confirmed, "
                    "5 Experimentally tested.\nThis version records stages 0 and 1 (the family's chemistry rules) for every candidate; "
                    "later stages are added by the user's own screening, DFT or experiment.\n"
                    "To score the candidates on MEIDNet Prism: meidnet score cifs/ --targets targets.csv --reference data/perov5\n")
        with open(os.path.join(self.path(run_id), "readiness.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(finite(readiness), f, indent=1, allow_nan=False, ensure_ascii=False)
        self.save(run)
        return run


def summary(run: dict) -> dict:
    return {k: run.get(k) for k in ("run_id", "project_id", "model_id", "status", "mode", "created", "started", "finished", "error", "summary",
                                    "estimated_seconds", "family", "progress")} | \
        {"n_candidates": len(run.get("candidates", [])), "verdict": (run.get("readiness") or {}).get("verdict")}


def status_view(run: dict) -> dict:
    return summary(run) | {"log": run.get("log", [])[-80:], "candidates": run.get("candidates", []), "notes": run.get("notes", [])}


# ───────────────────────── the search thread ─────────────────────────
def execute_search(job, run: dict, services) -> None:
    """Runs in a thread: validate again with the run folder, search with the engine, enrich each candidate as it is
    saved, then write the funnel, the configuration, the metrics, the table and the manifest."""
    from meidnet.config import dump_config
    from matter.schemas.goal import Goal
    from matter.services import export, manifest as M

    store, lock = services.runs, services.runs.lock_of(run["run_id"])
    run_dir = store.path(run["run_id"])
    t0 = time.time()

    def log(*a):
        msg = " ".join(str(x) for x in a)
        with lock:
            run["log"].append(msg)
            if len(run["log"]) > LOG_TAIL:
                del run["log"][: len(run["log"]) - LOG_TAIL]
            if msg.lstrip().startswith("=== target"):
                run["progress"]["target"] += 1
                run["progress"]["round"] = 0

    def on_step(step, steps, loss):
        with lock:
            run["progress"].update({"step": step, "steps": steps, "loss": loss, "seconds": round(time.time() - t0, 1)})
            if step == 0:
                run["progress"]["round"] += 1

    try:
        with lock:
            run["status"], run["started"] = "running", now_iso()
        store.save(run)
        goal = Goal.model_validate(run["goal"])
        v = G.validate(goal, services, run_dir=run_dir)
        lm = services.registry.load(run["model_id"])
        entry = services.registry.entry(run["model_id"])
        info = build_info(services.settings.build_info, services.settings.public)
        d = services.artefacts.dataset
        provenance = {"matter_version": info["matter"], "meidnet_version": info["meidnet"], "git_commit": info["git_sha"],
                      "model_sha256": entry.get("sha256"), "dataset_id": d.get("dataset_id"),
                      "dataset_fingerprint": (d.get("fingerprint") or {}).get("combined"), "goal_hash": run["readiness"].get("goal_hash"),
                      "project_id": run["project_id"]}
        ctx = EvidenceContext(lm=lm, family=v.family, artefacts=services.artefacts, latents=services.artefacts.latents(run["model_id"]),
                              dataset_index=services.dataset_index, backend=services.backend, goal=goal, model_id=run["model_id"],
                              mode=run["mode"], windows={k: tuple(w) for k, w in (run["readiness"].get("windows") or {}).items()},
                              run_id=run["run_id"], run_dir=run_dir, rules=rule_map(v.family),
                              ranges={c: tuple(r) for c, r in entry.get("property_ranges", {}).items()}, provenance=provenance)

        def on_candidate(sc, tlog):
            raw = sc.to_dict()
            raw["target_values"] = {k: float(x) for k, x in tlog.values.items()}
            try:
                cand = enrich(raw, ctx, len(run["candidates"]) + 1)
            except Exception as e:                           # evidence must never lose a candidate
                cand = {"candidate_id": f"{run['run_id']}-{len(run['candidates']) + 1:03d}", "engine": raw, "enrichment_error": str(e),
                        "identity": {"formula": raw.get("formula")}, "flags": raw.get("flags", []), "mode": run["mode"]}
            with lock:
                run["candidates"].append(cand)
            store.save(run)

        from matter.backends.base import SearchHooks
        hooks = SearchHooks(log=log, on_step=on_step, on_candidate=on_candidate, should_stop=lambda: services.jobs.should_stop(job, log))
        res = services.backend.search(lm, v.config, v.family, os.path.join(run_dir, "generation"), hooks)
        objectives = v.generation["objectives"]
        with lock:
            run["funnel"] = [funnel_for(t, v.family, objectives, v.generation.get("population")) for t in res.targets]
            run["clusters"] = assign_clusters(run["candidates"])       # one-to-many: alternatives grouped by encoder latent
            run["timings"] = {"search_s": round(time.time() - t0, 1)}
        with open(os.path.join(run_dir, "config.yaml"), "w", encoding="utf-8", newline="\n") as f:
            f.write(dump_config(v.config))
        with open(os.path.join(run_dir, "metrics.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(finite({"funnel": run["funnel"], "clusters": run["clusters"], "timings": run["timings"]}), f, indent=1, allow_nan=False)
        with open(os.path.join(run_dir, "candidates.csv"), "w", encoding="utf-8", newline="") as f:
            f.write(export.candidates_csv(run))
        with open(os.path.join(run_dir, "targets.csv"), "w", encoding="utf-8", newline="") as f:
            f.write(export.targets_csv(run))
        final = "stopped" if job.stop_flag else "done"
        finished = now_iso()
        manifest_doc = M.build_manifest(dict(run, status=final, finished=finished), services)
        with lock:                                            # the status changes last, with everything else in place
            run["finished"], run["manifest"], run["status"] = finished, manifest_doc, final
        store.save(run)
    except Exception as e:
        with lock:
            run["status"], run["finished"] = "error", now_iso()
            run["error"] = ("the search failed" if services.settings.public else "".join(traceback.format_exception(type(e), e, e.__traceback__)))
            if not services.settings.public:
                run["log"].append(str(e))
        store.save(run)
    except SystemExit as e:                                   # the engine's way of reporting a user error
        with lock:
            run["status"], run["finished"], run["error"] = "error", now_iso(), str(e.code if e.code is not None else e)
        store.save(run)
