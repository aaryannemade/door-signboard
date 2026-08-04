"""Non-admin WebSocket commands used by the Raspberry Pi client."""

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DEVICE_ID, DOMAIN, WS_STATUS, WS_SUBSCRIBE, desired_event_payload
from .coordinator import DoorSignboardCoordinator


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, websocket_subscribe)
    websocket_api.async_register_command(hass, websocket_status)


def _coordinator(hass: HomeAssistant) -> DoorSignboardCoordinator | None:
    entries = hass.data.get(DOMAIN, {})
    return next(iter(entries.values()), None)


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_SUBSCRIBE,
        vol.Required("device_id"): str,
    }
)
@callback
def websocket_subscribe(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Subscribe a device to complete desired-state messages."""

    coordinator = _coordinator(hass)
    if coordinator is None or msg["device_id"] != DEVICE_ID:
        connection.send_error(msg["id"], "not_found", "Door Signboard not found")
        return

    @callback
    def send_desired_state() -> None:
        connection.send_message(
            websocket_api.event_message(
                msg["id"], desired_event_payload(coordinator.state)
            )
        )

    connection.subscriptions[msg["id"]] = coordinator.async_subscribe_desired(
        send_desired_state
    )
    connection.send_result(msg["id"])
    send_desired_state()


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_STATUS,
        vol.Required("device_id"): str,
        vol.Required("status"): vol.In(
            {"online", "heartbeat", "applied", "error", "offline"}
        ),
        vol.Optional("revision"): int,
        vol.Optional("scene"): str,
        vol.Optional("error"): str,
    }
)
@callback
def websocket_status(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Receive device availability and render results."""

    coordinator = _coordinator(hass)
    if coordinator is None or msg["device_id"] != DEVICE_ID:
        connection.send_error(msg["id"], "not_found", "Door Signboard not found")
        return
    coordinator.async_handle_status(msg)
    connection.send_result(msg["id"])
