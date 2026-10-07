"""
The Studio's server: serves the page, a small JSON API and (optionally) the documentation site.

Everything scientific happens in the same Python functions the command line uses
(``load_family``, ``enumerate_space``, ``Designer``, ``fit``), so what the page shows is what
``meidnet`` would do with the exported YAML.

Local use:      meidnet studio [meidnet.yaml]            (127.0.0.1, one user, no limits)
Public hosting: python -m meidnet.studio.server --host 0.0.0.0 --port 7860 --public --docs-dir site
                 • every browser tab gets its own session (a random id it generates): its
                   uploaded data, its trained model, its searches
                 • budgets are capped and only built-in families can be loaded
                 • at most MAX_RUNNING searches/trainings run at once; others are told to retry

API (all POST bodies are JSON; `session` is the tab's id)
    GET  /                          the page
    GET  /api/state?session=        model (published or the session's own), config, variants, limits
    GET  /api/data?session=         data summary (published Perov-5 or the session's upload)
    POST /api/data/upload           {session, files:[{name, b64}]} → columns, row count, suggestions
    POST /api/data/check            {session, id_column, cif_column, properties, family, …} → check summary
    POST /api/train/start           {session, epochs} → trains a model for this session (thread)
    GET  /api/train/status?session=
    POST /api/family                {session, family, variant} → family + design space (session model if any)
    POST /api/search/start          {session, generation} → starts a search in a thread
    GET  /api/search/status?session=
    POST /api/search/stop           {session}
    POST /api/validate              {yaml} or {generation} → normalised generation section or errors
    POST /api/export                {session, generation} → YAML of the configuration
    GET  /files/<path>              files written by sessions (CIFs, reports)
    GET  /docs/…                    the documentation site, if --docs-dir is given
"""
from __future__ import annotations

import argparse
import base64
import copy
import io
import json
import mimetypes
import os
import re
import secrets
import shutil
import sys
import threading
import time
import traceback
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import yaml

from meidnet import __version__
from meidnet.checkpoint import LoadedModel, describe, load_checkpoint, property_ranges
from meidnet.config import GenerationSection, MEIDNetConfig, config_from_dict, dump_config
from meidnet.designspace import enumerate_space
from meidnet.family import list_families, load_family
from meidnet.terms import SEARCH_TERMS

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_RUNNING = 2                       # concurrent searches + trainings on a public host
PUBLIC_LIMITS = {"per_target": 6, "population": 32, "rounds": 6, "steps": 400, "targets": 2,
                 "upload_mb": 8, "rows": 1500, "epochs": 30, "max_sites": 20}
PUBLIC_JOB_SECONDS = 20 * 60          # a public search or training is stopped after this long
PUBLIC_MAX_SESSIONS = 400             # live tabs on a public host
PUBLIC_UNZIPPED_MB = 64               # disk an upload may take once its zip is unpacked
CIF_MAX_KB = 512                      # one CIF file (a 20-site cell is a few kB)
SESSION_TTL = 3600                    # seconds an idle session's files are kept (public host)
SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
RESERVED_SESSIONS = ("local", "localtab")      # shared defaults: never accepted on a public host
# what a visitor of a public host may set in the generation section; everything else keeps the server's value
PUBLIC_GENERATION_KEYS = ("family", "variant", "exclude_elements", "only_elements", "objectives", "targets",
                          "per_target", "population", "rounds", "steps", "seed", "overrides", "extra_constraints",
                          "disabled_rules")
PUBLIC_RULE_PARAMS = ("min", "max", "low", "high", "cutoff")
PUBLIC_MAX_CUTOFF = 8.0               # Å; neighbour searches grow with cutoff³


def _safe_yaml(text: str):
    """yaml.safe_load without anchors/aliases: '*name' references can expand a few hundred bytes of text into
    billions of objects once the settings are copied and serialised."""
    for token in yaml.scan(text, Loader=yaml.SafeLoader):
        if isinstance(token, (yaml.AliasToken, yaml.AnchorToken)):
            raise ValueError(f"YAML anchors and aliases (&name / *name) are not supported here "
                             f"(line {token.start_mark.line + 1}) - write the values out")
    return yaml.safe_load(text)


def default_config(model_path: str, run_root: str | None = None) -> MEIDNetConfig:
    """Config used when the Studio is started without a meidnet.yaml: the published perovskite model."""
    return config_from_dict({
        "name": "studio", "output_dir": run_root or "runs/studio", "model_path": model_path,
        "description": "MEIDNet Studio session (published Perov-5 model)",
        "generation": {
            "family": "perovskite_abx3", "variant": "halide",
            "objectives": [{"property": "dir_gap", "loss": "l2", "weight": 10000, "select_weight": 1.0},
                           {"property": "heat_all", "loss": "l1", "weight": 6000, "select_weight": 0.4}],
            "targets": [{"dir_gap": 2.0, "heat_all": -0.10}],
            "per_target": 3, "population": 24, "rounds": 3, "steps": 300, "min_cosine_sep": 0.98,
        },
    }, base_dir=os.getcwd())


class Job:
    """A background search or training with a progress snapshot the page can poll."""

    def __init__(self, kind: str):
        self.kind = kind
        self.lock = threading.Lock()
        self.running = True
        self.done = False
        self.error = None
        self.log = []
        self.candidates = []
        self.progress = {"target": 0, "targets": 0, "round": 0, "rounds": 0, "step": 0, "steps": 0, "loss": None,
                         "epoch": 0, "epochs": 0, "val": None, "curve": []}
        self.stop_flag = False
        self.report = None
        self.run_dir = None
        self.family = None                     # (family, variant) a search ran in
        self.started = time.time()
        self.finished = None

    def snapshot(self):
        with self.lock:
            return {"kind": self.kind, "running": self.running, "done": self.done, "error": self.error,
                    "log": self.log[-80:], "candidates": self.candidates, "progress": dict(self.progress),
                    "report": self.report, "seconds": (self.finished or time.time()) - self.started,
                    "family": list(self.family) if self.family else None}


EMPTY_STATUS = {"kind": None, "running": False, "done": False, "error": None, "log": [], "candidates": [],
                "progress": {"target": 0, "targets": 0, "round": 0, "rounds": 0, "step": 0, "steps": 0, "loss": None,
                             "epoch": 0, "epochs": 0, "val": None, "curve": []}, "report": None, "seconds": 0,
                "family": None}


class Session:
    """One browser tab: its uploaded data, trained model, enumeration cache and jobs."""

    def __init__(self, sid: str, root: str):
        self.sid = sid
        self.dir = os.path.join(root, "sessions", sid)             # data + model: never served
        self.data_dir = os.path.join(self.dir, "data")
        os.makedirs(self.data_dir, exist_ok=True)
        # reports, CIFs and run files: served under /files/shared/<token>/, so a shared link reveals neither
        # the session id (which controls the tab) nor the uploaded data
        self.share_dir = os.path.join(root, "shared", secrets.token_urlsafe(12))
        self.table_path: str | None = None
        self.structures_dir: str | None = None
        self.columns: list[str] = []
        self.n_rows = 0
        self.n_cifs = 0
        self.cfg: MEIDNetConfig | None = None      # built by /api/data/check
        self.check: dict | None = None
        self.lm: LoadedModel | None = None         # trained by /api/train
        self.use_published = False                 # /api/model/select: ignore the own model
        self.check_info: dict | None = None        # records with structures (for 3D)
        self.space_cache: dict[str, dict] = {}
        self.chem_cache: dict[str, dict] = {}
        self.search: Job | None = None
        self.train: Job | None = None
        self.checking = False                      # a data check is running (counts as busy)
        self.table_name = None                     # the uploaded table's own file name (for the exported YAML)
        self.touched = time.time()

    def touch(self):
        self.touched = time.time()

    @property
    def busy(self) -> bool:
        return self.checking or any(j is not None and j.running for j in (self.search, self.train))


