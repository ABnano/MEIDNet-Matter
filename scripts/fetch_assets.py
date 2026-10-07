"""Fetch the model files, with their checksums.

    python scripts/fetch_assets.py                     # every checkpoint the Space ships  -> checkpoints/<file>
    python scripts/fetch_assets.py --only mp20-wyck    # one, by id or file name
    python scripts/fetch_assets.py --all               # also the release-only ones (replicates, ablations)
    python scripts/fetch_assets.py --judges            # the CGCNN judge files
    python scripts/fetch_assets.py --dest other/       # another folder

The table is checkpoints/manifest.json.  Each file is tried from its urls in order (the GitHub release first, then the
Hugging Face mirror), written to <name>.part and renamed only when its sha256 matches.  A wrong checksum is an error,
never a silent keep.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MANIFEST = os.path.join(ROOT, "checkpoints", "manifest.json")

# the two files that predate the manifest; kept so older instructions still work
LEGACY = {
    "dual_autoencoder_clip_earlyfusion_propertyaware_2k.pth": {
        "sha256": "f9493781d5bbb05dfe106874269496c4c1c0364ae9e543703625c8d1efd60c87",
        "urls": ["https://github.com/ABnano/MEIDNet/raw/main/checkpoints/dual_autoencoder_clip_earlyfusion_propertyaware_2k.pth",
                 "https://huggingface.co/Babu09/MEIDNet/resolve/main/dual_autoencoder_clip_earlyfusion_propertyaware_2k.pth"]},
    "meidnet_paper_rerun_seed3.pth": {
        "sha256": "205de8b833900c54841d9dcfe3510a8e4a8a4bb9bbf5516d80cb68a7fc121889",
        "urls": ["https://huggingface.co/Babu09/MEIDNet/resolve/main/reproduction/meidnet_paper_rerun_seed3.pth"]},
}


def load_assets() -> dict:
    """file name -> {sha256, urls, id, ship, judge} from the manifest, plus the legacy entries."""
    assets = {name: dict(spec, id=name, ship=False, judge=False) for name, spec in LEGACY.items()}
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as f:
            manifest = json.load(f)
        for e in manifest.get("checkpoints", []):
            if "file" in e and e.get("sha256"):
                assets[e["file"]] = {"sha256": e["sha256"], "urls": e.get("urls", []), "id": e["id"], "ship": bool(e.get("ship")), "judge": False}
            for part in e.get("files", []) or []:
                if part.get("sha256"):
                    name = os.path.basename(part["file"])
                    assets[name] = {"sha256": part["sha256"], "urls": part.get("urls", []), "id": e["id"], "ship": False, "judge": True,
                                    "subdir": os.path.dirname(part["file"])}
    return assets


ASSETS = load_assets()


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve(name_or_id: str) -> list[str]:
    """File names for an id or a file name; an unknown name is an error."""
    if name_or_id in ASSETS:
        return [name_or_id]
    files = [n for n, spec in ASSETS.items() if spec["id"] == name_or_id]
    if not files:
        raise SystemExit(f"no asset {name_or_id!r}; known: {', '.join(sorted({s['id'] for s in ASSETS.values()}))}")
    return files


def fetch(name: str, dest: str, log=print) -> str:
    for n in resolve(name):
        name = n
    spec = ASSETS[name]
    folder = os.path.join(dest, spec.get("subdir", "")) if spec.get("subdir") else dest
    path = os.path.join(folder, name)
    if os.path.exists(path) and sha256_of(path) == spec["sha256"]:
        log(f"present  {name}")
        return path
    os.makedirs(folder, exist_ok=True)
    errors = []
    for url in spec["urls"]:
        part = path + ".part"
        try:
            log(f"download {name} from {url.split('/')[2]} ...")
            urllib.request.urlretrieve(url, part)
            got = sha256_of(part)
            if got != spec["sha256"]:
                os.remove(part)
                errors.append(f"{url}: sha256 {got[:12]} != {spec['sha256'][:12]}")
                continue
            os.replace(part, path)
            log(f"ok       {name} ({os.path.getsize(path):,} bytes)")
            return path
        except OSError as e:
            errors.append(f"{url}: {e}")
            if os.path.exists(part):
                os.remove(part)
    raise SystemExit(f"could not fetch {name}:\n  " + "\n  ".join(errors))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", default=os.path.join(ROOT, "checkpoints"))
    ap.add_argument("--only", nargs="*", help="ids or file names")
    ap.add_argument("--all", action="store_true", help="also the release-only checkpoints")
    ap.add_argument("--judges", action="store_true", help="also the judge files")
    a = ap.parse_args(argv)
    if a.only:
        names = [n for x in a.only for n in resolve(x)]
    else:
        names = [n for n, s in ASSETS.items() if s["ship"] or (a.all and not s["judge"] and n not in LEGACY) or (a.judges and s["judge"])]
        if not names:                                      # no manifest: the legacy demo model
            names = ["dual_autoencoder_clip_earlyfusion_propertyaware_2k.pth"]
    for n in names:
        fetch(n, a.dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
