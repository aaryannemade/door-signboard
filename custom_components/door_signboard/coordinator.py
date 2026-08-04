"""Persistent desired state and device status coordination."""

from collections.abc import Callable
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DEFAULT_STATE, DEFAULT_STATUS, DEVICE_ID, SCENES, validate_field

STORAGE_VERSION = 1
STORAGE_KEY = "door_signboard.state"
HEARTBEAT_TIMEOUT = timedelta(seconds=90)
logger = logging.getLogger(__name__)


class DoorSignboardCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Own all desired and reported signboard state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            logger=logger,
            config_entry=entry,
            name="Door Signboard",
        )
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.state = dict(DEFAULT_STATE)
        self.status = dict(DEFAULT_STATUS)
        self._last_seen = None
        self._desired_listeners: set[Callable[[], None]] = set()

    async def async_load(self) -> None:
        """Load persisted state and expose initial coordinator data."""

        stored = await self._store.async_load()
        if stored:
            self.state.update(stored.get("state", {}))
            self.status.update(stored.get("status", {}))
        self.status["connected"] = False
        self.async_set_updated_data(self.snapshot)

    @property
    def snapshot(self) -> dict[str, Any]:
        return {"state": dict(self.state), "status": dict(self.status)}

    async def async_update_field(self, field: str, value: str) -> None:
        """Persist one entity edit and push the complete desired state."""

        if field == "scene":
            if value not in SCENES:
                raise ValueError(f"Unsupported scene: {value}")
            normalized = value
        else:
            normalized = validate_field(field, value)
        if self.state[field] == normalized:
            return
        self.state[field] = normalized
        self.state["revision"] += 1
        self._changed()
        for listener in tuple(self._desired_listeners):
            listener()

    @callback
    def async_handle_status(self, data: dict[str, Any]) -> None:
        """Apply a status report received through the WebSocket API."""

        if data.get("device_id") != DEVICE_ID:
            return
        status = data.get("status")
        if status not in {"online", "heartbeat", "applied", "error", "offline"}:
            return

        if status == "offline":
            self.status["connected"] = False
        else:
            self.status["connected"] = True
            self._last_seen = dt_util.utcnow()

        if status == "applied":
            revision = data.get("revision")
            scene = data.get("scene")
            if (
                isinstance(revision, int)
                and revision >= self.status["applied_revision"]
                and revision <= self.state["revision"]
            ):
                self.status["applied_revision"] = revision
                if scene in SCENES:
                    self.status["last_applied_scene"] = scene
                self.status["last_error"] = ""
        elif status == "error":
            self.status["last_error"] = str(data.get("error", "Unknown error"))[:255]

        self._changed(persist=status in {"applied", "error"})

    @callback
    def async_subscribe_desired(
        self, listener: Callable[[], None]
    ) -> Callable[[], None]:
        """Subscribe a WebSocket connection to desired-state changes."""

        self._desired_listeners.add(listener)

        @callback
        def unsubscribe() -> None:
            self._desired_listeners.discard(listener)
            self.async_device_disconnected()

        return unsubscribe

    @callback
    def async_device_disconnected(self) -> None:
        if self.status["connected"]:
            self.status["connected"] = False
            self._changed(persist=False)

    @callback
    def async_check_heartbeat(self, now=None) -> None:
        if (
            self.status["connected"]
            and self._last_seen is not None
            and dt_util.utcnow() - self._last_seen > HEARTBEAT_TIMEOUT
        ):
            self.async_device_disconnected()

    def register_listeners(self) -> list[Any]:
        """Register the heartbeat timeout and return its unsubscribe call."""

        return [
            async_track_time_interval(
                self.hass, self.async_check_heartbeat, timedelta(seconds=30)
            )
        ]

    @callback
    def _changed(self, *, persist: bool = True) -> None:
        self.async_set_updated_data(self.snapshot)
        if persist:
            self._store.async_delay_save(
                lambda: {"state": self.state, "status": self.status},
                1,
            )
