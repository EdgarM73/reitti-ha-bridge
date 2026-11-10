"""Config and options flow."""

from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

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
)

_IDLE = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=10, max=86400, step=1, unit_of_measurement="s",
        mode=selector.NumberSelectorMode.BOX,
    )
)

_INTERVAL = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=10, max=3600, step=1, unit_of_measurement="s",
        mode=selector.NumberSelectorMode.BOX,
    )
)


def _normalize(url: str) -> str:
    url = url.strip().rstrip("/")
    return url if url.startswith(("http://", "https://")) else f"http://{url}"


def _gps_trackers(hass) -> list[str]:
    """device_tracker entities that can report a position.

    Router/Bluetooth/ping trackers only know home/not_home and have no
    coordinates, so pushing them to Reitti is pointless. Keep GPS trackers
    (HA Companion App, OwnTracks, Traccar, ...) and anything with coordinates.
    """
    return sorted(
        state.entity_id
        for state in hass.states.async_all("device_tracker")
        if state.attributes.get("source_type") == "gps"
        or (
            state.attributes.get("latitude") is not None
            and state.attributes.get("longitude") is not None
        )
    )


async def _check(hass, url: str) -> bool:
    """Return True if the server answers at all (any HTTP response)."""
    try:
        async with async_get_clientsession(hass).get(
            url, timeout=aiohttp.ClientTimeout(total=8)
        ):
            return True
    except (aiohttp.ClientError, TimeoutError):
        return False


class ReittiConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_URL] = _normalize(user_input[CONF_URL])
            await self.async_set_unique_id(user_input[CONF_DEVICE])
            self._abort_if_unique_id_configured()
            if await _check(self.hass, user_input[CONF_URL]):
                return self.async_create_entry(
                    title=f"Reitti ({user_input[CONF_DEVICE]})", data=user_input
                )
            errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_URL): str,
                vol.Required(CONF_API_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_DEVICE): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="device_tracker",
                        include_entities=_gps_trackers(self.hass) or None,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Change URL, token and tracked device of an existing entry."""
        entry = self._get_reconfigure_entry()
        cur = {**entry.data, **entry.options}
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input[CONF_URL] = _normalize(user_input[CONF_URL])
            device = user_input[CONF_DEVICE]
            others = {
                e.unique_id
                for e in self._async_current_entries(include_ignore=False)
                if e.entry_id != entry.entry_id
            }
            if device in others:
                return self.async_abort(reason="already_configured")
            if await _check(self.hass, user_input[CONF_URL]):
                # Drop options that would shadow the new values (see ReittiPusher._opts).
                options = {
                    k: v
                    for k, v in entry.options.items()
                    if k not in (CONF_URL, CONF_API_KEY, CONF_DEVICE)
                }
                self.hass.config_entries.async_update_entry(
                    entry,
                    unique_id=device,
                    title=f"Reitti ({device})",
                    data={**entry.data, **user_input},
                    options=options,
                )  # the update listener reloads the entry
                return self.async_abort(reason="reconfigure_successful")
            errors["base"] = "cannot_connect"

        trackers = _gps_trackers(self.hass)
        if cur[CONF_DEVICE] not in trackers:
            trackers.append(cur[CONF_DEVICE])  # keep the current one selectable
        schema = vol.Schema(
            {
                vol.Required(CONF_URL): str,
                vol.Required(CONF_API_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_DEVICE): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="device_tracker", include_entities=sorted(trackers)
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                user_input
                or {
                    CONF_URL: cur[CONF_URL],
                    CONF_API_KEY: cur[CONF_API_KEY],
                    CONF_DEVICE: cur[CONF_DEVICE],
                },
            ),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ReittiOptionsFlow()


class ReittiOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_INTERVAL] = int(user_input[CONF_INTERVAL])
            user_input[CONF_IDLE_INTERVAL] = int(user_input[CONF_IDLE_INTERVAL])
            user_input[CONF_URL] = _normalize(user_input[CONF_URL])
            if await _check(self.hass, user_input[CONF_URL]):
                return self.async_create_entry(data=user_input)
            errors["base"] = "cannot_connect"
        cur = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL, default=cur[CONF_URL]): str,
                    vol.Required(
                        CONF_API_KEY, default=cur[CONF_API_KEY]
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Required(
                        CONF_ENABLE_PUSH, default=cur.get(CONF_ENABLE_PUSH, True)
                    ): bool,
                    vol.Required(
                        CONF_INTERVAL, default=cur.get(CONF_INTERVAL, DEFAULT_INTERVAL)
                    ): _INTERVAL,
                    vol.Required(
                        CONF_IDLE_INTERVAL,
                        default=cur.get(CONF_IDLE_INTERVAL, DEFAULT_IDLE_INTERVAL),
                    ): _IDLE,
                }
            ),
            errors=errors,
        )
