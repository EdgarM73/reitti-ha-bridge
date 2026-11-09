# Reitti Tracker (HACS)

[![Validate](https://github.com/EdgarM73/reitti-ha-bridge/actions/workflows/validate.yaml/badge.svg)](https://github.com/EdgarM73/reitti-ha-bridge/actions/workflows/validate.yaml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

Pushes the position of a Home Assistant `device_tracker` to a [Reitti](https://github.com/dedicatedcode/reitti)
server via its OwnTracks ingest endpoint (`/api/v1/ingest/owntracks`).

Useful if the Home Assistant Companion App already tracks your phone and you want
that location history in Reitti without running a second tracking app.

## Install

### HACS (custom repository)
1. HACS → ⋮ → *Custom repositories* → add `https://github.com/EdgarM73/reitti-ha-bridge`, category *Integration*.
2. Install *Reitti Tracker*, restart Home Assistant.
3. Settings → Devices & services → Add integration → *Reitti Tracker*.

### Manual
Copy `custom_components/reitti_tracker` into your Home Assistant `config/custom_components/` folder and restart.

## Setup
- **URL**: address of your Reitti server, e.g. `https://reitti.example.com` or `http://reitti.local:8080`
- **API token**: created in Reitti (Settings → API tokens). The token must have a **device attached**,
  otherwise Reitti answers with HTTP 500 (`Token has no device attached`).
- **Device tracker**: the entity whose position is forwarded

Options (changeable later): enable/disable pushing, interval (default 30 s), URL and token.
A push also happens on every state change of the tracker.

## Services
| Service | Description |
|---|---|
| `reitti_tracker.push_now` | Sends the current position immediately. |

## Troubleshooting
- *Reitti rejected push: 500* → attach a device to the API token in Reitti.
- *Could not reach Reitti* → check URL, reverse proxy and that Home Assistant can reach the host.
- Enable debug logging for `custom_components.reitti_tracker` to see every pushed payload.

## Development
Home Assistant core needs Linux, so on Windows use WSL.

```bash
scripts/setup_wsl_env.sh   # venv with Home Assistant + pytest plugin
scripts/run_tests.sh       # tests with a mocked Reitti server
scripts/run_ha.sh          # local Home Assistant with this integration
```

Optional live tests against a real Reitti instance: put `REITTI_URL` and `REITTI_TOKEN` into
`~/.reitti-live.env`. They send real location points; the simulated bike ride additionally needs `REITTI_LIVE_RIDE=1`.

## License
MIT
