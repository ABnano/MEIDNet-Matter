# MEIDNet Matter on Hugging Face Spaces (Docker SDK, CPU basic).
# Built from the bundle that deploy/deploy_space.py stages: matter/ (with the built frontend in matter/static), engine/
# (the vendored MEIDNet snapshot and the evaluation components), examples/perov5/, examples/research/, checkpoints/,
# requirements.txt and build_info.json.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
    HF_HUB_DISABLE_TELEMETRY=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
WORKDIR /app

# every dependency at a known-good version (constraints.txt: a clean install of meidnet-matter[judge]), so two builds of
# the same release install the same packages; torch from the CPU index first (its own layer), then the rest
COPY constraints.txt .
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu -c constraints.txt "torch>=2.4,<3"
COPY requirements.txt .
RUN pip install --no-cache-dir -c constraints.txt -r requirements.txt

# the engine snapshot, installed as the `meidnet` distribution; nothing is fetched from PyPI for it
COPY engine/ ./engine/
RUN pip install --no-cache-dir --no-deps ./engine \
 && python -c "import meidnet, meidnet.symmetry; from meidnet_eval import stages; assert meidnet.__version__.startswith('2.4.0'); assert not stages.validate(verbose=False)"

COPY --chown=user . .
USER user
ENV HOME=/home/user PYTHONPATH=/app \
    MATTER_PUBLIC=1 MATTER_RUN_ROOT=/home/user/runs MATTER_CHECKPOINTS_DIR=/app/checkpoints \
    MATTER_CHECKPOINTS_MANIFEST=/app/checkpoints/manifest.json MATTER_DEMO_DIR=/app/examples/perov5 \
    MATTER_RESEARCH_DIR=/app/examples/research MATTER_STATIC_DIR=/app/matter/static MATTER_BUILD_INFO=/app/build_info.json \
    MATTER_WARM_START=1 MATTER_TORCH_THREADS=2

# the independent judge's weights, fetched once at build time into this user's cache, then proven present offline
ARG PREFETCH_WEIGHTS=1
RUN if [ "$PREFETCH_WEIGHTS" = "1" ]; then \
      python -c "import matgl; matgl.load_model('MEGNet-BandGap-mfi-MP-2019.4.1')" \
      && HF_HUB_OFFLINE=1 python -c "import matgl; matgl.load_model('MEGNet-BandGap-mfi-MP-2019.4.1'); print('judge weights cached')"; \
    fi
ENV HF_HUB_OFFLINE=1

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:7860/health',timeout=4).status==200 else 1)"
CMD ["python", "-m", "uvicorn", "matter.app:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
