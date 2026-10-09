"""MEIDNet Matter from Python: the same three stages as the site, against a running server.

    from matter.client import Matter
    m = Matter("https://babu09-meidnet-matter.hf.space")      # or a local server, http://127.0.0.1:8000

    # Explore: the dataset's map and one material
    points = m.explore()                                       # every training material: id, formula, x, y, properties, sites
    sro = m.material("mp-5229")                                # its values, its cell, its nearest neighbours in the latent space

    # Train Lite: a small MEIDNet training (10, 20 or 50 epochs on 1,500 Perov-5 materials), followed to the end
    job = m.train(epochs=20, seed=0)
    job = m.wait(job)                                          # polls until done; job["history"] holds the curves
    print(job["result"]["against_spread"])                     # error against the spread, next to the full model's
    m.download(m.urls.train_model(job["job_id"]), "lite.pt")   # the checkpoint itself

    # Generate: structures for a band gap, read by two models
    gen = m.wait(m.generate(targets=[2.0], per_target=4))
    for c in gen["candidates"]:
        print(c["formula"], c["label_structure_eV"], c["judge_eV"], c["statuses"])
    m.download(m.urls.generate_zip(gen["job_id"]), "cells.zip")

    # The Perov-5 demo: readiness, then a search within the family
    goal = m.project()["default_goal"]
    report = m.readiness(goal)
    run = m.wait(m.search(goal, acknowledge_exploratory=report["exploratory_required"]))
    cands = m.candidates(run["run_id"])

Every call returns the server's JSON as plain dicts and lists; errors raise MatterError with the server's code and
message. The client needs only the standard library; pass `transport` to route requests elsewhere (the tests route
them through the application in-process).
"""
from __future__ import annotations

import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

Transport = Callable[[str, str, bytes | None, dict], tuple[int, bytes, dict]]


class MatterError(Exception):
    """A non-2xx answer: the server's error code, message and status."""

    def __init__(self, status: int, code: str, message: str, fields: list | None = None, retry_after_s: int | None = None):
        super().__init__(f"{code}: {message}")
        self.status, self.code, self.message, self.fields, self.retry_after_s = status, code, message, fields or [], retry_after_s


class _Urls:
    """Download addresses, for a browser or `Matter.download`."""

    def __init__(self, base: str):
        self.base = base

    def cif(self, run_id: str, candidate_id: str) -> str:
        return f"{self.base}/api/runs/{run_id}/candidates/{candidate_id}/cif"

    def bundle(self, run_id: str) -> str:
        return f"{self.base}/api/runs/{run_id}/export/bundle.zip"

    def candidates_csv(self, run_id: str) -> str:
        return f"{self.base}/api/runs/{run_id}/export/candidates.csv"

    def generate_cif(self, job_id: str, candidate_id: str) -> str:
        return f"{self.base}/api/generate/{job_id}/candidates/{candidate_id}/cif"

    def generate_zip(self, job_id: str) -> str:
        return f"{self.base}/api/generate/{job_id}/export/cifs.zip"

    def train_model(self, job_id: str) -> str:
        return f"{self.base}/api/train/{job_id}/model.pt"

    def train_config(self, job_id: str) -> str:
        return f"{self.base}/api/train/{job_id}/config.yaml"

    def train_predictions(self, job_id: str) -> str:
        return f"{self.base}/api/train/{job_id}/predictions.csv"


