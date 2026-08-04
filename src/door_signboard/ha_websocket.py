"""Home Assistant WebSocket event client for the Raspberry Pi."""

import asyncio
from collections.abc import Awaitable, Callable
import json
import logging
from typing import Any

from websockets.asyncio.client import ClientConnection, connect

from .config import HomeAssistantConfig
from .constants import DesiredState, Scene, SignContent

logger = logging.getLogger(__name__)

WS_SUBSCRIBE = "door_signboard/subscribe"
WS_STATUS = "door_signboard/status"

StateHandler = Callable[[DesiredState], Awaitable[None]]

FIELD_LIMITS = {
    "apartment_number": 32,
    "name": 64,
    "phone_number": 13,
    "delivery_message": 160,
    "delivery_otp": 32,
    "away_message": 160,
    "busy_message": 160,
}


def parse_desired_state(
    payload: dict[str, Any],
    device_id: str,
    last_revision: int = -1,
) -> DesiredState | None:
    """Validate a desired-state event and ignore unrelated or stale events."""

    if payload.get("device_id") != device_id:
        return None
    revision = payload.get("revision")
    if not isinstance(revision, int) or revision < 0:
        raise ValueError("revision must be a non-negative integer")
    if revision <= last_revision:
        return None

    try:
        scene = Scene(payload["scene"])
    except (KeyError, ValueError) as error:
        raise ValueError("scene is missing or unsupported") from error

    values: dict[str, str] = {}
    for field, maximum in FIELD_LIMITS.items():
        value = payload.get(field)
        if not isinstance(value, str):
            raise ValueError(f"{field} must be text")
        value = value.strip()
        if any(character in value for character in ("\x00", "\r", "\n")):
            raise ValueError(f"{field} must be a single line")
        if field != "delivery_otp" and not value:
            raise ValueError(f"{field} cannot be empty")
        if len(value) > maximum:
            raise ValueError(f"{field} exceeds {maximum} characters")
        values[field] = value

    content = SignContent(
        apartment_number=values["apartment_number"],
        name=values["name"],
        phone_number=values["phone_number"],
        delivery_message=values["delivery_message"],
        delivery_otp=values["delivery_otp"] or None,
        away_message=values["away_message"],
        busy_message=values["busy_message"],
    )
    content.formatted_phone_number()
    return DesiredState(revision=revision, scene=scene, content=content)


class HomeAssistantWebSocketClient:
    """Maintain an authenticated subscription to signboard desired state."""

    def __init__(
        self,
        config: HomeAssistantConfig,
        state_handler: StateHandler,
        *,
        heartbeat_seconds: float = 30,
        reconnect_max_seconds: float = 30,
    ) -> None:
        self.config = config
        self._state_handler = state_handler
        self._heartbeat_seconds = heartbeat_seconds
        self._reconnect_max_seconds = reconnect_max_seconds
        self._websocket: ClientConnection | None = None
        self._send_lock = asyncio.Lock()
        self._stopped = asyncio.Event()
        self._next_id = 1
        self._last_revision = -1

    async def run_forever(self) -> None:
        delay = 1.0
        while not self._stopped.is_set():
            try:
                await self._run_session()
                delay = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if self._stopped.is_set():
                    break
                logger.warning("Home Assistant WebSocket disconnected: %s", error)
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=delay)
                except TimeoutError:
                    pass
                delay = min(delay * 2, self._reconnect_max_seconds)

    async def stop(self) -> None:
        self._stopped.set()
        websocket = self._websocket
        if websocket is not None:
            try:
                await self.report_status("offline")
            except Exception as error:
                logger.warning("Failed to report offline status: %s", error)
            finally:
                await websocket.close()

    async def report_applied(self, state: DesiredState) -> None:
        await self.report_status(
            "applied", revision=state.revision, scene=state.scene.value
        )

    async def report_error(self, revision: int, error: str) -> None:
        await self.report_status("error", revision=revision, error=error[:255])

    async def report_status(self, status: str, **data: Any) -> None:
        websocket = self._websocket
        if websocket is None:
            return
        await self._send_command(
            websocket,
            WS_STATUS,
            device_id=self.config.device_id,
            status=status,
            **data,
        )

    async def _run_session(self) -> None:
        async with connect(
            self.config.websocket_url(),
            ping_interval=20,
            ping_timeout=20,
        ) as websocket:
            await self._authenticate(websocket)
            self._websocket = websocket
            subscription_id = await self._send_command(
                websocket,
                WS_SUBSCRIBE,
                device_id=self.config.device_id,
            )
            await self._expect_success(websocket, subscription_id)
            # The first event in each session is HA's canonical current state.
            # Reconsider it so a previous display or status failure can recover.
            self._last_revision = -1
            await self.report_status("online")
            heartbeat = asyncio.create_task(self._heartbeat())
            try:
                async for raw_message in websocket:
                    await self._handle_message(raw_message, subscription_id)
            finally:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
                self._websocket = None

    async def _authenticate(self, websocket: ClientConnection) -> None:
        required = json.loads(await websocket.recv())
        if required.get("type") != "auth_required":
            raise ConnectionError("Home Assistant did not request authentication")
        await websocket.send(
            json.dumps({"type": "auth", "access_token": self.config.token})
        )
        result = json.loads(await websocket.recv())
        if result.get("type") != "auth_ok":
            raise PermissionError(result.get("message", "Home Assistant auth failed"))

    async def _handle_message(self, raw_message: str, subscription_id: int) -> None:
        message = json.loads(raw_message)
        if message.get("type") != "event" or message.get("id") != subscription_id:
            return
        event_data = message.get("event", {})
        try:
            state = parse_desired_state(
                event_data,
                self.config.device_id,
                self._last_revision,
            )
            if state is None:
                return
            self._last_revision = state.revision
            await self._state_handler(state)
        except (TypeError, ValueError) as error:
            revision = event_data.get("revision", -1)
            logger.warning("Rejected Home Assistant desired state: %s", error)
            await self.report_error(
                revision if isinstance(revision, int) else -1,
                str(error),
            )

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_seconds)
            await self.report_status("heartbeat")

    async def _send_command(
        self, websocket: ClientConnection, command_type: str, **data: Any
    ) -> int:
        async with self._send_lock:
            message_id = self._next_id
            self._next_id += 1
            await websocket.send(
                json.dumps({"id": message_id, "type": command_type, **data})
            )
            return message_id

    async def _expect_success(
        self, websocket: ClientConnection, message_id: int
    ) -> None:
        while True:
            message = json.loads(await websocket.recv())
            if message.get("type") == "result" and message.get("id") == message_id:
                if not message.get("success"):
                    raise ConnectionError(message.get("error", {}).get("message"))
                return
