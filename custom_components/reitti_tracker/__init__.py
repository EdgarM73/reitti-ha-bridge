"""Reitti Tracker: push device_tracker locations to a Reitti server."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .const import (
    CONF_API_KEY,
    CONF_DEVICE,
    CONF_ENABLE_PUSH,
    CONF_IDLE_INTERVAL,
    CONF_INTERVAL,
    CONF_URL,
    DEFAULT_IDLE_INTERVAL,
    DEFAULT_INTERVAL,
    DOMAIN,
    INGEST_PATH,
    SERVICE_PUSH_NOW,
)

_LOGGER = logging.getLogger(__name__)


class ReittiPusher:
    """Sends the current tracker position to Reitti."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._lock = asyncio.Lock()
        self._last_pos: tuple | None = None
        self._last_sent: float | None = None

    @property
    def _opts(self) -> dict:
        return {**self.entry.data, **self.entry.options}

    async def push(self, _event: Event | None = None, *, force: bool = False) -> bool:
        opts = self._opts
        if not opts.get(CONF_ENABLE_PUSH, True):
            return False

        entity_id = opts[CONF_DEVICE]
        state = self.hass.states.get(entity_id)
        if state is None:
            _LOGGER.warning("Tracker %s not found", entity_id)
            return False
        lat = state.attributes.get("latitude")
        lon = state.attributes.get("longitude")
        if lat is None or lon is None:
            _LOGGER.debug("Tracker %s has no coordinates", entity_id)
            return False

        # Unchanged position: only report again after the idle interval.
        if not force and self._last_sent is not None:
            idle = opts.get(CONF_IDLE_INTERVAL, DEFAULT_IDLE_INTERVAL)
            if (lat, lon) == self._last_pos and time.monotonic() - self._last_sent < idle:
                return False

        payload = {
            "_type": "location",
            "tid": entity_id.split(".", 1)[1][:2].upper(),
            "lat": lat,
            "lon": lon,
            "alt": state.attributes.get("altitude", 0),
            "acc": state.attributes.get("gps_accuracy", 0),
            "tst": int(time.time()),
        }
        url = opts[CONF_URL].rstrip("/") + INGEST_PATH
        session = async_get_clientsession(self.hass)

        async with self._lock:
            try:
                async with session.post(
                    url,
                    params={"token": opts[CONF_API_KEY]},
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (200, 202):
                        _LOGGER.debug("Pushed %s to Reitti", payload)
                        self._last_pos = (lat, lon)
                        self._last_sent = time.monotonic()
                        return True
                    body = await resp.text()
                    if resp.status >= 500:
                        _LOGGER.warning(
                            "Reitti rejected push: %s %s. If the Reitti log says "
                            "'Token has no device attached', attach a device to "
                            "this API token in Reitti.",
                            resp.status, body,
                        )
                    else:
                        _LOGGER.warning(
                            "Reitti rejected push: %s %s", resp.status, body
                        )
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                _LOGGER.warning("Could not reach Reitti at %s: %s", url, err)
        return False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    pusher = ReittiPusher(hass, entry)
    entry.runtime_data = pusher
    opts = pusher._opts

    entry.async_on_unload(
        async_track_state_change_event(hass, [opts[CONF_DEVICE]], pusher.push)
    )
    entry.async_on_unload(
        async_track_time_interval(
            hass,
            pusher.push,
            timedelta(seconds=opts.get(CONF_INTERVAL, DEFAULT_INTERVAL)),
        )
    )

    async def _push_now(call: ServiceCall) -> None:
        for e in hass.config_entries.async_loaded_entries(DOMAIN):
            await e.runtime_data.push(force=True)

    if not hass.services.has_service(DOMAIN, SERVICE_PUSH_NOW):
        hass.services.async_register(DOMAIN, SERVICE_PUSH_NOW, _push_now)

    entry.async_on_unload(entry.add_update_listener(_reload))
    await pusher.push()
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    remaining = [
        e for e in hass.config_entries.async_loaded_entries(DOMAIN) if e is not entry
    ]
    if not remaining:
        hass.services.async_remove(DOMAIN, SERVICE_PUSH_NOW)
    return True
