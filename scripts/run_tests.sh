#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f "$HOME/.reitti-live.env" ] && set -a && . "$HOME/.reitti-live.env" && set +a
exec "${VENV:-$HOME/reitti-venv}/bin/python" -m pytest -p no:cacheprovider "$@"