"""Default content displayed by the door signboard."""

from dataclasses import dataclass
from enum import Enum


class Scene(str, Enum):
    """The four sign layouts a user can select in Home Assistant.

    Subclassing ``str`` lets a Scene be compared to and serialized as its plain
    string value (e.g. ``"delivery"``), which the WebSocket payloads use.
    """

    DEFAULT = "default"
    DELIVERY = "delivery"
    AWAY = "away"
    BUSY = "busy"


# Placeholder defaults shown when Home Assistant has not supplied real values.
APARTMENT_NUMBER = "Tower X / XXX"
DELIVERY_MESSAGE = "Please leave Deliveries on the table"
AWAY_MESSAGE = "No one is at home right now, please call if urgent"
BUSY_MESSAGE = "Please do not disturb. I'm currently busy."
NAME = "XXXXXX"
PHONE_NUMBER = "911234567890"


@dataclass(frozen=True)
class SignContent:
    """Content values used to populate each scene layout."""

    apartment_number: str = APARTMENT_NUMBER
    delivery_message: str = DELIVERY_MESSAGE
    delivery_otp: str | None = None
    away_message: str = AWAY_MESSAGE
    busy_message: str = BUSY_MESSAGE
    name: str = NAME
    phone_number: str = PHONE_NUMBER

    def message_for(self, scene: Scene) -> str:
        """Return the message body for a message-bearing scene.

        Only DELIVERY, AWAY, and BUSY have a message; DEFAULT is not a valid
        key here and will raise KeyError by design.
        """

        return {
            Scene.DELIVERY: self.delivery_message,
            Scene.AWAY: self.away_message,
            Scene.BUSY: self.busy_message,
        }[scene]

    def formatted_phone_number(self) -> str:
        """Format a 12-digit number (country code + number) as +XX XXXXX XXXXX.

        Accepts an optional leading "+". Also doubles as validation: callers
        rely on this raising when the stored number is malformed.
        """

        digits = self.phone_number.removeprefix("+")
        if len(digits) != 12 or not digits.isdigit():
            raise ValueError("Phone number must contain exactly 12 digits")
        # e.g. "911234567890" -> "+91 12345 67890": 2-digit code, then 5 + 5.
        return f"+{digits[:2]} {digits[2:7]} {digits[7:]}"


@dataclass(frozen=True)
class DesiredState:
    """A complete, revisioned desired state received from Home Assistant."""

    revision: int
    scene: Scene
    content: SignContent
