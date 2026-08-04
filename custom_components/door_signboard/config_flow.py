"""Config flow for Door Signboard."""

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult

from .const import DEVICE_ID, DEVICE_NAME, DOMAIN


class DoorSignboardConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create the single Door Signboard config entry."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            await self.async_set_unique_id(DEVICE_ID)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=DEVICE_NAME, data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))
