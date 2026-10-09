"""Train Lite: a real MEIDNet training, small and fixed, run on the server so a visitor can watch the method learn.

What is fixed: the data (a 1,500-material subset of Perov-5 with 30% non-zero band gaps, featurised at build time by
matter.demo_build.build_trainlite, so no CIF is parsed here), the recipe (the demo's default one, at the subset's size),
the budget (TRAIN_PUBLIC_LIMITS). What the user chooses: epochs (10, 20 or 50) and the seed.

What comes back: the per-epoch curves (training loss and its parts, validation error of each property, alignment), the
model's predictions against the reference values of the 500 validation materials, a 2D map of the validation latents,
the same numbers for the demo's full model on the same 500 materials, the trained model file, and the recipe to run the
same training at full size locally. The small model never drives generation on this server: it is a lesson, not a
product, and the page says so.

Layout of a job folder (under <run_root>/train/<job_id>):
      job.json          the record (request, progress, history, result)
      model.pt          the trained MEIDNet checkpoint
      config.yaml       the recipe with the user's epochs and seed
      predictions.csv   material, split, reference and predicted value of each property
"""
from __future__ import annotations

import json
import os
import secrets
import time
import traceback

import numpy as np

from matter.api.errors import ApiError
from matter.jsonsafe import finite
from matter.schemas.train import EPOCH_OPTIONS, TRAINLITE_SCHEMA_ID
from matter.services.runs import LOG_TAIL, RunStore, now_iso

TRAIN_PUBLIC_LIMITS = {"epochs": max(EPOCH_OPTIONS), "seconds": 300}


class TrainStore(RunStore):
    """The RunStore's persistence (atomic saves, scan, cleanup, locks) with training records."""
    noun = "training job"

    def create(self, session_id: str, request: dict, subset: dict, estimated_seconds: int) -> dict:  # type: ignore[override]
        job_id = "lite-" + secrets.token_urlsafe(9)
        job = {"schema": TRAINLITE_SCHEMA_ID, "job_id": job_id, "run_id": job_id, "session_id": session_id, "status": "queued",
               "created": now_iso(), "created_ts": time.time(), "last_access": time.time(), "started": None, "finished": None, "error": None,
               "request": request, "subset": subset, "limits": TRAIN_PUBLIC_LIMITS if self.public else None,
               "estimated_seconds": estimated_seconds,
               "progress": {"epoch": 0, "epochs": request["epochs"], "phase": "queued", "seconds": 0.0},
               "history": [], "result": None, "log": [], "provenance": None}
        with self.lock:
            self.runs[job_id] = job
            self.locks[job_id] = _lock()
        self.save(job)
        return job

    def list(self, session_id: str | None) -> list[dict]:  # type: ignore[override]
        jobs = [r for r in self.runs.values() if session_id is None or r.get("session_id") == session_id]
        return [summary(j) for j in sorted(jobs, key=lambda r: r["created"], reverse=True)]


def _lock():
    import threading
    return threading.Lock()


def summary(job: dict) -> dict:
    return {k: job.get(k) for k in ("job_id", "status", "created", "started", "finished", "error", "request", "limits", "estimated_seconds", "progress")}


def status_view(job: dict) -> dict:
    return summary(job) | {"history": job.get("history", []), "log": job.get("log", [])[-40:], "subset": job.get("subset"),
                           "result": job.get("result"), "provenance": job.get("provenance")}


class Subset:
    """The featurised subset and the reference, read once from the demo folder; absent when the demo ships none."""

    def __init__(self, demo_dir: str):
        self.dir = os.path.join(demo_dir, "trainlite")
        self.available = os.path.isfile(os.path.join(self.dir, "subset.npz")) and os.path.isfile(os.path.join(self.dir, "reference.json"))
        self._data = None
        self.reference = json.load(open(os.path.join(self.dir, "reference.json"), encoding="utf-8")) if self.available else None
        self.config = open(os.path.join(self.dir, "config.yaml"), encoding="utf-8").read() if self.available else None

    def data(self):
        if self._data is None:
            self._data = np.load(os.path.join(self.dir, "subset.npz"))
        return self._data

    def describe(self) -> dict:
        if not self.available:
            return {"available": False}
        ref = self.reference
        return {"available": True, "epochs": list(EPOCH_OPTIONS), "subset": ref["subset"], "full_model": ref["full_model"],
                "recipe": ref["recipe"], "seconds_per_epoch_estimate": 0.5, "limits": TRAIN_PUBLIC_LIMITS}


