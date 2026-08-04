"""Default content displayed by the door signboard."""

from dataclasses import dataclass
from enum import Enum


class Scene(str, Enum):
    DEFAULT = "default"
    DELIVERY = "delivery"
    AWAY = "away"
    BUSY = "busy"

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
        """Return the message associated with a scene."""

        return {
            Scene.DELIVERY: self.delivery_message,
            Scene.AWAY: self.away_message,
            Scene.BUSY: self.busy_message,
        }[scene]

    def formatted_phone_number(self) -> str:
        """Format an unspaced phone number as +XX XXXXX XXXXX."""

        digits = self.phone_number.removeprefix("+")
        if len(digits) != 12 or not digits.isdigit():
            raise ValueError("Phone number must contain exactly 12 digits")
        return f"+{digits[:2]} {digits[2:7]} {digits[7:]}"
