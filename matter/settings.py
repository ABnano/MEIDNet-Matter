"""Settings, read from the environment once at start-up.

Nothing is read from the home folder: every path defaults to a folder under the current directory, so a test or a
container can redirect all of it. Matter never downloads a model on its own; ``scripts/fetch_assets.py`` does that.

    MATTER_PUBLIC           1 on a shared host: budgets capped, sessions required, errors masked, idle runs removed
    MATTER_RUN_ROOT         where runs are written                       (default ./runs)
    MATTER_CHECKPOINTS_DIR  folder holding the model files of models.json (default ./checkpoints)
    MATTER_CHECKPOINT       path of the default model file; overrides the models.json entry
    MATTER_DEMO_DIR         the demo project's artefacts                 (default <repo>/examples/perov5)
    MATTER_STATIC_DIR       the built frontend                           (default <repo>/matter/static)
    MATTER_CORS_ORIGINS     comma-separated origins allowed to call the API (the Vite dev server)
    MATTER_BUILD_INFO       a JSON file written at deploy time with the git commit and build date
    MATTER_TORCH_THREADS    torch.set_num_threads at start-up            (default 2 when public)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_CHECKPOINT = "dual_autoencoder_clip_earlyfusion_propertyaware_2k.pth"


def _flag(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    public: bool = False
    run_root: str = field(default_factory=lambda: os.path.join(os.getcwd(), "runs"))
    checkpoints_dir: str = field(default_factory=lambda: os.path.join(os.getcwd(), "checkpoints"))
    checkpoint: str | None = None
    demo_dir: str = field(default_factory=lambda: os.path.join(ROOT, "examples", "perov5"))
    static_dir: str = field(default_factory=lambda: os.path.join(ROOT, "matter", "static"))
    cors_origins: list[str] = field(default_factory=list)
    build_info: str | None = None
    torch_threads: int | None = None

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Settings":
        e = os.environ if env is None else env
        public = _flag(e.get("MATTER_PUBLIC"))
        threads = e.get("MATTER_TORCH_THREADS")
        origins = [o.strip() for o in (e.get("MATTER_CORS_ORIGINS") or "").split(",") if o.strip()]
        return cls(
            public=public,
            run_root=os.path.abspath(e.get("MATTER_RUN_ROOT") or os.path.join(os.getcwd(), "runs")),
            checkpoints_dir=os.path.abspath(e.get("MATTER_CHECKPOINTS_DIR") or os.path.join(os.getcwd(), "checkpoints")),
            checkpoint=os.path.abspath(e["MATTER_CHECKPOINT"]) if e.get("MATTER_CHECKPOINT") else None,
            demo_dir=os.path.abspath(e.get("MATTER_DEMO_DIR") or os.path.join(ROOT, "examples", "perov5")),
            static_dir=os.path.abspath(e.get("MATTER_STATIC_DIR") or os.path.join(ROOT, "matter", "static")),
            cors_origins=origins,
            build_info=e.get("MATTER_BUILD_INFO") or None,
            torch_threads=int(threads) if threads else (2 if public else None),
        )

    @property
    def mode(self) -> str:
        return "public" if self.public else "local"

    def model_file(self, name: str) -> str:
        """Where a model file named in models.json is expected; MATTER_CHECKPOINT overrides the default model."""
        if self.checkpoint and os.path.basename(self.checkpoint) == name:
            return self.checkpoint
        if self.checkpoint and name == DEFAULT_CHECKPOINT:
            return self.checkpoint
        return os.path.join(self.checkpoints_dir, name)