class Studio:
    def __init__(self, cfg: MEIDNetConfig | None, model_path: str | None = None, public: bool = False,
                 run_root: str | None = None, docs_dir: str | None = None):
        self.public = public
        self.run_root = os.path.abspath(run_root or (os.path.join(os.getcwd(), "runs", "studio")))
        os.makedirs(self.run_root, exist_ok=True)
        if cfg is None:
            from meidnet.cli import published_checkpoint
            cfg = default_config(os.path.abspath(model_path or published_checkpoint()), self.run_root)
        elif model_path:
            cfg.model_path = os.path.abspath(model_path)
        self.cfg = cfg
        self.lm = load_checkpoint(cfg.checkpoint_path)
        self.ranges = property_ranges(self.lm)
        self.space_cache: dict[str, dict] = {}
        self.space_lock = threading.Lock()        # guards key_locks only; enumerations lock per (cache, key)
        self.key_locks: dict[tuple, threading.Lock] = {}
        self.chem_cache: dict[str, dict] = {}     # shared 3D datasets (published model / project data)
        self.sessions: dict[str, Session] = {}
        self.sessions_lock = threading.Lock()
        self.jobs_lock = threading.Lock()         # "is a slot free?" and "take it" happen together
        self.train_lock = threading.Lock()        # one training at a time (torch's global random state)
        self.data_summary = None
        self.data_lock = threading.Lock()
        self.docs_dir = os.path.abspath(docs_dir) if docs_dir else None

    # ── sessions ─────────────────────────────────────────────────────────────
    def _sid(self, req: dict | str) -> str:
        s = str((req.get("session") if isinstance(req, dict) else req) or "local")
        if not SESSION_RE.match(s):
            raise ValueError("invalid session id")
        return s

    def session(self, req: dict | str, create: bool = True) -> Session | None:
        """The tab's session. Read-only requests pass create=False: an unknown id then gets the defaults
        without creating anything on the server."""
        sid = self._sid(req)
        with self.sessions_lock:
            s = self.sessions.get(sid)
            if s is None and create:
                if self.public and sid in RESERVED_SESSIONS:   # a shared default id would mix visitors' data
                    raise ValueError("this page needs its own session id - please reload it")
                if self.public and len(self.sessions) >= PUBLIC_MAX_SESSIONS:
                    raise ValueError("too many visitors right now - please try again in a few minutes")
                s = self.sessions[sid] = Session(sid, self.run_root)
            if s:
                s.touch()
            return s

    def _cleanup(self):
        """On a public host, delete the files of tabs idle for SESSION_TTL; a local Studio keeps everything
        (models, searches and reports stay under run_root)."""
        if not self.public:
            return
        now = time.time()
        with self.sessions_lock:
            gone = [self.sessions.pop(sid) for sid, s in list(self.sessions.items())
                    if not s.busy and now - s.touched > SESSION_TTL]
        for s in gone:                             # outside the lock: deleting files can take a while
            shutil.rmtree(s.dir, ignore_errors=True)
            shutil.rmtree(s.share_dir, ignore_errors=True)

    def _key_lock(self, *key) -> threading.Lock:
        with self.space_lock:
            return self.key_locks.setdefault(key, threading.Lock())

    def _running(self) -> int:
        with self.sessions_lock:
            return sum(1 for s in self.sessions.values() for j in (s.search, s.train) if j and j.running)

    def _job_error(self, e: BaseException, what: str) -> str:
        """Message for a failed job: user errors (bad family, too few materials, ...) verbatim; anything else
        as a traceback locally, and without server details on a public host."""
        if isinstance(e, (ValueError, SystemExit)):
            return str(e) or f"{what} failed"
        return f"{what} failed - see the server log" if self.public else traceback.format_exc()

    def _own(self, s: Session | None) -> bool:
        return bool(s and s.lm and not s.use_published)

    def _model_for(self, s: Session | None) -> LoadedModel:
        return s.lm if self._own(s) else self.lm

    # ── state ────────────────────────────────────────────────────────────────
    def family_meta(self, name: str) -> dict:
        fam = load_family(name, default_variant=True)
        return {"name": fam.name, "title": fam.title, "description": fam.description, "variants": fam.variants,
                "n_sites": fam.n_sites, "sites": [{"group": g, "frac": list(f)} for g, f in fam.sites],
                "lattice": fam.lattice, "lattice_rule": fam.lattice_rule}

    def _model_info(self, lm: LoadedModel, own: bool, hide_paths: bool | None = None) -> dict:
        hide = self.public if hide_paths is None else hide_paths
        hist = lm.meta.get("history") or {}
        val = (hist.get("val") or [None])[-1]
        desc = describe(lm)
        if hide:  # do not reveal server paths to visitors
            desc = desc.replace(lm.path, os.path.basename(lm.path))
        return {"description": desc, "legacy": lm.legacy, "own": own,
                "path": os.path.basename(lm.path) if hide else lm.path,
                "properties": lm.stats.to_dict(), "family": lm.family, "max_sites": lm.model.max_sites,
                "latent_dim": getattr(lm.model, "latent_dim", None),
                "validation": val, "note": lm.meta.get("note", ""),
                "history": {"train": [{k: r[k] for k in ("epoch", "total", "cosine") if k in r} for r in hist.get("train", [])],
                            "val": [{"epoch": v.get("epoch"), "mae": v.get("mae"), "retrieval_top1": v.get("retrieval_top1")}
                                    for v in hist.get("val", [])]} if hist else None}

    def _visible_config(self, cfg: MEIDNetConfig, hide_paths: bool | None = None) -> dict:
        """The configuration as the page sees it; on a public host, file paths are reduced to their names."""
        d = json.loads(json.dumps(cfg.model_dump(mode="json"), default=str))
        if self.public if hide_paths is None else hide_paths:
            name = lambda p: os.path.basename(str(p).rstrip("/\\")) if p else p   # noqa: E731
            for key in ("model_path", "output_dir"):
                d[key] = name(d.get(key))
            for key in ("table", "val_table", "structures_dir"):
                if isinstance(d.get("data"), dict) and d["data"].get(key):
                    d["data"][key] = name(d["data"][key])
            d["plugins"] = [name(p) for p in d.get("plugins") or []]
        return d

    def state(self, session: str = "local") -> dict:
        s = self.session(session, create=False)
        lm = self._model_for(s)
        g = self.cfg.generation
        cfg = s.cfg if (s and s.cfg and self._own(s)) else self.cfg
        return {
            "version": __version__, "public": self.public, "limits": PUBLIC_LIMITS if self.public else None,
            "docs_url": "/docs/" if self.docs_dir else None,
            "home_url": "/" if self.docs_dir else None,            # the landing page exists in platform mode only
            "config": self._visible_config(cfg),
            "model": self._model_info(lm, own=self._own(s)),
            "ranges": property_ranges(lm),
            "families": {n: self.family_meta(n) for n in list_families()},
            "current_family": (cfg.generation.family if cfg.generation else None) or (g.family if g else "perovskite_abx3"),
            "terms": {n: SEARCH_TERMS.doc(n) for n in SEARCH_TERMS.names()},
            "has_data": self.cfg.data is not None,
            "session": {"id": s.sid if s else self._sid(session), "has_upload": bool(s and s.table_path),
                        "has_model": bool(s and s.lm),
                        "using_own": self._own(s), "columns": s.columns if s else [], "n_rows": s.n_rows if s else 0,
                        "n_cifs": s.n_cifs if s else 0, "checked": bool(s and s.check), "busy": bool(s and s.busy),
                        "source": (s.table_name or os.path.basename(s.table_path)) if (s and s.table_path) else None},
        }

    # ── data: published / project / uploaded ────────────────────────────────
    def data(self, session: str = "local") -> dict:
        s = self.session(session, create=False)
        if s and s.check:
            return s.check
        with self.data_lock:
            if self.data_summary is None:
                self.data_summary = self._compute_data_summary()
            return self.data_summary

    def _compute_data_summary(self) -> dict:
        import numpy as np
        from meidnet import svg
        if self.cfg.data is None:
            cand = os.path.join(os.getcwd(), "data", "perov5", "train.csv")
            if not os.path.exists(cand):
                return {"available": False, "note": "The published model was trained on Perov-5 (11,356 structures). "
                                                    "Run `meidnet download-data` to see its distributions here."}
            import pandas as pd
            df = pd.read_csv(cand)
            out = {"available": True, "rows": int(len(df)), "kept": int(len(df)), "skipped": {}, "charts": {},
                   "source": "Perov-5 training split (CDVAE) - the data behind the published model",
                   "stats": {}}
            for col, lab, unit in (("heat_all", "Formation enthalpy", "eV/atom"), ("dir_gap", "Direct band gap", "eV")):
                out["charts"][col] = svg.histogram(df[col].values, lab, unit)
                out["stats"][col] = {"min": float(df[col].min()), "median": float(df[col].median()), "max": float(df[col].max())}
            return out
        return self._check_summary(self.cfg, source=os.path.basename(self.cfg.data.table))[0]

    def _check_summary(self, cfg: MEIDNetConfig, source: str, keep_structures: bool = False) -> tuple[dict, dict]:
        import numpy as np
        from meidnet import svg
        from meidnet.pipeline import check
        info = check(cfg, write_report=False, keep_structures=keep_structures)
        rep = info["report"]
        recs = info["records"]
        out = {"available": True, "rows": rep.rows, "kept": rep.kept, "skipped": dict(rep.skipped),
               "examples": rep.examples, "charts": {}, "stats": {}, "aligned": rep.aligned, "source": source,
               "site_counts": {str(k): v for k, v in sorted(rep.site_counts.items())},
               "elements": dict(rep.elements.most_common(20)),
               "family": info["family"].name if info["family"] else None}
        for i, p in enumerate(cfg.data.properties):
            vals = np.array([r.properties[i] for r in recs]) if recs else np.array([])
            out["charts"][p.column] = svg.histogram(vals, p.display, p.unit or p.display)
            if len(vals):
                out["stats"][p.column] = {"min": float(vals.min()), "median": float(np.median(vals)), "max": float(vals.max()),
                                          "std": float(vals.std())}
        if rep.elements:
            out["charts"]["elements"] = svg.hbars(list(rep.elements.items()), "Most common elements", max_items=16)
        if rep.skipped:
            out["charts"]["skipped"] = svg.hbars(list(rep.skipped.items()), "Why rows were skipped")
        return out, info

    def upload(self, req: dict) -> dict:
        s = self.session(req)
        files = req.get("files") or []
        if not files:
            raise ValueError("no files received")
        if s.busy:
            raise ValueError("this session is running a search or a training - stop it before uploading new data")
        # everything is written to a staging folder first: a rejected upload leaves the tab's data and model as
        # they were
        staging = os.path.join(s.dir, "data_new")
        shutil.rmtree(staging, ignore_errors=True)
        os.makedirs(staging)
        try:
            table, n_cifs, table_name = self._stage_files(staging, files)
            from meidnet.data import read_table
            try:
                df = read_table(table)
            except ImportError as e:               # optional reader (openpyxl, pyarrow, xlrd) not installed
                raise ValueError(str(e)) from e
            if len(df.columns) == 0:
                raise ValueError("the table has no columns")
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        shutil.rmtree(s.data_dir, ignore_errors=True)
        os.replace(staging, s.data_dir)
        s.table_path = os.path.join(s.data_dir, os.path.basename(table))
        s.structures_dir = os.path.join(s.data_dir, "structures") if n_cifs else None
        s.n_cifs, s.table_name = n_cifs, table_name
        s.cfg, s.check, s.lm, s.space_cache = None, None, None, {}
        s.check_info, s.chem_cache, s.use_published = None, {}, False
        truncated = bool(self.public and len(df) > PUBLIC_LIMITS["rows"])
        if truncated:
            df = df.head(PUBLIC_LIMITS["rows"])
            df.to_csv(os.path.join(s.data_dir, "table.csv"), index=False)
            s.table_path = os.path.join(s.data_dir, "table.csv")
        s.columns = [str(c) for c in df.columns]
        s.n_rows = int(len(df))
        import pandas as pd
        cols = list(df.columns)
        unnamed = {c for c in cols if str(c).startswith("Unnamed")}          # saved DataFrame indexes
        # an id column: "id" as a word of the name (material_id, ID, mp-id - not "is_hybrid"), else any name
        # containing "id" with unique values, else the first real column
        id_word = re.compile(r"(^|[^a-z])id($|[^a-z])")
        id_raw = next((c for c in cols if id_word.search(str(c).lower()) and c not in unnamed),
                      next((c for c in cols if "id" in str(c).lower() and c not in unnamed and df[c].is_unique),
                           next((c for c in cols if c not in unnamed), cols[0])))
        index_like = unnamed | {c for c in cols if c != id_raw and pd.api.types.is_integer_dtype(df[c])
                                and df[c].is_monotonic_increasing and df[c].is_unique}
        numeric = [str(c) for c in cols if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])
                   and df[c].nunique() > 3 and c not in index_like and c != id_raw]
        # pandas >= 3 gives text columns the "str" dtype, older versions "object"
        text_cols = [c for c in cols if pd.api.types.is_string_dtype(df[c]) or df[c].dtype == object]
        cif_col = next((str(c) for c in text_cols
                        if df[c].astype(str).str.contains("_cell_length_a", regex=False).any()), None)
        id_col = str(id_raw)
        return {"columns": s.columns, "rows": s.n_rows, "n_cifs": s.n_cifs,
                "suggest": {"id_column": id_col, "cif_column": cif_col,
                            "properties": [c for c in numeric if c != id_col][:6]},
                "truncated": truncated}

    def _stage_files(self, folder: str, files: list) -> tuple[str, int, str]:
        """Write an upload into ``folder``: the table as table.<ext>, CIFs (single files or from zips) under
        structures/. Returns (table path, number of CIF files, the table's own file name)."""
        limit = PUBLIC_LIMITS["upload_mb"] * 1024 * 1024 if self.public else 2 * 1024 ** 3
        # CIFs from zips and single .cif files share one budget: files (the row limit) and unpacked bytes
        max_files = PUBLIC_LIMITS["rows"] if self.public else None
        max_bytes = PUBLIC_UNZIPPED_MB * 1024 * 1024 if self.public else None
        cif_cap = CIF_MAX_KB * 1024
        total = unpacked = n_cifs = 0
        table = table_name = None
        structures = os.path.join(folder, "structures")

        def save_cif(fname: str, data: bytes):
            nonlocal unpacked, n_cifs
            if max_files is not None and n_cifs >= max_files:
                raise ValueError(f"at most {max_files:,} CIF files per upload on this server")
            if len(data) > cif_cap:
                raise ValueError(f"{fname} is larger than {CIF_MAX_KB} kB - is it really a CIF file?")
            unpacked += len(data)
            if max_bytes is not None and unpacked > max_bytes:
                raise ValueError(f"the structures take more than {PUBLIC_UNZIPPED_MB} MB once unpacked "
                                 "(limit on this server)")
            os.makedirs(structures, exist_ok=True)
            with open(os.path.join(structures, fname), "wb") as out:
                out.write(data)
            n_cifs += 1

        for f in files:
            name = os.path.basename(str(f.get("name") or "file"))
            raw = base64.b64decode(f.get("b64") or "")
            total += len(raw)
            if total > limit:
                raise ValueError(f"upload too large (limit {limit // 1024 // 1024} MB on this server)")
            ext = os.path.splitext(name)[1].lower()
            if ext == ".zip":
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    members = [m for m in z.infolist() if not m.is_dir() and m.filename.lower().endswith(".cif")]
                    if max_files is not None and len(members) > max_files:
                        raise ValueError(f"{name} holds {len(members):,} CIF files; at most {max_files:,} on this server")
                    for m in members:
                        with z.open(m) as src:            # read at most one byte past the cap, whatever
                            data = src.read(cif_cap + 1)  # the zip claims about the member's size
                        save_cif(os.path.basename(m.filename), data)
            elif ext in (".csv", ".xlsx", ".xls", ".json", ".parquet"):
                table, table_name = os.path.join(folder, "table" + ext), name
                with open(table, "wb") as out:
                    out.write(raw)
            elif ext == ".cif":
                save_cif(name, raw)
            else:
                raise ValueError(f"unsupported file type: {name} (use a CSV, Excel or JSON table, "
                                 "a .zip of CIF files, or .cif files)")
        if not table:
            raise ValueError("a table (CSV, Excel or JSON) with one row per material is required")
        return table, n_cifs, table_name

    def check_data(self, req: dict) -> dict:
        s = self.session(req)
        if not s.table_path:
            raise ValueError("upload a table first")
        with self.jobs_lock:                  # a training cannot start while the data it would use is replaced
            if s.busy:
                raise ValueError("this session is running a search, a training or a check - wait for it or "
                                 "stop it before checking new data")
            s.checking = True
        try:
            return self._check_data(s, req)
        finally:
            s.checking = False

    def _check_data(self, s: Session, req: dict) -> dict:
        props = req.get("properties") or []
        if not props:
            raise ValueError("choose at least one property column")
        for p in props:                       # units and labels end up in reports and charts: plain text only
            for key in ("unit", "label"):
                text = str(p.get(key) or "")
                if len(text) > 60 or not text.isprintable() or any(ch in text for ch in "<>"):
                    raise ValueError(f"the {key} of {p.get('column')} must be plain text (up to 60 characters, "
                                     "no < or >)")
        family = req.get("family") or "perovskite_abx3"
        if self.public and family not in list_families():
            raise ValueError("only built-in families are available on this server")
        # the variant the structures are aligned to and the search will use (the family's first when none is
        # named - a search needs one); an unknown family or variant is reported here, not inside a later job
        variant = load_family(family, variant=req.get("variant") or None, default_variant=True).variant
        data = {
            "table": s.table_path, "id_column": req.get("id_column") or s.columns[0],
            "cif_column": req.get("cif_column") or None,
            "structures_dir": s.structures_dir if not req.get("cif_column") else None,
            "properties": [{"column": p["column"], "unit": p.get("unit", ""), "label": p.get("label") or None}
                           for p in props],
            "max_sites": min(int(req.get("max_sites", 20)), PUBLIC_LIMITS["max_sites"]) if self.public else int(req.get("max_sites", 20)),
            "align_to_prototype": bool(req.get("align_to_prototype", True)),
            "prototype_tolerance": float(req.get("prototype_tolerance", 0.15)),
            "val_fraction": 0.1,
        }
        if data["cif_column"] is None and not data["structures_dir"]:
            raise ValueError("choose the column that holds the CIF text, or upload a zip of CIF files")
        gen = copy.deepcopy(self.cfg.generation.model_dump() if self.cfg.generation else {})
        if (gen.get("family"), gen.get("variant")) != (family, variant):
            for k in ("exclude_elements", "only_elements", "overrides"):   # they belong to the previous family
                gen.pop(k, None)
        columns = {p["column"] for p in props}   # rules on properties the new model will not predict are dropped
        gen["extra_constraints"] = [c for c in gen.get("extra_constraints") or []
                                    if "property" not in c or c["property"] in columns]
        gen.update({"family": family, "variant": variant,
                    "objectives": [{"property": p["column"], "loss": "l2", "weight": 10000.0, "select_weight": 1.0}
                                   for p in props],
                    "targets": [{p["column"]: 0.0 for p in props}]})
        raw = {"name": "your_data", "output_dir": s.dir, "family": family, "data": data,
               "training": {"epochs": 20, "batch_size": 16, "device": "cpu"}, "generation": gen}
        cfg = config_from_dict(raw, base_dir=s.data_dir)
        summary, info = self._check_summary(cfg, source=s.table_name or os.path.basename(s.table_path),
                                            keep_structures=True)
        s.check_info = info
        s.chem_cache = {}
        # targets default to the median of each property so the first search is sensible
        cfg.generation.targets = [{p["column"]: round(summary["stats"].get(p["column"], {}).get("median", 0.0), 3)
                                   for p in props}]
        s.cfg = cfg
        s.check = summary
        s.lm, s.space_cache, s.use_published = None, {}, False
        return summary

    def select_model(self, session: str, which: str) -> dict:
        s = self.session(session)
        if which not in ("own", "published"):
            raise ValueError("which must be 'own' or 'published'")
        if which == "own" and not s.lm:
            raise ValueError("this session has no trained model yet")
        s.use_published = which == "published"
        return {"ok": True, "using_own": self._own(s)}

    def reset_session(self, session: str) -> dict:
        s = self.session(session, create=False)
        if s and s.busy:
            return {"ok": False, "error": "a search, training or check is still running - stop it first"}
        if s:
            with self.sessions_lock:
                self.sessions.pop(s.sid, None)
            shutil.rmtree(s.dir, ignore_errors=True)
            shutil.rmtree(s.share_dir, ignore_errors=True)
        return {"ok": True}

    def _slot_error(self, s: Session) -> dict | None:
        """Why a job cannot start now (call with jobs_lock held), or None."""
        if s.busy:
            return {"ok": False, "error": "this session is already running a job"}
        if self.public and self._running() >= MAX_RUNNING:
            return {"ok": False, "error": f"{self._running()} jobs are running on this server right now - "
                                          "please try again in a minute", "busy": True}
        return None

    def _should_stop(self, job: Job) -> bool:
        """Stop pressed, or (public host) the job ran past its time limit."""
        if not job.stop_flag and self.public and time.time() - job.started > PUBLIC_JOB_SECONDS:
            job.stop_flag = True
            with job.lock:
                job.log.append(f"time limit of {PUBLIC_JOB_SECONDS // 60} minutes reached on this shared server")
        return job.stop_flag

    # ── training ─────────────────────────────────────────────────────────────
    def start_train(self, req: dict) -> dict:
        self._cleanup()
        s = self.session(req)
        if not s.cfg:
            return {"ok": False, "error": "check your data first"}
        epochs = int(req.get("epochs", 20))
        if self.public:
            epochs = max(1, min(epochs, PUBLIC_LIMITS["epochs"]))
        with self.jobs_lock:
            refused = self._slot_error(s)
            if refused:
                return refused
            s.cfg.training.epochs = epochs
            s.cfg.training.batch_size = max(2, min(int(req.get("batch_size", 16)), 64))
            job = Job("train")
            s.train = job
        threading.Thread(target=self._run_train, args=(s, job), daemon=True).start()
        return {"ok": True, "epochs": epochs}

    def _run_train(self, s: Session, job: Job):
        # trainings draw from torch's process-wide random state (initial weights, batch order): one at a time
        # keeps each of them reproducible (searches use their own generator, see Designer._randn)
        if not self.train_lock.acquire(blocking=False):
            with job.lock:
                job.log.append("waiting for another training on this server to finish ...")
            self.train_lock.acquire()
        try:
            if job.stop_flag:
                with job.lock:
                    job.log.append("stopped before it started")
                    job.running, job.done, job.finished = False, True, time.time()
                return
            self._train(s, job)
        finally:
            self.train_lock.release()

    def _train(self, s: Session, job: Job):
        try:
            from meidnet.checkpoint import build_model, save_checkpoint
            from meidnet.data import MaterialsDataset, compute_stats, split_records
            from meidnet.pipeline import check
            from meidnet.report import training_report
            from meidnet.train import evaluate, fit, pick_device, seed_everything
            cfg = s.cfg
            info = check(cfg, write_report=False)
            recs = info["records"]
            if len(recs) < cfg.training.batch_size:
                raise ValueError(f"only {len(recs)} usable materials - need at least {cfg.training.batch_size}")
            train_recs, val_recs = split_records(recs, cfg.data.val_fraction, cfg.training.seed)
            props = cfg.data.properties
            stats = compute_stats(train_recs, [p.column for p in props], [p.normalize for p in props],
                                  [p.display for p in props], [p.unit for p in props])
            train_set = MaterialsDataset(train_recs, stats)
            val_set = MaterialsDataset(val_recs, stats) if val_recs else None
            device = pick_device("cpu" if self.public else cfg.training.device)
            seed_everything(cfg.training.seed)
            model_cfg = cfg.model.model_dump()
            model = build_model(len(props), model_cfg, cfg.data.max_sites)
            ckpt = os.path.join(s.dir, "model.pt")
            with job.lock:
                job.progress.update({"epochs": cfg.training.epochs, "n_train": len(train_set), "n_val": len(val_recs)})

            def log(*a):
                with job.lock:
                    job.log.append(" ".join(str(x) for x in a))

            def on_epoch(ep, rec):
                with job.lock:
                    job.progress.update({"epoch": ep, "loss": rec["total"]})
                    job.progress["curve"].append([ep, rec["total"], rec["cosine"]])
                if val_set is not None and (ep % max(1, cfg.training.epochs // 10) == 0 or ep == cfg.training.epochs
                                            or job.stop_flag):
                    ev = evaluate(model, val_set, stats)
                    with job.lock:
                        job.progress["val"] = {"epoch": ep, "mae": ev["mae"], "retrieval_top1": ev["retrieval_top1"]}

            history = fit(model, train_set, val_set, cfg.training, device=device, on_epoch=on_epoch, log=log,
                          should_stop=lambda: self._should_stop(job))
            if history.get("stopped"):
                log("stopped by user - saving the model as it is")
            fam = info["family"]
            save_checkpoint(ckpt, model, stats, model_cfg, cfg.data.max_sites, fam.name if fam else cfg.family_name,
                            {"config": json.loads(json.dumps(cfg.model_dump(mode="json"))), "history": history,
                             "data_report": {"rows": info["report"].rows, "kept": info["report"].kept},
                             "train_formulas": sorted({r.formula for r in train_recs})})
            lm = load_checkpoint(ckpt)
            try:
                os.makedirs(s.share_dir, exist_ok=True)
                rep = training_report(cfg, lm, history, train_set, val_set,
                                      os.path.join(s.share_dir, "training_report.html"))
                shutil.copyfile(ckpt, os.path.join(s.share_dir, "model.pt"))   # downloadable next to its report
                with job.lock:
                    job.report = os.path.relpath(rep, self.run_root).replace(os.sep, "/")
            except Exception:
                print(traceback.format_exc())
            s.lm = lm
            s.space_cache, s.chem_cache = {}, {}     # predictions changed: rebuild the design space and 3D views
            s.use_published = False
            cfg.model_path = ckpt
        except (Exception, SystemExit) as e:          # pipeline helpers report user errors as SystemExit
            with job.lock:
                job.error = self._job_error(e, "the training")
                print(traceback.format_exc())
        finally:
            with job.lock:
                job.running = False
                job.done = True
                job.finished = time.time()

    # ── family + design space ────────────────────────────────────────────────
    def _family_name(self, name: str | None, s: Session | None = None) -> str:
        if not name:
            if s and s.cfg and self._own(s):
                name = s.cfg.generation.family
            else:
                name = self.cfg.generation.family if self.cfg.generation else "perovskite_abx3"
        if self.public and name not in list_families():
            raise ValueError(f"Only built-in families are available on this public server: {', '.join(list_families())}")
        return name

    def _family_src(self, name: str) -> str:
        """Your own family file is found next to your meidnet.yaml, as `meidnet generate` finds it."""
        return self.cfg.resolve(name) if (not self.public and name.endswith((".yaml", ".yml"))) else name

    def family(self, req: dict) -> dict:
        s = self.session(req, create=False) if req.get("session") else None
        name = self._family_name(req.get("family"), s)
        lm = self._model_for(s)
        own = self._own(s)
        cache = s.space_cache if own else self.space_cache
        fam = load_family(self._family_src(name), variant=req.get("variant"), default_variant=True)   # resolves the variant
        # visitors share the published model's cache, so they cannot choose how much of a space is enumerated
        limit = 20000 if self.public else int(req.get("max_compositions", 20000))
        key = json.dumps([name, fam.variant, limit])
        hit = cache.get(key)
        if hit is not None:
            return hit
        with self._key_lock(id(cache), key):      # one enumeration per (cache, family): others are not blocked
            hit = cache.get(key)
            if hit is not None:
                return hit
            space = enumerate_space(fam, lm, max_compositions=limit)
            payload = {
                "name": fam.name, "title": fam.title, "variant": fam.variant, "variants": fam.variants,
                "describe": fam.describe(),
                "groups": {g: {"description": grp.description, "slots": grp.slots, "universe": grp.universe,
                               "elements": grp.elements, "sample": grp.sample,
                               "oxidation_states": grp.oxidation_states} for g, grp in fam.groups.items()},
                "sampling_order": fam.sampling_order, "lattice_rule": fam.lattice_rule, "lattice": fam.lattice,
                "constraints": fam.constraints, "search_terms": fam.search_terms,
                "sites": [{"group": g, "frac": list(f)} for g, f in fam.sites],
                "space": space, "model_own": own,
            }
            cache[key] = payload
            return payload

    # ── searches ─────────────────────────────────────────────────────────────
    def _apply_limits(self, gen: dict, s: Session | None = None) -> dict:
        if not self.public:
            return gen
        for k in ("per_target", "population", "rounds", "steps"):
            if k in gen:
                gen[k] = max(1, min(int(gen[k]), PUBLIC_LIMITS[k]))
        if "targets" in gen:
            gen["targets"] = gen["targets"][:PUBLIC_LIMITS["targets"]]
        gen.pop("plugins", None)
        gen["family"] = self._family_name(gen.get("family"), s)
        return gen

    def _request_generation(self, gen, notes: list | None = None) -> dict:
        """
        The generation settings a request may change.  Locally: all of them.  On a public host only what the
        page offers (family, elements, objectives, targets, budgets, seed, rule limits, property windows); the
        rest keeps the server's value, because knobs such as decode_tries, rff_frequencies or a bond cutoff can
        stall or exhaust the shared machine.
        """
        if not isinstance(gen, dict):
            raise ValueError("expected a mapping with the generation settings")
        if not self.public:
            return dict(gen)
        note = notes.append if notes is not None else (lambda _: None)
        num = lambda v: v is None or (isinstance(v, (int, float)) and not isinstance(v, bool))   # noqa: E731
        out = {}
        for k, v in gen.items():
            if k in PUBLIC_GENERATION_KEYS:
                out[k] = v
            else:
                note(f"{k} is fixed on this shared server")
        if "overrides" in out:
            kept = {}
            for rule, params in (out["overrides"] or {}).items():
                params = params if isinstance(params, dict) else {}
                limits = {p: v for p, v in params.items() if p in PUBLIC_RULE_PARAMS and num(v)}
                if len(limits) != len(params):
                    note(f"overrides of {rule}: only numeric limits ({', '.join(PUBLIC_RULE_PARAMS)}) are used here")
                if limits.get("cutoff") is not None:
                    limits["cutoff"] = max(1.0, min(float(limits["cutoff"]), PUBLIC_MAX_CUTOFF))
                if limits:
                    kept[str(rule)] = limits
            out["overrides"] = kept
        if "extra_constraints" in out:
            windows = []
            for c in out["extra_constraints"] or []:
                if isinstance(c, dict) and c.get("name") == "property_window" and len(windows) < 4:
                    windows.append({"name": "property_window", "property": str(c.get("property")),
                                    **{b: c[b] for b in ("min", "max") if b in c and num(c[b])}})
                else:
                    note("only up to 4 predicted-property windows can be added as rules on this shared server")
            out["extra_constraints"] = windows
        return out

    def _check_against_model(self, fam, g: GenerationSection, lm: LoadedModel) -> None:
        """Objectives, targets and property windows must name properties the model predicts."""
        cols = list(lm.stats.columns)
        named = [o.property for o in g.objectives] + [k for t in g.targets for k in t]
        named += [c.get("property") for c in fam.constraints if c["name"] == "property_window"]
        unknown = sorted({str(p) for p in named if p not in cols})
        if unknown:
            raise ValueError(f"{', '.join(unknown)}: not predicted by this model (it predicts {', '.join(cols)})")

    def _base_cfg(self, s: Session | None) -> MEIDNetConfig:
        return s.cfg if (s and s.cfg and self._own(s)) else self.cfg

    def start_search(self, req: dict) -> dict:
        self._cleanup()
        s = self.session(req)
        base = self._base_cfg(s)
        gen = copy.deepcopy(base.generation.model_dump() if base.generation else {})
        try:
            gen.update(self._request_generation(req.get("generation") or {}))
            gen = self._apply_limits(gen, s)
            raw = dict(base.model_dump(mode="json"), generation=gen)
            if self.public:
                raw["plugins"] = []
            cfg = config_from_dict(raw, base_dir=base._base_dir)
            from meidnet.pipeline import family_for
            # refuse at once (not seconds later from the job) a target or window the model cannot predict
            self._check_against_model(family_for(cfg, need_variant=True), cfg.generation, self._model_for(s))
        except (Exception, SystemExit) as e:          # family_for reports family problems as SystemExit
            return {"ok": False, "error": str(e)}
        with self.jobs_lock:
            refused = self._slot_error(s)
            if refused:
                return refused
            cfg.model_path = s.lm.path if self._own(s) else base.checkpoint_path
            old = s.search
            job = Job("search")
            job.run_dir = os.path.join(s.share_dir, f"search_{time.strftime('%H%M%S')}_{secrets.token_hex(2)}")
            job.family = (cfg.generation.family, cfg.generation.variant)   # what this search actually used
            s.search = job
        if old and old.run_dir and os.path.isdir(old.run_dir):        # the previous run of this tab (finished)
            shutil.rmtree(old.run_dir, ignore_errors=True)
        threading.Thread(target=self._run_search, args=(s, job, cfg), daemon=True).start()
        return {"ok": True}

    def _run_search(self, s: Session, job: Job, cfg):
        try:
            from meidnet.generate import Designer
            from meidnet.pipeline import family_for
            from meidnet.report import generation_report
            from meidnet.train import pick_device
            fam = family_for(cfg, need_variant=True)
            device = pick_device("cpu" if self.public else cfg.training.device)
            base = self._model_for(s)
            lm = base if str(base.device) == str(device) else load_checkpoint(cfg.model_path, device=device)
            g = cfg.generation
            job.progress.update({"targets": len(g.targets), "rounds": g.rounds, "steps": g.steps})

            def log(*a):
                msg = " ".join(str(x) for x in a)
                with job.lock:
                    job.log.append(msg)
                    if msg.lstrip().startswith("=== target"):   # the Designer prints "\n=== target i/N ..."
                        job.progress["target"] += 1
                        job.progress["round"] = 0

            def on_step(step, steps, loss):
                with job.lock:
                    job.progress.update({"step": step, "steps": steps, "loss": loss})
                    if step == 0:
                        job.progress["round"] += 1

            def on_saved(c, tlog):
                with job.lock:
                    d = c.to_dict()
                    d["target_values"] = tlog.values
                    job.candidates.append(d)

            self._check_against_model(fam, g, lm)
            res = Designer(lm, fam, g, device=device, log=log, on_saved=on_saved, on_step=on_step,
                           should_stop=lambda: self._should_stop(job)).run(os.path.join(job.run_dir, "generation"),
                                                                           ranges=property_ranges(lm))
            with open(os.path.join(job.run_dir, "meidnet.yaml"), "w", encoding="utf-8") as f:
                f.write(dump_config(cfg))
            rep = generation_report(cfg, lm, fam, res, os.path.join(job.run_dir, "generation_report.html"))
            with job.lock:
                job.report = os.path.relpath(rep, self.run_root).replace(os.sep, "/")
        except (Exception, SystemExit) as e:          # pipeline helpers report user errors as SystemExit
            with job.lock:
                job.error = self._job_error(e, "the search")
                print(traceback.format_exc())
        finally:
            with job.lock:
                job.running = False
                job.done = True
                job.finished = time.time()

    def status(self, session: str, kind: str = "search") -> dict:
        s = self.session(session, create=False)
        job = (s.search if kind == "search" else s.train) if s else None
        return job.snapshot() if job else dict(EMPTY_STATUS)

    def stop(self, session: str) -> None:
        s = self.session(session, create=False)
        if s:
            for j in (s.search, s.train):
                if j:
                    j.stop_flag = True

    # ── config text ──────────────────────────────────────────────────────────
    def validate(self, req: dict) -> dict:
        """Validate a generation section given as YAML text or a dict; return the normalised dict or errors."""
        try:
            if "yaml" in req:
                doc = _safe_yaml(req["yaml"])
                doc = {} if doc is None else doc
                if not isinstance(doc, dict):
                    raise ValueError("expected settings written as 'key: value' lines, e.g. 'generation:' "
                                     "followed by indented lines such as '  rounds: 3'")
                gen = doc.get("generation", doc)
                gen = {} if gen is None else gen
            else:
                gen = req.get("generation") or {}
            notes = []
            gen = self._request_generation(gen, notes)
            s = self.session(req, create=False) if req.get("session") else None
            base = self._base_cfg(s)
            merged = copy.deepcopy(base.generation.model_dump() if base.generation else {})
            merged.update(gen)
            # validate what the user wrote first, so a wrong value is reported rather than silently capped
            norm = GenerationSection.model_validate(merged).model_dump(mode="json")
            # the family, variant and element filters must give a usable family, or the search would fail later
            from meidnet.pipeline import family_for
            raw = dict(base.model_dump(mode="json"), generation=norm)
            if self.public:
                raw["plugins"] = []
                self._family_name(norm.get("family"), s)       # built-in families only
            cfg = config_from_dict(raw, base_dir=base._base_dir)
            self._check_against_model(family_for(cfg, need_variant=True), cfg.generation, self._model_for(s))
            if self.public:
                capped = self._apply_limits(copy.deepcopy(norm), s)
                for k in ("per_target", "population", "rounds", "steps"):
                    if capped[k] != norm[k]:
                        notes.append(f"{k} {norm[k]} → {capped[k]} (limit on this shared server)")
                if len(capped["targets"]) != len(norm["targets"]):
                    notes.append(f"only the first {len(capped['targets'])} targets are kept on this shared server")
                norm = GenerationSection.model_validate(capped).model_dump(mode="json")
            return {"ok": True, "generation": norm, "notes": notes}
        except yaml.YAMLError as e:
            return {"ok": False, "errors": [f"YAML syntax: {e}"]}
        except SystemExit as e:                                 # family_for reports family problems this way
            return {"ok": False, "errors": [str(e)]}
        except Exception as e:
            from pydantic import ValidationError
            if isinstance(e, ValidationError):
                return {"ok": False, "errors": [" → ".join(str(x) for x in err["loc"]) + ": " + err["msg"] for err in e.errors()]}
            return {"ok": False, "errors": [str(e)]}

    def export(self, req: dict) -> str:
        s = self.session(req, create=False) if req.get("session") else None
        base = self._base_cfg(s)
        gen = copy.deepcopy(base.generation.model_dump() if base.generation else {})
        gen.update(self._request_generation(req.get("generation") or {}))
        raw = dict(base.model_dump(mode="json"), generation=gen)
        if self.public or self._own(s):
            raw["model_path"] = "model.pt" if self._own(s) else "<path to the model file>"
            raw["output_dir"] = "runs/{name}"
            raw["plugins"] = []
            if raw.get("data"):    # the names the user knows: their own table file, a structures/ folder
                raw["data"]["table"] = (s.table_name if self._own(s) and s.table_name
                                        else os.path.basename(raw["data"]["table"]))
                if raw["data"].get("structures_dir"):
                    raw["data"]["structures_dir"] = "structures"
        cfg = config_from_dict(raw, base_dir=base._base_dir)
        return dump_config(cfg)

    # ── chemiscope datasets ──────────────────────────────────────────────────
    def chemiscope(self, session: str, what: str, family: str | None = None, variant: str | None = None) -> dict:
        from meidnet.studio import chemiscope as cs
        if what not in ("space", "candidates", "data"):
            raise ValueError("what must be space, candidates or data")
        s = self.session(session, create=False)
        cap = min(cs.CHEMISCOPE_MAX, PUBLIC_LIMITS["rows"]) if self.public else cs.CHEMISCOPE_MAX
        if what == "space":
            name = self._family_name(family, s)
            fam_payload = self.family({"session": session, "family": name, "variant": variant})
            key = f"space|{name}|{fam_payload['variant']}|{self._own(s)}"
            cache = s.chem_cache if self._own(s) else self.chem_cache
            if key not in cache:
                fam = load_family(self._family_src(name), variant=fam_payload["variant"], default_variant=True)
                cache[key] = cs.space_dataset(fam, fam_payload["space"], self._model_for(s), max_structures=cap)
            return cache[key]
        if what == "candidates":
            job = s.search if s else None
            if not job or not job.candidates:
                return {"available": False, "note": "run a search first"}
            name, variant = job.family or (self._base_cfg(s).generation.family, self._base_cfg(s).generation.variant)
            fam = load_family(self._family_src(name), variant=variant, default_variant=True)
            return cs.candidates_dataset(job.candidates, fam, run_dir=job.run_dir, lm=self._model_for(s))
        if s and s.check_info and s.cfg:
            if not any(getattr(r, "structure", None) is not None for r in s.check_info["records"]):
                return {"available": False, "note": "no usable structures in this table - see the Data block"}
            if "data" not in s.chem_cache:
                s.chem_cache["data"] = cs.records_dataset(s.check_info["records"], s.cfg.data.properties,
                                                          s.table_name or os.path.basename(s.table_path or "table"), cap)
            return s.chem_cache["data"]
        if self.cfg.data is not None:                # the project's own data ...
            if "data" not in self.chem_cache:
                _, info = self._check_summary(self.cfg, os.path.basename(self.cfg.data.table), keep_structures=True)
                self.chem_cache["data"] = cs.records_dataset(info["records"], self.cfg.data.properties,
                                                             os.path.basename(self.cfg.data.table), cap)
            return self.chem_cache["data"]
        csv = os.path.join(os.getcwd(), "data", "perov5", "train.csv")   # ... or Perov-5, behind the published model
        if not os.path.exists(csv):
            return {"available": False, "note": "Perov-5 is not available on this server"}
        if "data" not in self.chem_cache:
            self.chem_cache["data"] = cs.published_data_dataset(
                csv, cache_path=os.path.join(self.run_root, "cache", "perov5_chemiscope.json"), max_structures=cap)
        return self.chem_cache["data"]

    # ── files ────────────────────────────────────────────────────────────────
    def resolve_file(self, rel: str) -> str | None:
        rel = unquote(rel).replace("\\", "/")
        if rel.startswith("docs/"):
            if not self.docs_dir:
                return None
            root, sub = self.docs_dir, rel[len("docs/"):]
            full = os.path.abspath(os.path.join(root, sub))
            if os.path.isdir(full):
                full = os.path.join(full, "index.html")
        else:
            # a public host serves only run outputs (reports, CIFs) under shared/<token>/ - never the uploaded
            # data or the trained models under sessions/<id>/
            root = os.path.join(self.run_root, "shared") if self.public else self.run_root
            if self.public:
                if not rel.startswith("shared/"):
                    return None
                rel = rel[len("shared/"):]
            full = os.path.abspath(os.path.join(root, rel))
        if not full.startswith(os.path.abspath(root) + os.sep) and full != os.path.abspath(root):
            return None
        return full if os.path.isfile(full) else None


# ───────────────────────── HTTP plumbing ─────────────────────────
def _finite(obj):
    """NaN/inf → None, recursively: browsers reject the NaN/Infinity tokens Python's json writes."""
    if isinstance(obj, float):
        return obj if obj == obj and obj not in (float("inf"), float("-inf")) else None
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_finite(v) for v in obj]
    if hasattr(obj, "item") and callable(obj.item):  # numpy scalars
        try:
            return _finite(obj.item())
        except Exception:
            return obj
    return obj


