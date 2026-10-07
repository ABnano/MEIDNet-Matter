"""Deploy MEIDNet Matter to its Hugging Face Space.

    python deploy/deploy_space.py --dry-run                 # stage the bundle in build/space_docker, upload nothing
    HF_TOKEN=<write token> python deploy/deploy_space.py    # stage, upload, wait for RUNNING, check the live pages

The token comes from the environment for that one command and is never written anywhere. The script deploys
Babu09/MEIDNet-Matter only; Babu09/MEIDNet and Babu09/MEIDNet-Prism are other products and are refused unless
--allow-other-space is given on purpose.

The bundle: matter/ (with the built frontend in matter/static), engine/ (the vendored MEIDNet snapshot), examples/perov5/,
examples/research/, every checkpoint the manifest marks for shipping (each verified against its sha256), the configs,
deploy/Dockerfile, deploy/requirements.txt, a README card, a .gitattributes that lists every binary type for LFS (the
Space build restores only the types named there; an unlisted binary arrives as a pointer file), and build_info.json.
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
import sys
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
STAGE = os.path.join(ROOT, "build", "space_docker")
TARGET = "Babu09/MEIDNet-Matter"
PROTECTED = ("Babu09/MEIDNet", "Babu09/MEIDNet-Prism")
CKPT_NAME = "dual_autoencoder_clip_earlyfusion_propertyaware_2k.pth"
CKPT_SHA256 = "f9493781d5bbb05dfe106874269496c4c1c0364ae9e543703625c8d1efd60c87"
MANIFEST = os.path.join(ROOT, "checkpoints", "manifest.json")
TEXT_TYPES = (".html", ".js", ".css", ".md", ".json", ".txt", ".py", ".yaml", ".yml", ".svg", ".csv", ".cff")
LFS_EXTENSIONS = ["pth", "npz", "npy", "pt", "safetensors", "csv", "gz", "zip", "png", "jpg", "jpeg", "gif", "webp", "ico",
                  "woff", "woff2", "ttf", "pdf", "wasm", "mp4", "webm"]
SECRET_RE = re.compile(r"\b(hf_[A-Za-z0-9]{30,}|ghp_[A-Za-z0-9]{30,}|pypi-[A-Za-z0-9_-]{40,})\b")
MAX_STAGE_MB = 80

README = """---
title: MEIDNet Matter
emoji: 🧭
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: true
license: mit
short_description: From your materials data to candidate structures
thumbnail: https://babu09-meidnet-matter.hf.space/og.png
tags: [materials, inverse-design, generative, crystal, perovskite, multimodal, search-engine, chemistry]
models: [Babu09/MEIDNet]
---

# MEIDNet Matter

