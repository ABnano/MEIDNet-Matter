"""Vendor a snapshot of the MEIDNet engine and its evaluation components into this repository as `engine/`.

Matter imports the engine as the `meidnet` package.  The published package (PyPI 2.2.0) predates the symmetry decoder,
the labels read from the returned structure and the staged evaluation, so until those are released upstream a snapshot
of the research checkout is carried here, installed with `pip install ./engine`, and recorded file by file with its
sha256 in `engine/SNAPSHOT.json` so the provenance of every line can be checked.

    python scripts/vendor_engine.py --src /path/to/meidnet_checkout [--dest engine]

The source tree is expected to hold `meidnet/` (the package) and `eval/` (the component scripts).  Bytecode caches,
batch-queue scripts and results are not copied.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))

PYPROJECT = '''[build-system]
requires = ["setuptools>=77", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "meidnet"
version = "{version}"
description = "MEIDNet engine snapshot vendored by MEIDNet Matter: multimodal inverse design for crystalline materials"
readme = "README.md"
requires-python = ">=3.10"
license = "MIT"
dependencies = [
  "torch>=2.1", "numpy>=1.24", "pandas>=2.0", "pymatgen>=2024.1.1", "scipy>=1.10", "spglib>=2.0",
  "scikit-learn>=1.3", "matplotlib>=3.7", "pyyaml>=6.0", "pydantic>=2.5", "openpyxl>=3.1",
]

[project.scripts]
meidnet = "meidnet.cli:main"

[tool.setuptools.packages.find]
include = ["meidnet", "meidnet.*", "meidnet_eval", "meidnet_eval.*"]

[tool.setuptools.package-data]
meidnet = ["families/*.yaml", "studio/*.html", "studio/*.js", "element_features_cgcnn.json"]
meidnet_eval = ["*.md"]
'''

README = '''# engine/ — the MEIDNet engine, vendored

`meidnet/` is a snapshot of the MEIDNet package at the research checkout recorded in `SNAPSHOT.json`
(upstream commit {commit} plus the uncommitted work of the staged-evaluation rounds), and `meidnet_eval/` holds the
evaluation components (the ten blocks and their bands in `stages.py`, the generation, judging, relaxation and
calibration scripts).  Install with `pip install ./engine` **before** `pip install -e .`; the distribution is named
`meidnet` ({version}) so the application's `meidnet>=2.2.0,<3` dependency resolves to it and nothing is fetched from PyPI.

On PyPI, `meidnet` {version} is this snapshot, uploaded by MEIDNet-Matter's release workflow so that `pip install meidnet-matter`
resolves without a clone; the upstream MEIDNet release 2.4.0 (https://github.com/ABnano/MEIDNet) will replace it.

Snapshot taken {date}.  To refresh it: `python scripts/vendor_engine.py --src <checkout>`.  The upstream release of this
work is planned as meidnet 2.4.0; when it exists, this folder is removed and the dependency pinned to that release.
'''

EVAL_INIT = '''"""The evaluation components of the MEIDNet staged pipeline, importable as a package.

