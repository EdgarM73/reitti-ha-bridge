#!/usr/bin/env bash
# Starts a local HA instance (http://localhost:8123) with this integration symlinked in.
set -euo pipefail
VENV="${VENV:-$HOME/reitti-venv}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"
CFG="${HA_CONFIG:-$HOME/ha-test-config}"
mkdir -p "$CFG/custom_components"
ln -sfn "$SRC/custom_components/reitti_tracker" "$CFG/custom_components/reitti_tracker"
exec "$VENV/bin/hass" -c "$CFG"