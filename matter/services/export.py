"""Exports: the candidate table as CSV, a candidate as JSON, the run bundle as a zip."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import zipfile

from matter.jsonsafe import finite


def candidate_rows(run: dict) -> tuple[list[str], list[dict]]:
    """Flat rows of the candidate table; the domain status and the flags of every property travel with it."""
    rows = []
    columns: list[str] = []
    for c in run.get("candidates", []):
        if "properties" not in c:
            continue
        row = {"candidate_id": c["candidate_id"], "formula": c["identity"]["formula"], "reduced_formula": c["identity"]["reduced_formula"],
               "site_key": c["identity"].get("site_key") or ""}
        for g, el in c["identity"]["elements"].items():
            row[f"site_{g}"] = el
        row["lattice_a"] = c["structure"].get("lattice_a")
        for p, v in c["properties"].items():
            row[f"target_{p}"] = v["target"]
            row[f"predicted_{p}"] = v["predicted"]
            row[f"difference_{p}"] = v["difference"]
            row[f"encoder_{p}"] = c["model_evidence"]["encoder_prediction"].get(p)
            row[f"agreement_{p}"] = c["model_evidence"]["agreement"][p]["label"]
            row[f"domain_{p}"] = v["domain"]["status"]
            if "dft_value" in v:
                row[f"dataset_dft_{p}"] = v["dft_value"]
        for r in c["constraints"]:
            row[f"rule_{r['id']}"] = r["value"] if r["value"] is not None else ("passed" if r["passed"] else "failed")
        row["rules_passed"] = f"{c['rules_passed']}/{c['rules_total']}"
        nn = c["model_evidence"]["nearest_training"]
        row["nearest_formula"] = nn[0]["formula"] if nn else ""
        row["nearest_cosine"] = nn[0]["cosine"] if nn else None
        row["local_density_n"] = c["model_evidence"]["local_density"]["n_within"]
        row["novelty_dataset"] = c["novelty"]["dataset"]["label"]
        row["novelty_training"] = c["novelty"]["training_split"]["label"]
        row["stability"] = c["stability"]["status"]
        row["latent_norm"] = c["model_evidence"]["latent_norm"]
        row["score"] = c["model_evidence"]["score"]
        row["round"] = c["round"]
        row["target_index"] = c["target_index"]
        row["mode"] = c["mode"]
        row["file"] = c["structure"]["file"]
        row["flags"] = " | ".join(c["flags"])
        row["why"] = c["why"]
        for k in row:
            if k not in columns:
                columns.append(k)
        rows.append(row)
    return columns, rows


def candidates_csv(run: dict) -> str:
    columns, rows = candidate_rows(run)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    return buf.getvalue()


def candidate_json(c: dict) -> str:
    return json.dumps(finite(c), indent=1, allow_nan=False, ensure_ascii=False)


def bundle_zip(run: dict, services) -> bytes:
    """run.json, config.yaml, metrics.json, readiness.json, candidates.csv, the engine's generation/ folder, one CIF
    per candidate under cifs/, the validation folder, environment.json and hashes.json."""
    from matter.version import build_info
    run_dir = services.runs.path(run["run_id"])
    buf = io.BytesIO()
    hashes = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        def add_bytes(name: str, data: bytes):
            z.writestr(name, data)
            hashes[name] = hashlib.sha256(data).hexdigest()

        add_bytes("run.json", json.dumps(finite(run), indent=1, allow_nan=False, ensure_ascii=False).encode("utf-8"))
        for name in ("config.yaml", "metrics.json", "readiness.json", "candidates.csv", os.path.join("validation", "README.txt")):
            p = os.path.join(run_dir, name)
            if os.path.exists(p):
                with open(p, "rb") as f:
                    add_bytes(name.replace(os.sep, "/"), f.read())
        gen = os.path.join(run_dir, "generation")
        for d, _, files in os.walk(gen):
            for fn in files:
                p = os.path.join(d, fn)
                with open(p, "rb") as f:
                    add_bytes(os.path.relpath(p, run_dir).replace(os.sep, "/"), f.read())
        for c in run.get("candidates", []):
            rel = (c.get("structure") or {}).get("file") or ("generation/" + c["engine"]["file"])
            p = os.path.join(run_dir, rel.replace("/", os.sep))
            if os.path.exists(p):
                with open(p, "rb") as f:
                    add_bytes(f"cifs/{c['candidate_id']}.cif", f.read().replace(b"\r\n", b"\n"))
        env = build_info(services.settings.build_info, services.settings.public)
        add_bytes("environment.json", json.dumps(env, indent=1).encode("utf-8"))
        if run.get("manifest"):
            add_bytes("manifest.json", json.dumps(finite(run["manifest"]), indent=1, allow_nan=False, ensure_ascii=False).encode("utf-8"))
        z.writestr("hashes.json", json.dumps(hashes, indent=1))
    return buf.getvalue()
