"""The run manifest: everything needed to say what produced the candidates."""
from __future__ import annotations

import hashlib
import os

from matter.version import build_info


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(run: dict, services) -> dict:
    art, settings = services.artefacts, services.settings
    entry = services.registry.entry(run["model_id"])
    d = art.dataset
    run_dir = services.runs.path(run["run_id"])
    info = build_info(settings.build_info, settings.public)
    candidates = []
    exported = {}
    for c in run.get("candidates", []):
        rel = (c.get("structure") or {}).get("file") or ("generation/" + c["engine"]["file"])
        path = os.path.join(run_dir, rel.replace("/", os.sep))
        digest = sha256_file(path) if os.path.exists(path) else None
        candidates.append({"candidate_id": c["candidate_id"], "formula": c.get("identity", {}).get("formula"), "file": rel, "sha256": digest})
        if digest:
            exported[rel] = digest
    for name in ("config.yaml", "metrics.json", "readiness.json", "candidates.csv"):
        p = os.path.join(run_dir, name)
        if os.path.exists(p):
            exported[name] = sha256_file(p)
    gen = run["generation"]
    return {
        "manifest_version": 1, "run_id": run["run_id"], "created": run["created"], "started": run["started"], "finished": run["finished"],
        "status": run["status"], "mode": run["mode"],
        "software": {"matter_version": info["matter"], "meidnet_version": info["meidnet"], "git_commit": info["git_sha"], "python": info["python"],
                     "torch": info["torch"], "pymatgen": info["pymatgen"], "platform": info["platform"], "space_id": info.get("space_id")},
        "project": {"project_id": run["project_id"], "title": art.project["title"]},
        "dataset": {"dataset_id": d["dataset_id"], "title": d["title"], "fingerprint": d["fingerprint"], "rows": d["rows"],
                    "property_schema": [{"column": c, "label": d["properties"][c]["label"], "unit": d["properties"][c]["unit"]} for c in art.columns],
                    "family": entry.get("family"), "split_strategy": "CDVAE fixed split (train/val/test files)", "source": d.get("source")},
        "model": {"model_id": entry["model_id"], "file": entry["file"], "sha256": entry["sha256"], "backend": entry["backend"],
                  "trained_on": f"{entry['training_rows']:,} materials ({entry['trained_on']})", "legacy": entry["legacy"],
                  "max_sites": entry["max_sites"], "latent_dim": entry["latent_dim"], "training": {"epochs": "not recorded", "duration": "not recorded", "seed": "not recorded"}},
        "readiness": run["readiness"],
        "design": {"goal": run["goal"], "summary": run["summary"], "targets": gen["targets"],
                   "constraints": {"family": run["family"], "extra": gen.get("extra_constraints", []), "overrides": gen.get("overrides", {}),
                                   "disabled": gen.get("disabled_rules", []), "exclude_elements": gen.get("exclude_elements", []),
                                   "only_elements": gen.get("only_elements", {})},
                   "search_config": gen, "seed": gen.get("seed"),
                   "candidate_budget": {"per_target": gen.get("per_target"), "targets": len(gen["targets"])}},
        "validation": {"config": None, "status": "Not screened"},
        "timestamps": {"created": run["created"], "started": run["started"], "finished": run["finished"]},
        "durations_s": run.get("timings", {}),
        "funnel": run.get("funnel"),
        "candidates": candidates, "exported_files": exported,
    }
