#!/bin/bash
# movieradar launcher: pulls the latest code from GitHub, then runs it.
#
# config.json (your real API keys) stays local, is gitignored, and is never
# touched by the pull. This is the single command to point Synology Task
# Scheduler (or cron, or a systemd timer) at.
#
# Usage: bash run.sh   (run from anywhere; it cd's into its own directory)

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

if [ ! -d .git ]; then
  echo "run.sh must live inside the movieradar git checkout (no .git found in $REPO_DIR)." >&2
  echo "Clone it first: git clone https://github.com/gerardcm/movieradar.git" >&2
  exit 1
fi

echo "Pulling latest code..."
git pull --ff-only

if [ ! -f config.json ]; then
  echo "config.json not found in $REPO_DIR." >&2
  echo "Copy config.example.json to config.json and fill in your API keys first." >&2
  exit 1
fi

echo "Running movieradar..."
python3 movieradar.py --config config.json
