from types import SimpleNamespace
import tempfile
import unittest

try:
    from custom_components.door_signboard.const import (
        DEFAULT_STATE,
        DEFAULT_STATUS,
        DOMAIN,
    )
    from custom_components.door_signboard.coordinator import DoorSignboardCoordinator
    from custom_components.door_signboard.websocket_api import (
        websocket_status,
        websocket_subscribe,
    )
    from homeassistant.core import HomeAssistant
except ImportError:
    DEFAULT_STATE = None
    DEFAULT_STATUS = None
    DOMAIN = None
    DoorSignboardCoordinator = None
    HomeAssistant = None
    websocket_status = None
    websocket_subscribe = None


class FakeCoordinator:
    def __init__(self) -> None:
        self.state = {
            "revision": 1,
            "scene": "default",
            "apartment_number": "Tower X / XXX",
            "name": "Resident",
            "phone_number": "911234567890",
            "delivery_message": "Delivery message",
            "delivery_otp": "",
            "away_message": "Away message",
            "busy_message": "Busy message",
        }
        self.status_reports = []

    def async_subscribe_desired(self, listener):
        self.listener = listener
        return lambda: None

    def async_handle_status(self, data):
        self.status_reports.append(data)


class FakeConnection:
    def __init__(self) -> None:
        self.subscriptions = {}
        self.results = []
        self.errors = []
        self.messages = []

    def send_result(self, message_id):
        self.results.append(message_id)

    def send_error(self, message_id, code, message):
        self.errors.append((message_id, code, message))

    def send_message(self, message):
        self.messages.append(message)


@unittest.skipIf(DOMAIN is None, "Home Assistant runtime is not installed")
class ComponentWebSocketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator = FakeCoordinator()
        self.hass = SimpleNamespace(data={DOMAIN: {"entry": self.coordinator}})
        self.connection = FakeConnection()

    def test_subscription_returns_initial_complete_state(self) -> None:
        websocket_subscribe(
            self.hass,
            self.connection,
            {
                "id": 1,
                "type": "door_signboard/subscribe",
                "device_id": "door_signboard",
            },
        )

        self.assertEqual(self.connection.results, [1])
        self.assertIn(1, self.connection.subscriptions)
        self.assertEqual(self.connection.messages[0]["event"]["revision"], 1)
        self.assertEqual(
            self.connection.messages[0]["event"]["apartment_number"],
            "Tower X / XXX",
        )

    def test_status_command_reaches_coordinator(self) -> None:
        message = {
            "id": 2,
            "type": "door_signboard/status",
            "device_id": "door_signboard",
            "status": "heartbeat",
        }

        websocket_status(self.hass, self.connection, message)

        self.assertEqual(self.connection.results, [2])
        self.assertEqual(self.coordinator.status_reports, [message])


@unittest.skipIf(DOMAIN is None, "Home Assistant runtime is not installed")
class CoordinatorRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_update_increments_revision_and_notifies_subscriber(self) -> None:
        coordinator = object.__new__(DoorSignboardCoordinator)
        coordinator.state = dict(DEFAULT_STATE)
        coordinator.status = dict(DEFAULT_STATUS)
        coordinator._desired_listeners = set()
        coordinator._changed = lambda: None
        notifications = []
        coordinator.async_subscribe_desired(lambda: notifications.append(True))

        await coordinator.async_update_field("scene", "away")
        await coordinator.async_update_field("scene", "away")

        self.assertEqual(coordinator.state["revision"], 1)
        self.assertEqual(notifications, [True])

    async def test_coordinator_loads_and_persists_with_home_assistant(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            hass = HomeAssistant(directory)
            coordinator = DoorSignboardCoordinator(
                hass,
                SimpleNamespace(
                    entry_id="test-entry",
                    async_on_unload=lambda callback: None,
                ),
            )

            await coordinator.async_load()
            await coordinator.async_update_field("scene", "busy")

            self.assertEqual(coordinator.state["revision"], 1)
            self.assertEqual(coordinator.state["scene"], "busy")
            await hass.async_stop(force=True)


if __name__ == "__main__":
    unittest.main()
