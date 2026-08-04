"""Constants and validation for the Door Signboard integration."""

from typing import Any

DOMAIN = "door_signboard"
DEVICE_ID = "door_signboard"
DEVICE_NAME = "Door Signboard"

WS_SUBSCRIBE = "door_signboard/subscribe"
WS_STATUS = "door_signboard/status"

SCENES = ("default", "delivery", "away", "busy")
EDITABLE_FIELDS = (
    "apartment_number",
    "name",
    "phone_number",
    "delivery_message",
    "delivery_otp",
    "away_message",
    "busy_message",
)
FIELD_LIMITS = {
    "apartment_number": 32,
    "name": 64,
    "phone_number": 13,
    "delivery_message": 160,
    "delivery_otp": 32,
    "away_message": 160,
    "busy_message": 160,
}
DEFAULT_STATE: dict[str, Any] = {
    "revision": 0,
    "scene": "default",
    "apartment_number": "Tower X / XXX",
    "name": "Resident",
    "phone_number": "911234567890",
    "delivery_message": "Please leave deliveries on the table",
    "delivery_otp": "",
    "away_message": "No one is at home right now, please call if urgent",
    "busy_message": "Please do not disturb. I'm currently busy.",
}
DEFAULT_STATUS: dict[str, Any] = {
    "connected": False,
    "applied_revision": 0,
    "last_applied_scene": "default",
    "last_error": "",
}


def validate_field(field: str, value: Any) -> str:
    """Validate and normalize one editable value."""

    if field not in EDITABLE_FIELDS:
        raise ValueError(f"Unknown signboard field: {field}")
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    value = value.strip()
    if any(character in value for character in ("\x00", "\r", "\n")):
        raise ValueError(f"{field} must be a single line")
    if field != "delivery_otp" and not value:
        raise ValueError(f"{field} cannot be empty")
    if len(value) > FIELD_LIMITS[field]:
        raise ValueError(f"{field} exceeds {FIELD_LIMITS[field]} characters")
    if field == "phone_number":
        digits = value.removeprefix("+")
        if len(digits) != 12 or not digits.isdigit():
            raise ValueError("phone_number must contain exactly 12 digits")
    return value


def desired_event_payload(state: dict[str, Any]) -> dict[str, Any]:
    """Return the stable wire representation of desired state."""

    return {
        "device_id": DEVICE_ID,
        "revision": state["revision"],
        "scene": state["scene"],
        **{field: state[field] for field in EDITABLE_FIELDS},
    }
