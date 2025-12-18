#!/usr/bin/env bash
set -euo pipefail

# Path to your Vite project (CHANGE THIS)
VITE_APP_DIR="${VITE_APP_DIR:-$HOME/projects/neuro-fabric-vite}"

# Where nginx serves from in THIS repo
UI_REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBLIC_DIR="${UI_REPO_DIR}/public"

echo "[1/4] Vite app dir: ${VITE_APP_DIR}"
echo "[2/4] UI repo dir:  ${UI_REPO_DIR}"
echo "[3/4] Building Vite..."
cd "${VITE_APP_DIR}"

# Install deps if missing
if [ ! -d node_modules ]; then
  npm ci
fi

npm run build

# Detect build output folder (Vite default is dist/)
DIST_DIR="${VITE_APP_DIR}/dist"
if [ ! -d "${DIST_DIR}" ]; then
  echo "ERROR: dist/ not found at ${DIST_DIR}. Check your Vite build output."
  exit 1
fi

echo "[4/4] Syncing dist/ -> public/ ..."
rm -rf "${PUBLIC_DIR:?}/"*
cp -R "${DIST_DIR}/." "${PUBLIC_DIR}/"

echo "DONE. public/ updated from Vite build."
echo "Next: git status && git add public && git commit"
