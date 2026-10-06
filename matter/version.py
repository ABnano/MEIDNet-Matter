"""What is running: versions of Matter, the engine and the libraries, and the git commit. Every run manifest embeds it."""
from __future__ import annotations

import datetime as _dt
import json
import os
import platform
import subprocess
import sys
from functools import lru_cache
from importlib import metadata

from matter import __version__
from matter.settings import ROOT


def _installed(dist: str) -> str | None:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return None


def _git_sha() -> tuple[str, bool]:
    """(commit, dirty) of the source checkout, or ("unknown", False) when not running from one."""
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        return "unknown", False
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout
        return (sha or "unknown"), bool(status.strip())
    except (OSError, subprocess.SubprocessError):
        return "unknown", False


@lru_cache(maxsize=1)
def build_info(build_info_path: str | None = None, public: bool = False) -> dict:
    import meidnet

    info = {
        "matter": __version__,
        "matter_installed": _installed("meidnet-matter"),
        "meidnet": meidnet.__version__,
        "meidnet_installed": _installed("meidnet"),
        "torch": _installed("torch"),
        "pymatgen": _installed("pymatgen"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "git_sha": os.environ.get("MATTER_GIT_SHA") or None,
        "git_dirty": None,
        "built_at": None,
        "mode": "public" if public else "local",
        "space_id": os.environ.get("SPACE_ID"),
    }
    if build_info_path and os.path.exists(build_info_path):
        with open(build_info_path, encoding="utf-8") as f:
            recorded = json.load(f)
        info["git_sha"] = info["git_sha"] or recorded.get("git_sha")
        info["git_dirty"] = recorded.get("git_dirty")
        info["built_at"] = recorded.get("built_at")
    if not info["git_sha"]:
        info["git_sha"], info["git_dirty"] = _git_sha()
    info["started_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    return info
