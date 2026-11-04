#!/usr/bin/env bash
# HOP Audit developer entry point.
#
#   ./dev.sh          set up if needed, then run backend + frontend (Ctrl+C stops both)
#   ./dev.sh setup    create the backend venv, install frontend deps, create .env
#   ./dev.sh test     backend and frontend test suites
#   ./dev.sh check    everything the definition of done asks for: lint, types,
#                     tests, production build, hop-doctor --strict
#   ./dev.sh doctor   hop-doctor only
#   ./dev.sh alembic …   run Alembic in backend/ (e.g. revision --autogenerate -m "…")
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
# Installs hold native code (wheels, esbuild). The checkout may be shared
# between a Mac and a Linux container, so each platform gets its own venv,
# and node_modules swaps its native packages when the platform changes.
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
case "$(uname -m)" in aarch64 | arm64) CPU=arm64 ;; x86_64) CPU=x64 ;; *) CPU="$(uname -m)" ;; esac
VENV="$BACKEND/.venv-$OS-$CPU"
PY="$VENV/bin/python"

die() { echo "Error: $*" >&2; exit 1; }
step() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# ── Setup ─────────────────────────────────────────────────────────────────────

fingerprint() { cat "$@" | cksum | cut -d' ' -f1; }
# True when the stamp file in $1 doesn't hold $2.
stale() { [ "$(cat "$1" 2>/dev/null)" != "$2" ]; }

setup_backend() {
  local want
  want=$(fingerprint "$BACKEND/requirements.txt" "$BACKEND/requirements-dev.txt")
  [ -x "$PY" ] || {
    step "Creating $(basename "$VENV")"
    if command -v uv &>/dev/null; then
      uv venv -q "$VENV"
    else
      python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || die "Python 3.11+ required"
      python3 -m venv "$VENV"
    fi
  }
  if stale "$VENV/.requirements" "$want" || ! "$PY" -c 'import hop_core' &>/dev/null; then
    step "Installing backend dependencies"
    if command -v uv &>/dev/null; then
      VIRTUAL_ENV="$VENV" uv pip install -q -r "$BACKEND/requirements-dev.txt"
    else
      "$VENV/bin/pip" install -q -r "$BACKEND/requirements-dev.txt"
    fi
    # Chromium for the Letter PDFs (pdf.py); a failed download only means
    # PDFs say what's missing, so it doesn't stop the setup.
    "$VENV/bin/playwright" install chromium &>/dev/null \
      || echo "Chromium for PDFs didn't install; run: $VENV/bin/playwright install chromium" >&2
    echo "$want" > "$VENV/.requirements"
  fi
}

# A clean install. On a folder shared with another OS, a stale entry can
# make node_modules undeletable from this side; it's moved aside instead
# (delete .node_modules-stale-* from the other side).
clean_install() {
  (cd "$FRONTEND" && npm ci --no-audit --no-fund --loglevel=error) || {
    mv "$FRONTEND/node_modules" "$FRONTEND/.node_modules-stale-$(date +%s)"
    (cd "$FRONTEND" && npm ci --no-audit --no-fund --loglevel=error)
  }
}

setup_frontend() {
  command -v node &>/dev/null || die "node not found; Angular 22 needs Node >= 22.22.3 or >= 24.15"
  node -e 'const [a,b,c]=process.versions.node.split(".").map(Number);
    process.exit((a===22&&(b>22||b===22&&c>=3))||(a===24&&b>=15)||a>24?0:1)' \
    || die "Node $(node --version) is too old; Angular 22 needs >= 22.22.3 or >= 24.15"
  local modules="$FRONTEND/node_modules" lock
  lock=$(fingerprint "$FRONTEND/package-lock.json")
  if stale "$modules/.lock" "$lock"; then
    step "Installing frontend dependencies"
    clean_install
    echo "$lock" > "$modules/.lock"
    echo "$OS-$CPU" > "$modules/.platform"
  elif stale "$modules/.platform" "$OS-$CPU"; then
    step "Swapping frontend native packages to $OS-$CPU"
    # Fast when it works; npm sometimes fails to create nested optional
    # packages, and then a clean install is the reliable way back.
    (cd "$FRONTEND" && npm install --no-save --no-audit --no-fund --loglevel=error --os="$OS" --cpu="$CPU") \
      || clean_install
    echo "$lock" > "$modules/.lock"
    echo "$OS-$CPU" > "$modules/.platform"
  fi
}

