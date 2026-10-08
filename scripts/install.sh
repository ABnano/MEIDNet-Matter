#!/usr/bin/env bash
# MEIDNet Matter, installed in one go on Linux, macOS or Windows through WSL: a virtual environment, CPU torch, the
# engine and the application with the judge, every dependency pinned to the versions the release was tested with, and
# a check that proves the install.  Downloads are retried, so a slow or flaky network finishes instead of failing
# half-way (an independent tester lost two installs that way).
#
#   bash scripts/install.sh [ENV_DIR]            ENV_DIR: the environment to create (default meidnet-matter-env)
#
#   MATTER_SOURCE=pypi|release   where the packages come from (default pypi; release = the wheels of the latest
#                                GitHub release, for an index mirror or when PyPI is unreachable)
#   MATTER_PIN=0                 do not pin the dependencies to the release's known-good versions
#   PYTHON=python3.12            the interpreter to build the environment from (default: python3)
#
# Windows 11 itself: Smart App Control blocks unsigned wheels one module at a time (torch, scipy, spglib, ...), which no
# installer can work around; use WSL (https://learn.microsoft.com/windows/wsl/install) and run this script inside it.
set -u
ENV_DIR="${1:-meidnet-matter-env}"
SOURCE="${MATTER_SOURCE:-pypi}"
PIN="${MATTER_PIN:-1}"
PYTHON="${PYTHON:-python3}"
REPO="https://github.com/ABnano/MEIDNet-Matter"
CPU_INDEX="https://download.pytorch.org/whl/cpu"
PIP_OPTS=(--timeout 180 --retries 10 --disable-pip-version-check)

say() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nSTOPPED: %s\n' "$*" >&2; exit 1; }
retry() {                                     # retry CMD...: three attempts, ten seconds apart
  local n
  for n in 1 2 3; do
    "$@" && return 0
    [ "$n" -lt 3 ] && { echo "   attempt $n failed; retrying in 10 s ..."; sleep 10; }
  done
  return 1
}

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) fail "this is a Windows shell: open WSL (Ubuntu) and run the script there";;
esac
command -v "$PYTHON" >/dev/null || fail "$PYTHON not found; install Python 3.10 or newer (python.org, or 'sudo apt install python3')"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || fail "$("$PYTHON" --version) is too old: Python 3.10 or newer is needed"

say "environment: $ENV_DIR ($("$PYTHON" --version))"
if [ ! -x "$ENV_DIR/bin/python" ]; then
  if ! "$PYTHON" -m venv "$ENV_DIR" 2>/dev/null; then
    if command -v uv >/dev/null; then
      uv venv --python "$PYTHON" "$ENV_DIR" || fail "uv could not create $ENV_DIR"
    else
      fail "python's venv module is missing (on Ubuntu/Debian: sudo apt install python3-venv; or install uv: https://docs.astral.sh/uv/)"
    fi
  fi
fi
PY="$ENV_DIR/bin/python"
"$PY" -m pip --version >/dev/null 2>&1 || "$PY" -m ensurepip --upgrade >/dev/null 2>&1 || {
  command -v uv >/dev/null && uv pip install --python "$PY" pip >/dev/null; }
"$PY" -m pip --version >/dev/null 2>&1 || fail "pip is not available in $ENV_DIR"
retry "$PY" -m pip install "${PIP_OPTS[@]}" -q --upgrade pip || fail "could not upgrade pip (network?)"

say "torch, CPU build (the default Linux build pulls about 2.5 GB of GPU libraries)"
retry "$PY" -m pip install "${PIP_OPTS[@]}" --index-url "$CPU_INDEX" torch || fail "torch did not install; check the network and run the script again (it resumes)"

PIN_OPTS=()
if [ "$PIN" = 1 ]; then
  PINS="$REPO/releases/latest/download/constraints.txt"               # the versions the release's own test installed
  if curl -fsSLI --retry 3 -o /dev/null "$PINS" 2>/dev/null; then PIN_OPTS=(-c "$PINS"); else echo "   (no constraints file on the latest release: installing unpinned)"; fi
fi
if [ "$SOURCE" = pypi ]; then
  say "the engine and the application with the judge, from PyPI"
  retry "$PY" -m pip install "${PIP_OPTS[@]}" --extra-index-url "$CPU_INDEX" "${PIN_OPTS[@]}" "meidnet-matter[judge]" \
    || fail "the install from PyPI did not finish; run the script again, or with MATTER_SOURCE=release"
else
  say "the engine and the application with the judge, from the wheels of the latest release"
  LIST=$(curl -fsSL --retry 5 "https://api.github.com/repos/ABnano/MEIDNet-Matter/releases/latest") || fail "could not read the latest release ($REPO/releases)"
  ENGINE=$(printf '%s' "$LIST" | grep -o 'https://[^"]*/meidnet-[0-9][^"]*\.whl' | head -1)
  APP=$(printf '%s' "$LIST" | grep -o 'https://[^"]*/meidnet_matter-[0-9][^"]*\.whl' | head -1)
  [ -n "$ENGINE" ] && [ -n "$APP" ] || fail "the latest release carries no wheels: $REPO/releases/latest"
  retry "$PY" -m pip install "${PIP_OPTS[@]}" --extra-index-url "$CPU_INDEX" "${PIN_OPTS[@]}" "meidnet @ $ENGINE" "meidnet-matter[judge] @ $APP" \
    || fail "the install from the release did not finish; run the script again"
fi

say "check"
"$PY" -c "import torch, meidnet, matter, matgl; print(f'IMPORT OK torch {torch.__version__} | meidnet {meidnet.__version__} | matter {matter.__version__} | matgl {matgl.__version__}')" \
  || fail "the packages installed but do not import; send the lines above with a bug report ($REPO/issues)"
"$ENV_DIR/bin/meidnet" --version >/dev/null || fail "the 'meidnet' command is missing from $ENV_DIR/bin"
"$ENV_DIR/bin/meidnet-matter" version >/dev/null || fail "the 'meidnet-matter' command is missing from $ENV_DIR/bin"

cat <<EOF

Installed. To use it:
  source $ENV_DIR/bin/activate
  meidnet --version                    # the engine's command line
  meidnet-matter version               # the application
The step-by-step guide for your own data: https://babu09-meidnet-matter.hf.space/method#run
(also at https://abnano.github.io/MEIDNet-Matter/#/method on networks that block hf.space)
EOF
