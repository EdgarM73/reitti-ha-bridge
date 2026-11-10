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

Options (changeable later):
- enable/disable pushing, URL and token
- **Interval** (default 30 s): how often the tracker is checked. A changed position is also sent on every state change.
- **Interval when position unchanged** (default 300 s): minimum time between two reports while the position has not changed.

## Buffering
Every point is buffered until Reitti has accepted it. If Reitti is down or rejects the push,
points are kept (up to 10 000, also across Home Assistant restarts) and delivered later in order
with their original timestamp. Retries back off from 30 s up to 10 min; `push_now` retries immediately.
The log warns once per outage and then every 30 minutes.

## Sensors
| Sensor | Description |
|---|---|
| Status | `ok`, `unreachable`, `rejected` or `auth_failed`; the last error is in the attributes |
| Last successful push | time Reitti last accepted a point |
| Buffered points | points waiting for delivery |

If Reitti answers 401/403, Home Assistant asks for a new API token (re-authentication).

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