**From your materials data to candidate structures.** A multimodal inverse-design workbench for crystalline
materials: define property targets and chemistry rules, read the Design Readiness report (can this dataset and model
support the target?), search for candidate structures, and export them with their evidence and a run manifest.
MEIDNet is the engine; MEIDNet Prism (https://babu09-meidnet.hf.space) is where to learn the method and benchmark it.

Matter currently searches property-conditioned candidates within supported structural families. Free-geometry
crystal generation is planned as additional design backends mature.

This version: the Perov-5 demo project end to end (cubic ABX3 perovskites, the published MEIDNet model, direct band
gap and formation enthalpy).

* [Open the app](https://babu09-meidnet-matter.hf.space/) · [Code](https://github.com/ABnano/MEIDNet-Matter) ·
  [Engine](https://github.com/ABnano/MEIDNet) · [Model](https://huggingface.co/Babu09/MEIDNet) ·
  [Paper](https://doi.org/10.1038/s41524-026-02153-3)

What happens on this shared Space: nothing is uploaded in this version; a search's run folder lives on the
container's disk, is removed after an hour of inactivity and on every restart, and is never used to train anything.
No account, no analytics beyond the Space's own metrics. Predictions are model estimates and are labelled as such.

Citation: A. Babu, R. Almeida Gouvêa, P. Vandergheynst, G.-M. Rignanese, MEIDNet: Multimodal generative AI framework
for inverse materials design, npj Computational Materials 12, 287 (2026).
"""


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def space_host(repo: str) -> str:
    owner, name = repo.split("/", 1)
    return f"{owner.lower()}-{re.sub(r'[._]', '-', name.lower())}.hf.space"


def git_info(root: str) -> tuple[str, bool]:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, timeout=10).stdout.strip())
        return sha or "unknown", dirty
    except (OSError, subprocess.SubprocessError):
        return "unknown", False


def build_frontend(root: str) -> None:
    subprocess.run(["npm", "ci", "--no-fund", "--no-audit"], cwd=os.path.join(root, "frontend"), check=True, shell=os.name == "nt")
    subprocess.run(["npm", "run", "build"], cwd=os.path.join(root, "frontend"), check=True, shell=os.name == "nt")


def frontend_is_fresh(root: str) -> bool:
    index = os.path.join(root, "matter", "static", "index.html")
    if not os.path.exists(index):
        return False
    built = os.path.getmtime(index)
    src = os.path.join(root, "frontend", "src")
    for d, _, files in os.walk(src):
        for f in files:
            if os.path.getmtime(os.path.join(d, f)) > built:
                return False
    return True


def build_stage(root: str = ROOT, stage: str = STAGE, fetch: bool = True, version: str | None = None,
                allow_missing: bool = False) -> str:
    """Stage the bundle.  allow_missing (dry runs only) skips checkpoints that are not on disk instead of failing."""
    """Copy what the Space needs into `stage` and write the card, the LFS list and the build info."""
    index = os.path.join(root, "matter", "static", "index.html")
    if not os.path.exists(index):
        raise SystemExit("matter/static/index.html is missing: build the frontend first (npm run build in frontend/) or pass --build")
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    os.makedirs(stage)
    shutil.copytree(os.path.join(root, "matter"), os.path.join(stage, "matter"), ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    shutil.copytree(os.path.join(root, "examples", "perov5"), os.path.join(stage, "examples", "perov5"))
    for extra in ("examples/research",):                                   # the studies, blocks and support files
        if os.path.isdir(os.path.join(root, extra)):
            shutil.copytree(os.path.join(root, extra), os.path.join(stage, extra))
    shutil.copytree(os.path.join(root, "engine"), os.path.join(stage, "engine"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "tests", "build", "*.egg-info"))
    # every checkpoint the manifest marks for shipping, each verified against its recorded checksum
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    os.makedirs(os.path.join(stage, "checkpoints"))
    shipped = {}
    for entry in manifest["checkpoints"]:
        if not entry.get("ship") or "file" not in entry:
            continue
        ckpt = os.path.join(root, "checkpoints", entry["file"])
        if not os.path.exists(ckpt) and fetch:
            from scripts.fetch_assets import fetch as fetch_asset
            fetch_asset(entry["id"], os.path.join(root, "checkpoints"))
        if not os.path.exists(ckpt):
            if allow_missing:
                print(f"  (dry run) {entry['file']} is not on disk; skipped")
                continue
            raise SystemExit(f"{ckpt} is missing: run python scripts/fetch_assets.py --only {entry['id']}")
        if entry.get("sha256") and sha256_file(ckpt) != entry["sha256"]:
            raise SystemExit(f"{ckpt} does not match the checksum in the manifest")
        shutil.copy2(ckpt, os.path.join(stage, "checkpoints", entry["file"]))
        shipped[entry["id"]] = entry.get("sha256")
    shutil.copy2(MANIFEST, os.path.join(stage, "checkpoints", "manifest.json"))
    if os.path.isdir(os.path.join(root, "checkpoints", "configs")):
        shutil.copytree(os.path.join(root, "checkpoints", "configs"), os.path.join(stage, "checkpoints", "configs"))
    shutil.copy2(os.path.join(root, "deploy", "Dockerfile"), os.path.join(stage, "Dockerfile"))
    shutil.copy2(os.path.join(root, "deploy", "requirements.txt"), os.path.join(stage, "requirements.txt"))
    with open(os.path.join(stage, "README.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(README)
    with open(os.path.join(stage, ".gitattributes"), "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(f"*.{e} filter=lfs diff=lfs merge=lfs -text\n" for e in LFS_EXTENSIONS))
    sha, dirty = git_info(root)
    if version is None:
        from matter import __version__ as version  # type: ignore[no-redef]
    info = {"matter_version": version, "git_sha": sha, "git_dirty": dirty, "built_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "frontend_index_sha256": sha256_file(index), "checkpoint_sha256": shipped.get("perov5-2k", CKPT_SHA256),
            "checkpoints": shipped, "engine_snapshot_sha256": sha256_file(os.path.join(stage, "engine", "SNAPSHOT.json"))}
    with open(os.path.join(stage, "build_info.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(info, f, indent=1)
    # text files with LF line endings, no secrets anywhere
    total = 0
    for d, _, files in os.walk(stage):
        for name in files:
            p = os.path.join(d, name)
            total += os.path.getsize(p)
            if name.lower().endswith(TEXT_TYPES):
                with open(p, "rb") as f:
                    data = f.read()
                if b"\r" in data:
                    while b"\r\n" in data:
                        data = data.replace(b"\r\n", b"\n")
                    with open(p, "wb") as f:
                        f.write(data)
                if SECRET_RE.search(data.decode("utf-8", "replace")):
                    raise SystemExit(f"a token-like string is in {os.path.relpath(p, stage)}; nothing was uploaded")
    sizes = {}
    for top in sorted(os.listdir(stage)):
        p = os.path.join(stage, top)
        sizes[top] = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(p) for f in fs) if os.path.isdir(p) else os.path.getsize(p)
    for top, n in sorted(sizes.items(), key=lambda kv: -kv[1]):
        print(f"  {n / 1e6:6.1f} MB  {top}")
    if total > MAX_STAGE_MB * 1024 * 1024:
        raise SystemExit(f"the bundle is {total / 1e6:.0f} MB, above the {MAX_STAGE_MB} MB cap")
    print(f"staged {stage} ({total / 1e6:.1f} MB)")
    return stage


def check_live(host: str, tries: int = 30, log=print) -> None:
    paths = ["/health", "/", "/api/projects/perov5-demo", "/p/perov5-demo/goal", "/favicon.svg",
             "/api/pipeline/blocks", "/api/studies", "/api/studies/mp20", "/api/checkpoints", "/pipeline", "/studies/mp20", "/play"]
    for path in paths:
        ok = False
        for _ in range(tries):
            try:
                with urllib.request.urlopen(f"https://{host}{path}", timeout=30) as r:
                    ok = r.status == 200
            except Exception:
                ok = False
            if ok:
                break
            time.sleep(5)
        log(f"  {path:28s} {'200' if ok else 'FAILED'}")
        if not ok:
            raise SystemExit(f"https://{host}{path} did not answer 200")
    # the generator and the judge load in a warm-start thread: give them a few minutes, then insist
    for _ in range(tries):
        try:
            with urllib.request.urlopen(f"https://{host}/health", timeout=30) as r:
                h = json.load(r)
        except Exception:
            h = {}
        if h.get("generation_model_loaded") and h.get("judge_ready"):
            log(f"  engine {h.get('engine', {}).get('version')}  symmetry decoder {h.get('engine', {}).get('symmetry_decoder')}  judge ready")
            return
        time.sleep(10)
    raise SystemExit(f"https://{host}/health never reported the generator and the judge as ready: {h}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=TARGET)
    ap.add_argument("--allow-other-space", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--build", action="store_true", help="run npm ci and npm run build first")
    ap.add_argument("--wait", type=int, default=900, help="seconds to wait for the Space to run")
    ap.add_argument("--hardware", default="cpu-basic")
    a = ap.parse_args(argv)
    if a.repo.lower() != TARGET.lower() and not a.allow_other_space:
        sys.exit(f"refusing: this script deploys {TARGET} only; {' and '.join(PROTECTED)} are other products. "
                 "Pass --allow-other-space to deploy a copy elsewhere on purpose.")
    if a.build or not frontend_is_fresh(ROOT):
        print("building the frontend ..." if a.build else "the frontend build is older than the sources: building ...")
        build_frontend(ROOT)
    stage = build_stage(ROOT, STAGE, allow_missing=a.dry_run)
    if a.dry_run:
        print("dry run: nothing uploaded")
        return
    token = os.environ.get("HF_TOKEN")
    if not token:
        sys.exit("set HF_TOKEN in the environment for this command (a Hugging Face write token); it is never stored")
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    from huggingface_hub import HfApi
    api = HfApi(token=token)
    print("logged in as", api.whoami()["name"])
    try:
        info = api.space_info(a.repo)
        if getattr(info, "sdk", None) not in (None, "docker"):
            print(f"the Space uses the {info.sdk} SDK: recreating it as a Docker Space")
            api.delete_repo(a.repo, repo_type="space")
            info = None
    except Exception:
        info = None
    if info is None:
        api.create_repo(a.repo, repo_type="space", space_sdk="docker", space_hardware=a.hardware, exist_ok=True)
    with open(os.path.join(stage, "build_info.json"), encoding="utf-8") as f:
        bi = json.load(f)
    api.upload_folder(folder_path=stage, repo_id=a.repo, repo_type="space",
                      commit_message=f"Deploy MEIDNet Matter {bi['matter_version']} ({bi['git_sha'][:7]})", delete_patterns=["*"])
    print(f"uploaded -> https://huggingface.co/spaces/{a.repo}  (building...)")
    t0 = time.time()
    stage_name = None
    while time.time() - t0 < a.wait:
        stage_name = api.get_space_runtime(a.repo).stage
        print(f"  {time.time() - t0:5.0f}s  {stage_name}")
        if stage_name == "RUNNING":
            break
        if stage_name in ("BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR"):
            sys.exit(f"the Space ended in {stage_name}: see https://huggingface.co/spaces/{a.repo}?logs=build")
        time.sleep(10)
    if stage_name != "RUNNING":
        sys.exit("the Space did not reach RUNNING in time")
    host = space_host(a.repo)
    check_live(host)
    print(f"live: https://{host}/")


if __name__ == "__main__":
    main()
