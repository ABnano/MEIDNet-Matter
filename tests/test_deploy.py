"""The deploy tooling, offline: the guard, the LFS list, the card, the bundle layout, no tokens in the tree."""
import codecs
import importlib.util
import json
import os
import re

import pytest

from tests.conftest import ROOT


def _deploy():
    spec = importlib.util.spec_from_file_location("deploy_space", os.path.join(ROOT, "deploy", "deploy_space.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _is_binary(path):
    with open(path, "rb") as f:
        head = f.read(4096)
    if b"\0" in head:
        return True
    try:
        codecs.getincrementaldecoder("utf-8")().decode(head, final=False)
        return False
    except UnicodeDecodeError:
        return True


def test_other_spaces_are_refused(monkeypatch):
    mod = _deploy()
    for repo in ("Babu09/MEIDNet", "Babu09/MEIDNet-Prism", "someone/else"):
        with pytest.raises(SystemExit) as e:
            mod.main(["--repo", repo, "--dry-run"])
        assert "refusing" in str(e.value) and "--allow-other-space" in str(e.value)
    monkeypatch.setattr(mod, "build_stage", lambda *a, **k: "stage")
    monkeypatch.setattr(mod, "frontend_is_fresh", lambda root: True)
    mod.main(["--repo", "babu09/meidnet-matter", "--dry-run"])                  # the target, in any case


def test_every_binary_in_the_bundle_sources_is_listed_for_lfs():
    lfs = set(_deploy().LFS_EXTENSIONS)
    missing = []
    for folder in ("examples", os.path.join("frontend", "public"), os.path.join("matter", "static")):
        for d, _, files in os.walk(os.path.join(ROOT, folder)):
            for name in files:
                p = os.path.join(d, name)
                if _is_binary(p) and name.rsplit(".", 1)[-1].lower() not in lfs:
                    missing.append(os.path.relpath(p, ROOT))
    assert not missing, f"binary files whose type is not in LFS_EXTENSIONS: {missing}"


def test_space_card_and_dockerfile_agree():
    mod = _deploy()
    front = mod.README.split("---")[1]
    fields = dict(line.split(":", 1) for line in front.strip().splitlines() if ":" in line)
    assert fields["thumbnail"].strip().startswith("https://")
    assert len(fields["short_description"].strip()) <= 60
    assert fields["sdk"].strip() == "docker" and fields["models"].strip() == "[Babu09/MEIDNet]"
    with open(os.path.join(ROOT, "deploy", "Dockerfile"), encoding="utf-8") as f:
        docker = f.read()
    assert f'"--port", "{fields["app_port"].strip()}"' in docker and f"EXPOSE {fields['app_port'].strip()}" in docker
    assert mod.space_host("Babu09/MEIDNet-Matter") == "babu09-meidnet-matter.hf.space"


def test_requirements_take_the_engine_from_the_bundle_not_pypi():
    with open(os.path.join(ROOT, "deploy", "requirements.txt"), encoding="utf-8") as f:
        req = f.read()
    with open(os.path.join(ROOT, "deploy", "Dockerfile"), encoding="utf-8") as f:
        docker = f.read()
    with open(os.path.join(ROOT, "engine", "pyproject.toml"), encoding="utf-8") as f:
        engine = f.read()
    assert not re.search(r"^meidnet", req, re.M), "the engine is installed from ./engine, never from PyPI"
    assert "pip install --no-cache-dir --no-deps ./engine" in docker and "download.pytorch.org/whl/cpu" in docker
    assert re.search(r'^name = "meidnet"', engine, re.M) and 'version = "2.4.0' in engine
    for dep in ("matgl==4.0.3", "torch-geometric", "pymatgen", "pandas", "scipy", "ase", "spglib"):
        assert dep in req, dep


def _fake_tree(root, mod, token_in_tree=False):
    (root / "matter" / "static").mkdir(parents=True)
    (root / "matter" / "__init__.py").write_text('__version__ = "9.9.9"\n', encoding="utf-8")
    (root / "matter" / "static" / "index.html").write_bytes(b"<!doctype html>\r\n<title>x</title>\r\n")
    (root / "matter" / "__pycache__").mkdir()
    (root / "matter" / "__pycache__" / "x.pyc").write_bytes(b"\0\0")
    if token_in_tree:
        (root / "matter" / "leak.txt").write_text("token hf_" + "a" * 34 + " here", encoding="utf-8")
    (root / "examples" / "perov5").mkdir(parents=True)
    (root / "examples" / "perov5" / "project.json").write_text("{}", encoding="utf-8")
    (root / "examples" / "research" / "pipeline").mkdir(parents=True)
    (root / "examples" / "research" / "pipeline" / "blocks.json").write_text("{}", encoding="utf-8")
    (root / "engine" / "meidnet").mkdir(parents=True)
    (root / "engine" / "SNAPSHOT.json").write_text("{}", encoding="utf-8")
    (root / "engine" / "meidnet" / "__init__.py").write_text("", encoding="utf-8")
    (root / "engine" / "meidnet" / "__pycache__").mkdir()
    (root / "engine" / "meidnet" / "__pycache__" / "y.pyc").write_bytes(b"\0")
    (root / "engine" / "tests").mkdir()
    (root / "engine" / "tests" / "test_x.py").write_text("", encoding="utf-8")
    (root / "checkpoints" / "configs").mkdir(parents=True)
    (root / "checkpoints" / "configs" / "a.yaml").write_text("x: 1\n", encoding="utf-8")
    (root / "checkpoints" / mod.CKPT_NAME).write_bytes(b"model")
    (root / "checkpoints" / "other.pt").write_bytes(b"m2")
    manifest = {"checkpoints": [
        {"id": "perov5-2k", "file": mod.CKPT_NAME, "sha256": mod.CKPT_SHA256, "ship": True},
        {"id": "other", "file": "other.pt", "sha256": "abc", "ship": True},
        {"id": "missing", "file": "missing.pt", "sha256": "abc", "ship": True},
        {"id": "kept-back", "file": "kept_back.pt", "sha256": "abc", "ship": False}]}
    (root / "checkpoints" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "deploy").mkdir()
    (root / "deploy" / "Dockerfile").write_text("FROM x\n", encoding="utf-8")
    (root / "deploy" / "requirements.txt").write_text("fastapi\n", encoding="utf-8")


def test_stage_layout_on_a_fake_tree(tmp_path, monkeypatch):
    mod = _deploy()
    root = tmp_path / "repo"
    _fake_tree(root, mod)
    monkeypatch.setattr(mod, "MANIFEST", str(root / "checkpoints" / "manifest.json"))
    monkeypatch.setattr(mod, "sha256_file", lambda p: mod.CKPT_SHA256 if p.endswith(".pth") else "abc")
    with pytest.raises(SystemExit) as e:                                        # a shipped checkpoint that is not on disk
        mod.build_stage(str(root), str(tmp_path / "stage0"), fetch=False, version="9.9.9")
    assert "missing.pt" in str(e.value) and "--only missing" in str(e.value)
    stage = mod.build_stage(str(root), str(tmp_path / "stage"), fetch=False, version="9.9.9", allow_missing=True)
    names = {os.path.relpath(os.path.join(d, f), stage).replace(os.sep, "/") for d, _, fs in os.walk(stage) for f in fs}
    assert {"README.md", ".gitattributes", "build_info.json", "requirements.txt", "Dockerfile", "matter/static/index.html",
            "examples/perov5/project.json", "examples/research/pipeline/blocks.json", f"checkpoints/{mod.CKPT_NAME}",
            "checkpoints/other.pt", "checkpoints/manifest.json", "checkpoints/configs/a.yaml",
            "engine/SNAPSHOT.json", "engine/meidnet/__init__.py"} <= names
    assert "checkpoints/kept_back.pt" not in names and "checkpoints/missing.pt" not in names
    assert not any("__pycache__" in n for n in names) and not any(n.startswith("engine/tests/") for n in names)
    assert b"\r\n" not in (tmp_path / "stage" / "matter" / "static" / "index.html").read_bytes()
    info = json.loads((tmp_path / "stage" / "build_info.json").read_text(encoding="utf-8"))
    assert info["matter_version"] == "9.9.9" and info["checkpoint_sha256"] == mod.CKPT_SHA256
    assert info["checkpoints"] == {"perov5-2k": mod.CKPT_SHA256, "other": "abc"} and info["engine_snapshot_sha256"] == "abc"
    attrs = (tmp_path / "stage" / ".gitattributes").read_text(encoding="utf-8")
    assert "*.pth filter=lfs" in attrs and "*.npz filter=lfs" in attrs and "*.pt filter=lfs" in attrs


def test_a_token_in_the_stage_aborts(tmp_path, monkeypatch):
    mod = _deploy()
    root = tmp_path / "repo"
    _fake_tree(root, mod, token_in_tree=True)
    monkeypatch.setattr(mod, "MANIFEST", str(root / "checkpoints" / "manifest.json"))
    monkeypatch.setattr(mod, "sha256_file", lambda p: mod.CKPT_SHA256 if p.endswith(".pth") else "abc")
    with pytest.raises(SystemExit) as e:
        mod.build_stage(str(root), str(tmp_path / "stage"), fetch=False, version="0", allow_missing=True)
    assert "token-like" in str(e.value)


def test_no_tokens_committed():
    pattern = re.compile(r"\b(hf_[A-Za-z0-9]{30,}|ghp_[A-Za-z0-9]{30,}|pypi-[A-Za-z0-9_-]{40,})\b")
    hits = []
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in (".git", "node_modules", "build", "checkpoints", "data", "runs", "static", ".pytest_cache")]
        for name in files:
            if name.rsplit(".", 1)[-1].lower() in ("py", "md", "json", "yml", "yaml", "txt", "ts", "tsx", "js", "mjs", "html", "css", "toml", "cff"):
                with open(os.path.join(d, name), encoding="utf-8", errors="replace") as f:
                    if pattern.search(f.read()):
                        hits.append(os.path.relpath(os.path.join(d, name), ROOT))
    assert not hits, hits
