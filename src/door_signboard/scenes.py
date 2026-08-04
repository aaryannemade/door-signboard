"""Available signboard scenes."""

from enum import Enum

class Scene(str, Enum):
    DEFAULT = "default"
    DELIVERY = "delivery"
    AWAY = "away"
    BUSY = "busy"
