"""Pre-render MEIDNet Matter's read-only API into the static mirror (GitHub Pages, https://abnano.github.io/MEIDNet-Matter/).

The mirror is the same site, built by `npm run build:mirror` into build/mirror, for networks that block *.hf.space (public
Wi-Fi often does).  Its pages read every GET from files written here, next to index.html (frontend/src/lib/mirror.ts maps
'/api/studies/mp20' to 'static-api/api/studies/mp20.json'); what computes live (generation, the demo search) points to
the Space.  The responses come from the application itself (FastAPI's test client), so the mirror shows what the Space
serves, from the same engine and the same research artefacts.

Written under OUT/static-api/: the version, the pipeline blocks and every block, the component list and every
component's source, the studies index, every study and every file a study lists, the checkpoints table and every
checkpoint (their files are not copied: the links point to the GitHub release), the demo project's summary.  Also
OUT/404.html (a path inside the mirror becomes its '#' route), OUT/.nojekyll and OUT/mirror.json (what was built).

Usage: python scripts/build_mirror.py [--out build/mirror]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

MIRROR = "https://abnano.github.io/MEIDNet-Matter/"
# characters every static host serves under their own name (a '#' or '?' in a file name would end the path)
SAFE = re.compile(r"^[A-Za-z0-9._()\-/+,=@]+$")

NOT_FOUND = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MEIDNet Matter</title>
<script>
// GitHub Pages answers a path it does not have with this page.  A path inside the mirror (.../MEIDNet-Matter/studies/mp20)
// is a route of the app, which the mirror keeps after '#' (.../MEIDNet-Matter/#/studies/mp20).
(function () {
  var path = location.pathname, base = '/';
  if (path.indexOf('/MEIDNet-Matter/') === 0) base = '/MEIDNet-Matter/';
  else if (/\\.github\\.io$/.test(location.hostname)) { var first = path.split('/')[1]; if (first) base = '/' + first + '/'; }
  var rest = path.indexOf(base) === 0 ? path.slice(base.length) : path.replace(/^\\//, '');
  location.replace(base + '#/' + rest + location.search);
})();
</script>
</head>
<body><p>Opening <a href="./">MEIDNet Matter</a>…</p></body>
</html>
"""


def target(out: str, route: str, kind: str) -> str:
    """The file a route is written to; the same rule as staticPath() in frontend/src/lib/mirror.ts."""
    rel = route.lstrip("/")
    if "?" in rel:
        rel = rel.replace("?", "@", 1)
    if not SAFE.match(rel):
        raise SystemExit(f"{route}: a name a static host cannot serve as it is")
    return os.path.join(out, "static-api", rel + (".json" if kind == "json" else ""))


