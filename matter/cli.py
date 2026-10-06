"""
meidnet-matter: the command line of MEIDNet Matter.

    meidnet-matter serve [--host 127.0.0.1] [--port 8000] [--public] [--reload]
    meidnet-matter version
    meidnet-matter build-demo --data-dir data/perov5 --out examples/perov5 [--model ID=PATH ...]

Paths and limits come from the environment (see matter/settings.py); the flags of `serve` override MATTER_PUBLIC,
MATTER_RUN_ROOT, MATTER_CHECKPOINTS_DIR, MATTER_DEMO_DIR and MATTER_STATIC_DIR for that process.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def cmd_serve(a):
    import uvicorn
    for flag, var in (("public", "MATTER_PUBLIC"), ("run_root", "MATTER_RUN_ROOT"), ("checkpoints", "MATTER_CHECKPOINTS_DIR"),
                      ("demo_dir", "MATTER_DEMO_DIR"), ("static_dir", "MATTER_STATIC_DIR")):
        v = getattr(a, flag)
        if v not in (None, False):
            os.environ[var] = "1" if v is True else str(v)
    uvicorn.run("matter.app:app", host=a.host, port=a.port, reload=a.reload, workers=1, log_level="info")


def cmd_version(a):
    from matter.settings import Settings
    from matter.version import build_info
    s = Settings.from_env()
    print(json.dumps(build_info(s.build_info, s.public), indent=1))


def cmd_build_demo(a):
    from matter.demo_build import build
    models = dict(m.split("=", 1) for m in a.model)
    build(a.data_dir, models, a.out, skip_recoverability=a.skip_recoverability, limit=a.limit)


def main(argv=None):
    p = argparse.ArgumentParser(prog="meidnet-matter", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the API and the web app")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--public", action="store_true", help="shared-host mode: capped budgets, sessions, masked errors")
    s.add_argument("--reload", action="store_true")
    s.add_argument("--run-root", dest="run_root", default=None)
    s.add_argument("--checkpoints", default=None, help="folder with the model files")
    s.add_argument("--demo-dir", dest="demo_dir", default=None)
    s.add_argument("--static-dir", dest="static_dir", default=None)
    s.set_defaults(fn=cmd_serve)
    v = sub.add_parser("version", help="print what would run, as JSON")
    v.set_defaults(fn=cmd_version)
    b = sub.add_parser("build-demo", help="write the demo project's artefacts from the Perov-5 CSVs and a checkpoint")
    b.add_argument("--data-dir", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--model", action="append", default=[], metavar="ID=PATH", help="a model to include (repeatable)")
    b.add_argument("--skip-recoverability", action="store_true")
    b.add_argument("--limit", type=int, default=None, help="only the first N rows of each split (a smoke test)")
    b.set_defaults(fn=cmd_build_demo)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
