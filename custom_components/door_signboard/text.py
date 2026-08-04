"""Editable text entities for Door Signboard."""

from dataclasses import dataclass

from homeassistant.components.text import TextEntity, TextEntityDescription, TextMode

from .const import FIELD_LIMITS
from .entity import DoorSignboardEntity, get_coordinator


@dataclass(frozen=True, kw_only=True)
class DoorSignboardTextDescription(TextEntityDescription):
    allow_empty: bool = False


DESCRIPTIONS = (
    DoorSignboardTextDescription(
        key="apartment_number", translation_key="apartment_number"
    ),
    DoorSignboardTextDescription(key="name", translation_key="resident_name"),
    DoorSignboardTextDescription(key="phone_number", translation_key="phone_number"),
    DoorSignboardTextDescription(
        key="delivery_message", translation_key="delivery_message"
    ),
    DoorSignboardTextDescription(
        key="delivery_otp", translation_key="delivery_otp", allow_empty=True
    ),
    DoorSignboardTextDescription(key="away_message", translation_key="away_message"),
    DoorSignboardTextDescription(key="busy_message", translation_key="busy_message"),
)


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = get_coordinator(hass, entry)
    async_add_entities(
        DoorSignboardText(coordinator, description) for description in DESCRIPTIONS
    )


class DoorSignboardText(DoorSignboardEntity, TextEntity):
    _attr_mode = TextMode.TEXT
    entity_description: DoorSignboardTextDescription

    def __init__(self, coordinator, description: DoorSignboardTextDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_native_min = 0 if description.allow_empty else 1
        self._attr_native_max = FIELD_LIMITS[description.key]
        if description.key == "phone_number":
            self._attr_pattern = r"^\+?[0-9]{12}$"

    @property
    def native_value(self) -> str:
        return self.coordinator.state[self.entity_description.key]

    async def async_set_value(self, value: str) -> None:
        await self.coordinator.async_update_field(self.entity_description.key, value)
