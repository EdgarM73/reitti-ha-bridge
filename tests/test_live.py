"""Live tests against a real Reitti server.

Skipped unless REITTI_URL (and, for the push test, REITTI_TOKEN) are set.
WARNING: the push test sends one real location point to that server.
"""
import asyncio
import os
import socket
from unittest.mock import patch

import aiohttp
import pytest
import pytest_socket
from pytest_socket import enable_socket, socket_allow_hosts
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.reitti_tracker import ReittiPusher
from custom_components.reitti_tracker.config_flow import _check, _normalize
from custom_components.reitti_tracker.const import DOMAIN, INGEST_PATH

URL = os.environ.get("REITTI_URL", "")
TOKEN = os.environ.get("REITTI_TOKEN", "")

pytestmark = pytest.mark.usefixtures("socket_enabled")


@pytest.fixture(autouse=True)
async def real_session(hass):
    """HA's test session uses a stubbed resolver; use a plain aiohttp session."""
    enable_socket()
    socket_allow_hosts(None)
    # HA's plugin additionally hard-blocks non-local connects; restore the real one.
    socket.socket.connect = pytest_socket._true_connect
    async with aiohttp.ClientSession() as session:
        with patch("custom_components.reitti_tracker.async_get_clientsession", return_value=session), \
             patch("custom_components.reitti_tracker.config_flow.async_get_clientsession", return_value=session), \
             patch(f"{__name__}.async_get_clientsession", return_value=session):
            yield session


@pytest.mark.skipif(not URL, reason="REITTI_URL not set")
async def test_live_server_reachable(hass):
    assert await _check(hass, _normalize(URL))


@pytest.mark.skipif(not URL, reason="REITTI_URL not set")
async def test_live_wrong_token_rejected(hass):
    """The ingest endpoint must reject a bogus token (proves auth is enforced)."""
    session = async_get_clientsession(hass)
    async with session.post(
        _normalize(URL) + INGEST_PATH,
        params={"token": "invalid-token-for-test"},
        json={"_type": "location", "lat": 0, "lon": 0, "tst": 1},
        timeout=aiohttp.ClientTimeout(total=10),
    ) as resp:
        assert resp.status in (400, 401, 403, 500), resp.status


@pytest.mark.skipif(not (URL and TOKEN), reason="REITTI_URL/REITTI_TOKEN not set")
async def test_live_push(hass):
    hass.states.async_set(
        "device_tracker.livetest",
        "not_home",
        {"latitude": 48.137, "longitude": 11.575, "gps_accuracy": 10, "altitude": 520},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"url": _normalize(URL), "api_key": TOKEN, "device": "device_tracker.livetest"},
        unique_id="device_tracker.livetest",
    )
    entry.add_to_hass(hass)
    # Use the pusher directly (no setup) so exactly one point is sent.
    assert await ReittiPusher(hass, entry).push() is True

# --- Simulated bike ride ---------------------------------------------------
# Hauptbahnhof -> Stachus (Karlsplatz), ~470 m straight line at ~14 km/h.
# Opt-in (takes ~2 minutes, sends ~25 real points): REITTI_LIVE_RIDE=1
RIDE_START = (48.1403, 11.5600)
RIDE_END = (48.1390, 11.5660)
RIDE_SECONDS = int(os.environ.get("REITTI_RIDE_SECONDS", "120"))
RIDE_STEP = 5


@pytest.mark.skipif(
    not (URL and TOKEN and os.environ.get("REITTI_LIVE_RIDE")),
    reason="set REITTI_URL, REITTI_TOKEN and REITTI_LIVE_RIDE=1",
)
async def test_live_bike_ride_to_stachus(hass):
    entity = "device_tracker.livetest"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"url": _normalize(URL), "api_key": TOKEN, "device": entity},
        unique_id=entity,
    )
    entry.add_to_hass(hass)
    pusher = ReittiPusher(hass, entry)

    steps = RIDE_SECONDS // RIDE_STEP
    for i in range(steps + 1):
        f = i / steps
        lat = RIDE_START[0] + (RIDE_END[0] - RIDE_START[0]) * f
        lon = RIDE_START[1] + (RIDE_END[1] - RIDE_START[1]) * f
        hass.states.async_set(
            entity,
            "not_home",
            {"latitude": lat, "longitude": lon, "gps_accuracy": 8, "altitude": 520},
        )
        assert await pusher.push() is True, f"push {i}/{steps} failed"
        if i < steps:
            await asyncio.sleep(RIDE_STEP)
