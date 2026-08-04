import json
import unittest
from unittest.mock import patch

from door_signboard import Scene
from door_signboard.config import HomeAssistantConfig
from door_signboard.ha_websocket import (
    HomeAssistantWebSocketClient,
    WS_STATUS,
    parse_desired_state,
)


def desired_payload(**overrides):
    payload = {
        "device_id": "door_signboard",
        "revision": 1,
        "scene": "delivery",
        "apartment_number": "Tower X / XXX",
        "name": "Resident",
        "phone_number": "911234567890",
        "delivery_message": "Please leave deliveries on the table",
        "delivery_otp": "123456",
        "away_message": "No one is home",
        "busy_message": "Please do not disturb",
    }
    payload.update(overrides)
    return payload


class DesiredStateTests(unittest.TestCase):
    def test_parses_complete_desired_state(self) -> None:
        state = parse_desired_state(desired_payload(), "door_signboard")

        self.assertEqual(state.revision, 1)
        self.assertEqual(state.scene, Scene.DELIVERY)
        self.assertEqual(state.content.delivery_otp, "123456")

    def test_ignores_other_devices_and_stale_revisions(self) -> None:
        self.assertIsNone(
            parse_desired_state(desired_payload(device_id="other"), "door_signboard")
        )
        self.assertIsNone(
            parse_desired_state(desired_payload(revision=2), "door_signboard", 2)
        )

    def test_rejects_invalid_phone(self) -> None:
        with self.assertRaisesRegex(ValueError, "12 digits"):
            parse_desired_state(desired_payload(phone_number="123"), "door_signboard")


class FakeWebSocket:
    def __init__(self, incoming, *, fail_send=False):
        self.incoming = [json.dumps(message) for message in incoming]
        self.sent = []
        self.fail_send = fail_send
        self.closed = False
        self.events = []

    async def recv(self):
        return self.incoming.pop(0)

    async def send(self, message):
        if self.fail_send:
            raise ConnectionError("disconnected")
        self.sent.append(json.loads(message))

    async def close(self):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.events:
            raise StopAsyncIteration
        return json.dumps(self.events.pop(0))


class FakeConnectionContext:
    def __init__(self, websocket):
        self.websocket = websocket

    async def __aenter__(self):
        return self.websocket

    async def __aexit__(self, *args):
        return False


class WebSocketClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_authenticates_without_logging_or_sending_token_later(self) -> None:
        websocket = FakeWebSocket([{"type": "auth_required"}, {"type": "auth_ok"}])
        client = HomeAssistantWebSocketClient(
            HomeAssistantConfig("http://ha.local:8123", "secret-token"),
            self._handle_state,
        )

        await client._authenticate(websocket)

        self.assertEqual(
            websocket.sent,
            [{"type": "auth", "access_token": "secret-token"}],
        )

    async def test_handles_event_once_and_ignores_stale_repeat(self) -> None:
        self.states = []
        client = HomeAssistantWebSocketClient(
            HomeAssistantConfig("http://ha.local:8123", "token"),
            self._handle_state,
        )
        message = json.dumps(
            {
                "id": 1,
                "type": "event",
                "event": desired_payload(),
            }
        )

        await client._handle_message(message, 1)
        await client._handle_message(message, 1)

        self.assertEqual(len(self.states), 1)

    async def test_reports_status_through_integration_command(self) -> None:
        websocket = FakeWebSocket([])
        client = HomeAssistantWebSocketClient(
            HomeAssistantConfig("http://ha.local:8123", "token"),
            self._handle_state,
        )
        client._websocket = websocket

        await client.report_status("heartbeat")

        self.assertEqual(
            websocket.sent,
            [
                {
                    "id": 1,
                    "type": WS_STATUS,
                    "device_id": "door_signboard",
                    "status": "heartbeat",
                }
            ],
        )

    async def test_stop_closes_socket_when_offline_report_fails(self) -> None:
        websocket = FakeWebSocket([], fail_send=True)
        client = HomeAssistantWebSocketClient(
            HomeAssistantConfig("http://ha.local:8123", "token"),
            self._handle_state,
        )
        client._websocket = websocket

        await client.stop()

        self.assertTrue(websocket.closed)
        self.assertTrue(client._stopped.is_set())

    async def test_reconnect_reconsiders_current_revision(self) -> None:
        websocket = FakeWebSocket(
            [
                {"type": "auth_required"},
                {"type": "auth_ok"},
                {"type": "result", "id": 1, "success": True},
            ]
        )
        websocket.events = [
            {"id": 1, "type": "event", "event": desired_payload()}
        ]
        self.states = []
        client = HomeAssistantWebSocketClient(
            HomeAssistantConfig("http://ha.local:8123", "token"),
            self._handle_state,
        )
        client._last_revision = 1

        with patch(
            "door_signboard.ha_websocket.connect",
            return_value=FakeConnectionContext(websocket),
        ):
            await client._run_session()

        self.assertEqual([state.revision for state in self.states], [1])

    async def _handle_state(self, state) -> None:
        if hasattr(self, "states"):
            self.states.append(state)


if __name__ == "__main__":
    unittest.main()