def prerender(out: str, log=print) -> dict:
    """Every read-only GET the site's pages make, written as files under OUT/static-api; returns a summary."""
    from fastapi.testclient import TestClient
    from matter.app import create_app
    from matter.settings import Settings

    runs = tempfile.mkdtemp(prefix="matter-mirror-runs-")          # never the home folder
    settings = Settings.from_env({"MATTER_RUN_ROOT": runs, "MATTER_CHECKPOINTS_DIR": os.path.join(ROOT, "checkpoints")})
    written, total = [], 0

    def save(route: str, body: bytes, kind: str) -> None:
        nonlocal total
        path = target(out, route, kind)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(body)
        written.append(os.path.relpath(path, out)); total += len(body)

    with TestClient(create_app(settings)) as client:
        def get(route: str, kind: str = "json", required: bool = True):
            r = client.get(route)
            if r.status_code != 200:
                if required:
                    raise SystemExit(f"{route}: HTTP {r.status_code} {r.text[:200]}")
                log(f"  skipped {route}: HTTP {r.status_code}")
                return None
            if kind == "json":
                data = r.json()
                return data
            save(route, r.content, kind)
            return r.content

        def put(route: str, data) -> None:
            save(route, json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), "json")

        put("/api/version", get("/api/version"))
        blocks = get("/api/pipeline/blocks"); put("/api/pipeline/blocks", blocks)
        for b in blocks["blocks"]:
            put(f"/api/pipeline/blocks/{b['id']}", get(f"/api/pipeline/blocks/{b['id']}"))
        comps = get("/api/pipeline/components"); put("/api/pipeline/components", comps)
        for c in comps:
            get(f"/api/pipeline/components/{c['file']}", kind="raw")
        studies = get("/api/studies"); put("/api/studies", studies)
        for s in studies["studies"]:
            study = get(f"/api/studies/{s['id']}"); put(f"/api/studies/{s['id']}", study)
            for name in sorted(study.get("files") or {}):
                get(f"/api/studies/{s['id']}/files/{name}", kind="raw")
        cks = get("/api/checkpoints")
        # the mirror holds no model files: every download goes to the release asset (or the Space) the table names
        for c in cks["checkpoints"]:
            c.update(available=False, loaded=False, download_url=None)
        put("/api/checkpoints", cks)
        for c in cks["checkpoints"]:
            one = get(f"/api/checkpoints/{c['id']}")
            one.update(available=False, loaded=False, download_url=None)
            put(f"/api/checkpoints/{c['id']}", one)
        demo = get("/api/projects/perov5-demo", required=False)          # the privacy page names the demo's data
        if demo is not None:
            put("/api/projects/perov5-demo", demo)

    # nothing the pages follow may point at the server: a value starting with /api/ would be a dead link here
    dead = []
    for rel in written:
        if rel.endswith(".json"):
            text = open(os.path.join(out, rel), encoding="utf-8").read()
            json.loads(text)
            dead += [f"{rel}: {m}" for m in re.findall(r'"(/api/[^"]*)"', text)]
    if dead:
        raise SystemExit("server paths left in the mirror:\n  " + "\n  ".join(dead[:20]))
    return {"files": len(written), "bytes": total}


def rooted_references(out: str) -> list[str]:
    """Resource paths rooted at a server's /. The mirror lives under /MEIDNet-Matter/ on GitHub Pages (and may move to any
    folder of any host), so a page or style that loads '/x' would break there: the build refuses them."""
    found = []
    with open(os.path.join(out, "index.html"), encoding="utf-8") as f:
        html = f.read()
    found += [f"index.html: {m}" for m in re.findall(r'(?:src|href)="(/(?!/)[^"]*)"', html)]
    for d, _, names in os.walk(os.path.join(out, "assets")):
        for n in names:
            if n.endswith(".css"):
                with open(os.path.join(d, n), encoding="utf-8") as f:
                    found += [f"assets/{n}: {m}" for m in re.findall(r"url\(\s*[\"']?(/(?!/)[^)\"']*)", f.read())]
    return found


def git_commit() -> str | None:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "mirror"), help="the folder `npm run build:mirror` wrote")
    a = ap.parse_args(argv)
    out = os.path.abspath(a.out)
    if not os.path.exists(os.path.join(out, "index.html")):
        raise SystemExit(f"{out}/index.html not found: run `npm run build:mirror` in frontend/ first")
    summary = prerender(out)
    # a social preview needs an absolute image address; the Space's page says /og.png, the mirror's says where it lives
    idx = os.path.join(out, "index.html")
    html = open(idx, encoding="utf-8").read().replace('content="/og.png"', f'content="{MIRROR}og.png"')
    with open(idx, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    rooted = rooted_references(out)
    if rooted:
        raise SystemExit("paths rooted at the server's / would break on GitHub Pages:\n  " + "\n  ".join(rooted))
    with open(os.path.join(out, "404.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(NOT_FOUND)
    open(os.path.join(out, ".nojekyll"), "w").close()
    import matter
    try:
        import meidnet
        engine = meidnet.__version__
    except Exception:
        engine = None
    info = {"site": "MEIDNet Matter, static mirror", "matter": matter.__version__, "engine": engine, "commit": git_commit(),
            "built_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "live_app": "https://huggingface.co/spaces/Babu09/MEIDNet-Matter", **summary}
    with open(os.path.join(out, "mirror.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(info, f, indent=1)
    size = sum(os.path.getsize(os.path.join(d, n)) for d, _, ns in os.walk(out) for n in ns)
    print(f"mirror: {summary['files']} pre-rendered files ({summary['bytes'] / 1e6:.1f} MB), {size / 1e6:.1f} MB in all -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