def _page(name: str) -> str:
    """A file shipped with the package (studio.html, landing.html, ask_prism.js), read on every request so that
    edits show without a restart."""
    with open(os.path.join(HERE, name), "r", encoding="utf-8") as f:
        return f.read()


def _byte_range(header, size: int):
    """The (start, end) of a single `Range: bytes=` request, inclusive; None to send the whole file;
    "unsatisfiable" when the range lies outside it. Multi-range requests get the whole file."""
    if not header or not header.strip().startswith("bytes=") or "," in header or size <= 0:
        return None
    spec = header.strip()[len("bytes="):].strip()
    first, _, last = spec.partition("-")
    try:
        if first == "":                      # bytes=-N: the last N bytes
            n = int(last)
            if n <= 0:
                return "unsatisfiable"
            return max(0, size - n), size - 1
        start = int(first)
        end = int(last) if last else size - 1
    except ValueError:
        return None
    if start >= size or start < 0 or end < start:
        return "unsatisfiable"
    return start, min(end, size - 1)


class Handler(BaseHTTPRequestHandler):
    studio: Studio = None
    timeout = 120                       # seconds a client may stay silent mid-request

    def log_message(self, fmt, *args):  # quiet
        pass

    def _send(self, code, body, ctype="application/json", sandbox=False, headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(_finite(body), default=float).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") or "json" in ctype else ""))
        self.send_header("Content-Length", str(len(body)))
        # run outputs change under the same name (a retrained model's report), and so do the pages after a deploy:
        # always revalidate those
        self.send_header("Cache-Control", "no-store" if ctype == "application/json" else
                         "no-cache" if sandbox or ctype == "text/html" else "max-age=300")
        self.send_header("X-Content-Type-Options", "nosniff")
        if sandbox:   # files written from visitors' data: no scripts, nothing loaded from elsewhere
            self.send_header("Content-Security-Policy",
                             "sandbox allow-popups allow-popups-to-escape-sandbox; default-src 'none'; "
                             "style-src 'unsafe-inline'; img-src data:")
        self.end_headers()
        if self.command != "HEAD":          # HEAD: the same headers, no body (link checkers, players probing the video)
            self.wfile.write(body)

    def _json(self, limit=1_000_000):
        raw = self.headers.get("Content-Length") or "0"
        if not raw.isdigit():
            raise ValueError("invalid Content-Length")
        n = int(raw)
        if n > limit:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _file(self, rel):
        full = self.studio.resolve_file(rel)
        if not full:
            return self._send(404, "not found", "text/plain")
        ctype = mimetypes.guess_type(full)[0] or ("text/plain" if full.endswith((".cif", ".yaml", ".log", ".csv")) else "application/octet-stream")
        if full.endswith((".cif", ".yaml", ".log", ".csv")):
            ctype = "text/plain"
        sandbox = not rel.startswith("docs/")
        size = os.path.getsize(full)
        rng = _byte_range(self.headers.get("Range"), size)
        if rng == "unsatisfiable":
            return self._send(416, b"", ctype, sandbox=sandbox, headers={"Content-Range": f"bytes */{size}", "Accept-Ranges": "bytes"})
        with open(full, "rb") as f:
            if rng:   # a slice: browsers stream and seek video this way, and Safari requires it to play at all
                start, end = rng
                f.seek(start)
                return self._send(206, f.read(end - start + 1), ctype, sandbox=sandbox,
                                  headers={"Content-Range": f"bytes {start}-{end}/{size}", "Accept-Ranges": "bytes"})
            return self._send(200, f.read(), ctype, sandbox=sandbox, headers={"Accept-Ranges": "bytes"})

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        q = parse_qs(u.query)
        sid = (q.get("session") or ["local"])[0]
        s = self.studio
        try:
            if path in ("/", "/index.html"):
                # platform mode (a docs site is served): the landing page; deep links keep working via /studio/
                if s.docs_dir and not any(k in q for k in ("panel", "explore", "tour")):
                    return self._send(200, _page("landing.html"), "text/html")
                if s.docs_dir:
                    self.send_response(302)
                    self.send_header("Location", "/studio/" + ("?" + u.query if u.query else ""))
                    self.end_headers()
                    return
                return self._send(200, _page("studio.html"), "text/html")
            if path in ("/studio", "/studio/", "/studio/index.html"):
                return self._send(200, _page("studio.html"), "text/html")
            if path == "/ask-prism.js":     # the help panel, shared by the landing page, the Studio and the docs
                return self._send(200, _page("ask_prism.js"), "text/javascript")
            if path == "/health":         # for uptime checks: answers without touching a session or the model
                return self._send(200, {"status": "ok", "version": __version__})
            if path == "/api/state":
                return self._send(200, s.state(sid))
            if path == "/api/data":
                return self._send(200, s.data(sid))
            if path == "/api/search/status":
                return self._send(200, s.status(sid, "search"))
            if path == "/api/train/status":
                return self._send(200, s.status(sid, "train"))
            if path == "/api/chemiscope":
                what = (q.get("what") or ["space"])[0]
                return self._send(200, s.chemiscope(sid, what, (q.get("family") or [None])[0], (q.get("variant") or [None])[0]))
            if path == "/docs":
                self.send_response(302)
                self.send_header("Location", "/docs/")
                self.end_headers()
                return
            if path.startswith("/docs/"):
                return self._file("docs/" + path[len("/docs/"):])
            if path.startswith("/files/"):
                return self._file(path[len("/files/"):])
            return self._send(404, {"error": "not found"})
        except (ValueError, SystemExit) as e:   # user errors; pipeline helpers raise SystemExit for them
            return self._send(400, {"error": str(e)})
        except Exception:
            print(traceback.format_exc(), file=sys.stderr, flush=True)  # always visible in the server log
            return self._send(500, {"error": traceback.format_exc() if not s.public else "server error"})

    def do_POST(self):
        path = urlparse(self.path).path
        s = self.studio
        try:
            if path == "/api/data/upload":
                limit = (PUBLIC_LIMITS["upload_mb"] * 2 + 2) * 1024 * 1024 if s.public else 3 * 1024 ** 3
                return self._send(200, s.upload(self._json(limit)))
            req = self._json()
            if path == "/api/family":
                return self._send(200, s.family(req))
            if path == "/api/data/check":
                return self._send(200, s.check_data(req))
            if path == "/api/train/start":
                return self._send(200, s.start_train(req))
            if path == "/api/search/start":
                return self._send(200, s.start_search(req))
            if path == "/api/search/stop":
                s.stop(s._sid(req))
                return self._send(200, {"ok": True})
            if path == "/api/validate":
                return self._send(200, s.validate(req))
            if path == "/api/model/select":
                return self._send(200, s.select_model(s._sid(req), str(req.get("which", "own"))))
            if path == "/api/session/reset":
                return self._send(200, s.reset_session(s._sid(req)))
            if path == "/api/export":
                return self._send(200, s.export(req), "text/plain")
            return self._send(404, {"error": "not found"})
        except (ValueError, SystemExit) as e:   # user errors; pipeline helpers raise SystemExit for them
            return self._send(400, {"error": str(e)})
        except Exception:
            print(traceback.format_exc(), file=sys.stderr, flush=True)  # always visible in the server log
            return self._send(500, {"error": traceback.format_exc() if not s.public else "server error"})


ASK_PRISM_TAG = '<script src="/ask-prism.js" defer></script>'


def inline_ask_prism(html: str) -> str:
    """The page with the Ask PRISM panel embedded: a file on a plain web host has no /ask-prism.js to load."""
    return html.replace(ASK_PRISM_TAG, "<script>\n" + _page("ask_prism.js") + "\n</script>", 1)


def export_static(cfg: MEIDNetConfig | None, out_path: str, model_path: str | None = None,
                  variants: list[tuple[str, str]] | None = None) -> str:
    """
    Write a self-contained copy of the Studio page with the state, data summary and
    design spaces embedded, so it works on a plain web host (no Python).  Searching,
    uploading and training are disabled in that copy.
    """
    studio = Studio(cfg, model_path)
    variants = variants or [("perovskite_abx3", v) for v in ("halide", "oxide", "chalcogenide", "nitride")]
    fams = {}
    for name, var in variants:
        print(f"enumerating {name}/{var} ...")
        fams[f"{name}|{var}"] = studio.family({"family": name, "variant": var})
    state = studio.state()
    # the file is published: no paths of the computer that built it
    state["config"] = studio._visible_config(studio.cfg, hide_paths=True)
    state["model"] = studio._model_info(studio.lm, own=False, hide_paths=True)
    payload = {"state": state, "data": studio.data(), "families": fams}
    with open(os.path.join(HERE, "studio.html"), "r", encoding="utf-8") as f:
        html = f.read()
    inject = "<script>window.MEIDNET_STATIC = " + json.dumps(payload, default=float) + ";</script>\n<script>"
    html = html.replace("<script>", inject, 1)
    html = inline_ask_prism(html)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {out_path} ({os.path.getsize(out_path) / 1e6:.1f} MB)")
    return out_path


def warm_up(studio: Studio, variants=None):
    """Pre-compute the design spaces so the first visitor does not wait (the double perovskites take ~1 min)."""
    variants = variants or ([("perovskite_abx3", v) for v in ("halide", "oxide", "chalcogenide", "nitride")]
                            + [("double_perovskite_a2bbx6", v) for v in ("halide", "oxide")])
    for name, var in variants:
        try:
            studio.family({"family": name, "variant": var})
        except Exception as e:  # pragma: no cover
            print(f"warm-up {name}/{var} failed: {e}")
    studio.data("warm-up")
    try:
        studio.chemiscope("warm-up", "data")   # an id that is never created: the shared dataset is cached
    except Exception as e:  # pragma: no cover
        print(f"warm-up chemiscope data failed: {e}")


def _clean_periodically(studio: Studio, every: int = 300):
    while True:
        time.sleep(every)
        try:
            studio._cleanup()
        except Exception:  # pragma: no cover
            print(traceback.format_exc(), file=sys.stderr, flush=True)


class _Server(ThreadingHTTPServer):
    # on Windows SO_REUSEADDR lets a second Studio bind the same port silently and answer some of the requests
    allow_reuse_address = os.name != "nt"


def serve(cfg: MEIDNetConfig | None, model_path: str | None = None, port: int = 8765, open_browser: bool = True,
          host: str = "127.0.0.1", public: bool = False, run_root: str | None = None, docs_dir: str | None = None):
    try:
        httpd = _Server((host, port), Handler)
    except OSError as e:
        raise SystemExit(f"Port {port} is in use ({e.strerror}) - is the Studio already running? "
                         f"Open http://127.0.0.1:{port}/ or start it with --port {port + 1}") from None
    Handler.studio = Studio(cfg, model_path, public=public, run_root=run_root, docs_dir=docs_dir)
    if public:
        threading.Thread(target=warm_up, args=(Handler.studio,), daemon=True).start()
        threading.Thread(target=_clean_periodically, args=(Handler.studio,), daemon=True).start()
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{port}/"
    studio_url = url + ("studio/" if docs_dir else "")
    print(f"MEIDNet Studio {'(public mode) ' if public else ''}running at {studio_url}" + (f"  (home page {url}, docs {url}docs/)" if docs_dir else "") + "  (Ctrl+C to stop)", flush=True)
    if open_browser and not public:
        threading.Timer(0.8, lambda: webbrowser.open(studio_url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()


def main(argv=None):
    p = argparse.ArgumentParser(description="MEIDNet Studio server")
    p.add_argument("config", nargs="?", default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--public", action="store_true", help="multi-user mode with capped budgets (hosting)")
    p.add_argument("--run-root", default=None, help="where session outputs are written")
    p.add_argument("--docs-dir", default=None, help="serve this folder (a built MkDocs site) at /docs/")
    p.add_argument("--no-open", action="store_true")
    a = p.parse_args(argv)
    cfg = None
    if a.config:
        from meidnet.config import load_config
        cfg = load_config(a.config)
    serve(cfg, model_path=a.model, port=a.port, open_browser=not a.no_open, host=a.host, public=a.public,
          run_root=a.run_root, docs_dir=a.docs_dir)


if __name__ == "__main__":
    main()
