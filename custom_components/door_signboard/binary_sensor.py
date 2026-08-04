"""Connectivity sensor for Door Signboard."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory

from .entity import DoorSignboardEntity, get_coordinator


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([DoorSignboardConnectedSensor(get_coordinator(hass, entry))])


class DoorSignboardConnectedSensor(DoorSignboardEntity, BinarySensorEntity):
    _attr_translation_key = "connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "connected")

    @property
    def is_on(self) -> bool:
        return self.coordinator.status["connected"]
