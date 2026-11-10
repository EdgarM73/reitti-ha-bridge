"""Diagnostic sensors: is the position actually arriving in Reitti?"""

from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from . import ReittiPusher, signal_update
from .const import (
    DOMAIN,
    STATUS_AUTH_FAILED,
    STATUS_OK,
    STATUS_REJECTED,
    STATUS_UNREACHABLE,
)


def _dt(ts: float | None) -> datetime | None:
    return None if ts is None else datetime.fromtimestamp(ts, timezone.utc)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    async_add_entities(
        [StatusSensor(entry), LastPushSensor(entry), BufferedSensor(entry)]
    )


class _Base(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, key: str) -> None:
        self._entry = entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _pusher(self) -> ReittiPusher:
        return self._entry.runtime_data

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._entry.entry_id), self._update
            )
        )

    @callback
    def _update(self) -> None:
        self.async_write_ha_state()


class StatusSensor(_Base):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [STATUS_OK, STATUS_UNREACHABLE, STATUS_REJECTED, STATUS_AUTH_FAILED]

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry, "status")

    @property
    def native_value(self) -> str | None:
        return self._pusher.status

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "last_error": self._pusher.last_error,
            "last_error_at": _dt(self._pusher.last_error_at),
        }


class LastPushSensor(_Base):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry, "last_push")

    @property
    def native_value(self) -> datetime | None:
        return _dt(self._pusher.last_success_at)


class BufferedSensor(_Base):
    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry, "buffered")

    @property
    def native_value(self) -> int:
        return self._pusher.buffered
