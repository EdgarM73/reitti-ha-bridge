"""A moving tracker that stays silent is not repeated with the current time."""

from datetime import timedelta
from unittest.mock import patch

from homeassistant.util import dt as dt_util

from .test_push import _setup

TRACKER = "device_tracker.iphone13"
MONO = "custom_components.reitti_tracker.time.monotonic"
NOW = "custom_components.reitti_tracker.dt_util.utcnow"


async def _report(hass, aioclient_mock, **attrs):
    """Set up, then let the tracker report a new position with the given attributes."""
    entry = await _setup(hass, aioclient_mock)
    hass.states.async_set(
        TRACKER, "not_home", {"latitude": 48.3, "longitude": 11.6, **attrs}
    )
    await hass.async_block_till_done()
    return entry, len(aioclient_mock.mock_calls)


async def test_moving_tracker_is_not_repeated(hass, aioclient_mock):
    entry, n = await _report(hass, aioclient_mock, speed=13)
    with patch(MONO, return_value=1e9):  # idle interval is over
        assert await entry.runtime_data.push() is False
    assert len(aioclient_mock.mock_calls) == n


async def test_moving_tracker_is_repeated_after_long_silence(hass, aioclient_mock):
    entry, n = await _report(hass, aioclient_mock, speed=13)
    later = dt_util.utcnow() + timedelta(minutes=20)
    with patch(MONO, return_value=1e9), patch(NOW, return_value=later):
        await entry.runtime_data.push()
    assert len(aioclient_mock.mock_calls) == n + 1


async def test_standing_tracker_is_repeated(hass, aioclient_mock):
    entry, n = await _report(hass, aioclient_mock, speed=0)
    with patch(MONO, return_value=1e9):
        await entry.runtime_data.push()
    assert len(aioclient_mock.mock_calls) == n + 1


async def test_tracker_without_speed_is_repeated(hass, aioclient_mock):
    entry, n = await _report(hass, aioclient_mock)
    with patch(MONO, return_value=1e9):
        await entry.runtime_data.push()
    assert len(aioclient_mock.mock_calls) == n + 1


async def test_push_now_still_sends_for_moving_tracker(hass, aioclient_mock):
    entry, n = await _report(hass, aioclient_mock, speed=13)
    await entry.runtime_data.push(force=True)
    assert len(aioclient_mock.mock_calls) == n + 1
