"""Scene selector for Door Signboard."""

from homeassistant.components.select import SelectEntity

from .const import SCENES
from .entity import DoorSignboardEntity, get_coordinator


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([DoorSignboardSceneSelect(get_coordinator(hass, entry))])


class DoorSignboardSceneSelect(DoorSignboardEntity, SelectEntity):
    _attr_translation_key = "scene"
    _attr_options = list(SCENES)

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "scene")

    @property
    def current_option(self) -> str:
        return self.coordinator.state["scene"]

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_update_field("scene", option)
