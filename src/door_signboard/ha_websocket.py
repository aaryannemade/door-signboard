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

# Custom WebSocket command types registered by the HA integration.
WS_SUBSCRIBE = "door_signboard/subscribe"
WS_STATUS = "door_signboard/status"

# Async callback invoked with each accepted desired state (DisplayOrchestrator.submit).
StateHandler = Callable[[DesiredState], Awaitable[None]]

# Maximum accepted length (characters) per text field, to reject oversized input.
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
    """Validate a desired-state event into a DesiredState, or return None.

    Returns None (silently skip) when the event is for another device or is not
    newer than ``last_revision``. Raises ValueError on malformed content so the
    caller can report the error back to Home Assistant.
    """

    # Ignore events addressed to a different signboard device.
    if payload.get("device_id") != device_id:
        return None
    revision = payload.get("revision")
    if not isinstance(revision, int) or revision < 0:
        raise ValueError("revision must be a non-negative integer")
    # Drop stale/duplicate revisions we have already processed.
    if revision <= last_revision:
        return None

    try:
        scene = Scene(payload["scene"])
    except (KeyError, ValueError) as error:
        raise ValueError("scene is missing or unsupported") from error

    # Validate every text field: correct type, single line, within length, and
    # non-empty (except the optional OTP).
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
        # Empty OTP string means "no OTP"; normalize it to None.
        delivery_otp=values["delivery_otp"] or None,
        away_message=values["away_message"],
        busy_message=values["busy_message"],
    )
    # Validate the phone number format now (raises on bad input) so we fail
    # here rather than later during rendering.
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
        # Serializes concurrent sends (status reports vs. commands) on one socket.
        self._send_lock = asyncio.Lock()
        self._stopped = asyncio.Event()
        # Monotonically increasing id required by the HA WebSocket protocol.
        self._next_id = 1
        # Highest revision handled so far; -1 means "accept the next event".
        self._last_revision = -1

    async def run_forever(self) -> None:
        """Connect and stay connected, reconnecting with exponential backoff."""

        delay = 1.0
        while not self._stopped.is_set():
            try:
                await self._run_session()
                delay = 1.0  # Clean return: reset backoff for next time.
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if self._stopped.is_set():
                    break
                logger.warning("Home Assistant WebSocket disconnected: %s", error)
                # Wait `delay` seconds before retrying, but wake immediately if
                # asked to stop.
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=delay)
                except TimeoutError:
                    pass
                # Double the backoff up to the configured cap.
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
        """Run one connection: authenticate, subscribe, then stream events."""

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
            # HA re-sends its current state as the first event on every new
            # subscription. Reset to -1 so we re-apply it even if the revision
            # is unchanged, letting a prior display/report failure self-heal.
            self._last_revision = -1
            await self.report_status("online")
            # Send periodic heartbeats so HA can detect a silently dead link.
            heartbeat = asyncio.create_task(self._heartbeat())
            try:
                # Process events until the socket closes or an error is raised.
                async for raw_message in websocket:
                    await self._handle_message(raw_message, subscription_id)
            finally:
                # Always stop the heartbeat and clear the socket on the way out.
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
        """Dispatch one incoming message; only our subscription events matter."""

        message = json.loads(raw_message)
        # Ignore anything that is not an event for our subscription (e.g. the
        # command results handled elsewhere).
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
                return  # Wrong device or stale revision: nothing to do.
            self._last_revision = state.revision
            await self._state_handler(state)
        except (TypeError, ValueError) as error:
            # Malformed content: report it back so HA surfaces the error, but
            # keep the connection alive for the next (hopefully valid) event.
            revision = event_data.get("revision", -1)
            logger.warning("Rejected Home Assistant desired state: %s", error)
            await self.report_error(
                revision if isinstance(revision, int) else -1,
                str(error),
            )

    async def _heartbeat(self) -> None:
        # Periodically tell HA we are alive; cancelled when the session ends.
        while True:
            await asyncio.sleep(self._heartbeat_seconds)
            await self.report_status("heartbeat")

    async def _send_command(
        self, websocket: ClientConnection, command_type: str, **data: Any
    ) -> int:
        """Send a command with a unique id and return that id."""

        # Lock so the id counter and the socket write stay consistent when
        # commands and status reports are sent concurrently.
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
        """Read messages until the result for ``message_id`` arrives.

        Raises ConnectionError if that command failed. Intermediate messages
        (for other ids) are skipped.
        """

        while True:
            message = json.loads(await websocket.recv())
            if message.get("type") == "result" and message.get("id") == message_id:
                if not message.get("success"):
                    raise ConnectionError(message.get("error", {}).get("message"))
                return
