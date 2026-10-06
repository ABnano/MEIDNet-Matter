"""Fetch the model files the demo project uses, with their checksums.

    python scripts/fetch_assets.py                  # -> checkpoints/<file> (skips files already present and correct)
    python scripts/fetch_assets.py --dest other/    # another folder

Each file is tried from GitHub first, then from the Hugging Face mirror, written to <name>.part and renamed only when
its sha256 matches. A wrong checksum is an error, never a silent keep.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import urllib.request

ASSETS = {
    "dual_autoencoder_clip_earlyfusion_propertyaware_2k.pth": {
        "sha256": "f9493781d5bbb05dfe106874269496c4c1c0364ae9e543703625c8d1efd60c87",
        "urls": ["https://github.com/ABnano/MEIDNet/raw/main/checkpoints/dual_autoencoder_clip_earlyfusion_propertyaware_2k.pth",
                 "https://huggingface.co/Babu09/MEIDNet/resolve/main/dual_autoencoder_clip_earlyfusion_propertyaware_2k.pth"],
    },
    "meidnet_paper_rerun_seed3.pth": {
        "sha256": "205de8b833900c54841d9dcfe3510a8e4a8a4bb9bbf5516d80cb68a7fc121889",
        "urls": ["https://huggingface.co/Babu09/MEIDNet/resolve/main/reproduction/meidnet_paper_rerun_seed3.pth"],
    },
}


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(name: str, dest: str, log=print) -> str:
    spec = ASSETS[name]
    path = os.path.join(dest, name)
    if os.path.exists(path) and sha256_of(path) == spec["sha256"]:
        log(f"present  {name}")
        return path
    os.makedirs(dest, exist_ok=True)
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", default="checkpoints")
    ap.add_argument("--only", nargs="*", default=None, help="file names to fetch (default: all)")
    a = ap.parse_args(argv)
    for name in a.only or ASSETS:
        if name not in ASSETS:
            raise SystemExit(f"unknown asset {name}; known: {', '.join(ASSETS)}")
        fetch(name, a.dest)


if __name__ == "__main__":
    sys.exit(main())
