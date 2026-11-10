"""Reitti Tracker: push device_tracker locations to a Reitti server."""

from __future__ import annotations

import asyncio
from collections import deque
import logging
import time
from datetime import timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store

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
    FLUSH_BATCH,
    INGEST_PATH,
    MAX_BUFFER,
    REMIND_AFTER,
    RETRY_MAX,
    RETRY_MIN,
    SERVICE_PUSH_NOW,
    STATUS_AUTH_FAILED,
    STATUS_OK,
    STATUS_REJECTED,
    STATUS_UNREACHABLE,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]
SAVE_DELAY = 10


def signal_update(entry_id: str) -> str:
    return f"{DOMAIN}_{entry_id}_update"


class ReittiPusher:
    """Records tracker positions and delivers them to Reitti.

    Every position is put into a buffer first and removed only after Reitti
    accepted it, so points survive outages of Reitti and restarts of Home
    Assistant and are delivered later with their original timestamp.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._lock = asyncio.Lock()
        self._store: Store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._queue: deque[dict] = deque(maxlen=MAX_BUFFER)
        self._last_pos: tuple | None = None
        self._last_recorded: float | None = None
        self._last_reported = None  # datetime of the last tracker report used
        # delivery state
        self._failures = 0
        self._retry_at = 0.0
        self._last_warned = 0.0
        # exposed to the sensors
        self.status: str | None = None
        self.last_error: str | None = None
        self.last_error_at: float | None = None
        self.last_success_at: float | None = None

    @property
    def _opts(self) -> dict:
        return {**self.entry.data, **self.entry.options}

    @property
    def buffered(self) -> int:
        return len(self._queue)

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self._queue.extend(data.get("queue", []))
        self.last_success_at = data.get("last_success")

    def _data_to_save(self) -> dict:
        return {"queue": list(self._queue), "last_success": self.last_success_at}

    async def async_save(self) -> None:
        await self._store.async_save(self._data_to_save())

    async def async_remove_store(self) -> None:
        await self._store.async_remove()

    def _changed(self) -> None:
        self._store.async_delay_save(self._data_to_save, SAVE_DELAY)
        async_dispatcher_send(self.hass, signal_update(self.entry.entry_id))

    def _record(self, force: bool) -> None:
        """Put the tracker's current position into the buffer if it is due."""
        opts = self._opts
        entity_id = opts[CONF_DEVICE]
        state = self.hass.states.get(entity_id)
        if state is None:
            _LOGGER.debug("Tracker %s not found", entity_id)
            return
        lat = state.attributes.get("latitude")
        lon = state.attributes.get("longitude")
        if lat is None or lon is None:
            _LOGGER.debug("Tracker %s has no coordinates", entity_id)
            return

        # Unchanged position: only report again after the idle interval.
        if not force and self._last_recorded is not None:
            idle = opts.get(CONF_IDLE_INTERVAL, DEFAULT_IDLE_INTERVAL)
            if (
                (lat, lon) == self._last_pos
                and time.monotonic() - self._last_recorded < idle
            ):
                return

        if len(self._queue) == MAX_BUFFER:
            _LOGGER.warning(
                "Buffer is full (%s points), dropping the oldest point", MAX_BUFFER
            )
        # Timestamp: when the tracker reported this position to Home Assistant.
        # If it has not reported since the last point (idle repeat), use now.
        reported = getattr(state, "last_reported", None) or state.last_updated
        if self._last_reported is None or reported > self._last_reported:
            tst = int(reported.timestamp())
            self._last_reported = reported
        else:
            tst = int(time.time())

        attrs = state.attributes
        payload = {
            "_type": "location",
            "tid": entity_id.split(".", 1)[1][:2].upper(),
            "lat": lat,
            "lon": lon,
            "alt": attrs.get("altitude", 0),
            "acc": attrs.get("gps_accuracy", 0),
            "tst": tst,
        }
        # Optional OwnTracks fields, only if the tracker provides them.
        for key, attr, convert in (
            ("batt", "battery_level", float),
            ("vel", "speed", lambda v: round(float(v) * 3.6)),  # m/s -> km/h
            ("cog", "course", lambda v: round(float(v))),
            ("vac", "vertical_accuracy", lambda v: round(float(v))),
        ):
            value = attrs.get(attr)
            if value is None:
                continue
            try:
                payload[key] = convert(value)
            except (TypeError, ValueError):
                pass
        self._queue.append(payload)
        self._last_pos = (lat, lon)
        self._last_recorded = time.monotonic()
        self._changed()

    async def push(self, _event: Event | None = None, *, force: bool = False) -> bool:
        """Record the current position if due, then deliver the buffer.

        Returns True if something was delivered and the buffer is empty.
        """
        if not self._opts.get(CONF_ENABLE_PUSH, True):
            return False
        self._record(force)
        if not self._queue:
            return False
        if not force and time.monotonic() < self._retry_at:
            return False  # backing off after a failure
        return await self._flush()

    async def _flush(self) -> bool:
        opts = self._opts
        url = opts[CONF_URL].rstrip("/") + INGEST_PATH
        session = async_get_clientsession(self.hass)
        sent = 0
        async with self._lock:
            while self._queue and sent < FLUSH_BATCH:
                payload = self._queue[0]
                try:
                    async with session.post(
                        url,
                        params={"token": opts[CONF_API_KEY]},
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        status = resp.status
                        body = "" if status in (200, 202) else await resp.text()
                except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                    self._failed(STATUS_UNREACHABLE, f"Could not reach Reitti at {url}: {err}")
                    return False

                if status in (200, 202):
                    self._queue.popleft()
                    sent += 1
                    self._succeeded()
                    continue
                if status in (400, 422):
                    # Reitti will never accept this point; don't block the rest.
                    _LOGGER.warning(
                        "Reitti refused a point for good (%s %s), dropping it: %s",
                        status, body, payload,
                    )
                    self._queue.popleft()
                    self._changed()
                    continue
                if status in (401, 403):
                    self._failed(
                        STATUS_AUTH_FAILED,
                        f"Reitti rejected push: {status} {body}. The API token is not accepted",
                    )
                    self.entry.async_start_reauth(self.hass)
                    return False
                hint = (
                    ". If the Reitti log says 'Token has no device attached', "
                    "attach a device to this API token in Reitti"
                    if status >= 500
                    else ""
                )
                self._failed(STATUS_REJECTED, f"Reitti rejected push: {status} {body}{hint}")
                return False

        if self._queue:
            # More than one batch is buffered: keep going without blocking the caller.
            self.entry.async_create_background_task(
                self.hass, self._flush(), f"{DOMAIN} flush"
            )
            return False
        return sent > 0

    def _succeeded(self) -> None:
        if self._failures:
            _LOGGER.info(
                "Reitti accepts points again after %s failed attempts, "
                "%s buffered points left to deliver",
                self._failures, len(self._queue),
            )
        self._failures = 0
        self._retry_at = 0.0
        self.status = STATUS_OK
        self.last_success_at = time.time()
        self._changed()

    def _failed(self, status: str, message: str) -> None:
        """Warn once per outage, then only remind now and then."""
        self._failures += 1
        now = time.monotonic()
        self._retry_at = now + min(RETRY_MIN * 2 ** (self._failures - 1), RETRY_MAX)
        if self._failures == 1 or now - self._last_warned >= REMIND_AFTER:
            self._last_warned = now
            _LOGGER.warning(
                "%s. %s points are buffered and will be delivered later "
                "(attempt %s, further failures are logged at debug level)",
                message, len(self._queue), self._failures,
            )
        else:
            _LOGGER.debug("%s (attempt %s)", message, self._failures)
        self.status = status
        self.last_error = message
        self.last_error_at = time.time()
        self._changed()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    pusher = ReittiPusher(hass, entry)
    await pusher.async_load()
    entry.runtime_data = pusher
    opts = pusher._opts

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

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
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.async_save()  # keep undelivered points
    remaining = [
        e for e in hass.config_entries.async_loaded_entries(DOMAIN) if e is not entry
    ]
    if not remaining:
        hass.services.async_remove(DOMAIN, SERVICE_PUSH_NOW)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_remove()
