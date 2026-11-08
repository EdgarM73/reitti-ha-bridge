# Reitti Tracker (HACS)

Pushes the position of a Home Assistant `device_tracker` to a [Reitti](https://github.com/dedicatedcode/reitti)
server via its OwnTracks ingest endpoint (`/api/v1/ingest/owntracks`).

## Install
1. HACS → Custom repositories → add this repo (category *Integration*).
2. Install, restart Home Assistant.
3. Settings → Devices & services → Add integration → *Reitti Tracker*.

## Setup
- **URL**: e.g. `http://reitti.local:8080`
- **API token**: created in Reitti (Settings → API tokens)
- **Device tracker**: the entity to forward

Options: enable/disable pushing, interval (default 30 s). A push also happens on every state change.

Service `reitti_tracker.push_now` sends the current position immediately.
