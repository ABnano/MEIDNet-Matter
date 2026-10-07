"""The FastAPI application: the JSON API under /api, /health, and the built frontend served from one folder.

    uvicorn matter.app:app --port 8000                 # settings from the environment (matter/settings.py)
    create_app(Settings(...))                          # tests build their own
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response

from matter import __version__
from matter.jsonsafe import MatterJSONResponse
from matter.settings import Settings
from matter.version import build_info

NOT_BUILT = """<!doctype html><meta charset="utf-8"><title>MEIDNet Matter</title>
<body style="font:15px/1.5 system-ui;max-width:40em;margin:4em auto;padding:0 1em">
<h1>MEIDNet Matter {version}</h1>
<p>The API is running; the web app has not been built yet.</p>
<p>Build it with <code>npm run build</code> in <code>frontend/</code>, or point <code>MATTER_STATIC_DIR</code> at a build.</p>
<p><a href="/health">/health</a> · <a href="/api/version">/api/version</a> · <a href="/docs">/docs</a> (the API reference)</p>
</body>"""


def _has_symmetry() -> bool:
    try:
        import meidnet.symmetry  # noqa: F401
        return True
    except Exception:
        return False


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from matter.services.container import Services
        app.state.services = Services.build(settings)
        yield
        app.state.services.close()

    app = FastAPI(title="MEIDNet Matter", version=__version__, lifespan=lifespan, default_response_class=MatterJSONResponse,
                  docs_url="/docs", redoc_url=None, openapi_url="/openapi.json")
    app.state.settings = settings
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

    from matter.api.errors import install_error_handlers
    from matter.api.router import api_router
    install_error_handlers(app, settings)
    app.include_router(api_router, prefix="/api")

    @app.get("/health", include_in_schema=False)
    def health(request: Request):
        services = getattr(request.app.state, "services", None)
        judge = getattr(services, "judge", None)
        return {"status": "ok", "version": __version__, "meidnet_version": _meidnet_version(), "mode": settings.mode,
                "model_loaded": bool(services and services.model_loaded),
                "generation_model_loaded": bool(services and getattr(services, "generation_ready", False)),
                "judge_ready": bool(judge and judge.available),
                "research_artefacts": bool(services and getattr(services, "studies", None) and services.studies.available),
                "engine": {"version": _meidnet_version(), "symmetry_decoder": _has_symmetry()}}

    static_root = os.path.abspath(settings.static_dir)
    index_path = os.path.join(static_root, "index.html")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        """A file of the built frontend when it exists, else index.html (the app routes client-side)."""
        if path.startswith("api/"):
            return MatterJSONResponse({"error": {"code": "not_found", "message": f"no API route /{path}"}}, status_code=404)
        if path:
            full = os.path.abspath(os.path.join(static_root, path.replace("\\", "/")))
            if full.startswith(static_root + os.sep) and os.path.isfile(full):
                headers = {"Cache-Control": "public, max-age=31536000, immutable"} if path.startswith("assets/") else {"Cache-Control": "no-cache"}
                return FileResponse(full, headers=headers)
        if os.path.isfile(index_path):
            return FileResponse(index_path, media_type="text/html", headers={"Cache-Control": "no-cache"})
        return HTMLResponse(NOT_BUILT.replace("{version}", __version__), headers={"Cache-Control": "no-cache"})

    return app


def _meidnet_version() -> str:
    import meidnet
    return meidnet.__version__


app = create_app()
