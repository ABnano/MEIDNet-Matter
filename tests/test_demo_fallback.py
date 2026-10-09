"""A checkpoints folder from before 0.8.0 holds only the published model: the demo then runs on it and /health says why,
instead of failing at the first search."""
import os
import shutil

from tests.conftest import make_client


def test_the_demo_falls_back_to_a_model_that_is_present(settings, checkpoint, tmp_path):
    import json
    from tests.conftest import DEMO_DIR
    default = json.load(open(os.path.join(DEMO_DIR, "project.json"), encoding="utf-8"))["default_model"]
    only = tmp_path / "checkpoints"
    only.mkdir()
    shutil.copyfile(checkpoint, only / os.path.basename(checkpoint))       # the published model alone
    settings.checkpoints_dir = str(only)
    with make_client(settings) as c:
        project = c.get("/api/projects/perov5-demo").json()
        assert project["default_model"] == "meidnet-2k" and project["default_goal"]["model_id"] == "meidnet-2k"
        h = c.get("/health").json()
        assert h["model_loaded"] is True and any(default in n and "fetch_assets" in n for n in h["notes"])
