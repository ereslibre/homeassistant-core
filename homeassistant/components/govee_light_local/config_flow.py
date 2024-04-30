"""Config flow for Govee light local."""

from __future__ import annotations

import asyncio
import ipaddress
import logging

from govee_local_api import GoveeController
import voluptuous as vol

from homeassistant.components import network
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_flow
import homeassistant.helpers.config_validation as cv

from homeassistant.components.light import (
    PLATFORM_SCHEMA
)

from homeassistant.const import {
    CONF_IP_ADDRESS,
    CONF_NAME
}

from .const import (
    CONF_LISTENING_PORT_DEFAULT,
    CONF_MULTICAST_ADDRESS_DEFAULT,
    CONF_TARGET_PORT_DEFAULT,
    DISCOVERY_TIMEOUT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

class GoveeFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> GoveeFlowHandler(config_entry):
        """Get the options flow for this handler."""
        return GoveeFlowHandler(config_entry)

    def __init__(self) -> None:
        self.host: str = {}
        self.port: int = {}

    def _show_form(
            self,
            step_id: str,
            user_input: dict[str, Any] | None = None,
            errors: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        if not user_input:
            user_input = {}

        description_placeholders = {}
        data_schema = vol.Schema(
            {
                vol.Required(CONF_IP_ADDRESS): vol.All(ipaddress.ip_address, cv.string),
                vol.Optional(CONF_NAME, default="Govee light"): cv.string,
            }
        )

        return self.async_show_form(
            step_id=step_id,
            data_schema=PLATFORM_SCHEMA,
            errors=errors or {},
            description_placeholders=description_placeholders,
        )

async def _async_has_devices(hass: HomeAssistant) -> bool:
    """Return if there are devices that can be discovered."""

    adapter = await network.async_get_source_ip(hass, network.PUBLIC_TARGET_IP)

    controller: GoveeController = GoveeController(
        loop=hass.loop,
        logger=_LOGGER,
        listening_address=adapter,
        broadcast_address=CONF_MULTICAST_ADDRESS_DEFAULT,
        broadcast_port=CONF_TARGET_PORT_DEFAULT,
        listening_port=CONF_LISTENING_PORT_DEFAULT,
        discovery_enabled=True,
        discovery_interval=1,
        update_enabled=False,
    )

    await controller.start()

    try:
        async with asyncio.timeout(delay=DISCOVERY_TIMEOUT):
            while not controller.devices:
                await asyncio.sleep(delay=1)
    except TimeoutError:
        _LOGGER.debug("No devices found")

    devices_count = len(controller.devices)
    controller.cleanup()

    return devices_count > 0


config_entry_flow.register_discovery_flow(
    DOMAIN, "Govee light local", _async_has_devices
)
