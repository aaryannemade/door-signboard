"""Shared Door Signboard entity base."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_ID, DEVICE_NAME, DOMAIN
from .coordinator import DoorSignboardCoordinator


class DoorSignboardEntity(CoordinatorEntity[DoorSignboardCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: DoorSignboardCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{DEVICE_ID}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, DEVICE_ID)},
            manufacturer="Waveshare",
            model="3.52-inch e-Paper HAT",
            name=DEVICE_NAME,
        )


def get_coordinator(hass, entry: ConfigEntry) -> DoorSignboardCoordinator:
    return hass.data[DOMAIN][entry.entry_id]