`stages.py` is the single definition of the ten blocks (S0–S9), their metrics and reference bands; the other modules
compute what the blocks grade.  `COMPONENTS` says where each one can run: in the web application ("web"), on a
workstation with the machine-learning potentials installed ("local"), or only on a cluster with a batch queue and
database access ("hpc").
"""
COMPONENTS = {{
{components}
}}
'''

# where each component can run; everything not listed is "local" (torch + pymatgen on a workstation)
RUNNABLE = {
    "stages.py": ("web", []), "preview.py": ("web", []), "conditional_generate.py": ("web", []),
    "target_calibration.py": ("web", ["matgl"]), "instrument_sheet.py": ("web", []), "metrics_sun.py": ("web", []),
    "journey.py": ("web", []), "ingest_upload.py": ("web", []), "intake.py": ("web", []),
    "d1_mlip_check.py": ("local", ["matgl", "ase"]), "candidate_cells.py": ("local", ["matgl", "ase"]),
    "relax_cache.py": ("local", ["matgl"]), "stability_distorted.py": ("local", ["matgl"]),
    "generate_to_target.py": ("local", ["matgl"]), "screen_local.py": ("local", ["matgl (judge)"]),
    "check_candidates.py": ("local", ["matgl", "ase"]), "hull_mlip.py": ("local", ["matgl", "ase", "a reference set: the JARVIS-DFT dump or an MP key"]),
    "discover.py": ("hpc", ["slurm", "mp_api"]), "sun_validate.py": ("hpc", ["matgl", "mp_api"]),
    "fetch_oqmd_structures.py": ("hpc", ["network"]), "prefetch_mp.py": ("hpc", ["mp_api"]),
    "mp_perovskite_dataset.py": ("hpc", ["mp_api"]), "mixed_anion_coverage.py": ("hpc", ["mp_api"]),
    "discovery_space.py": ("hpc", ["mp_api"]), "cgcnn_judge.py": ("local", ["cgcnn_repo"]),
}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head(src: str) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=src, capture_output=True, text=True, timeout=10).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def copy_tree(src: str, dst: str, keep) -> list[str]:
    copied = []
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != "__pycache__" and not d.startswith(".")]
        rel = os.path.relpath(root, src)
        for name in files:
            if not keep(rel, name):
                continue
            s = os.path.join(root, name)
            d = os.path.join(dst, rel, name) if rel != "." else os.path.join(dst, name)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)
            copied.append(os.path.relpath(d, dst))
    return sorted(copied)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="the MEIDNet checkout holding meidnet/ and eval/")
    ap.add_argument("--dest", default=os.path.join(ROOT, "engine"))
    a = ap.parse_args()
    src = os.path.abspath(a.src)
    pkg_src, eval_src = os.path.join(src, "meidnet"), os.path.join(src, "eval")
    for p in (pkg_src, eval_src):
        if not os.path.isdir(p):
            raise SystemExit(f"{p} is not a folder")
    version = re.search(r'__version__\s*=\s*"([^"]+)"', open(os.path.join(pkg_src, "__init__.py"), encoding="utf-8").read()).group(1)

    if os.path.isdir(a.dest):
        shutil.rmtree(a.dest)
    os.makedirs(a.dest)
    pkg_files = copy_tree(pkg_src, os.path.join(a.dest, "meidnet"),
                          lambda rel, n: n.endswith((".py", ".yaml", ".yml", ".json", ".html", ".js")) and not n.endswith(("_test.py",)))
    eval_files = copy_tree(eval_src, os.path.join(a.dest, "meidnet_eval"),
                           lambda rel, n: rel == "." and n.endswith(".py"))
    comps = []
    for f in eval_files:
        where, needs = RUNNABLE.get(f, ("local", []))
        comps.append(f'    "{f}": {{"runnable": "{where}", "needs": {json.dumps(needs)}}},')
    with open(os.path.join(a.dest, "meidnet_eval", "__init__.py"), "w", encoding="utf-8", newline="\n") as f:
        f.write(EVAL_INIT.format(components="\n".join(comps)))
    with open(os.path.join(a.dest, "pyproject.toml"), "w", encoding="utf-8", newline="\n") as f:
        f.write(PYPROJECT.format(version=version))
    commit = git_head(src)
    date = _dt.date.today().isoformat()
    with open(os.path.join(a.dest, "README.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(README.format(commit=commit[:10], version=version, date=date))
    files = {}
    for root, _dirs, names in os.walk(a.dest):
        for n in names:
            p = os.path.join(root, n)
            files[os.path.relpath(p, a.dest).replace(os.sep, "/")] = sha256_file(p)
    snapshot = {"schema": "meidnet-matter/engine-snapshot/1", "source": os.path.basename(os.path.normpath(src)),  # a name, never a machine path
                "source_commit": commit, "version": version,
                "snapshot_date": date, "n_files": len(files), "files": dict(sorted(files.items()))}
    with open(os.path.join(a.dest, "SNAPSHOT.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(snapshot, f, indent=1, sort_keys=True)
    print(f"engine {version} from {commit[:10]}: {len(pkg_files)} package files, {len(eval_files)} components -> {a.dest}")


if __name__ == "__main__":
    main()
