#!/usr/bin/env bash
# Creates a venv with Home Assistant + pytest plugin (HA core needs Linux: fcntl).
set -euo pipefail
VENV="${VENV:-$HOME/reitti-venv}"
command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/install.sh | sh; }
export PATH="$HOME/.local/bin:$PATH"
uv venv --clear "$VENV" --python 3.14
uv pip install --python "$VENV/bin/python" homeassistant pytest-homeassistant-custom-component
"$VENV/bin/python" -c "import homeassistant.const as c; print('HA', c.__version__)"
