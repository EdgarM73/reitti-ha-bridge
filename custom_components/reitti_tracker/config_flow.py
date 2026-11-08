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
    CONF_INTERVAL,
    CONF_URL,
    DEFAULT_INTERVAL,
    DOMAIN,
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
                    selector.EntitySelectorConfig(domain="device_tracker")
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
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
                }
            ),
            errors=errors,
        )
