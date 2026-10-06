# Deployment

## Local

Python 3.10 or later, Node 20.19 or later.

```bash
git clone https://github.com/ABnano/MEIDNet-Matter && cd MEIDNet-Matter
pip install -e ".[dev]"                 # the engine (meidnet) comes from PyPI
python scripts/fetch_assets.py          # the model files, with checksums, into checkpoints/
cd frontend && npm ci && npm run build && cd ..     # writes matter/static
python -m uvicorn matter.app:app --port 8000        # http://127.0.0.1:8000/
```

Settings are environment variables with defaults under the current directory (never the home folder): `MATTER_RUN_ROOT` (`./runs`), `MATTER_CHECKPOINTS_DIR` (`./checkpoints`), `MATTER_DEMO_DIR` (`examples/perov5`), `MATTER_STATIC_DIR` (`matter/static`), `MATTER_PUBLIC` (0), `MATTER_CORS_ORIGINS`, `MATTER_BUILD_INFO`, `MATTER_TORCH_THREADS`. `meidnet-matter serve` wraps uvicorn with the same options as flags.

Development: `python -m uvicorn matter.app:app --reload --port 8000` for the API and `npm run dev` in `frontend/` for the app on port 5173 (it proxies `/api` to port 8000).

Tests: `python -m pytest -q` (the slow ones load the model and run a tiny search; `-m "not slow"` skips them), `npm run typecheck && npm test && npm run lint` in `frontend/`, and the browser walk-through `node scripts/smoke_browser.mjs http://127.0.0.1:8000 build/smoke` against a running server (needs Chrome or Edge; set `BROWSER=<path>` if it is elsewhere).

On Windows with Smart App Control on: install with `pip install --no-deps` into an existing environment rather than creating new ones; the native binaries of esbuild and rollup run here, but if they are ever blocked, add `"overrides": {"esbuild": "npm:esbuild-wasm@0.25.12", "rollup": "npm:@rollup/wasm-node@4.64.0"}` to `frontend/package.json`, reinstall and commit the lockfile.

## The Docker image

`deploy/Dockerfile` builds a python:3.12-slim image from the bundle that `deploy/deploy_space.py` stages: the backend package with the built frontend, the demo artefacts, the model file, `requirements.txt` (CPU torch from the PyTorch index, meidnet pinned) and `build_info.json`. It runs as user 1000 with `MATTER_PUBLIC=1` (budgets capped, a session id required, errors masked, idle runs removed after an hour), one uvicorn worker on port 7860, and a health check on `/health`.

```bash
python deploy/deploy_space.py --dry-run     # stages build/space_docker
docker build -t meidnet-matter build/space_docker && docker run -p 7860:7860 meidnet-matter
```

## The Hugging Face Space

The script deploys `Babu09/MEIDNet-Matter` only (the two other Spaces of the ecosystem are refused unless `--allow-other-space` is passed on purpose). It uploads the staged bundle with `delete_patterns=["*"]`, waits for the Space to run, then checks `/health`, `/`, `/api/projects/perov5-demo`, the goal page and the favicon.

```bash
HF_TOKEN=<a write token created for this deploy> python deploy/deploy_space.py
```

The token is read from the environment for that one command and never written to a file; revoke it afterwards. Every binary type in the bundle is listed in the generated `.gitattributes`: the Space build restores only the LFS types named there, and an unlisted binary arrives as a pointer file. To roll back, check out an earlier tag and deploy again.

## Continuous integration

`ci.yml` runs the backend tests on Python 3.10 and 3.12 (with the model file cached by checksum), the frontend lint, type check, unit tests and build, and the browser walk-through against a server started from the build. `release.yml` runs on a `v*` tag: it builds the wheel with the frontend inside, checks that the tag, `CHANGELOG.md` and `CITATION.cff` agree, installs the wheel outside the repository, builds the Docker image, and publishes the GitHub release with the wheel, the sdist and the frontend zip.