def estimated_seconds(epochs: int) -> int:
    """Measured: 1,500 materials, 2 CPUs: about 0.2 s per epoch plus the model build; the validation pass each epoch adds a little."""
    return int(10 + 0.6 * epochs)


def execute_training(job_obj, job: dict, services) -> None:
    """The thread body: records from the featurised subset, the recipe with the user's epochs and seed, fit with a
    validation pass every epoch, save, then measure the model the way the readiness report measures the demo's."""
    import torch
    from meidnet.benchmark import encode, property_metrics, retrieval
    from meidnet.checkpoint import build_model, load_checkpoint, save_checkpoint
    from meidnet.config import config_from_dict, dump_config
    from meidnet.data import MaterialsDataset, Record, compute_stats
    from meidnet.train import evaluate, fit, seed_everything
    from matter.demo_build import TRAINLITE_CONFIG, pca2
    from matter.version import build_info

    store = services.trainings
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

    try:
        with lock:
            job["status"], job["started"] = "running", now_iso(); job["progress"]["phase"] = "preparing the data"
        store.save(job)
        sub = services.trainlite
        d = sub.data()
        columns = [str(c) for c in d["columns"]]
        splits = d["split"]
        recs = {s: [Record(str(i), x, y, str(f)) for i, x, y, f, sp in zip(d["material_id"], d["dense"], d["props"], d["formula"], splits) if sp == s]
                for s in ("train", "val")}
        raw = json.loads(json.dumps(TRAINLITE_CONFIG))
        raw["training"]["epochs"], raw["training"]["seed"] = int(req["epochs"]), int(req["seed"])
        raw["output_dir"] = job_dir
        cfg = config_from_dict(raw, base_dir=job_dir)
        props = cfg.data.properties
        stats = compute_stats(recs["train"], [p.column for p in props], [p.normalize for p in props], [p.display for p in props], [p.unit for p in props])
        train_set, val_set = MaterialsDataset(recs["train"], stats), MaterialsDataset(recs["val"], stats)
        seed_everything(cfg.training.seed)
        torch.set_num_threads(max(1, int(services.settings.torch_threads or 2)))
        model_cfg = cfg.model.model_dump()
        model = build_model(len(props), model_cfg, cfg.data.max_sites)
        with lock:
            job["progress"]["phase"] = "training"
        store.save(job)

        def on_epoch(ep, rec):
            ev = evaluate(model, val_set, stats)                       # every epoch: the curves the page draws live
            point = {"epoch": ep, "loss": round(float(rec["total"]), 4),
                     "parts": {k: round(float(v), 4) for k, v in rec.items() if k in ("recon_joint", "prop_joint", "recon_from_prop", "prop_from_prop",
                                                                                         "contrastive", "recon_from_struct", "prop_from_struct")},
                     "alignment_cosine": round(float(rec["cosine"]), 4),
                     "val_mae": {k: round(float(v), 4) for k, v in ev["mae"].items()}, "retrieval_top1": round(float(ev.get("retrieval_top1", 0.0)), 4)}
            with lock:
                job["history"].append(point)
                job["progress"].update({"epoch": ep, "seconds": round(time.time() - t0, 1)})
            store.save(job)

        history = fit(model, train_set, val_set, cfg.training, coord_mode=cfg.model.decoder_coordinate_input, device="cpu",
                      on_epoch=on_epoch, log=log, should_stop=lambda: services.jobs.should_stop(job_obj, log))
        with lock:
            job["progress"]["phase"] = "measuring"
        store.save(job)
        path = os.path.join(job_dir, "model.pt")
        save_checkpoint(path, model, stats, model_cfg, cfg.data.max_sites, None,
                        extra={"history": history, "config": raw, "data_report": {"rows": len(recs["train"]), "kept": len(recs["train"]), "skipped": {}},
                               "note": f"Train Lite: {len(recs['train'])} Perov-5 materials, {len(history['train'])} epochs, seed {cfg.training.seed}"})
        with open(os.path.join(job_dir, "config.yaml"), "w", encoding="utf-8", newline="\n") as f:
            f.write(dump_config(cfg))
        lm = load_checkpoint(path, device="cpu")
        Zc, Zp, P = encode(lm, recs["val"], space="projection")
        Y = np.array([r.properties for r in recs["val"]], dtype=float)
        metrics = property_metrics(columns, Y, P)
        rep = retrieval(Zc, Zp, Y)
        xy, explained = pca2(Zc)
        ref = sub.reference
        full = ref["full_model"]
        spread = ref["subset"]["spread"]
        words = {}
        for c in columns:
            s_ = ref["subset"]["spread_dir_gap_nonzero"] if c == "dir_gap" else spread[c]
            mae = metrics.get(f"mae_{c}_nonzero", metrics[f"mae_{c}"]) if c == "dir_gap" else metrics[f"mae_{c}"]
            words[c] = {"mae": float(mae), "spread": float(s_), "ratio": float(mae / s_) if s_ else None,
                        "basis": "materials with a non-zero gap" if c == "dir_gap" else "all validation materials",
                        "full_model_mae": float(full["val_mae_dir_gap_nonzero"] if c == "dir_gap" else full["val_mae"][c])}
        result = {"n_val": len(recs["val"]), "epochs_run": len(history["train"]), "stopped_early": bool(history.get("stopped")),
                  "seconds": round(float(history["seconds"]), 1),
                  "val": {"mae": {c: float(metrics[f"mae_{c}"]) for c in columns}, "r2": {c: float(metrics[f"r2_{c}"]) for c in columns},
                          "mae_dir_gap_nonzero": float(metrics.get("mae_dir_gap_nonzero", float("nan"))), "retrieval_top1": float(rep["retrieval_top1"])},
                  "against_spread": words,
                  "full_model": full,
                  "predictions": {"columns": columns, "rows": [[r.material_id, r.formula, *[round(float(v), 4) for v in Y[i]], *[round(float(v), 4) for v in P[i]]]
                                                             for i, r in enumerate(recs["val"])]},
                  "map": {"explained_variance": [round(v, 4) for v in explained],
                          "points": [[r.material_id, round(float(xy[i, 0]), 3), round(float(xy[i, 1]), 3), round(float(Y[i, columns.index("dir_gap")]), 4)]
                                     for i, r in enumerate(recs["val"])]},
                  "what_this_is": ("A MEIDNet model trained from scratch on 1,500 materials for a few epochs, measured on 500 held-out validation "
                                   "materials. It shows how the method learns; it is far smaller than the demo's full model and does not drive "
                                   "generation on this server. The same recipe at full size (config.yaml, 200 epochs on 11,356 materials) is the "
                                   "demo's default model."),
                  "full_training_command": ref["full_training_command"]}
        with open(os.path.join(job_dir, "predictions.csv"), "w", encoding="utf-8", newline="\n") as f:
            f.write(",".join(["material_id", "formula", *[f"reference_{c}" for c in columns], *[f"predicted_{c}" for c in columns]]) + "\n")
            for row in result["predictions"]["rows"]:
                f.write(",".join(str(x) for x in row) + "\n")
        info = build_info(services.settings.build_info, services.settings.public)
        with lock:
            job["result"] = finite(result)
            job["provenance"] = {"matter_version": info["matter"], "meidnet_version": info["meidnet"], "git_commit": info["git_sha"],
                                 "subset_file": "trainlite/subset.npz", "space_id": info.get("space_id")}
            job["progress"].update({"phase": "done", "epoch": len(history["train"]), "seconds": round(time.time() - t0, 1)})
            job["finished"], job["status"] = now_iso(), ("stopped" if history.get("stopped") else "done")
        store.save(job)
        with open(os.path.join(job_dir, "job.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(finite({k: v for k, v in job.items() if k != "session_id"}), f, indent=1, allow_nan=False, ensure_ascii=False)
    except Exception as e:
        with lock:
            job["status"], job["finished"] = "error", now_iso()
            job["error"] = "the training failed" if services.settings.public else "".join(traceback.format_exception(type(e), e, e.__traceback__))
        store.save(job)
    except SystemExit as e:
        with lock:
            job["status"], job["finished"], job["error"] = "error", now_iso(), str(e.code if e.code is not None else e)
        store.save(job)


def validate_request(body, public: bool) -> dict:
    req = body.model_dump()
    if req["epochs"] not in EPOCH_OPTIONS:
        raise ApiError("validation_error", f"epochs must be one of {EPOCH_OPTIONS}", status=422, fields=[{"loc": "epochs", "msg": "not an option"}])
    return req
