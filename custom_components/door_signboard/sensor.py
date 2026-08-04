"""Diagnostic sensors for Door Signboard."""

from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory

from .entity import DoorSignboardEntity, get_coordinator


@dataclass(frozen=True, kw_only=True)
class DoorSignboardSensorDescription(SensorEntityDescription):
    source: str


DESCRIPTIONS = (
    DoorSignboardSensorDescription(
        key="desired_revision", translation_key="desired_revision", source="state"
    ),
    DoorSignboardSensorDescription(
        key="applied_revision", translation_key="applied_revision", source="status"
    ),
    DoorSignboardSensorDescription(
        key="last_applied_scene", translation_key="last_applied_scene", source="status"
    ),
    DoorSignboardSensorDescription(
        key="last_error", translation_key="last_error", source="status"
    ),
)


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = get_coordinator(hass, entry)
    async_add_entities(
        DoorSignboardSensor(coordinator, description) for description in DESCRIPTIONS
    )


class DoorSignboardSensor(DoorSignboardEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    entity_description: DoorSignboardSensorDescription

    def __init__(
        self, coordinator, description: DoorSignboardSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        source = (
            self.coordinator.state
            if self.entity_description.source == "state"
            else self.coordinator.status
        )
        key = (
            "revision"
            if self.entity_description.key == "desired_revision"
            else self.entity_description.key
        )
        return source[key]
