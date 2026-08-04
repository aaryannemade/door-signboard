"""Default content displayed by the door signboard."""

from dataclasses import dataclass

from .scenes import Scene

APARTMENT_NUMBER = "Tower 4 / 702"
DELIVERY_MESSAGE = "Please leave deliveries at the door."
AWAY_MESSAGE = "We're away right now. Please call if it is urgent."
BUSY_MESSAGE = "Please do not disturb. I'm currently busy."
NAME = "Nemade"
PHONE_NUMBER = "000 000 0000"


@dataclass(frozen=True)
class SignContent:
    """Content values used to populate each scene layout."""

    apartment_number: str = APARTMENT_NUMBER
    delivery_message: str = DELIVERY_MESSAGE
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
