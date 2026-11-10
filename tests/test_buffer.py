"""Buffering, error handling and status sensors."""

import logging
from unittest.mock import patch

import aiohttp

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.reitti_tracker.const import DOMAIN

from .test_push import DATA, ENDPOINT, _setup

TRACKER = "device_tracker.iphone13"
MONO = "custom_components.reitti_tracker.time.monotonic"


def _move(hass, lat):
    hass.states.async_set(TRACKER, "not_home", {"latitude": lat, "longitude": 11.5})


def _state(hass, entry, key):
    reg = er.async_get(hass)
    entity_id = reg.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id, key
    return hass.states.get(entity_id)


async def _setup_down(hass, aioclient_mock):
    """Set up while Reitti is unreachable."""
    aioclient_mock.post(ENDPOINT, exc=aiohttp.ClientError("down"))
    _move(hass, 48.2)
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id=DATA["device"])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_points_are_buffered_and_delivered_in_order(hass, aioclient_mock):
    entry = await _setup_down(hass, aioclient_mock)
    _move(hass, 48.3)
    await hass.async_block_till_done()
    _move(hass, 48.4)
    await hass.async_block_till_done()
    pusher = entry.runtime_data
    assert pusher.buffered == 3
    assert _state(hass, entry, "buffered").state == "3"
    assert _state(hass, entry, "status").state == "unreachable"
    queued = [dict(p) for p in pusher._queue]

    aioclient_mock.clear_requests()
    aioclient_mock.post(ENDPOINT, status=200)
    with patch(MONO, return_value=1e9):  # backoff is over
        assert await pusher.push() is True
    sent = [c[2] for c in aioclient_mock.mock_calls]
    # same order, original timestamps (the idle interval is over too, so the
    # current position is reported once more at the end)
    assert sent[:3] == queued
    assert [p["lat"] for p in sent] == [48.2, 48.3, 48.4, 48.4]
    assert pusher.buffered == 0
    assert _state(hass, entry, "buffered").state == "0"
    assert _state(hass, entry, "status").state == "ok"
    assert _state(hass, entry, "last_push").state not in ("unknown", "unavailable")


async def test_backoff_and_single_warning(hass, aioclient_mock, caplog):
    with patch(MONO, return_value=1000.0):
        entry = await _setup_down(hass, aioclient_mock)
        pusher = entry.runtime_data
        n = len(aioclient_mock.mock_calls)
        _move(hass, 48.3)
        await hass.async_block_till_done()
        # still backing off: point is recorded, but no request is made
        assert pusher.buffered == 2 and len(aioclient_mock.mock_calls) == n
    for t in (1031.0, 1100.0, 1300.0):
        with patch(MONO, return_value=t):
            await pusher.push()
    assert len(aioclient_mock.mock_calls) == n + 3
    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "Could not reach Reitti" in r.message
    ]
    assert len(warnings) == 1

    with patch(MONO, return_value=1000.0 + 1300 + 1800):  # reminder is due
        await pusher.push()
    assert len([
        r for r in caplog.records
        if r.levelno == logging.WARNING and "Could not reach Reitti" in r.message
    ]) == 2

    aioclient_mock.clear_requests()
    aioclient_mock.post(ENDPOINT, status=200)
    await hass.services.async_call(DOMAIN, "push_now", blocking=True)
    assert "accepts points again" in caplog.text
    assert pusher.buffered == 0


async def test_buffer_survives_reload(hass, aioclient_mock):
    entry = await _setup_down(hass, aioclient_mock)
    _move(hass, 48.3)
    await hass.async_block_till_done()
    assert entry.runtime_data.buffered == 2
    assert await hass.config_entries.async_unload(entry.entry_id)

    aioclient_mock.clear_requests()
    aioclient_mock.post(ENDPOINT, status=200)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    lats = [c[2]["lat"] for c in aioclient_mock.mock_calls]
    assert lats[:2] == [48.2, 48.3]
    assert entry.runtime_data.buffered == 0


async def test_bad_point_is_dropped(hass, aioclient_mock):
    entry = await _setup(hass, aioclient_mock, status=400)
    assert entry.runtime_data.buffered == 0


async def test_server_error_keeps_point(hass, aioclient_mock):
    entry = await _setup(hass, aioclient_mock, status=500)
    assert entry.runtime_data.buffered == 1
    assert _state(hass, entry, "status").state == "rejected"
    assert "500" in _state(hass, entry, "status").attributes["last_error"]


async def test_auth_error_starts_reauth(hass, aioclient_mock):
    entry = await _setup(hass, aioclient_mock, status=401)
    assert entry.runtime_data.buffered == 1
    assert _state(hass, entry, "status").state == "auth_failed"
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]

    aioclient_mock.clear_requests()
    aioclient_mock.post(ENDPOINT, status=200)
    r = await hass.config_entries.flow.async_configure(
        flows[0]["flow_id"], {"api_key": "fresh"}
    )
    assert r["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert entry.data["api_key"] == "fresh"
    assert aioclient_mock.mock_calls[0][1].query["token"] == "fresh"
    assert entry.runtime_data.buffered == 0


async def test_remove_entry_deletes_buffer(hass, aioclient_mock, hass_storage):
    entry = await _setup_down(hass, aioclient_mock)
    assert await hass.config_entries.async_unload(entry.entry_id)
    key = f"{DOMAIN}.{entry.entry_id}"
    assert len(hass_storage[key]["data"]["queue"]) == 1
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage


async def test_timestamp_is_report_time_and_extras_are_sent(hass, aioclient_mock):
    entry = await _setup(hass, aioclient_mock)
    hass.states.async_set(
        TRACKER,
        "not_home",
        {
            "latitude": 48.5, "longitude": 11.5, "gps_accuracy": 7, "altitude": 510,
            "battery_level": 65, "speed": 5, "course": 181.4, "vertical_accuracy": 3,
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get(TRACKER)
    body = aioclient_mock.mock_calls[-1][2]
    assert body["tst"] == int(state.last_reported.timestamp())
    assert (body["batt"], body["vel"], body["cog"], body["vac"]) == (65.0, 18, 181, 3)

    # idle repeat of the same report: current time, not the old report time
    with patch("custom_components.reitti_tracker.time.time", return_value=2_000_000_000):
        await hass.services.async_call(DOMAIN, "push_now", blocking=True)
    assert aioclient_mock.mock_calls[-1][2]["tst"] == 2_000_000_000


async def test_missing_or_bad_extras_are_left_out(hass, aioclient_mock):
    await _setup(hass, aioclient_mock)
    hass.states.async_set(
        TRACKER, "not_home", {"latitude": 48.6, "longitude": 11.5, "speed": "n/a"}
    )
    await hass.async_block_till_done()
    body = aioclient_mock.mock_calls[-1][2]
    assert not {"batt", "vel", "cog", "vac"} & set(body)


async def test_retry_does_not_wait_for_the_check_interval(hass, aioclient_mock):
    """With a long check interval a stationary tracker must still recover."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    aioclient_mock.post(ENDPOINT, status=502, text="<html>\n<h1>502 Bad Gateway</h1>\n</html>")
    _move(hass, 48.2)
    entry = MockConfigEntry(
        domain=DOMAIN, data=DATA, unique_id=DATA["device"],
        options={"interval_seconds": 3600},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    pusher = entry.runtime_data
    assert pusher.buffered == 1
    assert "\n" not in pusher.last_error and "Token has no device" not in pusher.last_error

    aioclient_mock.clear_requests()
    aioclient_mock.post(ENDPOINT, status=200)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert pusher.buffered == 0
    assert pusher.status == "ok"
