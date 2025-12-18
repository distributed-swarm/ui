#!/usr/bin/env bash
set -euo pipefail

############################################
# CONFIG
############################################

# Path to your Vite project (the folder that contains package.json).
# You can override at runtime: VITE_APP_DIR=/path/to/vite ./tools/sync_vite_to_public.sh
VITE_APP_DIR="${VITE_APP_DIR:-$HOME/projects/neuro-fabric-vite}"

############################################
# Paths
############################################

# Repo root (one level above tools/)
UI_REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBLIC_DIR="${UI_REPO_DIR}/public"
DIST_DIR="${VITE_APP_DIR}/dist"

############################################
# Preflight checks
############################################

echo "[1/5] Vite app dir: ${VITE_APP_DIR}"
echo "[2/5] UI repo dir:  ${UI_REPO_DIR}"

if [ ! -d "${VITE_APP_DIR}" ]; then
  echo "ERROR: VITE_APP_DIR does not exist: ${VITE_APP_DIR}"
  exit 1
fi

if [ ! -f "${VITE_APP_DIR}/package.json" ]; then
  echo "ERROR: No package.json found in: ${VITE_APP_DIR}"
  echo "       Point VITE_APP_DIR to your Vite project root."
  exit 1
fi

if [ ! -d "${PUBLIC_DIR}" ]; then
  echo "ERROR: public/ directory not found in UI repo: ${PUBLIC_DIR}"
  exit 1
fi

############################################
# Build
############################################

echo "[3/5] Building Vite..."
cd "${VITE_APP_DIR}"

# Install deps if missing (or if node_modules is absent)
if [ ! -d node_modules ]; then
  if [ -f package-lock.json ]; then
    npm ci
  else
    npm install
  fi
fi

npm run build

############################################
# Verify dist
############################################

if [ ! -d "${DIST_DIR}" ]; then
  echo "ERROR: dist/ not found at ${DIST_DIR}"
  echo "       If your Vite output dir is not 'dist', update DIST_DIR in this script."
  exit 1
fi

############################################
# Sync dist -> public
############################################

echo "[4/5] Syncing dist/ -> public/ ..."

# Remove existing contents of public/ but keep the directory itself
# (and keep .gitkeep if you ever add one)
find "${PUBLIC_DIR}" -mindepth 1 -maxdepth 1 ! -name ".gitkeep" -exec rm -rf {} +

# Copy new build output
cp -R "${DIST_DIR}/." "${PUBLIC_DIR}/"

############################################
# Done
############################################

echo "[5/5] DONE."
echo "public/ updated from Vite build."
echo "Next:"
echo "  cd ${UI_REPO_DIR}"
echo "  git status"
echo "  git add public"
echo "  git commit -m \"Update UI build\""