setup_env() {
  if [ ! -f "$ROOT/.env" ]; then
    step "Creating .env with generated secrets"
    secret() { "$PY" -c 'import secrets; print(secrets.token_hex(32))'; }
    sed -e "s/^APP_SECRET_KEY=$/APP_SECRET_KEY=$(secret)/" \
        -e "s/^JWT_SECRET_KEY=$/JWT_SECRET_KEY=$(secret)/" \
        -e "s/^ENCRYPTION_KEY=$/ENCRYPTION_KEY=$(secret)/" \
        "$ROOT/.env.example" > "$ROOT/.env"
    echo "  Back up ENCRYPTION_KEY from .env: stored model keys can't be read without it."
  fi
  mkdir -p "$BACKEND/data"
}

setup() { setup_backend; setup_frontend; setup_env; }

# ── Checks ────────────────────────────────────────────────────────────────────

run_tests() {
  step "Backend tests"
  (cd "$BACKEND" && "$PY" -m pytest -q -p no:warnings)
  step "Frontend tests"
  (cd "$FRONTEND" && npm test --silent)
}

doctor() {
  step "hop-doctor"
  (cd "$ROOT" && "$VENV/bin/hop-doctor" --strict)
}

check() {
  step "Backend lint"
  (cd "$BACKEND" && "$VENV/bin/ruff" check . && "$VENV/bin/ruff" format --check .)
  step "Frontend lint and types"
  (cd "$FRONTEND" && npm run -s lint)
  run_tests
  step "Production build"
  (cd "$FRONTEND" && npx ng build --configuration production)
  doctor
  step "All checks passed"
}

# ── Run ───────────────────────────────────────────────────────────────────────

free_port() {
  "$PY" - "$1" <<'PY'
import socket, sys
def taken(port):  # ng serve listens on ::1, uvicorn on 127.0.0.1
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        with socket.socket(family) as s:
            try:
                if s.connect_ex((host, port)) == 0:
                    return True
            except OSError:
                pass
    return False

port = int(sys.argv[1])
while taken(port):
    port += 1
print(port)
PY
}

wait_for() {
  for _ in $(seq 1 "$3"); do curl -sf "$1" &>/dev/null && return 0; sleep 1; done
  die "$2 did not start; see the output above"
}

start() {
  setup
  local backend_port frontend_port backend_pid frontend_pid
  backend_port=$(free_port 8000)
  frontend_port=$(free_port 4200)
  PROXY=$(mktemp "${TMPDIR:-/tmp}/hop-audit-proxy-XXXXXX.json")
  printf '{"/api": {"target": "http://127.0.0.1:%s", "secure": false}}\n' "$backend_port" > "$PROXY"
  # kill 0 takes the whole process group: uvicorn's reloader and ng under npx too.
  trap 'trap - EXIT INT TERM; rm -f "$PROXY"; kill 0 2>/dev/null' EXIT INT TERM

  (cd "$BACKEND" && CORS_ORIGINS="http://localhost:$frontend_port" FRONTEND_BASE_URL="http://localhost:$frontend_port" \
    exec "$VENV/bin/uvicorn" main:app --host 127.0.0.1 --port "$backend_port" --reload --log-level warning) &
  backend_pid=$!
  wait_for "http://127.0.0.1:$backend_port/api/health" "Backend" 30

  (cd "$FRONTEND" && NG_CLI_ANALYTICS=false CI=1 \
    exec npx ng serve --port "$frontend_port" --proxy-config "$PROXY" --no-open) &
  frontend_pid=$!
  wait_for "http://localhost:$frontend_port/" "Frontend" 120

  echo
  echo "HOP Audit → http://localhost:$frontend_port   (API http://127.0.0.1:$backend_port/docs)"
  echo "Ctrl+C stops both."
  # Until either exits (no 'wait -n': macOS ships bash 3.2).
  while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$frontend_pid" 2>/dev/null; do sleep 2; done
}

case "${1:-start}" in
  start) start ;;
  setup) setup ;;
  test) setup_backend; setup_frontend; run_tests ;;
  check) setup; check ;;
  doctor) setup_backend; setup_env; doctor ;;
  alembic) setup_backend; setup_env; shift; cd "$BACKEND" && exec "$VENV/bin/alembic" "$@" ;;
  *) die "unknown command '$1' (start | setup | test | check | doctor | alembic)" ;;
esac
