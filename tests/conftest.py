"""Test fixtures. Nothing touches the real home folder: HOME/USERPROFILE and every Matter path point into a temporary
folder for the whole session. Tests that need a model file skip when it is not fetched (scripts/fetch_assets.py)."""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from matter.settings import DEFAULT_CHECKPOINT, Settings  # noqa: E402

CHECKPOINT = os.path.join(ROOT, "checkpoints", DEFAULT_CHECKPOINT)
DEMO_DIR = os.path.join(ROOT, "examples", "perov5")


@pytest.fixture(scope="session", autouse=True)
def _isolated_home(tmp_path_factory):
    home = tmp_path_factory.mktemp("home")
    mp = pytest.MonkeyPatch()
    for var in ("HOME", "USERPROFILE", "HF_HOME"):
        mp.setenv(var, str(home))
    mp.setenv("MPLBACKEND", "Agg")
    for var in ("MATTER_PUBLIC", "MATTER_RUN_ROOT", "MATTER_CHECKPOINT", "MATTER_CHECKPOINTS_DIR", "MATTER_DEMO_DIR",
                "MATTER_STATIC_DIR", "MATTER_CORS_ORIGINS", "MATTER_BUILD_INFO"):
        mp.delenv(var, raising=False)
    yield
    mp.undo()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(public=False, run_root=str(tmp_path / "runs"), checkpoints_dir=os.path.join(ROOT, "checkpoints"),
                    demo_dir=DEMO_DIR, static_dir=str(tmp_path / "static"))


@pytest.fixture
def public_settings(settings) -> Settings:
    settings.public = True
    settings.torch_threads = 2
    return settings


def make_client(settings: Settings):
    from fastapi.testclient import TestClient
    from matter.app import create_app
    return TestClient(create_app(settings))


@pytest.fixture
def client(settings):
    with make_client(settings) as c:
        yield c


@pytest.fixture
def checkpoint() -> str:
    if not os.path.exists(CHECKPOINT):
        pytest.skip(f"model file not fetched: run python scripts/fetch_assets.py (expected {CHECKPOINT})")
    try:
        import torch  # noqa: F401
    except OSError as e:                    # Smart App Control can block torch's DLLs on the development laptop
        pytest.skip(f"torch cannot be imported here: {e}")
    return CHECKPOINT
