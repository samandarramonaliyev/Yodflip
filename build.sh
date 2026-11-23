#!/usr/bin/env bash
# Render build step for the single Yodflip web service (also works locally on Linux/macOS/Git Bash).
#   1. Python dependencies   2. React build (frontend/dist)   3. collectstatic
#   4. migrate (incl. the level-progress data migration)
#   5. check + seed vocabulary (seed only when the files changed; never deletes words)   6. admin user
set -o errexit -o nounset -o pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODE_MAJOR="${NODE_MAJOR:-20}"

# --- Node.js (Render's Python runtime may not ship a recent Node) ---------------
node_ok() { command -v npm >/dev/null 2>&1 && [ "$(node -p 'process.versions.node.split(".")[0]')" -ge 18 ]; }
if ! node_ok; then
  echo "==> Installing Node.js ${NODE_MAJOR} locally"
  NODE_DIR="${ROOT}/.render/node"
  mkdir -p "${NODE_DIR}"
  VERSION="$(curl -fsSL "https://nodejs.org/dist/latest-v${NODE_MAJOR}.x/SHASUMS256.txt" | grep -oE "node-v[0-9.]+-linux-x64.tar.xz" | head -1)"
  curl -fsSL "https://nodejs.org/dist/latest-v${NODE_MAJOR}.x/${VERSION}" | tar -xJ -C "${NODE_DIR}" --strip-components=1
  export PATH="${NODE_DIR}/bin:${PATH}"
fi
echo "==> node $(node -v), npm $(npm -v)"

echo "==> Python dependencies"
python -m pip install --upgrade pip
python -m pip install -r "${ROOT}/backend/requirements.txt"

echo "==> React build"
cd "${ROOT}/frontend"
npm ci --no-audit --no-fund
npm run build

cd "${ROOT}/backend"
echo "==> collectstatic"
python manage.py collectstatic --noinput

echo "==> migrate"
python manage.py migrate --noinput

echo "==> check vocabulary files (exact counts, no duplicates, no empty fields)"
python manage.py check_seed

echo "==> seed vocabulary (skipped when unchanged; idempotent, keeps word IDs)"
python manage.py seed_words

echo "==> exam packs (check, then seed; idempotent, skipped when unchanged)"
python manage.py check_exams
python manage.py seed_exams

echo "==> admin user (only if DJANGO_SUPERUSER_EMAIL/PASSWORD are set)"
python manage.py ensure_superuser

echo "==> build finished"