def _urllib_transport(method: str, url: str, body: bytes | None, headers: dict) -> tuple[int, bytes, dict]:
    req = urllib.request.Request(url, method=method, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


class Matter:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", session: str | None = None, transport: Transport | None = None):
        self.base = base_url.rstrip("/")
        # one session per client: on the shared server a session runs one job at a time and owns its stop
        self.session = session or "py-" + secrets.token_urlsafe(8)
        self._transport = transport or _urllib_transport
        self.urls = _Urls(self.base)

    # ── plumbing ──
    def _call(self, method: str, path: str, body: Any = None, params: dict | None = None) -> Any:
        url = self.base + path + (("?" + urllib.parse.urlencode(params)) if params else "")
        headers = {"Accept": "application/json", "X-Matter-Session": self.session}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        status, raw, _ = self._transport(method, url, data, headers)
        payload = json.loads(raw) if raw else None
        if status >= 400:
            err = (payload or {}).get("error", {}) if isinstance(payload, dict) else {}
            raise MatterError(status, err.get("code", "http_error"), err.get("message", f"HTTP {status}"), err.get("fields"), err.get("retry_after_s"))
        return payload

    def download(self, url: str, path: str) -> str:
        """Save a file the server offers (a CIF, a zip, a checkpoint) and return its path."""
        status, raw, _ = self._transport("GET", url, None, {"X-Matter-Session": self.session})
        if status >= 400:
            try:
                err = json.loads(raw).get("error", {})
            except Exception:
                err = {}
            raise MatterError(status, err.get("code", "http_error"), err.get("message", f"HTTP {status}"))
        with open(path, "wb") as f:
            f.write(raw)
        return path

    def wait(self, job: dict, timeout: float = 900, every: float = 2.0) -> dict:
        """Poll a generation, training or search job until it is no longer queued or running; return its full record."""
        key = "job_id" if "job_id" in job else "run_id"
        jid = job[key]
        kind = "train" if jid.startswith("lite-") else "generate" if jid.startswith("gen-") else "runs"
        t0 = time.time()
        while True:
            full = self._call("GET", f"/api/{kind}/{jid}", params={"view": "full"})
            if full["status"] not in ("queued", "running"):
                return full
            if time.time() - t0 > timeout:
                raise TimeoutError(f"{jid} still {full['status']} after {timeout:.0f} s")
            time.sleep(every)

    # ── the server ──
    def health(self) -> dict:
        return self._call("GET", "/health")

    def version(self) -> dict:
        return self._call("GET", "/api/version")

    # ── Explore ──
    def project(self, project_id: str = "perov5-demo") -> dict:
        return self._call("GET", f"/api/projects/{project_id}")

    def dataset(self, project_id: str = "perov5-demo") -> dict:
        return self._call("GET", f"/api/projects/{project_id}/dataset")

    def explore(self, project_id: str = "perov5-demo") -> list[dict]:
        """Every training material as a dict: material_id, formula, x, y (the latent map), the properties, site_key."""
        payload = self._call("GET", f"/api/explore/{project_id}")
        cols = payload["columns"]
        return [dict(zip(cols, row)) for row in payload["points"]]

    def material(self, material_id: str, project_id: str = "perov5-demo", k: int = 6) -> dict:
        return self._call("GET", f"/api/explore/{project_id}/materials/{material_id}", params={"k": k})

    def studies(self) -> list[dict]:
        return self._call("GET", "/api/studies")["studies"]

    def study(self, study_id: str) -> dict:
        return self._call("GET", f"/api/studies/{study_id}")

    def checkpoints(self) -> list[dict]:
        return self._call("GET", "/api/checkpoints")["checkpoints"]

    def blocks(self) -> dict:
        return self._call("GET", "/api/pipeline/blocks")

    # ── Train Lite ──
    def train_options(self) -> dict:
        return self._call("GET", "/api/train/options")

    def train(self, epochs: int = 20, seed: int = 0) -> dict:
        return self._call("POST", "/api/train", {"epochs": epochs, "seed": seed})

    def training(self, job_id: str, full: bool = False) -> dict:
        return self._call("GET", f"/api/train/{job_id}", params={"view": "full"} if full else None)

    def trainings(self) -> list[dict]:
        return self._call("GET", "/api/train")

    def stop_training(self, job_id: str) -> dict:
        return self._call("POST", f"/api/train/{job_id}/stop", {})

    # ── Generate ──
    def generate(self, targets: list[float], per_target: int = 4, model_id: str = "mp20-wyck", window_eV: float = 0.5,
                 require_anion: bool = True, exclude_elements: list[str] | None = None, seed: int = 0) -> dict:
        body = {"model_id": model_id, "targets": targets, "per_target": per_target, "window_eV": window_eV, "require_anion": require_anion,
                "exclude_elements": exclude_elements if exclude_elements is not None else ["Ac", "Np", "Pa", "Pm", "Pu", "Tc", "Th", "U"], "seed": seed}
        return self._call("POST", "/api/generate", body)

    def generation(self, job_id: str, full: bool = False) -> dict:
        return self._call("GET", f"/api/generate/{job_id}", params={"view": "full"} if full else None)

    def generations(self) -> list[dict]:
        return self._call("GET", "/api/generate")

    def stop_generation(self, job_id: str) -> dict:
        return self._call("POST", f"/api/generate/{job_id}/stop", {})

    # ── the Perov-5 demo: readiness, search, candidates ──
    def validate_goal(self, goal: dict) -> dict:
        return self._call("POST", "/api/goals/validate", goal)

    def readiness(self, goal: dict) -> dict:
        return self._call("POST", "/api/readiness", goal)

    def search(self, goal: dict, acknowledge_exploratory: bool = False) -> dict:
        return self._call("POST", "/api/runs", {"goal": goal, "acknowledge_exploratory": acknowledge_exploratory})

    def run(self, run_id: str, full: bool = False) -> dict:
        return self._call("GET", f"/api/runs/{run_id}", params={"view": "full"} if full else None)

    def runs(self) -> list[dict]:
        return self._call("GET", "/api/runs")

    def stop_run(self, run_id: str) -> dict:
        return self._call("POST", f"/api/runs/{run_id}/stop", {})

    def candidates(self, run_id: str) -> list[dict]:
        return self._call("GET", f"/api/runs/{run_id}/candidates")

    def candidate(self, run_id: str, candidate_id: str) -> dict:
        return self._call("GET", f"/api/runs/{run_id}/candidates/{candidate_id}")

    def compare(self, run_id: str, candidate_ids: list[str]) -> dict:
        return self._call("POST", f"/api/runs/{run_id}/compare", {"candidate_ids": candidate_ids})

    def manifest(self, run_id: str) -> dict:
        return self._call("GET", f"/api/runs/{run_id}/manifest")
