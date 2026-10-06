# MEIDNet Matter on Hugging Face Spaces (Docker SDK, CPU basic).
# Built from the bundle that deploy/deploy_space.py stages: matter/ (with the built frontend in matter/static),
# examples/perov5/, checkpoints/, requirements.txt and build_info.json.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
RUN useradd -m -u 1000 user
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .
USER user
ENV HOME=/home/user PYTHONPATH=/app \
    MATTER_PUBLIC=1 MATTER_RUN_ROOT=/home/user/runs MATTER_CHECKPOINTS_DIR=/app/checkpoints \
    MATTER_DEMO_DIR=/app/examples/perov5 MATTER_STATIC_DIR=/app/matter/static MATTER_BUILD_INFO=/app/build_info.json

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:7860/health',timeout=4).status==200 else 1)"
CMD ["python", "-m", "uvicorn", "matter.app:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
